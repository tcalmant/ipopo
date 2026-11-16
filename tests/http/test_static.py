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
import unittest
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

    # Provided by unittest.TestCase
    assertEqual: Any
    assertIn: Any
    assertNotIn: Any
    assertTrue: Any
    subTest: Any

    def setUp(self) -> None:
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="pelix-static-"))
        self.outside = pathlib.Path(tempfile.mkdtemp(prefix="pelix-static-outside-"))
        (self.root / "index.html").write_text("<p>index</p>", encoding="utf-8")
        (self.root / "style.css").write_text("p { color: red; }", encoding="utf-8")
        (self.root / "data.unknownext").write_bytes(b"\x00\x01\x02")
        (self.root / ".secret").write_text("hidden", encoding="utf-8")
        (self.root / "empty").mkdir()
        (self.root / "sub").mkdir()
        (self.root / "sub" / "index.html").write_text("<p>sub</p>", encoding="utf-8")
        (self.outside / "private.txt").write_text("private", encoding="utf-8")
        os.symlink(self.outside / "private.txt", self.root / "escape.txt")

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
            ("/static/style.css", 200, "text/css; charset=utf-8", b"p { color: red; }"),
            ("/static/data.unknownext", 200, "application/octet-stream", b"\x00\x01\x02"),
            ("/static/sub/", 200, "text/html; charset=utf-8", b"<p>sub</p>"),
            ("/static/missing.txt", 404, None, None),
            ("/static/.secret", 404, None, None),
            ("/static/escape.txt", 404, None, None),
            ("/static/empty/", 404, None, None),
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
        code, headers, _ = self.request("/static/sub")
        self.assertEqual(code, 301)
        self.assertEqual(headers["Location"], "/static/sub/")

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
        code, headers, body = self.request("/static/style.css", "HEAD")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Length"], str(len("p { color: red; }")))
        self.assertEqual(body, b"")

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


@unittest.skipUnless(HAS_AIOHTTP, "aiohttp not installed")
class AsyncStaticTest(_StaticServerTests, unittest.TestCase):
    """
    Static files on the async HTTP service
    """

    http_bundle = "pelix.http.basic_async"
    http_factory = http.FACTORY_HTTP_ASYNC
