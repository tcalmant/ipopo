#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Implementation of the OSGi LogService, based on Python standard logging

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

import collections
import datetime
import logging
import sys
import time
from types import ModuleType
from typing import Any, Callable, Iterable, Optional, Set, Tuple, Union, cast

from pelix.constants import ActivatorProto, BundleActivator
from pelix.framework import Bundle, BundleContext
from pelix.internals.registry import ServiceReference, ServiceRegistration
from pelix.misc import (
    LOG_SERVICE,
    PROPERTY_LOG_LEVEL,
    PROPERTY_LOG_MAX_ENTRIES,
    LogEntry,
    LogListener,
    LogReader,
    LogService,
    OptExcInfo,
)

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Local logger
logger = logging.getLogger(__name__)

# Definition of the log levels (OSGi values)
LOG_ERROR = 1
LOG_WARNING = 2
LOG_INFO = 3
LOG_DEBUG = 4

# OSGi level => Python logging level
OSGI_TO_LEVEL = {
    LOG_DEBUG: logging.DEBUG,
    LOG_INFO: logging.INFO,
    LOG_WARNING: logging.WARNING,
    LOG_ERROR: logging.ERROR,
}

# Python logging level => OSGi level
LEVEL_TO_OSGI = {
    logging.DEBUG: LOG_DEBUG,
    logging.INFO: LOG_INFO,
    logging.WARNING: LOG_WARNING,
    logging.ERROR: LOG_ERROR,
    logging.CRITICAL: LOG_ERROR,
}

# ------------------------------------------------------------------------------


class LogEntryImpl(LogEntry):
    """
    Represents a log entry
    """

    __slots__ = (
        "__bundle",
        "__exception",
        "__level",
        "__message",
        "__reference",
        "__time",
        "__record",
    )

    def __init__(
        self,
        level: int,
        message: Optional[str],
        exception: OptExcInfo,
        bundle: Optional[Bundle],
        reference: Optional[ServiceReference[Any]],
    ) -> None:
        """
        :param level: The Python log level of the entry
        :param message: A human readable message
        :param exception: The exception associated to the entry
        :param bundle: The bundle that created the entry
        :param reference: The service reference associated to the entry
        """
        self.__bundle = bundle
        self.__exception = exception
        self.__level = level
        self.__message = message
        self.__reference = reference
        self.__time: float = time.time()
        self.__record: Optional[logging.LogRecord] = None

    def __str__(self) -> str:
        """
        String representation
        """
        values = [
            # 7: length of "WARNING"
            "{0: ^7} ::".format(logging.getLevelName(self.__level)),
            # Date
            str(datetime.datetime.fromtimestamp(self.__time)),
            "::",
        ]

        if self.__bundle:
            # Bundle name
            values.append("{0: <20s} ::".format(self.__bundle.get_symbolic_name()))

        # Message
        if self.__message:
            values.append(self.__message)

        if not self.__exception:
            # Print as is
            return " ".join(values)

        # Print the exception too
        return f"{' '.join(values)}\n{self.__exception}"

    @property
    def bundle(self) -> Optional[Bundle]:
        """
        The bundle that created this entry
        """
        return self.__bundle

    @property
    def message(self) -> Optional[str]:
        """
        The message associated to this entry
        """
        return self.__message

    @property
    def exception(self) -> OptExcInfo:
        """
        The exception associated to this entry
        """
        return self.__exception

    @property
    def level(self) -> int:
        """
        The log level of this entry (Python constant)
        """
        return self.__level

    @property
    def osgi_level(self) -> int:
        """
        The log level of this entry (OSGi constant)
        """
        return LEVEL_TO_OSGI.get(self.__level, LOG_INFO)

    @property
    def reference(self) -> Optional[ServiceReference[Any]]:
        """
        The reference to the service associated to this entry
        """
        return self.__reference

    @property
    def time(self) -> float:
        """
        The timestamp of this entry
        """
        return self.__time

    def to_record(self) -> logging.LogRecord:
        """
        Returns this object as a ``logging.LogRecord``
        """
        if self.__record is None:
            # Construct the record on demand
            self.__record = self.__make_record()

        return self.__record

    def __make_record(self) -> logging.LogRecord:
        """
        Converts this object into a ``logging.LogRecord`` object
        """
        # Extract local details
        bundle = self.bundle
        name = bundle.get_symbolic_name() if bundle is not None else "n/a"
        pathname = bundle.get_location() if bundle is not None else "n/a"
        lineno = 0

        level = self.level
        msg = self.message
        exc_info = self.exception

        # Construct the record
        record = logging.LogRecord(name, level, pathname, lineno, msg, None, exc_info, "n/a", None)

        # Fix the time related entries
        log_start_time = record.created - (record.relativeCreated / 1000)
        creation_time = self.__time

        record.created = creation_time
        record.msecs = (creation_time - int(creation_time)) * 1000
        record.relativeCreated = (creation_time - log_start_time) * 1000
        return record


class LogReaderImpl(LogReader):
    """
    The LogReader service
    """

    def __init__(self, context: BundleContext, max_entries: int) -> None:
        """
        :param context: The bundle context
        :param max_entries: Maximum stored entries
        """
        self._context = context
        self.__logs = collections.deque[LogEntry](maxlen=max_entries)
        self.__listeners: Set[LogListener] = set()

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
        if listener is not None:
            self.__listeners.add(listener)

    def remove_log_listener(self, listener: LogListener) -> None:
        """
        Unsubscribes a listener from log events.

        :param listener: The listener to remove
        """
        self.__listeners.discard(listener)

    def get_log(self) -> Tuple[LogEntry, ...]:
        """
        Returns the logs events kept by the service

        :return: A tuple of log entries
        """
        return tuple(self.__logs)

    def _store_entry(self, entry: LogEntry) -> None:
        """
        Stores a new log entry and notifies listeners

        :param entry: A LogEntry object
        """
        # Get the logger and log the message
        self.__logs.append(entry)

        # Notify listeners
        for listener in self.__listeners.copy():
            try:
                listener.logged(entry)
            except Exception as ex:
                # Create a new log entry, without using logging nor notifying
                # listener (to avoid a recursion)
                err_entry = LogEntryImpl(
                    logging.WARNING,
                    f"Error notifying logging listener {listener}: {ex}",
                    sys.exc_info(),
                    self._context.get_bundle(),
                    None,
                )

                # Insert the new entry before the real one
                self.__logs.pop()
                self.__logs.append(err_entry)
                self.__logs.append(entry)


class LogServiceInstance(LogService):
    """
    Instance of the log service given to a bundle by the factory
    """

    __slots__ = ("__reader", "__bundle")

    def __init__(self, reader: LogReaderImpl, bundle: Bundle) -> None:
        """
        :param reader: The Log Reader service
        :param bundle: Bundle associated to this instance
        """
        self.__reader = reader
        self.__bundle = bundle

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
        if not isinstance(reference, ServiceReference):
            # Ensure we have a clean Service Reference
            reference = None

        # Store the LogEntry
        entry = LogEntryImpl(level, message, exc_info, self.__bundle, reference)
        self.__reader._store_entry(entry)


class LogServiceFactory(logging.Handler):
    """
    Log Service Factory: provides a logger per bundle
    """

    def __init__(self, context: BundleContext, reader: LogReaderImpl, level: int) -> None:
        """
        :param context: The bundle context
        :param reader: The Log Reader service
        :param level: The minimal log level of this handler
        """
        logging.Handler.__init__(self, level)
        self._framework = context.get_framework()
        self._reader = reader

    def _bundle_from_module(self, module_object: Union[str, ModuleType]) -> Optional[Bundle]:
        """
        Find the bundle associated to a module

        :param module_object: A Python module object
        :return: The Bundle object associated to the module, or None
        """
        # Get the module name
        try:
            module_name = cast(str, getattr(module_object, "__name__"))
        except AttributeError:
            # We got a string
            module_name = str(module_object)

        return self._framework.get_bundle_by_name(module_name)

    def emit(self, record: logging.LogRecord) -> None:
        """
        Handle a message logged with the logger

        :param record: A log record
        """
        # Get the bundle
        bundle = self._bundle_from_module(record.module)

        # Convert to a LogEntry
        entry = LogEntryImpl(record.levelno, record.getMessage(), None, bundle, None)
        self._reader._store_entry(entry)

    def get_service(self, bundle: Bundle, registration: ServiceRegistration[LogService]) -> LogService:
        """
        Returns an instance of the log service for the given bundle

        :param bundle: Bundle consuming the service
        :param registration: Service registration bean
        :return: An instance of the logger
        """
        return LogServiceInstance(self._reader, bundle)

    @staticmethod
    def unget_service(bundle: Bundle, registration: ServiceRegistration[LogService]) -> None:
        """
        Releases the service associated to the given bundle

        :param bundle: Consuming bundle
        :param registration: Service registration bean
        """
        pass


@BundleActivator
class Activator(ActivatorProto):
    """
    The bundle activator
    """

    def __init__(self) -> None:
        self.__reader_reg: Optional[ServiceRegistration[LogReader]] = None
        self.__factory_reg: Optional[ServiceRegistration[Any]] = None
        self.__factory: Optional[LogServiceFactory] = None

    @staticmethod
    def get_level(context: BundleContext) -> int:
        """
        Get the log level from the bundle context (framework properties)

        :param context: A bundle context
        :return: A log level (int)
        """
        # Get the log level
        level_value = context.get_property(PROPERTY_LOG_LEVEL)

        if level_value:
            converters: Iterable[Callable[[Any], Any]] = (int, logging.getLevelName)
            for converter in converters:
                try:
                    parsed_level = converter(level_value)
                    if isinstance(parsed_level, int):
                        # Got a valid level
                        return parsed_level
                except (ValueError, TypeError):
                    pass

        # By default, use the INFO level
        return logging.INFO

    def start(self, context: BundleContext) -> None:
        """
        Bundle starting

        :param context: The bundle context
        """
        # Get the maximum number of entries authorized
        max_entries = context.get_property(PROPERTY_LOG_MAX_ENTRIES)
        try:
            # Normalize the value
            max_entries = int(max_entries)
        except (ValueError, TypeError):
            max_entries = 100

        # Register the LogReader service
        reader = LogReaderImpl(context, max_entries)
        self.__reader_reg = context.register_service(LogReader, reader, {})

        # Register the LogService factory
        self.__factory = LogServiceFactory(context, reader, self.get_level(context))
        self.__factory_reg = context.register_service(LOG_SERVICE, self.__factory, {}, factory=True)

        # Register the log service as a log handler
        logging.getLogger().addHandler(self.__factory)
        # ... but not for our own logs
        logger.removeHandler(self.__factory)

    def stop(self, _: BundleContext) -> None:
        """
        Bundle stopping
        """
        # Unregister the service
        if self.__factory_reg is not None:
            self.__factory_reg.unregister()
            self.__factory_reg = None

        if self.__reader_reg is not None:
            self.__reader_reg.unregister()
            self.__reader_reg = None

        # Unregister the handler
        if self.__factory is not None:
            logging.getLogger().removeHandler(self.__factory)
            self.__factory = None
