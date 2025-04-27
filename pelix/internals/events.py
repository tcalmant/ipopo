#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Event beans for Pelix.

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

from typing import TYPE_CHECKING, Any, Dict, Generic, Optional, TypeVar

if TYPE_CHECKING:
    from pelix.framework import Bundle
    from pelix.internals.registry import ServiceReference

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"


T = TypeVar("T")

# ------------------------------------------------------------------------------


class BundleEvent:
    """
    Represents a bundle event
    """

    __slots__ = ("__bundle", "__kind")

    INSTALLED = 1
    """The bundle has been installed."""

    STARTED = 2
    """The bundle has been started."""

    STARTING = 128
    """The bundle is about to be activated."""

    STOPPED = 4
    """
    The bundle has been stopped. All of its services have been unregistered.
    """

    STOPPING = 256
    """The bundle is about to deactivated."""

    STOPPING_PRECLEAN = 512
    """
    The bundle has been deactivated, but some of its services may still remain.
    """

    UNINSTALLED = 16
    """The bundle has been uninstalled."""

    UPDATED = 8
    """The bundle has been updated. (called after STARTED) """

    UPDATE_BEGIN = 32
    """ The bundle will be updated (called before STOPPING) """

    UPDATE_FAILED = 64
    """ The bundle update has failed. The bundle might be in RESOLVED state """

    def __init__(self, kind: int, bundle: "Bundle") -> None:
        """
        Sets up the event
        """
        self.__kind = kind
        self.__bundle = bundle

    def __str__(self) -> str:
        """
        String representation
        """
        return f"BundleEvent({self.__kind}, {self.__bundle})"

    def get_bundle(self) -> "Bundle":
        """
        Retrieves the modified bundle
        """
        return self.__bundle

    def get_kind(self) -> int:
        """
        Retrieves the kind of event
        """
        return self.__kind


# ------------------------------------------------------------------------------


class ServiceEvent(Generic[T]):
    """
    Represents a service event
    """

    __slots__ = ("__kind", "__reference", "__previous_properties")

    REGISTERED = 1
    """ This service has been registered """

    MODIFIED = 2
    """ The properties of a registered service have been modified """

    UNREGISTERING = 4
    """ This service is in the process of being unregistered """

    MODIFIED_ENDMATCH = 8
    """
    The properties of a registered service have been modified and the new
    properties no longer match the listener's filter
    """

    def __init__(
        self,
        kind: int,
        reference: "ServiceReference[T]",
        previous_properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Sets up the event

        :param kind: Kind of event
        :param reference: Reference to the modified service
        :param previous_properties: Previous service properties (for MODIFIED and MODIFIED_ENDMATCH events)
        """
        self.__kind = kind
        self.__reference = reference

        if previous_properties is not None and not isinstance(previous_properties, dict):
            # Accept None or dict() only
            previous_properties = {}

        self.__previous_properties = previous_properties

    def __str__(self) -> str:
        """
        String representation
        """
        return f"ServiceEvent({self.__kind}, {self.__reference})"

    def get_previous_properties(self) -> Optional[Dict[str, Any]]:
        """
        Returns the previous values of the service properties, meaningless if
        the the event is not MODIFIED nor MODIFIED_ENDMATCH.

        :return: The previous properties of the service
        """
        return self.__previous_properties

    def get_service_reference(self) -> "ServiceReference[T]":
        """
        Returns the reference to the service associated to this event

        :return: A ServiceReference object
        """
        return self.__reference

    def get_kind(self) -> int:
        """
        Returns the kind of service event (see the constants)

        :return: the kind of service event
        """
        return self.__kind
