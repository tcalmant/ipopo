#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Utility methods and decorators

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.5.5
:status: Beta

..

    This file is part of iPOPO.

    iPOPO is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    iPOPO is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with iPOPO. If not, see <http://www.gnu.org/licenses/>.
"""

# Pelix constants
import pelix.constants

# Standard library
import collections
import contextlib
import functools
import logging
import sys
import threading
import traceback

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 5, 5)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Using Python 3
PYTHON_3 = (sys.version_info[0] == 3)

# ------------------------------------------------------------------------------

@contextlib.contextmanager
def use_service(bundle_context, svc_reference):
    """
    Utility context to safely use a service in a "with" block.
    It looks after the the given service and releases its reference when exiting
    the context.

    :param bundle_context: The calling bundle context
    :param svc_reference: The reference of the service to use
    :return: The requested service
    :raise BundleException: Service not found
    :raise TypeError: Invalid service reference
    """
    try:
        # Give the service
        yield bundle_context.get_service(svc_reference)

    finally:
        try:
            # Release it
            bundle_context.unget_service(svc_reference)

        except pelix.constants.BundleException:
            # Service might have already been unregistered
            pass

# ------------------------------------------------------------------------------

class Deprecated(object):
    """
    Prints a warning when using the decorated method
    """
    def __init__(self, message=None, logger=None):
        """
        Sets the deprecation message, e.g. to indicate which method to call
        instead.
        If a logger is given, its 'warning' method will be called to print the
        message; else the standard 'print' method will be used.

        :param message: Message to be printed
        :param logger: The name of the logger to use, or None.
        """
        self.__message = message or "Deprecated method"
        self.__logger = logger or None
        self.__already_logged = False


    def __log(self, method_name):
        """
        Logs the deprecation message on first call, does nothing after

        :param method_name: Name of the deprecated method
        """
        if not self.__already_logged:
            # Print only if not already done
            stack = '\n\t'.join(traceback.format_stack())

            logging.getLogger(self.__logger).warning("%s: %s\n%s",
                                                     method_name,
                                                     self.__message,
                                                     stack)
            self.__already_logged = True


    def __call__(self, method):
        """
        Applies the modifications

        :param method: The decorated method
        :return: The wrapped method
        """
        # Prepare the wrapped call
        @functools.wraps(method)
        def wrapped(*args, **kwargs):
            """
            Wrapped deprecated method
            """
            self.__log(method.__name__)
            return method(*args, **kwargs)

        return wrapped


# ------------------------------------------------------------------------------

class Synchronized(object):
    """
    A synchronizer for global methods
    """
    def __init__(self, lock=None):
        """
        Sets up the decorator. If 'lock' is None, an RLock() is created for
        this decorator.

        :param lock: The lock to be used for synchronization (can be None)
        """
        if not is_lock(lock):
            self.__lock = threading.RLock()

        else:
            self.__lock = lock


    def __call__(self, method):
        """
        Sets up the decorated method

        :param method: The decorated method
        :return: The wrapped method
        """

        @functools.wraps(method)
        def wrapped(*args, **kwargs):
            """
            The wrapping method
            """
            with self.__lock:
                return method(*args, **kwargs)

        return wrapped


def SynchronizedClassMethod(*locks_attr_names, **kwargs):
    """
    A synchronizer decorator for class methods. An AttributeError can be raised
    at runtime if the given lock attribute doesn't exist or if it is None.

    If a parameter ``sorted`` is found in ``kwargs`` and its value is True,
    then the list of locks names will be sorted before locking.

    :param locks_attr_names: A list of the lock(s) attribute(s) name(s) to be
                             used for synchronization
    :return: The decorator method, surrounded with the lock
    """
    # Filter the names (remove empty ones)
    locks_attr_names = [lock_name
                        for lock_name in locks_attr_names
                        if lock_name]

    if not locks_attr_names:
        raise ValueError("The lock names list can't be empty")

    if 'sorted' not in kwargs or kwargs['sorted']:
        # Sort the lock names if requested
        # (locking always in the same order reduces the risk of dead lock)
        locks_attr_names = list(locks_attr_names)
        locks_attr_names.sort()

    def wrapped(method):
        """
        The wrapping method

        :param method: The wrapped method
        :return: The wrapped method
        :raise AttributeError: The given attribute name doesn't exist
        """
        @functools.wraps(method)
        def synchronized(self, *args, **kwargs):
            """
            Calls the wrapped method with a lock
            """
            # Raises an AttributeError if needed
            locks = [getattr(self, attr_name) for attr_name in locks_attr_names]
            locked = collections.deque()
            i = 0

            try:
                # Lock
                for lock in locks:
                    if lock is None:
                        # No lock...
                        raise AttributeError(
                            "Lock '{0}' can't be None in class {1}".format(
                                    locks_attr_names[i], type(self).__name__))

                    # Get the lock
                    i += 1
                    lock.acquire()
                    locked.appendleft(lock)

                # Use the method
                return method(self, *args, **kwargs)

            finally:
                # Unlock what has been locked in all cases
                for lock in locked:
                    lock.release()

                locked.clear()
                del locks[:]

        return synchronized

    # Return the wrapped method
    return wrapped

def is_lock(lock):
    """
    Tests if the given lock is an instance of a lock class
    """
    if lock is None:
        # Don't do useless tests
        return False

    for attr in ('acquire', 'release', '__enter__', '__exit__'):
        if not hasattr(lock, attr):
            # Missing something
            return False

    # Same API as a lock
    return True

# ------------------------------------------------------------------------------

def read_only_property(value):
    """
    Makes a read-only property that always returns the given value
    """
    return property(lambda cls: value)

# ------------------------------------------------------------------------------

def remove_all_occurrences(sequence, item):
    """
    Removes all occurrences of item in the given sequence

    :param sequence: The items list
    :param item: The item to be removed
    """
    if sequence is None:
        return

    while item in sequence:
        sequence.remove(item)

# ------------------------------------------------------------------------------

def add_listener(registry, listener):
    """
    Adds a listener in the registry, if it is not yet in

    :param registry: A registry (a list)
    :param listener: The listener to register
    :return: True if the listener has been added
    """
    if listener is None or listener in registry:
        return False

    registry.append(listener)
    return True


def remove_listener(registry, listener):
    """
    Removes a listener from the registry

    :param registry: A registry (a list)
    :param listener: The listener to remove
    :return: True if the listener was in the list
    """
    if listener is not None and listener in registry:
        registry.remove(listener)
        return True

    return False

# ------------------------------------------------------------------------------

if PYTHON_3:
    # Python 3 interpreter : bytes & str
    def is_string(string):
        """
        Utility method to test if the given parameter is a string
        (Python 2.x, 3.x) or a unicode (Python 2.x) object

        :param string: A potential string object
        :return: True if the given object is a string object or a Python 2.6
                 unicode object
        """
        # Python 3 only have the str string type
        return isinstance(string, str)

    def to_bytes(data, encoding="UTF-8"):
        """
        Converts the given string to an array of bytes.
        Returns the first parameter if it is already an array of bytes.

        :param data: A unicode string
        :param encoding: The encoding of data
        :return: The corresponding array of bytes
        """
        if type(data) is bytes:
            # Nothing to do
            return data

        return data.encode(encoding)


    def to_str(data, encoding="UTF-8"):
        """
        Converts the given parameter to a string.
        Returns the first parameter if it is already an instance of ``str``.

        :param data: A string
        :param encoding: The encoding of data
        :return: The corresponding string
        """
        if type(data) is str:
            # Nothing to do
            return data

        return str(data, encoding)

    # Same operation
    to_unicode = to_str

else:
    # Python 2 interpreter : str & unicode
    def is_string(string):
        """
        Utility method to test if the given parameter is a string
        (Python 2.x, 3.x) or a unicode (Python 2.x) object

        :param string: A potential string object
        :return: True if the given object is a string object or a Python 2.6
                 unicode object
        """
        # Python 2 also have unicode
        return isinstance(string, (str, unicode))


    def to_str(data, encoding="UTF-8"):
        """
        Converts the given parameter to a string.
        Returns the first parameter if it is already an instance of ``str``.

        :param data: A string
        :param encoding: The encoding of data
        :return: The corresponding string
        """
        if type(data) is str:
            # Nothing to do
            return data

        return data.encode(encoding)


    # Same operation
    to_bytes = to_str


    def to_unicode(data, encoding="UTF-8"):
        """
        Converts the given string to an unicode string using ``str.decode()``.
        Returns the first parameter if it is already an instance of ``unicode``.

        :param data: A string
        :param encoding: The encoding of data
        :return: The corresponding ``unicode`` string
        """
        if type(data) is unicode:
            # Nothing to do
            return data

        return data.decode(encoding)
