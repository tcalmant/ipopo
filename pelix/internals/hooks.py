#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
EventListenerHook for Pelix.

:author: Scott Lewis
:copyright: Copyright 2020, Scott Lewis
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2020 Scott Lewis

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

from collections.abc import MutableMapping, MutableSequence
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Generic,
    Iterable,
    Iterator,
    List,
    Optional,
    Protocol,
    TypeVar,
    Union,
    overload,
)

if TYPE_CHECKING:
    from pelix.framework import BundleContext
    from pelix.internals.events import ServiceEvent
    from pelix.internals.registry import ServiceListener
    from pelix.ldapfilter import LDAPCriteria, LDAPFilter

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class ShrinkableList(MutableSequence[T]):
    """
    List where items can be removed, but nothing can be added.
    For use in ShrinkableMap
    """

    def __init__(self, delegate: MutableSequence[T]) -> None:
        self._delegate = delegate

    def __len__(self) -> int:
        return len(self._delegate)

    @overload
    def __getitem__(self, index: int) -> T:
        ...

    @overload
    def __getitem__(self, index: slice) -> MutableSequence[T]:
        ...

    def __getitem__(self, index):  # type: ignore
        return self._delegate[index]

    def __delitem__(self, index: Union[int, slice]) -> None:
        del self._delegate[index]

    @overload
    def __setitem__(self, index: int, value: T) -> None:
        ...

    @overload
    def __setitem__(self, index: slice, values: Iterable[T]) -> None:
        ...

    def __setitem__(self, index, value) -> None:  # type: ignore
        raise IndexError

    def insert(self, index: int, value: T) -> None:
        raise IndexError

    def __str__(self) -> str:
        return str(self._delegate)


class ShrinkableMap(MutableMapping[K, V]):
    """
    Map where item->value mappings can be removed, but nothing can be added.
    For use in EventListenerHook
    """

    def __init__(self, delegate: MutableMapping[K, V]) -> None:
        self._delegate = delegate

    def __getitem__(self, key: K) -> V:
        return self._delegate[key]

    def __setitem__(self, key: K, value: V) -> None:
        raise IndexError

    def __delitem__(self, key: K) -> None:
        del self._delegate[key]

    def __iter__(self) -> Iterator[K]:
        return self._delegate.__iter__()

    def __len__(self) -> int:
        return len(self._delegate)


class ListenerInfo(Generic[T]):
    """
    Keeps information about a listener
    """

    # Try to reduce memory footprint (stored instances)
    __slots__ = (
        "__bundle_context",
        "__listener",
        "__specification",
        "__ldap_filter",
    )

    def __init__(
        self,
        bundle_context: "BundleContext",
        listener: T,
        specification: Optional[str],
        ldap_filter: Union[None, "LDAPCriteria", "LDAPFilter"],
    ) -> None:
        """
        :param bundle_context: Bundle context
        :param listener: Listener instance
        :param specification: Specification to listen to
        :param ldap_filter: LDAP filter on service properties
        """
        self.__bundle_context = bundle_context
        self.__listener = listener
        self.__specification = specification
        self.__ldap_filter = ldap_filter

    @property
    def bundle_context(self) -> "BundleContext":
        """
        The context of the bundle which added the listener.
        """
        return self.__bundle_context

    @property
    def listener(self) -> T:
        """
        The listener instance
        """
        return self.__listener

    @property
    def specification(self) -> Optional[str]:
        """
        The specification to listen to
        """
        return self.__specification

    @property
    def ldap_filter(self) -> Union[None, "LDAPCriteria", "LDAPFilter"]:
        """
        The LDAP filter on service properties
        """
        return self.__ldap_filter

    def get_bundle_context(self) -> "BundleContext":
        """
        Return the context of the bundle which added the listener.

        :return: A BundleContext object
        """
        return self.__bundle_context

    def get_filter(self) -> Optional[str]:
        """
        Returns the LDAP filter string with which the filter was added

        :return: An LDAP filter string
        """
        if self.__ldap_filter:
            return str(self.__ldap_filter)
        return None


class EventListenerHook(Protocol):
    """
    Event listener hook interface prototype.  The method in this class must be
    overridden for a service event listener hook to be called via whiteboard
    pattern
    """

    def event(
        self,
        service_event: "ServiceEvent[Any]",
        listener_dict: Dict["BundleContext", List["ServiceListener"]],
    ) -> None:
        """
        Method called when a service event is triggered.

        :param service_event: The ServiceEvent being triggered
        :param listener_dict: A dictionary associating a bundle context to a list of listeners
        """
        ...
