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
import tests.http.test_basic_ssl as basic_tests_ssl

try:
    assert importlib.util.find_spec("aiohttp") is not None
except Exception:
    raise unittest.SkipTest("aiohttp library not available")


# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


def make_test_class(
    test_class: str, http_bundle: str = "pelix.http.basic_async", factory: str = http.FACTORY_HTTP_ASYNC
) -> type:
    """
    Creates a test class for the given factory

    :param http_bundle: The HTTP implementation bundle name
    :param factory: The factory name
    :return: A test class
    """
    base_class = cast(type, getattr(basic_tests_ssl, test_class))

    return type(
        f"Async{base_class.__name__}",
        (base_class,),
        {
            "http_bundle": http_bundle,
            "http_factory": factory,
            "instance_name": f"test-{factory.replace('.', '-')}",
        },
    )


AsyncHTTPSTest = make_test_class("BasicHTTPSTest")

# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
