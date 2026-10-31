#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Cross-Origin Resource Sharing (CORS) support of the HTTP services

:author: Thomas Calmant
"""

import base64
import http.client as httplib
import importlib.util
import json
import os
import shutil
import socket
import tempfile
import time
import unittest
from email.message import Message
from typing import Any, cast

from pelix import http, services
from pelix.framework import Framework, FrameworkFactory, ServiceRegistration, create_framework
from pelix.http import cors
from pelix.ipopo.constants import (
    IPOPO_CONFIG_FACTORY_NAME,
    IPOPO_CONFIGADMIN_FACTORY_PID,
    IPOPO_INSTANCE_NAME,
    IPopoService,
)
from tests.http.utils import DEFAULT_HOST, install_ipopo

# ------------------------------------------------------------------------------

ORIGIN = "https://client.example.com"
OTHER_ORIGIN = "https://evil.example.com"

SERVER_NAME = "cors-test-server"
HANDLER_NAME = "cors-test-handler"

HAS_AIOHTTP = importlib.util.find_spec("aiohttp") is not None

# ------------------------------------------------------------------------------


class _Policy(http.CorsHandler):
    """
    Configurable policy for the unit tests
    """

    def __init__(self, origins: Any = ("*",), **kwargs: Any) -> None:
        self.policy = cors.StaticCorsHandler(origins, **kwargs)

    def get_allowed_origins(self, path: str):
        return self.policy.get_allowed_origins(path)

    def get_allowed_methods(self, path: str):
        return self.policy.get_allowed_methods(path)

    def get_allowed_headers(self, path: str):
        return self.policy.get_allowed_headers(path)

    def get_exposed_headers(self, path: str):
        return self.policy.get_exposed_headers(path)

    def allows_credentials(self, path: str) -> bool:
        return self.policy.allows_credentials(path)

    def get_max_age(self, path: str):
        return self.policy.get_max_age(path)


class ComputeCorsHeadersTest(unittest.TestCase):
    """
    Tests the computation of the CORS headers, without any server
    """

    def test_wildcard(self) -> None:
        """
        A wildcard policy without credentials sends a wildcard
        """
        headers = cors.compute_cors_headers(_Policy("*"), "/", ORIGIN)
        self.assertEqual(headers, {"Access-Control-Allow-Origin": "*"})

    def test_allow_list(self) -> None:
        """
        An allow list sends the origin back, and only if it is listed
        """
        policy = _Policy([ORIGIN, "https://other.example.com"])
        headers = cors.compute_cors_headers(policy, "/", ORIGIN)
        self.assertEqual(headers, {"Access-Control-Allow-Origin": ORIGIN, "Vary": "Origin"})

        self.assertIsNone(cors.compute_cors_headers(policy, "/", OTHER_ORIGIN))

    def test_no_origin_allowed(self) -> None:
        """
        An empty allow list refuses everything
        """
        for origins in (None, [], ""):
            with self.subTest(origins=origins):
                self.assertIsNone(cors.compute_cors_headers(_Policy(origins), "/", ORIGIN))

    def test_credentials(self) -> None:
        """
        With credentials, the origin is always sent back, never a wildcard
        """
        headers = cors.compute_cors_headers(_Policy("*", credentials=True), "/", ORIGIN)
        assert headers is not None
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(headers["Access-Control-Allow-Credentials"], "true")
        self.assertEqual(headers["Vary"], "Origin")

    def test_exposed_headers(self) -> None:
        """
        Exposed headers are only sent in actual responses
        """
        policy = _Policy("*", expose_headers="X-Total, X-Page")
        headers = cors.compute_cors_headers(policy, "/", ORIGIN)
        assert headers is not None
        self.assertEqual(headers["Access-Control-Expose-Headers"], "X-Total, X-Page")

        headers = cors.compute_cors_headers(policy, "/", ORIGIN, True, "GET")
        assert headers is not None
        self.assertNotIn("Access-Control-Expose-Headers", headers)

    def test_preflight_defaults(self) -> None:
        """
        Without explicit methods and headers, a preflight allows the requested ones
        """
        headers = cors.compute_cors_headers(_Policy("*"), "/", ORIGIN, True, "put", "X-Token, Content-Type")
        assert headers is not None
        self.assertEqual(headers["Access-Control-Allow-Methods"], "PUT")
        self.assertEqual(headers["Access-Control-Allow-Headers"], "X-Token, Content-Type")
        self.assertNotIn("Access-Control-Max-Age", headers)

    def test_preflight_explicit(self) -> None:
        """
        Explicit methods, headers and max age are sent as configured
        """
        policy = _Policy("*", methods="get, post", headers=["X-Token"], max_age=600)
        headers = cors.compute_cors_headers(policy, "/", ORIGIN, True, "POST", "X-Other")
        assert headers is not None
        self.assertEqual(headers["Access-Control-Allow-Methods"], "GET, POST")
        self.assertEqual(headers["Access-Control-Allow-Headers"], "X-Token")
        self.assertEqual(headers["Access-Control-Max-Age"], "600")

        # A method which is not allowed refuses the preflight
        self.assertIsNone(cors.compute_cors_headers(policy, "/", ORIGIN, True, "DELETE"))

    def test_resolve(self) -> None:
        """
        Tests the decision taken for a request
        """
        policy = _Policy(ORIGIN)

        # Not a cross-origin request, or no policy
        self.assertIsNone(cors.resolve_cors(policy, "/", "GET", None, None, None))
        self.assertIsNone(cors.resolve_cors(None, "/", "GET", ORIGIN, None, None))

        decision = cors.resolve_cors(policy, "/", "GET", ORIGIN, None, None)
        assert decision is not None
        self.assertFalse(decision.preflight)
        self.assertTrue(decision.allowed)

        # An OPTIONS request is only a preflight if it announces a method
        decision = cors.resolve_cors(policy, "/", "OPTIONS", ORIGIN, None, None)
        assert decision is not None
        self.assertFalse(decision.preflight)

        decision = cors.resolve_cors(policy, "/", "OPTIONS", OTHER_ORIGIN, "GET", None)
        assert decision is not None
        self.assertTrue(decision.preflight)
        self.assertFalse(decision.allowed)

    def test_policy_from_parameters(self) -> None:
        """
        A servlet declares its own policy by setting the allowed origins
        """
        self.assertIsNone(cors.policy_from_parameters({}))
        self.assertIsNone(cors.policy_from_parameters({http.HTTP_CORS_CREDENTIALS: True}))

        policy = cors.policy_from_parameters(
            {
                http.HTTP_CORS_ORIGINS: ORIGIN,
                http.HTTP_CORS_METHODS: ["get"],
                http.HTTP_CORS_CREDENTIALS: "true",
                http.HTTP_CORS_MAX_AGE: "-5",
            }
        )
        assert policy is not None
        self.assertEqual(list(policy.get_allowed_origins("/")), [ORIGIN])
        self.assertEqual(policy.get_allowed_methods("/"), ["GET"])
        self.assertTrue(policy.allows_credentials("/"))
        self.assertEqual(policy.get_max_age("/"), 0)

        # An explicit empty list refuses every origin
        policy = cors.policy_from_parameters({http.HTTP_CORS_ORIGINS: []})
        assert policy is not None
        self.assertEqual(list(policy.get_allowed_origins("/")), [])


# ------------------------------------------------------------------------------


class SyncServlet:
    """
    Synchronous servlet
    """

    def __init__(self) -> None:
        self.options_called = False

    def do_GET(self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse):
        response.send_content(200, "OK", "text/plain")

    def do_POST(self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse):
        # The servlet decides of its own CORS headers
        response.set_header("Access-Control-Allow-Origin", "https://custom.example.com")
        response.send_content(200, "Custom", "text/plain")

    def do_PUT(self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse):
        raise ValueError("Expected error")

    def do_OPTIONS(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ):
        self.options_called = True
        response.send_content(200, "Options", "text/plain")


class AsyncServlet:
    """
    Asynchronous servlet
    """

    def __init__(self) -> None:
        self.options_called = False

    async def do_async_GET(
        self, request: http.AbstractAsyncHTTPServletRequest, response: http.AbstractAsyncHTTPServletResponse
    ):
        await response.send_content(200, "OK", "text/plain")

    async def do_async_POST(
        self, request: http.AbstractAsyncHTTPServletRequest, response: http.AbstractAsyncHTTPServletResponse
    ):
        response.set_header("Access-Control-Allow-Origin", "https://custom.example.com")
        await response.send_content(200, "Custom", "text/plain")

    async def do_async_PUT(
        self, request: http.AbstractAsyncHTTPServletRequest, response: http.AbstractAsyncHTTPServletResponse
    ):
        raise ValueError("Expected error")

    async def do_async_OPTIONS(
        self, request: http.AbstractAsyncHTTPServletRequest, response: http.AbstractAsyncHTTPServletResponse
    ):
        self.options_called = True
        await response.send_content(200, "Options", "text/plain")


class EchoServlet:
    """
    Tells who the client is, sets cookies and a header twice
    """

    @staticmethod
    def describe(request: Any, cookies: dict[str, str]) -> str:
        return json.dumps([request.get_client_address()[0], request.is_secure(), cookies])

    @staticmethod
    def prepare(response: Any) -> None:
        response.add_cookie("a", "1")
        response.add_cookie("b", "2", secure=True)
        response.set_header("X-Once", "1")
        response.set_header("X-Once", "2")

    def do_GET(self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse):
        self.prepare(response)
        response.send_content(200, self.describe(request, request.get_cookies()), "application/json")


class AsyncEchoServlet(EchoServlet):
    async def do_async_GET(
        self, request: http.AbstractAsyncHTTPServletRequest, response: http.AbstractAsyncHTTPServletResponse
    ):
        self.prepare(response)
        await response.send_content(
            200, self.describe(request, await request.get_cookies()), "application/json"
        )


class WebSocketHandler(http.WebSocketHandler):
    """
    Accepts all WebSocket connections
    """

    async def ws_accept(self, request: Any) -> bool:
        return True

    async def ws_open(self, session: Any, request: Any) -> None:
        pass

    async def ws_message(self, session: Any, data: str) -> None:
        pass

    async def ws_binary(self, session: Any, data: bytes) -> None:
        pass

    async def ws_error(self, session: Any, error: str) -> None:
        pass

    async def ws_close(self, session: Any, code: int, reason: str) -> None:
        pass


# ------------------------------------------------------------------------------


class _CorsServerTests:
    """
    CORS tests against a live HTTP service, run for each kind of server and
    servlet
    """

    http_bundle = "pelix.http.basic"
    http_factory = http.FACTORY_HTTP_BASIC
    async_servlet = False

    framework: Framework
    ipopo: IPopoService
    port: int
    servlet: Any
    registration: ServiceRegistration[Any]

    # Provided by unittest.TestCase
    assertEqual: Any
    assertIn: Any
    assertIsNone: Any
    assertNotIn: Any
    assertTrue: Any
    assertFalse: Any
    assertLogs: Any
    subTest: Any

    def setUp(self) -> None:
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.framework.install_bundle(self.http_bundle).start()
        self.framework.install_bundle("pelix.http.cors").start()
        self.start_server()

    def tearDown(self) -> None:
        FrameworkFactory.delete_framework()

    def start_server(self, **properties: Any) -> None:
        """
        (Re)starts the HTTP service

        :param properties: Extra properties of the HTTP service
        """
        if self.ipopo.is_registered_instance(SERVER_NAME):
            self.ipopo.kill(SERVER_NAME)

        svc = self.ipopo.instantiate(
            self.http_factory,
            SERVER_NAME,
            {http.HTTP_SERVICE_ADDRESS: DEFAULT_HOST, http.HTTP_SERVICE_PORT: 0, **properties},
        )
        self.port = svc.get_access()[1]

    def register_servlet(self, properties: dict[str, Any] | None = None) -> None:
        """
        Registers the test servlet on /test

        :param properties: Extra service properties
        """
        context = self.framework.get_bundle_context()
        if self.async_servlet:
            self.servlet = AsyncServlet()
            spec = http.HTTP_SERVLET_ASYNC
            path_prop = http.HTTP_SERVLET_ASYNC_PATH
        else:
            self.servlet = SyncServlet()
            spec = http.HTTP_SERVLET
            path_prop = http.HTTP_SERVLET_PATH

        self.registration = context.register_service(
            spec, self.servlet, {path_prop: "/test", **(properties or {})}
        )

    def add_handler(self, **properties: Any) -> None:
        """
        Instantiates a global CORS handler

        :param properties: CORS handler properties
        """
        self.ipopo.instantiate(http.FACTORY_HTTP_CORS, HANDLER_NAME, properties)

    def request(
        self, method: str = "GET", uri: str = "/test", headers: dict[str, str] | None = None
    ) -> tuple[int, Message, bytes]:
        """
        Sends a request and returns the status, headers and body of the answer
        """
        conn = httplib.HTTPConnection(DEFAULT_HOST, self.port)
        try:
            conn.request(method, uri, None, headers or {})
            response = conn.getresponse()
            return response.status, response.msg, response.read()
        finally:
            conn.close()

    def check_statuses(self, cases: list[tuple[str, dict[str, str]]], expected: list[int]) -> None:
        """
        Sends (method, headers) requests on /test and compares their status codes
        """
        self.assertEqual([self.request(method, headers=headers)[0] for method, headers in cases], expected)

    def preflight(
        self, uri: str = "/test", origin: str = ORIGIN, method: str = "PUT", headers: str | None = None
    ) -> tuple[int, Message, bytes]:
        """
        Sends a preflight request
        """
        request_headers = {"Origin": origin, "Access-Control-Request-Method": method}
        if headers:
            request_headers["Access-Control-Request-Headers"] = headers
        return self.request("OPTIONS", uri, request_headers)

    def test_no_handler(self) -> None:
        """
        Without a CORS policy, a foreign origin is refused, unless
        pelix.http.cors.enforce is off: then nothing changes
        """
        self.register_servlet()
        self.assertEqual(self.request(headers={"Origin": ORIGIN})[0], 403)

        self.start_server(**{http.HTTP_CORS_ENFORCE: False})
        status, headers, _ = self.request(headers={"Origin": ORIGIN})
        self.assertEqual(status, 200)
        self.assertIsNone(headers["Access-Control-Allow-Origin"])

        # The preflight reaches the servlet
        status, headers, _ = self.preflight()
        self.assertEqual(status, 200)
        self.assertIsNone(headers["Access-Control-Allow-Origin"])
        self.assertTrue(self.servlet.options_called)

    def test_same_origin(self) -> None:
        """
        A request without origin gets no CORS header
        """
        self.register_servlet()
        self.add_handler(**{http.HTTP_CORS_ORIGINS: "*"})

        status, headers, _ = self.request()
        self.assertEqual(status, 200)
        self.assertIsNone(headers["Access-Control-Allow-Origin"])

    def test_simple_request(self) -> None:
        """
        Simple requests get the headers of the policy
        """
        self.register_servlet()
        self.add_handler(**{http.HTTP_CORS_ORIGINS: [ORIGIN], http.HTTP_CORS_EXPOSE_HEADERS: "X-Total"})

        status, headers, body = self.request(headers={"Origin": ORIGIN})
        self.assertEqual(status, 200)
        self.assertEqual(body, b"OK")
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(headers["Vary"], "Origin")
        self.assertEqual(headers["Access-Control-Expose-Headers"], "X-Total")

        # Refused origin, without pelix.http.cors.enforce: the request is handled,
        # but the browser won't let the script read it
        self.start_server(**{http.HTTP_CORS_ENFORCE: False})
        status, headers, _ = self.request(headers={"Origin": OTHER_ORIGIN})
        self.assertEqual(status, 200)
        self.assertIsNone(headers["Access-Control-Allow-Origin"])

    def test_credentials(self) -> None:
        """
        Credentials force the origin to be sent back
        """
        self.register_servlet()
        self.add_handler(**{http.HTTP_CORS_ORIGINS: "*", http.HTTP_CORS_CREDENTIALS: True})

        _, headers, _ = self.request(headers={"Origin": ORIGIN})
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(headers["Access-Control-Allow-Credentials"], "true")

    def test_servlet_headers_are_kept(self) -> None:
        """
        The CORS headers set by a servlet are not replaced
        """
        self.register_servlet()
        self.add_handler(**{http.HTTP_CORS_ORIGINS: "*"})

        status, headers, _ = self.request("POST", headers={"Origin": ORIGIN})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_all("Access-Control-Allow-Origin"), ["https://custom.example.com"])

    def test_preflight(self) -> None:
        """
        Preflight requests are answered by the server
        """
        self.register_servlet()
        self.add_handler(
            **{
                http.HTTP_CORS_ORIGINS: [ORIGIN],
                http.HTTP_CORS_METHODS: ["GET", "PUT"],
                http.HTTP_CORS_HEADERS: "X-Token",
                http.HTTP_CORS_MAX_AGE: 300,
            }
        )

        status, headers, body = self.preflight(headers="X-Token")
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(headers["Access-Control-Allow-Methods"], "GET, PUT")
        self.assertEqual(headers["Access-Control-Allow-Headers"], "X-Token")
        self.assertEqual(headers["Access-Control-Max-Age"], "300")
        self.assertFalse(self.servlet.options_called, "Preflight reached the servlet")

        # Unknown path: the preflight is answered all the same
        status, headers, _ = self.preflight("/unknown")
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)

        # Refused origin or method
        for origin, method in ((OTHER_ORIGIN, "GET"), (ORIGIN, "DELETE")):
            status, headers, _ = self.preflight(origin=origin, method=method)
            self.assertEqual(status, 403)
            self.assertIsNone(headers["Access-Control-Allow-Origin"])

        # An OPTIONS request which is not a preflight reaches the servlet
        status, _, _ = self.request("OPTIONS", headers={"Origin": ORIGIN})
        self.assertEqual(status, 200)
        self.assertTrue(self.servlet.options_called)

    def test_error_pages(self) -> None:
        """
        Error pages carry the CORS headers too, so that the client can read them
        """
        self.register_servlet()
        self.add_handler(**{http.HTTP_CORS_ORIGINS: "*"})

        status, headers, _ = self.request(uri="/unknown", headers={"Origin": ORIGIN})
        self.assertEqual(status, 404)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")

        status, headers, _ = self.request(uri="/test/../../etc", headers={"Origin": ORIGIN})
        self.assertEqual(status, 400)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")

        with self.assertLogs(level="ERROR"):
            status, headers, _ = self.request("PUT", headers={"Origin": ORIGIN})
        self.assertEqual(status, 500)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")

    def test_servlet_policy(self) -> None:
        """
        A servlet can declare its own policy, which replaces the global one
        """
        self.add_handler(**{http.HTTP_CORS_ORIGINS: "*"})
        self.register_servlet({http.HTTP_CORS_ORIGINS: ORIGIN, http.HTTP_CORS_CREDENTIALS: True})

        _, headers, _ = self.request(headers={"Origin": ORIGIN})
        self.assertEqual(headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(headers["Access-Control-Allow-Credentials"], "true")

        _, headers, _ = self.request(headers={"Origin": OTHER_ORIGIN})
        self.assertIsNone(headers["Access-Control-Allow-Origin"])

        status, _, _ = self.preflight(origin=OTHER_ORIGIN)
        self.assertEqual(status, 403)

        # Other paths still follow the global policy
        _, headers, _ = self.request(uri="/unknown", headers={"Origin": OTHER_ORIGIN})
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")

        # Updating the servlet properties updates its policy
        properties = self.registration.get_reference().get_properties()
        properties[http.HTTP_CORS_ORIGINS] = []
        self.registration.set_properties(properties)

        _, headers, _ = self.request(headers={"Origin": ORIGIN})
        self.assertIsNone(headers["Access-Control-Allow-Origin"])

    def test_servlet_policy_without_handler(self) -> None:
        """
        A servlet policy applies even without a global CORS handler
        """
        self.register_servlet({http.HTTP_CORS_ORIGINS: "*"})

        _, headers, _ = self.request(headers={"Origin": ORIGIN})
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")

        status, headers, _ = self.preflight()
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Methods"], "PUT")

    def test_handler_update(self) -> None:
        """
        The properties of the CORS handler component can be updated
        """
        self.register_servlet()
        self.add_handler(**{http.HTTP_CORS_ORIGINS: [ORIGIN]})

        _, headers, _ = self.request(headers={"Origin": OTHER_ORIGIN})
        self.assertIsNone(headers["Access-Control-Allow-Origin"])

        context = self.framework.get_bundle_context()
        reference = context.get_service_reference(http.CorsHandler)
        assert reference is not None
        handler = cast(cors.CorsHandlerComponent, context.get_service(reference))
        handler._origins = [ORIGIN, OTHER_ORIGIN]

        _, headers, _ = self.request(headers={"Origin": OTHER_ORIGIN})
        self.assertEqual(headers["Access-Control-Allow-Origin"], OTHER_ORIGIN)

    def test_origin_enforced(self) -> None:
        """
        With pelix.http.cors.enforce (default), the servlet doesn't run for a foreign origin
        """
        self.register_servlet()
        self.add_handler(**{http.HTTP_CORS_ORIGINS: [ORIGIN]})
        own = f"http://{DEFAULT_HOST}:{self.port}"
        preflight = {"Access-Control-Request-Method": "PUT"}
        self.check_statuses(
            [
                ("GET", {"Origin": OTHER_ORIGIN}),
                ("POST", {"Origin": OTHER_ORIGIN}),
                # Sandboxed pages and redirects
                ("POST", {"Origin": "null"}),
                ("GET", {"Origin": ORIGIN}),
                # Not a browser
                ("GET", {}),
                # Browsers send Origin on same-origin POST too
                ("GET", {"Origin": own}),
                ("GET", {"Origin": f"http://{DEFAULT_HOST}:{self.port + 1}"}),
                ("OPTIONS", {"Origin": ORIGIN, **preflight}),
                ("OPTIONS", {"Origin": OTHER_ORIGIN, **preflight}),
            ],
            [403, 403, 403, 200, 200, 200, 403, 204, 403],
        )

    def test_cookies_and_proxies(self) -> None:
        """
        Cookies, repeated headers, and the client told by the trusted proxies only
        """
        self.register_servlet()
        context = self.framework.get_bundle_context()
        if self.async_servlet:
            context.register_service(
                http.HTTP_SERVLET_ASYNC, AsyncEchoServlet(), {http.HTTP_SERVLET_ASYNC_PATH: "/echo"}
            )
        else:
            context.register_service(http.HTTP_SERVLET, EchoServlet(), {http.HTTP_SERVLET_PATH: "/echo"})

        status, headers, body = self.request(uri="/echo", headers={"Cookie": "x=1; y=2"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)[2], {"x": "1", "y": "2"})
        self.assertEqual(
            headers.get_all("Set-Cookie"),
            ["a=1; Path=/; SameSite=Lax; HttpOnly", "b=2; Path=/; SameSite=Lax; Secure; HttpOnly"],
        )
        # set_header replaces, whatever the service
        self.assertEqual(headers.get_all("X-Once"), ["2"])

        proxied = {"X-Forwarded-For": "6.6.6.6, 1.2.3.4", "X-Forwarded-Proto": "https"}
        behind_tls = {"Host": "meme.example.com", "Origin": "https://meme.example.com", **proxied}
        # Ignored from an untrusted peer
        client, secure, _ = json.loads(self.request(uri="/echo", headers=proxied)[2])
        self.assertNotIn(client, ("6.6.6.6", "1.2.3.4"))
        self.assertFalse(secure)
        self.assertEqual(self.request(headers=behind_tls)[0], 403)

        # The proxy keeps the public Host, which a loopback service must accept explicitly
        self.start_server(
            **{
                http.HTTP_PROXY_TRUSTED: "127.0.0.0/8, ::1",
                http.HTTP_ALLOWED_HOSTS: f"meme.example.com, {DEFAULT_HOST}",
            }
        )
        self.assertEqual(json.loads(self.request(uri="/echo", headers=proxied)[2])[:2], ["1.2.3.4", True])
        # The browser sends an https Origin, while the service only sees clear text
        self.assertEqual(self.request(headers=behind_tls)[0], 200)
        self.assertEqual(self.request(headers={**behind_tls, "Origin": "https://evil.example.com"})[0], 403)

    def test_allowed_hosts(self) -> None:
        """
        pelix.http.allowed_hosts refuses the other Host headers, on any path
        """
        self.register_servlet()
        rebound = [("GET", {"Host": "rebound.example"})]
        # By default, a server bound to a loopback address only accepts the loopback names
        self.check_statuses(
            [
                *rebound,
                ("GET", {"Host": f"{DEFAULT_HOST}:{self.port}"}),
                ("GET", {"Host": f"127.0.0.1:{self.port}"}),
                ("GET", {"Host": f"[::1]:{self.port}"}),
            ],
            [403, 200, 200, 200],
        )
        # Not checked when empty
        self.start_server(**{http.HTTP_ALLOWED_HOSTS: ""})
        self.check_statuses(rebound, [200])

        self.start_server(**{http.HTTP_ALLOWED_HOSTS: f"Example.com, {DEFAULT_HOST}, other.example:8080"})
        self.check_statuses(
            [
                *rebound,
                ("GET", {"Host": f"rebound.example:{self.port}"}),
                ("GET", {"Host": f"{DEFAULT_HOST}:{self.port}"}),
                ("GET", {"Host": "example.COM"}),
                ("GET", {"Host": "example.com:1234"}),
                # An entry with a port only matches this port
                ("GET", {"Host": "other.example:8080"}),
                ("GET", {"Host": "other.example:9090"}),
                ("GET", {"Host": "other.example"}),
            ],
            [403, 403, 200, 200, 200, 200, 403, 403],
        )
        self.assertEqual(self.request(uri="/unknown", headers={"Host": "rebound.example"})[0], 403)

        # An HTTP/1.0 request without Host can't be checked
        conn = httplib.HTTPConnection(DEFAULT_HOST, self.port, timeout=5)
        try:
            conn.putrequest("GET", "/test", skip_host=True)
            conn.endheaders()
            response = conn.getresponse()
            response.read()
            # aiohttp refuses it by itself, with a 400
            self.assertIn(response.status, (400, 403))
        finally:
            conn.close()

    def test_live_update(self) -> None:
        """
        An update of the header checks (e.g. by ConfigurationAdmin, with the default reconfigure
        policy) applies to the running server; the address and the port need a restart
        """
        self.register_servlet()
        rebound = {"Host": "rebound.example", "Origin": "http://rebound.example"}
        self.assertEqual(self.request(headers=rebound)[0], 403)

        port = self.port
        for properties, expected in (
            ({http.HTTP_ALLOWED_HOSTS: f"rebound.example, {DEFAULT_HOST}"}, 200),
            ({http.HTTP_ALLOWED_HOSTS: None}, 403),
            ({http.HTTP_ALLOWED_HOSTS: "", http.HTTP_CORS_ENFORCE: "true"}, 200),
            (
                {http.HTTP_ALLOWED_HOSTS: "", http.HTTP_CORS_ENFORCE: "true", http.HTTP_MAX_BODY_SIZE: "10"},
                200,
            ),
        ):
            with self.subTest(properties=properties):
                self.ipopo.reconfigure(SERVER_NAME, properties)
                self.assertEqual(self.request(headers=rebound)[0], expected)
        self.assertEqual(self.request(headers={"Origin": OTHER_ORIGIN})[0], 403)
        self.ipopo.reconfigure(SERVER_NAME, {http.HTTP_CORS_ENFORCE: "false"})
        self.assertEqual(self.request(headers={"Origin": OTHER_ORIGIN})[0], 200)

        # The server keeps its port, and the component says so
        with self.assertLogs(SERVER_NAME, "WARNING"):
            self.ipopo.reconfigure(SERVER_NAME, {http.HTTP_SERVICE_PORT: port + 1})
        details = self.ipopo.get_instance_details(SERVER_NAME)
        self.assertEqual(str(details["properties"][http.HTTP_SERVICE_PORT]), str(port))
        self.assertEqual(self.request()[0], 200)


class BasicCorsTest(_CorsServerTests, unittest.TestCase):
    """
    CORS on the basic HTTP service
    """


class ConfigAdminHostsTest(unittest.TestCase):
    """
    The allowed hosts of an HTTP service created by a ConfigurationAdmin factory configuration
    """

    def test_update(self) -> None:
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        framework = create_framework(
            (
                "pelix.ipopo.core",
                "pelix.ipopo.waiting",
                "pelix.services.configadmin",
                "pelix.ipopo.configadmin",
                "pelix.http.basic",
            ),
            {"configuration.folder": folder},
        )
        self.addCleanup(FrameworkFactory.delete_framework)
        framework.start()
        context = framework.get_bundle_context()
        config_admin = context.get_service(
            cast(Any, context.get_service_reference(services.IConfigurationAdmin))
        )

        # A free port, given explicitly: the configuration must match the running server
        with socket.socket() as sock:
            sock.bind((DEFAULT_HOST, 0))
            port = sock.getsockname()[1]

        properties = {
            IPOPO_CONFIG_FACTORY_NAME: http.FACTORY_HTTP_BASIC,
            IPOPO_INSTANCE_NAME: SERVER_NAME,
            http.HTTP_SERVICE_ADDRESS: DEFAULT_HOST,
            http.HTTP_SERVICE_PORT: port,
        }
        config = config_admin.create_factory_configuration(IPOPO_CONFIGADMIN_FACTORY_PID)
        config.update(properties)
        context.register_service(http.HTTP_SERVLET, SyncServlet(), {http.HTTP_SERVLET_PATH: "/test"})

        def status() -> int | None:
            conn = httplib.HTTPConnection(DEFAULT_HOST, port, timeout=5)
            try:
                conn.request("GET", "/test", headers={"Host": "app.example.com"})
                return conn.getresponse().status
            except OSError:
                return None
            finally:
                conn.close()

        for update, expected in (({}, 403), ({http.HTTP_ALLOWED_HOSTS: "app.example.com"}, 200), (None, 403)):
            with self.subTest(update=update):
                if update is not None:
                    config.update({**properties, **update})
                else:
                    # Back to the default allowed hosts
                    config.update(properties)
                deadline = time.monotonic() + 5
                while status() != expected and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertEqual(status(), expected)


@unittest.skipUnless(HAS_AIOHTTP, "aiohttp not installed")
class AsyncSyncServletCorsTest(_CorsServerTests, unittest.TestCase):
    """
    CORS on the async HTTP service, with synchronous servlets
    """

    http_bundle = "pelix.http.basic_async"
    http_factory = http.FACTORY_HTTP_ASYNC


@unittest.skipUnless(HAS_AIOHTTP, "aiohttp not installed")
class AsyncCorsTest(_CorsServerTests, unittest.TestCase):
    """
    CORS on the async HTTP service, with asynchronous servlets
    """

    http_bundle = "pelix.http.basic_async"
    http_factory = http.FACTORY_HTTP_ASYNC
    async_servlet = True

    def test_websocket_handshake(self) -> None:
        """
        The WebSocket handshake carries the CORS headers
        """
        self.add_handler(**{http.HTTP_CORS_ORIGINS: [ORIGIN]})
        self.framework.get_bundle_context().register_service(
            http.HTTP_WEBSOCKET_HANDLER, WebSocketHandler(), {http.HTTP_WEBSOCKET_PATH: "/ws"}
        )

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET /ws HTTP/1.1\r\n"
            f"Host: {DEFAULT_HOST}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"Origin: {ORIGIN}\r\n"
            "\r\n"
        )

        with socket.create_connection((DEFAULT_HOST, self.port), timeout=5) as sock:
            sock.sendall(request.encode("ascii"))
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk

        head = data.split(b"\r\n\r\n", 1)[0].decode("latin-1").lower()
        self.assertIn(" 101 ", head.splitlines()[0])
        self.assertIn(f"access-control-allow-origin: {ORIGIN}", head)


if __name__ == "__main__":
    unittest.main()
