#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
EventListenerHook for Pelix.

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Scott Lewis

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

from collections import MutableMapping, MutableSequence

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class ShrinkableList(MutableSequence):
    # pylint: disable=R0901
    """
    List where items can be removed, but nothing can be added.
    For use in ShrinkableMap
    """

    def __init__(self, delegate):
        self._delegate = delegate

    def __len__(self):
        return len(self._delegate)

    def __getitem__(self, index):
        return self._delegate[index]

    def __delitem__(self, index):
        del self._delegate[index]

    def __setitem__(self, index, value):
        raise IndexError

    def insert(self, index, value):
        raise IndexError

    def __str__(self):
        return str(self._delegate)


class ShrinkableMap(MutableMapping):
    """
    Map where item->value mappings can be removed, but nothing can be added.
    For use in EventListenerHook
    """

    def __init__(self, delegate):
        self._delegate = delegate

    def __getitem__(self, key):
        return self._delegate[key]

    def __setitem__(self, key, value):
        raise IndexError

    def __delitem__(self, key):
        del self._delegate[key]

    def __iter__(self):
        return self._delegate.__iter__()

    def __len__(self):
        return len(self._delegate)


class ListenerInfo(object):
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

    def __init__(self, bundle_context, listener, specification, ldap_filter):
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
    def bundle_context(self):
        """
        The context of the bundle which added the listener.
        """
        return self.__bundle_context

    @property
    def listener(self):
        """
        The listener instance
        """
        return self.__listener

    @property
    def specification(self):
        """
        The specification to listen to
        """
        return self.__specification

    @property
    def ldap_filter(self):
        """
        The LDAP filter on service properties
        """
        return self.__ldap_filter

    def get_bundle_context(self):
        """
        Return the context of the bundle which added the listener.

        :return: A BundleContext object
        """
        return self.__bundle_context

    def get_filter(self):
        """
        Returns the LDAP filter string with which the filter was added

        :return: An LDAP filter string
        """
        if self.__ldap_filter:
            return str(self.__ldap_filter)
        return None


class EventListenerHook(object):
    """
    Event listener hook interface prototype.  The method in this class must be
    overridden for a service event listener hook to be called via whiteboard
    pattern
    """

    def event(self, service_event, listener_dict):
        """
        Method called when a service event is triggered.

        :param service_event: The ServiceEvent being triggered
        :param listener_dict: A dictionary associating a bundle context to a
                              list of listeners
        """
        pass
