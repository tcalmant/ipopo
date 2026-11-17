#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix async HTTP service test module.

:author: Thomas Calmant
"""

import http.client as httplib
import importlib.util
import io
import logging
import threading
import unittest
from typing import Any, cast

import tests.http.test_basic as basic_tests
from pelix import http
from pelix.framework import FrameworkFactory
from tests.http.utils import (
    ASYNC_SERVLET_FACTORY,
    DEFAULT_HOST,
    SIMPLE_SERVLET_FACTORY,
    install_ipopo,
    instantiate_server,
)

if importlib.util.find_spec("aiohttp") is None:
    raise unittest.SkipTest("aiohttp library not available")

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


def make_test_class(
    test_class: str,
    servlet_factory: str,
    prop_servlet_path: str,
    servlet_class: str = "SimpleServlet",
    servlet_type: http.ServletType = http.ServletType.SYNC,
    server_factory: str = http.FACTORY_HTTP_ASYNC,
) -> type:
    """
    Creates a test class for the given factory

    :param http_bundle: The HTTP implementation bundle name
    :param factory: The factory name
    :return: A test class
    """
    base_class = cast(type, getattr(basic_tests, test_class))

    return type(
        f"Async{base_class.__name__}",
        (base_class,),
        {
            "http_bundle": "pelix.http.basic_async",
            "http_factory": server_factory,
            "instance_name": f"test-{server_factory.replace('.', '-')}",
            "test_servlet_factory": servlet_factory,
            "test_servlet_path_prop": prop_servlet_path,
            "test_servlet_class_name": servlet_class,
            "test_servlet_type": servlet_type,
        },
    )


# Test the behaviour of synchronous servlets
AsyncHTTPServiceMethodsTest = make_test_class(
    "BasicHTTPServiceMethodsTest", SIMPLE_SERVLET_FACTORY, http.HTTP_SERVLET_PATH
)
AsyncHTTPServiceServletsTest = make_test_class(
    "BasicHTTPServiceServletsTest", SIMPLE_SERVLET_FACTORY, http.HTTP_SERVLET_PATH
)

FullAsyncHTTPServiceMethodsTest = make_test_class(
    "BasicHTTPServiceMethodsTest",
    ASYNC_SERVLET_FACTORY,
    http.HTTP_SERVLET_ASYNC_PATH,
    "AsyncSimpleServlet",
    http.ServletType.ASYNC,
)
FullAsyncHTTPServiceServletsTest = make_test_class(
    "BasicHTTPServiceServletsTest",
    ASYNC_SERVLET_FACTORY,
    http.HTTP_SERVLET_ASYNC_PATH,
    "AsyncSimpleServlet",
    http.ServletType.ASYNC,
)


BLOCK = b"x" * 64 * 1024
""" A block of the size from which the async service streams a synchronous response """


class StreamingServlet:
    """
    Synchronous servlet writing its body in blocks, waiting for the test
    between the first and the next ones
    """

    def __init__(self) -> None:
        self.release = threading.Event()

    def do_GET(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        """
        Writes the body as the "mode" query parameter says
        """
        mode = request.get_query().get("mode", ["block"])[0]
        if mode == "length":
            response.set_header("content-length", 3 * len(BLOCK))
        response.end_headers()

        if mode == "flush":
            response.write(b"first")
            response.get_wfile().flush()
        elif mode == "small":
            response.write(b"small")
            return
        elif mode == "small-error":
            response.write(b"partial")
            raise ValueError("Error before streaming")
        else:
            response.write(BLOCK)

        # The client must receive the first part before the servlet ends
        if mode in ("block", "flush", "length") and not self.release.wait(10):
            raise TimeoutError("The client did not get the first block")

        if mode == "error":
            raise ValueError("Error after streaming")

        response.write(BLOCK)
        response.write(BLOCK)

    do_HEAD = do_GET


class WriteWrapperTest(unittest.TestCase):
    """
    Tests the stream given to synchronous servlets
    """

    def test_write(self) -> None:
        """
        Tests writing then closing the stream
        """
        from pelix.http.basic_async import _SyncHTTPServletResponse

        # The request and loop aren't used while the body is small
        response = _SyncHTTPServletResponse(cast(Any, None), cast(Any, None))
        stream = response.get_wfile()
        self.assertEqual(stream.mode, "wb")
        self.assertTrue(stream.writable())
        self.assertFalse(stream.readable())
        self.assertRaises(io.UnsupportedOperation, stream.read)

        self.assertEqual(stream.write(b"Hello, "), 7)
        stream.writelines([b"World", b"!"])
        stream.close()
        self.assertRaises(ValueError, stream.write, b"more")
        self.assertRaises(ValueError, stream.flush)

        # Data is still sent after close
        self.assertEqual(cast(Any, response.to_aiohttp_response()).body, b"Hello, World!")

    def test_response_multiple_writes(self) -> None:
        """
        Tests that a synchronous servlet can write its response in several calls
        """
        from pelix.http.basic_async import _SyncHTTPServletResponse

        response = _SyncHTTPServletResponse(cast(Any, None), cast(Any, None))
        response.set_response(200)
        response.write(b"Hello, ")
        response.write(b"World")
        response.get_wfile().write(b"!")

        self.assertEqual(cast(Any, response.to_aiohttp_response()).body, b"Hello, World!")


class StreamedSyncResponseTest(unittest.TestCase):
    """
    Tests that the async service streams the large bodies of synchronous servlets
    """

    def setUp(self) -> None:
        """
        Starts the async HTTP service with the streaming servlet
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        ipopo = install_ipopo(self.framework)
        self.framework.install_bundle("pelix.http.basic_async").start()
        svc = instantiate_server(ipopo, http.FACTORY_HTTP_ASYNC, "test-async-streaming", DEFAULT_HOST, 0)
        self.port = svc.get_access()[1]

        self.servlet = StreamingServlet()
        self.framework.get_bundle_context().register_service(
            http.HTTP_SERVLET, self.servlet, {http.HTTP_SERVLET_PATH: "/stream"}
        )

    def tearDown(self) -> None:
        """
        Releases the servlet and stops the framework
        """
        self.servlet.release.set()
        FrameworkFactory.delete_framework()

    def request(self, mode: str, method: str = "GET") -> httplib.HTTPResponse:
        """
        Sends a request to the streaming servlet

        :param mode: How the servlet writes its body
        :param method: HTTP method
        :return: The response, its body not read yet
        """
        self.servlet.release.clear()
        self.conn = httplib.HTTPConnection(DEFAULT_HOST, self.port, timeout=5)
        self.addCleanup(self.conn.close)
        self.conn.request(method, f"/stream?mode={mode}")
        return self.conn.getresponse()

    def test_streamed(self) -> None:
        """
        Tests that the client gets the first part of the body while the servlet still runs
        """
        for mode, first, length in (
            ("block", BLOCK, None),
            ("flush", b"first", None),
            ("length", BLOCK, str(3 * len(BLOCK))),
        ):
            with self.subTest(mode=mode):
                response = self.request(mode)
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("content-length"), length)
                self.assertEqual(response.read(len(first)), first)

                self.servlet.release.set()
                self.assertEqual(response.read(), 2 * BLOCK)

    def test_not_streamed(self) -> None:
        """
        Tests the responses which aren't streamed or have no body
        """
        for mode, method, status, body, length in (
            ("small", "GET", 200, b"small", "5"),
            ("small", "HEAD", 200, b"", "5"),
            ("large", "GET", 200, 3 * BLOCK, None),
            ("large", "HEAD", 200, b"", None),
            ("small-error", "GET", 500, None, None),
        ):
            with self.subTest(mode=mode, method=method):
                response = self.request(mode, method)
                self.assertEqual(response.status, status)
                if body is not None:
                    self.assertEqual(response.getheader("content-length"), length)
                    self.assertEqual(response.read(), body)

                if method == "HEAD":
                    # A body sent anyway would be read as the next response
                    self.conn.request("GET", "/stream?mode=small")
                    self.assertEqual(self.conn.getresponse().read(), b"small")

    def test_error_after_streaming(self) -> None:
        """
        Tests that an error after the start of the response cuts the connection
        """
        response = self.request("error")
        self.assertEqual(response.status, 200)
        self.assertRaises(httplib.IncompleteRead, response.read)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
