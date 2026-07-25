#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the content of the error pages sent by the HTTP services.

The details of an error (stack trace) must not be sent to the clients unless
the service has been explicitly configured to do so.

:author: Thomas Calmant
"""

import importlib.util
import logging
import re
import unittest
from typing import Any, Optional

import pelix.http as http
from pelix.framework import Framework, FrameworkFactory
from pelix.http.basic import HttpServiceImpl
from tests.http.utils import DEFAULT_HOST, get_http_page, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

INSTANCE_NAME = "test-http-errors"

SECRET = "s3cr3t-token-value"

ERROR_ID_PATTERN = re.compile(r"Error ID: ([0-9a-f]{32})")

# ------------------------------------------------------------------------------


class RaisingServlet:
    """
    Servlet raising an exception, with sensitive data in its message
    """

    def do_GET(self, request: Any, response: Any) -> None:
        """
        Always fails
        """
        raise ValueError(f"Error while handling token {SECRET}")


class CustomErrorHandler:
    """
    Custom error page generator, to check what it is given
    """

    def __init__(self) -> None:
        self.stack: Optional[str] = None

    def make_not_found_page(self, path: str) -> str:
        """
        Prepares a "page not found" page
        """
        return f"Not found: {path}"

    def make_exception_page(self, path: str, stack: str) -> str:
        """
        Prepares an error page, keeping what it has been given
        """
        self.stack = stack
        return f"Error: {stack}"


# ------------------------------------------------------------------------------


class ErrorPageContentTest(unittest.TestCase):
    """
    Tests the content of the 500 error page returned to a client
    """

    framework: Framework

    def setUp(self) -> None:
        """
        Sets up the test environment
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.framework.install_bundle("pelix.http.basic").start()

    def tearDown(self) -> None:
        """
        Cleans up the test environment
        """
        FrameworkFactory.delete_framework()

    def start_server(self, debug_errors: Optional[bool] = None) -> int:
        """
        Starts a HTTP server with a servlet raising an exception

        :param debug_errors: Value of the debug property, ignored if None
        :return: The port the server is bound to
        """
        properties = {
            http.HTTP_SERVICE_ADDRESS: DEFAULT_HOST,
            http.HTTP_SERVICE_PORT: 0,
            "pelix.http.logger.name": INSTANCE_NAME,
        }
        if debug_errors is not None:
            properties[http.HTTP_DEBUG_ERRORS] = debug_errors

        svc = self.ipopo.instantiate(http.FACTORY_HTTP_BASIC, INSTANCE_NAME, properties)

        context = self.framework.get_bundle_context()
        context.register_service(http.HTTP_SERVLET, RaisingServlet(), {http.HTTP_SERVLET_PATH: "/error"})
        return svc.get_access()[1]

    def get_error_page(self, debug_errors: Optional[bool] = None) -> str:
        """
        Calls the failing servlet and returns the error page

        :param debug_errors: Value of the debug property, ignored if None
        :return: The content of the error page
        """
        port = self.start_server(debug_errors)
        with self.assertLogs(INSTANCE_NAME, logging.ERROR):
            status, content = get_http_page(port, uri="/error")

        self.assertEqual(status, 500, "Error page not sent")
        return content.decode("utf-8")

    def test_details_are_hidden_by_default(self) -> None:
        """
        The error details must not be sent to the client by default
        """
        page = self.get_error_page()

        self.assertNotIn("Traceback", page, "Stack trace sent to the client")
        self.assertNotIn(SECRET, page, "Error message sent to the client")
        self.assertNotIn("basic.py", page, "Server file paths sent to the client")
        self.assertNotIn(__file__, page, "Server file paths sent to the client")
        self.assertIn("Error ID:", page, "No error ID given to the client")

    def test_details_are_hidden_when_debug_is_off(self) -> None:
        """
        An explicitly unset debug flag must keep the details hidden
        """
        page = self.get_error_page(False)
        self.assertNotIn("Traceback", page, "Stack trace sent to the client")
        self.assertNotIn(SECRET, page, "Error message sent to the client")

    def test_details_are_sent_in_debug(self) -> None:
        """
        The error details must be sent to the client when explicitly asked
        """
        page = self.get_error_page(True)

        self.assertIn("Traceback", page, "No stack trace in debug mode")
        self.assertIn(SECRET, page, "No error message in debug mode")

    def test_error_id_matches_the_logs(self) -> None:
        """
        The error ID given to the client must allow to find the error in the logs
        """
        port = self.start_server()
        with self.assertLogs(INSTANCE_NAME, logging.ERROR) as log_context:
            status, content = get_http_page(port, uri="/error")

        self.assertEqual(status, 500)
        page = content.decode("utf-8")

        match = ERROR_ID_PATTERN.search(page)
        assert match is not None, "No error ID in the error page"
        error_id = match.group(1)

        logged = "\n".join(log_context.output)
        self.assertIn(error_id, logged, "The error ID is not in the logs")
        self.assertIn("Traceback", logged, "The stack trace is not logged")
        self.assertIn(SECRET, logged, "The error message is not logged")

    def test_not_found_page(self) -> None:
        """
        The 404 page must still be sent, and must escape the request path
        """
        port = self.start_server()
        status, content = get_http_page(port, uri="/<script>alert(1)</script>")
        page = content.decode("utf-8")

        self.assertEqual(status, 404)
        self.assertNotIn("<script>", page, "Request path not escaped")


# ------------------------------------------------------------------------------


class MakeExceptionPageTest(unittest.TestCase):
    """
    Tests the generation of the error page by both HTTP service implementations
    """

    def get_services(self) -> Any:
        """
        Returns the HTTP service implementations to test
        """
        services = [("basic", HttpServiceImpl())]
        if importlib.util.find_spec("aiohttp") is not None:
            from pelix.http.basic_async import AsyncHttpServiceImpl

            services.append(("basic_async", AsyncHttpServiceImpl()))

        return services

    def test_stack_is_hidden_by_default(self) -> None:
        """
        The stack trace must not be in the generated page
        """
        for name, service in self.get_services():
            with self.subTest(service=name):
                page = service.make_exception_page("/path", f"Traceback: {SECRET}")
                self.assertNotIn(SECRET, page)
                self.assertNotIn("Traceback", page)
                self.assertIsNotNone(ERROR_ID_PATTERN.search(page), "No error ID in the page")

    def test_stack_is_shown_in_debug(self) -> None:
        """
        The stack trace must be in the generated page in debug mode
        """
        for name, service in self.get_services():
            with self.subTest(service=name):
                service._debug_errors = True
                page = service.make_exception_page("/path", f"Traceback: {SECRET}")
                self.assertIn(SECRET, page)

    def test_path_is_escaped(self) -> None:
        """
        The request path must be escaped in the generated page
        """
        for name, service in self.get_services():
            with self.subTest(service=name):
                page = service.make_exception_page("/<script>alert(1)</script>", "stack")
                self.assertNotIn("<script>", page)

    def test_custom_handler_gets_no_details(self) -> None:
        """
        A custom error handler must not be given the stack trace by default:
        it generates the page sent to the client
        """
        for name, service in self.get_services():
            with self.subTest(service=name):
                handler = CustomErrorHandler()
                service._error_handler = handler

                page = service.make_exception_page("/path", f"Traceback: {SECRET}")
                assert handler.stack is not None
                self.assertNotIn(SECRET, handler.stack)
                self.assertNotIn(SECRET, page)
                self.assertIsNotNone(ERROR_ID_PATTERN.search(handler.stack))

    def test_custom_handler_gets_details_in_debug(self) -> None:
        """
        A custom error handler must be given the stack trace in debug mode
        """
        for name, service in self.get_services():
            with self.subTest(service=name):
                handler = CustomErrorHandler()
                service._error_handler = handler
                service._debug_errors = True

                page = service.make_exception_page("/path", f"Traceback: {SECRET}")
                assert handler.stack is not None
                self.assertIn(SECRET, handler.stack)
                self.assertIn(SECRET, page)


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
