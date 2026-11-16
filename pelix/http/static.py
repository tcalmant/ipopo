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

import email.utils
import mimetypes
import os
from pathlib import Path

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
    segment (starting with a dot), a link leading out of the folder or a
    folder without its index file is answered with a 404 error code. Folders
    are never listed.
    """

    def __init__(self, root: str | os.PathLike[str], index: str | None = DEFAULT_INDEX) -> None:
        """
        :param root: Folder to serve
        :param index: File served for a request on a folder, None to refuse
                      those requests
        :raise ValueError: The root is not a folder
        """
        self._root = Path(root).resolve()
        if not self._root.is_dir():
            raise ValueError(f"Not a folder: {root}")

        self._index = index or None

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
        if any(segment.startswith(".") or "\0" in segment for segment in segments):
            # Hidden files (.git, .env...) are never public
            return None

        # The HTTP service resolves "..", but a link can still lead out of the root
        target = self._root.joinpath(*segments).resolve()
        if not target.is_relative_to(self._root):
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
        sub_path = request.get_sub_path()
        target = self._resolve(sub_path)
        if target is not None and target.is_dir():
            if not sub_path.endswith("/"):
                # Relative links of the index page must resolve inside the folder
                response.set_response(301)
                response.set_header("Location", request.get_path() + "/")
                response.set_header("Content-Length", 0)
                response.end_headers()
                return

            target = target / self._index if self._index else None

        if target is None or not target.is_file():
            self._send_status(response, 404, with_body)
            return

        try:
            stat = target.stat()
            content = target.read_bytes() if with_body else b""
        except OSError:
            # Unreadable (rights) or removed meanwhile
            self._send_status(response, 404, with_body)
            return

        modified = int(stat.st_mtime)
        since = request.get_header("If-Modified-Since")
        if since:
            try:
                if modified <= email.utils.parsedate_to_datetime(since).timestamp():
                    response.set_response(304)
                    response.end_headers()
                    return
            except (TypeError, ValueError):
                # Invalid date: the header is ignored, as RFC 9110 requires
                pass

        mime_type, _ = mimetypes.guess_type(target.name)
        if mime_type is None:
            mime_type = "application/octet-stream"
        elif mime_type.startswith("text/") or mime_type in _TEXT_TYPES:
            mime_type += "; charset=utf-8"

        response.set_response(200)
        response.set_header("Content-Type", mime_type)
        response.set_header("Content-Length", stat.st_size)
        response.set_header("Last-Modified", email.utils.formatdate(modified, usegmt=True))
        response.set_header("X-Content-Type-Options", "nosniff")
        response.end_headers()
        if with_body:
            response.write(content)

    @staticmethod
    def _send_status(response: http.AbstractHTTPServletResponse, code: int, with_body: bool) -> None:
        """
        Sends an error code, with a short text body for a GET request
        """
        if with_body:
            response.send_content(code, "Not found", "text/plain")
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
class StaticFilesComponent:
    """
    Static files servlet configured with the ``pelix.http.static.*``
    properties of the component instance, read when it is validated.
    """

    def __init__(self) -> None:
        self._path: str | None = None
        self._root: str | None = None
        self._index: str | None = DEFAULT_INDEX
        self.__servlet: StaticFilesServlet | None = None

    @Validate
    def _validate(self, _: BundleContext) -> None:
        """
        Component validated: checks the folder to serve

        :raise ValueError: No folder or not a folder
        """
        if not self._root:
            raise ValueError(f"Missing the {http.HTTP_STATIC_ROOT} property")
        self.__servlet = StaticFilesServlet(self._root, self._index)

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        """
        Component invalidated
        """
        self.__servlet = None

    def do_GET(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        if self.__servlet is not None:
            self.__servlet.do_GET(request, response)

    def do_HEAD(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        if self.__servlet is not None:
            self.__servlet.do_HEAD(request, response)
