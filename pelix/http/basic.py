#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix basic HTTP service bundle.

Provides an implementation of the Pelix HTTP service based on the standard
Python library.

:author: Thomas Calmant
:copyright: Copyright 2012, isandlaTech
:license: GPLv3
:version: 0.1
:status: Alpha

..

    This file is part of iPOPO.

    iPOPO is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    iPOPO is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with iPOPO. If not, see <http://www.gnu.org/licenses/>.
"""

__version__ = (0, 1, 0)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

from pelix.ipopo.decorators import ComponentFactory, Provides, Validate, \
    Invalidate, Property, Instantiate, Requires, Bind, Unbind

import pelix.ipopo.constants as constants
import pelix.framework as pelix
import pelix.utilities as utilities

import logging
import socket
import sys
import threading

# Basic HTTP server
if sys.version_info[0] == 3:
    # Python 3
    import urllib.parse as urlparse
    from http.server import HTTPServer
    from http.server import BaseHTTPRequestHandler
    from socketserver import ThreadingMixIn

else:
    # Python 2
    import urlparse
    from BaseHTTPServer import HTTPServer
    from BaseHTTPServer import BaseHTTPRequestHandler
    from SocketServer import ThreadingMixIn

# ------------------------------------------------------------------------------

# HTTP service constants
import pelix.http as http

HTTP_SERVICE_COMPONENT_FACTORY = "pelix.http.service.basic.factory"

# ------------------------------------------------------------------------------

class _HTTPServletRequest(http.AbstractHTTPServletRequest):
    """
    HTTP Servlet request helper
    """
    def __init__(self, request_handler):
        """
        Sets up the request helper
        
        :param request_handler: The basic request handler
        """
        self._handler = request_handler


    def get_client_address(self):
        """
        Retrieves the address of the client
        
        :return: A (host, port) tuple
        """
        return self._handler.client_address


    def get_header(self, name, default=None):
        """
        Retrieves the value of a header
        """
        return self._handler.headers.get(name, default)


    def get_headers(self):
        """
        Retrieves all headers
        """
        return self._handler.headers


    def get_path(self):
        """
        Retrieves the request full path
        """
        return self._handler.path


    def get_rfile(self):
        """
        Retrieves the input as a file stream
        """
        return self._handler.rfile


class _HTTPServletResponse(http.AbstractHTTPServletResponse):
    """
    HTTP Servlet response helper
    """
    def __init__(self, request_handler):
        """
        Sets up the response helper
        
        :param request_handler: The basic request handler
        """
        self._handler = request_handler


    def set_response(self, code, message=None):
        """
        Sets the response line.
        This method should be the first called when sending an answer.
        
        :param code: HTTP result code
        :param message: Associated message
        """
        self._handler.send_response(code, message)


    def set_header(self, name, value):
        """
        Sets the value of a header.
        This method should not be called after ``end_headers()``.
        
        :param name: Header name
        :param value: Header value
        """
        self._handler.send_header(name, value)


    def end_headers(self):
        """
        Ends the headers part
        """
        self._handler.end_headers()


    def get_wfile(self):
        """
        Retrieves the output as a file stream.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.
        
        :return: The output file-like object
        """
        return self._handler.wfile


    def write(self, data):
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

    def __init__(self, http_svc, *args, **kwargs):
        """
        Sets up the request handler (called for each request)
        
        :param http_svc: The associated HTTP service
        """
        self._service = http_svc

        # This calls the do_* methods
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)


    def __getattr__(self, name):
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

        # Parse the URL
        parsed_url = urlparse.urlparse(self.path)
        parsed_path = parsed_url.path

        # Get the corresponding servlet
        servlet_info = self._service.get_servlet(parsed_path)
        if servlet_info is not None:
            servlet = servlet_info[0]
            if hasattr(servlet, name):
                # Prepare the helpers
                request = _HTTPServletRequest(self)
                response = _HTTPServletResponse(self)

                # Create a wrapper to pass the handler to the servlet
                def wrapper():
                    return getattr(servlet, name)(request, response)

                # Return it
                return wrapper

        # Return the super implementation if needed
        return self.send_no_servlet_response


    def log_error(self, message, *args, **kwargs):
        """
        Log server error
        """
        self._service.log(logging.ERROR, message, *args, **kwargs)


    def log_request(self, message, *args, **kwargs):
        """
        Log a request to the server
        """
        self._service.log(logging.DEBUG, message, *args, **kwargs)


    def send_no_servlet_response(self):
        """
        Default response sent when no servlet is found for the requested path
        """
        page = """<html>
<head>
<title>404 - Page not found</title>
</head>
<body>
<h1>Page not found</h1>
<p>No servlet is associated to this path: <pre>{0}</pre></p>
</body>
</html>""".format(self.path)

        # Use the helper to send the error page
        response = _HTTPServletResponse(self)
        response.send_content(404, page)

# ------------------------------------------------------------------------------

class _HttpServerFamily(ThreadingMixIn, HTTPServer):
    """
    A small modification to have a threaded HTTP Server with a custom address
    family
    
    Inspired from:
    http://www.arcfn.com/2011/02/ipv6-web-serving-with-arc-or-python.html
    """
    def __init__(self, server_address, request_handler_class, logger=None):
        """
        Proxy constructor
        
        :param server_address: The server address
        :param request_handler_class: The request handler class
        :param logger: An optional logger, in case of ignored error
        """
        # Determine the address family
        addr_info = socket.getaddrinfo(server_address[0], server_address[1],
                                       0, 0, socket.SOL_TCP)

        # Change the address family before the socket is created
        # Get the family of the first possibility
        self.address_family = addr_info[0][0]

        # Special case: IPv6
        ipv6 = (self.address_family == socket.AF_INET6)

        # Set up the server, socket, ... but do not bind immediately
        HTTPServer.__init__(self, server_address, request_handler_class, False)

        if ipv6:
            # Explicitly ask to be accessible both by IPv4 and IPv6
            # Some versions of Python don't have V6ONLY.
            # On Linux, IPC6_V6ONLY = 26
            IPV6_V6ONLY = getattr(socket, "IPV6_V6ONLY", 26)

            try:
                self.socket.setsockopt(socket.IPPROTO_IPV6, IPV6_V6ONLY, 0)

            except socket.error as ex:
                # Ignore the error, but log it if possible
                if logger is not None:
                    logger.exception("Couldn't set IP double stack flag: %s",
                                     ex)

        # Bind & accept
        self.server_bind()
        self.server_activate()

# ------------------------------------------------------------------------------

@ComponentFactory(name=HTTP_SERVICE_COMPONENT_FACTORY)
@Provides(specifications=http.HTTP_SERVICE)
@Requires("_servlets_services", http.HTTP_SERVLET, True, True)
@Property("_address", http.HTTP_SERVICE_ADDRESS, "0.0.0.0")
@Property("_port", http.HTTP_SERVICE_PORT, 8080)
@Property("_instance_name", constants.IPOPO_INSTANCE_NAME)
@Property("_logger_name", "pelix.http.logger.name", "")
@Property("_logger_level", "pelix.http.logger.level", logging.ERROR)
class HttpService(object):
    """
    Basic HTTP service component
    """
    def __init__(self):
        """
        Constructor
        """
        # Properties
        self._address = "0.0.0.0"
        self._port = 8080
        self._instance_name = None
        self._logger_name = None
        self._logger_level = None

        # The logger
        self._logger = None

        # Servlets registry lock
        self._lock = threading.Lock()

        # Path -> (servlet, parameters)
        self._servlets = {}

        # Field injected by iPOPO
        self._servlets_services = None

        self._server = None
        self._thread = None


    def __str__(self):
        """
        String representation of the instance
        """
        return "BasicHttpService({0}, {1:d})".format(self._address, self._port)


    def __safe_callback(self, instance, method, *args, **kwargs):
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

        callback = getattr(instance, method, None)
        if callback is None:
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


    @Bind
    def _bind(self, service, service_reference):
        """
        Called by iPOPO when a service is bound
        """
        specifications = service_reference.get_property(pelix.OBJECTCLASS)
        if http.HTTP_SERVLET in specifications:
            # Servlet bound
            paths = service_reference.get_property(http.HTTP_SERVLET_PATH)
            if utilities.is_string(paths):
                # Register the servlet to a single path
                self.register_servlet(paths, service, None)

            elif isinstance(paths, (list, tuple)):
                # Register the servlet to multiple paths
                for path in paths:
                    self.register_servlet(path, service, None)


    @Unbind
    def _unbind(self, service, service_reference):
        """
        Called by iPOPO when a service is gone
        """
        specifications = service_reference.get_property(pelix.OBJECTCLASS)
        if http.HTTP_SERVLET in specifications:
            # Servlet gone: unregister all paths associated to this servlet
            self.unregister(None, service)


    def get_access(self):
        """
        Retrieves the (address, port) tuple to access the server
        """
        sock_info = self._server.socket.getsockname()

        # Only keep the address and the port information
        return sock_info[0], sock_info[1]


    def get_hostname(self):
        """
        Retrieves the server host name
        
        :return: The server host name
        """
        return socket.gethostname()


    def get_servlet(self, path):
        """
        Retrieves the servlet matching the given path and its parameters.
        Returns None if no servlet matches the given path.
        
        :param path: A request URI
        :return: A tuple (servlet, parameters) or None
        """
        if not path or path[0] != "/":
            # No path, nothing to return
            return None

        # Use lower case for comparison
        path = path.lower()

        with self._lock:
            longest_match = ""
            for servlet_path in self._servlets.keys():
                if path.startswith(servlet_path):
                    # Found a corresponding servlet
                    if len(servlet_path) > len(longest_match):
                        # And its deeper than the previous one
                        longest_match = servlet_path

            # Return the found servlet
            if not longest_match:
                # No match found
                return None

            else:
                # Retrieve the stored information
                return self._servlets[longest_match]


    def register_servlet(self, path, servlet, parameters=None):
        """
        Registers a servlet
        
        :param path: Path handled by this servlet
        :param servlet: The servlet instance
        :param parameters: The parameters associated to this path
        :return: True if the servlet has been registered, False if it refused
                 the binding.
        :raise ValueError: Invalid path or handler
        """
        if servlet is None:
            raise ValueError("Invalid servlet instance")

        if not path or path[0] != '/':
            raise ValueError("Invalid path given to register the servlet: {0}" \
                             .format(path))

        # Use lower-case paths
        path = path.lower()

        # Prepare the parameters
        if parameters is None:
            parameters = {}

        parameters['http.address'] = self._address
        parameters['http.port'] = self._port

        with self._lock:
            if path in self._servlets:
                # Already registered path
                if self._servlets[path][0] is servlet:
                    # Nothing to do
                    return True

                else:
                    raise ValueError("A servlet is already registered on {0}" \
                                     .format(path))

            # Call back the method
            if self.__safe_callback(servlet, "bound_to", path, parameters):
                # Store the servlet
                self._servlets[path] = (servlet, parameters)
                return True

            return False


    def unregister(self, path, servlet=None):
        """
        Unregisters the servlet for the given path
        
        :param path: The path to a servlet
        :param servlet: If given, unregisters all the paths handled by this
                        servlet
        
        :return: True if at least one path as been unregistered, else False
        """
        if servlet is not None:
            with self._lock:
                # Unregister all paths for this servlet
                paths = [path
                         for (path, servlet_info) in self._servlets.items()
                         if servlet_info[0] == servlet]

            result = False
            for path in paths:
                result |= self.unregister(path)

            return result

        else:
            if not path:
                # Invalid path
                return False

            # Always use lower case to compare paths
            path = path.lower()

            with self._lock:
                # Notify the servlet
                servlet_info = self._servlets.get(path, None)
                if servlet_info is None:
                    # Unknown path
                    return False

                self.__safe_callback(servlet_info[0], "unbound_from",
                                     path, servlet_info[1])

                # Remove the servlet
                del self._servlets[path]
                return True


    def log(self, level, message, *args, **kwargs):
        """
        Logs the given message
        
        :param level: Log entry level
        :param message: Log message (Python logging format)
        """
        if self._logger is not None:
            # Log the message
            self._logger.log(level, message, *args, **kwargs)


    def log_exception(self, message, *args, **kwargs):
        """
        Logs an exception
        
        :param message: Log message (Python logging format)
        """
        if self._logger is not None:
            # Log the exception
            self._logger.exception(message, *args, **kwargs)


    @Validate
    def validate(self, context):
        """
        Component validation
        """
        if not self._address:
            # Local host by default
            self._address = "localhost"

        if self._port is None or self._port < 0:
            # Random port
            self._port = 0

        else:
            # Ensure we have an integer
            self._port = int(self._port)

        # Set up the logger
        if self._logger_name is not None:
            if not self._logger:
                # Empty name, use the instance name
                self._logger_name = self._instance_name

            self._logger = logging.getLogger(self._logger_name)
            self._logger.level = int(self._logger_level)

        self.log(logging.INFO, "Starting HTTP server: [%s]:%d ...",
                 self._address, self._port)

        # Create the server
        self._server = _HttpServerFamily((self._address, self._port),
                                         lambda *x: _RequestHandler(self, *x),
                                         self._logger)

        # Property update (if port was 0)
        self._port = self._server.socket.getsockname()[1]

        # Run it in a separate thread
        self._thread = threading.Thread(target=self._server.serve_forever)
        self._thread.daemon = True
        self._thread.start()

        self.log(logging.INFO, "HTTP server started: [%s]:%d ...",
                 self._address, self._port)


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidation
        """
        self.log(logging.INFO, "Shutting down HTTP server: [%s]:%d ...",
                 self._address, self._port)

        # Shutdown server
        self._server.shutdown()

        # Wait for the thread to stop...
        self.log(logging.INFO,
                 "Waiting HTTP server ([%s]:%d) thread to stop...",
                 self._address, self._port)
        self._thread.join(2)

        # Close the server
        self._server.server_close()

        self.log(logging.INFO, "HTTP server down: [%s]:%d ...",
                 self._address, self._port)

        # Clean up
        self._servlets.clear()
        self._thread = None
        self._server = None
        self._logger = None
