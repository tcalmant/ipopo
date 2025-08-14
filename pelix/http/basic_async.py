#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix basic asynchronous HTTP service bundle.

Provides an implementation of the Pelix HTTP service based on aiohttp.

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

import asyncio
import concurrent.futures
import io
import logging
import re
import socket
import ssl
import threading
import traceback
from typing import IO, TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

import aiohttp.web

import pelix.http as http
import pelix.ipopo.constants as constants
import pelix.remote
import pelix.utilities as utilities
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    HiddenProperty,
    Invalidate,
    Property,
    Provides,
    Requires,
    UnbindField,
    UpdateField,
    Validate,
)

if TYPE_CHECKING:
    from pelix.framework import BundleContext


# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

HTTP_SERVICE_EXTRA = "http.extra"
""" HTTP service extra properties (dictionary) """

DEFAULT_BIND_ADDRESS = "0.0.0.0"
""" By default, bind to all IPv4 interfaces """

LOCALHOST_ADDRESS = "127.0.0.1"
"""
Local address, if None is given as binding address, instead of the default one
"""


class _SyncHTTPServletRequest(http.AbstractHTTPServletRequest):
    """
    HTTP Servlet request helper
    """

    def __init__(self, request: aiohttp.web.Request, full_path: str, prefix: str, content: bytes) -> None:
        """
        Sets up the request helper

        :param request: The asyncio Request object
        :param full_path: The full request path, including the prefix
        :param prefix: The path to the servlet root
        :parma content: The request content
        """
        self._request = request
        self._prefix = prefix
        self._content = content

        # Compute the sub path
        self._sub_path = full_path[len(prefix) :]
        if not self._sub_path.startswith("/"):
            self._sub_path = f"/{self._sub_path}"

        self._sub_path = re.sub("/+", "/", self._sub_path)

    def get_command(self) -> str:
        """
        Returns the HTTP verb (GET, POST, ...) used for the request
        """
        return self._request.method.upper()

    def get_client_address(self) -> Tuple[str, int]:
        """
        Retrieves the address of the client

        :return: A (host, port) tuple
        """
        if self._request.transport is None:
            # No transport, no address
            raise IOError("No transport available for the request")

        return self._request.transport.get_extra_info("peername")[:2]

    def get_header(self, name: str, default: Optional[Any] = None) -> Any:
        """
        Retrieves the value of a header
        """
        return self._request.headers.get(name, default)

    def get_headers(self) -> Dict[str, Any]:
        """
        Retrieves all headers
        """
        return cast(Dict[str, Any], self._request.headers)

    def get_path(self) -> str:
        """
        Retrieves the request full path
        """
        return self._request.path

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
        return io.BytesIO(self._content)


class _WriteWrapper(IO[bytes]):
    def __init__(self):
        self._buffer = io.BytesIO()
        self._closed = False

    def get(self) -> bytes:
        """
        Retrieves the written data as bytes.
        This method should be called after the response has been sent.

        :return: The written data
        """
        return self._buffer.getvalue()

    def read(self, size: int = -1) -> bytes:
        raise IOError("This stream is not readable")

    def write(self, b: bytes) -> int:
        return self._buffer.write(b)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        raise IOError("This stream is not seekable")

    def tell(self) -> int:
        raise IOError("This stream is not seekable")

    def close(self) -> None:
        self._closed = True

    def flush(self) -> None:
        pass

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def closed(self) -> bool:
        return self._closed


class _SyncHTTPServletResponse(http.AbstractHTTPServletResponse):
    """
    HTTP Servlet response helper
    """

    def __init__(self, request: aiohttp.web.Request, loop: asyncio.AbstractEventLoop) -> None:
        """
        Sets up the response helper

        :param request: The asyncio Request object
        :param loop: The asyncio event loop
        """
        self._request = request
        self._loop = loop
        self._headers: Dict[str, str] = {}
        self._headers_set: bool = False
        self._code: int = 200
        self._message: str | None = None
        self._writer = _WriteWrapper()

    def to_aiohttp_response(self) -> aiohttp.web.StreamResponse:
        """
        Converts the response to an aiohttp StreamResponse object.
        This method should be called after all headers have been set.

        :return: The aiohttp StreamResponse object
        """
        return aiohttp.web.Response(
            body=self._writer.get(), status=self._code, reason=self._message, headers=self._headers
        )

    def set_response(self, code: int, message: Optional[str] = None) -> None:
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        if self._headers_set:
            raise IOError("Headers have already been set, cannot change the response code")

        self._code = code
        self._message = message

    def set_header(self, name: str, value: Any) -> None:
        """
        Sets the value of a header.
        This method should not be called after ``end_headers()``.

        :param name: Header name
        :param value: Header value
        """
        if self._headers_set:
            raise IOError("Headers have already been set, cannot change them")

        if value is None:
            self._headers.pop(name.lower(), None)
        else:
            self._headers[name.lower()] = str(value)

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
        self._headers_set = True

    def get_wfile(self) -> IO[bytes]:
        """
        Retrieves the output as a file stream.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :return: The output file-like object
        """
        if not self._headers_set:
            self.end_headers()

        return self._writer

    def write(self, data: bytes) -> None:
        """
        Writes the given data.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :param data: Data to be written
        """
        writer = self.get_wfile()
        writer.write(data)
        writer.close()


# ------------------------------------------------------------------------------


@ComponentFactory(http.FACTORY_HTTP_ASYNC)
@Provides(http.HTTP_SERVICE)
@Requires("_servlets_services", http.Servlet, True, True)
@Requires("_error_handler", http.ErrorHandler, optional=True)
@Property("_address", http.HTTP_SERVICE_ADDRESS, DEFAULT_BIND_ADDRESS)
@Property("_port", http.HTTP_SERVICE_PORT, 8080)
@Property("_uses_ssl", http.HTTP_USES_SSL, False)
@Property("_cert_file", http.HTTPS_CERT_FILE, None)
@Property("_key_file", http.HTTPS_KEY_FILE, None)
@HiddenProperty("_key_password", http.HTTPS_KEY_PASSWORD, None)
@Property("_extra", HTTP_SERVICE_EXTRA, None)
@Property("_instance_name", constants.IPOPO_INSTANCE_NAME)
@Property("_logger_name", "pelix.http.logger.name", "")
@Property("_logger_level", "pelix.http.logger.level", None)
class AsyncHttpServiceImpl(http.HTTPService):
    """
    Asynchronous HTTP service component
    """

    def __init__(self) -> None:
        # Properties
        self._address = "0.0.0.0"
        self._port = 8080
        self._uses_ssl = False
        self._extra: Optional[Dict[str, Any]] = None
        self._instance_name: Optional[str] = None
        self._logger_name: Optional[str] = None
        self._logger_level: str | int | None = None

        # SSL Parameters
        self._cert_file: Optional[str] = None
        self._key_file: Optional[str] = None
        self._key_password: Optional[str] = None

        # Validation flag
        self._validated = False

        # The logger
        self._logger: logging.Logger = logging.getLogger(f"{__name__}#init")

        # Servlets registry lock
        self._lock = threading.RLock()

        # Path -> (servlet, parameters)
        self._servlets: Dict[str, Tuple[http.Servlet, Dict[str, Any]]] = {}

        # Fields injected by iPOPO
        self._servlets_services: List[http.Servlet] = []
        self._error_handler: Optional[http.ErrorHandler] = None

        # Servlet -> ServiceReference
        self._servlets_refs: Dict[http.Servlet, ServiceReference[http.Servlet]] = {}
        self._binding_lock = threading.RLock()

        # Server control
        self._bound_address: tuple[str, int] | None = None
        self._app: aiohttp.web.Application | None = None
        self._thread: threading.Thread | None = None
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self._stop_done_event: threading.Event = threading.Event()

    def __str__(self) -> str:
        """
        String representation of the instance
        """
        return f"BasicHttpService({self._address}, {self._port})"

    @Validate
    def validate(self, context: "BundleContext") -> None:
        """
        Component validated
        """
        # Check if we'll use an SSL connection
        self._uses_ssl = self._cert_file is not None

        if not self._address:
            # No address given, use the localhost address
            self._address = LOCALHOST_ADDRESS

        if self._port is None:
            # Random port
            self._port = 0
        else:
            # Ensure we have an integer
            self._port = int(self._port)
            if self._port < 0:
                # Random port
                self._port = 0

        # Normalize the extra properties
        if not isinstance(self._extra, dict):
            self._extra = {}

        # Set up the logger
        if not self._logger_name:
            # Empty name, use the instance name
            self._logger_name = self._instance_name

        self._logger = logging.getLogger(self._logger_name)

        level: int | None = None
        if self._logger_level is None:
            self._logger.level = logging.INFO
        elif isinstance(self._logger_level, int):
            level = self._logger_level
        else:
            level = logging.getLevelNamesMapping().get(self._logger_level)
            if level is None:
                try:
                    level = int(self._logger_level)
                except ValueError:
                    # Invalid level
                    level = None

        self._logger.level = level if level is not None else logging.INFO

        self.log(
            logging.INFO,
            "Starting HTTP%s server: [%s]:%d ...",
            "S" if self._uses_ssl else "",
            self._address,
            self._port,
        )

        # Create the server
        app = aiohttp.web.Application(logger=self._logger)
        app.add_routes([aiohttp.web.route("*", "/{tail:.*}", self.__global_handler)])
        self._app = app

        # Start the server in a separate thread
        self._stop_event.clear()
        self._stop_done_event.clear()
        self._thread = threading.Thread(target=self._run_server_thread, name="Pelix Async HTTP Server Thread")
        self._thread.daemon = True
        self._thread.start()

        with self._binding_lock:
            # Set the validation flag up, once the server is ready
            self._validated = True

            # Register bound servlets
            for service, svc_ref in self._servlets_refs.items():
                self.__register_servlet_service(service, svc_ref)

    @Invalidate
    def invalidate(self, context: "BundleContext") -> None:
        """
        Component invalidated
        """
        # Clear the validation flag
        self._validated = False

        self.log(
            logging.INFO,
            "Stopping HTTP%s server: [%s]:%d ...",
            "S" if self._uses_ssl else "",
            self._address,
            self._port,
        )

        # Set the stop event
        if self._loop is not None:
            # Call for a stop
            async def async_stop_caller():
                self._stop_event.set()

            asyncio.run_coroutine_threadsafe(async_stop_caller(), self._loop).result()

        # Wait for the stop done event to be set
        self._logger.debug("Waiting for the stop done event to be set...")
        if not self._stop_done_event.wait(timeout=5):
            self.log(
                logging.WARNING,
                "The stop done event was not set in time, the server may not have stopped properly",
            )

        # Wait for the server thread to stop
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.5)
            if self._thread.is_alive():
                self.log(logging.WARNING, "HTTP server thread did not stop in time")

        self._thread = None

        # Close the event loop
        if self._loop is not None and self._loop.is_closed():
            self._loop.close()

        # Clear references
        self._loop = None
        self._app = None

    def _run_server_thread(self) -> None:
        """
        Runs the HTTP server in a separate thread.
        """
        try:
            # Set the event loop for this thread
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # Setup the server
            self._loop.run_until_complete(self._run_server())
        except Exception:
            self._logger.exception("Error running async HTTP server")
        finally:
            if self._loop is not None:
                self._loop.stop()
            self._stop_done_event.set()

    async def _run_server(self) -> None:
        assert self._app is not None, "Application must be initialized before running the server"

        # Create the server
        runner = aiohttp.web.AppRunner(self._app)
        await runner.setup()

        # Prepare SSL context if needed
        ssl_context: ssl.SSLContext | None = None
        if self._uses_ssl:
            assert self._cert_file is not None, "Certificate file must be set for HTTPS"

            # Create the SSL context
            ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            ssl_context.load_cert_chain(
                certfile=self._cert_file, keyfile=self._key_file, password=self._key_password
            )

        # Create the site
        site = aiohttp.web.TCPSite(runner, self._address, self._port, ssl_context=ssl_context)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            self._executor = executor

            # Start the site
            await site.start()

            # Get bound address and port
            sock = cast(asyncio.Server, site._server).sockets[0]
            host, port = sock.getsockname()[:2]
            self._bound_address = (host, port)
            self._port = port

            self.log(
                logging.INFO,
                "HTTP%s server bound to: [%s]:%d ...",
                "S" if self._uses_ssl else "",
                self._address,
                self._port,
            )

            # Keep the thread alive until the server is stopped
            await self._stop_event.wait()

            # Clean up the server
            await site.stop()
            await runner.shutdown()
            await runner.cleanup()
            await self._app.shutdown()
            await self._app.cleanup()
        self._logger.debug("HTTP server stopped")

    async def __global_handler(self, request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        """
        Global handler for the Pelix async HTTP service.

        :param request: The incoming request
        :return: The response to send
        """
        assert self._loop is not None, "EventLoop must be initialized before handling requests"

        if self._executor is None:
            # No executor available, cannot handle the request
            return aiohttp.web.Response(status=503, text="Service unavailable")

        # Remove the double-slashes in the request path
        path = re.sub("/+", "/", request.path)

        # Get the corresponding servlet
        found_servlet = self.get_servlet(path)
        if found_servlet is not None:
            method_name = f"do_{request.method.upper()}"
            servlet, _, prefix = found_servlet
            if hasattr(servlet, f"do_{request.method.upper()}"):
                # Read the request content
                # FIXME: find a better way to handle the content, wrapping the request
                #        in a file-like object
                content = await request.read()

                # Prepare the helpers
                servlet_request = _SyncHTTPServletRequest(request, path, prefix, content)
                servlet_response = _SyncHTTPServletResponse(request, self._loop)

                try:
                    # Handle the request
                    handler_method = getattr(servlet, method_name)
                    await self._loop.run_in_executor(
                        self._executor, handler_method, servlet_request, servlet_response
                    )
                    return servlet_response.to_aiohttp_response()
                except:
                    # Send a 500 error page on error
                    return self.send_exception(path)

        # Return the super implementation if needed
        return aiohttp.web.Response(status=404, body=self.make_not_found_page(path), content_type="text/html")

    def send_exception(self, path: str) -> aiohttp.web.Response:
        """
        Sends an exception page with a 500 error code.
        Must be called from inside the exception handling block.

        :param response: The response handler
        """
        # Get a formatted stack trace
        stack = traceback.format_exc()

        # Log the error
        self._logger.error("Error handling request upon: %s\n%s\n", path, stack)

        # Send the page
        return aiohttp.web.Response(status=500, text=self.make_exception_page(path, stack))

    def __safe_callback(self, instance: http.Servlet, method: str, *args: Any, **kwargs: Any) -> Any:
        """
        Safely calls the given method in the given instance.
        Returns True on method absence.
        Returns False on error.
        Returns the method result if found.

        :param instance: The instance to call
        :param method: The method to call in the instance
        :return: The method result or True on method absence or False on error
        """
        # Call back the method
        if instance is None:
            # Consider invalidity as a failure
            return False

        try:
            callback = getattr(instance, method)
        except AttributeError:
            # Consider absence as a success
            return True

        try:
            result = callback(*args, **kwargs)
            if result is None:
                # Special case: consider None as success
                return True

            return result

        except Exception as ex:
            self.log_exception("Error calling back an instance: %s", ex)

        return False

    def __register_servlet_service(
        self, service: http.Servlet, service_reference: ServiceReference[http.Servlet]
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
        # Ignore imported services
        if self.__is_imported(service_reference):
            self._logger.debug("Ignoring imported service as it is imported: %s", service_reference)
            return

        with self._binding_lock:
            self._servlets_refs[service] = service_reference

            if self._validated:
                # We've been validated, register the service
                self.__register_servlet_service(service, service_reference)

    @UpdateField("_servlets_services")
    def _update(
        self,
        _: str,
        service: http.Servlet,
        service_reference: ServiceReference[http.Servlet],
        old_properties: Dict[str, Any],
    ) -> None:
        """
        Called by iPOPO when the properties of a service have been updated
        """
        # Ignore imported services
        if self.__is_imported(service_reference):
            return
        # Check if the property concerns the registration
        old_path = old_properties.get(http.HTTP_SERVLET_PATH)
        new_path = service_reference.get_property(http.HTTP_SERVLET_PATH)
        if old_path == new_path:
            # Nothing to do
            return

        with self._binding_lock:
            # Unregister the previous paths
            self.unregister(None, service)

            if self._validated:
                # Register the service with its new properties
                self.__register_servlet_service(service, service_reference)

    @UnbindField("_servlets_services")
    def _unbind(
        self, _: str, service: http.Servlet, service_reference: ServiceReference[http.Servlet]
    ) -> None:
        """
        Called by iPOPO when a service is gone
        """
        # Ignore imported services
        if self.__is_imported(service_reference):
            return

        with self._binding_lock:
            # Servlet gone: unregister all paths associated to this servlet
            self.unregister(None, service)

            # Remove the service reference
            try:
                del self._servlets_refs[service]
            except KeyError:
                self.log(logging.DEBUG, "Tried to remove an unknown servlet: %s", service)

    def get_access(self) -> Tuple[str, int]:
        """
        Retrieves the (address, port) tuple to access the server
        """
        assert self._bound_address is not None, "Server must be started before accessing its address"
        return self._bound_address

    @staticmethod
    def get_hostname() -> str:
        """
        Retrieves the server host name

        :return: The server host name
        """
        return socket.gethostname()

    def is_https(self) -> bool:
        """
        Returns True if this is an HTTPS server

        :return: True if this server uses SSL
        """
        return self._uses_ssl

    def get_registered_paths(self) -> List[str]:
        """
        Returns the paths registered by servlets

        :return: The paths registered by servlets (sorted list)
        """
        return sorted(self._servlets)

    def get_servlet(self, path: Optional[str]) -> Optional[Tuple[http.Servlet, Dict[str, Any], str]]:
        """
        Retrieves the servlet matching the given path and its parameters.
        Returns None if no servlet matches the given path.

        :param path: A request URI
        :return: A tuple (servlet, parameters, prefix) or None
        """
        if not path or path[0] != "/":
            # No path, nothing to return
            return None

        # Use lower case for comparison
        path = path.lower()

        if path[-1] != "/":
            # Add a trailing slash
            path += "/"

        with self._lock:
            longest_match = ""
            longest_match_len = 0
            for servlet_path in self._servlets:
                tested_path = servlet_path
                if tested_path[-1] != "/":
                    # Add a trailing slash
                    tested_path += "/"

                if path.startswith(tested_path) and len(servlet_path) > longest_match_len:
                    # Found a corresponding servlet
                    # which is deeper than the previous one
                    longest_match = servlet_path
                    longest_match_len = len(servlet_path)

            # Return the found servlet
            if not longest_match:
                # No match found
                return None

            # Retrieve the stored information
            servlet, params = self._servlets[longest_match]
            return servlet, params, longest_match

    def make_not_found_page(self, path: str) -> str:
        """
        Prepares a "page not found" page for a 404 error

        :param path: Request path
        :return: A HTML page
        """
        page = None
        if self._error_handler is not None:
            page = self._error_handler.make_not_found_page(path)

        if not page:
            page = f"""<html>
<head>
<title>404 - Page not found</title>
</head>
<body>
<h1>Page not found</h1>
<p>No servlet is associated to this path:</p>
<pre>{path}</pre>
<h2>Registered paths:</h2>
{http.make_html_list(self.get_registered_paths())}
</body>
</html>"""
        return page

    def make_exception_page(self, path: str, stack: str) -> str:
        """
        Prepares a page printing an exception stack trace in a 500 error

        :param path: Request path
        :param stack: Exception stack trace
        :return: A HTML page
        """
        page = None
        if self._error_handler is not None:
            page = self._error_handler.make_exception_page(path, stack)

        if not page:
            page = f"""<html>
<head>
<title>500 - Internal Server Error</title>
</head>
<body>
<h1>Internal Server Error</h1>
<p>Error handling request upon: {path}</p>
<pre>
{stack}
</pre>
</body>
</html>"""
        return page

    def register_servlet(
        self, path: str, servlet: http.Servlet, parameters: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Registers a servlet

        :param path: Path handled by this servlet
        :param servlet: The servlet instance
        :param parameters: The parameters associated to this path
        :return: True if the servlet has been registered, False if it refused the binding.
        :raise ValueError: Invalid path or handler
        """
        if servlet is None:
            raise ValueError("Invalid servlet instance")

        if not path or path[0] != "/":
            raise ValueError("Invalid path given to register the servlet: {0}".format(path))

        # Use lower-case paths
        path = path.lower()

        # Prepare the parameters
        if parameters is None:
            parameters = {}

        with self._lock:
            if path in self._servlets:
                # Already registered path
                if self._servlets[path][0] is servlet:
                    # Double-registration: Nothing to do
                    return True
                else:
                    # Path is already taken by another servlet
                    already_taken = True
            else:
                # Path is available
                already_taken = False

            # Add server information in parameters
            parameters[http.PARAM_ADDRESS] = self._address
            parameters[http.PARAM_PORT] = self._port
            parameters[http.PARAM_HTTPS] = self._uses_ssl
            parameters[http.PARAM_NAME] = self._instance_name
            parameters[http.PARAM_EXTRA] = self._extra.copy() if self._extra else None

            # The servlet might refuse to be bound to this server
            if not self.__safe_callback(servlet, "accept_binding", path, parameters):
                # Server refused: stop right there
                # => No need to raise the "already taken path" exception
                return False

            if already_taken:
                # The path is already taken by another servlet
                raise ValueError("A servlet is already registered on {0}".format(path))

            # Tell the servlet it can be bound to the path
            if self.__safe_callback(servlet, "bound_to", path, parameters):
                # Store the servlet
                self._servlets[path] = (servlet, parameters)
                return True

            # The servlet refused the binding
            return False

    def unregister(self, path: Optional[str], servlet: Optional[http.Servlet] = None) -> bool:
        """
        Unregisters the servlet for the given path

        :param path: The path to a servlet
        :param servlet: If given, unregisters all the paths handled by this servlet
        :return: True if at least one path as been unregistered, else False
        """
        if servlet is not None:
            with self._lock:
                # Unregister all paths for this servlet
                paths = [
                    servlet_path
                    for (servlet_path, servlet_info) in self._servlets.items()
                    if servlet_info[0] == servlet
                ]

            result = False
            for servlet_path in paths:
                result |= self.unregister(servlet_path)

            return result
        else:
            if not path:
                # Invalid path
                return False

            # Always use lower case to compare paths
            path = path.lower()

            with self._lock:
                # Notify the servlet
                servlet_info = self._servlets.get(path)
                if servlet_info is None:
                    # Unknown path
                    return False

                self.__safe_callback(servlet_info[0], "unbound_from", path, servlet_info[1])

                # Remove the servlet
                try:
                    del self._servlets[path]
                except KeyError:
                    self.log(logging.DEBUG, "Tried to remove an unknown servlet path: %s", path)
                return True

    def log(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        """
        Logs the given message

        :param level: Log entry level
        :param message: Log message (Python logging format)
        """
        if self._logger is not None:
            # Log the message
            self._logger.log(level, message, *args, **kwargs)

    def log_exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """
        Logs an exception

        :param message: Log message (Python logging format)
        """
        if self._logger is not None:
            # Log the exception
            self._logger.exception(message, *args, **kwargs)

    @staticmethod
    def __is_imported(service_reference: ServiceReference[Any]) -> bool:
        """
        Tests if the given service has been imported by Remote Services

        :param service_reference: The reference of the service to check
        :return: True if the service is flagged as imported
        """
        return cast(bool, service_reference.get_property(pelix.remote.PROP_IMPORTED))
