#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix async HTTP service test module.

:author: Thomas Calmant
"""

import importlib.util
import logging
import unittest
from typing import cast

import pelix.http as http
import tests.http.test_basic as basic_tests
from tests.http.utils import ASYNC_SERVLET_FACTORY, SIMPLE_SERVLET_FACTORY

try:
    assert importlib.util.find_spec("aiohttp") is not None
except Exception:
    raise unittest.SkipTest("aiohttp library not available")

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 1)
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

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
