#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix HTTP routing test module.

:author: Thomas Calmant
"""

try:
    import unittest2 as unittest
except ImportError:
    import unittest

try:
    # Python 3
    import http.client as httplib
except (ImportError, AttributeError):
    # Python 2 or IronPython
    import httplib

# Pelix
from pelix.framework import create_framework, FrameworkFactory
from pelix.utilities import to_str

# HTTP service constants
import pelix.http.routing as routing

# Utilities
from tests.http.test_basic import install_ipopo, instantiate_server, \
    get_http_page

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080

HTTP_METHODS = ("GET", "HEAD", "POST", "PUT", "DELETE")

# ------------------------------------------------------------------------------


class HttpRountingTests(unittest.TestCase):
    """
    Tests of the HTTP routing class
    """
    def setUp(self):
        """
        Sets up the test environment
        """
        # Start a framework
        self.framework = create_framework(['pelix.http.basic'])
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.http = instantiate_server(self.ipopo)

    def tearDown(self):
        """
        Cleans up the test environment
        """
        # Stop the framework
        FrameworkFactory.delete_framework(self.framework)
        self.framework = None

    def test_empty(self):
        """
        Tests the routing mother class with no routing
        """
        # Register the router as a servlet
        router = routing.RestDispatcher()
        self.http.register_servlet("/routing", router)

        for method in HTTP_METHODS:
            code = get_http_page(uri="/routing/", method=method)
            # Ensure 404 (not 500)
            self.assertEqual(code, 404)

    def test_dispatch(self):
        """
        Tests the dispatcher
        """
        class Servlet(routing.RestDispatcher):
            def __init__(self):
                super(Servlet, self).__init__()
                self.called_path = None

            def reset(self):
                self.called_path = None

            @routing.HttpGet("")
            def test_no_path(self, request, response):
                self.called_path = request.get_sub_path()
                response.send_content(300, "Should not happen")

            @routing.HttpGet("/")
            def test_route(self, request, response):
                self.called_path = request.get_sub_path()
                response.send_content(200, "OK")

            @routing.HttpGet("/test")
            def test_basic(self, request, response):
                self.called_path = request.get_sub_path()
                response.send_content(200, "OK")

            @routing.HttpGet("/test/a")
            def test_sub_a(self, request, response):
                self.called_path = request.get_sub_path()
                response.send_content(200, "OK")

            @routing.HttpGet("/test/b")
            def test_sub_b(self, request, response):
                self.called_path = request.get_sub_path()
                response.send_content(200, "OK")

        router = Servlet()
        self.http.register_servlet("/routing", router)

        # No path
        code = get_http_page(uri="/")
        self.assertEqual(code, 404)

        # Route path
        for path in ("", "/", "/test", "/test/a", "/test/b"):
            router.reset()
            code, data = get_http_page(uri="/routing{0}".format(path),
                                       only_code=False)
            self.assertEqual(code, 200)
            self.assertEqual(to_str(data), "OK")
            self.assertEqual(router.called_path, path or "/")


    def test_methods(self):
        """
        Tests the methods filters
        """

    def test_types(self):
        """
        Tests the type parsing by the dispatcher
        """

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
