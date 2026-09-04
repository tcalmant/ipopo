#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix HTTP routing test module.

:author: Thomas Calmant
"""

import random
import sys
import unittest
import uuid
from typing import Any

from pelix import http
from pelix.framework import Framework, FrameworkFactory, create_framework
from pelix.http import AbstractHTTPServletRequest, AbstractHTTPServletResponse, routing
from pelix.ipopo.constants import IPopoService
from pelix.utilities import to_str
from tests.http.utils import (
    DEFAULT_HOST,
    get_http_code,
    get_http_page,
    install_ipopo,
    instantiate_server,
    kill_server,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

HTTP_METHODS = ("GET", "HEAD", "POST", "PUT", "DELETE")

# ------------------------------------------------------------------------------


class HttpRoutingTests(unittest.TestCase):
    """
    Tests of the HTTP routing class
    """

    framework: Framework
    ipopo: IPopoService

    http_bundle = "pelix.http.basic"
    http_factory: str = http.FACTORY_HTTP_BASIC
    instance_name: str = "test-http-service"

    @classmethod
    def tearDownClass(cls):
        FrameworkFactory.delete_framework()

    def setUp(self) -> None:
        """
        Sets up the test environment
        """
        # Start a framework
        self.framework = create_framework([self.http_bundle])
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self._port = 0
        self.http = self.instantiate_server()

    def tearDown(self) -> None:
        """
        Cleans up the test environment
        """
        # Kill the server component
        self.kill_server()

        # Stop the framework
        FrameworkFactory.delete_framework(self.framework)

    def instantiate_server(self):
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
            kill_server(self.ipopo, self.instance_name)
        except:
            print("Error while killing the server component", file=sys.stderr)
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

    def get_http_page(
        self, uri: str = "/", method: str = "GET", headers: dict[str, Any] | None = None, content: Any = None
    ) -> tuple[int, bytes]:
        """
        Retrieves the content of an HTTP request
        :param uri: Request URI
        :param method: Request HTTP method (GET, POST, ...)
        :param headers: Request headers
        :param content: Request content
        :return: The HTTP status code and the response content
        """
        if self._port == 0:
            self.fail("Server not instantiated")

        return get_http_page(self._port, DEFAULT_HOST, uri, method, headers, content)

    def test_decorator_type_check(self) -> None:
        """
        Tests the @Http decorator type checking (all others depends on it)
        """
        value: Any

        # Define some invalid types
        class BadClass:
            pass

        # Define a valid methods
        def empty_method() -> None:
            pass

        def args_method(abc: Any, *args: Any) -> None:
            pass

        def kwargs_method(abc: Any, **kwargs: Any) -> None:
            pass

        class SomeClass:
            def correct_method(self, *args: Any) -> None:
                pass

        bad_types = (None, 12, "Bad", BadClass)
        valid_methods = (empty_method, args_method, kwargs_method)

        for value in valid_methods:
            # No change intended
            decorated = routing.Http("/", None)(value)
            self.assertIs(decorated, value)

        for value in bad_types:
            decorator = routing.Http("/", None)
            self.assertRaises(TypeError, decorator.__call__, value)

    def test_decorator_method_check(self) -> None:
        """
        Tests the @Http decorator method checking (all others depends on it)
        """

        def dummy() -> None:
            pass

        for valid in (
            None,
            ("POST",),
            ["GET"],
            ("GET", "HEAD"),
            ["GET, HEAD"],
            {"HEAD", "GET"},
            frozenset(("GET", "HEAD")),
        ):
            self.assertIs(routing.Http("/", valid)(dummy), dummy)

        for invalid in (123, "HEAD"):
            self.assertRaises(TypeError, routing.Http, "/", invalid)

    def test_empty(self) -> None:
        """
        Tests the routing mother class with no routing
        """
        # Register the router as a servlet
        router = routing.RestDispatcher()
        self.http.register_servlet("/routing", router)

        for method in HTTP_METHODS:
            code = self.get_http_code(uri="/routing/", method=method)
            # Ensure 404 (not 500)
            self.assertEqual(code, 404)

    def test_dispatch(self) -> None:
        """
        Tests the dispatcher
        """

        class Servlet(routing.RestDispatcher):
            def __init__(self) -> None:
                super(Servlet, self).__init__()
                self.called_path: str | None = None
                self.prefix: str | None = None

            def reset(self) -> None:
                self.called_path = None
                self.prefix = None

            @routing.HttpGet("")
            def test_no_path(
                self, request: AbstractHTTPServletRequest, response: AbstractHTTPServletResponse
            ) -> None:
                self.called_path = request.get_sub_path()
                self.prefix = request.get_prefix_path()
                response.send_content(300, "Should not happen")

            @routing.HttpGet("/")
            def test_route(
                self, request: AbstractHTTPServletRequest, response: AbstractHTTPServletResponse
            ) -> None:
                self.called_path = request.get_sub_path()
                self.prefix = request.get_prefix_path()
                response.send_content(200, "OK")

            @routing.HttpGet("/test")
            def test_basic(
                self, request: AbstractHTTPServletRequest, response: AbstractHTTPServletResponse
            ) -> None:
                self.called_path = request.get_sub_path()
                self.prefix = request.get_prefix_path()
                response.send_content(200, "OK")

            @routing.HttpGet("/test/a")
            def test_sub_a(
                self, request: AbstractHTTPServletRequest, response: AbstractHTTPServletResponse
            ) -> None:
                self.called_path = request.get_sub_path()
                self.prefix = request.get_prefix_path()
                response.send_content(200, "OK")

            @routing.HttpGet("/test/b")
            def test_sub_b(
                self, request: AbstractHTTPServletRequest, response: AbstractHTTPServletResponse
            ) -> None:
                self.called_path = request.get_sub_path()
                self.prefix = request.get_prefix_path()
                response.send_content(200, "OK")

        # Use a random prefix
        prefix = f"/routing{random.randint(0, 100)}"
        router = Servlet()
        self.http.register_servlet(prefix, router)

        # Route path
        for path in ("", "/", "/test", "/test/a", "/test/b"):
            router.reset()
            code, data = self.get_http_page(uri=f"{prefix}{path}")
            self.assertEqual(code, 200)
            self.assertEqual(to_str(data), "OK")
            self.assertEqual(router.called_path, path or "/")
            self.assertEqual(router.prefix, prefix)

    def test_dispatch_root_vs_typed_param(self) -> None:
        """
        A root route ("" / "/") and a single top-level typed <param> route on the same
        dispatcher must not collide: every route marker is optional in the compiled
        pattern, so the root path also matches the parameterized route with its
        parameter absent, and that must not be preferred over the route which needs no
        parameter at all (previously crashed with a missing-argument TypeError instead
        of a 500, since the parameterized route "won" the tie-break with the parameter
        silently missing from the call).
        """

        class Servlet(routing.RestDispatcher):
            def __init__(self) -> None:
                self.called: str | None = None
                super().__init__()

            @routing.HttpGet("")
            @routing.HttpGet("/")
            def list_root(
                self, request: AbstractHTTPServletRequest, response: AbstractHTTPServletResponse
            ) -> None:
                self.called = "root"
                response.send_content(200, "root")

            @routing.HttpGet("/<item_id:int>")
            def get_item(
                self,
                request: AbstractHTTPServletRequest,
                response: AbstractHTTPServletResponse,
                item_id: int,
            ) -> None:
                self.called = f"item:{item_id}"
                response.send_content(200, f"item:{item_id}")

        prefix = f"/routing{random.randint(0, 100)}"
        router = Servlet()
        self.http.register_servlet(prefix, router)

        for path in ("", "/"):
            router.called = None
            code, data = self.get_http_page(uri=f"{prefix}{path}")
            self.assertEqual(code, 200)
            self.assertEqual(to_str(data), "root")
            self.assertEqual(router.called, "root")

        code, data = self.get_http_page(uri=f"{prefix}/42")
        self.assertEqual(code, 200)
        self.assertEqual(to_str(data), "item:42")
        self.assertEqual(router.called, "item:42")

    def test_dispatch_optional_param_with_default(self) -> None:
        """
        A single route whose method parameter has a Python default must still be
        callable with that parameter absent (root of the servlet): the fix for the
        collision above must not break this legitimate, pre-existing use of the
        "every marker is optional" behaviour.
        """

        class Servlet(routing.RestDispatcher):
            def __init__(self) -> None:
                self.called: str | None = None
                super().__init__()

            @routing.HttpGet("/<item_id:int>")
            def get_item(
                self,
                request: AbstractHTTPServletRequest,
                response: AbstractHTTPServletResponse,
                item_id: int | None = None,
            ) -> None:
                self.called = f"item:{item_id}"
                response.send_content(200, f"item:{item_id}")

        prefix = f"/routing{random.randint(0, 100)}"
        router = Servlet()
        self.http.register_servlet(prefix, router)

        code, data = self.get_http_page(uri=f"{prefix}/")
        self.assertEqual(code, 200)
        self.assertEqual(to_str(data), "item:None")

        code, data = self.get_http_page(uri=f"{prefix}/7")
        self.assertEqual(code, 200)
        self.assertEqual(to_str(data), "item:7")

    def test_methods(self) -> None:
        """
        Tests the methods filters
        """

        class Servlet(routing.RestDispatcher):
            def __init__(self) -> None:
                super(Servlet, self).__init__()
                self.verb: str | None = None

            def reset(self) -> None:
                self.verb = None

            @routing.HttpGet("/get")
            def get(self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse) -> None:
                self.verb = req.get_command()
                resp.send_content(200, self.verb)

            @routing.HttpHead("/head")
            def head(self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse) -> None:
                self.verb = req.get_command()
                resp.send_content(200, self.verb)

            @routing.HttpPost("/post")
            def post(self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse) -> None:
                self.verb = req.get_command()
                resp.send_content(200, self.verb)

            @routing.HttpPut("/put")
            def put(self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse) -> None:
                self.verb = req.get_command()
                resp.send_content(200, self.verb)

            @routing.HttpDelete("/delete")
            def delete(self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse) -> None:
                self.verb = req.get_command()
                resp.send_content(200, self.verb)

            @routing.HttpGet("/get-head")
            @routing.HttpHead("/get-head")
            def get_head(self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse) -> None:
                self.verb = req.get_command()
                resp.send_content(200, self.verb)

            @routing.Http("/all", HTTP_METHODS)
            def all_commands(
                self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse
            ) -> None:
                self.verb = req.get_command()
                resp.send_content(200, self.verb)

        # Use a random prefix
        prefix = f"/routing{random.randint(0, 100)}"
        router = Servlet()
        self.http.register_servlet(prefix, router)

        # Try basic filtering
        for method in HTTP_METHODS:
            router.reset()
            code, data = self.get_http_page(uri=f"{prefix}/{method.lower()}", method=method)
            self.assertEqual(code, 200, method)
            self.assertEqual(router.verb, method)
            if method != "HEAD":
                # No response body in HEAD, obviously
                self.assertEqual(to_str(data), method)

            for other_method in HTTP_METHODS:
                if other_method != method:
                    # Ensure that other HTTP methods are filtered
                    code = self.get_http_code(uri=f"{prefix}/{method.lower()}", method=other_method)
                    self.assertEqual(code, 404)

        # Try with multi-commands methods
        for method in ("GET", "HEAD"):
            router.reset()
            code = self.get_http_code(uri=f"{prefix}/get-head", method=method)
            self.assertEqual(code, 200, method)
            self.assertEqual(router.verb, method)

        # All methods
        for method in HTTP_METHODS:
            router.reset()
            code = self.get_http_code(uri=f"{prefix}/all", method=method)
            self.assertEqual(code, 200, method)
            self.assertEqual(router.verb, method)

    def test_types(self) -> None:
        """
        Tests the type parsing by the dispatcher
        """

        class Servlet(routing.RestDispatcher):
            def __init__(self) -> None:
                super(Servlet, self).__init__()
                self.args: list[Any] = []

            def reset(self) -> None:
                self.args = []

            @routing.HttpGet("/basic/<value>")
            @routing.HttpGet("/interm/<value>/toto")
            @routing.HttpGet("/<value>/toto")
            def test_basic(
                self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse, value: Any
            ) -> None:
                self.args = [value]
                resp.send_content(200, "OK")

            @routing.HttpGet("/int/<value:int>")
            @routing.HttpGet("/int/<value:int>/toto")
            def test_int(
                self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse, value: int
            ) -> None:
                self.args = [value]
                resp.send_content(200, "OK")

            @routing.HttpGet("/float/<value:float>")
            @routing.HttpGet("/float/<value:float>/toto")
            def test_float(
                self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse, value: float
            ) -> None:
                self.args = [value]
                resp.send_content(200, "OK")

            @routing.HttpGet("/path/<value:path>")
            def test_path(
                self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse, value: str
            ) -> None:
                self.args = [value]
                resp.send_content(200, "OK")

            @routing.HttpGet("/uuid/<value:uuid>")
            def test_uuid(
                self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse, value: str
            ) -> None:
                self.args = [value]
                resp.send_content(200, "OK")

            @routing.HttpGet("/all/<count:int>/<temp:float>/<label:string>/<path:path>/toto")
            def all(
                self,
                req: AbstractHTTPServletRequest,
                resp: AbstractHTTPServletResponse,
                count: int,
                temp: float,
                label: str,
                path: str,
            ) -> None:
                self.args = [count, temp, label, path]
                resp.send_content(200, "OK")

            @routing.HttpGet("/opt")
            @routing.HttpGet("/opt/<toto>")
            @routing.HttpGet("/opt/<toto>/<titi>")
            def optional(
                self,
                req: AbstractHTTPServletRequest,
                resp: AbstractHTTPServletResponse,
                toto: Any = None,
                titi: Any = None,
            ) -> None:
                self.args = [toto, titi]
                resp.send_content(200, "OK")

            @routing.HttpGet("/kwarg")
            @routing.HttpGet("/kwarg/<var1:int>/<var2>")
            @routing.HttpGet("/kwarg/<var1:int>")
            @routing.HttpGet("/kwarg/<var2>")
            def keyword(
                self, req: AbstractHTTPServletRequest, resp: AbstractHTTPServletResponse, **kwargs: Any
            ) -> None:
                self.args = [arg for arg in kwargs]
                resp.send_content(200, "OK")

        # Use a random prefix
        prefix = f"/routing{random.randint(0, 100)}"
        router = Servlet()
        self.http.register_servlet(prefix, router)

        # Basic
        val: Any
        for pattern in ("/basic/{0}", "/{0}/toto", "/interm/{0}/toto"):
            for val in ("titi", "123", "a-b", "a.c", "a123"):
                path = pattern.format(val)
                router.reset()
                code = self.get_http_code(uri=f"{prefix}/{path}")
                self.assertEqual(code, 200, path)
                self.assertEqual(router.args[0], val, path)
                self.assertIsInstance(router.args[0], str, path)

        # Integers
        for pattern in ("/int/{0}", "/int/{0}/toto"):
            for val in (0, 123, -456):
                path = pattern.format(val)
                router.reset()
                code = self.get_http_code(uri=f"{prefix}/{path}")
                self.assertEqual(code, 200, path)
                self.assertEqual(router.args[0], val, path)
                self.assertIsInstance(router.args[0], int, path)

        # Float
        for pattern in ("/float/{0}", "/float/{0}/toto"):
            for val in (0.0, 0.5, 12.34, -56.78):
                path = pattern.format(val)
                router.reset()
                code = self.get_http_code(uri=f"{prefix}/{path}")
                self.assertEqual(code, 200, path)
                self.assertEqual(router.args[0], val, path)
                self.assertIsInstance(router.args[0], float, path)

        # Paths
        for val in ("simple", "root/sub", "A/B/C", "123/456/789"):
            path = f"/path/{val}"
            router.reset()
            code = self.get_http_code(uri=f"{prefix}/{path}")
            self.assertEqual(code, 200, path)
            self.assertEqual(router.args[0], val, path)
            self.assertIsInstance(router.args[0], str, path)

        # UUID
        for val in (
            uuid.uuid1(),
            uuid.uuid4(),
            uuid.uuid3(uuid.NAMESPACE_OID, "test"),
            uuid.uuid5(uuid.NAMESPACE_OID, "test"),
        ):
            path = f"/uuid/{val}"
            router.reset()
            code = self.get_http_code(uri=f"{prefix}/{path}")
            self.assertEqual(code, 200, path)
            self.assertEqual(router.args[0], val, path)
            self.assertIsInstance(router.args[0], uuid.UUID, path)

        # Optional
        for path, toto, titi in (
            ("opt", None, None),
            ("opt/123", "123", None),
            ("opt/toto/titi", "toto", "titi"),
        ):
            router.reset()
            code = self.get_http_code(uri=f"{prefix}/{path}")
            self.assertEqual(code, 200, path)
            self.assertListEqual(router.args, [toto, titi], path)

        # Keyword arguments
        for path, toto, titi in (
            ("opt", None, None),
            ("opt/123", "123", None),
            ("opt/toto/titi", "toto", "titi"),
        ):
            router.reset()
            code = self.get_http_code(uri=f"{prefix}/{path}")
            self.assertEqual(code, 200, path)
            self.assertListEqual(router.args, [toto, titi], path)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
