#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Implementation of the OSGi LogService, based on Python standard logging

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

# Standard library
import collections
import datetime
import logging
import sys
import time
import traceback

# Pelix
import pelix.framework
from pelix.constants import BundleActivator
from pelix.misc import (
    LOG_SERVICE,
    LOG_READER_SERVICE,
    PROPERTY_LOG_LEVEL,
    PROPERTY_LOG_MAX_ENTRIES,
)

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
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


class LogEntry(object):
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
    )

    def __init__(self, level, message, exception, bundle, reference):
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
        self.__time = time.time()

    def __str__(self):
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
            values.append(
                "{0: <20s} ::".format(self.__bundle.get_symbolic_name())
            )

        # Message
        values.append(self.__message)

        if not self.__exception:
            # Print as is
            return " ".join(values)

        # Print the exception too
        return "{0}\n{1}".format(" ".join(values), self.__exception)

    @property
    def bundle(self):
        """
        The bundle that created this entry
        """
        return self.__bundle

    @property
    def message(self):
        """
        The message associated to this entry
        """
        return self.__message

    @property
    def exception(self):
        """
        The exception associated to this entry
        """
        return self.__exception

    @property
    def level(self):
        """
        The log level of this entry (Python constant)
        """
        return self.__level

    @property
    def osgi_level(self):
        """
        The log level of this entry (OSGi constant)
        """
        return LEVEL_TO_OSGI.get(self.__level, LOG_INFO)

    @property
    def reference(self):
        """
        The reference to the service associated to this entry
        """
        return self.__reference

    @property
    def time(self):
        """
        The timestamp of this entry
        """
        return self.__time


class LogReaderService:
    """
    The LogReader service
    """

    def __init__(self, context, max_entries):
        """
        :param context: The bundle context
        :param max_entries: Maximum stored entries
        """
        self._context = context
        self.__logs = collections.deque(maxlen=max_entries)
        self.__listeners = set()

    def add_log_listener(self, listener):
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

    def remove_log_listener(self, listener):
        """
        Unsubscribes a listener from log events.

        :param listener: The listener to remove
        """
        self.__listeners.discard(listener)

    def get_log(self):
        """
        Returns the logs events kept by the service

        :return: A tuple of log entries
        """
        return tuple(self.__logs)

    def _store_entry(self, entry):
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
                err_entry = LogEntry(
                    logging.WARNING,
                    "Error notifying logging listener {0}: {1}".format(
                        listener, ex
                    ),
                    sys.exc_info(),
                    self._context.get_bundle(),
                    None,
                )

                # Insert the new entry before the real one
                self.__logs.pop()
                self.__logs.append(err_entry)
                self.__logs.append(entry)


class LogServiceInstance:
    # pylint: disable=R0903
    """
    Instance of the log service given to a bundle by the factory
    """

    __slots__ = ("__reader", "__bundle")

    def __init__(self, reader, bundle):
        """
        :param reader: The Log Reader service
        :param bundle: Bundle associated to this instance
        """
        self.__reader = reader
        self.__bundle = bundle

    def log(self, level, message, exc_info=None, reference=None):
        # pylint: disable=W0212
        """
        Logs a message, possibly with an exception

        :param level: Severity of the message (Python logging level)
        :param message: Human readable message
        :param exc_info: The exception context (sys.exc_info()), if any
        :param reference: The ServiceReference associated to the log
        """
        if not isinstance(reference, pelix.framework.ServiceReference):
            # Ensure we have a clean Service Reference
            reference = None

        if exc_info is not None:
            # Format the exception to avoid memory leaks
            try:
                exception_str = "\n".join(traceback.format_exception(*exc_info))
            except (TypeError, ValueError, AttributeError):
                exception_str = "<Invalid exc_info>"
        else:
            exception_str = None

        # Store the LogEntry
        entry = LogEntry(
            level, message, exception_str, self.__bundle, reference
        )
        self.__reader._store_entry(entry)


class LogServiceFactory(logging.Handler):
    """
    Log Service Factory: provides a logger per bundle
    """

    def __init__(self, context, reader, level):
        """
        :param context: The bundle context
        :param reader: The Log Reader service
        :param level: The minimal log level of this handler
        """
        logging.Handler.__init__(self, level)
        self._framework = context.get_framework()
        self._reader = reader

    def _bundle_from_module(self, module_object):
        """
        Find the bundle associated to a module

        :param module_object: A Python module object
        :return: The Bundle object associated to the module, or None
        """
        try:
            # Get the module name
            module_object = module_object.__name__
        except AttributeError:
            # We got a string
            pass

        return self._framework.get_bundle_by_name(module_object)

    def emit(self, record):
        # pylint: disable=W0212
        """
        Handle a message logged with the logger

        :param record: A log record
        """
        # Get the bundle
        bundle = self._bundle_from_module(record.module)

        # Convert to a LogEntry
        entry = LogEntry(
            record.levelno, record.getMessage(), None, bundle, None
        )
        self._reader._store_entry(entry)

    def get_service(self, bundle, registration):
        # pylint: disable=W0613
        """
        Returns an instance of the log service for the given bundle

        :param bundle: Bundle consuming the service
        :param registration: Service registration bean
        :return: An instance of the logger
        """
        return LogServiceInstance(self._reader, bundle)

    @staticmethod
    def unget_service(bundle, registration):
        """
        Releases the service associated to the given bundle

        :param bundle: Consuming bundle
        :param registration: Service registration bean
        """
        pass


@BundleActivator
class Activator(object):
    """
    The bundle activator
    """

    def __init__(self):
        self.__reader_reg = None
        self.__factory_reg = None
        self.__factory = None

    @staticmethod
    def get_level(context):
        """
        Get the log level from the bundle context (framework properties)

        :param context: A bundle context
        :return: A log level (int)
        """
        # Get the log level
        level_value = context.get_property(PROPERTY_LOG_LEVEL)

        if level_value:
            for converter in int, logging.getLevelName:
                try:
                    parsed_level = converter(level_value)
                    if isinstance(parsed_level, int):
                        # Got a valid level
                        return parsed_level
                except (ValueError, TypeError):
                    pass

        # By default, use the INFO level
        return logging.INFO

    def start(self, context):
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
        reader = LogReaderService(context, max_entries)
        self.__reader_reg = context.register_service(
            LOG_READER_SERVICE, reader, {}
        )

        # Register the LogService factory
        self.__factory = LogServiceFactory(
            context, reader, self.get_level(context)
        )
        self.__factory_reg = context.register_service(
            LOG_SERVICE, self.__factory, {}, factory=True
        )

        # Register the log service as a log handler
        logging.getLogger().addHandler(self.__factory)
        # ... but not for our own logs
        logger.removeHandler(self.__factory)

    def stop(self, _):
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
        logging.getLogger().removeHandler(self.__factory)
        self.__factory = None
