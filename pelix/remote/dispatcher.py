#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Common dispatcher

Calls services according to the given method name and parameters

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.1
:status: Alpha

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

**TODO:**
* "system" methods (list, help, ...) ?
"""

# Version string
__version__ = "0.1.0"

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Remote Services constants
import pelix.remote
from pelix.remote import RemoteServiceError

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Provides, \
    Bind, Property, Validate

# Standard library
import logging
import uuid

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

@ComponentFactory('pelix-remote-dispatcher-factory')
@Provides(pelix.remote.SERVICE_DISPATCHER)
@Requires('_listeners', pelix.remote.SERVICE_ENDPOINT_LISTENER, True, True,
          "(listen.exported=*)")
@Property("_uid", "pelix.remote.dispatcher.uid")
class Dispatcher(object):
    """
    Common dispatcher for all exporters
    """
    def __init__(self):
        """
        Sets up the component
        """
        # Dispatcher UID (to avoid importing its own services)
        self._uid = None

        # Injected listeners
        self._listeners = []

        # Kind -> {Name -> Endpoint}
        self.__kind_endpoints = {}

        # UID -> Endpoint
        self.__endpoints = {}


    @Bind
    def bind(self, svc, svc_ref):
        """
        Service bound to the component
        """
        specs = svc_ref.get_property(pelix.framework.OBJECTCLASS)
        if pelix.remote.SERVICE_ENDPOINT_LISTENER in specs \
        and svc_ref.get_property(pelix.remote.PROP_LISTEN_EXPORTED):
            # Exported services listener
            try:
                for endpoint in self.__endpoints.values():
                    svc.endpoint_added(endpoint)

            except Exception as ex:
                _logger.exception("Error notifying bound listener: %s", ex)


    @property
    def uid(self):
        """
        Returns the UID of this dispatcher
        """
        return self._uid


    def add_endpoint(self, kind, name, endpoint):
        """
        Adds an end point to the dispatcher
        
        :param kind: A kind of end point
        :param name: The name of the end point
        :param endpoint: The description of the end point (Endpoint object)
        :raise KeyError: Already known end point
        :raise ValueError: Invalid end point object
        """
        if not kind:
            raise ValueError("Empty kind given")
        elif not name:
            raise ValueError("Empty name given")
        elif endpoint is None:
            raise ValueError("No end point given")

        # Get or set the map for the given kind
        kind_map = self.__kind_endpoints.setdefault(kind, {})
        if name in kind_map:
            raise KeyError("Already known end point: {0}".format(name))

        # Store the end point
        kind_map[name] = endpoint
        self.__endpoints[endpoint.uid] = endpoint

        # Call listeners
        if self._listeners:
            for listener in self._listeners[:]:
                listener.endpoint_added(endpoint)

        return True


    def update_endpoint(self, kind, name, endpoint, old_properties):
        """
        Adds an end point to the dispatcher
        
        :param kind: A kind of end point
        :param name: The name of the end point
        :param new_properties: The new properties of the service
        :raise KeyError: Unknown end point
        :raise ValueError: Invalid end point object
        """
        if not kind:
            raise ValueError("Empty kind given")
        elif not name:
            raise ValueError("Empty name given")
        elif endpoint is None:
            raise ValueError("No end point given")

        # Get or set the map for the given kind
        kind_map = self.__kind_endpoints.setdefault(kind, {})
        if name not in kind_map:
            raise KeyError("Unknown known end point: {0}".format(name))

        elif endpoint != kind_map[name]:
            raise ValueError("Not the good end point: {0}".format(name))

        # Call listeners
        if self._listeners:
            for listener in self._listeners:
                listener.endpoint_updated(endpoint, old_properties)


    def remove_endpoint(self, kind, name):
        """
        Removes the end point
        
        :param kind: A kind of end point
        :param name: The name of the end point
        :raise KeyError: Unknown end point
        """
        endpoint = self.__kind_endpoints[kind].pop(name)
        del self.__endpoints[endpoint.uid]

        # Call listeners
        if self._listeners:
            for listener in self._listeners[:]:
                listener.endpoint_removed(endpoint)


    def get_endpoints(self, kind=None, name=None):
        """
        Retrieves all end points matching the given kind and/or name
        
        :param kind: A kind of end point
        :param name: The name of the end point
        :return: A list of end point matching the parameters
        """
        if kind:
            # Filter by kind
            kind_map = self.__kind_endpoints.get(kind)
            if kind_map:
                # Get the found kind
                kind_maps = [kind_map]

            else:
                # Unknown kind
                return []

        else:
            # Get all kinds
            kind_maps = self.__kind_endpoints.values()

        results = []
        if name:
            # Filter by name
            for kind_map in kind_maps:
                endpoint = kind_map.get(name)
                if endpoint is not None:
                    results.append(endpoint)

        else:
            # No filter
            for kind_map in kind_maps:
                results.extend(kind_map.values())

        return results


    def get_service(self, kind, name):
        """
        Retrieves the instance of the service at the given end point for the
        given kind.
        
        :param kind: A kind of end point
        :param name: The name of the end point
        :return: The service corresponding to the given end point, or None
        """
        try:
            return self.__kind_endpoints[kind][name].instance

        except KeyError:
            return None


    def dispatch(self, kind, name, method, params):
        """
        Calls the service for the given kind with the name
        
        :param kind: A kind of end point
        :param name: The name of the end point
        :param method: Method to call
        :param params: List of parameters
        :return: The result of the method
        :raise RemoteServiceError: Unknown end point / method
        :raise: The exception raised by the method
        """
        # Get the service
        try:
            service = self.__kind_endpoints[kind][name].instance
        except KeyError:
            raise RemoteServiceError("Unknown endpoint: {0}".format(name))

        # Get the method
        method_ref = getattr(service, method, None)
        if method_ref is None:
            raise RemoteServiceError("Unknown method {0}".format(method))

        # Call it (let the errors be propagated)
        return method_ref(*params)


    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Generate a UID if necessary
        if not self._uid:
            self._uid = str(uuid.uuid4())
        _logger.debug("Remote Services dispatcher validated: uid=%s", self._uid)
