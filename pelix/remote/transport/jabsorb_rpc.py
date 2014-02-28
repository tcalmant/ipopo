#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix Remote Services: Java-compatible RPC, based on the Jabsorb library

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 1.1
:status: Beta

..

    Copyright 2014 isandlaTech

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

# Documentation strings format
__docformat__ = "restructuredtext en"

# Module version
__version_info__ = (1, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------

# JSON-RPC
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCDispatcher, \
    NoMulticallResult
import jsonrpclib.jsonrpc as jsonrpclib

# Cohorte
import pelix.misc.jabsorb as jabsorb

# iPOPO Decorators
from pelix.ipopo.decorators import ComponentFactory, Provides, Validate, \
    Invalidate, Requires, Property
import pelix.framework
import pelix.http
import pelix.remote.beans
from pelix.remote import RemoteServiceError
from pelix.utilities import to_str

# Standard library
import logging
import socket
import threading
import uuid

# ------------------------------------------------------------------------------

JABSORB_CONFIG = 'ecf.jabsorb'
""" Remote Service configuration constant """

PROP_ENDPOINT_NAME = '{0}.name'.format(JABSORB_CONFIG)
""" Name of the endpoint """

PROP_HTTP_ACCESSES = '{0}.accesses'.format(JABSORB_CONFIG)
""" HTTP accesses (comma-separated String) """

HOST_SERVLET_PATH = "/JABSORB-RPC"
""" Default servlet path """

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

class _JabsorbRpcServlet(SimpleJSONRPCDispatcher):
    """
    A JSON-RPC servlet, replacing the SimpleJSONRPCDispatcher from jsonrpclib,
    converting data from and to Jabsorb format.
    """
    def __init__(self, dispatch_method, encoding=None):
        """
        Sets up the servlet
        """
        SimpleJSONRPCDispatcher.__init__(self, encoding)

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
            pass

        # Avoid calling this method in the "except" block, as it would be in
        # an exception state (logs will consider the KeyError as a failure)
        return self._dispatch_method(name, params)


    def do_GET(self, request, response):
        """
        Handles a GET request
        """
        response.send_content(200, "Jabsorb-RPC servlet", "text/plain")


    def do_POST(self, request, response):
        """
        Handle a POST request

        :param request: The HTTP request bean
        :param request: The HTTP response handler
        """
        # Get the request JSON content
        data = jsonrpclib.loads(to_str(request.read_data()))

        # Convert from Jabsorb
        data = jabsorb.from_jabsorb(data)

        # Dispatch
        try:
            result = self._unmarshaled_dispatch(data, self._simple_dispatch)

        except NoMulticallResult:
            # No result (never happens, but who knows...)
            result = None

        if result is not None:
            # Convert result to Jabsorb
            if 'result' in result:
                result['result'] = jabsorb.to_jabsorb(result['result'])

            # Store JSON
            result = jsonrpclib.jdumps(result)

        else:
            # It was a notification
            result = ''

        # Send the result
        response.send_content(200, result, 'application/json-rpc')

# ------------------------------------------------------------------------------

@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_JABSORBRPC_EXPORTER)
@Provides(pelix.remote.SERVICE_EXPORT_PROVIDER)
@Requires('_dispatcher', pelix.remote.SERVICE_DISPATCHER)
@Requires('_http', pelix.http.HTTP_SERVICE)
@Property('_path', pelix.http.HTTP_SERVLET_PATH, HOST_SERVLET_PATH)
@Property('_kinds', pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
          (JABSORB_CONFIG, 'jabsorb-rpc'))
class JabsorbRpcServiceExporter(object):
    """
    JABSORB-RPC Remote Services exporter
    """
    def __init__(self):
        """
        Sets up the exporter
        """
        # Bundle context
        self._context = None

        # Dispatcher
        self._dispatcher = None

        # Supported configurations
        self._kinds = None

        # HTTP Service
        self._http = None
        self._path = None

        # JSON-RPC servlet
        self._servlet = None

        # Exported services: Name -> ExportEndpoint
        self.__endpoints = {}

        # Thread safety
        self.__lock = threading.Lock()


    def _dispatch(self, method, params):
        """
        Called by the JSON-RPC servlet: calls the method of an exported service
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
        jabsorb_name = svc_ref.get_property(PROP_ENDPOINT_NAME)
        if jabsorb_name:
            # The end point name has been configured in the Jabsorb way
            name = jabsorb_name

        with self.__lock:
            if name in self.__endpoints:
                # Already known end point
                raise NameError("Already known end point {0} for JABSORB-RPC" \
                                .format(name))

            # Get the service (let it raise a BundleException if any)
            service = self._context.get_service(svc_ref)

            # Prepare extra properties
            properties = {PROP_ENDPOINT_NAME: name}

            # HTTP accesses, as a comma-separated string
            properties[PROP_HTTP_ACCESSES] = self.get_accesses()

            # Prepare the export endpoint
            try:
                endpoint = pelix.remote.beans.ExportEndpoint(str(uuid.uuid4()),
                                                             fw_uid,
                                                             self._kinds,
                                                             name, svc_ref,
                                                             service,
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
        with self.__lock:
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
        with self.__lock:
            try:
                # Clean up storage
                del self.__endpoints[endpoint.name]

            except KeyError:
                # Unknown endpoint
                _logger.warning("Unknown endpoint: %s", endpoint)

            else:
                # Release the service
                svc_ref = endpoint.reference
                self._context.unget_service(svc_ref)


    def get_accesses(self):
        """
        Retrieves the URLs to access this component as a comma-separated list.
        The first URL contains a '{server}' variable
        """
        # Get HTTP server access
        host, port = self._http.get_access()
        if ':' in host:
            # IPv6 address
            host = '[{0}]'.format(host)

        # Return two accesses: with a {server} variable and with the
        # bound address
        model = "http://{{server}}:{0}{1}".format(port, self._path)
        return ','.join((model, model.format(server=host)))


    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Store the context
        self._context = context

        # Create/register the servlet
        self._servlet = _JabsorbRpcServlet(self._dispatch)
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
    def __init__(self, uid, name, url, on_error):
        """
        Sets up the call proxy

        :param uid: End point UID
        :param name: End point name
        :param url: End point URL
        :param on_error: A method to call back in case of socket error
        """
        self.__uid = uid
        self.__name = name
        self.__url = url
        self.__on_error = on_error


    def __getattr__(self, name):
        """
        Prefixes the requested attribute name by the endpoint name
        """
        # Make a proxy for this call
        # This is an ugly trick to handle multithreaded calls, as the underlying
        # proxy re-uses the same connection when possible: sometimes it means
        # sending a request before retrieving a result
        proxy = jsonrpclib.ServerProxy(self.__url)

        def wrapped_call(*args, **kwargs):
            """
            Wrapped call
            """
            # Get the method from the proxy
            method = getattr(proxy, "{0}.{1}".format(self.__name, name))

            # Convert arguments
            args = [jabsorb.to_jabsorb(arg) for arg in args]
            kwargs = dict([(key, jabsorb.to_jabsorb(value))
                               for key, value in kwargs.items()])

            try:
                result = method(*args, **kwargs)
                return jabsorb.from_jabsorb(result)

            except socket.error:
                # In case of transport error, look if the service has gone away
                if self.__on_error is not None:
                    self.__on_error(self.__uid)

                # Let the exception stop the caller
                raise

        return wrapped_call

# ------------------------------------------------------------------------------

@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_JABSORBRPC_IMPORTER)
@Provides(pelix.remote.SERVICE_IMPORT_ENDPOINT_LISTENER)
@Property('_kinds', pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
          (JABSORB_CONFIG, 'jabsorb-rpc'))
class JabsorbRpcServiceImporter(object):
    """
    JABSORB-RPC Remote Services importer
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
        self.__reg_lock = threading.Lock()


    def endpoint_added(self, endpoint):
        """
        An end point has been imported
        """
        configs = set(endpoint.configurations)
        if '*' not in configs and not configs.intersection(self._kinds):
            # Not for us
            return

        # Get the access URL
        access_url = endpoint.properties.get(PROP_HTTP_ACCESSES)
        if not access_url:
            # No URL information
            _logger.warning("No access URL given: %s", endpoint)
            return

        # Get the first URL in the list
        access_url = access_url.split(',')[0]

        # Replace the server variable
        if endpoint.server:
            server = endpoint.server
            if ':' in server and not server[0] == '[':
                # IPv6 address
                server = '[{0}]'.format(server)

            access_url = access_url.replace('{server}', server)

        _logger.debug("Chosen access: %s", access_url)

        with self.__reg_lock:
            # Already known end point
            if endpoint.uid in self.__registrations:
                return

            # Compute the name
            name = endpoint.properties.get(PROP_ENDPOINT_NAME)
            if not name:
                _logger.error("Remote endpoint has no name: %s", endpoint)
                return

            # Register the service
            svc = _ServiceCallProxy(endpoint.uid, name, access_url,
                                    self._unregister)
            svc_reg = self._context.register_service(endpoint.specifications,
                                                     svc, endpoint.properties)

            # Store references
            self.__registrations[endpoint.uid] = svc_reg


    def endpoint_updated(self, endpoint, old_properties):
        """
        An end point has been updated
        """
        with self.__reg_lock:
            try:
                # Update service properties
                svc_reg = self.__registrations[endpoint.uid]
                svc_reg.set_properties(endpoint.properties)

            except KeyError:
                # Unknown end point
                return


    def endpoint_removed(self, endpoint):
        """
        An end point has been removed
        """
        with self.__reg_lock:
            if endpoint.uid in self.__registrations:
                # Unregister the end point
                self._unregister(endpoint.uid)


    def _unregister(self, endpoint_uid):
        """
        Unregisters the service associated to the given UID

        :param endpoint_uid: An end point UID
        :return: True on success, else False
        """
        try:
            # Pop references
            svc_reg = self.__registrations.pop(endpoint_uid)

            # Unregister the service
            svc_reg.unregister()
            return True

        except KeyError:
            _logger.debug("Unknown end point %s", endpoint_uid)
            return False

        except pelix.framework.BundleException as ex:
            _logger.debug("Can't unregister end point %s: %s", endpoint_uid, ex)
            return False


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
