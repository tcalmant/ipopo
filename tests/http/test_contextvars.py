#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the propagation of the context variables to the synchronous servlets of the
asynchronous HTTP service.

:author: Thomas Calmant
"""

import contextvars
import importlib.util
import unittest
from typing import Any, cast

from pelix import http
from pelix.framework import Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import IPopoService
from tests.http.utils import DEFAULT_HOST, get_http_page, install_ipopo

if importlib.util.find_spec("aiohttp") is None:
    raise unittest.SkipTest("aiohttp library not available")

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------

_TEST_VAR: contextvars.ContextVar[str] = contextvars.ContextVar("test_var")


class ContextServlet:
    """
    Servlet which answers the value it sees, then sets a new one
    """

    def __init__(self) -> None:
        self.calls = 0

    def do_GET(self, request: http.AbstractHTTPServletRequest, response: Any) -> None:
        """
        Answers the current value of the test variable and replaces it
        """
        seen = _TEST_VAR.get("unset")
        self.calls += 1
        _TEST_VAR.set(f"set-by-request-{self.calls}")
        response.send_content(200, seen, "text/plain")


class AsyncBackendContextTest(unittest.TestCase):
    """
    A synchronous servlet of the asynchronous HTTP service runs in a copy of the
    context of the request, not in the context of the executor thread which happens
    to be free
    """

    framework: Framework
    ipopo: IPopoService

    def setUp(self) -> None:
        """
        Prepares a framework with the asynchronous HTTP service
        """
        self.framework = create_framework([])
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.servlet = ContextServlet()

        context = self.framework.get_bundle_context()
        context.install_bundle("pelix.http.basic_async").start()

        service = cast(
            http.HTTPService,
            self.ipopo.instantiate(
                http.FACTORY_HTTP_ASYNC,
                "test-http-context",
                {http.HTTP_SERVICE_ADDRESS: DEFAULT_HOST, http.HTTP_SERVICE_PORT: 0},
            ),
        )
        context.register_service(http.HTTP_SERVLET, self.servlet, {http.HTTP_SERVLET_PATH: "/context"})
        self.port = service.get_access()[1]

    def tearDown(self) -> None:
        """
        Cleans up for the next test
        """
        FrameworkFactory.delete_framework(self.framework)
        self.framework = None  # type: ignore

    def test_no_leak_between_requests(self) -> None:
        """
        The executor threads are reused: what a servlet sets must not be visible to
        the next request handled by the same thread
        """
        # More requests than the executor has workers, sent one after the other so
        # that an idle thread is always available for reuse
        for _ in range(8):
            code, data = get_http_page(self.port, DEFAULT_HOST, "/context")
            self.assertEqual(code, 200)
            self.assertEqual(data, b"unset", "A previous request leaked its context")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
