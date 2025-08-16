#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix HTTP package.

Defines the interfaces that must respect HTTP service implementations.

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
from abc import ABC, abstractmethod
from enum import Enum
from typing import IO, Any, Dict, Iterable, List, Optional, Protocol, Tuple, runtime_checkable

from pelix.constants import Specification
from pelix.utilities import to_bytes

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# HTTP service constants
HTTP_SERVICE = "pelix.http.service"
""" HTTP Service specification """

# ... binding address
HTTP_SERVICE_ADDRESS = "pelix.http.address"
""" HTTP Service binding address property (string) """

# ... binding port
HTTP_SERVICE_PORT = "pelix.http.port"
""" HTTP Service binding port property (int) """

# ... server uses SSL (read-only flag)
HTTP_USES_SSL = "pelix.https"
""" Read-only flag indicating if the server is using SSL (HTTPS) """

# ... the certificate file for HTTPS servers
HTTPS_CERT_FILE = "pelix.https.cert_file"
""" Path to the certificate file to configure a HTTPS server """

# ... the key file for HTTPS servers
HTTPS_KEY_FILE = "pelix.https.key_file"
""" Path to the certificate key file to configure a HTTPS server """

# ... the password of the key file for HTTPS servers
# (supported since Python 3.3)
HTTPS_KEY_PASSWORD = "pelix.https.key_password"

# HTTP servlet constants
HTTP_SERVLET = "pelix.http.servlet"
""" HTTP Servlet service specification """

# ... servlet path(s) (string or list of strings)
HTTP_SERVLET_PATH = "pelix.http.path"
""" HTTP Servlet path(s) (string or list or tuple of strings) """

# Async servlet service specification
HTTP_SERVLET_ASYNC = "pelix.http.servlet.async"
""" Asynchronous HTTP Servlet service specification """

# ... servlet path(s) (string or list of strings)
HTTP_SERVLET_ASYNC_PATH = "pelix.http.path.async"
""" HTTP Asynchronous Servlet path(s) (string or list or tuple of strings) """

# WebSocket handler service specification
HTTP_WEBSOCKET_HANDLER = "pelix.http.websocket.handler"
""" WebSocket handler service specification """

# ... WebSocket handler path (string or list of strings)
HTTP_WEBSOCKET_PATH = "pelix.http.websocket.path"
""" WebSocket handler path(s) (string or list or tuple of strings) """

# Service to provide custom 404 and 500 error pages
HTTP_ERROR_PAGES = "pelix.http.error.pages"

# ------------------------------------------------------------------------------

FACTORY_HTTP_BASIC = "pelix.http.service.basic.factory"
""" Name of the HTTP service component factory """

FACTORY_HTTP_ASYNC = "pelix.http.service.async.factory"
""" Name of the Async HTTP service component factory """

# ------------------------------------------------------------------------------

PARAM_NAME = "http.name"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains the name of the server.
If the HTTP service is implemented with iPOPO, it might be the instance name.
"""

PARAM_EXTRA = "http.extra"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains a copy of extra properties of the HTTP service implementation.
Its content is implementation dependent.
"""

PARAM_ADDRESS = "http.address"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains the socket binding address of the HTTP server binding the servlet
"""

PARAM_PORT = "http.port"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains the listening port of the HTTP server binding the servlet
"""

PARAM_HTTPS = "http.https"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains a boolean: if True, the connection to the server is encrypted (HTTPS)
"""

PARAM_ASYNC = "http.async"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains a boolean: if True, the servlet is bound as an asynchronous servlet.
"""

# ------------------------------------------------------------------------------


def make_html_list(items: Iterable[Any], tag: str = "ul") -> str:
    """
    Makes a HTML list from the given iterable

    :param items: The items to list
    :param tag: The tag to use (ul or ol)
    :return: The HTML list code
    """
    html_list = "\n".join(f'<li><a href="{item}">{item}</a></li>' for item in items)
    return f"<{tag}>\n{html_list}\n</{tag}>"


# ------------------------------------------------------------------------------


class AbstractHTTPServletRequest(ABC):
    """
    Abstract HTTP Servlet request helper
    """

    @abstractmethod
    def get_command(self) -> str:
        """
        Returns the HTTP verb (GET, POST, ...) used for the request
        """
        ...

    @abstractmethod
    def get_client_address(self) -> Tuple[str, int]:
        """
        Returns the address of the client

        :return: A (host, port) tuple
        """
        ...

    @abstractmethod
    def get_header(self, name: str, default: Any = None) -> Any:
        """
        Returns the value of a header

        :param name: Header name
        :param default: Default value if the header doesn't exist
        :return: The header value or the default one
        """
        ...

    @abstractmethod
    def get_headers(self) -> Dict[str, Any]:
        """
        Returns a copy all headers, with a dictionary interface

        :return: A dictionary-like object
        """
        ...

    @abstractmethod
    def get_path(self) -> str:
        """
        Returns the request full path

        :return: A request full path (string)
        """
        ...

    @abstractmethod
    def get_prefix_path(self) -> str:
        """
        Returns the path to the servlet root

        :return: A request path (string)
        """
        ...

    @abstractmethod
    def get_sub_path(self) -> str:
        """
        Returns the servlet-relative path, i.e. after the prefix

        :return: A request path (string)
        """
        ...

    @abstractmethod
    def get_rfile(self) -> IO[bytes]:
        """
        Returns the request input as a file stream

        :return: A file-like input stream
        """
        ...

    def read_data(self) -> bytes:
        """
        Reads all the data in the input stream

        :return: The read data
        """
        try:
            size = int(self.get_header("content-length"))
        except (ValueError, TypeError):
            size = -1

        return self.get_rfile().read(size)


class AbstractHTTPServletResponse(ABC):
    """
    HTTP Servlet response helper
    """

    @abstractmethod
    def set_response(self, code: int, message: Optional[str] = None) -> None:
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        ...

    @abstractmethod
    def set_header(self, name: str, value: Any) -> None:
        """
        Sets the value of a header.
        This method should not be called after ``end_headers()``.

        :param name: Header name
        :param value: Header value
        """
        ...

    @abstractmethod
    def is_header_set(self, name: str) -> bool:
        """
        Checks if the given header has already been set

        :param name: Header name
        :return: True if it has already been set
        """
        ...

    @abstractmethod
    def end_headers(self) -> None:
        """
        Ends the headers part
        """
        ...

    @abstractmethod
    def get_wfile(self) -> IO[bytes]:
        """
        Retrieves the output as a file stream.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :return: A file-like output stream
        """
        ...

    @abstractmethod
    def write(self, data: bytes) -> None:
        """
        Writes the given data.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :param data: Data to be written
        """
        ...

    def send_content(
        self,
        http_code: int,
        content: str,
        mime_type: Optional[str] = "text/html",
        http_message: Optional[str] = None,
        content_length: int = -1,
    ) -> None:
        """
        Utility method to send the given content as an answer.
        You can still use get_wfile or write afterwards, if you forced the
        content length.

        If content_length is negative (default), it will be computed as the
        length of the content;
        if it is positive, the given value will be used;
        if it is None, the content-length header won't be sent.

        :param http_code: HTTP result code
        :param content: Data to be sent (must be a string)
        :param mime_type: Content MIME type (content-type)
        :param http_message: HTTP code description
        :param content_length: Forced content length
        """
        self.set_response(http_code, http_message)
        if mime_type and not self.is_header_set("content-type"):
            self.set_header("content-type", mime_type)

        # Convert the content
        raw_content = to_bytes(content)

        if content_length is not None and not self.is_header_set("content-length"):
            if content_length < 0:
                # Compute the length
                content_length = len(raw_content)

            # Send the length
            self.set_header("content-length", content_length)

        self.end_headers()

        # Send the content
        self.write(raw_content)


class AbstractAsyncHTTPServletRequest(ABC):
    """
    Asynchronous HTTP Servlet request helper
    """

    @abstractmethod
    def get_command(self) -> str:
        """
        Returns the HTTP verb (GET, POST, ...) used for the request
        """
        ...

    @abstractmethod
    def get_client_address(self) -> Tuple[str, int]:
        """
        Returns the address of the client

        :return: A (host, port) tuple
        """
        ...

    @abstractmethod
    async def get_header(self, name: str, default: Any = None) -> Any:
        """
        Returns the value of a header

        :param name: Header name
        :param default: Default value if the header doesn't exist
        :return: The header value or the default one
        """
        ...

    @abstractmethod
    async def get_headers(self) -> Dict[str, Any]:
        """
        Returns a copy all headers, with a dictionary interface

        :return: A dictionary-like object
        """
        ...

    @abstractmethod
    def get_path(self) -> str:
        """
        Returns the request full path

        :return: A request full path (string)
        """
        ...

    @abstractmethod
    def get_prefix_path(self) -> str:
        """
        Returns the path to the servlet root

        :return: A request path (string)
        """
        ...

    @abstractmethod
    def get_sub_path(self) -> str:
        """
        Returns the servlet-relative path, i.e. after the prefix

        :return: A request path (string)
        """
        ...

    @abstractmethod
    def get_rfile(self) -> asyncio.StreamReader:
        """
        Returns the request input as a stream reader

        :return: A stream reader for the input stream
        """
        ...

    async def read_data(self) -> bytes:
        """
        Reads all the data in the input stream

        :return: The read data
        """
        try:
            size = int(await self.get_header("content-length"))
        except (ValueError, TypeError):
            size = -1

        return await self.get_rfile().read(size)


class AbstractAsyncWriter(ABC):
    """
    Abstract class to wrap asynchronous writers
    """

    async def write(self, raw: bytes) -> int:
        """
        Writes raw data to the stream

        :param raw: Data to write
        :return: Number of bytes written
        """
        ...

    async def flush(self) -> None:
        """
        Flushes the buffer if any
        """
        ...


class AbstractAsyncHTTPServletResponse(ABC):
    """
    Asynchronous HTTP Servlet response helper
    """

    @abstractmethod
    def set_response(self, code: int, message: Optional[str] = None) -> None:
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        ...

    @abstractmethod
    def set_header(self, name: str, value: Any) -> None:
        """
        Sets the value of a header.
        This method should not be called after ``end_headers()``.

        :param name: Header name
        :param value: Header value
        """
        ...

    @abstractmethod
    def is_header_set(self, name: str) -> bool:
        """
        Checks if the given header has already been set

        :param name: Header name
        :return: True if it has already been set
        """
        ...

    @abstractmethod
    def setup_sse(self) -> None:
        """
        Sets up the response for Server-Sent Events (SSE).
        This method mist be called before `end_headers()`.
        """
        raise NotImplementedError

    @abstractmethod
    async def end_headers(self) -> None:
        """
        Ends the headers part
        """
        ...

    @abstractmethod
    def get_wfile(self) -> AbstractAsyncWriter:
        """
        Retrieves the output as a writer.
        ``end_headers()`` should have been called before.

        :return: A writer for the output stream
        """
        ...

    @abstractmethod
    async def write(self, data: bytes) -> None:
        """
        Writes the given data.
        ``end_headers()`` should have been called before.

        :param data: Data to be written
        """
        out = self.get_wfile()
        await out.write(data)
        await out.flush()

    @abstractmethod
    async def send_sse(
        self, event: str | None = None, data: str | None = None, id: str | None = None
    ) -> None:
        """
        Sends a Server-Sent Event (SSE) message.

        :param event: The event name (optional)
        :param data: The event data (optional)
        :param id: The event ID (optional)
        """
        raise NotImplementedError

    async def send_content(
        self,
        http_code: int,
        content: str,
        mime_type: Optional[str] = "text/html",
        http_message: Optional[str] = None,
        content_length: int = -1,
    ) -> None:
        """
        Utility method to send the given content as an answer.
        You can still use get_wfile or write afterwards, if you forced the
        content length.

        If content_length is negative (default), it will be computed as the
        length of the content;
        if it is positive, the given value will be used;
        if it is None, the content-length header won't be sent.

        :param http_code: HTTP result code
        :param content: Data to be sent (must be a string)
        :param mime_type: Content MIME type (content-type)
        :param http_message: HTTP code description
        :param content_length: Forced content length
        """
        self.set_response(http_code, http_message)
        if mime_type and not self.is_header_set("content-type"):
            self.set_header("content-type", mime_type)

        # Convert the content
        raw_content = to_bytes(content)

        if content_length is not None and not self.is_header_set("content-length"):
            if content_length < 0:
                # Compute the length
                content_length = len(raw_content)

            # Send the length
            self.set_header("content-length", content_length)

        await self.end_headers()

        # Send the content
        await self.write(raw_content)


class ErrorHandler(Protocol):
    """
    Custom HTTP error page generator
    """

    def make_not_found_page(self, path: str) -> str:
        """
        Prepares a "page not found" page for a 404 error

        :param path: Request path
        :return: A HTML page
        """
        ...

    def make_exception_page(self, path: str, stack: str) -> str:
        """
        Prepares a page printing an exception stack trace in a 500 error

        :param path: Request path
        :param stack: Exception stack trace
        :return: A HTML page
        """
        ...


@Specification(HTTP_SERVLET)
class Servlet(Protocol):
    """
    Interface of an HTTP servlet

    Servlets are classes with `do_<VERB>` methods, where `<VERB>` is the
    HTTP verb used for the request (GET, POST, PUT, DELETE, ...).
    Those methods take two arguments: an AbstractHTTPServletRequest and an
    AbstractHTTPServletResponse.
    """


@Specification(HTTP_SERVLET_ASYNC)
class AsyncServlet(Protocol):
    """
    Interface of an asynchronous HTTP servlet

    Servlets are classes with `do_async_<VERB>` coroutines, where `<VERB>` is
    the HTTP verb used for the request (GET, POST, PUT, DELETE, ...).
    Those methods take two arguments: an AbstractAsyncHTTPServletRequest and an
    AbstractAsyncHTTPServletResponse.
    """


class WebSocketSession(Protocol):
    """
    Websocket session helper
    """

    def get_client_address(self) -> Tuple[str, int]:
        """
        Returns the address of the client

        :return: A (host, port) tuple
        """
        ...

    async def send_binary(self, message: bytes) -> None:
        """
        Sends a binary message to the client

        :param message: Binary message to send
        """
        ...

    async def send_text(self, message: str) -> None:
        """
        Sends a message to the client

        :param message: Message to send
        """
        ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        """
        Closes the WebSocket session

        :param code: Close code (default is 1000, normal closure)
        :param reason: Optional reason for the closure
        """
        ...


@Specification(HTTP_WEBSOCKET_HANDLER)
@runtime_checkable
class WebSocketHandler(Protocol):
    """
    Interface of a WebSocket handler

    WebSocket handlers are classes with `on_open`, `on_message`, `on_close`
    and `on_error` methods.
    """

    async def ws_accept(self, request: AbstractAsyncHTTPServletRequest) -> bool:
        """
        Called when a new WebSocket connection is requested.

        :param request: The HTTP request that initiates the WebSocket connection
        :return: True if the connection is accepted, False to reject it
        """
        ...

    async def ws_open(self, session: WebSocketSession, request: AbstractAsyncHTTPServletRequest) -> None:
        """
        Called when a new WebSocket connection is opened
        """
        ...

    async def ws_binary(self, session: WebSocketSession, message: bytes) -> None:
        """
        Called when a binary message is received from the client
        """
        ...

    async def ws_message(self, session: WebSocketSession, message: str) -> None:
        """
        Called when a message is received from the client
        """
        ...

    async def ws_close(self, session: WebSocketSession, code: int, reason: str) -> None:
        """
        Called when the WebSocket connection is closed
        """
        ...

    async def ws_error(self, session: WebSocketSession, error: str) -> None:
        """
        Called when an error occurs
        """
        ...


class AbstractWebSocketHandler(WebSocketHandler):
    """
    Abstract class for WebSocket handlers

    This class can be used to implement a WebSocket handler with default methods.
    """

    async def ws_accept(self, request: AbstractAsyncHTTPServletRequest) -> bool:
        """
        Accepts all WebSocket connections by default
        """
        return True

    async def ws_open(self, session: WebSocketSession, request: AbstractAsyncHTTPServletRequest) -> None:
        """
        Default implementation does nothing
        """

    async def ws_binary(self, session: WebSocketSession, message: bytes) -> None:
        """
        Default implementation does nothing
        """

    async def ws_message(self, session: WebSocketSession, message: str) -> None:
        """
        Default implementation does nothing
        """

    async def ws_close(self, session: WebSocketSession, code: int, reason: str) -> None:
        """
        Default implementation does nothing
        """

    async def ws_error(self, session: WebSocketSession, error: Exception) -> None:
        """
        Default implementation does nothing
        """


class ServletType(Enum):
    """
    Type of servlet
    """

    SYNC = "sync"
    """ Synchronous servlet """

    ASYNC = "async"
    """ Asynchronous servlet """

    WEBSOCKET = "websocket"
    """ WebSocket handler """


@Specification(HTTP_SERVICE)
class HTTPService(Protocol):
    """
    HTTP service interface
    """

    def get_access(self) -> Tuple[str, int]:
        """
        Retrieves the (address, port) tuple to access the server
        """
        ...

    def get_hostname(self) -> str:
        """
        Retrieves the server host name

        :return: The server host name
        """
        ...

    def is_https(self) -> bool:
        """
        Returns True if this is an HTTPS server

        :return: True if this server uses SSL
        """
        ...

    def get_registered_paths(self) -> List[str]:
        """
        Returns the paths registered by servlets

        :return: The paths registered by servlets (sorted list)
        """
        ...

    def get_servlet(self, path: Optional[str]) -> Optional[Tuple[Servlet, Dict[str, Any], str, ServletType]]:
        """
        Retrieves the servlet matching the given path and its parameters.
        Returns None if no servlet matches the given path.

        :param path: A request URI
        :return: A tuple (servlet, parameters, prefix, type) or None
        """
        ...

    def make_not_found_page(self, path: str) -> str:
        """
        Prepares a "page not found" page for a 404 error

        :param path: Request path
        :return: A HTML page
        """
        ...

    def make_exception_page(self, path: str, stack: str) -> str:
        """
        Prepares a page printing an exception stack trace in a 500 error

        :param path: Request path
        :param stack: Exception stack trace
        :return: A HTML page
        """
        ...

    def register_servlet(
        self,
        path: str,
        servlet: Servlet,
        parameters: Optional[Dict[str, Any]] = None,
        servlet_type: ServletType = ServletType.SYNC,
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
        ...

    def unregister(self, path: Optional[str], servlet: Optional[Servlet] = None) -> bool:
        """
        Unregisters the servlet for the given path

        :param path: The path to a servlet
        :param servlet: If given, unregisters all the paths handled by this servlet
        :return: True if at least one path as been unregistered, else False
        """
        ...

    def log(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        """
        Logs the given message

        :param level: Log entry level
        :param message: Log message (Python logging format)
        """
        ...

    def log_exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """
        Logs an exception

        :param message: Log message (Python logging format)
        """
        ...
