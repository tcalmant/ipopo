#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: XML-RPC implementation

Based on standard package xmlrpclib

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
import xmlrpc.client as xmlrpclib
from typing import Any, Callable, Dict, Iterable, Optional, Union
from xmlrpc.server import SimpleXMLRPCDispatcher

import pelix.http
from pelix.internals.registry import ServiceReference
import pelix.remote
from pelix.remote.beans import ImportEndpoint
import pelix.remote.transport.commons as commons
from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Requires, Validate
from pelix.utilities import to_str

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

XMLRPC_CONFIGURATION = "xmlrpc"
""" Remote Service configuration constant """

PROP_XMLRPC_URL = f"{XMLRPC_CONFIGURATION}.url"
""" XML-RPC servlet URL """

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class _XmlRpcServlet(SimpleXMLRPCDispatcher, pelix.http.Servlet):
    """
    A XML-RPC servlet that can be registered in the Pelix HTTP service

    Calls the dispatch method given in the constructor
    """

    def __init__(
        self,
        dispatch_method: Callable[[str, Union[Iterable[Any], Dict[str, Any]]], Any],
        encoding: Optional[str] = None,
    ) -> None:
        """
        Sets up the servlet
        """
        SimpleXMLRPCDispatcher.__init__(self, allow_none=True, encoding=encoding)

        # Register the system.* functions
        self.register_introspection_functions()

        # Make a link to the dispatch method
        self._dispatch_method = dispatch_method

    def _simple_dispatch(self, name: str, params: Union[Iterable[Any], Dict[str, Any]]) -> Any:
        """
        Dispatch method
        """
        try:
            # Internal method
            return self.funcs[name](*params)
        except KeyError:
            # Other method
            pass

        # Call the other method outside the except block, to avoid messy logs
        # in case of error
        return self._dispatch_method(name, params)

    def do_POST(
        self, request: pelix.http.AbstractHTTPServletRequest, response: pelix.http.AbstractHTTPServletResponse
    ) -> None:
        # pylint: disable=C0103
        """
        Handles a HTTP POST request

        :param request: The HTTP request bean
        :param response: The HTTP response handler
        """
        # Get the request content
        data = to_str(request.read_data())

        # Dispatch
        result = self._marshaled_dispatch(data, self._simple_dispatch)  # type: ignore

        # Send the result
        response.send_content(200, result, "text/xml")


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_XMLRPC_EXPORTER)
@Provides(pelix.remote.RemoteServiceExportProvider)
@Requires("_http", pelix.http.HTTPService)
@Property("_path", pelix.http.HTTP_SERVLET_PATH, "/XML-RPC")
@Property(
    "_kinds",
    pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
    (XMLRPC_CONFIGURATION,),
)
class XmlRpcServiceExporter(commons.AbstractRpcServiceExporter):
    """
    XML-RPC Remote Services exporter
    """

    _http: pelix.http.HTTPService

    def __init__(self) -> None:
        """
        Sets up the exporter
        """
        # Call parent
        super(XmlRpcServiceExporter, self).__init__()

        # HTTP Service
        self._path = ""

        # XML-RPC servlet
        self._servlet: Optional[pelix.http.Servlet] = None

    def get_access(self) -> str:
        """
        Retrieves the URL to access this component
        """
        port = self._http.get_access()[1]
        return "http{2}://{{server}}:{0}{1}".format(port, self._path, "s" if self._http.is_https() else "")

    def make_endpoint_properties(
        self, svc_ref: ServiceReference[Any], name: str, fw_uid: Optional[str]
    ) -> Dict[str, Any]:
        """
        Prepare properties for the ExportEndpoint to be created

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: A dictionary of extra endpoint properties
        """
        return {PROP_XMLRPC_URL: self.get_access()}

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        # Call parent
        super(XmlRpcServiceExporter, self).validate(context)

        # Create/register the servlet
        self._servlet = _XmlRpcServlet(self.dispatch)
        self._path = self._path or ""
        self._http.register_servlet(self._path, self._servlet)

    @Invalidate
    def invalidate(self, context: BundleContext) -> None:
        """
        Component invalidated
        """
        # Unregister the servlet
        self._http.unregister(None, self._servlet)

        # Call parent
        super(XmlRpcServiceExporter, self).invalidate(context)

        # Clean up members
        self._servlet = None


# ------------------------------------------------------------------------------


class _ServiceCallProxy:
    # pylint: disable=R0903
    """
    Service call proxy
    """

    def __init__(self, name: str, url: str) -> None:
        """
        Sets up the call proxy

        :param name: End point name
        :param url: End point URL
        """
        self.__name = name
        self.__url = url

    def __getattr__(self, name: str) -> Any:
        """
        Prefixes the requested attribute name by the endpoint name
        """
        # Make a proxy for this call
        # This is an ugly trick to handle multithreaded calls, as the
        # underlying proxy re-uses the same connection when possible: sometimes
        # it means sending a request before retrieving a result
        proxy = xmlrpclib.ServerProxy(self.__url, allow_none=True)
        return getattr(proxy, f"{self.__name}.{name}")


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_XMLRPC_IMPORTER)
@Provides(pelix.remote.RemoteServiceImportEndpointListener)
@Property(
    "_kinds",
    pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
    (XMLRPC_CONFIGURATION,),
)
class XmlRpcServiceImporter(commons.AbstractRpcServiceImporter):
    """
    XML-RPC Remote Services importer
    """

    def make_service_proxy(self, endpoint: ImportEndpoint) -> Any:
        """
        Creates the proxy for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        :return: A service proxy
        """
        if not endpoint.name:
            _logger.warning("Ignoring endpoint with no name: %s", endpoint)
            return None

        # Get the access URL
        access_url = endpoint.properties.get(PROP_XMLRPC_URL)
        if not access_url:
            # No URL information
            _logger.warning("No access URL given: %s", endpoint)
            return None

        if endpoint.server is not None:
            # Server information given
            access_url = access_url.format(server=endpoint.server)
        else:
            # Use the local IP as the source server, just in case
            local_server = "localhost"
            access_url = access_url.format(server=local_server)

        # Return the proxy
        return _ServiceCallProxy(endpoint.name, access_url)

    def clear_service_proxy(self, endpoint: ImportEndpoint) -> None:
        """
        Destroys the proxy made for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        """
        # Nothing to do
        return
