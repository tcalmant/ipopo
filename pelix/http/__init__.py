#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix HTTP package.

Defines the interfaces that must respect HTTP service implementations.

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.1.1
:status: Beta

..

    Copyright 2013 isandlaTech

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

# Module version
__version_info__ = (0, 1, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix utility methods
from pelix.utilities import to_bytes

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

# HTTP servlet constants
HTTP_SERVLET = "pelix.http.servlet"
""" HTTP Servlet service specification """

# ... servlet path(s) (string or list of strings)
HTTP_SERVLET_PATH = "pelix.http.path"
""" HTTP Servlet path(s) (string or list or tuple of strings) """

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

# ------------------------------------------------------------------------------

class AbstractHTTPServletRequest(object):
    """
    Abstract HTTP Servlet request helper
    """
    def get_client_address(self):
        """
        Returns the address of the client

        :return: A (host, port) tuple
        """
        raise NotImplementedError("This method must be implemented by a child")


    def get_header(self, name, default=None):
        """
        Returns the value of a header

        :param name: Header name
        :param default: Default value if the header doesn't exist
        :return: The header value or the default one
        """
        raise NotImplementedError("This method must be implemented by a child")


    def get_headers(self):
        """
        Returns a copy all headers, with a dictionary interface

        :return: A dictionary-like object
        """
        raise NotImplementedError("This method must be implemented by a child")


    def get_path(self):
        """
        Returns the request full path

        :return: A request full path (string)
        """
        raise NotImplementedError("This method must be implemented by a child")


    def get_rfile(self):
        """
        Returns the request input as a file stream

        :return: A file-like input stream
        """
        raise NotImplementedError("This method must be implemented by a child")


    def read_data(self):
        """
        Reads all the data in the input stream

        :return: The read data
        """
        try:
            size = int(self.get_header('content-length'))

        except ValueError:
            size = -1

        return self.get_rfile().read(size)


class AbstractHTTPServletResponse(object):
    """
    HTTP Servlet response helper
    """
    def set_response(self, code, message=None):
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        raise NotImplementedError("This method must be implemented by a child")


    def set_header(self, name, value):
        """
        Sets the value of a header.
        This method should not be called after ``end_headers()``.

        :param name: Header name
        :param value: Header value
        """
        raise NotImplementedError("This method must be implemented by a child")


    def end_headers(self):
        """
        Ends the headers part
        """
        raise NotImplementedError("This method must be implemented by a child")


    def get_wfile(self):
        """
        Retrieves the output as a file stream.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :return: A file-like output stream
        """
        raise NotImplementedError("This method must be implemented by a child")


    def write(self, data):
        """
        Writes the given data.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :param data: Data to be written
        """
        raise NotImplementedError("This method must be implemented by a child")


    def send_content(self, http_code, content, mime_type="text/html",
                      http_message=None, content_length=-1):
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
        if mime_type:
            self.set_header("content-type", mime_type)

        # Convert the content
        content = to_bytes(content)

        if content_length is not None:
            if content_length < 0:
                # Compute the length
                content_length = len(content)

            # Send the length
            self.set_header("content-length", content_length)

        self.end_headers()

        # Send the content
        self.write(content)

