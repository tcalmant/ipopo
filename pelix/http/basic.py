#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix basic HTTP service bundle.

Provides an implementation of the Pelix HTTP service based on the standard
Python library.

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

# Standard library
import logging
import socket
import threading
import traceback

# Basic HTTP server
try:
    # Python 3
    # pylint: disable=F0401,E0611
    from http.server import HTTPServer
    from http.server import BaseHTTPRequestHandler
    from socketserver import ThreadingMixIn, TCPServer
except ImportError:
    # Python 2 or IronPython
    # pylint: disable=F0401
    from BaseHTTPServer import HTTPServer
    from BaseHTTPServer import BaseHTTPRequestHandler
    from SocketServer import ThreadingMixIn, TCPServer

# iPOPO
from pelix.ipopo.decorators import (
    ComponentFactory,
    Provides,
    Requires,
    Validate,
    Invalidate,
    Property,
    HiddenProperty,
    BindField,
    UpdateField,
    UnbindField,
)
import pelix.ipopo.constants as constants
import pelix.ipv6utils
import pelix.utilities as utilities
import pelix.misc.ssl_wrap as ssl_wrap
import pelix.remote

# HTTP service constants
import pelix.http as http

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
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

# ------------------------------------------------------------------------------


class _HTTPServletRequest(http.AbstractHTTPServletRequest):
    """
    HTTP Servlet request helper
    """

    def __init__(self, request_handler, prefix):
        """
        Sets up the request helper

        :param request_handler: The basic request handler
        :param prefix: Teh path to the servlet root
        """
        self._handler = request_handler
        self._prefix = prefix

        # Compute the sub path
        self._sub_path = self._handler.path[len(prefix) :]
        if not self._sub_path.startswith("/"):
            self._sub_path = "/{0}".format(self._sub_path)

        while "//" in self._sub_path:
            self._sub_path = self._sub_path.replace("//", "/")

    def get_command(self):
        """
        Returns the HTTP verb (GET, POST, ...) used for the request
        """
        return self._handler.command

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

    def get_prefix_path(self):
        """
        Returns the path to the servlet root

        :return: A request path (string)
        """
        return self._prefix

    def get_sub_path(self):
        """
        Returns the servlet-relative path, i.e. after the prefix

        :return: A request path (string)
        """
        return self._sub_path

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
        self._headers = {}

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
        self._headers[name.lower()] = value

    def is_header_set(self, name):
        """
        Checks if the given header has already been set

        :param name: Header name
        :return: True if it has already been set
        """
        return name.lower() in self._headers

    def end_headers(self):
        """
        Ends the headers part
        """
        # Send them all at once
        for name, value in self._headers.items():
            self._handler.send_header(name, value)

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


class _RequestHandler(BaseHTTPRequestHandler, object):
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

        # Remove the query part and double-slashes in the request path
        parsed_path = self.path.split("?", 1)[0].replace("//", "/")

        # Get the corresponding servlet
        found_servlet = self._service.get_servlet(parsed_path)
        if found_servlet is not None:
            servlet, _, prefix = found_servlet
            if hasattr(servlet, name):
                # Prepare the helpers
                request = _HTTPServletRequest(self, prefix)
                response = _HTTPServletResponse(self)

                # Create a wrapper to pass the handler to the servlet
                def wrapper():
                    """
                    Wrapped servlet call
                    """
                    try:
                        # Handle the request
                        return getattr(servlet, name)(request, response)
                    except:
                        # Send a 500 error page on error
                        return self.send_exception(response)

                # Return it
                return wrapper

        # Return the super implementation if needed
        return self.send_no_servlet_response

    def log_error(self, message, *args, **kwargs):
        # pylint: disable=W0221
        """
        Log server error
        """
        self._service.log(logging.ERROR, message, *args, **kwargs)

    def log_request(self, code="-", size="-"):
        """
        Logs a request to the server
        """
        self._service.log(logging.DEBUG, '"%s" %s', self.requestline, code)

    def send_no_servlet_response(self):
        """
        Default response sent when no servlet is found for the requested path
        """
        # Use the helper to send the error page
        response = _HTTPServletResponse(self)
        response.send_content(404, self._service.make_not_found_page(self.path))

    def send_exception(self, response):
        """
        Sends an exception page with a 500 error code.
        Must be called from inside the exception handling block.

        :param response: The response handler
        """
        # Get a formatted stack trace
        stack = traceback.format_exc()

        # Log the error
        self.log_error(
            "Error handling request upon: %s\n%s\n", self.path, stack
        )

        # Send the page
        response.send_content(
            500, self._service.make_exception_page(self.path, stack)
        )


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
        server_address,
        request_handler_class,
        request_queue_size=5,
        logger=None,
    ):
        """
        Proxy constructor

        :param server_address: The server address
        :param request_handler_class: The request handler class
        :param request_queue_size: The size of the request queue
                                   (clients waiting for treatment)
        :param logger: An optional logger, in case of ignored error
        """
        # Determine the address family
        addr_info = socket.getaddrinfo(
            server_address[0], server_address[1], 0, 0, socket.SOL_TCP
        )

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
            except AttributeError as ex:
                if logger is not None:
                    logger.exception("System misses IPv6 constant: %s", ex)
            except socket.error as ex:
                if logger is not None:
                    logger.exception(
                        "Error setting up IPv6 double stack: %s", ex
                    )

        # Bind & accept
        self.server_bind()
        self.server_activate()

    def server_bind(self):
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

    def process_request(self, request, client_address):
        """
        Starts a new thread to process the request, adding the client address
        in its name.
        """
        thread = threading.Thread(
            name="HttpService-{0}-Client-{1}".format(
                self.server_port, client_address
            ),
            target=self.process_request_thread,
            args=(request, client_address),
        )
        thread.daemon = self.daemon_threads
        thread.start()


# ------------------------------------------------------------------------------


@ComponentFactory(http.FACTORY_HTTP_BASIC)
@Provides(http.HTTP_SERVICE)
@Requires("_servlets_services", http.HTTP_SERVLET, True, True)
@Requires("_error_handler", http.HTTP_ERROR_PAGES, optional=True)
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
@Property("_request_queue_size", "pelix.http.request_queue_size", 100)
class HttpService(object):
    """
    Basic HTTP service component
    """

    def __init__(self):
        # Properties
        self._address = "0.0.0.0"
        self._port = 8080
        self._uses_ssl = False
        self._extra = None
        self._instance_name = None
        self._logger_name = None
        self._logger_level = None
        self._request_queue_size = 5

        # SSL Parameters
        self._cert_file = None
        self._key_file = None
        self._key_password = None

        # Validation flag
        self._validated = False

        # The logger
        self._logger = None

        # Servlets registry lock
        self._lock = threading.Lock()

        # Path -> (servlet, parameters)
        self._servlets = {}

        # Fields injected by iPOPO
        self._servlets_services = None
        self._error_handler = None

        # Servlet -> ServiceReference
        self._servlets_refs = {}
        self._binding_lock = threading.Lock()

        # Server control
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

    def __register_servlet_service(self, service, service_reference):
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
    def _bind(self, _, service, service_reference):
        """
        Called by iPOPO when a service is bound
        """
        # Ignore imported services
        if self.__is_imported(service_reference):
            return
        with self._binding_lock:
            self._servlets_refs[service] = service_reference

            if self._validated:
                # We've been validated, register the service
                self.__register_servlet_service(service, service_reference)

    @UpdateField("_servlets_services")
    def _update(self, _, service, service_reference, old_properties):
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
    def _unbind(self, _, service, service_reference):
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
            del self._servlets_refs[service]

    def get_access(self):
        """
        Retrieves the (address, port) tuple to access the server
        """
        sock_info = self._server.socket.getsockname()

        # Only keep the address and the port information
        return sock_info[0], sock_info[1]

    @staticmethod
    def get_hostname():
        """
        Retrieves the server host name

        :return: The server host name
        """
        return socket.gethostname()

    def is_https(self):
        """
        Returns True if this is an HTTPS server

        :return: True if this server uses SSL
        """
        return self._uses_ssl

    def get_registered_paths(self):
        """
        Returns the paths registered by servlets

        :return: The paths registered by servlets (sorted list)
        """
        return sorted(self._servlets)

    def get_servlet(self, path):
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

                if (
                    path.startswith(tested_path)
                    and len(servlet_path) > longest_match_len
                ):
                    # Found a corresponding servlet
                    # which is deeper than the previous one
                    longest_match = servlet_path
                    longest_match_len = len(servlet_path)

            # Return the found servlet
            if not longest_match:
                # No match found
                return None

            # Retrieve the stored information
            return tuple(self._servlets[longest_match]) + (longest_match,)

    def make_not_found_page(self, path):
        """
        Prepares a "page not found" page for a 404 error

        :param path: Request path
        :return: A HTML page
        """
        page = None
        if self._error_handler is not None:
            page = self._error_handler.make_not_found_page(path)

        if not page:
            page = """<html>
<head>
<title>404 - Page not found</title>
</head>
<body>
<h1>Page not found</h1>
<p>No servlet is associated to this path:</p>
<pre>{0}</pre>
<h2>Registered paths:</h2>
{1}
</body>
</html>""".format(
                path, http.make_html_list(self.get_registered_paths())
            )

        return page

    def make_exception_page(self, path, stack):
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
            page = """<html>
<head>
<title>500 - Internal Server Error</title>
</head>
<body>
<h1>Internal Server Error</h1>
<p>Error handling request upon: {0}</p>
<pre>
{1}
</pre>
</body>
</html>""".format(
                path, stack
            )

        return page

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

        if not path or path[0] != "/":
            raise ValueError(
                "Invalid path given to register the servlet: {0}".format(path)
            )

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
            parameters[http.PARAM_EXTRA] = self._extra.copy()

            # The servlet might refuse to be bound to this server
            if not self.__safe_callback(
                servlet, "accept_binding", path, parameters
            ):
                # Server refused: stop right there
                # => No need to raise the "already taken path" exception
                return False

            if already_taken:
                # The path is already taken by another servlet
                raise ValueError(
                    "A servlet is already registered on {0}".format(path)
                )

            # Tell the servlet it can be bound to the path
            if self.__safe_callback(servlet, "bound_to", path, parameters):
                # Store the servlet
                self._servlets[path] = (servlet, parameters)
                return True

            # The servlet refused the binding
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

                self.__safe_callback(
                    servlet_info[0], "unbound_from", path, servlet_info[1]
                )

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
    def validate(self, _):
        """
        Component validation
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

        # Normalize the request queue size
        try:
            self._request_queue_size = int(self._request_queue_size)
        except (ValueError, TypeError):
            self._request_queue_size = 5

        if self._request_queue_size <= 0:
            self._request_queue_size = 5

        # Normalize the extra properties
        if not isinstance(self._extra, dict):
            self._extra = {}

        # Set up the logger
        if self._logger_name is not None:
            if not self._logger:
                # Empty name, use the instance name
                self._logger_name = self._instance_name

            self._logger = logging.getLogger(self._logger_name)

            if self._logger_level is None:
                self._logger.level = logging.INFO
            else:
                self._logger.level = int(self._logger_level)

        self.log(
            logging.INFO,
            "Starting HTTP%s server: [%s]:%d ...",
            "S" if self._uses_ssl else "",
            self._address,
            self._port,
        )

        # Create the server
        self._server = _HttpServerFamily(
            (self._address, self._port),
            lambda *x: _RequestHandler(self, *x),
            self._request_queue_size,
            self._logger,
        )

        if self._uses_ssl:
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
            name="HttpService-{0}-Server".format(self._port),
        )
        self._thread.daemon = True
        self._thread.start()

        with self._binding_lock:
            # Set the validation flag up, once the server is ready
            self._validated = True

            # Register bound servlets
            for service, svc_ref in self._servlets_refs.items():
                self.__register_servlet_service(service, svc_ref)

        self.log(
            logging.INFO,
            "HTTP%s server started: [%s]:%d",
            "S" if self._uses_ssl else "",
            self._address,
            self._port,
        )

    @Invalidate
    def invalidate(self, _):
        """
        Component invalidation
        """
        with self._binding_lock:
            # Refuse new registrations
            self._validated = False

            # Unregister servlets (to call unbound_from...)
            for service in self._servlets_refs:
                self.unregister(None, service)

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
        self._logger = None

    @staticmethod
    def __is_imported(service_reference):
        """
        Tests if the given service has been imported by Remote Services

        :param service_reference: The reference of the service to check
        :return: True if the service is flagged as imported
        """
        return service_reference.get_property(pelix.remote.PROP_IMPORTED)
