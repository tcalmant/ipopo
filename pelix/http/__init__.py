#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix HTTP package.

Defines the interfaces that must respect HTTP service implementations.

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Thomas Calmant

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

# Standard typing module should be optional
try:
    # pylint: disable=W0611
    from typing import Any, ByteString, Dict, Iterable, IO, Tuple
except ImportError:
    pass

# Pelix utility methods
from pelix.utilities import to_bytes

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
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


def make_html_list(items, tag="ul"):
    # type: (Iterable[Any], str) -> str
    """
    Makes a HTML list from the given iterable

    :param items: The items to list
    :param tag: The tag to use (ul or ol)
    :return: The HTML list code
    """
    html_list = "\n".join(
        '<li><a href="{0}">{0}</a></li>'.format(item) for item in items
    )
    return "<{0}>\n{1}\n</{0}>".format(tag, html_list)


# ------------------------------------------------------------------------------


class AbstractHTTPServletRequest(object):
    """
    Abstract HTTP Servlet request helper
    """

    def get_command(self):
        # type: () -> str
        """
        Returns the HTTP verb (GET, POST, ...) used for the request
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def get_client_address(self):
        # type: () -> Tuple[str, int]
        """
        Returns the address of the client

        :return: A (host, port) tuple
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def get_header(self, name, default=None):
        # type: (str, Any) -> Any
        """
        Returns the value of a header

        :param name: Header name
        :param default: Default value if the header doesn't exist
        :return: The header value or the default one
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def get_headers(self):
        # type: () -> Dict[str, Any]
        """
        Returns a copy all headers, with a dictionary interface

        :return: A dictionary-like object
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def get_path(self):
        # type: () -> str
        """
        Returns the request full path

        :return: A request full path (string)
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def get_prefix_path(self):
        # type: () -> str
        """
        Returns the path to the servlet root

        :return: A request path (string)
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def get_sub_path(self):
        # type: () -> str
        """
        Returns the servlet-relative path, i.e. after the prefix

        :return: A request path (string)
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def get_rfile(self):
        # type: () -> IO
        """
        Returns the request input as a file stream

        :return: A file-like input stream
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def read_data(self):
        # type: () -> ByteString
        """
        Reads all the data in the input stream

        :return: The read data
        """
        try:
            size = int(self.get_header("content-length"))
        except (ValueError, TypeError):
            size = -1

        return self.get_rfile().read(size)


class AbstractHTTPServletResponse(object):
    """
    HTTP Servlet response helper
    """

    def set_response(self, code, message=None):
        # type: (int, str) -> None
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def set_header(self, name, value):
        # type: (str, Any) -> None
        """
        Sets the value of a header.
        This method should not be called after ``end_headers()``.

        :param name: Header name
        :param value: Header value
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def is_header_set(self, name):
        # type: (str) -> bool
        """
        Checks if the given header has already been set

        :param name: Header name
        :return: True if it has already been set
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def end_headers(self):
        """
        Ends the headers part
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def get_wfile(self):
        # type: () -> IO
        """
        Retrieves the output as a file stream.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :return: A file-like output stream
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def write(self, data):
        # type: (ByteString) -> None
        """
        Writes the given data.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :param data: Data to be written
        """
        raise NotImplementedError(
            "This method must be implemented by a child class"
        )

    def send_content(
        self,
        http_code,
        content,
        mime_type="text/html",
        http_message=None,
        content_length=-1,
    ):
        # type: (int, str, str, str, int) -> None
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

        if content_length is not None and not self.is_header_set(
            "content-length"
        ):
            if content_length < 0:
                # Compute the length
                content_length = len(raw_content)

            # Send the length
            self.set_header("content-length", content_length)

        self.end_headers()

        # Send the content
        self.write(raw_content)
