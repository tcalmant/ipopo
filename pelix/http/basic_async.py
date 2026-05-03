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
import html
import io
import logging
import re
import socket
import ssl
import sys
import threading
import traceback
from typing import IO, TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

import aiohttp.client_exceptions
import aiohttp.web

import pelix.constants as fw_constants
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

        :param request: The aiohttp Request object
        :param full_path: The full request path, including the prefix
        :param prefix: The path to the servlet root
        :param content: The request content
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

        peer_name = self._request.transport.get_extra_info("peername")
        if not peer_name:
            raise IOError("No peer name available for the request")
        return peer_name[:2]

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

    @property
    def closed(self) -> bool:
        return self._closed


class _SyncHTTPServletResponse(http.AbstractHTTPServletResponse):
    """
    HTTP Servlet response helper
    """

    def __init__(self, request: aiohttp.web.Request, loop: asyncio.AbstractEventLoop) -> None:
        """
        Sets up the response helper

        :param request: The aiohttp Request object
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


class _AsyncHTTPServletRequest(http.AbstractAsyncHTTPServletRequest):
    """
    HTTP Servlet request helper
    """

    def __init__(self, request: aiohttp.web.Request, full_path: str, prefix: str) -> None:
        """
        Sets up the request helper

        :param request: The aiohttp Request object
        :param full_path: The full request path, including the prefix
        :param prefix: The path to the servlet root
        """
        self._request = request
        self._prefix = prefix

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

        peer_name = self._request.transport.get_extra_info("peername")
        if not peer_name:
            raise IOError("No peer name available for the request")
        return peer_name[:2]

    async def get_header(self, name: str, default: Optional[Any] = None) -> Any:
        """
        Retrieves the value of a header
        """
        return self._request.headers.get(name, default)

    async def get_headers(self) -> Dict[str, Any]:
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

    def get_rfile(self) -> asyncio.StreamReader:
        """
        Retrieves the input as a file stream
        """
        # aiohttp StreamReader is compatible with the asyncio one
        return cast(asyncio.StreamReader, self._request.content)


class _AioHttpWriter(http.AbstractAsyncWriter):
    """
    Wrapper for aiohttp StreamResponse
    """

    def __init__(self, response: aiohttp.web.StreamResponse) -> None:
        self._response = response

    async def write(self, raw: bytes) -> int:
        await self._response.write(raw)
        return len(raw)

    async def flush(self) -> None:
        await self._response.drain()


class _AsyncHTTPServletResponse(http.AbstractAsyncHTTPServletResponse):
    """
    HTTP Servlet response helper
    """

    def __init__(self, request: aiohttp.web.Request) -> None:
        """
        Sets up the response helper

        :param request: The aiohttp Request object
        """
        self._request = request
        self._headers_set: bool = False
        self._sse_set: bool = False
        self._response = aiohttp.web.StreamResponse()

    def to_aiohttp_response(self) -> aiohttp.web.StreamResponse:
        """
        Converts the response to an aiohttp StreamResponse object.
        This method should be called after all headers have been set.

        :return: The aiohttp StreamResponse object
        """
        return self._response

    def set_response(self, code: int, message: Optional[str] = None) -> None:
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        if self._headers_set:
            raise IOError("Headers have already been set, cannot change the response code")

        self._response.set_status(code, message)

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
            self._response.headers.popall(name.lower(), None)
        else:
            self._response.headers.add(name.lower(), str(value))

    def is_header_set(self, name: str) -> bool:
        """
        Checks if the given header has already been set

        :param name: Header name
        :return: True if it has already been set
        """
        return self._response.headers.get(name.lower(), None) is not None

    def setup_sse(self, strict: bool = True) -> None:
        """
        Sets up the response for Server-Sent Events (SSE)

        :param strict: If True, raises an error if the request is not for SSE
        """
        if self._sse_set:
            # Already set up for SSE
            return

        if strict and not any(
            "text/event-stream" in accepted for accepted in self._request.headers.getall("accept", "")
        ):
            raise ValueError("Cannot set up SSE for a non-SSE request")

        if self._headers_set:
            raise IOError("Headers have already been set, cannot change them")

        self._response.headers["Content-Type"] = "text/event-stream"
        self._response.headers["Cache-Control"] = "no-cache"
        self._response.headers["Connection"] = "keep-alive"
        self._sse_set = True

    async def end_headers(self) -> None:
        """
        Ends the headers part
        """
        self._headers_set = True
        await self._response.prepare(self._request)

    def get_wfile(self) -> http.AbstractAsyncWriter:
        """
        Retrieves the output as a writer.
        ``end_headers()`` should have been called before.

        :return: A writer for the output stream
        """
        return _AioHttpWriter(self._response)

    async def write(self, data: bytes) -> None:
        """
        Writes the given data.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :param data: Data to be written
        """
        await self._response.write(data)

    async def send_sse(
        self, event: str | None = None, data: str | None = None, id: str | None = None
    ) -> None:
        """
        Sends a Server-Sent Event (SSE) message.

        :param event: Optional event type (e.g., "message", "update")
        :param data: The event data (without newline characters)
        :param id: Optional event ID (set to "" to reset the ID)
        """
        if not self._sse_set:
            raise IOError("SSE not set up, call setup_sse() first")

        # Prepare the SSE message
        parts: list[str] = []
        if id:
            parts.append(f"id: {id}")
        elif id is not None:
            # Reset ID
            parts.append("id")

        if event:
            parts.append(f"event: {event}")
        elif event is not None:
            parts.append("event")

        if data:
            # Split the data into lines and prefix each line with "data: "
            for line in data.splitlines() or [""]:
                parts.append(f"data: {line}")
        else:
            # Empty data line
            parts.append("data")

        # End of the event
        parts.append("")
        parts.append("")

        try:
            await self.write("\n".join(parts).encode("utf-8"))
        except aiohttp.client_exceptions.ClientConnectionResetError:
            raise IOError("Client connection reset during SSE send") from None


class WSSession(http.WebSocketSession):
    def __init__(
        self,
        ws_handler: http.WebSocketHandler,
        servlet_request: _AsyncHTTPServletRequest,
        ws_response: aiohttp.web.WebSocketResponse,
    ) -> None:
        """
        Initializes the WebSocket session

        :param ws_handler: The WebSocket handler
        :param servlet_request: The servlet request
        :param ws_response: The WebSocket response
        """
        self._handler = ws_handler
        self._request = servlet_request
        self._response = ws_response

    def get_client_address(self) -> Tuple[str, int]:
        """
        Returns the address of the client

        :return: A (host, port) tuple
        """
        return self._request.get_client_address()

    async def send_binary(self, message: bytes) -> None:
        """
        Sends a binary message to the client

        :param message: Binary message to send
        """
        if self._response.closed:
            raise IOError("WebSocket session is closed")

        await self._response.send_bytes(message)

    async def send_text(self, message: str) -> None:
        """
        Sends a message to the client

        :param message: Message to send
        """
        if self._response.closed:
            raise IOError("WebSocket session is closed")

        await self._response.send_str(message)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        """
        Closes the WebSocket session

        :param code: Close code (default is 1000, normal closure)
        :param reason: Optional reason for the closure
        """
        if not self._response.closed:
            await self._response.close(code=code, message=(reason or "").encode("utf-8"))


# ------------------------------------------------------------------------------


@ComponentFactory(http.FACTORY_HTTP_ASYNC)
@Provides(http.HTTP_SERVICE)
@Requires("_servlets_services", http.Servlet, True, True)
@Requires("_servlets_async_services", http.AsyncServlet, True, True)
@Requires("_websocket_handler_services", http.WebSocketHandler, True, True)
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

        # Path -> (servlet, parameters, type)
        self._servlets: Dict[
            str, Tuple[http.Servlet | http.AsyncServlet, Dict[str, Any], http.ServletType]
        ] = {}

        # Fields injected by iPOPO
        self._servlets_services: List[http.Servlet] = []
        self._servlets_async_services: List[http.AsyncServlet] = []
        self._websocket_handler_services: List[http.WebSocketHandler] = []
        self._error_handler: Optional[http.ErrorHandler] = None

        # Servlet -> ServiceReference
        self._servlets_refs: Dict[
            http.Servlet | http.AsyncServlet | http.WebSocketHandler,
            ServiceReference[http.Servlet | http.AsyncServlet | http.WebSocketHandler],
        ] = {}
        self._binding_lock = threading.RLock()

        # Server control
        self._bound_address: tuple[str, int] | None = None
        self._app: aiohttp.web.Application | None = None
        self._thread: threading.Thread | None = None
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._start_done_event: utilities.EventData[tuple[str, int]] = utilities.EventData()
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
            level = logging.INFO
        elif isinstance(self._logger_level, int):
            level = self._logger_level
        else:
            level = utilities.get_log_level(self._logger_level)
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
        self._start_done_event.clear()
        self._thread = threading.Thread(target=self._run_server_thread, name="Pelix Async HTTP Server Thread")
        self._thread.daemon = True
        self._thread.start()

        # Wait for the server to be ready
        if not self._start_done_event.wait(10):
            self._logger.error("HTTP server did not start in time")
            raise IOError("HTTP server did not start in time")

        if self._start_done_event.data is None:
            self._logger.error("HTTP server did not bind to an address")
            raise IOError("HTTP server did not bind to an address")

        host, port = self._start_done_event.data
        self._bound_address = (host, port)
        self._port = port

        with self._binding_lock:
            # Set the validation flag up, once the server is ready
            self._validated = True

            # Register bound servlets
            for service, svc_ref in self._servlets_refs.items():
                self.__register_servlet_service(service, svc_ref)

        self._logger.info(
            "HTTP%s server bound to: [%s]:%d ...",
            "S" if self._uses_ssl else "",
            self._address,
            self._port,
        )

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
        if self._loop is not None and not self._loop.is_closed():
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
            if sys.platform.startswith("win"):
                # aiodns requires a specific event loop on Windows
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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
        try:
            assert self._app is not None, "Application must be initialized before running the server"

            # Create the server
            runner = aiohttp.web.AppRunner(self._app)
            await runner.setup()

            # Prepare SSL context if needed
            ssl_context: ssl.SSLContext | None = None
            if self._uses_ssl:
                assert self._cert_file is not None, "Certificate file must be set for HTTPS"

                # Create the SSL context
                ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                ssl_context.load_cert_chain(
                    certfile=self._cert_file, keyfile=self._key_file, password=self._key_password
                )

            # Create the site
            site = aiohttp.web.TCPSite(runner, self._address, self._port, ssl_context=ssl_context)

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                self._executor = executor

                # Start the site
                await site.start()

                # Get bound address and port
                sock = cast(asyncio.Server, site._server).sockets[0]
                host, port = sock.getsockname()[:2]

                # We're ready
                self._start_done_event.set((host, port))

                # Keep the thread alive until the server is stopped
                await self._stop_event.wait()

                # Clean up the server
                await site.stop()
                await runner.shutdown()
                await runner.cleanup()
                await self._app.shutdown()
                await self._app.cleanup()
        except Exception as ex:
            # Anything went wrong, log the error
            self._logger.error("Error running the HTTP server: %s", ex)
            self._start_done_event.raise_exception(ex)

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
            servlet, _, prefix, servlet_type = found_servlet

            async_name = f"do_async_{request.method.upper()}"
            sync_name = f"do_{request.method.upper()}"

            try:
                match servlet_type:
                    case http.ServletType.ASYNC if hasattr(servlet, async_name):
                        # Prepare the helpers
                        servlet_request = _AsyncHTTPServletRequest(request, path, prefix)
                        servlet_response = _AsyncHTTPServletResponse(request)

                        # Handle the request
                        handler_method = getattr(servlet, async_name)
                        await handler_method(servlet_request, servlet_response)
                        return servlet_response.to_aiohttp_response()

                    case http.ServletType.SYNC if hasattr(servlet, sync_name):
                        # Read the request content
                        # FIXME: find a better way to handle the content, wrapping the request
                        #        in a file-like object
                        content = await request.read()

                        # Prepare the helpers
                        servlet_request = _SyncHTTPServletRequest(request, path, prefix, content)
                        servlet_response = _SyncHTTPServletResponse(request, self._loop)

                        # Handle the request in the executor
                        handler_method = getattr(servlet, sync_name)
                        await self._loop.run_in_executor(
                            self._executor, handler_method, servlet_request, servlet_response
                        )
                        return servlet_response.to_aiohttp_response()

                    case http.ServletType.WEBSOCKET if isinstance(servlet, http.WebSocketHandler):
                        # Prepare the WebSocket handler
                        ws_handler = cast(http.WebSocketHandler, servlet)
                        servlet_request = _AsyncHTTPServletRequest(request, path, prefix)

                        # Prepare the WebSocket response
                        ws_response = aiohttp.web.WebSocketResponse()

                        # Prepare a session
                        ws_session = WSSession(ws_handler, servlet_request, ws_response)

                        # Early check
                        if not await ws_handler.ws_accept(servlet_request):
                            # The handler does not accept the WebSocket connection
                            return aiohttp.web.Response(status=400, text="WebSocket connection refused")

                        # Prepare the WebSocket response
                        await ws_response.prepare(request)

                        try:
                            # Notify the WebSocket handler of the new connection
                            await ws_handler.ws_open(ws_session, servlet_request)

                            async for msg in ws_response:
                                # Handle incoming messages
                                match msg.type:
                                    case aiohttp.WSMsgType.ERROR:
                                        # Error message received
                                        self._logger.error("WebSocket error: %s", ws_response.exception())
                                        await ws_handler.ws_error(ws_session, msg.data)

                                    case aiohttp.WSMsgType.PING:
                                        # Ping message received
                                        await ws_response.pong(msg.data)

                                    case aiohttp.WSMsgType.BINARY:
                                        # Binary message received
                                        await ws_handler.ws_binary(ws_session, msg.data)

                                    case aiohttp.WSMsgType.TEXT:
                                        # Text message received
                                        await ws_handler.ws_message(ws_session, msg.data)
                            else:
                                code = ws_response.close_code or aiohttp.WSCloseCode.GOING_AWAY
                                await ws_handler.ws_close(ws_session, code, "Session closed")
                        except Exception as ex:
                            self._logger.exception("Error handling WebSocket connection: %s", ex)
                            await ws_handler.ws_error(ws_session, str(ex))
                        finally:
                            if not ws_response.closed:
                                await ws_response.close()

                        return ws_response
            except Exception:
                # Send a 500 error page on error
                self._logger.exception("Error handling %s request to %s", request.method, path)
                return self.send_exception(path)

        # Return the super implementation if needed
        return aiohttp.web.Response(status=404, text=self.make_not_found_page(path), content_type="text/html")

    def send_exception(self, path: str) -> aiohttp.web.Response:
        """
        Sends an exception page with a 500 error code.
        Must be called from inside the exception handling block.

        :param path: Erroneous request path
        :return: The aiohttp Response to send
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
        self,
        service: http.Servlet | http.AsyncServlet | http.WebSocketHandler,
        service_reference: ServiceReference[http.Servlet | http.AsyncServlet | http.WebSocketHandler],
    ) -> None:
        """
        Registers a servlet according to its service properties

        :param service: A servlet service
        :param service_reference: The associated ServiceReference
        """
        spec = cast(list[str], service_reference.get_property(fw_constants.OBJECTCLASS))
        if http.HTTP_SERVLET in spec:
            # Servlet bound
            sync_servlet = cast(http.Servlet, service)
            paths = service_reference.get_property(http.HTTP_SERVLET_PATH)
            if utilities.is_string(paths):
                # Register the servlet to a single path
                self.register_servlet(paths, sync_servlet, {}, http.ServletType.SYNC)
            elif isinstance(paths, (list, tuple)):
                # Register the servlet to multiple paths
                for path in paths:
                    self.register_servlet(path, sync_servlet, {}, http.ServletType.SYNC)

        # No else here: a service could implement both specifications
        if http.HTTP_SERVLET_ASYNC in spec:
            # Asynchronous servlet bound
            async_servlet = cast(http.AsyncServlet, service)
            paths = service_reference.get_property(http.HTTP_SERVLET_ASYNC_PATH)
            if utilities.is_string(paths):
                # Register the servlet to a single path
                self.register_servlet(paths, async_servlet, {}, http.ServletType.ASYNC)
            elif isinstance(paths, (list, tuple)):
                # Register the servlet to multiple paths
                for path in paths:
                    self.register_servlet(path, async_servlet, {}, http.ServletType.ASYNC)

        # No else here: a service could implement both specifications
        if http.HTTP_WEBSOCKET_HANDLER in spec:
            # WebSocket handler bound
            websocket_handler = cast(http.WebSocketHandler, service)
            paths = service_reference.get_property(http.HTTP_WEBSOCKET_PATH)
            if utilities.is_string(paths):
                # Register the WebSocket handler to a single path
                self.register_servlet(paths, websocket_handler, {}, http.ServletType.WEBSOCKET)
            elif isinstance(paths, (list, tuple)):
                # Register the WebSocket handler to multiple paths
                for path in paths:
                    self.register_servlet(path, websocket_handler, {}, http.ServletType.WEBSOCKET)

    @BindField("_servlets_services")
    @BindField("_servlets_async_services")
    @BindField("_websocket_handler_services")
    def _bind_servlet(
        self,
        _: str,
        service: http.Servlet | http.AsyncServlet | http.WebSocketHandler,
        service_reference: ServiceReference[http.Servlet | http.AsyncServlet | http.WebSocketHandler],
    ) -> None:
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
    @UpdateField("_servlets_async_services")
    @UpdateField("_websocket_handler_services")
    def _update_servlet(
        self,
        _: str,
        service: http.Servlet | http.AsyncServlet | http.WebSocketHandler,
        service_reference: ServiceReference[http.Servlet | http.AsyncServlet | http.WebSocketHandler],
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

        old_async_path = old_properties.get(http.HTTP_SERVLET_ASYNC_PATH)
        new_async_path = service_reference.get_property(http.HTTP_SERVLET_ASYNC_PATH)

        old_ws_path = old_properties.get(http.HTTP_WEBSOCKET_PATH)
        new_ws_path = service_reference.get_property(http.HTTP_WEBSOCKET_PATH)

        if old_path == new_path and old_async_path == new_async_path and old_ws_path == new_ws_path:
            # Nothing to do
            return

        with self._binding_lock:
            # Unregister the previous paths
            self.unregister(None, service)

            if self._validated:
                # Register the service with its new properties
                self.__register_servlet_service(service, service_reference)

    @UnbindField("_servlets_services")
    @UnbindField("_servlets_async_services")
    @UnbindField("_websocket_handler_services")
    def _unbind_servlet(
        self,
        _: str,
        service: http.Servlet | http.AsyncServlet | http.WebSocketHandler,
        service_reference: ServiceReference[http.Servlet | http.AsyncServlet | http.WebSocketHandler],
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
                # Service reference not found, nothing to do
                pass

    def get_access(self) -> Tuple[str, int]:
        """
        Retrieves the (address, port) tuple to access the server
        """
        assert self._bound_address is not None, "Server must be started before accessing its address"
        return self._bound_address

    def get_hostname(self) -> str:
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

    def get_servlet(
        self, path: Optional[str]
    ) -> Optional[Tuple[http.Servlet | http.AsyncServlet, Dict[str, Any], str, http.ServletType]]:
        """
        Retrieves the servlet matching the given path and its parameters.
        Returns None if no servlet matches the given path.

        :param path: A request URI
        :return: A tuple (servlet, parameters, prefix, type) or None
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
            servlet, params, servlet_type = self._servlets[longest_match]
            return servlet, params, longest_match, servlet_type

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
<code>{html.escape(path)}</code>
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
<p>Error handling request upon: <code>{html.escape(path)}</code></p>
<pre>
{html.escape(stack)}
</pre>
</body>
</html>"""
        return page

    def register_servlet(
        self,
        path: str,
        servlet: http.Servlet | http.AsyncServlet,
        parameters: Optional[Dict[str, Any]] = None,
        servlet_type: http.ServletType = http.ServletType.SYNC,
    ) -> bool:
        """
        Registers a servlet

        :param path: Path handled by this servlet
        :param servlet: The servlet instance
        :param parameters: The parameters associated to this path
        :param servlet_type: The type of servlet (sync, async, websocket, ...)
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
            parameters[http.PARAM_ASYNC] = servlet_type != http.ServletType.SYNC

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
                self._servlets[path] = (servlet, parameters, servlet_type)
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
