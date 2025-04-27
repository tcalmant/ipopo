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

from abc import ABC, abstractmethod
from typing import IO, Any, Dict, Iterable, List, Optional, Protocol, Tuple
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

# Service to provide custom 404 and 500 error pages
HTTP_ERROR_PAGES = "pelix.http.error.pages"

# ------------------------------------------------------------------------------

FACTORY_HTTP_BASIC = "pelix.http.service.basic.factory"
""" Name of the HTTP service component factory """

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
    """


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

    def get_servlet(self, path: Optional[str]) -> Optional[Tuple[Servlet, Dict[str, Any], str]]:
        """
        Retrieves the servlet matching the given path and its parameters.
        Returns None if no servlet matches the given path.

        :param path: A request URI
        :return: A tuple (servlet, parameters, prefix) or None
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
        self, path: str, servlet: Servlet, parameters: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Registers a servlet

        :param path: Path handled by this servlet
        :param servlet: The servlet instance
        :param parameters: The parameters associated to this path
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
