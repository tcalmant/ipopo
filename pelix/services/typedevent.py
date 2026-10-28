#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
A Typed Event bus for Pelix, inspired by the OSGi Typed Event specification:
events are dataclass instances, handlers receive the type they declare

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.3.0

..

    Copyright 2026 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import collections
import dataclasses
import importlib
import logging
import threading
import time
import typing
from collections.abc import Iterable, Mapping
from typing import Any, cast

import pelix.constants
import pelix.framework
import pelix.ldapfilter
import pelix.services
import pelix.threadpool
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Validate
from pelix.services import MonitorEvent
from pelix.services.eventdelivery import (
    EventDeliveryError,
    EventProperties,
    OrderedDelivery,
    is_valid_topic,
    is_valid_topic_scope,
    topic_matches,
)
from pelix.utilities import to_iterable

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["TypedEventAdmin", "default_topic", "event_to_map", "map_to_event"]

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# Handler kinds
_TYPED = "typed"
_UNTYPED = "untyped"
_UNHANDLED = "unhandled"

# ------------------------------------------------------------------------------


def default_topic(event_type: type) -> str:
    """
    Computes the default topic of an event type, as in OSGi Typed Event 157.3.2:
    its fully qualified name, with ``.`` replaced by ``/``

    :param event_type: A class
    :return: The topic, e.g. ``argos/events/ChunkChanged``
    :raise ValueError: The name of the class can't make a topic (local class)
    """
    topic = f"{event_type.__module__}.{event_type.__qualname__}".replace(".", "/")
    if not is_valid_topic(topic):
        raise ValueError(f"No default topic for {event_type!r}: give a topic explicitly")
    return topic


def event_to_map(event: object) -> dict[str, Any]:
    """
    Converts a dataclass instance to a dictionary of its fields (not recursive)

    :param event: A dataclass instance
    :raise TypeError: Not a dataclass instance
    """
    if isinstance(event, type) or not dataclasses.is_dataclass(event):
        raise TypeError(f"A typed event must be a dataclass instance, not {type(event).__name__}")
    return {field.name: getattr(event, field.name) for field in dataclasses.fields(event)}


def map_to_event(event_type: Any, data: Mapping[str, Any]) -> Any:
    """
    Converts event data to an event type: a dataclass is built from the fields it
    declares, extra keys being ignored; ``dict``, ``Mapping`` and ``Any`` get the data as is.

    :param event_type: The target type
    :param data: Event data
    :raise TypeError: Unsupported type, or a field without default is missing
    """
    if event_type in (Any, object, dict, Mapping):
        return data

    if isinstance(event_type, type) and dataclasses.is_dataclass(event_type):
        kwargs = {f.name: data[f.name] for f in dataclasses.fields(event_type) if f.init and f.name in data}
        return event_type(**kwargs)

    raise TypeError(f"Can't convert event data to {event_type!r}")


def _import_type(name: str) -> Any:
    """
    Finds a class from its fully qualified name

    :raise ImportError: Not found
    """
    parts = name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        try:
            obj: Any = importlib.import_module(".".join(parts[:i]))
            for attr in parts[i:]:
                obj = getattr(obj, attr)
            return obj
        except (ImportError, AttributeError):
            continue
    raise ImportError(f"Unknown type {name!r}")


class _Target(typing.NamedTuple):
    """
    A handler selected for an event
    """

    kind: str
    ref: ServiceReference[Any]
    event_type: Any


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.services.FACTORY_TYPED_EVENT_BUS)
@Provides([pelix.services.SERVICE_TYPED_EVENT_BUS, pelix.services.SERVICE_TYPED_EVENT_MONITOR])
@Property("_nb_threads", "pool.threads", 10)
@Property("_history_size", pelix.services.PROP_TYPED_EVENT_HISTORY_SIZE, 0)
class TypedEventAdmin(pelix.services.TypedEventBus, pelix.services.TypedEventMonitor):
    """
    The Typed Event bus implementation
    """

    def __init__(self) -> None:
        self._context: pelix.framework.BundleContext | None = None
        self._nb_threads: int = 10
        self._history_size: int = 0
        self._pool: pelix.threadpool.ThreadPool | None = None
        self._delivery: OrderedDelivery | None = None

        # Handler types, by service ID (None: unusable handler, already reported)
        self._types: dict[Any, Any] = {}
        self._types_lock = threading.Lock()

        self._history: collections.deque[MonitorEvent] = collections.deque(maxlen=1)
        self._history_lock = threading.Lock()

    # --------------------------------------------------------------------------
    # Handler selection

    def _handler_type(self, context: pelix.framework.BundleContext, ref: ServiceReference[Any]) -> Any:
        """
        Finds the event type of a typed handler: its ``event.type`` property, or the
        annotation of the ``event`` parameter of its ``notify()`` method

        :return: The type, or None if the handler is unusable (reported once)
        """
        svc_id = ref.get_property(pelix.constants.SERVICE_ID)
        with self._types_lock:
            if svc_id in self._types:
                return self._types[svc_id]

        event_type: Any = None
        try:
            declared = ref.get_property(pelix.services.PROP_EVENT_TYPE)
            if isinstance(declared, str):
                event_type = _import_type(declared)
            elif declared is not None:
                event_type = declared
            else:
                handler = context.get_service(ref)
                try:
                    event_type = typing.get_type_hints(handler.notify)["event"]
                finally:
                    context.unget_service(ref)

            if isinstance(event_type, type) and not ref.get_property(pelix.services.PROP_EVENT_TOPICS):
                # Fails here on a local class, instead of in every delivery
                default_topic(event_type)
        except Exception:
            _logger.warning(
                "Ignoring typed event handler %s: no usable event.type nor annotated 'event' parameter",
                svc_id,
                exc_info=True,
            )
            event_type = None

        with self._types_lock:
            self._types[svc_id] = event_type
        return event_type

    @staticmethod
    def _scopes(ref: ServiceReference[Any]) -> list[str]:
        """
        Lists the valid topic scopes of a handler (invalid ones are reported and ignored)
        """
        scopes: list[str] = []
        for scope in cast(
            Iterable[str], to_iterable(ref.get_property(pelix.services.PROP_EVENT_TOPICS), False)
        ):
            if is_valid_topic_scope(scope):
                scopes.append(scope)
            else:
                _logger.warning(
                    "Ignoring invalid topic scope %r of handler %s",
                    scope,
                    ref.get_property(pelix.constants.SERVICE_ID),
                )
        return scopes

    def _select(
        self, context: pelix.framework.BundleContext, topic: str, data: Mapping[str, Any]
    ) -> list[_Target]:
        """
        Finds the typed and untyped handlers an event is for. Without any, the
        unhandled event handlers are returned.
        """
        # The topic is a property of the event (OSGi 113.3.2), which filters can test
        filter_props = {**data, pelix.services.PROP_EVENT_TOPICS: topic}

        targets: list[_Target] = []
        alive: set[Any] = set()
        for kind, spec in (
            (_TYPED, pelix.services.TypedEventHandler),
            (_UNTYPED, pelix.services.UntypedEventHandler),
        ):
            for ref in context.get_all_service_references(spec, None) or ():
                alive.add(ref.get_property(pelix.constants.SERVICE_ID))
                event_type = None
                if kind == _TYPED:
                    event_type = self._handler_type(context, ref)
                    if event_type is None:
                        continue

                    scopes = self._scopes(ref) or (
                        [default_topic(event_type)] if isinstance(event_type, type) else []
                    )
                else:
                    scopes = self._scopes(ref)

                if not any(topic_matches(scope, topic) for scope in scopes):
                    continue

                ldap_filter = ref.get_property(pelix.services.PROP_EVENT_FILTER)
                try:
                    parsed = pelix.ldapfilter.get_ldap_filter(ldap_filter)
                except (ValueError, TypeError):
                    _logger.warning("Ignoring handler %s: invalid filter %r", ref, ldap_filter)
                    continue

                if parsed is None or parsed.matches(filter_props):
                    targets.append(_Target(kind, ref, event_type))

        with self._types_lock:
            for svc_id in set(self._types) - alive:
                del self._types[svc_id]

        if not targets:
            targets = [
                _Target(_UNHANDLED, ref, None)
                for ref in context.get_all_service_references(pelix.services.UnhandledEventHandler, None)
                or ()
            ]
        return targets

    # --------------------------------------------------------------------------
    # Delivery

    @staticmethod
    def _notify(
        context: pelix.framework.BundleContext,
        target: _Target,
        topic: str,
        event: object | None,
        data: Mapping[str, Any],
        errors: list[tuple[Any, Exception]] | None,
    ) -> None:
        """
        Calls one handler, reporting its failure in ``errors`` if given
        """
        svc_id = target.ref.get_property(pelix.constants.SERVICE_ID)
        try:
            handler = context.get_service(target.ref)
        except pelix.constants.BundleException:
            # Handler gone since the selection
            return

        try:
            if target.kind == _TYPED:
                if (
                    event is not None
                    and isinstance(target.event_type, type)
                    and isinstance(event, target.event_type)
                ):
                    # Same object: an identity (a handle) crosses the bus
                    handler.notify(topic, event)
                else:
                    handler.notify(topic, map_to_event(target.event_type, data))
            elif target.kind == _UNTYPED:
                handler.notify_untyped(topic, data)
            else:
                handler.notify_unhandled(topic, data)
        except Exception as ex:
            _logger.exception("Error notifying typed event handler %s", svc_id)
            if errors is not None:
                errors.append((svc_id, ex))
        finally:
            context.unget_service(target.ref)

    def _publish(
        self, topic: str, event: object | None, data: dict[str, Any], sync: bool, raise_errors: bool
    ) -> None:
        if not is_valid_topic(topic):
            raise ValueError(f"Invalid event topic: {topic!r}")

        # Read once: the component can be invalidated by another thread meanwhile
        context, delivery = self._context, self._delivery
        if context is None or delivery is None:
            raise RuntimeError("The typed event bus is not validated")

        shared = EventProperties(data)
        self._record(topic, shared)

        targets = self._select(context, topic, shared)
        if sync:
            errors: list[tuple[Any, Exception]] | None = [] if raise_errors else None
            for target in targets:
                self._notify(context, target, topic, event, shared, errors)
            if errors:
                raise EventDeliveryError(topic, errors)
            return

        for target in targets:

            def task(target: _Target = target) -> None:
                self._notify(context, target, topic, event, shared, None)

            delivery.submit(target.ref.get_property(pelix.constants.SERVICE_ID), task)

    def deliver(
        self, event: object, topic: str | None = None, *, sync: bool = False, raise_errors: bool = False
    ) -> None:
        data = event_to_map(event)
        if topic is None:
            topic = default_topic(type(event))
        self._publish(topic, event, data, sync, raise_errors)

    def deliver_untyped(
        self,
        topic: str,
        data: Mapping[str, Any],
        *,
        sync: bool = False,
        raise_errors: bool = False,
    ) -> None:
        self._publish(topic, None, dict(data), sync, raise_errors)

    # --------------------------------------------------------------------------
    # Monitor

    def _record(self, topic: str, data: Mapping[str, Any]) -> None:
        if self._history_size > 0:
            with self._history_lock:
                self._history.append(MonitorEvent(topic, data, time.time()))

    def history(self, count: int | None = None) -> list[MonitorEvent]:
        with self._history_lock:
            events = list(self._history)
        return events if count is None else events[-count:] if count > 0 else []

    # --------------------------------------------------------------------------
    # Life cycle

    @Validate
    def validate(self, context: pelix.framework.BundleContext) -> None:
        """
        Component validated
        """
        self._context = context

        try:
            self._nb_threads = max(int(self._nb_threads), 2)
        except (TypeError, ValueError):
            self._nb_threads = 10

        try:
            size = max(int(self._history_size), 0)
        except (TypeError, ValueError):
            size = 0
        self._history_size = size
        self._history = collections.deque(maxlen=max(size, 1))

        self._pool = pelix.threadpool.ThreadPool(self._nb_threads, logname="typedevent-pool")
        self._pool.start()
        self._delivery = OrderedDelivery(self._pool)

    @Invalidate
    def invalidate(self, context: pelix.framework.BundleContext) -> None:
        """
        Component invalidated
        """
        if self._delivery is not None:
            self._delivery.clear()
            self._delivery = None

        if self._pool is not None:
            self._pool.stop()
            self._pool = None

        self._context = None
        with self._types_lock:
            self._types.clear()
