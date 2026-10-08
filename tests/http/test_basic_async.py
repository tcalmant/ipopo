#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix async HTTP service test module.

:author: Thomas Calmant
"""

import importlib.util
import io
import logging
import unittest
from typing import Any, cast

import tests.http.test_basic as basic_tests
from pelix import http
from tests.http.utils import ASYNC_SERVLET_FACTORY, SIMPLE_SERVLET_FACTORY

if importlib.util.find_spec("aiohttp") is None:
    raise unittest.SkipTest("aiohttp library not available")

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 4)
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


class WriteWrapperTest(unittest.TestCase):
    """
    Tests the stream buffering the body of synchronous servlet responses
    """

    def test_write(self) -> None:
        """
        Tests writing then closing the stream
        """
        from pelix.http.basic_async import _WriteWrapper

        stream = _WriteWrapper()
        self.assertEqual(stream.mode, "wb")
        self.assertTrue(stream.writable())
        self.assertFalse(stream.readable())
        self.assertRaises(io.UnsupportedOperation, stream.read)

        self.assertEqual(stream.write(b"Hello, "), 7)
        stream.writelines([b"World", b"!"])
        stream.flush()
        stream.close()

        # Data is still available after close
        self.assertEqual(stream.get(), b"Hello, World!")
        self.assertRaises(ValueError, stream.write, b"more")

    def test_response_multiple_writes(self) -> None:
        """
        Tests that a synchronous servlet can write its response in several calls
        """
        from pelix.http.basic_async import _SyncHTTPServletResponse

        # The request and loop aren't used to buffer the body
        response = _SyncHTTPServletResponse(cast(Any, None), cast(Any, None))
        response.set_response(200)
        response.write(b"Hello, ")
        response.write(b"World")
        response.get_wfile().write(b"!")
        response.get_wfile().flush()

        self.assertEqual(cast(Any, response.to_aiohttp_response()).body, b"Hello, World!")


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
