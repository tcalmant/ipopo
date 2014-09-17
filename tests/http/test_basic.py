#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix basic HTTP service test module.

:author: Thomas Calmant
"""

from pelix.framework import FrameworkFactory, BundleContext
from tests import log_on, log_off

import pelix.ipopo.constants as constants
import logging

try:
    import unittest2 as unittest
except ImportError:
    import unittest

try:
    # Python 3
    import http.client as httplib

except ImportError:
    # Python 2
    import httplib

# HTTP service constants
import pelix.http as http

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8080

# ------------------------------------------------------------------------------


def install_bundle(framework, bundle_name="tests.ipopo_bundle"):
    """
    Installs and starts the test bundle and returns its module

    :param framework: A Pelix framework instance
    :param bundle_name: A bundle name
    :return: The installed bundle Python module
    """
    context = framework.get_bundle_context()

    bundle = context.install_bundle(bundle_name)
    bundle.start()

    return bundle.get_module()


def install_ipopo(framework):
    """
    Installs and starts the iPOPO bundle. Returns the iPOPO service

    :param framework: A Pelix framework instance
    :return: The iPOPO service
    :raise Exception: The iPOPO service cannot be found
    """
    context = framework.get_bundle_context()
    assert isinstance(context, BundleContext)

    # Install & start the bundle
    bundle = context.install_bundle("pelix.ipopo.core")
    bundle.start()

    # Get the service
    ref = context.get_service_reference(constants.SERVICE_IPOPO)
    if ref is None:
        raise Exception("iPOPO Service not found")

    return context.get_service(ref)


def instantiate_server(ipopo_svc, module,
                       address=DEFAULT_HOST, port=DEFAULT_PORT):
    """
    Instantiates a basic server component
    """
    return ipopo_svc.instantiate(http.FACTORY_HTTP_BASIC,
                                 "test-http-service",
                                 {http.HTTP_SERVICE_ADDRESS: address,
                                  http.HTTP_SERVICE_PORT: port})


def kill_server(ipopo_svc):
    """
    Kills the basic server component
    """
    ipopo_svc.kill("test-http-service")


def get_http_page(host=DEFAULT_HOST, port=DEFAULT_PORT,
                  uri="/", method="GET", headers=None, content=None,
                  only_code=True):
    """
    Retrieves the result of an HTTP request

    :param host: Server host name
    :param port: Server port
    :param uri: Request URI
    :param method: Request HTTP method (GET, POST, ...)
    :param headers: Request headers
    :param content: POST request content
    :param only_code: If True, only the code is returned
    :return: A (code, content) tuple
    """
    conn = httplib.HTTPConnection(host, port)
    conn.request(method, uri, content, headers or {})
    result = conn.getresponse()
    data = result.read()
    conn.close()

    if only_code:
        return result.status

    return result.status, data

# ------------------------------------------------------------------------------


class BasicHTTPServiceServletsTest(unittest.TestCase):
    """
    Tests of the basic HTTP service servlets handling
    """
    def setUp(self):
        """
        Sets up the test environment
        """
        # Start a framework
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

        # Install iPOPO
        self.ipopo = install_ipopo(self.framework)

        # Install HTTP service
        self.http_bundle = install_bundle(self.framework, "pelix.http.basic")

        # Install test bundle
        self.servlets = install_bundle(self.framework,
                                       "tests.http.servlets_bundle")

    def tearDown(self):
        """
        Cleans up the test environment
        """
        # Stop the framework
        FrameworkFactory.delete_framework(self.framework)
        self.framework = None

    def testBlank(self):
        """
        Tests the server when no servlet is active
        """
        instantiate_server(self.ipopo, self.http_bundle)
        self.assertEqual(get_http_page(only_code=True), 404,
                         "Received something other than a 404")

    def testRegisteredServlet(self):
        """
        Tests the registration of a servlet object
        """
        http_svc = instantiate_server(self.ipopo, self.http_bundle)

        # Register the servlet
        servlet = self.servlets.SimpleServlet()
        self.assertTrue(http_svc.register_servlet("/test", servlet),
                        "Servlet not registered")

        # Test the call back
        self.assertEqual(["/test"], servlet.bound, "bound_to not called")
        self.assertEqual([], servlet.unbound, "unbound_from called")
        servlet.reset()

        # Test information
        self.assertIs(http_svc.get_servlet("/test")[0], servlet,
                      "get_servlet() didn't return the servlet")
        self.assertIs(http_svc.get_servlet("/test/Toto")[0], servlet,
                      "get_servlet() didn't return the servlet")
        self.assertIsNone(http_svc.get_servlet("/"),
                          "Root is associated to a servlet")
        self.assertIsNone(http_svc.get_servlet("/tes"),
                          "Incomplete path is associated to a servlet")

        # Test access to /
        self.assertEqual(get_http_page(uri="/", only_code=True), 404,
                         "Received something other than a 404")

        # Test access to /test
        self.assertEqual(get_http_page(uri="/test", method="GET",
                                       only_code=True), 200,
                         "Servlet not registered ?")
        self.assertEqual(get_http_page(uri="/test", method="POST",
                                       only_code=True), 201,
                         "Servlet not registered ?")
        self.assertEqual(get_http_page(uri="/test", method="PUT",
                                       only_code=True), 404,
                         "Unwanted answer")

        # Sub path
        self.assertEqual(get_http_page(uri="/test/toto", method="GET",
                                       only_code=True), 200,
                         "Servlet not registered ?")

        # Unregister the servlet
        http_svc.unregister("/test")

        # Test the call back
        self.assertEqual(["/test"], servlet.unbound, "unbound_from not called")
        self.assertEqual([], servlet.bound, "bound_to called")
        servlet.reset()

        # Test access to /
        self.assertEqual(get_http_page(uri="/", only_code=True), 404,
                         "Received something other than a 404")

        # Test access to /test
        self.assertEqual(get_http_page(uri="/test", method="POST",
                                       only_code=True), 404,
                         "Servlet still registered")

        # Sub path
        self.assertEqual(get_http_page(uri="/test/toto", method="GET",
                                       only_code=True), 404,
                         "Servlet still registered")

    def testBindingRaiser(self):
        """
        Tests the behavior of the HTTP service when a bound_to() method raises
        an exception
        """
        http_svc = instantiate_server(self.ipopo, self.http_bundle)

        # Make the servlet raise an exception
        servlet = self.servlets.SimpleServlet(True)

        # Register the servlet
        log_off()
        self.assertFalse(http_svc.register_servlet("/test", servlet),
                         "Servlet registered even raising an exception")
        log_on()

        self.assertEqual(get_http_page(uri="/test", only_code=True), 404,
                         "Servlet registered even raising an exception")

    def testUnbindingRaiser(self):
        """
        Tests the behavior of the HTTP service when a bound_to() method raises
        an exception
        """
        http_svc = instantiate_server(self.ipopo, self.http_bundle)

        # Make the servlet to not raise an exception
        servlet = self.servlets.SimpleServlet(False)

        # Register the servlet
        self.assertTrue(http_svc.register_servlet("/test", servlet),
                        "Servlet not registered")
        self.assertEqual(get_http_page(uri="/test", only_code=True), 200,
                         "Servlet not registered ?")

        # Make it raise an exception
        servlet.raiser = True

        # Unregister it (no exception should be propagated)
        log_off()
        http_svc.unregister("/test")
        log_on()

        # The servlet must have been unregistered
        self.assertEqual(get_http_page(uri="/test", only_code=True), 404,
                         "Servlet still registered")

    def testAcceptBinding(self):
        """
        Tests the behavior of the HTTP service when a bound_to() method raises
        an exception
        """
        http_svc = instantiate_server(self.ipopo, self.http_bundle)

        # Make the first servlet
        servlet = self.servlets.SimpleServlet(False)

        # Make the second servlet
        servlet_2 = self.servlets.SimpleServlet(False)

        # Register the first servlet
        self.assertTrue(http_svc.register_servlet("/test", servlet),
                        "Servlet not registered")
        self.assertEqual(get_http_page(uri="/test", only_code=True), 200,
                         "Servlet not registered ?")

        # Second registration must work
        self.assertTrue(http_svc.register_servlet("/test", servlet),
                        "Servlet not registered")

        # Try to register the second servlet, accepting the server
        servlet_2.accept = True
        self.assertRaises(ValueError, http_svc.register_servlet,
                          "/test", servlet_2)

        # Ensure that our first servlet is still there
        self.assertEqual(get_http_page(uri="/test", only_code=True), 200,
                         "Servlet not registered ?")

        # Try to register the second servlet, rejecting the server
        servlet_2.accept = False
        self.assertFalse(http_svc.register_servlet("/test", servlet_2),
                         "Non-accepted server -> must return False")

        # Ensure that our first servlet is still there
        self.assertEqual(get_http_page(uri="/test", only_code=True), 200,
                         "Servlet not registered ?")

        # Unregister it (no exception should be propagated)
        log_off()
        http_svc.unregister("/test")
        log_on()

        # The servlet must have been unregistered
        self.assertEqual(get_http_page(uri="/test", only_code=True), 404,
                         "Servlet still registered")

    def testWhiteboardPatternSimple(self):
        """
        Tests the whiteboard pattern with a simple path
        """
        http_svc = instantiate_server(self.ipopo, self.http_bundle)

        # Instantiate the servlet component
        servlet_name = "test-whiteboard-simple"
        servlet = self.ipopo.instantiate(self.servlets.SIMPLE_SERVLET_FACTORY,
                                         servlet_name,
                                         {http.HTTP_SERVLET_PATH: "/test",
                                          "raiser": False})

        # Test the call back
        self.assertEqual(["/test"], servlet.bound, "bound_to not called")
        self.assertEqual([], servlet.unbound, "unbound_from called")
        servlet.reset()

        # Test information
        self.assertIs(http_svc.get_servlet("/test")[0], servlet,
                      "get_servlet() didn't return the servlet")

        # Test access to /test
        self.assertEqual(get_http_page(uri="/test", method="GET",
                                       only_code=True), 200,
                         "Servlet not registered ?")
        self.assertEqual(get_http_page(uri="/test", method="POST",
                                       only_code=True), 201,
                         "Servlet not registered ?")
        self.assertEqual(get_http_page(uri="/test", method="PUT",
                                       only_code=True), 404,
                         "Unwanted answer")

        # Kill the component
        self.ipopo.kill(servlet_name)

        # Test the call back
        self.assertEqual(["/test"], servlet.unbound, "unbound_from not called")
        self.assertEqual([], servlet.bound, "bound_to called")
        servlet.reset()

        # Test access to /test
        self.assertEqual(get_http_page(uri="/test", method="POST",
                                       only_code=True), 404,
                         "Servlet still registered")

    def testWhiteboardPatternMultiple(self):
        """
        Tests the whiteboard pattern with a multiple paths
        """
        http_svc = instantiate_server(self.ipopo, self.http_bundle)

        # Instantiate the servlet component
        servlet_name = "test-whiteboard-multiple"
        paths = ["/test1", "/test2", "/test/1"]

        servlet = self.ipopo.instantiate(self.servlets.SIMPLE_SERVLET_FACTORY,
                                         servlet_name,
                                         {http.HTTP_SERVLET_PATH: paths,
                                          "raiser": False})

        # Test the call back
        for path in paths:
            self.assertIn(path, servlet.bound,
                          "bound_to not called for {0}".format(path))
        self.assertEqual([], servlet.unbound, "unbound_from called")
        servlet.reset()

        # Test information
        for path in paths:
            self.assertIs(http_svc.get_servlet(path)[0], servlet,
                          "get_servlet() didn't return the servlet")

        # Test access to /test
        for path in paths:
            self.assertEqual(get_http_page(uri=path, only_code=True), 200,
                             "Servlet not registered ?")

        # Kill the component
        self.ipopo.kill(servlet_name)

        # Test the call back
        for path in paths:
            self.assertIn(path, servlet.unbound,
                          "unbound_from not called for {0}".format(path))
        self.assertEqual([], servlet.bound, "bound_to called")
        servlet.reset()

        # Test access to paths
        for path in paths:
            self.assertEqual(get_http_page(uri=path, only_code=True),
                             404, "Servlet still registered")

    def testWhiteboardPatternUpdate(self):
        """
        Tests the whiteboard pattern with a simple path, which path property
        is updated
        """
        http_svc = instantiate_server(self.ipopo, self.http_bundle)

        # Instantiate the servlet component
        servlet_name = "test-whiteboard-simple"
        servlet = self.ipopo.instantiate(self.servlets.SIMPLE_SERVLET_FACTORY,
                                         servlet_name,
                                         {http.HTTP_SERVLET_PATH: "/test",
                                          "raiser": False})

        # Test the call back
        self.assertEqual(["/test"], servlet.bound, "bound_to not called")
        self.assertEqual([], servlet.unbound, "unbound_from called")
        servlet.reset()

        # Test information
        self.assertIs(http_svc.get_servlet("/test")[0], servlet,
                      "get_servlet() didn't return the servlet")

        # Test access to /test
        self.assertEqual(get_http_page(uri="/test", method="GET",
                                       only_code=True), 200,
                         "Servlet not registered ?")
        self.assertEqual(get_http_page(uri="/test-updated", method="GET",
                                       only_code=True), 404,
                         "Unwanted success")

        # Update the service property
        servlet.change('/test-updated')

        # Test the call back
        self.assertEqual(["/test-updated"], servlet.bound,
                         "bound_to not called")
        self.assertEqual(["/test"], servlet.unbound, "unbound_from not called")
        servlet.reset()

        # Test information
        self.assertIs(http_svc.get_servlet("/test-updated")[0], servlet,
                      "get_servlet() didn't return the servlet")

        # Test access to /test-updated
        self.assertEqual(get_http_page(uri="/test-updated", method="GET",
                                       only_code=True), 200,
                         "Servlet not registered ?")
        self.assertEqual(get_http_page(uri="/test", method="GET",
                                       only_code=True), 404,
                         "Unwanted answer after update")

        # Kill the component
        self.ipopo.kill(servlet_name)

        # Test the call back
        self.assertEqual(["/test-updated"], servlet.unbound,
                         "unbound_from not called")
        self.assertEqual([], servlet.bound, "bound_to called")
        servlet.reset()

        # Test access to /test-updated
        self.assertEqual(get_http_page(uri="/test-updated", method="GET",
                                       only_code=True), 404,
                         "Servlet still registered")

# ------------------------------------------------------------------------------


class BasicHTTPServiceMethodsTest(unittest.TestCase):
    """
    Tests of the basic HTTP service methods
    """
    def setUp(self):
        """
        Sets up the test environment
        """
        # Start a framework
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

        # Install iPOPO
        self.ipopo = install_ipopo(self.framework)

        # Install HTTP service
        self.http_bundle = install_bundle(self.framework, "pelix.http.basic")
        self.http_svc = instantiate_server(self.ipopo, self.http_bundle)

        # Install test bundle
        self.servlets = install_bundle(self.framework,
                                       "tests.http.servlets_bundle")

    def tearDown(self):
        """
        Cleans up the test environment
        """
        # Stop the framework
        FrameworkFactory.delete_framework(self.framework)
        self.framework = None

    def testGetServerInfo(self):
        """
        Test server information methods
        """
        # Given a valid address
        address = "127.0.0.1"
        port = 8090

        kill_server(self.ipopo)
        http_svc = instantiate_server(self.ipopo, self.http_bundle,
                                      address, port)

        import socket
        self.assertEqual(http_svc.get_hostname(), socket.gethostname(),
                         "Different host names found")

        self.assertEqual(http_svc.get_access(), (address, port),
                         "Different accesses found")

        # Given no address -> must be in a standard localhost representation
        # (depends on test system)
        localhost_names = ("localhost", "127.0.0.1", "127.0.1.1", "::1")
        kill_server(self.ipopo)
        http_svc = instantiate_server(self.ipopo, self.http_bundle,
                                      None, port)

        access = http_svc.get_access()
        self.assertIn(access[0], localhost_names, "Address is not localhost")
        self.assertEqual(access[1], port, "Different ports found")

        # Given no port -> random port
        kill_server(self.ipopo)
        http_svc = instantiate_server(self.ipopo, self.http_bundle,
                                      None, None)

        address, port = http_svc.get_access()
        self.assertEqual(get_http_page(address, port, only_code=True), 404,
                         "HTTP Service not stated with a random port")

    def testGetServlet(self):
        """
        Tests the get_servlet() method
        """
        self.assertIsNone(self.http_svc.get_servlet(None),
                          "None servlet may not exist")

        self.assertIsNone(self.http_svc.get_servlet(""),
                          "Empty path may not be handled")

        self.assertIsNone(self.http_svc.get_servlet("test"),
                          "Invalid path may not be handled")

        self.assertIsNone(self.http_svc.get_servlet("/"),
                          "Empty servlet service may return None")

        # Dummy objects
        servlet_1 = object()
        servlet_2 = object()

        # Register'em
        self.assertTrue(self.http_svc.register_servlet("/test", servlet_1))
        self.assertTrue(self.http_svc.register_servlet("/test/sub", servlet_2))

        # Test the get_servlet method
        for path in ("/test", "/test/", "/test/1"):
            self.assertIs(self.http_svc.get_servlet(path)[0], servlet_1,
                          "Servlet 1 should handle {0}".format(path))

        for path in ("/test/sub", "/test/sub/", "/test/sub/1"):
            self.assertIs(self.http_svc.get_servlet(path)[0], servlet_2,
                          "Servlet 2 should handle {0}".format(path))

    def testRegisterServlet(self):
        """
        Tests the behavior of register_servlet with dummy objects
        """
        # Dummy objects
        servlet_1 = object()
        servlet_2 = object()

        # Refuse None servlets
        self.assertRaises(ValueError, self.http_svc.register_servlet,
                          "/test", None)

        # Refuse empty paths
        for invalid in (None, "", "test"):
            self.assertRaises(ValueError, self.http_svc.register_servlet,
                              invalid, servlet_1)

        # Registration must succeed, even without calls to bound_to
        self.assertTrue(self.http_svc.register_servlet("/test", servlet_1))
        # Allow re-registration of the same object
        self.assertTrue(self.http_svc.register_servlet("/test", servlet_1))

        # Refuse overrides
        self.assertRaises(ValueError, self.http_svc.register_servlet,
                          "/test", servlet_2)
        self.assertTrue(self.http_svc.register_servlet("/test/sub", servlet_2))

    def testUnregisterServlet(self):
        """
        Tests the behavior of register_servlet with dummy objects
        """
        # Dummy object
        servlet_1 = object()

        self.http_svc.register_servlet("/test", servlet_1)

        # Try to unregister invalid/unknown paths
        for invalid in (None, "", "test", "/test/sub", "/"):
            self.assertFalse(self.http_svc.unregister(invalid),
                             "An invalid path was unregistered: {0}"
                             .format(invalid))

        # Try to unregister a None servlet
        self.assertFalse(self.http_svc.unregister(None),
                         "None can't be unregistered.")

        # Try to unregister an unknown servlet
        self.assertFalse(self.http_svc.unregister(None, object()),
                         "An unknown servlet can't be unregistered.")

# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
