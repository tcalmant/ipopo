#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the static files servlet of the HTTP services

:author: Thomas Calmant
"""

import email.utils
import http.client as httplib
import importlib.util
import os
import pathlib
import shutil
import tempfile
import time
import unittest
import unittest.mock
import zlib
from email.message import Message
from typing import Any

from pelix import http
from pelix.framework import Framework, FrameworkFactory
from pelix.http.static import StaticFilesServlet
from pelix.ipopo.constants import IPopoService
from tests.http.utils import DEFAULT_HOST, install_ipopo

# ------------------------------------------------------------------------------

SERVER_NAME = "static-test-server"
STATIC_NAME = "static-test-files"
HAS_AIOHTTP = importlib.util.find_spec("aiohttp") is not None
STYLE = b"p { color: red; }"
# Spans several blocks, with a partial one at the end
BIG = os.urandom(200 * 1024 + 7)

# ------------------------------------------------------------------------------


class StaticFilesServletTest(unittest.TestCase):
    """
    Tests of the servlet without a server
    """

    def test_root_must_be_a_folder(self) -> None:
        """
        A missing folder or a file is refused
        """
        with tempfile.TemporaryDirectory() as tmp:
            some_file = pathlib.Path(tmp) / "file.txt"
            some_file.write_text("content")
            for root in (pathlib.Path(tmp) / "missing", some_file):
                with self.subTest(root=root), self.assertRaises(ValueError):
                    StaticFilesServlet(root)

    def test_invalid_configuration(self) -> None:
        """
        Index names which are not a public file name and links leading out of
        a folder whose links are not followed are refused
        """
        with tempfile.TemporaryDirectory() as tmp:
            cases: list[dict[str, Any]] = [
                {"index": ".index.html"},
                {"index": "sub/index.html"},
                {"links_outside": True},
            ]
            for kwargs in cases:
                with self.subTest(**kwargs), self.assertRaises(ValueError):
                    StaticFilesServlet(tmp, **kwargs)


class _StaticServerTests:
    """
    Static files tests against a live HTTP service, run for each kind of server
    """

    http_bundle = "pelix.http.basic"
    http_factory = http.FACTORY_HTTP_BASIC

    framework: Framework
    ipopo: IPopoService
    port: int
    root: pathlib.Path
    outside: pathlib.Path
    has_links: bool

    # Provided by unittest.TestCase
    assertEqual: Any
    assertIn: Any
    assertIsNone: Any
    assertIsNotNone: Any
    assertNotEqual: Any
    assertNotIn: Any
    assertTrue: Any
    skipTest: Any
    subTest: Any

    def setUp(self) -> None:
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="pelix-static-"))
        self.outside = pathlib.Path(tempfile.mkdtemp(prefix="pelix-static-outside-"))
        (self.root / "index.html").write_text("<p>index</p>", encoding="utf-8")
        (self.root / "style.css").write_bytes(STYLE)
        (self.root / "style.css.gz").write_bytes(zlib.compress(STYLE))
        (self.root / "big.bin").write_bytes(BIG)
        (self.root / "empty.txt").write_bytes(b"")
        (self.root / "data.unknownext").write_bytes(b"\x00\x01\x02")
        (self.root / ".secret").write_text("hidden", encoding="utf-8")
        (self.root / "empty").mkdir()
        (self.root / "sub").mkdir()
        (self.root / "sub" / "index.html").write_text("<p>sub</p>", encoding="utf-8")
        (self.outside / "private.txt").write_text("private", encoding="utf-8")
        (self.root / "leak").mkdir()
        (self.root / ".git").mkdir()
        (self.root / ".git" / "config").write_text("hidden", encoding="utf-8")
        (self.root / "a b été").mkdir()
        try:
            os.symlink(self.outside / "private.txt", self.root / "escape.txt")
            os.symlink(self.outside / "private.txt", self.root / "leak" / "index.html")
            os.symlink(self.root / ".git" / "config", self.root / "public.txt")
            os.symlink(self.root / ".git", self.root / "gitdir")
            os.symlink(self.root / "loop", self.root / "loop")
            os.symlink(self.root / "style.css", self.root / "alias.css")
            os.symlink(self.root / "sub", self.root / "linkdir")
            self.has_links = True
        except OSError:
            # Windows without the privilege to create symbolic links
            self.has_links = False

        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.framework.install_bundle(self.http_bundle).start()
        self.framework.install_bundle("pelix.http.static").start()
        svc = self.ipopo.instantiate(
            self.http_factory,
            SERVER_NAME,
            {http.HTTP_SERVICE_ADDRESS: DEFAULT_HOST, http.HTTP_SERVICE_PORT: 0},
        )
        self.port = svc.get_access()[1]

    def tearDown(self) -> None:
        FrameworkFactory.delete_framework()
        shutil.rmtree(self.root)
        shutil.rmtree(self.outside)

    def serve(self, **properties: Any) -> None:
        """
        Instantiates the static files component on /static
        """
        self.ipopo.instantiate(
            http.FACTORY_HTTP_STATIC,
            STATIC_NAME,
            {http.HTTP_SERVLET_PATH: "/static", http.HTTP_STATIC_ROOT: str(self.root), **properties},
        )

    def request(
        self, uri: str, method: str = "GET", headers: dict[str, str] | None = None
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

    def test_served_files(self) -> None:
        """
        Status, type and content of the served files
        """
        self.serve()
        cases = [
            ("/static/index.html", 200, "text/html; charset=utf-8", b"<p>index</p>"),
            ("/static/", 200, "text/html; charset=utf-8", b"<p>index</p>"),
            ("/static/style.css", 200, "text/css; charset=utf-8", STYLE),
            ("/static/data.unknownext", 200, "application/octet-stream", b"\x00\x01\x02"),
            ("/static/sub/", 200, "text/html; charset=utf-8", b"<p>sub</p>"),
            ("/static/big.bin", 200, "application/octet-stream", BIG),
            ("/static/empty.txt", 200, "text/plain; charset=utf-8", b""),
            ("/static/missing.txt", 404, None, None),
            ("/static/.secret", 404, None, None),
            ("/static/escape.txt", 404, None, None),
            ("/static/empty/", 404, None, None),
            ("/static/leak/", 404, None, None),
            ("/static/.git/config", 404, None, None),
            ("/static/public.txt", 404, None, None),
            ("/static/gitdir/config", 404, None, None),
            ("/static/loop", 404, None, None),
            ("/static/alias.css", 404, None, None),
            ("/static/linkdir/", 404, None, None),
            ("/static/style.css/", 404, None, None),
        ]
        for uri, status, mime_type, content in cases:
            with self.subTest(uri=uri):
                code, headers, body = self.request(uri)
                self.assertEqual(code, status)
                if mime_type is not None:
                    self.assertEqual(headers["Content-Type"], mime_type)
                    self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                    self.assertEqual(body, content)

    def test_folder_redirect(self) -> None:
        """
        A folder without its trailing slash is redirected, so that relative links work
        """
        self.serve()
        cases = [
            ("/static/sub", "/static/sub/"),
            ("/static", "/static/"),
            ("/static/a%20b%20%C3%A9t%C3%A9", "/static/a%20b%20%C3%A9t%C3%A9/"),
        ]
        for uri, location in cases:
            with self.subTest(uri=uri):
                code, headers, _ = self.request(uri)
                self.assertEqual(code, 301)
                self.assertEqual(headers["Location"], location)

    def test_no_index(self) -> None:
        """
        An empty index refuses the requests on folders
        """
        self.serve(**{http.HTTP_STATIC_INDEX: ""})
        self.assertEqual(self.request("/static/")[0], 404)
        self.assertEqual(self.request("/static/index.html")[0], 200)

    def test_head(self) -> None:
        """
        HEAD sends the headers of GET, without the content
        """
        self.serve()
        for range_header in ({}, {"Range": "bytes=0-1"}):
            with self.subTest(range=range_header):
                # Range is only defined for GET
                code, headers, body = self.request("/static/style.css", "HEAD", range_header)
                self.assertEqual(code, 200)
                self.assertEqual(headers["Content-Length"], str(len(STYLE)))
                self.assertEqual(headers["Accept-Ranges"], "bytes")
                self.assertEqual(body, b"")

    def test_content_encoding(self) -> None:
        """
        A compressed file is sent with the type of its content and its encoding
        """
        self.serve()
        code, headers, body = self.request("/static/style.css.gz")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "text/css; charset=utf-8")
        self.assertEqual(headers["Content-Encoding"], "gzip")
        self.assertEqual(zlib.decompress(body), STYLE)

    def test_types(self) -> None:
        """
        Charset of the text files, types files and types table
        """
        mime_types = self.outside / "mime.types"
        mime_types.write_text("# Comment\napplication/x-custom unknownext\n", encoding="utf-8")
        cases: list[tuple[dict[str, Any], str, str]] = [
            ({http.HTTP_STATIC_CHARSET: "iso-8859-1"}, "style.css", "text/css; charset=iso-8859-1"),
            ({http.HTTP_STATIC_CHARSET: ""}, "style.css", "text/css"),
            ({http.HTTP_STATIC_MIME_TYPES: str(mime_types)}, "data.unknownext", "application/x-custom"),
            ({http.HTTP_STATIC_MIME_TYPES: [str(mime_types)]}, "data.unknownext", "application/x-custom"),
            ({http.HTTP_STATIC_TYPES: {"unknownext": "image/x-a"}}, "data.unknownext", "image/x-a"),
            ({http.HTTP_STATIC_TYPES: {".css": "text/x-b"}}, "style.css", "text/x-b; charset=utf-8"),
        ]
        for properties, name, mime_type in cases:
            with self.subTest(properties=properties):
                self.serve(**properties)
                try:
                    code, headers, _ = self.request(f"/static/{name}")
                    self.assertEqual(code, 200)
                    self.assertEqual(headers["Content-Type"], mime_type)
                finally:
                    self.ipopo.kill(STATIC_NAME)

    def test_range(self) -> None:
        """
        A single range is sent with a 206 code, others ranges are ignored
        """
        self.serve()
        size = len(STYLE)
        cases = [
            ("bytes=0-0", 206, f"bytes 0-0/{size}", STYLE[:1]),
            ("bytes=2-", 206, f"bytes 2-{size - 1}/{size}", STYLE[2:]),
            ("bytes=-3", 206, f"bytes {size - 3}-{size - 1}/{size}", STYLE[-3:]),
            ("bytes=-100", 206, f"bytes 0-{size - 1}/{size}", STYLE),
            ("bytes=5-100", 206, f"bytes 5-{size - 1}/{size}", STYLE[5:]),
            ("BYTES=1-2", 206, f"bytes 1-2/{size}", STYLE[1:3]),
            (f"bytes={size}-", 416, f"bytes */{size}", b""),
            ("bytes=-0", 416, f"bytes */{size}", b""),
            ("bytes=3-1", 200, None, STYLE),
            ("bytes=0-1,3-4", 200, None, STYLE),
            ("items=0-1", 200, None, STYLE),
            ("bytes=-", 200, None, STYLE),
            ("bytes=" + "9" * 5000 + "-", 200, None, STYLE),
        ]
        for range_header, status, content_range, content in cases:
            with self.subTest(range=range_header[:20]):
                code, headers, body = self.request("/static/style.css", headers={"Range": range_header})
                self.assertEqual(code, status)
                self.assertEqual(headers["Content-Range"], content_range)
                self.assertEqual(body, content)

        # Across blocks of a big file
        code, _, body = self.request("/static/big.bin", headers={"Range": "bytes=65530-131080"})
        self.assertEqual(code, 206)
        self.assertEqual(body, BIG[65530:131081])

        # The range of an empty file could only be empty
        self.assertEqual(self.request("/static/empty.txt", headers={"Range": "bytes=-1"})[0], 200)

    def test_if_range(self) -> None:
        """
        If-Range only accepts the current entity tag: a date is a weak validator
        """
        self.serve()
        _, headers, _ = self.request("/static/style.css")
        cases = [
            (headers["ETag"], 206),
            ('"other"', 200),
            ("W/" + headers["ETag"], 200),
            (headers["Last-Modified"], 200),
        ]
        for if_range, status in cases:
            with self.subTest(if_range=if_range):
                code, _, _ = self.request(
                    "/static/style.css", headers={"Range": "bytes=0-1", "If-Range": if_range}
                )
                self.assertEqual(code, status)

    def test_preconditions(self) -> None:
        """
        Conditional requests, evaluated in the order of RFC 9110
        """
        self.serve()
        _, headers, _ = self.request("/static/style.css")
        etag = headers["ETag"]
        last_modified = headers["Last-Modified"]
        older = email.utils.formatdate(0, usegmt=True)
        cases: list[tuple[dict[str, str], int]] = [
            ({"If-None-Match": etag}, 304),
            ({"If-None-Match": f'"a", W/{etag}'}, 304),
            ({"If-None-Match": "*"}, 304),
            ({"If-None-Match": '"other"'}, 200),
            # If-Modified-Since is ignored along If-None-Match
            ({"If-None-Match": '"other"', "If-Modified-Since": last_modified}, 200),
            ({"If-Match": etag}, 200),
            ({"If-Match": "*"}, 200),
            ({"If-Match": '"other"'}, 412),
            # If-Match uses the strong comparison
            ({"If-Match": f"W/{etag}"}, 412),
            ({"If-Unmodified-Since": older}, 412),
            ({"If-Unmodified-Since": last_modified}, 200),
            # If-Unmodified-Since is ignored along If-Match
            ({"If-Match": etag, "If-Unmodified-Since": older}, 200),
            # A failed precondition wins over the range
            ({"If-None-Match": etag, "Range": "bytes=0-1"}, 304),
        ]
        for request_headers, status in cases:
            with self.subTest(headers=request_headers):
                self.assertEqual(self.request("/static/style.css", headers=request_headers)[0], status)

    def test_changed_file(self) -> None:
        """
        The entity tag changes with the file, even within the same second
        """
        self.serve()
        _, headers, _ = self.request("/static/style.css")
        stats = (self.root / "style.css").stat()
        os.utime(self.root / "style.css", ns=(stats.st_atime_ns, stats.st_mtime_ns + 1000))
        _, new_headers, _ = self.request("/static/style.css")
        self.assertNotEqual(headers["ETag"], new_headers["ETag"])
        self.assertEqual(
            self.request("/static/style.css", headers={"If-None-Match": headers["ETag"]})[0], 200
        )

    def test_follow_links(self) -> None:
        """
        Followed links stay in the folder, unless allowed to lead out of it
        """
        if not self.has_links:
            self.skipTest("Symbolic links can't be created")

        cases: list[tuple[dict[str, Any], str, int]] = []
        follow = {http.HTTP_STATIC_FOLLOW_LINKS: True}
        outside = {**follow, http.HTTP_STATIC_LINKS_OUTSIDE: True}
        for properties in (follow, outside):
            cases.extend(
                [
                    (properties, "/static/alias.css", 200),
                    (properties, "/static/linkdir/", 200),
                    (properties, "/static/public.txt", 404),
                    (properties, "/static/gitdir/config", 404),
                    (properties, "/static/loop", 404),
                ]
            )
        cases.extend(
            [
                (follow, "/static/escape.txt", 404),
                (follow, "/static/leak/", 404),
                (outside, "/static/escape.txt", 200),
                (outside, "/static/leak/", 200),
                # Links leading out require the links to be followed
                ({http.HTTP_STATIC_LINKS_OUTSIDE: True}, "/static/index.html", 404),
            ]
        )
        for properties, uri, status in cases:
            with self.subTest(properties=properties, uri=uri):
                self.serve(**properties)
                try:
                    self.assertEqual(self.request(uri)[0], status)
                finally:
                    self.ipopo.kill(STATIC_NAME)

    def test_if_modified_since(self) -> None:
        """
        A conditional request is answered with 304 until the file changes
        """
        self.serve()
        _, headers, _ = self.request("/static/style.css")
        last_modified = headers["Last-Modified"]
        older = email.utils.formatdate(0, usegmt=True)
        cases = [
            (last_modified, 304),
            (older, 200),
            ("not a date", 200),
        ]
        for since, status in cases:
            with self.subTest(since=since):
                self.assertEqual(
                    self.request("/static/style.css", headers={"If-Modified-Since": since})[0], status
                )

    @unittest.skipUnless(hasattr(time, "tzset"), "Time zones can't be changed")
    def test_if_modified_since_asctime(self) -> None:
        """
        A date in the obsolete asctime format is in GMT, whatever the local time zone
        """
        self.serve()
        now = time.time()
        os.utime(self.root / "style.css", (now - 3600, now - 3600))
        since = time.strftime("%a %b %d %H:%M:%S %Y", time.gmtime(now - 7200))
        old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/Los_Angeles"
        time.tzset()
        try:
            self.assertEqual(self.request("/static/style.css", headers={"If-Modified-Since": since})[0], 200)
        finally:
            if old_tz is None:
                del os.environ["TZ"]
            else:
                os.environ["TZ"] = old_tz
            time.tzset()

    def test_extra_headers(self) -> None:
        """
        Configured headers are added to the served files
        """
        self.serve(**{http.HTTP_STATIC_HEADERS: {"Content-Security-Policy": "sandbox"}})
        _, headers, _ = self.request("/static/style.css")
        self.assertEqual(headers["Content-Security-Policy"], "sandbox")

        # Also on a 304, which holds no other representation metadata (RFC 9110, 15.4.5)
        code, headers, _ = self.request("/static/style.css", headers={"If-None-Match": headers["ETag"]})
        self.assertEqual(code, 304)
        self.assertEqual(headers["Content-Security-Policy"], "sandbox")
        self.assertIsNotNone(headers["ETag"])
        self.assertIsNotNone(headers["Last-Modified"])
        self.assertIsNone(headers["Content-Type"])

    def test_missing_root(self) -> None:
        """
        The component is not valid without a root folder
        """
        self.ipopo.instantiate(http.FACTORY_HTTP_STATIC, STATIC_NAME, {http.HTTP_SERVLET_PATH: "/static"})
        self.assertEqual(self.request("/static/index.html")[0], 404)


class BasicStaticTest(_StaticServerTests, unittest.TestCase):
    """
    Static files on the basic HTTP service
    """


class CheckedPathStaticTest(_StaticServerTests, unittest.TestCase):
    """
    Static files opened by checking their path, as on Windows which can't
    open a file relatively to a folder
    """

    def setUp(self) -> None:
        patcher = unittest.mock.patch("pelix.http.static._WALK_WITH_FD", False)
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()


@unittest.skipUnless(HAS_AIOHTTP, "aiohttp not installed")
class AsyncStaticTest(_StaticServerTests, unittest.TestCase):
    """
    Static files on the async HTTP service
    """

    http_bundle = "pelix.http.basic_async"
    http_factory = http.FACTORY_HTTP_ASYNC
