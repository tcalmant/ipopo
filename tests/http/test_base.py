#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the code shared by the HTTP service implementations.

:author: Thomas Calmant
"""

import importlib.util
import unittest
from typing import Any

from pelix import http
from pelix.framework import Framework, FrameworkFactory
from pelix.http._base import AbstractHttpService, compute_sub_path, normalize_request_path
from pelix.http.basic import HttpServiceImpl
from tests.http.utils import DEFAULT_HOST, get_http_page, install_ipopo, instantiate_server

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class SimpleServlet:
    """
    A servlet which does nothing: only its identity matters here
    """

    def do_GET(self, request: Any, response: Any) -> None:
        """
        Does nothing
        """


def get_services() -> list[tuple[str, AbstractHttpService]]:
    """
    Returns the HTTP service implementations to test.
    They are used outside of any framework: only the code shared by both
    implementations is tested here.

    :return: A list of (name, service) tuples
    """
    services: list[tuple[str, AbstractHttpService]] = [("basic", HttpServiceImpl())]
    if importlib.util.find_spec("aiohttp") is not None:
        from pelix.http.basic_async import AsyncHttpServiceImpl

        services.append(("basic_async", AsyncHttpServiceImpl()))

    return services


# ------------------------------------------------------------------------------


class NormalizeRequestPathTest(unittest.TestCase):
    """
    Tests the normalization of the path of an incoming request
    """

    def test_query_string_is_removed(self) -> None:
        """
        The query string must not be part of the path used for routing
        """
        self.assertEqual(normalize_request_path("/path?a=1"), "/path")
        self.assertEqual(normalize_request_path("/path?a=1?b=2"), "/path")
        self.assertEqual(normalize_request_path("/path?"), "/path")

    def test_slashes_are_collapsed(self) -> None:
        """
        Any sequence of consecutive slashes must be collapsed into a single one
        """
        for raw, expected in (
            ("/a/b", "/a/b"),
            ("/a//b", "/a/b"),
            ("/a///b", "/a/b"),
            ("//a////b//", "/a/b/"),
            ("////", "/"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_request_path(raw), expected)

    def test_trailing_slash_is_kept(self) -> None:
        """
        A single trailing slash is meaningful and must be kept
        """
        self.assertEqual(normalize_request_path("/path/"), "/path/")
        self.assertEqual(normalize_request_path("/path/?a=1"), "/path/")

    def test_is_idempotent(self) -> None:
        """
        Normalizing an already normalized path must not change it
        """
        for raw in ("/", "/a/b", "/a/b/", "/a%2Fb"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_request_path(normalize_request_path(raw)), raw)


class ComputeSubPathTest(unittest.TestCase):
    """
    Tests the computation of the servlet-relative path
    """

    def test_simple_prefix(self) -> None:
        """
        Basic computation of the sub path
        """
        self.assertEqual(compute_sub_path("/prefix/sub", "/prefix"), "/sub")
        self.assertEqual(compute_sub_path("/prefix/sub/", "/prefix"), "/sub/")

    def test_prefix_with_trailing_slash(self) -> None:
        """
        The prefix can end with a slash
        """
        self.assertEqual(compute_sub_path("/prefix/sub", "/prefix/"), "/sub")

    def test_exact_match(self) -> None:
        """
        A request on the prefix itself has a root sub path
        """
        self.assertEqual(compute_sub_path("/prefix", "/prefix"), "/")
        self.assertEqual(compute_sub_path("/prefix/", "/prefix"), "/")

    def test_slashes_are_collapsed(self) -> None:
        """
        The sub path must not contain sequences of slashes either
        """
        self.assertEqual(compute_sub_path("/prefix///sub", "/prefix"), "/sub")
        self.assertEqual(compute_sub_path("/prefix/sub//other", "/prefix"), "/sub/other")

    def test_root_prefix(self) -> None:
        """
        The root prefix is a valid one
        """
        self.assertEqual(compute_sub_path("/sub", "/"), "/sub")


# ------------------------------------------------------------------------------


class ResolveRequestTest(unittest.TestCase):
    """
    Tests the routing seam shared by both implementations
    """

    def test_no_servlet(self) -> None:
        """
        The routing result must give the normalized path even without a servlet
        """
        for name, service in get_services():
            with self.subTest(service=name):
                routing = service.resolve_request("/unknown//path?a=1")
                self.assertIsNone(routing.servlet)
                self.assertEqual(routing.path, "/unknown/path")

    def test_servlet_is_found(self) -> None:
        """
        A registered servlet must be found, with its prefix
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                self.assertTrue(service.register_servlet("/test", servlet))

                routing = service.resolve_request("/test/sub")
                self.assertIs(routing.servlet, servlet)
                self.assertEqual(routing.prefix, "/test")
                self.assertEqual(routing.path, "/test/sub")
                self.assertIs(routing.servlet_type, http.ServletType.SYNC)

    def test_query_string_does_not_break_routing(self) -> None:
        """
        The query string must not be taken into account to find the servlet
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                service.register_servlet("/test", servlet)

                routing = service.resolve_request("/test/sub?a=1&b=2")
                self.assertIs(routing.servlet, servlet)
                self.assertEqual(routing.path, "/test/sub")

    def test_repeated_slashes_reach_the_same_servlet(self) -> None:
        """
        Both implementations must agree on the servlet handling a path with
        sequences of slashes: this used to differ between them
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                service.register_servlet("/test", servlet)

                reference = service.resolve_request("/test/sub")
                for raw in ("/test//sub", "/test///sub", "//test////sub"):
                    with self.subTest(raw=raw):
                        routing = service.resolve_request(raw)
                        self.assertIs(routing.servlet, servlet)
                        self.assertEqual(routing.path, reference.path)
                        self.assertEqual(routing.prefix, reference.prefix)


class ServletRegistryTest(unittest.TestCase):
    """
    Tests the servlets registry shared by both implementations
    """

    def test_get_servlet_returns_a_4_tuple(self) -> None:
        """
        The documented result of get_servlet must not have changed
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                service.register_servlet("/test", servlet, {"custom": 42})

                found = service.get_servlet("/test/sub")
                assert found is not None
                self.assertEqual(len(found), 4)

                found_servlet, params, prefix, servlet_type = found
                self.assertIs(found_servlet, servlet)
                self.assertEqual(params["custom"], 42)
                self.assertEqual(prefix, "/test")
                self.assertIs(servlet_type, http.ServletType.SYNC)

    def test_unknown_path(self) -> None:
        """
        get_servlet must return None for an unhandled path
        """
        for name, service in get_services():
            with self.subTest(service=name):
                self.assertIsNone(service.get_servlet("/unknown"))
                self.assertIsNone(service.get_servlet(""))
                self.assertIsNone(service.get_servlet(None))
                self.assertIsNone(service.get_servlet("no-leading-slash"))

    def test_registered_paths(self) -> None:
        """
        The registered paths must be sorted
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                for path in ("/b", "/a", "/c"):
                    service.register_servlet(path, servlet)

                self.assertEqual(service.get_registered_paths(), ["/a", "/b", "/c"])

    def test_invalid_registration(self) -> None:
        """
        Invalid servlets and paths must be refused
        """
        for name, service in get_services():
            with self.subTest(service=name):
                self.assertRaises(ValueError, service.register_servlet, "/test", None)
                self.assertRaises(ValueError, service.register_servlet, "", SimpleServlet())
                self.assertRaises(ValueError, service.register_servlet, "test", SimpleServlet())

    def test_path_already_taken(self) -> None:
        """
        Two servlets can't share a path
        """
        for name, service in get_services():
            with self.subTest(service=name):
                service.register_servlet("/test", SimpleServlet())
                self.assertRaises(ValueError, service.register_servlet, "/test", SimpleServlet())

    def test_double_registration(self) -> None:
        """
        Registering the same servlet twice on the same path is a no-op
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                self.assertTrue(service.register_servlet("/test", servlet))
                self.assertTrue(service.register_servlet("/test", servlet))
                self.assertEqual(service.get_registered_paths(), ["/test"])

    def test_unregister(self) -> None:
        """
        A servlet can be unregistered by path or by instance
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                service.register_servlet("/a", servlet)
                service.register_servlet("/b", servlet)

                self.assertTrue(service.unregister("/a"))
                self.assertEqual(service.get_registered_paths(), ["/b"])

                # Unknown path
                self.assertFalse(service.unregister("/a"))
                self.assertFalse(service.unregister(None))

                # By instance
                self.assertTrue(service.unregister(None, servlet))
                self.assertEqual(service.get_registered_paths(), [])

    def test_sync_service_refuses_async_servlets(self) -> None:
        """
        The synchronous implementation only supports synchronous servlets
        """
        service = HttpServiceImpl()
        for servlet_type in (http.ServletType.ASYNC, http.ServletType.WEBSOCKET):
            with self.subTest(servlet_type=servlet_type):
                self.assertRaises(
                    ValueError,
                    service.register_servlet,
                    "/test",
                    SimpleServlet(),
                    None,
                    servlet_type,
                )

    def test_async_service_accepts_all_servlet_types(self) -> None:
        """
        The asynchronous implementation supports every kind of servlet
        """
        if importlib.util.find_spec("aiohttp") is None:
            self.skipTest("aiohttp is not installed")

        from pelix.http.basic_async import AsyncHttpServiceImpl

        service = AsyncHttpServiceImpl()
        for index, servlet_type in enumerate(http.ServletType):
            with self.subTest(servlet_type=servlet_type):
                path = f"/test{index}"
                self.assertTrue(service.register_servlet(path, SimpleServlet(), None, servlet_type))

                found = service.get_servlet(path)
                assert found is not None
                self.assertIs(found[3], servlet_type)

                # The servlet must know how it has been registered
                self.assertEqual(found[1][http.PARAM_ASYNC], servlet_type != http.ServletType.SYNC)


# ------------------------------------------------------------------------------


class EchoPathServlet:
    """
    A servlet which tells its name and which path it has been given
    """

    def __init__(self, name: str) -> None:
        """
        :param name: A name identifying this servlet in the responses
        """
        self._name = name

    def do_GET(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        """
        Sends back the name of the servlet, its prefix and the sub path
        """
        response.send_content(
            200,
            f"{self._name}|{request.get_prefix_path()}|{request.get_sub_path()}",
            "text/plain",
        )


class EndToEndPathTest(unittest.TestCase):
    """
    Test routing over a real HTTP connection
    """

    framework: Framework

    def setUp(self) -> None:
        """
        Starts a framework with an HTTP server on a random port
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

        ipopo = install_ipopo(self.framework)
        context = self.framework.get_bundle_context()
        context.install_bundle("pelix.http.basic").start()

        self.http_svc = instantiate_server(ipopo, http.FACTORY_HTTP_BASIC, "test-http-paths", port=0)
        self.port = self.http_svc.get_access()[1]

        # Two servlets, one nested in the other
        self.http_svc.register_servlet("/test", EchoPathServlet("root"))
        self.http_svc.register_servlet("/test/inner", EchoPathServlet("inner"))

    def tearDown(self) -> None:
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)

    def test_repeated_slashes_keep_the_deepest_servlet(self) -> None:
        """
        Adding slashes must not move the request from the deepest matching
        servlet to a shallower one
        """
        for uri in (
            "/test/inner/x",
            "/test//inner/x",
            "/test///inner/x",
            "/test/inner//x",
            "//test///inner////x",
        ):
            with self.subTest(uri=uri):
                code, content = get_http_page(self.port, DEFAULT_HOST, uri)
                self.assertEqual(code, 200, f"{uri} did not reach a servlet")
                self.assertEqual(
                    content.decode("utf-8"),
                    "inner|/test/inner|/x",
                    f"{uri} was not handled by the deepest servlet",
                )

    def test_repeated_slashes_on_the_shallow_servlet(self) -> None:
        """
        The servlet must always be given the same, fully collapsed, sub path
        """
        for uri in ("/test/sub", "/test//sub", "/test///sub", "/test////sub"):
            with self.subTest(uri=uri):
                code, content = get_http_page(self.port, DEFAULT_HOST, uri)
                self.assertEqual(code, 200, f"{uri} did not reach the servlet")
                self.assertEqual(content.decode("utf-8"), "root|/test|/sub")

    def test_query_string_is_not_in_the_sub_path(self) -> None:
        """
        The query string must neither prevent the servlet from being found nor
        appear in the sub path: it would break the regular expressions of the
        REST-like router of pelix.http.routing
        """
        code, content = get_http_page(self.port, DEFAULT_HOST, "/test/inner/x?a=1")
        self.assertEqual(code, 200)
        self.assertEqual(content.decode("utf-8"), "inner|/test/inner|/x")

    def test_sub_path_is_cut_at_the_right_place(self) -> None:
        """
        The sub path is computed by removing the prefix, which comes from the
        normalized path: it must be cut from the normalized path too, else the
        repeated slashes shift the cut and eat the beginning of the sub path
        """
        for uri, expected in (
            ("/test/inner/abcdef", "/abcdef"),
            ("/test//inner/abcdef", "/abcdef"),
            ("/test///inner/abcdef", "/abcdef"),
            ("/test/inner///abcdef", "/abcdef"),
        ):
            with self.subTest(uri=uri):
                code, content = get_http_page(self.port, DEFAULT_HOST, uri)
                self.assertEqual(code, 200)
                self.assertEqual(content.decode("utf-8"), f"inner|/test/inner|{expected}")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
