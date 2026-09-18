#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the authentication support of the HTTP services

:author: Thomas Calmant
"""

import base64
import http.client as httplib
import importlib.util
import logging
import pathlib
import shutil
import tempfile
import unittest
from email.message import Message
from typing import Any

from pelix import http
from pelix.framework import Framework, FrameworkFactory
from pelix.http import auth
from pelix.ipopo.constants import IPopoService
from pelix.security import (
    FACTORY_HTPASSWD,
    PROP_HTPASSWD_FILE,
    PROP_HTPASSWD_GROUPS,
    AuthenticationFailed,
    UsernamePassword,
    get_current_subject,
)
from pelix.security.decorators import AllowGroup
from tests.http.utils import DEFAULT_HOST, install_ipopo

# ------------------------------------------------------------------------------

# "abc", as htpasswd -s writes it
ABC_SHA1 = "{SHA}qZk+NkcGgWq6PiVxeFDCbJzQ2J0="

SERVER_NAME = "auth-test-server"

HAS_AIOHTTP = importlib.util.find_spec("aiohttp") is not None


def basic(username: str, password: str) -> dict[str, str]:
    """
    Returns the headers of a request with Basic credentials
    """
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


# ------------------------------------------------------------------------------


class BasicHttpAuthenticatorTest(unittest.TestCase):
    """
    Tests the extraction of Basic credentials, without any server
    """

    def setUp(self) -> None:
        self.authenticator = auth.BasicHttpAuthenticator()

    def test_extraction(self) -> None:
        """
        Valid credentials are extracted, whatever the case of the scheme
        """
        credentials = self.authenticator.extract_credentials(basic("alice", "p:a:ss"))
        self.assertEqual(credentials, UsernamePassword("alice", "p:a:ss"))

        headers = {"Authorization": "basic " + base64.b64encode("élodie:mot".encode()).decode()}
        credentials = self.authenticator.extract_credentials(headers)
        self.assertEqual(credentials, UsernamePassword("élodie", "mot"))

    def test_other_schemes(self) -> None:
        """
        Other schemes and missing headers are ignored
        """
        for headers in ({}, {"Authorization": ""}, {"Authorization": "Bearer abc"}):
            with self.subTest(headers=headers):
                self.assertIsNone(self.authenticator.extract_credentials(headers))

    def test_malformed(self) -> None:
        """
        Malformed credentials are refused
        """
        for token in (
            "not base64!",
            base64.b64encode(b"no-colon").decode(),
            base64.b64encode(b":pwd").decode(),
        ):
            with self.subTest(token=token), self.assertRaises(AuthenticationFailed):
                self.authenticator.extract_credentials({"Authorization": f"Basic {token}"})

    def test_challenge(self) -> None:
        """
        The realm is quoted in the challenge
        """
        self.assertEqual(
            self.authenticator.get_challenge('My "realm"'), 'Basic realm="My \\"realm\\"", charset="UTF-8"'
        )


# ------------------------------------------------------------------------------


class SyncServlet:
    """
    Synchronous servlet answering with the name of the current subject
    """

    def do_GET(self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse):
        subject = get_current_subject()
        response.send_content(200, f"{subject.name}|{subject.method}", "text/plain")

    @AllowGroup("ops")
    def do_POST(self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse):
        response.send_content(200, "posted", "text/plain")


class AsyncServlet:
    """
    Asynchronous servlet answering with the name of the current subject
    """

    async def do_async_GET(
        self, request: http.AbstractAsyncHTTPServletRequest, response: http.AbstractAsyncHTTPServletResponse
    ):
        subject = get_current_subject()
        await response.send_content(200, f"{subject.name}|{subject.method}", "text/plain")

    @AllowGroup("ops")
    async def do_async_POST(
        self, request: http.AbstractAsyncHTTPServletRequest, response: http.AbstractAsyncHTTPServletResponse
    ):
        await response.send_content(200, "posted", "text/plain")


class _AuthServerTests:
    """
    Authentication tests against a live HTTP service, run for each kind of
    server and servlet
    """

    http_bundle = "pelix.http.basic"
    http_factory = http.FACTORY_HTTP_BASIC
    async_servlet = False

    framework: Framework
    ipopo: IPopoService
    port: int
    folder: pathlib.Path

    # Provided by unittest.TestCase
    addCleanup: Any
    assertEqual: Any
    assertIn: Any
    assertIsNone: Any
    assertLogs: Any
    assertNotIn: Any
    subTest: Any

    def setUp(self) -> None:
        self.folder = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        users = self.folder / ".htpasswd"
        users.write_text(f"alice:{ABC_SHA1}\nbob:{ABC_SHA1}\n")
        users.chmod(0o600)
        groups = self.folder / ".htgroup"
        groups.write_text("ops: alice\n")

        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.addCleanup(FrameworkFactory.delete_framework)
        self.ipopo = install_ipopo(self.framework)
        for bundle in (self.http_bundle, "pelix.http.auth", "pelix.security.core", "pelix.security.htpasswd"):
            self.framework.install_bundle(bundle).start()

        self.ipopo.instantiate(
            FACTORY_HTPASSWD, "htpasswd", {PROP_HTPASSWD_FILE: str(users), PROP_HTPASSWD_GROUPS: str(groups)}
        )

    def start_server(
        self,
        required: bool = False,
        with_authenticator: bool = True,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """
        Starts the HTTP service and registers the test servlet on /test
        """
        if with_authenticator:
            self.ipopo.instantiate(http.FACTORY_HTTP_AUTH_BASIC, "basic-auth", {})

        svc = self.ipopo.instantiate(
            self.http_factory,
            SERVER_NAME,
            {
                http.HTTP_SERVICE_ADDRESS: DEFAULT_HOST,
                http.HTTP_SERVICE_PORT: 0,
                http.HTTP_AUTH_REQUIRED: required,
                **(properties or {}),
            },
        )
        self.port = svc.get_access()[1]
        self.register_servlet("/test")

    def register_servlet(self, path: str, properties: dict[str, Any] | None = None) -> None:
        """
        Registers a test servlet
        """
        context = self.framework.get_bundle_context()
        if self.async_servlet:
            context.register_service(
                http.HTTP_SERVLET_ASYNC,
                AsyncServlet(),
                {http.HTTP_SERVLET_ASYNC_PATH: path, **(properties or {})},
            )
        else:
            context.register_service(
                http.HTTP_SERVLET, SyncServlet(), {http.HTTP_SERVLET_PATH: path, **(properties or {})}
            )

    def request(
        self, method: str = "GET", uri: str = "/test", headers: dict[str, str] | None = None
    ) -> tuple[int, Message, str]:
        """
        Sends a request and returns the status, headers and body of the answer
        """
        conn = httplib.HTTPConnection(DEFAULT_HOST, self.port)
        try:
            conn.request(method, uri, None, headers or {})
            response = conn.getresponse()
            return response.status, response.msg, response.read().decode("utf-8")
        finally:
            conn.close()

    def test_anonymous(self) -> None:
        """
        Without requirement, requests are handled as anonymous
        """
        self.start_server()

        status, headers, body = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(body, "anonymous|None")
        self.assertIsNone(headers["WWW-Authenticate"])

    def test_optional_credentials(self) -> None:
        """
        Credentials are checked even if they are not required
        """
        self.start_server()

        status, _, body = self.request(headers=basic("alice", "abc"))
        self.assertEqual(status, 200)
        self.assertEqual(body, "alice|basic")

        # Wrong credentials are refused, as the client expects to be authenticated
        status, headers, _ = self.request(headers=basic("alice", "wrong"))
        self.assertEqual(status, 401)
        self.assertIn('realm="Pelix"', headers["WWW-Authenticate"])

    def test_required(self) -> None:
        """
        Requests without valid credentials are refused when they are required
        """
        self.start_server(True, properties={http.HTTP_AUTH_REALM: "Secret"})

        for request_headers in (
            None,
            basic("alice", "wrong"),
            basic("nobody", "abc"),
            {"Authorization": "Basic !"},
        ):
            with self.subTest(headers=request_headers):
                status, headers, body = self.request(headers=request_headers)
                self.assertEqual(status, 401)
                self.assertEqual(headers["WWW-Authenticate"], 'Basic realm="Secret", charset="UTF-8"')
                self.assertNotIn("alice", body)

        status, _, body = self.request(headers=basic("alice", "abc"))
        self.assertEqual(status, 200)
        self.assertEqual(body, "alice|basic")

    def test_required_hides_paths(self) -> None:
        """
        An unauthenticated client can't tell which paths exist
        """
        self.start_server(True)

        status, _, _ = self.request(uri="/unknown")
        self.assertEqual(status, 401)

        status, _, _ = self.request(uri="/unknown", headers=basic("alice", "abc"))
        self.assertEqual(status, 404)

    def test_required_without_authenticator(self) -> None:
        """
        A protected resource stays protected when no authenticator is bound
        """
        with self.assertLogs(SERVER_NAME, logging.WARNING):
            self.start_server(True, False)
            status, headers, _ = self.request(headers=basic("alice", "abc"))

        self.assertEqual(status, 401)
        self.assertIsNone(headers["WWW-Authenticate"])

    def test_servlet_override(self) -> None:
        """
        A servlet can override the requirement of the HTTP service
        """
        self.start_server(True)
        self.register_servlet("/public", {http.HTTP_AUTH_REQUIRED: False})

        status, _, body = self.request(uri="/public")
        self.assertEqual(status, 200)
        self.assertEqual(body, "anonymous|None")

        # And the other way round
        self.ipopo.kill(SERVER_NAME)
        self.start_server(False, False)
        self.register_servlet("/private", {http.HTTP_AUTH_REQUIRED: "true", http.HTTP_AUTH_REALM: "Private"})

        status, headers, _ = self.request(uri="/private")
        self.assertEqual(status, 401)
        self.assertIn('realm="Private"', headers["WWW-Authenticate"])

        status, _, _ = self.request()
        self.assertEqual(status, 200)

    def test_servlet_guards(self) -> None:
        """
        The pelix.security decorators of the servlet methods are applied
        """
        self.start_server()

        # Anonymous: the client is asked for credentials
        status, headers, _ = self.request("POST")
        self.assertEqual(status, 401)
        self.assertIn("Basic", headers["WWW-Authenticate"])

        # Authenticated, but not in the group
        status, headers, _ = self.request("POST", headers=basic("bob", "abc"))
        self.assertEqual(status, 403)
        self.assertIsNone(headers["WWW-Authenticate"])

        status, _, body = self.request("POST", headers=basic("alice", "abc"))
        self.assertEqual(status, 200)
        self.assertEqual(body, "posted")

    def test_no_leak_between_requests(self) -> None:
        """
        The subject of a request doesn't leak to the next one on the same connection
        """
        self.start_server()

        conn = httplib.HTTPConnection(DEFAULT_HOST, self.port)
        try:
            bodies = []
            for request_headers in (basic("alice", "abc"), {}):
                conn.request("GET", "/test", None, request_headers)
                bodies.append(conn.getresponse().read().decode("utf-8"))
        finally:
            conn.close()

        self.assertEqual(bodies, ["alice|basic", "anonymous|None"])

    def test_cors_preflight_is_not_challenged(self) -> None:
        """
        Browsers never send credentials in a preflight: it must not be refused
        """
        self.start_server(True)
        self.framework.install_bundle("pelix.http.cors").start()
        self.ipopo.instantiate(http.FACTORY_HTTP_CORS, "cors", {http.HTTP_CORS_ORIGINS: "*"})

        status, headers, _ = self.request(
            "OPTIONS", headers={"Origin": "https://app.example.com", "Access-Control-Request-Method": "GET"}
        )
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")

        # The 401 response is readable by the script
        status, headers, _ = self.request(headers={"Origin": "https://app.example.com"})
        self.assertEqual(status, 401)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")


class BasicAuthTest(_AuthServerTests, unittest.TestCase):
    """
    Authentication on the basic HTTP service
    """


@unittest.skipUnless(HAS_AIOHTTP, "aiohttp not installed")
class AsyncSyncServletAuthTest(_AuthServerTests, unittest.TestCase):
    """
    Authentication on the async HTTP service, with synchronous servlets
    """

    http_bundle = "pelix.http.basic_async"
    http_factory = http.FACTORY_HTTP_ASYNC


@unittest.skipUnless(HAS_AIOHTTP, "aiohttp not installed")
class AsyncAuthTest(_AuthServerTests, unittest.TestCase):
    """
    Authentication on the async HTTP service, with asynchronous servlets
    """

    http_bundle = "pelix.http.basic_async"
    http_factory = http.FACTORY_HTTP_ASYNC
    async_servlet = True


if __name__ == "__main__":
    unittest.main()
