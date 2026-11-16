#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Serves the files of a folder through the Pelix HTTP services.

Provides a servlet serving the files of a folder (front-end assets, generated
documents...) and a component factory to configure it with properties.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.3.0

..

    Copyright 2026 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import datetime
import email.utils
import http.client as http_client
import mimetypes
import os
import stat
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pelix import http
from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Validate

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["StaticFilesServlet"]

# ------------------------------------------------------------------------------

DEFAULT_INDEX = "index.html"
""" File served for a request on a folder, by default """

# Types served as UTF-8 text: the files are expected to be written in UTF-8
_TEXT_TYPES = {"application/javascript", "application/json", "image/svg+xml", "text/javascript"}


class StaticFilesServlet:
    """
    Serves the files of a folder, for the GET and HEAD methods.

    Only regular files inside the folder are served: a path with a hidden
    segment (starting with a dot), before or after following the links, a link
    leading out of the folder or a folder without its index file is answered
    with a 404 error code. Folders are never listed.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        index: str | None = DEFAULT_INDEX,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """
        :param root: Folder to serve
        :param index: File served for a request on a folder, None to refuse
                      those requests
        :param headers: Headers added to the responses of the served files
        :raise ValueError: The root is not a folder
        """
        self._root = Path(root).resolve()
        if not self._root.is_dir():
            raise ValueError(f"Not a folder: {root}")

        self._index = index or None
        self._headers = dict(headers or {})

    def do_GET(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        """
        Sends the requested file
        """
        self._serve(request, response, True)

    def do_HEAD(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        """
        Sends the headers of the requested file, without its content
        """
        self._serve(request, response, False)

    def _resolve(self, sub_path: str) -> Path | None:
        """
        Finds the file or folder matching a servlet-relative path.

        :param sub_path: Path relative to the servlet, already normalized by
                         the HTTP service
        :return: The resolved path, or None if it must not be served
        """
        segments = [segment for segment in sub_path.split("/") if segment]
        if any(segment.startswith(".") for segment in segments):
            # Hidden files (.git, .env...) are never public
            return None

        try:
            # The HTTP service resolves "..", but a link can still lead out of the root
            target = self._root.joinpath(*segments).resolve()
        except (OSError, RuntimeError):
            # Loop of links (RuntimeError before Python 3.13)
            return None

        if not target.is_relative_to(self._root):
            return None
        if any(part.startswith(".") for part in target.relative_to(self._root).parts):
            # A link inside the root must not expose a hidden file either
            return None
        return target

    def _serve(
        self,
        request: http.AbstractHTTPServletRequest,
        response: http.AbstractHTTPServletResponse,
        with_body: bool,
    ) -> None:
        """
        Answers a GET or HEAD request.

        :param request: The request
        :param response: The response
        :param with_body: If False, only the headers are sent
        """
        path = request.get_path()
        sub_path = request.get_sub_path()
        target = self._resolve(sub_path)
        if target is not None and target.is_dir():
            if not path.endswith("/"):
                # Relative links of the index page must resolve inside the folder
                response.set_response(301)
                response.set_header("Location", urllib.parse.quote(path + "/"))
                response.set_header("Content-Length", 0)
                response.end_headers()
                return

            target = self._resolve(f"{sub_path}/{self._index}") if self._index else None
        elif path.endswith("/"):
            # A file is not a folder
            target = None

        if target is None:
            self._send_status(response, 404, with_body)
            return

        try:
            # Opened once, without following a link swapped in meanwhile nor
            # blocking on a FIFO: the checks apply to what is actually read
            descriptor = os.open(target, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError:
            self._send_status(response, 404, with_body)
            return

        with os.fdopen(descriptor, "rb") as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode):
                self._send_status(response, 404, with_body)
                return

            modified = int(info.st_mtime)
            if self._not_modified(request, modified):
                response.set_response(304)
                response.end_headers()
                return

            try:
                content = file.read() if with_body else b""
            except OSError:
                self._send_status(response, 404, with_body)
                return

        mime_type, _ = mimetypes.guess_type(target.name)
        if mime_type is None:
            mime_type = "application/octet-stream"
        elif mime_type.startswith("text/") or mime_type in _TEXT_TYPES:
            mime_type += "; charset=utf-8"

        response.set_response(200)
        response.set_header("Content-Type", mime_type)
        response.set_header("Content-Length", len(content) if with_body else info.st_size)
        response.set_header("Last-Modified", email.utils.formatdate(modified, usegmt=True))
        response.set_header("X-Content-Type-Options", "nosniff")
        for name, value in self._headers.items():
            response.set_header(name, value)
        response.end_headers()
        if with_body:
            response.write(content)

    @staticmethod
    def _not_modified(request: http.AbstractHTTPServletRequest, modified: int) -> bool:
        """
        Tells if the client copy is up to date, according to If-Modified-Since
        """
        since = request.get_header("If-Modified-Since")
        if not since:
            return False

        try:
            date = email.utils.parsedate_to_datetime(since)
        except (TypeError, ValueError):
            # Invalid date: the header is ignored, as RFC 9110 requires
            return False

        if date.tzinfo is None:
            # The obsolete asctime format has no zone: it is assumed to be in UTC (RFC 9110, 5.6.7)
            date = date.replace(tzinfo=datetime.UTC)
        return modified <= date.timestamp()

    @staticmethod
    def _send_status(response: http.AbstractHTTPServletResponse, code: int, with_body: bool) -> None:
        """
        Sends an error code, with a short text body for a GET request
        """
        if with_body:
            response.send_content(code, http_client.responses.get(code, "Error"), "text/plain")
        else:
            response.set_response(code)
            response.set_header("Content-Length", 0)
            response.end_headers()


# ------------------------------------------------------------------------------


@ComponentFactory(http.FACTORY_HTTP_STATIC)
@Provides(http.Servlet)
@Property("_path", http.HTTP_SERVLET_PATH, None)
@Property("_root", http.HTTP_STATIC_ROOT, None)
@Property("_index", http.HTTP_STATIC_INDEX, DEFAULT_INDEX)
@Property("_headers", http.HTTP_STATIC_HEADERS, None)
class StaticFilesComponent:
    """
    Static files servlet configured with the ``pelix.http.static.*``
    properties of the component instance, read when it is validated.
    """

    def __init__(self) -> None:
        self._path: str | None = None
        self._root: str | None = None
        self._index: str | None = DEFAULT_INDEX
        self._headers: Mapping[str, Any] | None = None
        self.__servlet: StaticFilesServlet | None = None

    @Validate
    def _validate(self, _: BundleContext) -> None:
        """
        Component validated: checks the folder to serve

        :raise ValueError: No folder or not a folder
        """
        if not self._root:
            raise ValueError(f"Missing the {http.HTTP_STATIC_ROOT} property")
        headers = {str(name): str(value) for name, value in (self._headers or {}).items()}
        self.__servlet = StaticFilesServlet(self._root, self._index, headers)

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        """
        Component invalidated
        """
        self.__servlet = None

    def do_GET(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        servlet = self.__servlet
        if servlet is None:
            # Invalidated while the request was waiting
            StaticFilesServlet._send_status(response, 503, True)
        else:
            servlet.do_GET(request, response)

    def do_HEAD(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        servlet = self.__servlet
        if servlet is None:
            StaticFilesServlet._send_status(response, 503, False)
        else:
            servlet.do_HEAD(request, response)
