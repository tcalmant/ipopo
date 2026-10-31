#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: JSON-RPC implementation

Based on a modified version of the 3rd-party package jsonrpclib-pelix.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.3.0

..

    Copyright 2026 Thomas Calmant

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
import uuid
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import jsonrpclib.config
import jsonrpclib.jsonrpc
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCDispatcher

import pelix.http
import pelix.remote
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Requires, Validate
from pelix.remote import security
from pelix.remote.beans import ImportEndpoint
from pelix.remote.transport import commons
from pelix.remote.transport.xmlrpc_client import LimitedTransportMixIn
from pelix.security import SecurityError
from pelix.utilities import to_str

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["JSONRPC_CONFIGURATION", "PROP_JSONRPC_URL", "make_client_transport"]

# ------------------------------------------------------------------------------

JSONRPC_CONFIGURATION = "jsonrpc"
""" Remote Service configuration constant """

PROP_JSONRPC_URL = f"{JSONRPC_CONFIGURATION}.url"
""" JSON-RPC servlet URL """

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class _JsonRpcServlet(SimpleJSONRPCDispatcher):
    """
    A JSON-RPC servlet that can be registered in the Pelix HTTP service

    Calls the dispatch method given in the constructor
    """

    def __init__(
        self,
        dispatch_method: Callable[[str, Iterable[Any] | dict[str, Any]], Any],
        encoding: str | None = None,
    ) -> None:
        """
        Sets up the servlet
        """
        SimpleJSONRPCDispatcher.__init__(self, encoding=encoding)

        # Register the system.* functions
        self.register_introspection_functions()

        # Make a link to the dispatch method
        self._dispatch_method = dispatch_method

    def _simple_dispatch(self, name: str, params: Iterable[Any] | dict[str, Any]) -> Any:
        """
        Dispatch method
        """
        try:
            # Internal method
            func = self.funcs[name]
        except KeyError:
            # Other method
            pass
        else:
            # Internal method found
            if isinstance(params, dict):
                return func(**params)

            return func(*params)

        # Call the other method outside the except block, to avoid messy logs
        # in case of error
        try:
            return self._dispatch_method(name, params)
        except SecurityError as ex:
            # An expected answer, not an internal error
            return jsonrpclib.jsonrpc.Fault(-32001, security.refusal_message(ex))

    def do_POST(
        self, request: pelix.http.AbstractHTTPServletRequest, response: pelix.http.AbstractHTTPServletResponse
    ) -> None:
        """
        Handles a HTTP POST request

        :param request: The HTTP request bean
        :param response: The HTTP response handler
        """
        if not pelix.http.check_content_type(request, response, pelix.http.JSON_CONTENT_TYPES):
            return

        try:
            # Get the request content
            data = to_str(request.read_data())

            # Dispatch
            result = self._marshaled_dispatch(data, self._simple_dispatch)

            # Send the result
            response.send_content(200, result, "application/json-rpc")
        except Exception:
            # The details describe the server: only the log gets them
            error_id = uuid.uuid4().hex
            _logger.exception("Error %s handling a JSON-RPC request", error_id)
            response.send_content(500, f"Internal error. Error ID: {error_id}\n", "text/plain")


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_JSONRPC_EXPORTER)
@Provides(pelix.remote.RemoteServiceExportProvider)
@Requires("_http", pelix.http.HTTPService)
@Property("_path", pelix.http.HTTP_SERVLET_PATH, "/JSON-RPC")
@Property("_auth_required", security.PROP_AUTH_REQUIRED, None)
@Property(
    "_kinds",
    pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
    (JSONRPC_CONFIGURATION,),
)
class JsonRpcServiceExporter(commons.AbstractRpcServiceExporter):
    """
    JSON-RPC Remote Services exporter
    """

    # HTTP Service
    _http: pelix.http.HTTPService

    def __init__(self) -> None:
        """
        Sets up the exporter
        """
        # Call parent
        super().__init__()

        # HTTP Service
        self._path: str = ""

        # JSON-RPC servlet
        self._servlet: pelix.http.Servlet | None = None
        self._auth_required: bool | None = None

    def is_local_only(self) -> bool:
        """
        Tells if the HTTP service can only be reached from the local host
        """
        return security.is_loopback_host(self._http.get_access()[0])

    def get_access(self) -> str:
        """
        Retrieves the URL to access this component
        """
        port = self._http.get_access()[1]
        return f"http{'s' if self._http.is_https() else ''}://{{server}}:{port}{self._path}"

    def make_endpoint_properties(
        self, svc_ref: ServiceReference[Any], name: str, fw_uid: str | None
    ) -> dict[str, Any]:
        """
        Prepare properties for the ExportEndpoint to be created

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: A dictionary of extra endpoint properties
        """
        return {PROP_JSONRPC_URL: self.get_access()}

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        # Call parent
        super().validate(context)

        # Create/register the servlet
        self._servlet = _JsonRpcServlet(self.dispatch)
        # Without the property, the setting of the HTTP service applies
        parameters = (
            None if self._auth_required is None else {pelix.http.HTTP_AUTH_REQUIRED: self._auth_required}
        )
        self._http.register_servlet(self._path, self._servlet, parameters)

    @Invalidate
    def invalidate(self, context: BundleContext) -> None:
        """
        Component invalidated
        """
        # Unregister the servlet
        self._http.unregister(None, self._servlet)

        # Call parent
        super().invalidate(context)

        # Clean up members
        self._servlet = None


# ------------------------------------------------------------------------------


# jsonrpclib doesn't follow the signatures of the xmlrpc.client stubs
class _JsonRpcTransport(LimitedTransportMixIn, jsonrpclib.jsonrpc.Transport):  # ty: ignore[invalid-method-override]
    pass


class _JsonRpcSafeTransport(LimitedTransportMixIn, jsonrpclib.jsonrpc.SafeTransport):  # ty: ignore[invalid-method-override]
    pass


def make_client_transport(
    url: str, limits: commons.ClientLimits, headers: Mapping[str, str] | None = None
) -> jsonrpclib.jsonrpc.Transport:
    """
    Prepares the transport of a JSON-RPC server proxy, applying the client limits

    :param url: URL of the server
    :param limits: The client limits
    :param headers: Headers to add to the requests (see :func:`pelix.remote.security.get_auth_headers`)
    :return: A transport for the ``ServerProxy`` of ``jsonrpclib``
    """
    config = jsonrpclib.config.DEFAULT
    if url.lower().startswith("https:"):
        transport = _JsonRpcSafeTransport(limits, config, None)
    else:
        transport = _JsonRpcTransport(limits, config)

    # The proxies ignore their own headers argument when given a transport
    if headers:
        transport.push_headers(dict(headers))
    return transport


class _ServiceCallProxy:
    """
    Service call proxy
    """

    def __init__(self, name: str, url: str, limits: commons.ClientLimits, headers: dict[str, str]) -> None:
        """
        Sets up the call proxy

        :param name: End point name
        :param url: End point URL
        :param limits: Limits of the calls
        :param headers: Authentication headers
        """
        self.__name = name
        self.__url = url
        self.__limits = limits
        self.__headers = headers

    def __getattr__(self, name: str) -> Any:
        """
        Prefixes the requested attribute name by the endpoint name
        """
        # Make a proxy for this call
        # This is an ugly trick to handle multi-threaded calls, as the
        # underlying proxy reuses the same connection when possible: sometimes
        # it means sending a request before retrieving a result
        proxy = jsonrpclib.jsonrpc.ServerProxy(
            self.__url,
            transport=make_client_transport(self.__url, self.__limits, self.__headers),
        )
        return getattr(proxy, f"{self.__name}.{name}")


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_JSONRPC_IMPORTER)
@Provides(pelix.remote.RemoteServiceImportEndpointListener)
@Property(
    "_kinds",
    pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
    (JSONRPC_CONFIGURATION,),
)
class JsonRpcServiceImporter(commons.AbstractRpcServiceImporter):
    """
    JSON-RPC Remote Services importer
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
        access_url = endpoint.properties.get(PROP_JSONRPC_URL)
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
        assert self._context is not None
        headers = security.get_auth_headers(self._context, "remote.jsonrpc", access_url, endpoint.properties)
        return _ServiceCallProxy(endpoint.name, access_url, commons.get_client_limits(self._context), headers)

    def clear_service_proxy(self, endpoint: ImportEndpoint) -> None:
        """
        Destroys the proxy made for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        """
        # Nothing to do
        return
