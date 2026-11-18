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
import logging
import mimetypes
import os
import re
import stat
import time
import urllib.parse
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import IO, Any

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

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

DEFAULT_INDEX = "index.html"
""" File served for a request on a folder, by default """

DEFAULT_CHARSET = "utf-8"
""" Charset declared for the text files, by default """

# Size of the blocks read from a file and written to the client
_CHUNK_SIZE = 64 * 1024

# Flags missing on a platform are ignored: O_BINARY only exists on Windows,
# O_NONBLOCK avoids blocking on a FIFO, O_NOFOLLOW only exists on POSIX
_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_BINARY", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)

# Opening each segment relatively to its parent refuses the links without a
# race between the check and the opening, where the platform allows it
_WALK_WITH_FD = hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd

# Returned instead of a descriptor for a folder: Windows can't open one
_FOLDER = -1

# Characters a Windows path segment must not hold: a drive or a data stream
# (file.txt:stream) separator, or a path separator
_FORBIDDEN_CHARS = ("/", "\\", ":") if os.name == "nt" else ("/",)

# An entity tag of an If-Match, If-None-Match header (RFC 9110, 8.8.3)
_ETAG_PATTERN = re.compile(r'(?:W/)?"[^"]*"')

# A single range of bytes (RFC 9110, 14.1.2): other forms are ignored
_RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)", re.IGNORECASE)


def _is_public(name: str) -> bool:
    """
    Tells if a path segment can be served: hidden files (.git, .env...) and
    segments changing the meaning of a path are never public
    """
    return bool(name) and not name.startswith(".") and not any(char in name for char in _FORBIDDEN_CHARS)


def _parse_date(value: str | None) -> float | None:
    """
    Parses an HTTP date

    :return: Its timestamp, or None if the value is missing or invalid
    """
    if not value:
        return None

    try:
        date = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        # Invalid date: the header is ignored, as RFC 9110 requires
        return None

    if date.tzinfo is None:
        # The obsolete asctime format has no zone: it is assumed to be in UTC (RFC 9110, 5.6.7)
        date = date.replace(tzinfo=datetime.UTC)
    return date.timestamp()


def _match_etag(header: str, etag: str, strong: bool) -> bool:
    """
    Tells if the entity tag of a file is listed in an If-Match or
    If-None-Match header (RFC 9110, 8.8.3.2)

    :param header: Header value
    :param etag: The (strong) entity tag of the file
    :param strong: Use the strong comparison: weak tags never match
    """
    if header.strip() == "*":
        # The file exists
        return True

    for match in _ETAG_PATTERN.finditer(header):
        tag = match.group(0)
        if tag.startswith("W/"):
            if strong:
                continue
            tag = tag[2:]
        if tag == etag:
            return True
    return False


class StaticFilesServlet:
    """
    Serves the files of a folder, for the GET and HEAD methods.

    Only regular files inside the folder are served: a path with a hidden
    segment (starting with a dot), a symbolic link (unless they are followed),
    a link leading out of the folder (unless allowed) or a folder without its
    index file is answered with a 404 error code. Folders are never listed.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        index: str | None = DEFAULT_INDEX,
        headers: Mapping[str, str] | None = None,
        charset: str | None = DEFAULT_CHARSET,
        follow_links: bool = False,
        links_outside: bool = False,
        mime_types: Iterable[str | os.PathLike[str]] = (),
        types: Mapping[str, str] | None = None,
    ) -> None:
        """
        :param root: Folder to serve
        :param index: File served for a request on a folder, None to refuse
                      those requests
        :param headers: Headers added to the responses of the served files
        :param charset: Charset declared for the ``text/*`` files, None to
                        declare none
        :param follow_links: Follow the symbolic links (and Windows junctions)
                             instead of hiding them
        :param links_outside: Followed links can lead out of the folder
        :param mime_types: Files mapping extensions to MIME types, in the
                           ``mime.types`` format of Apache
        :param types: Extension (with or without its dot) to MIME type, over
                      the default ones and those of the files
        :raise ValueError: Invalid root folder, index or combination of flags
        :raise OSError: Unreadable MIME types file
        """
        self._root = Path(root).resolve()
        if not self._root.is_dir():
            raise ValueError(f"Not a folder: {root}")
        if index and not _is_public(index):
            raise ValueError(f"Invalid index file name: {index}")
        if links_outside and not follow_links:
            raise ValueError("Links can't lead out of the folder if they are not followed")

        self._index = index or None
        self._headers = dict(headers or {})
        self._charset = charset or None
        self._follow_links = follow_links
        self._links_outside = links_outside

        # Not the module-level table: it reads the files of the host
        # (/etc/mime.types...), and the served types would change with it
        self._types = mimetypes.MimeTypes([os.fspath(name) for name in mime_types])
        for extension, mime_type in (types or {}).items():
            self._types.add_type(mime_type, extension if extension.startswith(".") else f".{extension}")

    def do_GET(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        """
        Sends the requested file, or the requested range of it
        """
        self._serve(request, response, True)

    def do_HEAD(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        """
        Sends the headers of the requested file, without its content
        """
        self._serve(request, response, False)

    def _open(self, segments: list[str]) -> int | None:
        """
        Opens the file or folder matching the given path segments, according
        to the links policy

        :param segments: Public segments of the path, relative to the root
        :return: A file descriptor, _FOLDER for a folder which was not opened,
                 or None if the path must not be served
        """
        if self._follow_links:
            return self._open_resolved(segments)
        if _WALK_WITH_FD:
            return self._open_walk(segments)
        return self._open_checked(segments)

    def _open_walk(self, segments: list[str]) -> int | None:
        """
        Opens each segment relatively to its parent, without following the
        links (POSIX)
        """
        descriptor = os.open(self._root, _OPEN_FLAGS)
        try:
            for segment in segments:
                child = os.open(segment, _OPEN_FLAGS, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
        except OSError:
            # A link (ELOOP), a missing file or a file used as a folder
            os.close(descriptor)
            return None
        return descriptor

    def _open_checked(self, segments: list[str]) -> int | None:
        """
        Opens a path if it holds no link, junction or alias, checked before
        and after the opening (Windows, which can't open relatively to a
        folder: a link swapped in and out during the opening is not seen)
        """
        path = self._root.joinpath(*segments)
        if not self._is_canonical(path):
            return None
        if path.is_dir():
            # Its index file is checked the same way
            return _FOLDER

        try:
            descriptor = os.open(path, _OPEN_FLAGS)
        except OSError:
            return None

        try:
            same = self._is_canonical(path) and os.path.samestat(os.fstat(descriptor), os.stat(path))
        except OSError:
            same = False
        if not same:
            os.close(descriptor)
            return None
        return descriptor

    @staticmethod
    def _is_canonical(path: Path) -> bool:
        """
        Tells if a path is its own resolution: links, junctions, short (8.3)
        names and trailing dots or spaces all resolve to another name
        """
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            return False
        return os.path.normcase(resolved) == os.path.normcase(path)

    def _open_resolved(self, segments: list[str]) -> int | None:
        """
        Opens a path after following its links
        """
        try:
            target = self._root.joinpath(*segments).resolve(strict=True)
        except (OSError, RuntimeError):
            # Missing file or loop of links (RuntimeError before Python 3.13)
            return None

        if target.is_relative_to(self._root):
            parts = target.relative_to(self._root).parts
        elif self._links_outside:
            # Skip the anchor ("/", "C:\\"), which is not a name
            parts = target.parts[1:]
        else:
            return None

        if not all(_is_public(part) for part in parts):
            # A link must not expose a hidden file either
            return None
        if target.is_dir():
            return _FOLDER

        try:
            # Without following a link swapped in after the resolution
            return os.open(target, _OPEN_FLAGS)
        except OSError:
            return None

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
        segments = [segment for segment in request.get_sub_path().split("/") if segment]
        name = segments[-1] if segments else ""
        descriptor = self._open(segments) if all(_is_public(segment) for segment in segments) else None

        if descriptor == _FOLDER or (descriptor is not None and stat.S_ISDIR(os.fstat(descriptor).st_mode)):
            if descriptor != _FOLDER:
                os.close(descriptor)
            if not path.endswith("/"):
                # Relative links of the index page must resolve inside the folder
                response.set_response(301)
                response.set_header("Location", urllib.parse.quote(path + "/"))
                response.set_header("Content-Length", 0)
                response.end_headers()
                return

            descriptor = self._open([*segments, self._index]) if self._index else None
            name = self._index or ""
            if descriptor == _FOLDER:
                # The index is a folder
                descriptor = None
        elif descriptor is not None and path.endswith("/"):
            # A file is not a folder
            os.close(descriptor)
            descriptor = None

        if descriptor is None:
            self._send_status(response, 404, with_body)
            return

        with os.fdopen(descriptor, "rb") as file:
            info = os.fstat(descriptor)
            if stat.S_ISREG(info.st_mode):
                self._send_file(request, response, file, info, name, with_body)
            else:
                self._send_status(response, 404, with_body)

    def _send_file(
        self,
        request: http.AbstractHTTPServletRequest,
        response: http.AbstractHTTPServletResponse,
        file: IO[bytes],
        info: os.stat_result,
        name: str,
        with_body: bool,
    ) -> None:
        """
        Sends an opened regular file, after evaluating the preconditions and
        the range of the request (RFC 9110, 13.2.2)
        """
        size = info.st_size
        # A sub-second modification time makes it a strong validator (RFC 9110, 8.8.3.1)
        etag = f'"{info.st_mtime_ns:x}-{size:x}"'
        # Never later than the response itself (RFC 9110, 8.8.2.1)
        modified = min(int(info.st_mtime), int(time.time()))
        validators = {"ETag": etag, "Last-Modified": email.utils.formatdate(modified, usegmt=True)}

        failed = self._check_preconditions(request, etag, modified)
        if failed == 304:
            # Only the validators and the configured headers: no representation
            # metadata (RFC 9110, 15.4.5)
            response.set_response(304)
            for header, value in {**validators, **self._headers}.items():
                response.set_header(header, value)
            response.end_headers()
            return
        elif failed is not None:
            self._send_status(response, failed, with_body)
            return

        # Range is only defined for GET (RFC 9110, 14.2)
        part = self._get_range(request, etag, size) if with_body else None
        if part is not None and not part:
            response.set_response(416)
            response.set_header("Content-Range", f"bytes */{size}")
            response.set_header("Content-Length", 0)
            response.end_headers()
            return

        # The "./" prefix keeps a name like "data:x" from being taken for a URL
        mime_type, encoding = self._types.guess_type(f"./{name}")
        if mime_type is None:
            mime_type = "application/octet-stream"
        elif mime_type.startswith("text/") and self._charset:
            mime_type += f"; charset={self._charset}"

        if part is None:
            response.set_response(200)
            part = range(size)
        else:
            response.set_response(206)
            response.set_header("Content-Range", f"bytes {part.start}-{part.stop - 1}/{size}")

        response.set_header("Content-Type", mime_type)
        if encoding:
            response.set_header("Content-Encoding", encoding)
        response.set_header("Content-Length", len(part))
        response.set_header("Accept-Ranges", "bytes")
        response.set_header("X-Content-Type-Options", "nosniff")
        for header, value in {**validators, **self._headers}.items():
            response.set_header(header, value)
        response.end_headers()

        if with_body:
            self._copy(file, part, response, name)

    @staticmethod
    def _check_preconditions(
        request: http.AbstractHTTPServletRequest, etag: str, modified: int
    ) -> int | None:
        """
        Evaluates the preconditions of a GET or HEAD request, in the order of
        RFC 9110, 13.2.2 (If-Range is evaluated with the range)

        :return: The status code to answer (304, 412), None to go on
        """
        if_match = request.get_header("If-Match")
        if if_match is not None:
            if not _match_etag(if_match, etag, True):
                return 412
        else:
            date = _parse_date(request.get_header("If-Unmodified-Since"))
            if date is not None and modified > date:
                return 412

        if_none_match = request.get_header("If-None-Match")
        if if_none_match is not None:
            if _match_etag(if_none_match, etag, False):
                return 304
        else:
            date = _parse_date(request.get_header("If-Modified-Since"))
            if date is not None and modified <= date:
                return 304
        return None

    @staticmethod
    def _get_range(request: http.AbstractHTTPServletRequest, etag: str, size: int) -> range | None:
        """
        Finds the range of bytes to send (RFC 9110, 13.1.5 and 14)

        :return: The range to send, an empty range if it can't be satisfied,
                 None to send the whole file
        """
        header = request.get_header("Range")
        if not header or size == 0:
            # A range of an empty file could only be empty: send it whole
            return None

        if_range = request.get_header("If-Range")
        if if_range is not None and if_range.strip() != etag:
            # Changed file, or a date: a date at the second is a weak
            # validator, which can't match (RFC 9110, 8.8.2.2)
            return None

        match = _RANGE_PATTERN.fullmatch(header.strip())
        if match is None:
            # Several ranges, another unit or an invalid range: ignored, as allowed
            return None

        try:
            first, last = (int(value) if value else None for value in match.groups())
        except ValueError:
            # Beyond the number of digits Python converts
            return None

        if first is not None:
            if last is not None and last < first:
                # Invalid range
                return None
            start = first
            stop = last + 1 if last is not None else size
        elif last is not None:
            # Suffix: the last bytes of the file
            start = max(size - last, 0)
            stop = size if last else 0
        else:
            return None

        if start >= size or stop <= start:
            return range(0)
        return range(start, min(stop, size))

    @staticmethod
    def _copy(file: IO[bytes], part: range, response: http.AbstractHTTPServletResponse, name: str) -> None:
        """
        Sends a range of a file by blocks
        """
        file.seek(part.start)
        remaining = len(part)
        while remaining > 0:
            block = file.read(min(_CHUNK_SIZE, remaining))
            if not block:
                # Too late to change the length: the client gets a truncated answer
                _logger.warning("File %s shrank while being sent", name)
                return
            response.write(block)
            remaining -= len(block)

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
@Property("_charset", http.HTTP_STATIC_CHARSET, DEFAULT_CHARSET)
@Property("_follow_links", http.HTTP_STATIC_FOLLOW_LINKS, False)
@Property("_links_outside", http.HTTP_STATIC_LINKS_OUTSIDE, False)
@Property("_mime_types", http.HTTP_STATIC_MIME_TYPES, None)
@Property("_types", http.HTTP_STATIC_TYPES, None)
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
        self._charset: str | None = DEFAULT_CHARSET
        self._follow_links: bool = False
        self._links_outside: bool = False
        self._mime_types: str | Iterable[str] | None = None
        self._types: Mapping[str, str] | None = None
        self.__servlet: StaticFilesServlet | None = None

    @Validate
    def _validate(self, _: BundleContext) -> None:
        """
        Component validated: checks the configuration

        :raise ValueError: Invalid configuration
        :raise OSError: Unreadable MIME types file
        """
        if not self._root:
            raise ValueError(f"Missing the {http.HTTP_STATIC_ROOT} property")
        headers = {str(name): str(value) for name, value in (self._headers or {}).items()}
        mime_types = [self._mime_types] if isinstance(self._mime_types, str) else self._mime_types or ()
        self.__servlet = StaticFilesServlet(
            self._root,
            self._index,
            headers,
            self._charset,
            bool(self._follow_links),
            bool(self._links_outside),
            mime_types,
            self._types,
        )

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
