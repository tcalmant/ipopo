#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix miscellaneous modules

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

import logging
from collections.abc import Iterator
from types import TracebackType
from typing import Any, Protocol, Self, TypeAlias

from pelix.constants import Specification
from pelix.framework import Bundle
from pelix.internals.registry import ServiceReference

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "FACTORY_EVENT_ADMIN_PRINTER",
    "LOG_READER_SERVICE",
    "LOG_SERVICE",
    "PROPERTY_LOG_LEVEL",
    "PROPERTY_LOG_MAX_ENTRIES",
    "LogEntry",
    "LogListener",
    "LogReader",
    "LogService",
    "LogStream",
    "OptExcInfo",
]


OptExcInfo: TypeAlias = (
    tuple[type[BaseException], BaseException, TracebackType] | tuple[None, None, None] | None
)

# ------------------------------------------------------------------------------


FACTORY_EVENT_ADMIN_PRINTER = "pelix-misc-eventadmin-printer-factory"
"""
Name of the EventAdmin printer factory.
"""

# ------------------------------------------------------------------------------

PROPERTY_LOG_LEVEL = "pelix.log.level"
"""
The log level property, which can be an integer or a string from the logging
module (default: logging.INFO)
"""

PROPERTY_LOG_MAX_ENTRIES = "pelix.log.max_entries"
"""
The maximum number of log entries to store in memory (default: 100)
"""

LOG_SERVICE = "pelix.log"
"""
The log service, providing:
- log(level, message, exception=None, reference=None): logs an entry with
  the given log level, human-readable message, exception (if any) and
  associated service reference (if any)
"""

LOG_READER_SERVICE = "pelix.log.reader"
"""
The log reader service, providing:
- add_log_listener(listener): subscribe a listener to log events
- remove_log_listener(listener): unsubscribe a listener from log events
- get_log(): returns the list of stored log entries

Log listeners must provide a ``logged(entry)`` method, accepting a ``LogEntry``
object as parameter.
"""


class LogEntry(Protocol):
    """
    Specification of a log entry
    """

    @property
    def bundle(self) -> Bundle | None:
        """
        The bundle that created this entry
        """
        ...

    @property
    def message(self) -> str | None:
        """
        The message associated to this entry
        """
        ...

    @property
    def exception(self) -> OptExcInfo:
        """
        The exception associated to this entry
        """
        ...

    @property
    def level(self) -> int:
        """
        The log level of this entry (Python constant)
        """
        ...

    @property
    def osgi_level(self) -> int:
        """
        The log level of this entry (OSGi constant)
        """
        ...

    @property
    def reference(self) -> ServiceReference[Any] | None:
        """
        The reference to the service associated to this entry
        """
        ...

    @property
    def time(self) -> float:
        """
        The timestamp of this entry
        """
        ...

    def to_record(self) -> logging.LogRecord:
        """
        Returns this entry as a ``logging.LogRecord``, to be used with a ``logging.Formatter``
        """
        ...


class LogStream(Protocol):
    """
    A bounded live feed of log entries, to be used in a ``with`` block or closed explicitly.

    Iterating blocks until an entry is available and ends once the stream is closed.
    When the consumer is slower than the log, the oldest pending entries are discarded.
    """

    def __iter__(self) -> Iterator[LogEntry]: ...

    def __next__(self) -> LogEntry: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...

    def get(self, timeout: float | None = None) -> LogEntry | None:
        """
        Returns the next entry, or None on timeout or when the stream is closed and drained
        """
        ...

    def close(self) -> None:
        """
        Stops the stream: it doesn't receive new entries
        """
        ...


@Specification("pelix.log.listener")
class LogListener(Protocol):
    """
    Specification of log listener
    """

    def logged(self, entry: LogEntry) -> None:
        """
        Logs an entry with the given log level, human-readable message, exception (if any)
        and associated service reference (if any)
        """
        ...


@Specification(LOG_READER_SERVICE)
class LogReader(Protocol):
    """
    Specification of a log reader service
    """

    def add_log_listener(self, listener: LogListener) -> None:
        """
        Subscribes a listener to log events.

        A log listener is an object providing with a ``logged`` method, with
        the following signature:

        .. code-block:: python

            def logged(self, log_entry):
                '''
                A log entry (LogEntry) has been added to the log service
                '''
                # ...

        :param listener: A new listener
        """
        ...

    def remove_log_listener(self, listener: LogListener) -> None:
        """
        Unsubscribes a listener from log events.

        :param listener: The listener to remove
        """
        ...

    def get_log(self) -> tuple[LogEntry, ...]:
        """
        Returns the logs events kept by the service

        :return: A tuple of log entries
        """
        ...

    def stream(self, history: bool = False, max_size: int = 1000) -> LogStream:
        """
        Opens a bounded stream following the log live

        :param history: If True, the stream starts with the entries kept by the service
        :param max_size: Maximum number of pending entries (the oldest ones are discarded)
        :return: A log stream, to be closed by the caller
        """
        ...


@Specification(LOG_SERVICE)
class LogService(Protocol):
    """
    Specification of the Log service
    """

    def log(
        self,
        level: int,
        message: str | None,
        exc_info: OptExcInfo = None,
        reference: ServiceReference[Any] | None = None,
    ) -> None:
        """
        Logs a message, possibly with an exception

        :param level: Severity of the message (Python logging level)
        :param message: Human readable message
        :param exc_info: The exception context (sys.exc_info()), if any
        :param reference: The ServiceReference associated to the log
        """
        ...
