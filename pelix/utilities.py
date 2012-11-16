#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Utility methods and decorators

:author: Thomas Calmant
:copyright: Copyright 2012, isandlaTech
:license: GPLv3
:version: 0.3
:status: Alpha

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

from functools import wraps
from collections import deque
import sys
import threading

# ------------------------------------------------------------------------------

__version__ = (0, 3, 0)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Using Python 3
PYTHON_3 = (sys.version_info[0] == 3)

# ------------------------------------------------------------------------------

class Synchronized:
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

        @wraps(method)
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
        @wraps(method)
        def synchronized(self, *args, **kwargs):
            """
            Calls the wrapped method with a lock
            """
            # Raises an AttributeError if needed
            locks = [getattr(self, attr_name) for attr_name in locks_attr_names]
            locked = deque()
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

else:
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
