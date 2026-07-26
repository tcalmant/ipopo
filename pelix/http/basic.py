#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix basic HTTP service bundle.

Provides an implementation of the Pelix HTTP service based on the standard
Python library.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.2.2

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
import socket
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import TCPServer, ThreadingMixIn
from typing import IO, TYPE_CHECKING, Any, cast

import pelix.ipv6utils
from pelix import http, utilities
from pelix.http._base import (
    DEFAULT_BIND_ADDRESS,
    DEFAULT_REQUEST_QUEUE_SIZE,
    HTTP_SERVICE_EXTRA,
    LOCALHOST_ADDRESS,
    AbstractHttpService,
    compute_sub_path,
)
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Invalidate,
    Provides,
    Requires,
    UnbindField,
    UpdateField,
    Validate,
)
from pelix.misc import ssl_wrap

if TYPE_CHECKING:
    from pelix.framework import BundleContext

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Kept for backward compatibility: those constants are now defined in _base
__all__ = ["DEFAULT_BIND_ADDRESS", "HTTP_SERVICE_EXTRA", "LOCALHOST_ADDRESS", "HttpServiceImpl"]

# ------------------------------------------------------------------------------


class _HTTPServletRequest(http.AbstractHTTPServletRequest):
    """
    HTTP Servlet request helper
    """

    def __init__(self, request_handler: BaseHTTPRequestHandler, full_path: str, prefix: str) -> None:
        """
        Sets up the request helper

        :param request_handler: The basic request handler
        :param full_path: The normalized request path, including the prefix
        :param prefix: The path to the servlet root
        """
        self._handler = request_handler
        self._prefix = prefix

        # Compute the sub path
        self._sub_path = compute_sub_path(full_path, prefix)

    def get_command(self) -> str:
        """
        Returns the HTTP verb (GET, POST, ...) used for the request
        """
        return self._handler.command

    def get_client_address(self) -> tuple[str, int]:
        """
        Retrieves the address of the client

        :return: A (host, port) tuple
        """
        return self._handler.client_address

    def get_header(self, name: str, default: Any | None = None) -> Any:
        """
        Retrieves the value of a header
        """
        return self._handler.headers.get(name, default)

    def get_headers(self) -> dict[str, Any]:
        """
        Retrieves all headers
        """
        return cast(dict[str, Any], self._handler.headers)

    def get_path(self) -> str:
        """
        Retrieves the request full path
        """
        return self._handler.path

    def get_prefix_path(self) -> str:
        """
        Returns the path to the servlet root

        :return: A request path (string)
        """
        return self._prefix

    def get_sub_path(self) -> str:
        """
        Returns the servlet-relative path, i.e. after the prefix

        :return: A request path (string)
        """
        return self._sub_path

    def get_rfile(self) -> IO[bytes]:
        """
        Retrieves the input as a file stream
        """
        return self._handler.rfile


class _HTTPServletResponse(http.AbstractHTTPServletResponse):
    """
    HTTP Servlet response helper
    """

    def __init__(self, request_handler: BaseHTTPRequestHandler) -> None:
        """
        Sets up the response helper

        :param request_handler: The basic request handler
        """
        self._handler = request_handler
        self._headers: dict[str, Any] = {}

    def set_response(self, code: int, message: str | None = None) -> None:
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        self._handler.send_response(code, message)

    def set_header(self, name: str, value: Any) -> None:
        """
        Sets the value of a header.
        This method should not be called after ``end_headers()``.

        :param name: Header name
        :param value: Header value
        """
        self._headers[name.lower()] = value

    def is_header_set(self, name: str) -> bool:
        """
        Checks if the given header has already been set

        :param name: Header name
        :return: True if it has already been set
        """
        return name.lower() in self._headers

    def end_headers(self) -> None:
        """
        Ends the headers part
        """
        # Send them all at once
        for name, value in self._headers.items():
            self._handler.send_header(name, value)

        self._handler.end_headers()

    def get_wfile(self) -> IO[bytes]:
        """
        Retrieves the output as a file stream.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :return: The output file-like object
        """
        return self._handler.wfile

    def write(self, data: bytes) -> None:
        """
        Writes the given data.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :param data: Data to be written
        """
        self._handler.wfile.write(data)


# ------------------------------------------------------------------------------


class _RequestHandler(BaseHTTPRequestHandler):
    """
    Basic HTTP server request handler
    """

    # Override the default HTTP version
    default_request_version = "HTTP/1.0"

    def __init__(self, http_svc: AbstractHttpService, *args: Any, **kwargs: Any) -> None:
        """
        Sets up the request handler (called for each request)

        :param http_svc: The associated HTTP service
        """
        self._service = http_svc

        # This calls the do_* methods
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """
        Retrieves the do_* in the servlet corresponding to the request path.
        If the name is not a "do_*", returns the normal result of __getattr__.

        :param name: Name of the attribute
        :return: The found attribute
        :raise AttributeError: Attribute not found
        """
        if not name.startswith("do_"):
            # Not a request handling
            return object.__getattribute__(self, name)

        # Get the corresponding servlet
        routing = self._service.resolve_request(self.path)
        servlet = routing.servlet
        if servlet is not None and hasattr(servlet, name):
            # Prepare the helpers
            request = _HTTPServletRequest(self, routing.path, routing.prefix)
            response = _HTTPServletResponse(self)

            # Create a wrapper to pass the handler to the servlet
            def wrapper() -> None:
                """
                Wrapped servlet call
                """
                try:
                    # Handle the request
                    getattr(servlet, name)(request, response)
                except Exception:
                    # Send a 500 error page on error
                    self.send_exception(response)

            # Return it
            return wrapper

        # Return the super implementation if needed
        return self.send_no_servlet_response

    def log_error(self, format: str, *args: Any, **kwargs: Any) -> None:
        # pylint: disable=W0221
        """
        Log server error
        """
        self._service.log(logging.ERROR, format, *args, **kwargs)

    def log_request(self, code: str | int = "-", size: str | int = "-") -> None:
        """
        Logs a request to the server
        """
        self._service.log(logging.DEBUG, '"%s" %s', self.requestline, code)

    def send_no_servlet_response(self) -> None:
        """
        Default response sent when no servlet is found for the requested path
        """
        # Use the helper to send the error page
        response = _HTTPServletResponse(self)
        response.send_content(404, self._service.make_not_found_page(self.path))

    def send_exception(self, response: http.AbstractHTTPServletResponse) -> None:
        """
        Sends an exception page with a 500 error code.
        Must be called from inside the exception handling block.

        :param response: The response handler
        """
        # Get a formatted stack trace.
        # The error is logged by the service, which also decides what can be
        # sent to the client
        stack = traceback.format_exc()

        # Send the page
        response.send_content(500, self._service.make_exception_page(self.path, stack))


# ------------------------------------------------------------------------------


class _HttpServerFamily(ThreadingMixIn, HTTPServer):
    """
    A small modification to have a threaded HTTP Server with a custom address
    family

    Inspired from:
    http://www.arcfn.com/2011/02/ipv6-web-serving-with-arc-or-python.html
    """

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        request_queue_size: int = 5,
        logger: logging.Logger | None = None,
    ):
        """
        Proxy constructor

        :param server_address: The server address
        :param request_handler_class: The request handler class
        :param request_queue_size: The size of the request queue (clients waiting for treatment)
        :param logger: An optional logger, in case of ignored error
        """
        # Determine the address family
        addr_info = socket.getaddrinfo(server_address[0], server_address[1], 0, 0, socket.SOL_TCP)

        # Change the address family before the socket is created
        # Get the family of the first possibility
        self.address_family = addr_info[0][0]

        # Set the queue size
        self.request_queue_size = request_queue_size

        # Set up the server, socket, ... but do not bind immediately
        HTTPServer.__init__(self, server_address, request_handler_class, False)
        self.server_name = server_address[0]
        self.server_port = server_address[1]

        if self.address_family == socket.AF_INET6:
            # Explicitly ask to be accessible both by IPv4 and IPv6
            try:
                pelix.ipv6utils.set_double_stack(self.socket)
            except AttributeError:
                if logger is not None:
                    logger.exception("System misses IPv6 constant")
            except OSError:
                if logger is not None:
                    logger.exception("Error setting up IPv6 double stack")

        # Bind & accept
        self.server_bind()
        self.server_activate()

    def server_bind(self) -> None:
        """
        Override server_bind to store the server name, even in IronPython.

        See https://ironpython.codeplex.com/workitem/29477
        """
        TCPServer.server_bind(self)
        host, port = self.socket.getsockname()[:2]
        self.server_port = port
        try:
            self.server_name = socket.getfqdn(host)
        except ValueError:
            # Use the local host name in case of error, like CPython does
            self.server_name = socket.gethostname()

    def process_request(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: Any
    ) -> None:
        """
        Starts a new thread to process the request, adding the client address
        in its name.
        """
        thread = threading.Thread(
            name=f"HttpService-{self.server_port}-Client-{client_address}",
            target=self.process_request_thread,
            args=(request, client_address),
        )
        thread.daemon = self.daemon_threads
        thread.start()


# ------------------------------------------------------------------------------


@ComponentFactory(http.FACTORY_HTTP_BASIC)
@Provides(http.HTTP_SERVICE)
@Requires("_servlets_services", http.Servlet, True, True)
@Requires("_error_handler", http.ErrorHandler, optional=True)
class HttpServiceImpl(AbstractHttpService):
    """
    Basic HTTP service component
    """

    def __init__(self) -> None:
        super().__init__()

        # Property specific to this implementation
        self._request_queue_size = DEFAULT_REQUEST_QUEUE_SIZE

        # Field injected by iPOPO
        self._servlets_services: list[http.Servlet] = []

        # Server control
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _check_servlet_type(self, servlet_type: http.ServletType) -> None:
        """
        This implementation only supports synchronous servlets

        :param servlet_type: The type of servlet to register
        :raise ValueError: The kind of servlet is not supported
        """
        if servlet_type != http.ServletType.SYNC:
            raise ValueError("Asynchronous mode is not supported")

    def _register_servlet_service(
        self, service: http.Servlet, service_reference: ServiceReference[Any]
    ) -> None:
        """
        Registers a servlet according to its service properties

        :param service: A servlet service
        :param service_reference: The associated ServiceReference
        """
        # Servlet bound
        paths = service_reference.get_property(http.HTTP_SERVLET_PATH)
        if utilities.is_string(paths):
            # Register the servlet to a single path
            self.register_servlet(paths, service)
        elif isinstance(paths, (list, tuple)):
            # Register the servlet to multiple paths
            for path in paths:
                self.register_servlet(path, service)

    @BindField("_servlets_services")
    def _bind(self, _: str, service: http.Servlet, service_reference: ServiceReference[http.Servlet]) -> None:
        """
        Called by iPOPO when a service is bound
        """
        self._on_bind(service, service_reference)

    @UpdateField("_servlets_services")
    def _update(
        self,
        _: str,
        service: http.Servlet,
        service_reference: ServiceReference[http.Servlet],
        old_properties: dict[str, Any],
    ) -> None:
        """
        Called by iPOPO when the properties of a service have been updated
        """
        self._on_update(service, service_reference, old_properties, (http.HTTP_SERVLET_PATH,))

    @UnbindField("_servlets_services")
    def _unbind(
        self, _: str, service: http.Servlet, service_reference: ServiceReference[http.Servlet]
    ) -> None:
        """
        Called by iPOPO when a service is gone
        """
        self._on_unbind(service, service_reference)

    def get_access(self) -> tuple[str, int]:
        """
        Retrieves the (address, port) tuple to access the server
        """
        assert self._server is not None
        sock_info = self._server.socket.getsockname()

        # Only keep the address and the port information
        return sock_info[0], sock_info[1]

    @Validate
    def validate(self, _: "BundleContext") -> None:
        """
        Component validation
        """
        self._normalize_configuration()
        self._setup_logger()

        # Normalize the request queue size
        try:
            self._request_queue_size = int(self._request_queue_size)
        except (ValueError, TypeError):
            self._request_queue_size = DEFAULT_REQUEST_QUEUE_SIZE

        if self._request_queue_size <= 0:
            self._request_queue_size = DEFAULT_REQUEST_QUEUE_SIZE

        self.log(
            logging.INFO,
            "Starting HTTP%s server: [%s]:%d ...",
            "S" if self._uses_ssl else "",
            self._address,
            self._port,
        )

        parent = self

        class LocalRequestHandler(_RequestHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(parent, *args, **kwargs)

        # Create the server
        self._server = _HttpServerFamily(
            (self._address, self._port),
            LocalRequestHandler,
            self._request_queue_size,
            self._logger,
        )

        if self._uses_ssl:
            if not self._cert_file or not self._key_file:
                raise ValueError("No certificate given to setup HTTPS")

            # Activate HTTPS if required
            self._server.socket = ssl_wrap.wrap_socket(
                self._server.socket,
                self._cert_file,
                self._key_file,
                self._key_password,
            )

        # Property update (if port was 0)
        self._port = self._server.server_port

        # Run it in a separate thread
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name=f"HttpService-{self._port}-Server",
        )
        self._thread.daemon = True
        self._thread.start()

        # Register the servlets bound before the server was ready
        self._register_bound_servlets()

        self.log(
            logging.INFO,
            "HTTP%s server started: [%s]:%d",
            "S" if self._uses_ssl else "",
            self._address,
            self._port,
        )

    @Invalidate
    def invalidate(self, _: "BundleContext") -> None:
        """
        Component invalidation
        """
        # Refuse new registrations and notify the bound servlets
        self._unregister_all_servlets()

        self.log(
            logging.INFO,
            "Shutting down HTTP server: [%s]:%d ...",
            self._address,
            self._port,
        )

        # Shutdown server (if active)
        if self._server is not None:
            self._server.shutdown()

            # Wait for the thread to stop...
            self.log(
                logging.INFO,
                "Waiting HTTP server ([%s]:%d) thread to stop...",
                self._address,
                self._port,
            )

            if self._thread is not None:
                self._thread.join(2)

            # Close the server
            self._server.server_close()

        self.log(
            logging.INFO,
            "HTTP server down: [%s]:%d ...",
            self._address,
            self._port,
        )

        # Clean up
        self._servlets.clear()
        self._thread = None
        self._server = None
        # Rename the logger, to detect late use after invalidation
        self._logger = logging.getLogger(f"{self._logger.name}--invalidated")
