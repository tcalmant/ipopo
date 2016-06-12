#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Implementation of the OSGi LogService, based on Python standard logging

:author: Thomas Calmant
:copyright: Copyright 2016, Thomas Calmant
:license: Apache License 2.0
:version: 0.6.4

..

    Copyright 2016 Thomas Calmant

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
import inspect
import logging
import sys
import time
import traceback

# Pelix
import pelix.framework
from pelix.constants import BundleActivator
from pelix.misc import LOG_SERVICE, LOG_READER_SERVICE, \
    PROPERTY_LOG_LEVEL, PROPERTY_LOG_MAX_ENTRIES

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 6, 4)
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
    LOG_ERROR: logging.ERROR
}

# Python logging level => OSGi level
LEVEL_TO_OSGI = {
    logging.DEBUG: LOG_DEBUG,
    logging.INFO: LOG_INFO,
    logging.WARNING: LOG_WARNING,
    logging.ERROR: LOG_ERROR,
    logging.CRITICAL: LOG_ERROR
}

# ------------------------------------------------------------------------------


class LogEntry(object):
    """
    Represents a log entry
    """
    __slots__ = ('__bundle', '__exception', '__level',
                 '__message', '__reference', '__time')

    def __init__(self, level, message, exception, bundle, reference):
        """
        Sets up members

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
            str(datetime.datetime.fromtimestamp(self.__time)), '::']

        if self.__bundle:
            # Bundle name
            values.append("{0: <20s} ::".format(
                self.__bundle.get_symbolic_name()))

        # Message
        values.append(self.__message)

        if not self.__exception:
            # Print as is
            return ' '.join(values)
        else:
            # Print the exception too
            return '{0}\n{1}'.format(' '.join(values), self.__exception)

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


class LogService(logging.Handler):
    """
    Implementation of the log and log reader services
    """
    def __init__(self, context, level, max_entries):
        """
        Sets up members

        :param context: The bundle context
        :param level: The minimal log level of this handler
        :param max_entries: Maximum stored entries
        """
        logging.Handler.__init__(self, level)

        self._context = context
        self._framework = context.get_bundle(0)
        self.__logs = collections.deque(maxlen=max_entries)
        self.__listeners = set()

    def add_log_listener(self, listener):
        """
        Subscribes a listener to log events.

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
                    "Error notifying logging listener {0}: {1}"
                    .format(listener, ex), sys.exc_info(),
                    self._context.get_bundle(), None)

                # Insert the new entry before the real one
                self.__logs.pop()
                self.__logs.append(err_entry)
                self.__logs.append(entry)

    def _bundle_from_module(self, module):
        """
        Find the bundle associated to a module

        :param module: A Python module object
        :return: The Bundle object associated to the module, or None
        """
        try:
            # Get the module name
            module = module.__name__
        except AttributeError:
            # We got a string
            pass

        return self._framework.get_bundle_by_name(module)

    def log(self, level, message, exc_info=None, reference=None):
        """
        Logs a message, possibly with an exception

        :param level: Severity of the message (Python logging level)
        :param message: Human readable message
        :param exc_info: The exception context (sys.exc_info()), if any
        :param reference: The ServiceReference associated to the log
        """
        # Try to find the bundle
        if isinstance(reference, pelix.framework.ServiceReference):
            # Use the bundle that registered the associated service
            bundle = reference.get_bundle()
        else:
            # Sanitize
            reference = None

            # Use the caller as bundle, if possible
            try:
                # Stack[1]: caller
                # caller[0]: Frame object
                bundle = self._bundle_from_module(
                    inspect.stack()[1][0].f_globals['__name__'])
            except KeyError:
                # No '__name__' in frame globals
                bundle = None

        if exc_info is not None:
            # Format the exception to avoid memory leaks
            try:
                exception_str = '\n'.join(traceback.format_exception(*exc_info))
            except (TypeError, ValueError, AttributeError):
                exception_str = '<Invalid exc_info>'
        else:
            exception_str = None

        # Store the LogEntry
        entry = LogEntry(level, message, exception_str, bundle, reference)
        self._store_entry(entry)

    def emit(self, record):
        """
        Handle a message logged with the logger

        :param record: A log record
        """
        # Get the bundle
        bundle = self._bundle_from_module(record.module)

        # Convert to a LogEntry
        entry = LogEntry(record.levelno, record.message, None, bundle, None)
        self._store_entry(entry)


@BundleActivator
class Activator(object):
    """
    The bundle activator
    """
    def __init__(self):
        """
        Sets up members
        """
        self.__registration = None
        self.__service = None

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
            for converter in (int, logging.getLevelName):
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

        # Prepare the service
        self.__service = LogService(
            context, self.get_level(context), max_entries)

        # Register the log service as a log handler
        logging.getLogger().addHandler(self.__service)
        # ... but not for our own logs
        logger.removeHandler(self.__service)

        try:
            # Register the service
            self.__registration = context.register_service(
                [LOG_SERVICE, LOG_READER_SERVICE], self.__service, {})
        except:
            # In case of error remove the handler
            logging.getLogger().removeHandler(self.__service)
            raise

    def stop(self, _):
        """
        Bundle stopping
        """
        # Unregister the service
        if self.__registration is not None:
            self.__registration.unregister()
            self.__registration = None

        # Unregister the handler
        logging.getLogger().removeHandler(self.__service)
        self.__service = None
