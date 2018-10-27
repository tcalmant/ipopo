#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Imported end points registry

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
import logging
import threading

# Remote Services constants
import pelix.constants
import pelix.remote
import pelix.remote.beans as beans

# iPOPO decorators
from pelix.ipopo.decorators import (
    ComponentFactory,
    Requires,
    Provides,
    Instantiate,
    Invalidate,
    Validate,
    BindField,
)

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


@ComponentFactory("pelix-remote-imports-registry-factory")
@Provides(pelix.remote.SERVICE_REGISTRY)
@Requires(
    "_listeners",
    pelix.remote.SERVICE_IMPORT_ENDPOINT_LISTENER,
    aggregate=True,
    optional=True,
)
@Instantiate("pelix-remote-imports-registry")
class ImportsRegistry(object):
    """
    Registry of discovered end points. End points are identified by their UID
    """

    def __init__(self):
        # Listeners (injected)
        self._listeners = []

        # Framework UID
        self._fw_uid = None

        # Framework UID -> [ImportEndpoint]
        self._frameworks = {}

        # End point UID -> ImportEndpoint
        self._registry = {}

        # Lock
        self.__lock = threading.Lock()

    @BindField("_listeners", if_valid=True)
    def _bind_listener(self, field, listener, svc_ref):
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

    def add(self, endpoint):
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
                self._frameworks.setdefault(endpoint.framework, []).append(
                    endpoint
                )

        # Notify listeners (out of lock)
        if self._listeners:
            for listener in self._listeners[:]:
                try:
                    listener.endpoint_added(endpoint)
                except Exception as ex:
                    _logger.exception("Error calling listener: %s", ex)
        return True

    def update(self, uid, new_properties):
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
                        listener.endpoint_updated(
                            stored_endpoint, old_properties
                        )
                    except Exception as ex:
                        _logger.exception("Error calling listener: %s", ex)
            return True

    def contains(self, endpoint):
        """
        Checks if an endpoint is in the registry

        :param endpoint: An endpoint UID or an
                         :class:`~pelix.remote.beans.ImportEndpoint` object
        :return: True if the endpoint is known, else False
        """
        if isinstance(endpoint, beans.ImportEndpoint):
            return endpoint.uid in self._registry

        return endpoint in self._registry

    # Support for the 'in' keyword
    __contains__ = contains

    def remove(self, uid):
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

    def lost_framework(self, uid):
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
    def _validate(self, context):
        """
        Component validated
        """
        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

    @Invalidate
    def _invalidate(self, _):
        """
        Component invalidated: clean up storage
        """
        # Clean up
        self._fw_uid = None
        self._frameworks.clear()
        self._registry.clear()
