#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Utility methods and decorators

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
import contextlib
import functools
import inspect
import logging
import threading
import traceback
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Concatenate,
    Generator,
    Generic,
    Iterable,
    List,
    Optional,
    ParamSpec,
    TypeVar,
    Union,
    cast,
)

import pelix.constants

if TYPE_CHECKING:
    from pelix.framework import BundleContext
    from pelix.internals.registry import ServiceReference

T = TypeVar("T")
P = ParamSpec("P")

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


@contextlib.contextmanager
def use_service(
    bundle_context: "BundleContext", svc_reference: "ServiceReference[T]"
) -> Generator[T, None, None]:
    """
    Utility context to safely use a service in a "with" block.
    It looks after the the given service and releases its reference when
    exiting the context.

    :param bundle_context: The calling bundle context
    :param svc_reference: The reference of the service to use
    :return: The requested service
    :raise BundleException: Service not found
    :raise TypeError: Invalid service reference
    """
    if svc_reference is None:
        raise TypeError("Invalid ServiceReference")

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


# Mimic ArgSpec from getargspec()
ArgSpec = collections.namedtuple("ArgSpec", "args varargs keywords defaults")


def get_method_arguments(method: Callable[..., Any]) -> ArgSpec:
    """
    inspect.signature()-based way to get the arguments of a method.

    :param method: The method to extract the signature from
    :return: The arguments specification, without self
    """
    # Use the recommended signature method
    signature = inspect.signature(method)

    args = []
    varargs = None
    keywords = None
    defaults = []

    for param in signature.parameters.values():
        kind = param.kind
        if kind == inspect.Parameter.VAR_POSITIONAL:
            varargs = param.name
        elif kind == inspect.Parameter.VAR_KEYWORD:
            keywords = param.name
        else:
            args.append(param.name)

        if param.default is not param.empty:
            defaults.append(param.default)

    return ArgSpec(args, varargs, keywords, defaults or None)


# ------------------------------------------------------------------------------


class Deprecated:
    """
    Prints a warning when using the decorated method
    """

    def __init__(self, message: Optional[str] = None, logger: Optional[str] = None) -> None:
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

    def __log(self, method_name: str) -> None:
        """
        Logs the deprecation message on first call, does nothing after

        :param method_name: Name of the deprecated method
        """
        if not self.__already_logged:
            # Print only if not already done
            stack = "\n\t".join(traceback.format_stack())

            logging.getLogger(self.__logger).warning("%s: %s\n%s", method_name, self.__message, stack)
            self.__already_logged = True

    def __call__(self, method: Callable[P, T]) -> Callable[P, T]:
        """
        Applies the modifications

        :param method: The decorated method
        :return: The wrapped method
        """

        # Prepare the wrapped call
        @functools.wraps(method)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            """
            Wrapped deprecated method
            """
            self.__log(method.__name__)
            return method(*args, **kwargs)

        return cast(Callable[P, T], wrapped)


# ------------------------------------------------------------------------------


class Synchronized:
    """
    A synchronizer for global methods
    """

    def __init__(self, lock: Optional[threading.Lock] = None) -> None:
        """
        Sets up the decorator. If 'lock' is None, an RLock() is created for
        this decorator.

        :param lock: The lock to be used for synchronization (can be None)
        """
        if lock is None or not is_lock(lock):
            self.__lock: Union[threading.Lock, threading.RLock] = threading.RLock()
        else:
            self.__lock = lock

    def __call__(self, method: Callable[P, T]) -> Callable[P, T]:
        """
        Sets up the decorated method

        :param method: The decorated method
        :return: The wrapped method
        """

        @functools.wraps(method)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            """
            The wrapping method
            """
            with self.__lock:
                return method(*args, **kwargs)

        return cast(Callable[P, T], wrapped)


def SynchronizedClassMethod(*locks_attr_names: str, **kwargs: Any) -> Callable[..., Any]:
    # pylint: disable=C1801
    """
    A synchronizer decorator for class methods. An AttributeError can be raised
    at runtime if the given lock attribute doesn't exist or if it is None.

    If a parameter ``sorted`` is found in ``kwargs`` and its value is True,
    then the list of locks names will be sorted before locking.

    :param locks_attr_names: A list of the lock(s) attribute(s) name(s) to be used for synchronization
    :return: The decorator method, surrounded with the lock
    """
    # Filter the names (remove empty ones)
    locks_names = [lock_name for lock_name in locks_attr_names if lock_name]

    if not locks_names:
        raise ValueError("The lock names list can't be empty")

    if "sorted" not in kwargs or kwargs["sorted"]:
        # Sort the lock names if requested
        # (locking always in the same order reduces the risk of dead lock)
        locks_names = list(locks_names)
        locks_names.sort()

    def wrapped(method: Callable[Concatenate[Any, P], T]) -> Callable[P, T]:
        """
        The wrapping method

        :param method: The wrapped method
        :return: The wrapped method
        :raise AttributeError: The given attribute name doesn't exist
        """

        @functools.wraps(method)
        def synchronized(self: Any, *args: P.args, **kwargs: P.kwargs) -> T:
            """
            Calls the wrapped method with a lock
            """
            # Raises an AttributeError if needed
            locks = [getattr(self, attr_name) for attr_name in locks_names]
            locked = collections.deque[threading.Lock]()
            i = 0

            try:
                # Lock
                for lock in locks:
                    if lock is None:
                        # No lock...
                        raise AttributeError(
                            f"Lock '{locks_names[i]}' can't be None in class {type(self).__name__}"
                        )

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

        return cast(Callable[P, T], synchronized)

    # Return the wrapped method
    return wrapped


def is_lock(lock: Any) -> bool:
    """
    Tests if the given lock is an instance of a lock class
    """
    if lock is None:
        # Don't do useless tests
        return False

    for attr in "acquire", "release", "__enter__", "__exit__":
        if not hasattr(lock, attr):
            # Missing something
            return False

    # Same API as a lock
    return True


# ------------------------------------------------------------------------------


def read_only_property(value: Any) -> property:
    """
    Makes a read-only property that always returns the given value
    """
    return property(lambda cls: value)


# ------------------------------------------------------------------------------


def remove_all_occurrences(sequence: List[Any], item: Any) -> None:
    """
    Removes all occurrences of item in the given sequence

    :param sequence: The items list
    :param item: The item to be removed
    """
    if sequence is None:
        return

    while item in sequence:
        sequence.remove(item)


def remove_duplicates(items: Iterable[T]) -> List[T]:
    """
    Returns a list without duplicates, keeping elements order

    :param items: A list of items
    :return: The list without duplicates, in the same order
    """
    if items is None:
        return items

    new_list: List[T] = []
    for item in items:
        if item not in new_list:
            new_list.append(item)
    return new_list


# ------------------------------------------------------------------------------


def add_listener(registry: List[T], listener: T) -> bool:
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


def remove_listener(registry: List[T], listener: T) -> bool:
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


def is_bytes(string: Any) -> bool:
    """
    Utility method to test if the given parameter is a string
    (Python 2.x) or a bytes (Python 3.x) object

    :param string: A potential string object
    :return: True if the given object is a bytes string
    """
    # str in Python 2 is bytes in Python 3
    return isinstance(string, (bytes, bytearray))


def is_string(string: Any) -> bool:
    """
    Utility method to test if the given parameter is a string
    (Python 2.x, 3.x) or a unicode (Python 2.x) object

    :param string: A potential string object
    :return: True if the given object is a string object or a Python 2.x
                unicode object
    """
    # Python 3 only have the str string type
    return isinstance(string, str)


def to_bytes(data: Union[bytes, str], encoding: str = "UTF-8") -> bytes:
    """
    Converts the given string to an array of bytes.
    Returns the first parameter if it is already an array of bytes.

    :param data: A unicode string
    :param encoding: The encoding of data
    :return: The corresponding array of bytes
    """
    if isinstance(data, bytes):
        # Nothing to do
        return data

    return data.encode(encoding)


def to_str(data: Union[bytes, bytearray, str], encoding: str = "UTF-8") -> str:
    """
    Converts the given parameter to a string.
    Returns the first parameter if it is already an instance of ``str``.

    :param data: A string
    :param encoding: The encoding of data
    :return: The corresponding string
    """
    if isinstance(data, str):
        # Nothing to do
        return data

    return str(data, encoding)


# ------------------------------------------------------------------------------


def to_iterable(value: Any, allow_none: bool = True) -> Optional[Iterable[Any]]:
    """
    Tries to convert the given value to an iterable, if necessary.
    If the given value is a list, a list is returned; if it is a string, a list
    containing one string is returned, ...

    :param value: Any object
    :param allow_none: If True, the method returns None if value is None, else it returns an empty list
    :return: A list containing the given string, or the given value
    """
    if value is None:
        # None given
        if allow_none:
            return None

        return []

    elif isinstance(value, (list, tuple, set, frozenset)):
        # Iterable given, return it as-is
        return value

    # Return a one-value list
    return [value]


# ------------------------------------------------------------------------------


class EventData(Generic[T]):
    """
    A threading event with some associated data
    """

    __slots__ = ("__event", "__data", "__exception")

    def __init__(self) -> None:
        """
        Sets up the event
        """
        self.__event = threading.Event()
        self.__data: Optional[T] = None
        self.__exception: Optional[BaseException] = None

    @property
    def data(self) -> Optional[T]:
        """
        Returns the associated value
        """
        return self.__data

    @property
    def exception(self) -> Optional[BaseException]:
        """
        Returns the exception used to stop the wait() method
        """
        return self.__exception

    def clear(self) -> None:
        """
        Clears the event
        """
        self.__event.clear()
        self.__data = None
        self.__exception = None

    def is_set(self) -> bool:
        """
        Checks if the event is set
        """
        return self.__event.is_set()

    def set(self, data: Optional[T] = None) -> None:
        """
        Sets the event
        """
        self.__data = data
        self.__exception = None
        self.__event.set()

    def raise_exception(self, exception: BaseException) -> None:
        """
        Raises an exception in wait()

        :param exception: An Exception object
        """
        self.__data = None
        self.__exception = exception
        self.__event.set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Waits for the event or for the timeout

        :param timeout: Wait timeout (in seconds)
        :return: True if the event as been set, else False
        """
        result = self.__event.wait(timeout)
        # pylint: disable=E0702
        # Pylint seems to miss the "is None" check below
        if self.__exception is None:
            return result
        else:
            raise self.__exception


class CountdownEvent:
    """
    Sets up an Event once the internal integer reaches 0
    (kind of the opposite of a semaphore)
    """

    def __init__(self, value: int) -> None:
        """
        Sets up the counter

        :param value: The initial value of the counter, which must be greater than 0.
        :raise ValueError: The value is not greater than 0
        """
        if value <= 0:
            raise ValueError("Initial value is not greater than 0")

        self.__lock = threading.Lock()
        self.__value = value
        self.__event = threading.Event()

    def is_set(self) -> bool:
        """
        Checks if the event is set
        """
        return self.__event.is_set()

    def step(self) -> bool:
        """
        Decreases the internal counter. Raises an error if the counter goes
        below 0

        :return: True if this step was the final one, else False
        :raise ValueError: The counter has gone below 0
        """
        with self.__lock:
            self.__value -= 1
            if self.__value == 0:
                # All done
                self.__event.set()
                return True
            elif self.__value < 0:
                # Gone too far
                raise ValueError("The counter has gone below 0")

        return False

    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Waits for the event or for the timeout

        :param timeout: Wait timeout (in seconds)
        :return: True if the event as been set, else False
        """
        return self.__event.wait(timeout)


def str2bool(value: Optional[str]) -> bool:
    """
    Translates a string to a boolean.

    Inspired from distutils.strtobool, removed from Python 3.12

    True values are "true", "yes", "y", "on" and not "1".
    All other values are false.
    """
    if not value:
        return False

    return value.lower().strip() in ("true", "yes", "y", "on", "1")
