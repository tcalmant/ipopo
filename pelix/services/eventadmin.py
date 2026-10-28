#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
An EventAdmin-like implementation for Pelix: a publish-subscribe service

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

import copy
import fnmatch
import logging
import time
from collections.abc import Iterable, Mapping
from typing import Any, cast

import pelix.constants
import pelix.framework
import pelix.ldapfilter
import pelix.services
import pelix.threadpool
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Validate
from pelix.services.eventdelivery import EventDeliveryError, EventProperties, OrderedDelivery
from pelix.utilities import to_iterable

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["EventAdmin", "EventDeliveryError", "EventProperties"]

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


@ComponentFactory(pelix.services.FACTORY_EVENT_ADMIN)
@Provides(pelix.services.EventAdmin)
@Property("_nb_threads", "pool.threads", 10)
class EventAdmin(pelix.services.EventAdmin):
    """
    The EventAdmin implementation
    """

    def __init__(self) -> None:
        # The bundle context
        self._context: pelix.framework.BundleContext | None = None

        # The framework instance UID
        self._fw_uid: str | None = None

        # Number of threads in the pool
        self._nb_threads: int = 10

        # Thread pool
        self._pool: pelix.threadpool.ThreadPool | None = None

        # Ordered delivery of the posted events, on top of the pool
        self._delivery: OrderedDelivery | None = None

    def _get_handlers_ids(self, topic: str, properties: Mapping[str, Any]) -> list[tuple[str, bool]] | None:
        """
        Retrieves the IDs of the listeners that requested to handle this event

        :param topic: Topic of the event
        :param properties: Associated properties
        :return: The (service ID, ordered) tuples of the services to call back for this event.
                 None if none found. ``ordered`` is False if the handler asked
                 for ``async.unordered`` delivery
        """
        handlers: list[tuple[str, bool]] = []

        # Get the handler service references
        assert self._context is not None
        handlers_refs = self._context.get_all_service_references(pelix.services.ServiceEventHandler, None)

        if handlers_refs is None:
            # No service found
            return None

        # The topic is a property of the event, which a filter can test (OSGi 113.3.2)
        filter_props = {**properties, pelix.services.PROP_EVENT_TOPICS: topic}

        for svc_ref in handlers_refs:
            # Check the LDAP filter
            ldap_filter = svc_ref.get_property(pelix.services.PROP_EVENT_FILTER)
            try:
                matches = self.__match_filter(filter_props, ldap_filter)
            except (ValueError, TypeError):
                # OSGi 113.4: an invalid filter is logged and the handler ignored
                _logger.warning(
                    "Ignoring event handler %s: invalid filter %r",
                    svc_ref.get_property(pelix.constants.SERVICE_ID),
                    ldap_filter,
                )
                continue

            if matches:
                # Get the service ID
                svc_id = svc_ref.get_property(pelix.constants.SERVICE_ID)
                ordered = (
                    svc_ref.get_property(pelix.services.PROP_EVENT_DELIVERY)
                    != pelix.services.DELIVERY_ASYNC_UNORDERED
                )

                # Filter matches the event, test the topic
                topics = to_iterable(svc_ref.get_property(pelix.services.PROP_EVENT_TOPICS), True)
                if not topics:
                    # Filter matches, and no topic filter given: notify it
                    handlers.append((svc_id, ordered))
                else:
                    for handled_topic in cast(Iterable[str], to_iterable(topics, False)):
                        if fnmatch.fnmatch(topic, handled_topic):
                            # Full match, keep the service ID
                            handlers.append((svc_id, ordered))
                            break

        return handlers

    @staticmethod
    def __match_filter(
        properties: Mapping[str, Any], ldap_filter: None | str | pelix.ldapfilter.LdapFilterOrCriteria
    ) -> bool:
        """
        Tests if the given properties match the given filter

        :param properties: A set of properties
        :param ldap_filter: An LDAP filter string, object or None
        :return: True if the properties match the filter
        """
        if not ldap_filter:
            # No filter
            return True

        # Normalize the filter
        ldap_filter = pelix.ldapfilter.get_ldap_filter(ldap_filter)
        return ldap_filter is None or ldap_filter.matches(cast(dict[str, Any], properties))

    def __get_service(
        self, service_id: str
    ) -> tuple[
        ServiceReference[pelix.services.ServiceEventHandler] | None,
        pelix.services.ServiceEventHandler | None,
    ]:
        """
        Retrieves the reference and the service associated to the given ID,
        or a (None, None) tuple if no service was found.

        The service must be freed with BundleContext.unget_service() after
        usage

        :param service_id: A service ID
        :return: A (reference, service) tuple or (None, None)
        """
        try:
            # Prepare the filter
            ldap_filter = f"({pelix.constants.SERVICE_ID}={service_id})"

            # Get the reference
            assert self._context is not None
            ref = self._context.get_service_reference(pelix.services.ServiceEventHandler, ldap_filter)
            if ref is None:
                # Unknown service
                return None, None

            # Get the service
            return ref, self._context.get_service(ref)
        except pelix.constants.BundleException:
            # Service disappeared
            return None, None

    def __notify_handlers(
        self,
        topic: str,
        properties: dict[str, Any],
        handlers_ids: Iterable[str],
        copy_props: bool = True,
        errors: list[tuple[Any, BaseException]] | None = None,
    ) -> None:
        """
        Notifies the handlers of an event

        :param topic: Topic of the event
        :param properties: Associated properties
        :param handlers_ids: IDs of the services to notify
        :param copy_props: If True, each handler gets a deep copy of the properties,
                           else all share an immutable EventProperties
        :param errors: If not None, the (handler ID, exception) of the failed notifications
                       are appended to it
        """
        if self._context is None:
            # No more context
            return

        shared = None if copy_props else EventProperties(properties)

        for handler_id in handlers_ids:
            # Define the "ref" variable name (and reset it on each loop)
            ref = None
            try:
                # Get the service
                ref, handler = self.__get_service(handler_id)
                if handler is not None:
                    # Use a copy of the properties each time (or the shared immutable view)
                    handler.handle_event(
                        topic,
                        cast(dict[str, Any], shared if shared is not None else copy.deepcopy(properties)),
                    )
            except Exception as ex:
                # OSGi 113.8.1: log, then go on with the other handlers
                _logger.exception("Error notifying event handler %s", handler_id)
                if errors is not None:
                    errors.append((handler_id, ex))
            finally:
                if ref is not None:
                    self._context.unget_service(ref)

    def __setup_properties(self, properties: dict[str, Any] | None) -> dict[str, Any]:
        """
        Adds the EventAdmin specific properties to the event

        :param properties: The initial event properties
        :return: A copy of the initial properties, or new ones, with the EventAdmin specific properties
        """
        # Compute the event time stamp
        timestamp = time.time()

        if not isinstance(properties, dict):
            # Create a new dictionary
            props: dict[str, Any] = {}

        else:
            # Copy the given one
            props = properties.copy()

        # ... event time stamp
        props[pelix.services.EVENT_PROP_TIMESTAMP] = timestamp

        # ... framework UID
        props[pelix.services.EVENT_PROP_FRAMEWORK_UID] = self._fw_uid

        return props

    def send(
        self,
        topic: str,
        properties: dict[str, Any] | None = None,
        *,
        copy: bool = True,
        raise_errors: bool = False,
    ) -> None:
        """
        Sends synchronously the given event: the handlers are called in the
        calling thread, before this method returns.

        :param topic: Topic of event
        :param properties: Associated properties
        :param copy: If False, the handlers get one shared immutable
                     :class:`~pelix.services.eventdelivery.EventProperties` instead
                     of a deep copy of the properties each
        :param raise_errors: If True, raise an :class:`EventDeliveryError` after all
                             the handlers have been notified, if some of them failed.
                             By default, errors are only logged (OSGi 113.8.1)
        :raise EventDeliveryError: A handler failed and ``raise_errors`` is True
        """
        # Compute properties
        properties = self.__setup_properties(properties)

        # Get the currently available handlers
        handlers = self._get_handlers_ids(topic, properties)
        if handlers:
            # Notify them
            errors: list[tuple[Any, BaseException]] | None = [] if raise_errors else None
            self.__notify_handlers(topic, properties, [h[0] for h in handlers], copy, errors)
            if errors:
                raise EventDeliveryError(topic, errors)

    def post(self, topic: str, properties: dict[str, Any] | None = None, *, copy: bool = True) -> None:
        """
        Sends asynchronously the given event.

        The events posted by a thread reach a given handler in the order they
        were posted, except for the handlers registered with the
        ``event.delivery`` property set to ``async.unordered``.

        :param topic: Topic of event
        :param properties: Associated properties
        :param copy: If False, the handlers get one shared immutable
                     :class:`~pelix.services.eventdelivery.EventProperties` instead
                     of a deep copy of the properties each
        """
        # Compute properties
        properties = self.__setup_properties(properties)

        # Get the currently available handlers
        handlers = self._get_handlers_ids(topic, properties)
        # Read once: the component can be invalidated by another thread meanwhile
        delivery = self._delivery
        if handlers and delivery is not None:
            for handler_id, ordered in handlers:
                # One task per handler: a slow handler does not delay the others
                def task(handler_id: str = handler_id) -> None:
                    self.__notify_handlers(topic, properties, [handler_id], copy)

                if ordered:
                    delivery.submit(handler_id, task)
                else:
                    delivery.submit_unordered(task)

    @Validate
    def validate(self, context: pelix.framework.BundleContext) -> None:
        """
        Component validated
        """
        # Store the bundle context
        self._context = context

        # Get the framework instance UID
        self._fw_uid = cast(str | None, context.get_property(pelix.constants.FRAMEWORK_UID))

        # Normalize properties
        try:
            self._nb_threads = int(self._nb_threads)
            self._nb_threads = max(self._nb_threads, 2)
        except ValueError:
            # Default value
            self._nb_threads = 10

        # Create the thread pool
        self._pool = pelix.threadpool.ThreadPool(self._nb_threads, logname="eventadmin-pool")
        self._pool.start()
        self._delivery = OrderedDelivery(self._pool)

    @Invalidate
    def invalidate(self, context: pelix.framework.BundleContext) -> None:
        """
        Component invalidated
        """
        # Stop the thread pool (empties its queue)
        if self._delivery is not None:
            self._delivery.clear()
            self._delivery = None

        if self._pool is not None:
            self._pool.stop()
            self._pool = None

        # Forget the bundle context
        self._context = None
        self._fw_uid = None
