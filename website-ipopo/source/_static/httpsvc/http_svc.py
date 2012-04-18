#!/usr/bin/python
#-- Content-Encoding: UTF-8 --
"""
HTTP Service bundle for Pelix / iPOPO

:author: Thomas Calmant
:license: GPLv3
"""

import socket
import sys
import threading

import logging
_logger = logging.getLogger("HTTP Service")

# ------------------------------------------------------------------------------

# Let the module work with Python 2 and 3
if sys.version_info[0] == 3:
    # Python 3
    import urllib.parse as urlparse
    from http.server import HTTPServer
    from http.server import BaseHTTPRequestHandler

    def to_bytes(string):
        """
        Converts the given string to bytes
        
        :param string: String to be converted
        :return: Bytes
        """
        return string.decode('UTF-8')

else:
    # Python 2
    import urlparse
    from BaseHTTPServer import HTTPServer
    from BaseHTTPServer import BaseHTTPRequestHandler

    def to_bytes(string):
        """
        Converts the given string to bytes
        
        :param string: String to be converted
        :return: Bytes
        """
        return string

# ------------------------------------------------------------------------------

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Provides, Validate, \
    Invalidate, Property, Instantiate, Requires, Bind, Unbind

# Pelix framework
import pelix.framework

# ------------------------------------------------------------------------------

class RequestHandler(BaseHTTPRequestHandler):
    """
    HTTP Service : Request handler
    
    Implementation of the request handler for the HTTP Service
    """
    def __init__(self, http_svc, *args, **kwargs):
        """
        Constructor
        
        :param http_svc: The associated HTTP service instance
        """
        # Store the reference to the service
        self.service = http_svc

        # Call the parent constructor
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)


    def send_data(self, data, code=200, type="text/html", raw=False):
        """
        Sends the given data to the client
        
        :param data: Response content
        :param code: HTTP response code
        :param type: HTTP content type
        :param raw: If False, data will be converted to bytes, on Python 3
        """
        if not raw:
            data = to_bytes(data)

        # Send headers
        self.send_response(code)
        self.send_header("content-type", type)
        self.send_header("content-length", len(data))
        self.end_headers()

        # Send content
        self.wfile.write(data)


    def send_default_response(self):
        """
        Default response sent when no servlet is found : a 404 page
        """
        # Set page content
        page = """<html>
<head>
<title>404 - Page not found</title>
</head>
<body>
<h1>No servlet associated to this path</h1>
<p>Path: <pre>{path}</pre></p>
</body>
</html>""".format(path=self.path)

        # Convert the page content to bytes and send it
        self.send_data(page, 404)


    def send_exception(self, exception):
        """
        Sends a 500 error to the client, with the trace in the page content
        
        :param exception: The raised exception
        """
        # Import traceback
        import traceback

        # Set page content
        page = """<html>
<head>
<title>500 - Error retrieving page</title>
</head>
<body>
<h1>Exception treating request to {path}</h1>
<p>Exception : {type}</p>
<p>{trace}</p>
</body>
</html>""".format(path=self.path, type=type(exception).__name__,
                  trace=traceback.format_tb(exception.__traceback__))

        # Convert the page content to bytes and send it
        self.send_data(page, 500)



    def __getattr__(self, name):
        """
        Get attribute (used by parent class to find do_METHOD methods
        
        :param name: Requested member name
        """
        if not name.startswith("do_"):
            # Not a request handling method, use default behavior
            return object.__getattr__(self, name)

        # Parse the URL
        parsed_url = urlparse.urlparse(self.path)
        parsed_path = parsed_url.path

        # Ensure we have a trailing slash
        if parsed_path[0] != '/':
            parsed_path = "/%s" % parsed_path

        # Ask for the service to find us the corresponding servlet
        servlet = self.service.get_servlet(parsed_path)

        if servlet is None:
            # No servlet associated to this path : return the default response
            # sender
            return self.send_default_response

        # Try to use the servlet
        try:
            if not hasattr(servlet, name):
                # The servlet doesn't handle this kind of access,
                # use our default one (i.e. parent one)
                return getattr(self, name)

            # Create a wrapper to pass the handler to the servlet
            def wrapper():
                return getattr(servlet, name)(self)

            # Return it
            return wrapper

        except Exception as ex:
            # Something bad occurred, tell the client using a wrapped method
            def wrapper():
                return self.send_exception(ex)

            return wrapper

# ------------------------------------------------------------------------------

# Declare the component factory
@ComponentFactory(name="HttpServiceFactory")
# We want it to be instantiated immediately
@Instantiate(name="HttpService")
# Declare the provided specifications
@Provides(specifications="demo.HttpService")
# Declare the http.port property and its default value
@Property("port", "http.port", 8080)
# The component wants servlets with a valid path to be injected directly
@Requires("__servlets_svc", "demo.HttpServlet", aggregate=True, optional=True,
          spec_filter="(servlet.path=/*)")
class HTTPComponent(object):
    """
    The HTTP component, providing a HTTP service
    """
    def __init__(self):
        """
        Set up members
        """
        self.port = 0

        # Path -> Servlet service
        self.servlets = {}

        # Servlet dictionary lock
        self.servlets_lock = threading.Lock()


    def get_hostname(self):
        """
        Retrieves the server host name
        
        :return: The host name
        """
        return socket.gethostname()


    def get_port(self):
        """
        Retrieves the port that this server listens to
        
        :return: The port this server listens to
        """
        return self.port


    def get_servlet(self, path):
        """
        Retrieves the servlet associated to the given path, or None
        
        :param path: The requested path
        :return: The corresponding servlet, or None
        """
        found_path = ""
        len_found_path = len(found_path)
        found_svc = None

        with self.servlets_lock:
            for reg_path in self.servlets:
                if len(reg_path) > len_found_path and path.startswith(reg_path):
                    # A longer matching path has been found
                    found_path = reg_path
                    len_found_path = len(found_path)
                    found_svc = self.servlets[found_path]

        return found_svc


    @Bind
    def bind(self, service, reference):
        """
        A dependency has been injected
        
        :param service: The injected service
        :param reference: The associated ServiceReference
        """
        # Only take care of servlets
        specifications = reference.get_property(pelix.framework.OBJECTCLASS)
        if "demo.HttpServlet" not in specifications:
            # Ignore
            return

        # Test if the path has already been taken 
        path = reference.get_property("servlet.path")

        with self.servlets_lock:
            if path in self.servlets:
                # Raise an error, it will be logged
                raise ValueError("Path already taken : {path}".format(path=path))

            # Store the servlet
            self.servlets[path] = service

            _logger.info("HTTP Servlet bound to %s", path)


    @Unbind
    def unbind(self, service):
        """
        A dependency has gone
        
        :param service: The removed service instance
        """
        # Compute keys to be removed
        paths = [path for path in self.servlets
                 if service is self.servlets[path]]

        with self.servlets_lock:
            # Remove  all paths for this service
            for path in paths:
                del self.servlets[path]


    @Validate
    def validate(self, context):
        """
        Component validation
        
        :param context: The bundle context
        """
        # Set up the HTTP server, associating all request handlers with this
        # instance
        self.server = HTTPServer(('', self.port), \
                                 lambda * x : RequestHandler(self, *x))

        # Start to serve clients
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        _logger.info("HTTP service listening on http://localhost:%d/",
                     self.port)


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidation
        
        :param context: The bundle context
        """
        # Shutdown connections
        self.server.socket.shutdown(socket.SHUT_RDWR)

        # Force the socket to be closed (may raise an error)
        self.server.socket.close()

        _logger.info("HTTP Service gone (port %d)", self.port)
