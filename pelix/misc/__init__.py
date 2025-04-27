#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix miscellaneous modules

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2025 Thomas Calmant

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

from types import TracebackType
from typing import Any, Optional, Protocol, Tuple, TypeAlias
from pelix.constants import Specification

from pelix.framework import Bundle
from pelix.internals.registry import ServiceReference

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"


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
    def bundle(self) -> Optional[Bundle]:
        """
        The bundle that created this entry
        """
        ...

    @property
    def message(self) -> Optional[str]:
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
    def reference(self) -> Optional[ServiceReference[Any]]:
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

    def get_log(self) -> Tuple[LogEntry, ...]:
        """
        Returns the logs events kept by the service

        :return: A tuple of log entries
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
        message: Optional[str],
        exc_info: OptExcInfo = None,
        reference: Optional[ServiceReference[Any]] = None,
    ) -> None:
        """
        Logs a message, possibly with an exception

        :param level: Severity of the message (Python logging level)
        :param message: Human readable message
        :param exc_info: The exception context (sys.exc_info()), if any
        :param reference: The ServiceReference associated to the log
        """
        ...
