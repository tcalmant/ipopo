#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Helpers shared by the event services (EventAdmin and Typed Event):
ordered asynchronous delivery, immutable event properties and topic matching

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
import contextvars
import logging
import re
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any, Self

import pelix.threadpool

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "EventDeliveryError",
    "EventProperties",
    "OrderedDelivery",
    "is_valid_topic",
    "is_valid_topic_scope",
    "topic_matches",
]

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# OSGi Event Admin 113.3.1: topic ::= token ( '/' token )*, a token being made of
# alphanumeric characters, underscores and hyphens
_TOPIC = re.compile(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*")

# ------------------------------------------------------------------------------


def is_valid_topic(topic: str) -> bool:
    """
    Tests if the given string is a valid OSGi topic (``token ( '/' token )*``)

    :param topic: A topic
    :return: True if the topic is valid
    """
    return isinstance(topic, str) and _TOPIC.fullmatch(topic) is not None


def is_valid_topic_scope(scope: str) -> bool:
    """
    Tests if the given string is a valid OSGi topic scope: ``*``, a topic,
    or a topic followed by ``/*``

    :param scope: A topic scope, as given by an event handler
    :return: True if the scope is valid
    """
    if scope == "*":
        return True

    if isinstance(scope, str) and scope.endswith("/*"):
        scope = scope[:-2]

    return is_valid_topic(scope)


def topic_matches(scope: str, topic: str) -> bool:
    """
    Tests if a topic matches a topic scope, as defined in the OSGi
    Event Admin specification (113.4): ``a/b`` matches only ``a/b``,
    ``a/b/*`` matches every topic below ``a/b`` but not ``a/b`` itself and
    ``*`` matches everything. Matching is case-sensitive.

    :param scope: A topic scope, as given by an event handler
    :param topic: The topic of an event
    :return: True if the topic is in the scope
    """
    if scope == "*":
        return True

    if scope.endswith("/*"):
        return topic.startswith(scope[:-1])

    return scope == topic


# ------------------------------------------------------------------------------


class EventDeliveryError(ExceptionGroup):
    """
    Raised by a synchronous delivery, when asked to, if at least one handler failed.

    All the handlers have been notified when it is raised: it groups their
    exceptions, and ``errors`` gives the service ID of the handler of each one.
    """

    def __new__(cls, topic: str, errors: list[tuple[Any, Exception]]) -> Self:
        # ExceptionGroup takes its message and exceptions in __new__
        return super().__new__(cls, f"Handlers failed on event {topic!r}", [ex for _, ex in errors])

    def __init__(self, topic: str, errors: list[tuple[Any, Exception]]) -> None:
        """
        :param topic: Topic of the event
        :param errors: A list of (service ID of the handler, exception) tuples
        """
        # Keeps these arguments in args, as pickle gives them back to __new__: the
        # base __init__ accepts anything, whatever the stubs say
        super().__init__(topic, errors)  # ty: ignore[invalid-argument-type]
        self.topic = topic
        self.errors = errors

    def derive(self, excs: Sequence[Exception]) -> "EventDeliveryError":
        # Called by split() and except*: keeps the topic and the handler of each exception.
        # They come in their original order, but a nested group comes as a new group, with
        # the traceback of the original one
        remaining = iter(self.errors)
        errors = []
        for ex in excs:
            sid = next(sid for sid, orig in remaining if orig is ex or orig.__traceback__ is ex.__traceback__)
            errors.append((sid, ex))
        return EventDeliveryError(self.topic, errors)


class EventProperties(Mapping[str, Any]):
    """
    An immutable view of the properties of an event, which can be shared between
    handlers without being copied (OSGi Event Admin 113.3.3).

    The mapping is immutable, not the values it holds: a mutable value stays mutable.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        """
        :param data: The initial content, which is copied
        """
        self._data: dict[str, Any] = dict(data) if data else {}

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"EventProperties({self._data!r})"


# ------------------------------------------------------------------------------


class OrderedDelivery:
    """
    Runs tasks on a thread pool, in submission order for a given key, and
    concurrently for different keys. At most one thread works for a key, so a slow
    handler never uses more than one thread of the pool.

    This is the delivery guarantee of OSGi Event Admin 113.7.3 and Typed Event
    157.3.3: the events posted by one thread reach a handler in the order they were posted.
    """

    def __init__(self, pool: pelix.threadpool.ThreadPool) -> None:
        """
        :param pool: A started thread pool
        """
        self._pool = pool
        self._lock = threading.Lock()
        self._queues: dict[Any, collections.deque[tuple[contextvars.Context, Callable[[], None]]]] = {}

    def submit(self, key: Any, task: Callable[[], None]) -> None:
        """
        Queues a task after the ones already submitted with the same key

        :param key: Ordering key (the service ID of a handler)
        :param task: Task to run, in a copy of the context of the caller
        """
        item = (contextvars.copy_context(), task)
        with self._lock:
            queue = self._queues.get(key)
            if queue is not None:
                # A thread is already draining this key
                queue.append(item)
                return

            self._queues[key] = collections.deque((item,))

        self._pool.enqueue(self._drain, key)

    def submit_unordered(self, task: Callable[[], None]) -> None:
        """
        Queues a task which can run at any moment, in any order

        :param task: Task to run, in a copy of the context of the caller
        """
        self._pool.enqueue(self._run, task)

    def clear(self) -> None:
        """
        Forgets the pending tasks
        """
        with self._lock:
            self._queues.clear()

    @staticmethod
    def _run(task: Callable[[], None]) -> None:
        try:
            task()
        except Exception:
            _logger.exception("Error in an event delivery task")

    def _drain(self, key: Any) -> None:
        """
        Runs the tasks of a key until its queue is empty
        """
        while True:
            with self._lock:
                queue = self._queues.get(key)
                if not queue:
                    # Done, or cleared: next submit starts a new drain
                    self._queues.pop(key, None)
                    return

                context, task = queue.popleft()

            try:
                context.run(task)
            except Exception:
                _logger.exception("Error in an event delivery task")
