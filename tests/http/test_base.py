#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the code shared by the HTTP service implementations.

:author: Thomas Calmant
"""

import importlib.util
import time
import types
import unittest
from email.message import Message
from typing import Any, cast
from unittest import mock

from pelix import http
from pelix.framework import Framework, FrameworkFactory
from pelix.http import _base
from pelix.http._base import (
    SESSION_USER,
    AbstractHttpService,
    SessionContext,
    SessionManager,
    compute_sub_path,
    normalize_allowed_hosts,
    normalize_request_path,
    normalize_trusted_proxies,
    split_host_port,
)
from pelix.http.basic import HttpServiceImpl, _HTTPServletResponse
from pelix.security import ATTRIBUTE_SESSION_ID, Subject
from tests.http.utils import DEFAULT_HOST, get_http_code, get_http_page, install_ipopo, instantiate_server

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 4)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class SimpleServlet:
    """
    A servlet which does nothing: only its identity and the paths it has been
    bound to matter here
    """

    def __init__(self) -> None:
        self.bound: list[str] = []

    def do_GET(self, request: Any, response: Any) -> None:
        """
        Does nothing
        """

    def bound_to(self, path: str, parameters: dict[str, Any]) -> bool:
        """
        Records the path the servlet has been bound to
        """
        self.bound.append(path)
        return True


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

    def test_is_idempotent_on_its_own_result(self) -> None:
        """
        Normalizing an already normalized path must not change it.

        Note that the normalization is not idempotent on a *raw* path: it
        decodes, so applying it twice would decode twice. It is called once,
        on the raw path given by the client.
        """
        for raw in ("/", "/a/b", "/a/b/", "/a b"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_request_path(normalize_request_path(raw)), raw)

        # Decoding really is applied only once
        self.assertEqual(normalize_request_path("/a%2520b"), "/a%20b")
        self.assertEqual(normalize_request_path(normalize_request_path("/a%2520b")), "/a b")

    def test_percent_encoding_is_decoded(self) -> None:
        """
        The path is decoded before being routed, so that the servlet and the
        router can never disagree about what was requested
        """
        for raw, expected in (
            ("/a%20b", "/a b"),
            ("/%61%62", "/ab"),
            ("/files/a%2Fb", "/files/a/b"),
            ("/%2E/a", "/a"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_request_path(raw), expected)

    def test_dot_segments_are_resolved(self) -> None:
        """
        The ``.`` and ``..`` segments must be resolved before routing
        """
        for raw, expected in (
            ("/a/./b", "/a/b"),
            ("/public/../admin", "/admin"),
            ("/public/%2e%2e/admin", "/admin"),
            ("/public/%2E%2E%2Fadmin", "/admin"),
            ("/a/b/../c/", "/a/c/"),
            ("/a/..%2fb", "/b"),
            ("/a/b/..", "/a"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_request_path(raw), expected)

    def test_escaping_the_root_is_refused(self) -> None:
        """
        A path resolving above the root must be refused, not clamped to it
        """
        for raw in (
            "/..",
            "/../..",
            "/a/../..",
            "/%2e%2e",
            "/%2e%2e%2f%2e%2e%2fetc/passwd",
            "/a/../../b",
        ):
            with self.subTest(raw=raw):
                self.assertRaises(ValueError, normalize_request_path, raw)

    def test_control_characters_are_refused(self) -> None:
        """
        A decoded path must not hold a control character: a NUL byte truncates
        a path for anything calling into C
        """
        for raw in ("/a%00b", "/a\x00b", "/a%0Ab", "/a%7Fb", "/a%1fb"):
            with self.subTest(raw=raw):
                self.assertRaises(ValueError, normalize_request_path, raw)


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


class HostTest(unittest.TestCase):
    """
    Tests the parsing of the Host header and of its whitelist
    """

    def test_split_host_port(self) -> None:
        for value, expected in (
            ("LocalHost", ("localhost", None)),
            ("localhost:8080", ("localhost", "8080")),
            ("example.com.:80", ("example.com", "80")),
            ("[::1]", ("[::1]", None)),
            ("[::1]:8080", ("[::1]", "8080")),
        ):
            with self.subTest(value=value):
                self.assertEqual(split_host_port(value), expected)

    def test_normalize_allowed_hosts(self) -> None:
        for value, expected in (
            (None, None),
            ("", None),
            ([], None),
            ("a, B:1,", [("a", None), ("b", "1")]),
            (["a"], [("a", None)]),
        ):
            with self.subTest(value=value):
                self.assertEqual(normalize_allowed_hosts(value), expected)


class ProxyTest(unittest.TestCase):
    """
    Tests the resolution of the client behind trusted proxies
    """

    def test_normalize_trusted_proxies(self) -> None:
        self.assertEqual(normalize_trusted_proxies(None), [])
        self.assertEqual(len(normalize_trusted_proxies("10.0.0.0/8, ::1,")), 2)
        with self.assertRaises(ValueError):
            normalize_trusted_proxies(["not an address"])

    def test_resolve_client(self) -> None:
        forged = {"X-Forwarded-For": ["6.6.6.6"], "X-Forwarded-Proto": ["https"]}
        proxy = ("10.0.0.2", 1234)
        cases: list[tuple[str | None, str, dict[str, list[str]], bool, Any]] = [
            # Headers are ignored by default, and from untrusted peers
            (None, "10.0.0.2", forged, False, (proxy, False)),
            ("10.0.0.1", "10.0.0.2", forged, False, (proxy, False)),
            # The left of the chain is forged by the client: the first untrusted hop from the right is used
            (
                "10.0.0.0/8",
                "10.0.0.2",
                {"X-Forwarded-For": ["6.6.6.6, 1.2.3.4", "10.0.0.3"]},
                False,
                (("1.2.3.4", 0), False),
            ),
            (
                "::1, 127.0.0.1",
                "::ffff:127.0.0.1",
                {"X-Forwarded-For": ["2001:db8::1"]},
                False,
                (("2001:db8::1", 0), False),
            ),
            (None, "::ffff:1.2.3.4", {}, False, (("1.2.3.4", 1234), False)),
            ("10.0.0.0/8", "10.0.0.2", {"X-Forwarded-For": ["10.0.0.5, 10.0.0.3"]}, False, (proxy, False)),
            ("10.0.0.0/8", "10.0.0.2", {"X-Forwarded-For": ["1.2.3.4, nonsense"]}, False, (proxy, False)),
            # One clear text hop makes the request insecure; unknown values are ignored
            ("10.0.0.2", "10.0.0.2", {"X-Forwarded-Proto": ["https"]}, False, (proxy, True)),
            ("10.0.0.2", "10.0.0.2", {"X-Forwarded-Proto": ["https, HTTPS"]}, False, (proxy, True)),
            ("10.0.0.2", "10.0.0.2", {"X-Forwarded-Proto": ["https", "http"]}, True, (proxy, False)),
            ("10.0.0.2", "10.0.0.2", {"X-Forwarded-Proto": ["javascript"]}, False, (proxy, False)),
            ("10.0.0.2", "10.0.0.2", {"X-Forwarded-Proto": ["javascript"]}, True, (proxy, True)),
        ]
        for trusted, peer, values, uses_ssl, expected in cases:
            with self.subTest(trusted=trusted, peer=peer, headers=values, uses_ssl=uses_ssl):
                service = types.SimpleNamespace(
                    _uses_ssl=uses_ssl, _proxy_trusted=normalize_trusted_proxies(trusted)
                )
                headers = Message()
                for name, items in values.items():
                    for item in items:
                        headers[name] = item
                result = AbstractHttpService.resolve_client(cast(Any, service), (peer, 1234), headers)
                self.assertEqual(result, expected)


class CookieTest(unittest.TestCase):
    """
    Tests the cookie helpers and the headers of the responses
    """

    def test_parse(self) -> None:
        self.assertEqual(http.parse_cookies(None), {})
        self.assertEqual(http.parse_cookies('a=1; b="2"; broken; a=other; =x'), {"a": "1", "b": "2"})

    def test_format(self) -> None:
        self.assertEqual(http.format_cookie("sid", "abc"), "sid=abc; Path=/; SameSite=Lax; HttpOnly")
        self.assertEqual(
            http.format_cookie("sid", "abc", max_age=0, secure=True, http_only=False, same_site="None"),
            "sid=abc; Path=/; SameSite=None; Max-Age=0; Secure",
        )

        # Nothing can split the header
        kwargs: dict[str, Any]
        for kwargs in (
            {"name": "a b", "value": "x"},
            {"name": "a", "value": "x\r\nSet-Cookie: b=1"},
            {"name": "a", "value": "x;y"},
            {"name": "a", "value": "x", "path": "/;Domain=evil"},
            {"name": "a", "value": "x", "same_site": "Wide"},
            {"name": "a", "value": "x", "same_site": "None"},
        ):
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                cast(Any, http.format_cookie)(**kwargs)

    def test_basic_response_headers(self) -> None:
        response = _HTTPServletResponse(cast(Any, None))
        response.add_header("X-A", "1")
        response.add_header("X-A", "2")
        self.assertEqual(response._headers["x-a"], ["1", "2"])
        response.set_header("X-A", "3")
        self.assertEqual(response._headers["x-a"], ["3"])
        response.set_header("X-A", None)
        self.assertFalse(response.is_header_set("X-A"))
        for method in (response.set_header, response.add_header):
            with self.assertRaises(ValueError):
                method("X-B", "a\r\nSet-Cookie: b=1")

        # Once the headers are sent, changes are ignored, as they always were
        response._sent = True
        response.set_header("X-C", "1")
        response.add_header("X-C", "1")
        self.assertFalse(response.is_header_set("X-C"))

    def test_legacy_request_classes(self) -> None:
        """
        A request class written before get_peer_address() can still be instantiated
        """
        for cls in (http.AbstractHTTPServletRequest, http.AbstractAsyncHTTPServletRequest):
            with self.subTest(cls=cls):
                self.assertNotIn("get_peer_address", cls.__abstractmethods__)
                self.assertNotIn("get_client_address", cls.__abstractmethods__)


class SessionTest(unittest.TestCase):
    """
    Tests the sessions kept by the services, without any server
    """

    def setUp(self) -> None:
        self.manager = SessionManager(10)

    def context(self, cookie: str | None = None) -> SessionContext:
        return SessionContext(self.manager, "SID", cookie, False)

    def test_find_and_rename(self) -> None:
        self.assertIsNone(self.manager.find("never given"))
        session = self.manager.create()
        old_id = session.get_id()
        self.assertTrue(session.is_new())
        self.assertIs(self.manager.find(old_id), session)
        self.assertFalse(session.is_new())

        new_id = self.manager.rename(session)
        self.assertNotEqual(new_id, old_id)
        self.assertIsNone(self.manager.find(old_id))
        self.assertIs(self.manager.find(new_id), session)

    def test_expiration(self) -> None:
        session = self.manager.create()
        now = time.monotonic()
        for delay, alive in ((5, True), (14, True), (30, False)):
            # Using the session keeps it alive
            with (
                self.subTest(delay=delay),
                mock.patch.object(_base.time, "monotonic", return_value=now + delay),
            ):
                self.assertEqual(self.manager.find(session.get_id()) is session, alive)

        # Expired sessions nobody asks for are dropped when another one starts
        self.manager.create()
        with mock.patch.object(_base.time, "monotonic", return_value=now + 30):
            self.manager.create()
        self.assertEqual(len(self.manager._sessions), 1)

    def test_capacity(self) -> None:
        """
        The oldest anonymous session gives way first: anonymous requests can't log users out
        """
        with mock.patch.object(_base, "MAX_SESSIONS", 2):
            anonymous = self.manager.create()
            user = self.manager.create()
            user.set_attribute(SESSION_USER, "alice")
            other = self.manager.create()
            # find() keeps a session alive: only look for the evicted one
            self.assertEqual(len(self.manager._sessions), 2)
            self.assertIsNone(self.manager.find(anonymous.get_id()))

            # All logged in: the oldest overall gives way
            other.set_attribute(SESSION_USER, "bob")
            self.manager.create()
        self.assertIsNone(self.manager.find(user.get_id()))
        self.assertIs(self.manager.find(other.get_id()), other)

    def test_context(self) -> None:
        # An unknown cookie is left alone: a parallel request may carry the one of before a login
        context = self.context("unknown")
        self.assertIsNone(context.get(False))
        self.assertIsNone(context.cookie)
        with self.assertRaises(RuntimeError):
            context.change_id()

        session = cast(http.HttpSession, context.get(True))
        session.set_attribute(SESSION_USER, "alice")
        with (
            mock.patch.object(_base.auth, "restore", side_effect=OSError("LDAP is down")),
            self.assertLogs("pelix.http._base", "ERROR"),
        ):
            # A failing membership provider makes an anonymous request
            self.assertIsNone(context.restore())

        # Dropped by another request: can't be renamed
        session.invalidate()
        session.invalidate()
        with self.assertRaises(RuntimeError):
            context.change_id()

        # Once the headers are out, the cookie can't change
        context = self.context()
        context.sent = True
        for method in (context.change_id, lambda: context.get(True)):
            with self.assertRaises(RuntimeError):
                method()
        self.assertEqual(self.manager._sessions, {})

    def test_login(self) -> None:
        """
        The session gets a new identifier and keeps its attributes, unless another user logs in
        """
        context = self.context()
        cast(http.HttpSession, context.get(True)).set_attribute("cart", 3)
        old_cookie = context.cookie
        alice = Subject("alice", attributes={"mail": "a@b.c"}, authenticated=True)
        with mock.patch.object(_base.auth, "login", return_value=alice):
            result = context.login("alice", "abc", None)
        self.assertEqual(result.attributes["mail"], "a@b.c")
        self.assertIn(ATTRIBUTE_SESSION_ID, result.attributes)
        self.assertNotEqual(context.cookie, old_cookie)
        self.assertEqual(cast(http.HttpSession, context.get(False)).get_attribute("cart"), 3)

        with mock.patch.object(_base.auth, "login", return_value=Subject("bob", authenticated=True)):
            context.login("bob", "abc", None)
        session = cast(http.HttpSession, context.get(False))
        self.assertEqual(session.get_attribute(SESSION_USER), "bob")
        self.assertIsNone(session.get_attribute("cart"))

        context.sent = True
        with self.assertRaises(RuntimeError):
            context.logout()

    def test_cookie_name(self) -> None:
        """
        A cookie name which isn't a token is replaced by the default one
        """
        for name, service in get_services():
            with self.subTest(service=name):
                service._session_cookie = "a b"
                with self.assertLogs(level="WARNING"):
                    service._normalize_configuration()
                self.assertEqual(service._session_cookie, "PELIXSESSIONID")


BOUNDARY = "xX-boundary-Xx"
MULTIPART = f"multipart/form-data; boundary={BOUNDARY}"


def make_form(*fields: tuple[str, str | None, bytes]) -> bytes:
    """
    Prepares a multipart body, as a browser does: (name, file name or None, data) fields
    """
    body = b""
    for name, filename, data in fields:
        disposition = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        content_type = "Content-Type: image/gif\r\n" if filename else ""
        body += f"--{BOUNDARY}\r\nContent-Disposition: {disposition}\r\n{content_type}\r\n".encode()
        body += data + b"\r\n"
    return body + f"--{BOUNDARY}--\r\n".encode()


class MultipartTest(unittest.TestCase):
    """
    Tests the multipart/form-data parser
    """

    def test_parse(self) -> None:
        # The data holds what looks like a boundary and CRLF
        data = b"GIF89a\r\n--" + BOUNDARY.encode()[:5] + b"\r\n\x00\xff"
        fields = make_form(
            ("title", None, "Élodie".encode()), ("file", "../a b.gif", data), ("empty", None, b"")
        )
        awkward = "'()+_,./:=? -x"
        cases: list[tuple[str, bytes, list[tuple[str, str | None, str | None, bytes]]]] = [
            # The file name is given as is: the caller must not trust it
            (
                MULTIPART,
                fields,
                [
                    ("title", None, None, "Élodie".encode()),
                    ("file", "../a b.gif", "image/gif", data),
                    ("empty", None, None, b""),
                ],
            ),
            # Preamble and epilogue are ignored
            (
                MULTIPART,
                b"preamble\r\n" + make_form(("a", None, b"1")) + b"epilogue",
                [("a", None, None, b"1")],
            ),
            (
                f'multipart/form-data; boundary="{BOUNDARY}"',
                make_form(("f", "été.gif", b"x")),
                [("f", "été.gif", "image/gif", b"x")],
            ),
            # Special characters, padding, folded headers, RFC 5987 names, repeated names
            (
                f'multipart/form-data; boundary="{awkward}"',
                (
                    f"--{awkward} \t\r\nContent-Disposition: form-data; name=a;\r\n  filename*=UTF-8''%C3%A9t%C3%A9.gif\r\n\r\n1\r\n"
                    f"--{awkward}\r\nContent-Disposition: form-data; name=a\r\n\r\n2\r\n--{awkward}--"
                ).encode(),
                [("a", "été.gif", None, b"1"), ("a", None, None, b"2")],
            ),
        ]
        for content_type, body, expected in cases:
            with self.subTest(content_type=content_type, body=body[:40]):
                parts = http.parse_multipart(content_type, body)
                self.assertEqual([(p.name, p.filename, p.content_type, p.data) for p in parts], expected)

    def test_refused(self) -> None:
        good = make_form(("a", None, b"1"))
        cases: list[tuple[str | None, bytes]] = [
            (None, good),
            ("text/plain", good),
            ("multipart/form-data", good),
            (f"multipart/form-data; boundary={'b' * 71}", good),
            (f"{MULTIPART}\u00e9", good),
            ("multipart/form-data; boundary=b ", good),
            (MULTIPART, b""),
            # No closing delimiter
            (MULTIPART, good[: -len(BOUNDARY) - 6]),
            (MULTIPART, f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=a\r\n".encode()),
            (
                MULTIPART,
                f"--{BOUNDARY}\r\nContent-Disposition: attachment; name=a\r\n\r\n1\r\n--{BOUNDARY}--".encode(),
            ),
            (
                MULTIPART,
                f"--{BOUNDARY}\r\nContent-Disposition: form-database; name=a\r\n\r\n1\r\n--{BOUNDARY}--".encode(),
            ),
            (
                MULTIPART,
                f"--{BOUNDARY}\r\nContent-Disposition: form-data\r\n\r\n1\r\n--{BOUNDARY}--".encode(),
            ),
            (
                MULTIPART,
                f"--{BOUNDARY}\r\nContent-Disposition: form-data; name*=UTF-8''a\r\n\r\n1\r\n--{BOUNDARY}--".encode(),
            ),
            (MULTIPART, f"--{BOUNDARY}\r\n{'X-Pad: ' + 'a' * 9000}\r\n\r\n1\r\n--{BOUNDARY}--".encode()),
            (MULTIPART, f"--{BOUNDARY}\r\nno header end--{BOUNDARY}--".encode()),
            # A body of delimiters costs nothing
            (MULTIPART, (f"\r\n--{BOUNDARY}" * 100_000).encode()),
        ]
        for content_type, body in cases:
            with (
                self.subTest(content_type=content_type, body=body[:40]),
                self.assertRaises(http.MultipartError),
            ):
                http.parse_multipart(content_type, body)

    def test_max_parts(self) -> None:
        body = make_form(*[(f"f{i}", None, b"") for i in range(5)])
        self.assertEqual(len(http.parse_multipart(MULTIPART, body, 5)), 5)
        with self.assertRaises(http.MultipartError):
            http.parse_multipart(MULTIPART, body, 4)


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


class RefusedPathTest(unittest.TestCase):
    """
    Tests the paths the router refuses before looking for a servlet
    """

    def test_traversal_is_resolved_before_routing(self) -> None:
        """
        A path walking back into a servlet must reach that servlet, and the
        servlet must be given the resolved path
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                service.register_servlet("/admin", servlet)

                for raw in ("/public/../admin/x", "/public/%2e%2e/admin/x"):
                    with self.subTest(raw=raw):
                        routing = service.resolve_request(raw)
                        self.assertIs(routing.servlet, servlet)
                        self.assertEqual(routing.prefix, "/admin")
                        self.assertEqual(routing.path, "/admin/x")
                        self.assertIsNone(routing.error)

    def test_escaping_the_root_is_a_bad_request(self) -> None:
        """
        A path escaping the root is refused with a 400, without any servlet
        being looked for
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                service.register_servlet("/test", servlet)

                for raw in ("/..", "/test/../..", "/%2e%2e%2f%2e%2e%2fetc/passwd"):
                    with self.subTest(raw=raw):
                        routing = service.resolve_request(raw)
                        self.assertEqual(routing.error, 400)
                        self.assertIsNone(routing.servlet)

    def test_control_characters_are_a_bad_request(self) -> None:
        """
        A control character in the decoded path is refused with a 400
        """
        for name, service in get_services():
            with self.subTest(service=name):
                routing = service.resolve_request("/test%00/sub")
                self.assertEqual(routing.error, 400)
                self.assertIsNone(routing.servlet)


class CaseSensitivityTest(unittest.TestCase):
    """
    Tests the case-sensitive matching of the servlet paths
    """

    def test_paths_are_case_sensitive(self) -> None:
        """
        URI paths are case-sensitive: /Admin and /admin are two resources
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                service.register_servlet("/admin", servlet)

                self.assertIsNotNone(service.get_servlet("/admin/x"))
                for raw in ("/Admin/x", "/ADMIN/x", "/aDmIn/x"):
                    with self.subTest(raw=raw):
                        self.assertIsNone(service.get_servlet(raw))

    def test_registration_keeps_its_case(self) -> None:
        """
        A servlet registered on a mixed-case path keeps it, and is reachable
        on that exact path only. This is what the JSON-RPC, XML-RPC and
        JABSORB-RPC transports rely on: they advertise the path they declared.
        """
        for name, service in get_services():
            with self.subTest(service=name):
                # A fresh servlet per service: bound_to is recorded on it
                servlet = SimpleServlet()
                self.assertTrue(service.register_servlet("/JSON-RPC", servlet))

                self.assertEqual(service.get_registered_paths(), ["/JSON-RPC"])
                self.assertIsNotNone(service.get_servlet("/JSON-RPC"))
                self.assertIsNone(service.get_servlet("/json-rpc"))

                # The servlet has been told the path it asked for
                self.assertEqual(servlet.bound, ["/JSON-RPC"])

    def test_two_cases_are_two_servlets(self) -> None:
        """
        Two paths differing only by their case must not collide
        """
        lower = SimpleServlet()
        upper = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                self.assertTrue(service.register_servlet("/admin", lower))
                self.assertTrue(service.register_servlet("/Admin", upper))

                found_lower = service.get_servlet("/admin")
                found_upper = service.get_servlet("/Admin")
                assert found_lower is not None
                assert found_upper is not None
                self.assertIs(found_lower[0], lower)
                self.assertIs(found_upper[0], upper)

    def test_folding_can_be_restored(self) -> None:
        """
        The escape hatch property restores the behaviour of earlier versions
        """
        servlet = SimpleServlet()
        for name, service in get_services():
            with self.subTest(service=name):
                service._case_sensitive_paths = False
                service.register_servlet("/Admin", servlet)

                # Registered folded, reachable in any case
                self.assertEqual(service.get_registered_paths(), ["/admin"])
                for raw in ("/admin", "/Admin", "/ADMIN"):
                    with self.subTest(raw=raw):
                        self.assertIsNotNone(service.get_servlet(raw))

                self.assertTrue(service.unregister("/ADMIN"))
                self.assertEqual(service.get_registered_paths(), [])


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

    http_bundle: str = "pelix.http.basic"
    http_factory: str = http.FACTORY_HTTP_BASIC

    def setUp(self) -> None:
        """
        Starts a framework with an HTTP server on a random port
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

        ipopo = install_ipopo(self.framework)
        context = self.framework.get_bundle_context()
        context.install_bundle(self.http_bundle).start()

        self.http_svc = instantiate_server(ipopo, self.http_factory, "test-http-paths", port=0)
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

    def test_paths_are_case_sensitive(self) -> None:
        """
        A request differing from the registration only by its case must not
        reach that servlet
        """
        for uri in ("/Test/inner/x", "/TEST/INNER/x"):
            with self.subTest(uri=uri):
                self.assertEqual(get_http_code(self.port, DEFAULT_HOST, uri), 404)

    def test_case_does_not_reach_the_deepest_servlet(self) -> None:
        """
        Changing the case of a nested servlet must fall back to the shallower
        one rather than reach the nested servlet anyway. This is the bypass:
        the router used to fold the path while the servlet saw the original.
        """
        code, content = get_http_page(self.port, DEFAULT_HOST, "/test/Inner/x")
        self.assertEqual(code, 200)
        self.assertEqual(content.decode("utf-8"), "root|/test|/Inner/x")

    def test_traversal_is_resolved_before_routing(self) -> None:
        """
        A path walking back into a servlet reaches it, and the servlet is given
        the resolved path: the router and the servlet can never disagree
        """
        for uri in (
            "/test/inner/../inner/x",
            "/test/sub/../inner/x",
            "/test/inner/%2e%2e/inner/x",
            "/test/inner/..%2finner/x",
        ):
            with self.subTest(uri=uri):
                code, content = get_http_page(self.port, DEFAULT_HOST, uri)
                self.assertEqual(code, 200, f"{uri} did not reach a servlet")
                self.assertEqual(content.decode("utf-8"), "inner|/test/inner|/x")

    def test_traversal_out_of_a_servlet(self) -> None:
        """
        Walking out of the deepest servlet must move the request to the
        shallower one, not leave a ".." in the sub path
        """
        code, content = get_http_page(self.port, DEFAULT_HOST, "/test/inner/../x")
        self.assertEqual(code, 200)
        self.assertEqual(content.decode("utf-8"), "root|/test|/x")

    def test_percent_encoding_reaches_the_servlet_decoded(self) -> None:
        """
        The servlet is given a decoded sub path
        """
        for uri, expected in (
            ("/test/inner/a%20b", "/a b"),
            ("/test/inner/a%2Fb", "/a/b"),
            ("/test/inner/%61%62", "/ab"),
        ):
            with self.subTest(uri=uri):
                code, content = get_http_page(self.port, DEFAULT_HOST, uri)
                self.assertEqual(code, 200)
                self.assertEqual(content.decode("utf-8"), f"inner|/test/inner|{expected}")

    def test_escaping_the_root_is_a_bad_request(self) -> None:
        """
        A path escaping the root is refused with a 400, not a 404: it is the
        request which is malformed, not the resource which is missing
        """
        for uri in ("/..", "/test/../../x", "/%2e%2e%2f%2e%2e%2fetc/passwd"):
            with self.subTest(uri=uri):
                self.assertEqual(get_http_code(self.port, DEFAULT_HOST, uri), 400)

    def test_control_character_is_a_bad_request(self) -> None:
        """
        A NUL byte in the decoded path is refused
        """
        self.assertEqual(get_http_code(self.port, DEFAULT_HOST, "/test/inner/a%00b"), 400)


@unittest.skipIf(importlib.util.find_spec("aiohttp") is None, "aiohttp library not available")
class AsyncEndToEndPathTest(EndToEndPathTest):
    """
    Runs the routing tests over the asynchronous server.

    This is not redundant: the two servers give the router a different string
    (the raw target here, an already decoded one before this was fixed), so the
    decoding half of the normalization is only covered on this side.
    """

    http_bundle = "pelix.http.basic_async"
    http_factory = http.FACTORY_HTTP_ASYNC


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
