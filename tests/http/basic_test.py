#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix basic HTTP service test module.

:author: Thomas Calmant
"""
from pelix.framework import FrameworkFactory, BundleContext
from tests import log_on, log_off

import pelix.ipopo.constants as constants
import pelix.framework as pelix
import os
import logging
import sys
import threading
import time

try:
    import unittest2 as unittest

except ImportError:
    import unittest
    import tests
    tests.inject_unittest_methods()


if sys.version_info[0] == 3:
    import http.client as httplib

else:
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

    bid = context.install_bundle(bundle_name)
    bundle = context.get_bundle(bid)
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
    bid = context.install_bundle("pelix.ipopo.core")
    bundle = context.get_bundle(bid)
    bundle.start()

    # Get the service
    ref = context.get_service_reference(constants.IPOPO_SERVICE_SPECIFICATION)
    if ref is None:
        raise Exception("iPOPO Service not found")

    return context.get_service(ref)


def instantiate_server(ipopo_svc, module,
                       address=DEFAULT_HOST, port=DEFAULT_PORT):
    """
    Instantiates a basic server component
    """
    return ipopo_svc.instantiate(module.HTTP_SERVICE_COMPONENT_FACTORY,
                                 "test-http-service",
                                 {http.HTTP_SERVICE_ADDRESS: address,
                                  http.HTTP_SERVICE_PORT: port})


def get_http_page(host=DEFAULT_HOST, port=DEFAULT_PORT,
                  uri="/", method="GET", headers={}, content=None,
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
    conn.request(method, uri, content, headers)
    result = conn.getresponse()
    data = result.read()
    conn.close()

    if only_code:
        return result.status

    return result.status, data

# ------------------------------------------------------------------------------

class SimpleServlet(object):
    """
    A simple servlet implementation
    """
    def __init__(self, raiser=False):
        """
        Sets up the servlet
        
        :param raiser: If True, the servlet will raise an exception on bound_to
        """
        self.raiser = raiser
        self.bound = []
        self.unbound = []


    def reset(self):
        """
        Resets the servlet data
        """
        del self.bound[:]
        del self.unbound[:]


    def bound_to(self, path, params):
        """
        Servlet bound to a path
        """
        self.bound.append(path)

        if self.raiser:
            raise Exception("Some exception")


    def unbound_from(self, path, params):
        """
        Servlet unbound from a path
        """
        self.unbound.append(path)

        if self.raiser:
            raise Exception("Some exception")


    def do_GET(self, request, response):
        """
        Handle a GET
        """
        content = """<html>
<head>
<title>Test SimpleServlet</title>
</head>
<body>
<ul>
<li>Client address: {clt_addr[0]}</li>
<li>Client port: {clt_addr[1]}</li>
<li>Host: {host}</li>
<li>Keys: {keys}</li>
</ul>
</body>
</html>""".format(clt_addr=request.get_client_address(),
                  host=request.get_header('host', 0),
                  keys=request.get_headers().keys())

        response.send_content(200, content)


    def do_POST(self, request, response):
        """
        Handle a GET
        """
        response.send_content(201, "Success")


# ------------------------------------------------------------------------------

class BasicHTTPServiceTest(unittest.TestCase):
    """
    Tests of the basic HTTP service
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
        self.basic_bundle = install_bundle(self.framework, "pelix.http.basic")


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
        http_svc = instantiate_server(self.ipopo, self.basic_bundle)
        self.assertEqual(get_http_page(only_code=True), 404,
                         "Received something other than a 404")


    def testRegisteredServlet(self):
        """
        Tests the registration of a servlet object
        """
        http_svc = instantiate_server(self.ipopo, self.basic_bundle)

        # Register the servlet
        servlet = SimpleServlet()
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


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
