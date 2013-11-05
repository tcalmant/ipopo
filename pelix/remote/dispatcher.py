#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Common dispatcher

Calls services according to the given method name and parameters

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.2
:status: Beta

..

    Copyright 2013 isandlaTech

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

# Module version
__version_info__ = (0, 2, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Remote Services constants
import pelix.remote
from pelix.remote import RemoteServiceError

# HTTP constants
import pelix.http

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Provides, \
    Bind, Property, Validate, Invalidate, Instantiate
from pelix.utilities import to_str

# Standard library
import json
import logging
import threading

try:
    # Python 3
    import http.client as httplib

except ImportError:
    # Python 2
    import httplib

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

@ComponentFactory('pelix-remote-dispatcher-factory')
@Provides(pelix.remote.SERVICE_DISPATCHER)
@Requires('_listeners', pelix.remote.SERVICE_ENDPOINT_LISTENER, True, True,
          "(listen.exported=*)")
@Instantiate('pelix-remote-dispatcher')
class Dispatcher(object):
    """
    Common dispatcher for all exporters
    """
    def __init__(self):
        """
        Sets up the component
        """
        # Injected listeners
        self._listeners = []

        # Kind -> {Name -> Endpoint}
        self.__kind_endpoints = {}

        # UID -> Endpoint
        self.__endpoints = {}

        # Lock
        self.__lock = threading.Lock()


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

        with self.__lock:
            # Get or set the map for the given kind
            kind_map = self.__kind_endpoints.setdefault(kind, {})
            if name in kind_map:
                raise KeyError("Already known end point: {0}".format(name))

            # Store the end point
            kind_map[name] = endpoint
            self.__endpoints[endpoint.uid] = endpoint

        # Call listeners (out of the lock)
        if self._listeners:
            for listener in self._listeners[:]:
                listener.endpoint_added(endpoint)

        return True


    def update_endpoint(self, kind, name, endpoint, old_properties):
        """
        Adds an end point to the dispatcher

        :param kind: A kind of end point
        :param name: The name of the end point
        :param endpoint: The updated Endpoint object
        :param old_properties: The previous properties of the service
        :raise KeyError: Unknown end point
        :raise ValueError: Invalid end point object
        """
        if not kind:
            raise ValueError("Empty kind given")
        elif not name:
            raise ValueError("Empty name given")
        elif endpoint is None:
            raise ValueError("No end point given")

        with self.__lock:
            # Get or set the map for the given kind
            kind_map = self.__kind_endpoints.setdefault(kind, {})
            if name not in kind_map:
                raise KeyError("Unknown known end point: {0}".format(name))

            elif endpoint != kind_map[name]:
                raise ValueError("Not the right end point: {0}".format(name))

        # Call listeners (out of the lock)
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
        with self.__lock:
            endpoint = self.__kind_endpoints[kind].pop(name)
            del self.__endpoints[endpoint.uid]

        # Call listeners (out of the lock)
        if self._listeners:
            for listener in self._listeners[:]:
                listener.endpoint_removed(endpoint)


    def get_endpoint(self, uid):
        """
        Retrieves an end point description, selected by its UID.
        Returns None if the UID is unknown.

        :param uid: UID of an end point
        :return: The end point description
        """
        return self.__endpoints.get(uid)


    def get_endpoints(self, kind=None, name=None):
        """
        Retrieves all end points matching the given kind and/or name

        :param kind: A kind of end point
        :param name: The name of the end point
        :return: A list of end point matching the parameters
        """
        with self.__lock:
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
        :raise Exception: The exception raised by the method
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

# -----------------------------------------------------------------------------

@ComponentFactory(pelix.remote.FACTORY_REGISTRY_SERVLET)
@Provides(pelix.http.HTTP_SERVLET)
@Provides(pelix.remote.SERVICE_DISPATCHER_SERVLET, "_controller")
@Requires('_dispatcher', pelix.remote.SERVICE_DISPATCHER)
@Requires('_registry', pelix.remote.SERVICE_REGISTRY)
@Property('_path', pelix.http.HTTP_SERVLET_PATH, "/pelix-dispatcher")
class RegistryServlet(object):
    """
    Servlet to access the content of the registry
    """
    def __init__(self):
        """
        Sets up members
        """
        # The framework UID
        self._fw_uid = None

        # The dispatcher
        self._dispatcher = None

        # The imported services registry
        self._registry = None

        # Controller for the provided service:
        # => activate only if bound to a server
        self._controller = False

        # Servlet path property
        self._path = None

        # Ports of exposing servers
        self._ports = []


    def bound_to(self, path, parameters):
        """
        This servlet has been bound to a server

        :param path: The servlet path in the server
        :param parameters: The servlet/server parameters
        """
        port = parameters['http.port']
        if port not in self._ports:
            # Get its access port
            self._ports.append(port)

            # Activate the service, we're bound to a server
            self._controller = True


    def unbound_from(self, path, parameters):
        """
        This servlet has been unbound from a server

        :param path: The servlet path in the server
        :param parameters: The servlet/server parameters
        """
        port = parameters['http.port']
        if port in self._ports:
            # Remove its access port
            self._ports.remove(port)

            # Deactivate the service if no more server available
            if not self._ports:
                self._controller = False


    def do_GET(self, request, response):
        """
        Handles a GET request

        :param request: Request handler
        :param response: Response handler
        """
        # Split the path
        path_parts = request.get_path().split('/')

        if path_parts[-2] == "endpoint":
            # /endpoint/<uid>: specific end point
            uid = path_parts[-1]
            endpoint = self.get_endpoint(uid)
            if endpoint is None:
                response.send_content(404, "Unknown UID: {0}".format(uid),
                                      "text/plain")
                return

            else:
                data = self._make_endpoint_dict(endpoint)

        elif path_parts[-1] == "endpoints":
            # /endpoints: all end points
            endpoints = self.get_endpoints()
            if not endpoints:
                data = []

            else:
                data = [self._make_endpoint_dict(endpoint)
                        for endpoint in endpoints]

        else:
            # Unknown
            response.send_content(404, "Unhandled path", "text/plain")
            return

        # Convert the result to JSON
        data = json.dumps(data)

        # Send the result
        response.send_content(200, data, 'application/json')


    def do_POST(self, request, response):
        """
        Handles a POST request

        :param request: Request handler
        :param response: Response handler
        """
        # Read the content
        endpoints = json.loads(to_str(request.read_data()))
        if endpoints:
            # Got something
            sender = request.get_client_address()[0]
            for endpoint in endpoints:
                self.register_endpoint(sender, endpoint)

        # We got the end points
        response.send_content(200, 'OK', 'text/plain')


    def _make_endpoint_dict(self, endpoint):
        """
        Converts the end point into a dictionary

        :param endpoint: The end point to convert
        :return: A dictionary
        """
        # Filter the ObjectClass property
        properties = endpoint.reference.get_properties()
        del properties[pelix.framework.OBJECTCLASS]

        return {"sender": self._fw_uid,
                "uid": endpoint.uid,
                "kind": endpoint.kind,
                "name": endpoint.name,
                "url": endpoint.url,
                "specifications": endpoint.specifications,
                "properties": properties}


    def filter_properties(self, framework_uid, properties):
        """
        Replaces in-place export properties by import ones

        :param framework_uid: The UID of the framework exporting the service
        :param properties: End point properties
        :return: The filtered dictionary.
        """
        # Add the "imported" property
        properties[pelix.remote.PROP_IMPORTED] = True

        # Replace the "exported configs"
        if pelix.remote.PROP_EXPORTED_CONFIGS in properties:
            properties[pelix.remote.PROP_IMPORTED_CONFIGS] = \
                                properties[pelix.remote.PROP_EXPORTED_CONFIGS]

        # Clear export properties
        for name in (pelix.remote.PROP_EXPORTED_CONFIGS,
                     pelix.remote.PROP_EXPORTED_INTERFACES):
            if name in properties:
                del properties[name]

        # Add the framework UID to the properties
        properties[pelix.remote.PROP_FRAMEWORK_UID] = framework_uid

        return properties


    def register_endpoint(self, host_address, endpoint_dict):
        """
        Registers a new end point in the registry

        :param host_address: Address of the service exporter
        :param endpoint_dict: An end point description dictionary (result of
                              a request to the dispatcher servlet)
        """
        # Get the UID of the framework exporting the service
        framework = endpoint_dict['sender']

        # Filter properties
        properties = self.filter_properties(framework,
                                            endpoint_dict['properties'])

        # Format the URL
        url = endpoint_dict['url'].format(server=host_address)

        # Create the end point object
        endpoint = pelix.remote.beans.ImportEndpoint(endpoint_dict['uid'], \
                                 framework, endpoint_dict['kind'],
                                 endpoint_dict['name'], url,
                                 endpoint_dict['specifications'], properties)

        # Register it
        self._registry.add(endpoint)


    def get_access(self):
        """
        Returns the port and path to access this servlet with the first
        bound HTTP service.
        Returns None if this servlet is still not bound to a server

        :return: A tuple: (port, path) or None
        """
        if self._ports:
            return (self._ports[0], self._path)


    def get_endpoints(self):
        """
        Returns the complete list of end points

        :return: The list of all known end points
        """
        return self._dispatcher.get_endpoints()


    def get_endpoint(self, uid):
        """
        Returns the end point with the given UID or None.

        :return: The end point description or None
        """
        return self._dispatcher.get_endpoint(uid)


    def send_discovered(self, host, port, path):
        """
        Sends a "discovered" HTTP POST request to the dispatcher servlet of the
        framework that has been discovered

        :param host: The address of the sender
        :param port: Port of the HTTP server of the sender
        :param path: Path of the dispatcher servlet
        """
        # Get the end points from the dispatcher
        endpoints = [self._make_endpoint_dict(endpoint)
                     for endpoint in self._dispatcher.get_endpoints()]

        # Request the end points
        try:
            conn = httplib.HTTPConnection(host, port)
            conn.request("POST", path,
                         json.dumps(endpoints),
                         {"Content-Type": "application/json"})

            result = conn.getresponse()
            data = result.read()
            conn.close()

        except Exception as ex:
            _logger.exception("Error accessing a discovered framework: %s", ex)

        else:
            if result.status != 200:
                # Not a valid result
                _logger.warning("Got an HTTP code %d when contacting a "
                                "discovered framework: %s",
                                result.status, data)


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        """
        # Clean up
        self._fw_uid = None


    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Get the framework UID
        self._fw_uid = context.get_property(pelix.framework.FRAMEWORK_UID)

        _logger.debug("Dispatcher servlet for %s on %s", self._fw_uid,
                      self._path)
