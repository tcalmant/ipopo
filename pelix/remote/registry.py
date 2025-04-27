#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Imported end points registry

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

import logging
import threading
from typing import Any, Dict, List, Optional, Union

import pelix.constants
import pelix.remote.beans as beans
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Instantiate,
    Invalidate,
    Provides,
    Requires,
    Validate,
)
from pelix.remote import RemoteServiceImportEndpointListener, RemoteServiceRegistry

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


@ComponentFactory("pelix-remote-imports-registry-factory")
@Provides(RemoteServiceRegistry)
@Requires(
    "_listeners",
    RemoteServiceImportEndpointListener,
    aggregate=True,
    optional=True,
)
@Instantiate("pelix-remote-imports-registry")
class ImportsRegistry(RemoteServiceRegistry):
    """
    Registry of discovered end points. End points are identified by their UID
    """

    _listeners: List[RemoteServiceImportEndpointListener]

    def __init__(self) -> None:
        # Framework UID
        self._fw_uid: Optional[str] = None

        # Framework UID -> [ImportEndpoint]
        self._frameworks: Dict[Optional[str], List[beans.ImportEndpoint]] = {}

        # End point UID -> ImportEndpoint
        self._registry: Dict[str, beans.ImportEndpoint] = {}

        # Lock
        self.__lock = threading.Lock()

    @BindField("_listeners", if_valid=True)
    def _bind_listener(
        self,
        field: str,
        listener: RemoteServiceImportEndpointListener,
        svc_ref: ServiceReference[RemoteServiceImportEndpointListener],
    ) -> None:
        # pylint: disable=W0613
        """
        New listener bound
        """
        with self.__lock:
            # Late listener
            for endpoint in self._registry.values():
                try:
                    listener.endpoint_added(endpoint)
                except Exception as ex:
                    _logger.exception("Error calling listener: %s", ex)

    def add(self, endpoint: beans.ImportEndpoint) -> bool:
        """
        Registers an end point and notifies listeners. Does nothing if the
        endpoint UID was already known.

        :param endpoint: An :class:`~pelix.remote.beans.ImportEndpoint` object
        :return: True if the end point has been added
        """
        with self.__lock:
            # Check framework UID (avoid to import our own services)
            if endpoint.framework == self._fw_uid:
                return False

            # Check if the end point already exists
            if endpoint.uid in self._registry:
                # Already known end point: do nothing
                _logger.debug("Already known endpoint")
                return False

            # Store the end point
            self._registry[endpoint.uid] = endpoint
            if endpoint.framework:
                self._frameworks.setdefault(endpoint.framework, []).append(endpoint)

        # Notify listeners (out of lock)
        if self._listeners:
            for listener in self._listeners[:]:
                try:
                    listener.endpoint_added(endpoint)
                except Exception as ex:
                    _logger.exception("Error calling listener: %s", ex)
        return True

    def update(self, uid: str, new_properties: Dict[str, Any]) -> bool:
        """
        Updates an end point and notifies listeners

        :param uid: The UID of the end point
        :param new_properties: The new properties of the end point
        :return: True if the endpoint is known, else False
        """
        try:
            with self.__lock:
                # Update the stored end point
                stored_endpoint = self._registry[uid]

                # Replace the stored properties
                old_properties = stored_endpoint.properties.copy()
                stored_endpoint.properties = new_properties
        except KeyError:
            # Unknown end point: ignore it
            return False
        else:
            # Notify listeners
            if self._listeners:
                for listener in self._listeners[:]:
                    try:
                        listener.endpoint_updated(stored_endpoint, old_properties)
                    except Exception as ex:
                        _logger.exception("Error calling listener: %s", ex)
            return True

    def contains(self, endpoint: Union[str, beans.ImportEndpoint]) -> bool:
        """
        Checks if an endpoint is in the registry

        :param endpoint: An endpoint UID or an :class:`~pelix.remote.beans.ImportEndpoint` object
        :return: True if the endpoint is known, else False
        """
        if isinstance(endpoint, beans.ImportEndpoint):
            return endpoint.uid in self._registry

        return endpoint in self._registry

    # Support for the 'in' keyword
    __contains__ = contains

    def remove(self, uid: str) -> bool:
        """
        Unregisters an end point and notifies listeners

        :param uid: The UID of the end point to unregister
        :return: True if the endpoint was known
        """
        # Remove the end point from the individual storage
        try:
            endpoint = self._registry.pop(uid)
        except KeyError:
            # Unknown end point
            _logger.debug("Unknown end point UID: %s", uid)
            return False

        # Remove it from its framework storage, if any
        try:
            framework_endpoints = self._frameworks[endpoint.framework]
            if endpoint in framework_endpoints:
                framework_endpoints.remove(endpoint)
                if not framework_endpoints:
                    # Remove framework entry if there is no more endpoint
                    # from it
                    del self._frameworks[endpoint.framework]
        except (KeyError, ValueError):
            # Ignore the absence of reference in the framework storage
            pass

        # Notify listeners
        if self._listeners:
            for listener in self._listeners[:]:
                try:
                    listener.endpoint_removed(endpoint)
                except Exception as ex:
                    _logger.exception("Error calling listener: %s", ex)

        return True

    def lost_framework(self, uid: Optional[str]) -> None:
        """
        Unregisters all the end points associated to the given framework UID

        :param uid: The UID of a framework
        """
        # Get the end points of this framework
        endpoints = self._frameworks.pop(uid, [])
        for endpoint in endpoints:
            with self.__lock:
                # Remove endpoint from registry
                try:
                    del self._registry[endpoint.uid]
                except KeyError:
                    # The endpoint may have been removed by a listener
                    pass

            # Notify listeners
            if self._listeners:
                for listener in self._listeners[:]:
                    try:
                        listener.endpoint_removed(endpoint)
                    except Exception as ex:
                        _logger.exception("Error calling listener: %s", ex)

    @Validate
    def _validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        """
        Component invalidated: clean up storage
        """
        # Clean up
        self._fw_uid = None
        self._frameworks.clear()
        self._registry.clear()
