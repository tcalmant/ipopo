#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix basic asynchronous HTTP service bundle.

Provides an implementation of the Pelix HTTP service based on aiohttp.

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

import asyncio
import concurrent.futures
import contextvars
import functools
import io
import logging
import ssl
import sys
import threading
import traceback
from typing import IO, TYPE_CHECKING, Any, cast

import aiohttp.client_exceptions
import aiohttp.web

import pelix.constants as fw_constants
from pelix import http, utilities
from pelix.http._base import (
    DEFAULT_BIND_ADDRESS,
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
__all__ = [
    "DEFAULT_BIND_ADDRESS",
    "HTTP_SERVICE_EXTRA",
    "LOCALHOST_ADDRESS",
    "AsyncHttpServiceImpl",
    "WSSession",
]


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
        self._full_path = full_path
        self._prefix = prefix
        self._content = content

        # Compute the sub path
        self._sub_path = compute_sub_path(full_path, prefix)

    def get_command(self) -> str:
        """
        Returns the HTTP verb (GET, POST, ...) used for the request
        """
        return self._request.method.upper()

    def get_client_address(self) -> tuple[str, int]:
        """
        Retrieves the address of the client

        :return: A (host, port) tuple
        """
        if self._request.transport is None:
            # No transport, no address
            raise OSError("No transport available for the request")

        peer_name = self._request.transport.get_extra_info("peername")
        if not peer_name:
            raise OSError("No peer name available for the request")
        return peer_name[:2]

    def get_header(self, name: str, default: Any | None = None) -> Any:
        """
        Retrieves the value of a header
        """
        return self._request.headers.get(name, default)

    def get_headers(self) -> dict[str, Any]:
        """
        Retrieves all headers
        """
        return cast(dict[str, Any], self._request.headers)

    def get_path(self) -> str:
        """
        Retrieves the request full path, normalized
        """
        return self._full_path

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
        raise OSError("This stream is not readable")

    def write(self, b: bytes) -> int:  # type: ignore
        return self._buffer.write(b)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        raise OSError("This stream is not seekable")

    def tell(self) -> int:
        raise OSError("This stream is not seekable")

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
        self._headers: dict[str, str] = {}
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

    def set_response(self, code: int, message: str | None = None) -> None:
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        if self._headers_set:
            raise OSError("Headers have already been set, cannot change the response code")

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
            raise OSError("Headers have already been set, cannot change them")

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

    def __init__(
        self,
        request: aiohttp.web.Request,
        full_path: str,
        prefix: str,
        max_body_size: int | None = None,
    ) -> None:
        """
        Sets up the request helper

        :param request: The aiohttp Request object
        :param full_path: The full request path, including the prefix
        :param prefix: The path to the servlet root
        :param max_body_size: Maximum accepted size of the body, in bytes
        """
        self._request = request
        self._full_path = full_path
        self._prefix = prefix
        self.max_body_size = max_body_size

        # Compute the sub path
        self._sub_path = compute_sub_path(full_path, prefix)

    def get_command(self) -> str:
        """
        Returns the HTTP verb (GET, POST, ...) used for the request
        """
        return self._request.method.upper()

    def get_client_address(self) -> tuple[str, int]:
        """
        Retrieves the address of the client

        :return: A (host, port) tuple
        """
        if self._request.transport is None:
            # No transport, no address
            raise OSError("No transport available for the request")

        peer_name = self._request.transport.get_extra_info("peername")
        if not peer_name:
            raise OSError("No peer name available for the request")
        return peer_name[:2]

    async def get_header(self, name: str, default: Any | None = None) -> Any:
        """
        Retrieves the value of a header
        """
        return self._request.headers.get(name, default)

    async def get_headers(self) -> dict[str, Any]:
        """
        Retrieves all headers
        """
        return cast(dict[str, Any], self._request.headers)

    def get_path(self) -> str:
        """
        Retrieves the request full path, normalized
        """
        return self._full_path

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

    def set_response(self, code: int, message: str | None = None) -> None:
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        if self._headers_set:
            raise OSError("Headers have already been set, cannot change the response code")

        self._response.set_status(code, message)

    def set_header(self, name: str, value: Any) -> None:
        """
        Sets the value of a header.
        This method should not be called after ``end_headers()``.

        :param name: Header name
        :param value: Header value
        """
        if self._headers_set:
            raise OSError("Headers have already been set, cannot change them")

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
            raise OSError("Headers have already been set, cannot change them")

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
            raise OSError("SSE not set up, call setup_sse() first")

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
            raise OSError("Client connection reset during SSE send") from None


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

    def get_client_address(self) -> tuple[str, int]:
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
            raise OSError("WebSocket session is closed")

        await self._response.send_bytes(message)

    async def send_text(self, message: str) -> None:
        """
        Sends a message to the client

        :param message: Message to send
        """
        if self._response.closed:
            raise OSError("WebSocket session is closed")

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
class AsyncHttpServiceImpl(AbstractHttpService):
    """
    Asynchronous HTTP service component
    """

    def __init__(self) -> None:
        super().__init__()

        # This implementation always has a logger
        self._logger = logging.getLogger(f"{__name__}#init")

        # Fields injected by iPOPO
        self._servlets_services: list[http.Servlet] = []
        self._servlets_async_services: list[http.AsyncServlet] = []
        self._websocket_handler_services: list[http.WebSocketHandler] = []

        # Server control
        self._bound_address: tuple[str, int] | None = None
        self._app: aiohttp.web.Application | None = None
        self._thread: threading.Thread | None = None
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._start_done_event: utilities.EventData[tuple[str, int]] = utilities.EventData()
        self._stop_event: asyncio.Event = asyncio.Event()
        self._stop_done_event: threading.Event = threading.Event()

    @Validate
    def validate(self, context: "BundleContext") -> None:
        """
        Component validated
        """
        self._normalize_configuration()
        self._setup_logger()

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
            raise OSError("HTTP server did not start in time")

        if self._start_done_event.data is None:
            self._logger.error("HTTP server did not bind to an address")
            raise OSError("HTTP server did not bind to an address")

        host, port = self._start_done_event.data
        self._bound_address = (host, port)
        self._port = port

        # Register the servlets bound before the server was ready
        self._register_bound_servlets()

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
            # Cancel pending tasks
            pending = [task for task in asyncio.all_tasks(self._loop) if not task.done()]
            for task in pending:
                task.cancel()

            if self._loop.is_running():
                # The server thread didn't stop in time: the loop can neither be
                # driven from here nor closed. This happens when aiohttp is still
                # draining the connection of a client whose request was refused.
                # Its own thread stops it when it is done.
                self.log(
                    logging.WARNING,
                    "The event loop is still running: leaving it to its own thread",
                )
            else:
                try:
                    if pending:
                        self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

                    self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                    self._loop.run_until_complete(self._loop.shutdown_default_executor())
                except Exception:
                    self._logger.exception("Error closing the event loop")
                finally:
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
                self._loop = asyncio.SelectorEventLoop()
            else:
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
        except Exception as ex:  # noqa: BLE001
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

        # Use the raw path: aiohttp already decoded request.path, normalizing it again would double-decode
        routing = self.resolve_request(request.raw_path)
        if routing.error is not None:
            # The path itself has been refused: no servlet is looked for
            return aiohttp.web.Response(
                status=400, text="<html><body><h1>Bad Request</h1></body></html>", content_type="text/html"
            )

        path = routing.path
        servlet = routing.servlet
        if servlet is not None:
            prefix = routing.prefix
            servlet_type = routing.servlet_type

            async_name = f"do_async_{request.method.upper()}"
            sync_name = f"do_{request.method.upper()}"

            # The servlet can accept bodies of a different size than the others
            max_body_size = self.resolve_max_body_size(routing.parameters)

            try:
                match servlet_type:
                    case http.ServletType.ASYNC if hasattr(servlet, async_name):
                        # Prepare the helpers
                        servlet_request = _AsyncHTTPServletRequest(request, path, prefix, max_body_size)
                        servlet_response = _AsyncHTTPServletResponse(request)

                        # Handle the request
                        handler_method = getattr(servlet, async_name)
                        await handler_method(servlet_request, servlet_response)
                        return servlet_response.to_aiohttp_response()

                    case http.ServletType.SYNC if hasattr(servlet, sync_name):
                        # Read the request content
                        # FIXME: find a better way to handle the content, wrapping the request
                        #        in a file-like object
                        content = await http.read_body(
                            # aiohttp StreamReader is compatible with the asyncio one
                            cast(asyncio.StreamReader, request.content),
                            request.content_length,
                            max_body_size,
                        )

                        # Prepare the helpers
                        servlet_request = _SyncHTTPServletRequest(request, path, prefix, content)
                        servlet_response = _SyncHTTPServletResponse(request, self._loop)

                        # Copy the context here: unlike asyncio.to_thread, run_in_executor does not carry it
                        handler_method = getattr(servlet, sync_name)
                        context = contextvars.copy_context()
                        await self._loop.run_in_executor(
                            self._executor,
                            functools.partial(context.run, handler_method, servlet_request, servlet_response),
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

                            # End of loop: the WebSocket connection is closed
                            code = ws_response.close_code or aiohttp.WSCloseCode.GOING_AWAY
                            await ws_handler.ws_close(ws_session, code, "Session closed")
                        except Exception as ex:
                            self._logger.exception("Error handling WebSocket connection")
                            await ws_handler.ws_error(ws_session, str(ex))
                        finally:
                            if not ws_response.closed:
                                await ws_response.close()

                        return ws_response
            except aiohttp.web.HTTPException:
                # Let aiohttp answer the errors it detects itself
                raise
            except http.BodyTooLargeError as ex:
                # An asynchronous servlet refused to read the body of the
                # request: aiohttp only checks the size of the bodies it reads
                # itself, i.e. those given to synchronous servlets
                self.log(
                    logging.WARNING,
                    "Refused a request body of %d bytes on %s (maximum is %d)",
                    ex.size,
                    path,
                    ex.max_size,
                )
                # Note: the body has not been read. aiohttp will keep the
                # connection alive for a while, reading and discarding the rest
                # of the body the client announced ("lingering close"), so that
                # the client can finish sending it and read this answer
                raise aiohttp.web.HTTPRequestEntityTooLarge(ex.max_size, ex.size) from ex
            except Exception:  # noqa: BLE001
                # Send a 500 error page on error.
                # The details are logged by make_exception_page()
                self._logger.error("Error handling %s request to %s", request.method, path)
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
        # Get a formatted stack trace.
        # The error is logged by make_exception_page(), which also decides what
        # can be sent to the client
        stack = traceback.format_exc()

        # Send the page
        return aiohttp.web.Response(status=500, text=self.make_exception_page(path, stack))

    def _set_extra_parameters(self, parameters: dict[str, Any], servlet_type: http.ServletType) -> None:
        """
        Tells the servlet if it is registered in asynchronous mode

        :param parameters: The parameters given to the servlet
        :param servlet_type: The type of the servlet being registered
        """
        parameters[http.PARAM_ASYNC] = servlet_type != http.ServletType.SYNC

    def _register_servlet_service(
        self,
        service: http.Servlet | http.AsyncServlet | http.WebSocketHandler,
        service_reference: ServiceReference[Any],
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
                self.register_servlet(
                    paths,
                    sync_servlet,
                    self._get_servlet_parameters(service_reference),
                    http.ServletType.SYNC,
                )
            elif isinstance(paths, (list, tuple)):
                # Register the servlet to multiple paths
                for path in paths:
                    self.register_servlet(
                        path,
                        sync_servlet,
                        self._get_servlet_parameters(service_reference),
                        http.ServletType.SYNC,
                    )

        # No else here: a service could implement both specifications
        if http.HTTP_SERVLET_ASYNC in spec:
            # Asynchronous servlet bound
            async_servlet = cast(http.AsyncServlet, service)
            paths = service_reference.get_property(http.HTTP_SERVLET_ASYNC_PATH)
            if utilities.is_string(paths):
                # Register the servlet to a single path
                self.register_servlet(
                    paths,
                    async_servlet,
                    self._get_servlet_parameters(service_reference),
                    http.ServletType.ASYNC,
                )
            elif isinstance(paths, (list, tuple)):
                # Register the servlet to multiple paths
                for path in paths:
                    self.register_servlet(
                        path,
                        async_servlet,
                        self._get_servlet_parameters(service_reference),
                        http.ServletType.ASYNC,
                    )

        # No else here: a service could implement both specifications
        if http.HTTP_WEBSOCKET_HANDLER in spec:
            # WebSocket handler bound
            websocket_handler = cast(http.WebSocketHandler, service)
            paths = service_reference.get_property(http.HTTP_WEBSOCKET_PATH)
            if utilities.is_string(paths):
                # Register the WebSocket handler to a single path
                self.register_servlet(
                    paths,
                    websocket_handler,
                    self._get_servlet_parameters(service_reference),
                    http.ServletType.WEBSOCKET,
                )
            elif isinstance(paths, (list, tuple)):
                # Register the WebSocket handler to multiple paths
                for path in paths:
                    self.register_servlet(
                        path,
                        websocket_handler,
                        self._get_servlet_parameters(service_reference),
                        http.ServletType.WEBSOCKET,
                    )

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
        self._on_bind(service, service_reference)

    @UpdateField("_servlets_services")
    @UpdateField("_servlets_async_services")
    @UpdateField("_websocket_handler_services")
    def _update_servlet(
        self,
        _: str,
        service: http.Servlet | http.AsyncServlet | http.WebSocketHandler,
        service_reference: ServiceReference[http.Servlet | http.AsyncServlet | http.WebSocketHandler],
        old_properties: dict[str, Any],
    ) -> None:
        """
        Called by iPOPO when the properties of a service have been updated
        """
        self._on_update(
            service,
            service_reference,
            old_properties,
            (
                http.HTTP_SERVLET_PATH,
                http.HTTP_SERVLET_ASYNC_PATH,
                http.HTTP_WEBSOCKET_PATH,
                http.HTTP_MAX_BODY_SIZE,
            ),
        )

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
        self._on_unbind(service, service_reference)

    def get_access(self) -> tuple[str, int]:
        """
        Retrieves the (address, port) tuple to access the server
        """
        assert self._bound_address is not None, "Server must be started before accessing its address"
        return self._bound_address
