#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix basic HTTP service test module.

:author: Thomas Calmant
"""

import logging
import socket
import unittest
from typing import Any, cast

from pelix import http
from pelix.framework import Framework, FrameworkFactory
from pelix.ipopo.constants import IPopoService
from tests import log_off, log_on
from tests.http.utils import (
    DEFAULT_HOST,
    SIMPLE_SERVLET_FACTORY,
    TestServlet,
    ensure_get_servlet,
    get_http_code,
    install_bundle,
    install_ipopo,
    instantiate_server,
    kill_server,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class BasicHTTPServiceServletsTest(unittest.TestCase):
    """
    Tests of the basic HTTP service servlets handling
    """

    framework: Framework
    ipopo: IPopoService

    http_bundle = "pelix.http.basic"
    http_factory: str = http.FACTORY_HTTP_BASIC
    instance_name: str = "test-http-service"
    test_servlet_factory: str = SIMPLE_SERVLET_FACTORY
    test_servlet_path_prop: str = http.HTTP_SERVLET_PATH
    test_servlet_class_name: str = "SimpleServlet"
    test_servlet_type: http.ServletType = http.ServletType.SYNC

    @classmethod
    def tearDownClass(cls):
        FrameworkFactory.delete_framework()

    def setUp(self) -> None:
        """
        Sets up the test environment
        """
        # Start a framework
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()

        # Install iPOPO
        self.ipopo = install_ipopo(self.framework)

        # Install HTTP service
        install_bundle(self.framework, self.http_bundle)

        # Install test bundle
        self.servlets = install_bundle(self.framework, "tests.http.servlets_bundle")
        self._port: int = 0

    def tearDown(self) -> None:
        """
        Cleans up the test environment
        """
        # Kill the server component
        self.kill_server()

        # Stop the framework
        FrameworkFactory.delete_framework()
        self.framework = None  # type: ignore

    def instantiate_server(self) -> http.HTTPService:
        """
        Instantiates a server component
        """
        srv = instantiate_server(self.ipopo, self.http_factory, self.instance_name, DEFAULT_HOST, 0)
        self._port = srv.get_access()[1]
        return srv

    def kill_server(self) -> None:
        """
        Kills the server component
        """
        try:
            self._port = 0
            kill_server(self.ipopo, self.instance_name)
        except:
            logging.exception("Error while killing the server component")
            raise

    def get_http_code(
        self, uri: str = "/", method: str = "GET", headers: dict[str, Any] | None = None, content: Any = None
    ) -> int:
        """
        Retrieves the status code of an HTTP request
        :param uri: Request URI
        :param method: Request HTTP method (GET, POST, ...)
        :param headers: Request headers
        :return: The HTTP status code
        """
        if self._port == 0:
            self.fail("Server not instantiated")

        return get_http_code(self._port, DEFAULT_HOST, uri, method, headers, content)

    def make_servlet(self, raiser: bool = False) -> tuple[TestServlet, http.ServletType]:
        """
        Creates a simple servlet instance
        """
        return getattr(self.servlets, self.test_servlet_class_name)(raiser), self.test_servlet_type

    def testBlank(self) -> None:
        """
        Tests the server when no servlet is active
        """
        self.instantiate_server()
        self.assertEqual(self.get_http_code(), 404, "Received something other than a 404")

    def testRegisteredServlet(self) -> None:
        """
        Tests the registration of a servlet object
        """
        http_svc = self.instantiate_server()

        # Register the servlet
        servlet, servlet_type = self.make_servlet()
        self.assertTrue(
            http_svc.register_servlet("/test", servlet, servlet_type=servlet_type), "Servlet not registered"
        )

        # Test the call back
        self.assertEqual(["/test"], servlet.bound, "bound_to not called")
        self.assertEqual([], servlet.unbound, "unbound_from called")
        servlet.reset()

        # Test information
        self.assertIs(
            ensure_get_servlet(http_svc, "/test")[0], servlet, "get_servlet() didn't return the servlet"
        )
        self.assertIs(
            ensure_get_servlet(http_svc, "/test/Toto")[0], servlet, "get_servlet() didn't return the servlet"
        )
        self.assertIsNone(http_svc.get_servlet("/"), "Root is associated to a servlet")
        self.assertIsNone(http_svc.get_servlet("/tes"), "Incomplete path is associated to a servlet")

        # Test access to /
        self.assertEqual(self.get_http_code(uri="/"), 404, "Received something other than a 404")

        # Test access to /test
        self.assertEqual(self.get_http_code(uri="/test", method="GET"), 200, "Servlet not registered ?")
        self.assertEqual(self.get_http_code(uri="/test", method="POST"), 201, "Servlet not registered ?")
        self.assertEqual(self.get_http_code(uri="/test", method="PUT"), 404, "Unwanted answer")

        # Sub path
        self.assertEqual(self.get_http_code(uri="/test/toto", method="GET"), 200, "Servlet not registered ?")

        # Unregister the servlet
        http_svc.unregister("/test")

        # Test the call back
        self.assertEqual(["/test"], servlet.unbound, "unbound_from not called")
        self.assertEqual([], servlet.bound, "bound_to called")
        servlet.reset()

        # Test access to /
        self.assertEqual(self.get_http_code(uri="/"), 404, "Received something other than a 404")

        # Test access to /test
        self.assertEqual(self.get_http_code(uri="/test", method="POST"), 404, "Servlet still registered")

        # Sub path
        self.assertEqual(self.get_http_code(uri="/test/toto", method="GET"), 404, "Servlet still registered")

    def testBindingRaiser(self) -> None:
        """
        Tests the behavior of the HTTP service when a bound_to() method raises
        an exception
        """
        http_svc = self.instantiate_server()

        # Make the servlet raise an exception
        servlet, servlet_type = self.make_servlet(True)

        # Register the servlet
        log_off()
        self.assertFalse(
            http_svc.register_servlet("/test", servlet, servlet_type=servlet_type),
            "Servlet registered even raising an exception",
        )
        log_on()

        self.assertEqual(self.get_http_code(uri="/test"), 404, "Servlet registered even raising an exception")

    def testUnbindingRaiser(self) -> None:
        """
        Tests the behavior of the HTTP service when a bound_to() method raises
        an exception
        """
        http_svc = self.instantiate_server()

        # Make the servlet to not raise an exception
        servlet, servlet_type = self.make_servlet()

        # Register the servlet
        self.assertTrue(
            http_svc.register_servlet("/test", servlet, servlet_type=servlet_type), "Servlet not registered"
        )
        self.assertEqual(self.get_http_code(uri="/test"), 200, "Servlet not registered ?")

        # Make it raise an exception
        servlet.raiser = True

        # Unregister it (no exception should be propagated)
        log_off()
        http_svc.unregister("/test")
        log_on()

        # The servlet must have been unregistered
        self.assertEqual(self.get_http_code(uri="/test"), 404, "Servlet still registered")

    def testAcceptBinding(self) -> None:
        """
        Tests the behavior of the HTTP service when a bound_to() method raises
        an exception
        """
        http_svc = self.instantiate_server()

        # Make the first servlet
        servlet, servlet_type = self.make_servlet(False)

        # Make the second servlet
        servlet_2, servlet_type_2 = self.make_servlet(False)

        # Register the first servlet
        self.assertTrue(
            http_svc.register_servlet("/test", servlet, servlet_type=servlet_type), "Servlet not registered"
        )
        self.assertEqual(self.get_http_code(uri="/test"), 200, "Servlet not registered ?")

        # Second registration must work
        self.assertTrue(
            http_svc.register_servlet("/test", servlet, servlet_type=servlet_type), "Servlet not registered"
        )

        # Try to register the second servlet, accepting the server
        servlet_2.accept = True
        self.assertRaises(
            ValueError, http_svc.register_servlet, "/test", servlet_2, servlet_type=servlet_type_2
        )

        # Ensure that our first servlet is still there
        self.assertEqual(self.get_http_code(uri="/test"), 200, "Servlet not registered ?")

        # Try to register the second servlet, rejecting the server
        servlet_2.accept = False
        self.assertFalse(
            http_svc.register_servlet("/test", servlet_2, servlet_type=servlet_type_2),
            "Non-accepted server -> must return False",
        )

        # Ensure that our first servlet is still there
        self.assertEqual(self.get_http_code(uri="/test"), 200, "Servlet not registered ?")

        # Unregister it (no exception should be propagated)
        log_off()
        http_svc.unregister("/test")
        log_on()

        # The servlet must have been unregistered
        self.assertEqual(self.get_http_code(uri="/test"), 404, "Servlet still registered")

    def testWhiteboardPatternSimple(self) -> None:
        """
        Tests the whiteboard pattern with a simple path
        """
        http_svc = self.instantiate_server()

        # Instantiate the servlet component
        servlet_name = "test-whiteboard-simple"
        servlet = self.ipopo.instantiate(
            self.test_servlet_factory,
            servlet_name,
            {self.test_servlet_path_prop: "/test", "raiser": False},
        )

        # Test the call back
        self.assertEqual(["/test"], servlet.bound, "bound_to not called")
        self.assertEqual([], servlet.unbound, "unbound_from called")
        servlet.reset()

        # Test information
        self.assertIs(
            ensure_get_servlet(http_svc, "/test")[0], servlet, "get_servlet() didn't return the servlet"
        )
        self.assertEqual(
            ensure_get_servlet(http_svc, "/test")[2],
            "/test",
            "get_servlet() didn't return the prefix correctly",
        )

        # Test access to /test
        self.assertEqual(self.get_http_code(uri="/test", method="GET"), 200, "Servlet not registered ?")
        self.assertEqual(self.get_http_code(uri="/test", method="POST"), 201, "Servlet not registered ?")
        self.assertEqual(self.get_http_code(uri="/test", method="PUT"), 404, "Unwanted answer")

        # Kill the component
        self.ipopo.kill(servlet_name)

        # Test the call back
        self.assertEqual(["/test"], servlet.unbound, "unbound_from not called")
        self.assertEqual([], servlet.bound, "bound_to called")
        servlet.reset()

        # Test access to /test
        self.assertEqual(self.get_http_code(uri="/test", method="POST"), 404, "Servlet still registered")

    def testWhiteboardPatternMultiple(self) -> None:
        """
        Tests the whiteboard pattern with a multiple paths
        """
        http_svc = self.instantiate_server()

        # Instantiate the servlet component
        servlet_name = "test-whiteboard-multiple"
        paths = ["/test1", "/test2", "/test/1"]

        servlet = self.ipopo.instantiate(
            self.test_servlet_factory,
            servlet_name,
            {self.test_servlet_path_prop: paths, "raiser": False},
        )

        # Test the call back
        for path in paths:
            self.assertIn(path, servlet.bound, f"bound_to not called for {path}")
        self.assertEqual([], servlet.unbound, "unbound_from called")
        servlet.reset()

        # Test information
        for path in paths:
            self.assertIs(
                ensure_get_servlet(http_svc, path)[0], servlet, "get_servlet() didn't return the servlet"
            )

        # Test access to /test
        for path in paths:
            self.assertEqual(self.get_http_code(uri=path), 200, "Servlet not registered ?")

        # Kill the component
        self.ipopo.kill(servlet_name)

        # Test the call back
        for path in paths:
            self.assertIn(path, servlet.unbound, f"unbound_from not called for {path}")
        self.assertEqual([], servlet.bound, "bound_to called")
        servlet.reset()

        # Test access to paths
        for path in paths:
            self.assertEqual(self.get_http_code(uri=path), 404, "Servlet still registered")

    def testWhiteboardPatternUpdate(self) -> None:
        """
        Tests the whiteboard pattern with a simple path, which path property
        is updated
        """
        http_svc = self.instantiate_server()

        # Instantiate the servlet component
        servlet_name = "test-whiteboard-simple"
        servlet = self.ipopo.instantiate(
            self.test_servlet_factory,
            servlet_name,
            {self.test_servlet_path_prop: "/test", "raiser": False},
        )

        # Test the call back
        self.assertEqual(["/test"], servlet.bound, "bound_to not called")
        self.assertEqual([], servlet.unbound, "unbound_from called")
        servlet.reset()

        # Test information
        self.assertIs(
            ensure_get_servlet(http_svc, "/test")[0], servlet, "get_servlet() didn't return the servlet"
        )

        # Test access to /test
        self.assertEqual(self.get_http_code(uri="/test", method="GET"), 200, "Servlet not registered ?")
        self.assertEqual(self.get_http_code(uri="/test-updated", method="GET"), 404, "Unwanted success")

        # Update the service property
        servlet.change("/test-updated")

        # Test the call back
        self.assertEqual(["/test-updated"], servlet.bound, "bound_to not called")
        self.assertEqual(["/test"], servlet.unbound, "unbound_from not called")
        servlet.reset()

        # Test information
        self.assertIs(
            ensure_get_servlet(http_svc, "/test-updated")[0],
            servlet,
            "get_servlet() didn't return the servlet",
        )

        # Test access to /test-updated
        self.assertEqual(
            self.get_http_code(uri="/test-updated", method="GET"), 200, "Servlet not registered ?"
        )
        self.assertEqual(self.get_http_code(uri="/test", method="GET"), 404, "Unwanted answer after update")

        # Kill the component
        self.ipopo.kill(servlet_name)

        # Test the call back
        self.assertEqual(["/test-updated"], servlet.unbound, "unbound_from not called")
        self.assertEqual([], servlet.bound, "bound_to called")
        servlet.reset()

        # Test access to /test-updated
        self.assertEqual(
            self.get_http_code(uri="/test-updated", method="GET"), 404, "Servlet still registered"
        )


# ------------------------------------------------------------------------------


class BasicHTTPServiceMethodsTest(unittest.TestCase):
    """
    Tests of the basic HTTP service methods
    """

    framework: Framework
    ipopo: IPopoService

    http_bundle = "pelix.http.basic"
    http_factory: str = http.FACTORY_HTTP_BASIC
    instance_name: str = "test-http-service"

    def setUp(self) -> None:
        """
        Sets up the test environment
        """
        # Start a framework
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()

        # Install iPOPO
        self.ipopo = install_ipopo(self.framework)

        # Install HTTP service
        install_bundle(self.framework, self.http_bundle)
        self.http_svc = self.instantiate_server()

        # Install test bundle
        self.servlets = install_bundle(self.framework, "tests.http.servlets_bundle")
        self._port: int = 0

    def tearDown(self) -> None:
        """
        Cleans up the test environment
        """
        # Stop the framework
        FrameworkFactory.delete_framework()
        self.framework = None  # type: ignore

    def instantiate_server(
        self, address: str | None = DEFAULT_HOST, port: int | None = None
    ) -> http.HTTPService:
        """
        Instantiates a basic server component
        """
        srv = instantiate_server(self.ipopo, self.http_factory, self.instance_name, address, port)
        self._port = srv.get_access()[1]
        return srv

    def kill_server(self) -> None:
        """
        Kills the server component
        """
        try:
            kill_server(self.ipopo, self.instance_name)
        except:
            logging.exception("Error while killing the server component")
            raise

    def get_http_code(
        self, uri: str = "/", method: str = "GET", headers: dict[str, Any] | None = None, content: Any = None
    ) -> int:
        """
        Retrieves the status code of an HTTP request
        :param uri: Request URI
        :param method: Request HTTP method (GET, POST, ...)
        :param headers: Request headers
        :return: The HTTP status code
        """
        if self._port == 0:
            self.fail("Server not instantiated")

        return get_http_code(self._port, DEFAULT_HOST, uri, method, headers, content)

    def testGetServerInfo(self) -> None:
        """
        Test server information methods
        """
        # Given a valid address
        address = "127.0.0.1"
        port = 8090

        self.kill_server()
        http_svc = self.instantiate_server(address, port)

        self.assertEqual(http_svc.get_hostname(), socket.gethostname(), "Different host names found")

        self.assertEqual(http_svc.get_access(), (address, port), "Different accesses found")

        # Given no address -> must be in a standard localhost representation
        # (depends on test system)
        localhost_names = ("localhost", "127.0.0.1", "127.0.1.1", "::1")
        self.kill_server()
        http_svc = self.instantiate_server(None, port)

        access = http_svc.get_access()
        self.assertIn(access[0], localhost_names, "Address is not localhost")
        self.assertEqual(access[1], port, "Different ports found")

        # Given no port -> random port
        self.kill_server()
        http_svc = self.instantiate_server(None, None)

        address, port = http_svc.get_access()
        self.assertEqual(get_http_code(port, address), 404, "HTTP Service not stated with a random port")

    def testGetServlet(self) -> None:
        """
        Tests the get_servlet() method
        """
        self.assertIsNone(self.http_svc.get_servlet(None), "None servlet may not exist")

        self.assertIsNone(self.http_svc.get_servlet(""), "Empty path may not be handled")

        self.assertIsNone(self.http_svc.get_servlet("test"), "Invalid path may not be handled")

        self.assertIsNone(self.http_svc.get_servlet("/"), "Empty servlet service may return None")

        # Dummy objects
        servlet_1 = cast(http.Servlet, object())
        servlet_2 = cast(http.Servlet, object())

        # Register'em
        path_1 = "/test"
        path_2 = "/test/sub"

        self.assertTrue(self.http_svc.register_servlet(path_1, servlet_1))
        self.assertTrue(self.http_svc.register_servlet(path_2, servlet_2))

        # Test the get_servlet method
        for path in ("/test", "/test/", "/test/1"):
            self.assertIs(
                ensure_get_servlet(self.http_svc, path)[0],
                servlet_1,
                f"Servlet 1 should handle {path}",
            )
            self.assertEqual(ensure_get_servlet(self.http_svc, path)[2], path_1, "Servlet 1 path is not kept")

        for path in ("/test/sub", "/test/sub/", "/test/sub/1"):
            self.assertIs(
                ensure_get_servlet(self.http_svc, path)[0],
                servlet_2,
                f"Servlet 2 should handle {path}",
            )
            self.assertEqual(ensure_get_servlet(self.http_svc, path)[2], path_2, "Servlet 2 path is not kept")

    def testRegisterServlet(self) -> None:
        """
        Tests the behavior of register_servlet with dummy objects
        """
        # Dummy objects
        servlet_1 = cast(http.Servlet, object())
        servlet_2 = cast(http.Servlet, object())

        # Refuse None servlets
        self.assertRaises(ValueError, self.http_svc.register_servlet, "/test", None)

        # Refuse empty paths
        for invalid in (None, "", "test"):
            self.assertRaises(ValueError, self.http_svc.register_servlet, invalid, servlet_1)

        # Registration must succeed, even without calls to bound_to
        self.assertTrue(self.http_svc.register_servlet("/test", servlet_1))
        # Allow re-registration of the same object
        self.assertTrue(self.http_svc.register_servlet("/test", servlet_1))

        # Refuse overrides
        self.assertRaises(ValueError, self.http_svc.register_servlet, "/test", servlet_2)
        self.assertTrue(self.http_svc.register_servlet("/test/sub", servlet_2))

    def testUnregisterServlet(self) -> None:
        """
        Tests the behavior of register_servlet with dummy objects
        """
        # Dummy object
        servlet_1 = cast(http.Servlet, object())

        self.http_svc.register_servlet("/test", servlet_1)

        # Try to unregister invalid/unknown paths
        for invalid in (None, "", "test", "/test/sub", "/"):
            self.assertFalse(
                self.http_svc.unregister(invalid), f"An invalid path was unregistered: {invalid}"
            )

        # Try to unregister a None servlet
        self.assertFalse(self.http_svc.unregister(None), "None can't be unregistered.")

        # Try to unregister an unknown servlet
        self.assertFalse(
            self.http_svc.unregister(None, cast(http.Servlet, object())),
            "An unknown servlet can't be unregistered.",
        )


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
