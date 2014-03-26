#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: JSON-RPC implementation

Based on a modified version of the 3rd-party package jsonrpclib.
A patched version of jsonrpclib will be released soon.

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.1.2
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

**TODO:**
* "system" methods (list, help, ...)
"""

# Module version
__version_info__ = (0, 1, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Validate, \
    Invalidate, Property, Provides

# Pelix constants
import pelix.http
import pelix.remote.beans
from pelix.remote import RemoteServiceError
from pelix.utilities import to_str

# Standard library
import logging
import uuid

# JSON-RPC module
import jsonrpclib
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCDispatcher

# ------------------------------------------------------------------------------

JSONRPC_CONFIGURATION = 'jsonrpc'
""" Remote Service configuration constant """

PROP_JSONRPC_URL = '{0}.url'.format(JSONRPC_CONFIGURATION)
""" JSON-RPC servlet URL """

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

class _JsonRpcServlet(SimpleJSONRPCDispatcher):
    """
    A JSON-RPC servlet that can be registered in the Pelix HTTP service

    Calls the dispatch method given in the constructor
    """
    def __init__(self, dispatch_method, encoding=None):
        """
        Sets up the servlet
        """
        SimpleJSONRPCDispatcher.__init__(self, encoding=encoding)

        # Register the system.* functions
        self.register_introspection_functions()

        # Make a link to the dispatch method
        self._dispatch_method = dispatch_method


    def _simple_dispatch(self, name, params):
        """
        Dispatch method
        """
        try:
            # Internal method
            return self.funcs[name](*params)

        except KeyError:
            # Other method
            return self._dispatch_method(name, params)


    def do_POST(self, request, response):
        """
        Handles a HTTP POST request

        :param request: The HTTP request bean
        :param request: The HTTP response handler
        """
        try:
            # Get the request content
            data = to_str(request.read_data())

            # Dispatch
            result = self._marshaled_dispatch(data, self._simple_dispatch)

            # Send the result
            response.send_content(200, result, 'application/json-rpc')

        except Exception as ex:
            response.send_content(500, "Internal error:\n{0}\n".format(ex),
                                  'text/plain')

# ------------------------------------------------------------------------------

@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_JSONRPC_EXPORTER)
@Provides(pelix.remote.SERVICE_EXPORT_PROVIDER)
@Requires('_http', pelix.http.HTTP_SERVICE)
@Property('_path', pelix.http.HTTP_SERVLET_PATH, '/JSON-RPC')
@Property('_kinds', pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
          (JSONRPC_CONFIGURATION,))
class JsonRpcServiceExporter(object):
    """
    JSON-RPC Remote Services exporter
    """
    def __init__(self):
        """
        Sets up the exporter
        """
        # Bundle context
        self._context = None

        # Handled configurations
        self._kinds = None

        # HTTP Service
        self._http = None
        self._path = None

        # JSON-RPC servlet
        self._servlet = None

        # Exported services: Name -> ExportEndpoint
        self.__endpoints = {}


    def _dispatch(self, method, params):
        """
        Called by the servlet: calls the method of an exported service
        """
        # Get the best matching name
        matching = None
        len_found = 0
        for name in self.__endpoints:
            if len(name) > len_found and method.startswith(name + "."):
                # Better matching end point name (longer that previous one)
                matching = name
                len_found = len(matching)

        if matching is None:
            # No end point name match
            raise KeyError("No end point found for: {0}".format(method))

        # Extract the method name. (+1 for the trailing dot)
        method_name = method[len_found + 1:]

        # Get the service
        try:
            service = self.__endpoints[matching].instance
        except KeyError:
            raise RemoteServiceError("Unknown endpoint: {0}".format(matching))

        # Get the method
        method_ref = getattr(service, method_name, None)
        if method_ref is None:
            raise RemoteServiceError("Unknown method {0}".format(method))

        # Call it (let the errors be propagated)
        return method_ref(*params)


    def handles(self, configurations):
        """
        Checks if this provider handles the given configuration types

        :param configurations: Configuration types
        """
        if configurations is None or configurations == '*':
            # 'Matches all'
            return True

        return bool(set(configurations).intersection(self._kinds))


    def export_service(self, svc_ref, name, fw_uid):
        """
        Prepares an export endpoint

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: An ExportEndpoint bean
        :raise NameError: Already known name
        :raise BundleException: Error getting the service
        """
        if name in self.__endpoints:
            # Already known end point
            raise NameError("Already known end point {0} for JSON-RPC" \
                            .format(name))

        # Get the service (let it raise a BundleException if any
        service = self._context.get_service(svc_ref)

        # Prepare extra properties
        properties = {PROP_JSONRPC_URL: self.get_access()}

        # Prepare the export endpoint
        try:
            endpoint = pelix.remote.beans.ExportEndpoint(str(uuid.uuid4()),
                                                         fw_uid, self._kinds,
                                                         name, svc_ref, service,
                                                         properties)
        except ValueError:
            # No specification to export (specifications filtered, ...)
            return None

        # Store information
        self.__endpoints[name] = endpoint

        # Return the endpoint bean
        return endpoint


    def update_export(self, endpoint, new_name, old_properties):
        """
        Updates an export endpoint

        :param endpoint: An ExportEndpoint bean
        :param new_name: Future endpoint name
        :param old_properties: Previous properties
        :raise NameError: Rename refused
        """
        try:
            if self.__endpoints[new_name] is not endpoint:
                # Reject the new name, as an endpoint uses it
                raise NameError("New name of {0} already used: {1}" \
                                .format(endpoint.name, new_name))

            else:
                # Name hasn't changed
                pass

        except KeyError:
            # No endpoint matches the new name: update the storage
            self.__endpoints[new_name] = self.__endpoints.pop(endpoint.name)

            # Update the endpoint
            endpoint.name = new_name


    def unexport_service(self, endpoint):
        """
        Deletes an export endpoint

        :param endpoint: An ExportEndpoint bean
        """
        # Clean up storage
        del self.__endpoints[endpoint.name]

        # Release the service
        svc_ref = endpoint.reference
        self._context.unget_service(svc_ref)


    def get_access(self):
        """
        Retrieves the URL to access this component
        """
        port = self._http.get_access()[1]
        return "http://{{server}}:{0}{1}".format(port, self._path)


    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Store the context
        self._context = context

        # Create/register the servlet
        self._servlet = _JsonRpcServlet(self._dispatch)
        self._http.register_servlet(self._path, self._servlet)


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        """
        # Unregister the servlet
        self._http.unregister(None, self._servlet)

        # Clean up the storage
        self.__endpoints.clear()

        # Clean up members
        self._servlet = None
        self._context = None

# ------------------------------------------------------------------------------

class _ServiceCallProxy(object):
    """
    Service call proxy
    """
    def __init__(self, name, url):
        """
        Sets up the call proxy

        :param name: End point name
        :param url: End point URL
        """
        self.__name = name
        self.__url = url


    def __getattr__(self, name):
        """
        Prefixes the requested attribute name by the endpoint name
        """
        # Make a proxy for this call
        # This is an ugly trick to handle multi-threaded calls, as the
        # underlying proxy re-uses the same connection when possible: sometimes
        # it means sending a request before retrieving a result
        proxy = jsonrpclib.jsonrpc.ServerProxy(self.__url)
        return getattr(proxy, "{0}.{1}".format(self.__name, name))


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_JSONRPC_IMPORTER)
@Provides(pelix.remote.SERVICE_IMPORT_ENDPOINT_LISTENER)
@Property('_kinds', pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
          (JSONRPC_CONFIGURATION,))
class JsonRpcServiceImporter(object):
    """
    JSON-RPC Remote Services importer
    """
    def __init__(self):
        """
        Sets up the exporter
        """
        # Bundle context
        self._context = None

        # Component properties
        self._kinds = None

        # Registered services (endpoint UID -> ServiceReference)
        self.__registrations = {}


    def endpoint_added(self, endpoint):
        """
        An end point has been imported
        """
        configs = set(endpoint.configurations)
        if '*' not in configs and not configs.intersection(self._kinds):
            # Not for us
            return

        # Get the access URL
        access_url = endpoint.properties.get(PROP_JSONRPC_URL)
        if not access_url:
            # No URL information
            _logger.warning("No access URL given: %s", endpoint)
            return

        if endpoint.server is not None:
            # Server information given
            access_url = access_url.format(server=endpoint.server)

        else:
            # Use the local IP as the source server, just in case
            local_server = "localhost"
            access_url = access_url.format(server=local_server)

        # Register the service
        svc = _ServiceCallProxy(endpoint.name, access_url)
        svc_reg = self._context.register_service(endpoint.specifications, svc,
                                                 endpoint.properties)

        # Store references
        self.__registrations[endpoint.uid] = svc_reg


    def endpoint_updated(self, endpoint, old_properties):
        """
        An end point has been updated
        """
        try:
            # Update service registration properties
            self.__registrations[endpoint.uid].set_properties(
                                                          endpoint.properties)

        except KeyError:
            # Unknown end point
            return


    def endpoint_removed(self, endpoint):
        """
        An end point has been removed
        """
        try:
            # Pop reference and unregister the service
            self.__registrations.pop(endpoint.uid).unregister()

        except KeyError:
            # Unknown end point
            return


    @Validate
    def validate(self, context):
        """
        Component validated
        """
        self._context = context


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        """
        self._context = None
