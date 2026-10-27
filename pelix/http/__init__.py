#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix HTTP package.

Defines the interfaces that must respect HTTP service implementations.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.2.4

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

import asyncio
import concurrent.futures
import email.message
import email.parser
import re
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import IO, Any, Protocol, runtime_checkable

from pelix.constants import Specification
from pelix.security import Credentials, Subject
from pelix.utilities import to_bytes

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 2, 4)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "FACTORY_HTTP_ASYNC",
    "FACTORY_HTTP_AUTH_BASIC",
    "FACTORY_HTTP_BASIC",
    "FACTORY_HTTP_CORS",
    "HTTPS_CERT_FILE",
    "HTTPS_KEY_FILE",
    "HTTPS_KEY_PASSWORD",
    "HTTP_ALLOWED_HOSTS",
    "HTTP_AUTHENTICATOR",
    "HTTP_AUTH_REALM",
    "HTTP_AUTH_REQUIRED",
    "HTTP_CASE_SENSITIVE_PATHS",
    "HTTP_CORS_CREDENTIALS",
    "HTTP_CORS_ENFORCE",
    "HTTP_CORS_EXPOSE_HEADERS",
    "HTTP_CORS_HANDLER",
    "HTTP_CORS_HEADERS",
    "HTTP_CORS_MAX_AGE",
    "HTTP_CORS_METHODS",
    "HTTP_CORS_ORIGINS",
    "HTTP_DEBUG_ERRORS",
    "HTTP_ERROR_PAGES",
    "HTTP_MAX_BODY_SIZE",
    "HTTP_PROXY_TRUSTED",
    "HTTP_SERVICE",
    "HTTP_SERVICE_ADDRESS",
    "HTTP_SERVICE_PORT",
    "HTTP_SERVLET",
    "HTTP_SERVLET_ASYNC",
    "HTTP_SERVLET_ASYNC_PATH",
    "HTTP_SERVLET_PATH",
    "HTTP_SESSION_COOKIE_NAME",
    "HTTP_SESSION_ENABLED",
    "HTTP_SESSION_MAX_INACTIVE_INTERVAL",
    "HTTP_SOCKET_TIMEOUT",
    "HTTP_USES_SSL",
    "HTTP_WEBSOCKET_HANDLER",
    "HTTP_WEBSOCKET_PATH",
    "PARAM_ADDRESS",
    "PARAM_ASYNC",
    "PARAM_EXTRA",
    "PARAM_HTTPS",
    "PARAM_NAME",
    "PARAM_PORT",
    "AbstractAsyncHTTPServletRequest",
    "AbstractAsyncHTTPServletResponse",
    "AbstractAsyncWriter",
    "AbstractHTTPServletRequest",
    "AbstractHTTPServletResponse",
    "AbstractWebSocketHandler",
    "AsyncServlet",
    "BodyTooLargeError",
    "CorsHandler",
    "ErrorHandler",
    "HTTPService",
    "HeadersView",
    "HttpAuthenticator",
    "HttpSession",
    "MultipartError",
    "Part",
    "Servlet",
    "ServletType",
    "WebSocketHandler",
    "WebSocketSession",
    "format_cookie",
    "make_html_list",
    "parse_cookies",
    "parse_multipart",
    "read_body",
]

# ------------------------------------------------------------------------------

# HTTP service constants
HTTP_SERVICE = "pelix.http.service"
""" HTTP Service specification """

# ... binding address
HTTP_SERVICE_ADDRESS = "pelix.http.address"
""" HTTP Service binding address property (string) """

# ... binding port
HTTP_SERVICE_PORT = "pelix.http.port"
""" HTTP Service binding port property (int) """

# ... server uses SSL (read-only flag)
HTTP_USES_SSL = "pelix.https"
""" Read-only flag indicating if the server is using SSL (HTTPS) """

# ... the certificate file for HTTPS servers
HTTPS_CERT_FILE = "pelix.https.cert_file"
""" Path to the certificate file to configure a HTTPS server """

# ... the key file for HTTPS servers
HTTPS_KEY_FILE = "pelix.https.key_file"
""" Path to the certificate key file to configure a HTTPS server """

# ... the password of the key file for HTTPS servers
# (supported since Python 3.3)
HTTPS_KEY_PASSWORD = "pelix.https.key_password"

# ... send the details of errors to the clients
HTTP_DEBUG_ERRORS = "pelix.http.debug"
"""
If set, error pages sent to clients contain the stack trace of the error and
the 404 page lists the registered servlet paths (boolean, False by default).

Stack traces give details about the server (installed packages, file paths,
handled data, ...): this flag must be kept unset in production. The details of
an error are always logged by the server, along with the error ID shown in the
error page.
"""

# ... maximum size of the body of a request
HTTP_MAX_BODY_SIZE = "pelix.http.max_body_size"
"""
Maximum size, in bytes, of the body of a request (integer, 1 MiB by default).

A request declaring a bigger body is answered with a 413 error code. A value
lesser than or equal to 0 removes the limit.
"""

# ... timeout of the sockets of the server
HTTP_SOCKET_TIMEOUT = "pelix.http.socket_timeout"
"""
Timeout, in seconds, of the sockets handling the requests (float, 60 by
default).

Avoids a slow client to keep a request handling thread busy forever. A value
lesser than or equal to 0 removes the timeout.
"""

# ... Host header whitelist
HTTP_ALLOWED_HOSTS = "pelix.http.allowed_hosts"
"""
Host names the server accepts in the ``Host`` header of the requests (string,
comma-separated string or list of strings, not set by default).

A request whose ``Host`` header is missing or not listed is answered with a 403
error code, before any servlet is looked for. This protects the server against
DNS rebinding: a page loaded from a hostile name resolving to the server
address can otherwise read its responses, as the browser sees them as
same-origin.

An entry without port matches any port (``localhost``), an entry with a port
only matches this port (``localhost:8080``). IPv6 literals are given in
brackets (``[::1]``). The comparison is case-insensitive. If not set or
empty, the ``Host`` header is not checked.

.. versionadded:: 3.3.0
"""

# ... case sensitivity of the servlet paths
HTTP_CASE_SENSITIVE_PATHS = "pelix.http.case_sensitive_paths"
"""
Whether servlet paths are matched case-sensitively (boolean, True by default).

URI paths are case-sensitive (RFC 3986), so ``/Admin`` and ``/admin`` are two
different resources. Setting this property to False restores the folding of
earlier versions, in which they were the same one: it is provided only to give
an existing deployment time to spell its paths as it registers them.
"""

# HTTP servlet constants
HTTP_SERVLET = "pelix.http.servlet"
""" HTTP Servlet service specification """

# ... servlet path(s) (string or list of strings)
HTTP_SERVLET_PATH = "pelix.http.path"
""" HTTP Servlet path(s) (string or list or tuple of strings) """

# Async servlet service specification
HTTP_SERVLET_ASYNC = "pelix.http.servlet.async"
""" Asynchronous HTTP Servlet service specification """

# ... servlet path(s) (string or list of strings)
HTTP_SERVLET_ASYNC_PATH = "pelix.http.path.async"
""" HTTP Asynchronous Servlet path(s) (string or list or tuple of strings) """

# WebSocket handler service specification
HTTP_WEBSOCKET_HANDLER = "pelix.http.websocket.handler"
""" WebSocket handler service specification """

# ... WebSocket handler path (string or list of strings)
HTTP_WEBSOCKET_PATH = "pelix.http.websocket.path"
""" WebSocket handler path(s) (string or list or tuple of strings) """

# Service to provide custom 404 and 500 error pages
HTTP_ERROR_PAGES = "pelix.http.error.pages"

# Cross-Origin Resource Sharing (CORS)
HTTP_CORS_HANDLER = "pelix.http.cors.handler"
"""
Specification of the service giving the CORS policy of the HTTP services.

When no such service is bound, and no servlet declares its own policy, the
HTTP services don't send any CORS header.
"""

HTTP_CORS_ORIGINS = "pelix.http.cors.origins"
"""
Origins allowed to read the responses (string or list of strings).
``*`` allows any origin, an empty list none.

As a servlet service property, it declares the CORS policy of the servlet: it
replaces the one of the bound CORS handler service, if any. The other
``pelix.http.cors.*`` servlet properties are only read when it is set.
"""

HTTP_CORS_METHODS = "pelix.http.cors.methods"
"""
Methods allowed in cross-origin requests (string, comma-separated string or
list of strings). If not set, the method of a preflight request is allowed.
"""

HTTP_CORS_HEADERS = "pelix.http.cors.headers"
"""
Request headers allowed in cross-origin requests (string, comma-separated
string or list of strings). If not set, the headers of a preflight request are
allowed.
"""

HTTP_CORS_EXPOSE_HEADERS = "pelix.http.cors.expose_headers"
"""
Response headers the client script is allowed to read, in addition to the
CORS-safelisted ones (string, comma-separated string or list of strings).
"""

HTTP_CORS_CREDENTIALS = "pelix.http.cors.credentials"
"""
If True, cross-origin requests can carry credentials (cookies, authorization
header, ...). The allowed origin is then always sent explicitly, never as
``*`` (boolean, False by default).
"""

HTTP_PROXY_TRUSTED = "pelix.http.proxy.trusted"
"""
HTTP service property: addresses or networks (CIDR) of the reverse proxies
allowed to tell who the client is, as a list or a comma-separated string.

When the peer of a request is one of them, the right-most address of the
``X-Forwarded-For`` header which is not a trusted proxy becomes the address
of the client, and ``X-Forwarded-Proto`` tells if it used HTTPS. They are
ignored for any other peer. The proxy must keep the ``Host`` header of the
client. Empty by default: those headers are never read.
"""

HTTP_SESSION_ENABLED = "pelix.http.session.enabled"
"""
HTTP service property: if set, servlets can use ``get_session()``, ``login()``
and ``logout()`` of their request, and the user logged in a session is the
subject of the later requests (boolean, False by default). There is one set of
sessions per HTTP service, kept in memory: a restart logs everyone out.

The session cookie is ``HttpOnly`` and ``SameSite=Lax``, and ``Secure`` when the
client used HTTPS (see ``pelix.http.proxy.trusted``). Its content is a random
identifier, replaced on each login. The ``Lax`` attribute and
``pelix.http.cors.enforce`` are the protection against cross-site requests.
"""

HTTP_SESSION_MAX_INACTIVE_INTERVAL = "pelix.http.session.max_inactive_interval"
""" Seconds without request after which a session is dropped (1800 by default) """

HTTP_SESSION_COOKIE_NAME = "pelix.http.session.cookie.name"
"""
Name of the session cookie (``PELIXSESSIONID`` by default). Cookies don't
isolate ports: services of one host must use different names
"""

HTTP_CORS_ENFORCE = "pelix.http.cors.enforce"
"""
HTTP service property: if set, a request carrying an ``Origin`` header which is
neither the origin of the server nor allowed by the CORS policy is answered
with a 403 error code, and no servlet is called (boolean, False by default).

Without it, the CORS policy only decides which ``Access-Control-*`` headers are
sent: a "simple" cross-site request, like a form posted by a page of another
site, is still handled by the servlet, and only its response is hidden from
the page. A request without ``Origin`` header (not sent by a browser) is never
refused. Preflight requests are not concerned: they are always answered by the
server.

.. versionadded:: 3.3.0
"""

HTTP_CORS_MAX_AGE = "pelix.http.cors.max_age"
"""
Time, in seconds, a client can cache the result of a preflight request
(integer). If not set, the client decides.
"""

# Authentication
HTTP_AUTHENTICATOR = "pelix.http.auth.authenticator"
"""
Specification of the services extracting credentials from HTTP requests
(see :class:`HttpAuthenticator`)
"""

HTTP_AUTH_REQUIRED = "pelix.http.auth.required"
"""
If True, requests must carry valid credentials, else they are answered with a
401 error code (boolean, False by default).

As a property of the HTTP service, it applies to all paths. As a servlet
service property, it overrides the one of the HTTP service for the requests
handled by the servlet, in both directions.
"""

HTTP_AUTH_REALM = "pelix.http.auth.realm"
"""
Name of the protection space given in authentication challenges (string,
"Pelix" by default). Can be overridden by a servlet service property.
"""


# ------------------------------------------------------------------------------

FACTORY_HTTP_BASIC = "pelix.http.service.basic.factory"
""" Name of the HTTP service component factory """

FACTORY_HTTP_ASYNC = "pelix.http.service.async.factory"
""" Name of the Async HTTP service component factory """

FACTORY_HTTP_AUTH_BASIC = "pelix.http.auth.basic.factory"
"""
Name of the component factory of the HTTP Basic authentication service (see
:mod:`pelix.http.auth`)
"""

FACTORY_HTTP_CORS = "pelix.http.cors.factory"
"""
Name of the component factory of a CORS handler service, configured with the
``pelix.http.cors.*`` properties (see :mod:`pelix.http.cors`)
"""

# ------------------------------------------------------------------------------

PARAM_NAME = "http.name"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains the name of the server.
If the HTTP service is implemented with iPOPO, it might be the instance name.
"""

PARAM_EXTRA = "http.extra"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains a copy of extra properties of the HTTP service implementation.
Its content is implementation dependent.
"""

PARAM_ADDRESS = "http.address"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains the socket binding address of the HTTP server binding the servlet
"""

PARAM_PORT = "http.port"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains the listening port of the HTTP server binding the servlet
"""

PARAM_HTTPS = "http.https"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains a boolean: if True, the connection to the server is encrypted (HTTPS)
"""

PARAM_ASYNC = "http.async"
"""
Entry in the parameters dictionary of ``bound_to`` and ``unbound_from``.
Contains a boolean: if True, the servlet is bound as an asynchronous servlet.
"""

# ------------------------------------------------------------------------------


def make_html_list(items: Iterable[Any], tag: str = "ul") -> str:
    """
    Makes a HTML list from the given iterable

    :param items: The items to list
    :param tag: The tag to use (ul or ol)
    :return: The HTML list code
    """
    html_list = "\n".join(f'<li><a href="{item}">{item}</a></li>' for item in items)
    return f"<{tag}>\n{html_list}\n</{tag}>"


# ------------------------------------------------------------------------------


class BodyTooLargeError(Exception):
    """
    The body of a request is bigger than the limit given by the
    ``pelix.http.max_body_size`` property of the HTTP service.
    """

    def __init__(self, size: int, max_size: int) -> None:
        """
        :param size: Size of the body of the request, in bytes
        :param max_size: Maximum accepted size, in bytes
        """
        super().__init__(f"Request body is too large: {size} bytes, maximum is {max_size}")
        self.size = size
        self.max_size = max_size


_COOKIE_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_COOKIE_VALUE = re.compile(r"[\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]*")
_BOUNDARY = re.compile(r"[0-9A-Za-z'()+_,./:=? -]{0,69}[0-9A-Za-z'()+_,./:=?-]")
_COOKIE_PATH = re.compile(r"[\x20-\x3a\x3c-\x7e]*")


def parse_cookies(header: str | None) -> dict[str, str]:
    """
    Parses the value of a ``Cookie`` header

    :param header: The header value, if any
    :return: The cookies by name. When a name is repeated, the first value wins:
             browsers send the most specific path first.
    """
    cookies: dict[str, str] = {}
    for item in (header or "").split(";"):
        name, sep, value = item.partition("=")
        if sep and name.strip():
            cookies.setdefault(name.strip(), value.strip().strip('"'))
    return cookies


def format_cookie(
    name: str,
    value: str,
    *,
    max_age: int | None = None,
    path: str = "/",
    secure: bool = False,
    http_only: bool = True,
    same_site: str = "Lax",
) -> str:
    """
    Prepares the value of a ``Set-Cookie`` header

    :param name: Cookie name (a token)
    :param value: Cookie value, without quote or separator: nothing is escaped
    :param max_age: Lifetime in seconds (0 deletes the cookie), None for a session cookie
    :param path: Path the cookie is sent for
    :param secure: If True, the browser only sends it over HTTPS
    :param http_only: If True, scripts can't read it
    :param same_site: ``Strict``, ``Lax`` or ``None`` (the latter needs ``secure``)
    :raise ValueError: A part isn't valid: it could split the header
    """
    if not _COOKIE_NAME.fullmatch(name) or not _COOKIE_VALUE.fullmatch(value):
        raise ValueError("Invalid cookie name or value")
    if not _COOKIE_PATH.fullmatch(path) or same_site not in ("Strict", "Lax", "None"):
        raise ValueError("Invalid cookie path or SameSite attribute")
    if same_site == "None" and not secure:
        raise ValueError("SameSite=None needs the Secure attribute")

    parts = [f"{name}={value}", f"Path={path}", f"SameSite={same_site}"]
    if max_age is not None:
        parts.append(f"Max-Age={int(max_age)}")
    if secure:
        parts.append("Secure")
    if http_only:
        parts.append("HttpOnly")
    return "; ".join(parts)


class HttpSession:
    """
    What the server remembers of a browser between its requests (the Servlet
    ``HttpSession``). Attributes are kept in memory, and the access is thread-safe.
    """

    def __init__(
        self, session_id: str, max_inactive_interval: int, expire: Callable[["HttpSession"], None]
    ) -> None:
        """
        :param session_id: The secret identifier, sent to the browser
        :param max_inactive_interval: Seconds without request before the session is dropped
        :param expire: Called with the session to drop it from the server
        """
        self._id = session_id
        self._max_inactive_interval = max_inactive_interval
        self._expire = expire
        self._attributes: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._new = True
        self._valid = True

    def _check(self) -> None:
        if not self._valid:
            raise RuntimeError("The session has been invalidated")

    def get_id(self) -> str:
        """
        Returns the identifier of the session: it is a secret, never log it
        """
        self._check()
        return self._id

    def is_new(self) -> bool:
        """
        Checks if the browser doesn't know this session yet
        """
        self._check()
        return self._new

    def get_max_inactive_interval(self) -> int:
        """
        Returns the seconds without request after which the session is dropped
        """
        return self._max_inactive_interval

    def get_attribute(self, name: str, default: Any = None) -> Any:
        """
        Returns an attribute

        :param name: Attribute name
        :param default: Value if the attribute isn't set
        """
        self._check()
        with self._lock:
            return self._attributes.get(name, default)

    def set_attribute(self, name: str, value: Any) -> None:
        """
        Sets an attribute

        :param name: Attribute name
        :param value: Attribute value
        """
        self._check()
        with self._lock:
            self._attributes[name] = value

    def remove_attribute(self, name: str) -> None:
        """
        Removes an attribute, if it is set

        :param name: Attribute name
        """
        self._check()
        with self._lock:
            self._attributes.pop(name, None)

    def invalidate(self) -> None:
        """
        Drops the session: the browser's cookie is of no use any more.
        Prefer ``logout()`` of the request, which also removes the cookie.
        Does nothing if the session is already invalidated.
        """
        with self._lock:
            if not self._valid:
                return
            self._valid = False
        self._expire(self)


class MultipartError(ValueError):
    """
    The body of a request is not the ``multipart/form-data`` it claims to be, or
    is over the limits of :func:`parse_multipart`. The services answer a 400.
    """


@dataclass(frozen=True)
class Part:
    """
    A field of a ``multipart/form-data`` body (the Servlet ``Part``). The data is
    in memory: the size of the body is bound by ``pelix.http.max_body_size``,
    which a servlet receiving files can raise for itself.
    """

    name: str
    """ Name of the form field """

    filename: str | None
    """ Name of the file as the browser sent it. It is not checked: never use it as a path """

    content_type: str | None
    """ Media type of the part, without parameters, if the client gave one: check the content, not this """

    data: bytes
    """ Content of the part """


def parse_multipart(content_type: str | None, body: bytes, max_parts: int = 100) -> list[Part]:
    """
    Splits a ``multipart/form-data`` body (RFC 7578)

    :param content_type: Value of the ``Content-Type`` header of the request
    :param body: The body of the request
    :param max_parts: Maximum number of parts accepted
    :return: The parts, in the order of the body
    :raise MultipartError: The body is malformed, or has too many parts
    """
    header = email.message.Message()
    header["Content-Type"] = content_type or ""
    boundary = header.get_param("boundary")
    if header.get_content_type() != "multipart/form-data" or not isinstance(boundary, str):
        raise MultipartError("Not a multipart/form-data request")
    if not _BOUNDARY.fullmatch(boundary):
        raise MultipartError("Invalid boundary")

    # Walked with find(), so that each part is copied once and a body of delimiters costs nothing
    delimiter = b"--" + boundary.encode("ascii")
    marker = b"\r\n" + delimiter
    pos = 0 if body.startswith(delimiter) else body.find(marker) + 2
    if pos < 2 and not body.startswith(delimiter):
        raise MultipartError("No delimiter")

    parts: list[Part] = []
    while True:
        pos += len(delimiter)
        if body[pos : pos + 2] == b"--":
            # Closing delimiter: the epilogue is ignored
            return parts

        if len(parts) >= max_parts:
            raise MultipartError(f"More than {max_parts} parts")

        # Spaces and tabs can pad the line of the delimiter
        eol = body.find(b"\r\n", pos)
        head_end = body.find(b"\r\n\r\n", eol)
        if eol < 0 or head_end < 0 or head_end - eol > 8192 or body[pos:eol].strip(b" \t"):
            raise MultipartError("Malformed part")

        fields = email.parser.HeaderParser().parsestr(body[eol + 2 : head_end].decode("utf-8", "replace"))
        name = fields.get_param("name", header="Content-Disposition")
        if fields.get_content_disposition() != "form-data" or not isinstance(name, str):
            raise MultipartError("A part isn't a form field")

        end = body.find(marker, head_end + 4)
        if end < 0:
            raise MultipartError("The closing delimiter is missing")

        parts.append(
            Part(
                name,
                fields.get_filename(),
                fields.get_content_type() if "Content-Type" in fields else None,
                body[head_end + 4 : end],
            )
        )
        pos = end + 2


async def read_body(reader: "asyncio.StreamReader", size: int | None, max_size: int | None) -> bytes:
    """
    Reads the body of a request from an asynchronous stream, without loading
    more than the accepted maximum size in memory.

    :param reader: The stream to read the body from
    :param size: Size of the body announced by the client, None if unknown
    :param max_size: Maximum accepted size, in bytes, None for no limit
    :return: The body of the request
    :raise BodyTooLargeError: The body is bigger than the accepted maximum size
    """
    if size is not None and max_size is not None and size > max_size:
        # The client announces a body we don't want to read
        raise BodyTooLargeError(size, max_size)

    if size is None:
        if max_size is None:
            # No bound at all: read until the end of the stream
            return await reader.read(-1)

        # Size of the body unknown (chunked request): read one byte more than
        # the maximum, to detect an oversized body without loading it all
        remaining = max_size + 1
    else:
        remaining = size

    # A stream can return less bytes than requested, even before its end
    data = bytearray()
    while remaining > 0:
        chunk = await reader.read(remaining)
        if not chunk:
            # End of the stream
            break

        data.extend(chunk)
        remaining -= len(chunk)

    if max_size is not None and len(data) > max_size:
        raise BodyTooLargeError(len(data), max_size)

    return bytes(data)


class _RequestMixin(ABC):
    """
    What the synchronous and asynchronous servlet requests share, once the
    HTTP service gave them the result of the trusted proxies and the sessions
    """

    remote: tuple[tuple[str, int], bool] | None = None
    """
    The client address and the security of its connection, once the trusted
    proxies are taken into account. It is set by the HTTP service.
    """

    sessions: Any = None
    """
    The sessions of the request, if ``pelix.http.session.enabled`` is set.
    It is set by the HTTP service.
    """

    def get_peer_address(self) -> tuple[str, int]:
        """
        Returns the address of the other end of the connection, i.e. of the
        reverse proxy if there is one

        :return: A (host, port) tuple
        :raise NotImplementedError: A request class written before this method
                                    must override ``get_client_address()``
        """
        raise NotImplementedError

    def get_client_address(self) -> tuple[str, int]:
        """
        Returns the address of the client, as told by the trusted proxies
        (see ``pelix.http.proxy.trusted``). Its port is 0 if it comes from a header.

        :return: A (host, port) tuple
        """
        return self.remote[0] if self.remote else self.get_peer_address()

    def is_secure(self) -> bool:
        """
        Checks if the client used HTTPS, as told by the trusted proxies

        :return: True if the request was sent over TLS
        """
        return bool(self.remote and self.remote[1])

    def _get_sessions(self) -> Any:
        if self.sessions is None:
            raise RuntimeError("HTTP sessions are not enabled: see pelix.http.session.enabled")
        return self.sessions

    def get_session(self, create: bool) -> HttpSession | None:
        """
        Returns the session of the browser

        :param create: If True, a session is started when there is none
        :return: The session, or None if there is none (or they are not enabled, unless ``create``)
        """
        return self._get_sessions().get(create) if create or self.sessions else None

    def change_session_id(self) -> str:
        """
        Replaces the identifier of the session, to call when the privileges of
        the browser change (``login()`` does it)

        :return: The new identifier
        :raise RuntimeError: There is no session
        """
        return self._get_sessions().change_id()

    def logout(self) -> None:
        """
        Forgets the user of the browser: its session is dropped, and so is its cookie
        """
        if self.sessions is not None:
            self.sessions.logout()


class _ResponseMixin(ABC):
    """
    What the synchronous and asynchronous servlet responses share
    """

    @abstractmethod
    def set_header(self, name: str, value: Any) -> None: ...

    def add_header(self, name: str, value: Any) -> None:
        """
        Adds a value to a header, e.g. ``Set-Cookie``, which can be sent many times.
        This method should not be called after ``end_headers()``.
        Without an override, a response class only keeps the last value.

        :param name: Header name
        :param value: Header value
        """
        self.set_header(name, value)

    def add_cookie(self, name: str, value: str, **attributes: Any) -> None:
        """
        Sends a cookie: see :func:`format_cookie` for the arguments.
        It is ``HttpOnly`` and ``SameSite=Lax`` unless told otherwise;
        pass ``secure=request.is_secure()`` for the browser to send it
        over HTTPS only.

        :raise ValueError: The cookie isn't valid
        """
        self.add_header("Set-Cookie", format_cookie(name, value, **attributes))


class AbstractHTTPServletRequest(_RequestMixin):
    """
    Abstract HTTP Servlet request helper
    """

    max_body_size: int | None = None
    """
    Maximum size, in bytes, of the body accepted by ``read_data()``, or None
    for no limit. It is set by the HTTP service, according to its
    ``pelix.http.max_body_size`` property.
    """

    @abstractmethod
    def get_command(self) -> str:
        """
        Returns the HTTP verb (GET, POST, ...) used for the request
        """
        ...

    def get_cookies(self) -> dict[str, str]:
        """
        Returns the cookies sent with the request

        :return: The cookie values by name
        """
        return parse_cookies(self.get_header("Cookie"))

    def get_parts(self, max_parts: int = 100) -> list[Part]:
        """
        Reads the fields of a ``multipart/form-data`` body (see :func:`parse_multipart`)

        :raise BodyTooLargeError: The body is bigger than the accepted maximum size
        :raise MultipartError: The body isn't a valid form
        """
        return parse_multipart(self.get_header("Content-Type"), self.read_data(), max_parts)

    def login(self, username: str, password: str) -> Subject:
        """
        Authenticates a user with a password, and makes it the subject of the
        later requests of the browser, in a new session. Failures count for the
        throttle of ``pelix.security``, by user and by client address.

        :return: The subject, to use for the rest of the request
        :raise AuthenticationFailed: Wrong credentials, or locked out
        """
        addr = self.get_client_address()[0]
        return self._get_sessions().login(username, password, addr)

    @abstractmethod
    def get_header(self, name: str, default: Any = None) -> Any:
        """
        Returns the value of a header

        :param name: Header name
        :param default: Default value if the header doesn't exist
        :return: The header value or the default one
        """
        ...

    @abstractmethod
    def get_headers(self) -> dict[str, Any]:
        """
        Returns a copy all headers, with a dictionary interface

        :return: A dictionary-like object
        """
        ...

    @abstractmethod
    def get_path(self) -> str:
        """
        Returns the request full path, normalized.

        The path is percent-decoded, its query string is removed, its repeated
        slashes are collapsed and its ``.`` and ``..`` segments are resolved.
        A segment therefore never holds a separator. Everything else the client
        encoded reaches the servlet unchanged, so a servlet mapping a segment
        onto a file system or another name space still has to validate it.

        :return: A request full path (string)
        """
        ...

    @abstractmethod
    def get_prefix_path(self) -> str:
        """
        Returns the path to the servlet root, as the servlet was registered.

        Servlet paths are matched case-sensitively unless
        :const:`HTTP_CASE_SENSITIVE_PATHS` says otherwise.

        :return: A request path (string)
        """
        ...

    @abstractmethod
    def get_sub_path(self) -> str:
        """
        Returns the servlet-relative path, i.e. after the prefix.

        It is cut out of the path :meth:`get_path` returns, so it carries the
        same guarantees.

        :return: A request path (string)
        """
        ...

    @abstractmethod
    def get_rfile(self) -> IO[bytes]:
        """
        Returns the request input as a file stream.

        The stream gives the raw body of the request: it is **not** limited by
        ``pelix.http.max_body_size``, unlike :meth:`read_data`.
        A servlet reading it is responsible for limiting the number of bytes it
        accepts.

        :return: A file-like input stream
        """
        ...

    def read_data(self) -> bytes:
        """
        Reads the body of the request, within the limit given by the
        ``pelix.http.max_body_size`` property.

        A request which doesn't declare a valid ``Content-Length`` header is
        considered as having an empty body: reading until the end of the stream
        would block the thread handling the request until the client decides to
        close the connection.

        :return: The read data
        :raise BodyTooLargeError: The declared body is bigger than the accepted
                                  maximum size
        """
        try:
            size = int(self.get_header("content-length"))
        except (ValueError, TypeError):
            # No (valid) content length: consider the body empty.
            # Reading until the end of the stream would block the handling
            # thread until the client closes the connection, and this stream
            # doesn't decode the chunked transfer encoding anyway.
            size = 0

        max_size = self.max_body_size
        if max_size is not None:
            if size > max_size:
                raise BodyTooLargeError(size, max_size)

            # Don't trust the declared size either
            size = min(size, max_size)

        return self.get_rfile().read(size)


class AbstractHTTPServletResponse(_ResponseMixin):
    """
    HTTP Servlet response helper
    """

    @abstractmethod
    def set_response(self, code: int, message: str | None = None) -> None:
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        ...

    @abstractmethod
    def set_header(self, name: str, value: Any) -> None:
        """
        Sets the value of a header.
        This method should not be called after ``end_headers()``.

        :param name: Header name
        :param value: Header value
        """
        ...

    @abstractmethod
    def is_header_set(self, name: str) -> bool:
        """
        Checks if the given header has already been set

        :param name: Header name
        :return: True if it has already been set
        """
        ...

    @abstractmethod
    def end_headers(self) -> None:
        """
        Ends the headers part
        """
        ...

    @abstractmethod
    def get_wfile(self) -> IO[bytes]:
        """
        Retrieves the output as a file stream.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :return: A file-like output stream
        """
        ...

    @abstractmethod
    def write(self, data: bytes) -> None:
        """
        Writes the given data.
        ``end_headers()`` should have been called before, except if you want
        to write your own headers.

        :param data: Data to be written
        """
        ...

    def send_content(
        self,
        http_code: int,
        content: str,
        mime_type: str | None = "text/html",
        http_message: str | None = None,
        content_length: int = -1,
    ) -> None:
        """
        Utility method to send the given content as an answer.
        You can still use get_wfile or write afterwards, if you forced the
        content length.

        If content_length is negative (default), it will be computed as the
        length of the content;
        if it is positive, the given value will be used;
        if it is None, the content-length header won't be sent.

        :param http_code: HTTP result code
        :param content: Data to be sent (must be a string)
        :param mime_type: Content MIME type (content-type)
        :param http_message: HTTP code description
        :param content_length: Forced content length
        """
        self.set_response(http_code, http_message)
        if mime_type and not self.is_header_set("content-type"):
            self.set_header("content-type", mime_type)

        # Convert the content
        raw_content = to_bytes(content)

        if content_length is not None and not self.is_header_set("content-length"):
            if content_length < 0:
                # Compute the length
                content_length = len(raw_content)

            # Send the length
            self.set_header("content-length", content_length)

        self.end_headers()

        # Send the content
        self.write(raw_content)


class AbstractAsyncHTTPServletRequest(_RequestMixin):
    """
    Asynchronous HTTP Servlet request helper
    """

    max_body_size: int | None = None
    """
    Maximum size, in bytes, of the body accepted by ``read_data()``, or None
    for no limit. It is set by the HTTP service, according to its
    ``pelix.http.max_body_size`` property.
    """

    @abstractmethod
    def get_command(self) -> str:
        """
        Returns the HTTP verb (GET, POST, ...) used for the request
        """
        ...

    async def get_cookies(self) -> dict[str, str]:
        """
        See :meth:`AbstractHTTPServletRequest.get_cookies`
        """
        return parse_cookies(await self.get_header("Cookie"))

    async def get_parts(self, max_parts: int = 100) -> list[Part]:
        """
        See :meth:`AbstractHTTPServletRequest.get_parts`
        """
        content_type, body = await self.get_header("Content-Type"), await self.read_data()
        # A big upload must not block the event loop while it is parsed
        return await asyncio.to_thread(parse_multipart, content_type, body, max_parts)

    async def login(self, username: str, password: str) -> Subject:
        """
        See :meth:`AbstractHTTPServletRequest.login`
        """
        addr = self.get_client_address()[0]
        return await asyncio.to_thread(self._get_sessions().login, username, password, addr)

    @abstractmethod
    async def get_header(self, name: str, default: Any = None) -> Any:
        """
        Returns the value of a header

        :param name: Header name
        :param default: Default value if the header doesn't exist
        :return: The header value or the default one
        """
        ...

    @abstractmethod
    async def get_headers(self) -> dict[str, Any]:
        """
        Returns a copy all headers, with a dictionary interface

        :return: A dictionary-like object
        """
        ...

    @abstractmethod
    def get_path(self) -> str:
        """
        Returns the request full path, normalized.

        The path is percent-decoded, its query string is removed, its repeated
        slashes are collapsed and its ``.`` and ``..`` segments are resolved.
        A segment therefore never holds a separator. Everything else the client
        encoded reaches the servlet unchanged, so a servlet mapping a segment
        onto a file system or another name space still has to validate it.

        :return: A request full path (string)
        """
        ...

    @abstractmethod
    def get_prefix_path(self) -> str:
        """
        Returns the path to the servlet root, as the servlet was registered.

        Servlet paths are matched case-sensitively unless
        :const:`HTTP_CASE_SENSITIVE_PATHS` says otherwise.

        :return: A request path (string)
        """
        ...

    @abstractmethod
    def get_sub_path(self) -> str:
        """
        Returns the servlet-relative path, i.e. after the prefix.

        It is cut out of the path :meth:`get_path` returns, so it carries the
        same guarantees.

        :return: A request path (string)
        """
        ...

    @abstractmethod
    def get_rfile(self) -> asyncio.StreamReader:
        """
        Returns the request input as a stream reader.

        The reader gives the raw body of the request: it is **not** limited by
        ``pelix.http.max_body_size``, unlike :meth:`read_data`.
        A servlet reading it is responsible for limiting the number of bytes it
        accepts.

        :return: A stream reader for the input stream
        """
        ...

    async def read_data(self) -> bytes:
        """
        Reads the body of the request, within the limit given by the
        ``pelix.http.max_body_size`` property.

        A request which doesn't declare a valid ``Content-Length`` header, e.g.
        a chunked one, is read until the end of its stream, the limit then
        applying to the bytes actually read.

        :return: The read data
        :raise BodyTooLargeError: The body is bigger than the accepted maximum
                                  size
        """
        try:
            size: int | None = int(await self.get_header("content-length"))
        except (ValueError, TypeError):
            # Unlike the synchronous implementation, reading until the end of
            # the stream is safe here: the underlying reader is bound by the
            # transfer framing, and a missing content length is how a chunked
            # request looks like.
            size = None

        return await read_body(self.get_rfile(), size, self.max_body_size)


class AbstractAsyncWriter(ABC):
    """
    Abstract class to wrap asynchronous writers
    """

    @abstractmethod
    async def write(self, raw: bytes) -> int:
        """
        Writes raw data to the stream

        :param raw: Data to write
        :return: Number of bytes written
        """
        ...

    async def flush(self) -> None:
        """
        Flushes the buffer if any
        """
        ...  # noqa: PIE790


class AbstractAsyncHTTPServletResponse(_ResponseMixin):
    """
    Asynchronous HTTP Servlet response helper
    """

    @abstractmethod
    def set_response(self, code: int, message: str | None = None) -> None:
        """
        Sets the response line.
        This method should be the first called when sending an answer.

        :param code: HTTP result code
        :param message: Associated message
        """
        ...

    @abstractmethod
    def set_header(self, name: str, value: Any) -> None:
        """
        Sets the value of a header.
        This method should not be called after ``end_headers()``.

        :param name: Header name
        :param value: Header value
        """
        ...

    @abstractmethod
    def is_header_set(self, name: str) -> bool:
        """
        Checks if the given header has already been set

        :param name: Header name
        :return: True if it has already been set
        """
        ...

    @abstractmethod
    def setup_sse(self, strict: bool = True) -> None:
        """
        Sets up the response for Server-Sent Events (SSE)

        :param strict: If True, raises an error if the request is not for SSE
        """
        raise NotImplementedError

    @abstractmethod
    async def end_headers(self) -> None:
        """
        Ends the headers part
        """
        ...

    @abstractmethod
    def get_wfile(self) -> AbstractAsyncWriter:
        """
        Retrieves the output as a writer.
        ``end_headers()`` should have been called before.

        :return: A writer for the output stream
        """
        ...

    @abstractmethod
    async def write(self, data: bytes) -> None:
        """
        Writes the given data.
        ``end_headers()`` should have been called before.

        :param data: Data to be written
        """
        out = self.get_wfile()
        await out.write(data)
        await out.flush()

    @abstractmethod
    async def send_sse(
        self, event: str | None = None, data: str | None = None, id: str | None = None
    ) -> None:
        """
        Sends a Server-Sent Event (SSE) message.

        :param event: The event name (optional)
        :param data: The event data (optional)
        :param id: The event ID (optional)
        """
        raise NotImplementedError

    async def send_content(
        self,
        http_code: int,
        content: str,
        mime_type: str | None = "text/html",
        http_message: str | None = None,
        content_length: int = -1,
    ) -> None:
        """
        Utility method to send the given content as an answer.
        You can still use get_wfile or write afterwards, if you forced the
        content length.

        If content_length is negative (default), it will be computed as the
        length of the content;
        if it is positive, the given value will be used;
        if it is None, the content-length header won't be sent.

        :param http_code: HTTP result code
        :param content: Data to be sent (must be a string)
        :param mime_type: Content MIME type (content-type)
        :param http_message: HTTP code description
        :param content_length: Forced content length
        """
        self.set_response(http_code, http_message)
        if mime_type and not self.is_header_set("content-type"):
            self.set_header("content-type", mime_type)

        # Convert the content
        raw_content = to_bytes(content)

        if content_length is not None and not self.is_header_set("content-length"):
            if content_length < 0:
                # Compute the length
                content_length = len(raw_content)

            # Send the length
            self.set_header("content-length", content_length)

        await self.end_headers()

        # Send the content
        await self.write(raw_content)


class ErrorHandler(Protocol):
    """
    Custom HTTP error page generator
    """

    def make_not_found_page(self, path: str) -> str:
        """
        Prepares a "page not found" page for a 404 error

        :param path: Request path
        :return: A HTML page
        """
        ...

    def make_exception_page(self, path: str, stack: str) -> str:
        """
        Prepares a page printing an exception stack trace in a 500 error

        :param path: Request path
        :param stack: Exception stack trace
        :return: A HTML page
        """
        ...


@Specification(HTTP_CORS_HANDLER)
class CorsHandler(Protocol):
    """
    Gives the Cross-Origin Resource Sharing (CORS) policy of the HTTP services.

    Each method is given the normalized path of the request, so that a single
    handler can give a different policy to different parts of the server.
    """

    def get_allowed_origins(self, path: str) -> Iterable[str]:
        """
        Returns the origins allowed to read the responses to requests on the
        given path

        :param path: Request path
        :return: The allowed origins; ``*`` allows any origin
        """
        ...

    def get_allowed_methods(self, path: str) -> Iterable[str] | None:
        """
        Returns the methods allowed in cross-origin requests on the given path

        :param path: Request path
        :return: The allowed methods, or None to allow the one of the request
        """
        ...

    def get_allowed_headers(self, path: str) -> Iterable[str] | None:
        """
        Returns the request headers allowed in cross-origin requests on the
        given path

        :param path: Request path
        :return: The allowed headers, or None to allow those of the request
        """
        ...

    def get_exposed_headers(self, path: str) -> Iterable[str] | None:
        """
        Returns the response headers a client script is allowed to read

        :param path: Request path
        :return: The exposed headers, or None
        """
        ...

    def allows_credentials(self, path: str) -> bool:
        """
        Checks if cross-origin requests on the given path can carry
        credentials

        :param path: Request path
        :return: True to allow credentials
        """
        ...

    def get_max_age(self, path: str) -> int | None:
        """
        Returns the time, in seconds, a client can cache the result of a
        preflight request on the given path

        :param path: Request path
        :return: A time in seconds, or None to let the client decide
        """
        ...


class HeadersView(Protocol):
    """
    Read-only, case-insensitive view on the headers of a request
    """

    def get(self, name: str, /) -> Any:
        """
        Returns the value of a header

        :param name: Header name (case-insensitive)
        :return: The header value, or None if it is missing
        """
        ...


@Specification(HTTP_AUTHENTICATOR)
class HttpAuthenticator(Protocol):
    """
    Extracts credentials from HTTP requests, for an authentication scheme.

    The credentials are then checked by the ``pelix.security`` services: an
    HTTP authenticator doesn't decide whether they are valid.
    """

    def get_scheme(self) -> str:
        """
        Returns the name of the authentication scheme, e.g. ``Basic``

        :return: The authentication scheme
        """
        ...

    def extract_credentials(self, headers: HeadersView) -> Credentials | None:
        """
        Extracts the credentials carried by a request, if it uses the scheme of
        this authenticator

        :param headers: The headers of the request
        :return: The credentials, or None if the request doesn't carry
                 credentials of this scheme
        :raise pelix.security.AuthenticationFailed: Malformed credentials
        """
        ...

    def get_challenge(self, realm: str) -> str:
        """
        Returns the challenge sent in the ``WWW-Authenticate`` header of a 401
        response, telling the client how to authenticate

        :param realm: The protection space of the requested resource
        :return: The challenge, e.g. ``Basic realm="Pelix", charset="UTF-8"``
        """
        ...


@Specification(HTTP_SERVLET)
class Servlet(Protocol):
    """
    Interface of an HTTP servlet

    Servlets are classes with `do_<VERB>` methods, where `<VERB>` is the
    HTTP verb used for the request (GET, POST, PUT, DELETE, ...).
    Those methods take two arguments: an AbstractHTTPServletRequest and an
    AbstractHTTPServletResponse.
    """


@Specification(HTTP_SERVLET_ASYNC)
class AsyncServlet(Protocol):
    """
    Interface of an asynchronous HTTP servlet

    Servlets are classes with `do_async_<VERB>` coroutines, where `<VERB>` is
    the HTTP verb used for the request (GET, POST, PUT, DELETE, ...).
    Those methods take two arguments: an AbstractAsyncHTTPServletRequest and an
    AbstractAsyncHTTPServletResponse.
    """


class WebSocketSession(Protocol):
    """
    Websocket session helper
    """

    def get_client_address(self) -> tuple[str, int]:
        """
        Returns the address of the client

        :return: A (host, port) tuple
        """
        ...

    async def send_binary(self, message: bytes) -> None:
        """
        Sends a binary message to the client

        :param message: Binary message to send
        """
        ...

    async def send_text(self, message: str) -> None:
        """
        Sends a message to the client

        :param message: Message to send
        """
        ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        """
        Closes the WebSocket session

        :param code: Close code (default is 1000, normal closure)
        :param reason: Optional reason for the closure
        """
        ...

    def submit_text(self, message: str) -> concurrent.futures.Future[None]:
        """
        Thread-safe :meth:`send_text`: can be called from any thread, e.g. a
        component pushing events from its own thread. Don't wait for the result
        from the event loop thread (deadlock).

        :param message: Message to send
        :return: A future set when the message is sent, or holding the
                 ``OSError`` of a closed session
        :raise OSError: The server is stopped
        """
        ...

    def submit_binary(self, message: bytes) -> concurrent.futures.Future[None]:
        """
        Thread-safe :meth:`send_binary`, see :meth:`submit_text`

        :param message: Binary message to send
        """
        ...

    def submit_close(self, code: int = 1000, reason: str | None = None) -> concurrent.futures.Future[None]:
        """
        Thread-safe :meth:`close`, see :meth:`submit_text`

        :param code: Close code (default is 1000, normal closure)
        :param reason: Optional reason for the closure
        """
        ...


@Specification(HTTP_WEBSOCKET_HANDLER)
@runtime_checkable
class WebSocketHandler(Protocol):
    """
    Interface of a WebSocket handler

    WebSocket handlers are classes with `on_open`, `on_message`, `on_close`
    and `on_error` methods.
    """

    async def ws_accept(self, request: AbstractAsyncHTTPServletRequest) -> bool:
        """
        Called when a new WebSocket connection is requested.

        :param request: The HTTP request that initiates the WebSocket connection
        :return: True if the connection is accepted, False to reject it
        """
        ...

    async def ws_open(self, session: WebSocketSession, request: AbstractAsyncHTTPServletRequest) -> None:
        """
        Called when a new WebSocket connection is opened
        """
        ...

    async def ws_binary(self, session: WebSocketSession, message: bytes) -> None:
        """
        Called when a binary message is received from the client
        """
        ...

    async def ws_message(self, session: WebSocketSession, message: str) -> None:
        """
        Called when a message is received from the client
        """
        ...

    async def ws_close(self, session: WebSocketSession, code: int, reason: str) -> None:
        """
        Called when the WebSocket connection is closed
        """
        ...

    async def ws_error(self, session: WebSocketSession, error: str) -> None:
        """
        Called when an error occurs
        """
        ...


class AbstractWebSocketHandler(WebSocketHandler):
    """
    Abstract class for WebSocket handlers

    This class can be used to implement a WebSocket handler with default methods.
    """

    async def ws_accept(self, request: AbstractAsyncHTTPServletRequest) -> bool:
        """
        Accepts all WebSocket connections by default
        """
        return True

    async def ws_open(self, session: WebSocketSession, request: AbstractAsyncHTTPServletRequest) -> None:
        """
        Default implementation does nothing
        """

    async def ws_binary(self, session: WebSocketSession, message: bytes) -> None:
        """
        Default implementation does nothing
        """

    async def ws_message(self, session: WebSocketSession, message: str) -> None:
        """
        Default implementation does nothing
        """

    async def ws_close(self, session: WebSocketSession, code: int, reason: str) -> None:
        """
        Default implementation does nothing
        """

    async def ws_error(self, session: WebSocketSession, error: str) -> None:
        """
        Default implementation does nothing
        """


class ServletType(Enum):
    """
    Type of servlet
    """

    SYNC = "sync"
    """ Synchronous servlet """

    ASYNC = "async"
    """ Asynchronous servlet """

    WEBSOCKET = "websocket"
    """ WebSocket handler """


@Specification(HTTP_SERVICE)
class HTTPService(Protocol):
    """
    HTTP service interface
    """

    def get_access(self) -> tuple[str, int]:
        """
        Retrieves the (address, port) tuple to access the server
        """
        ...

    def get_hostname(self) -> str:
        """
        Retrieves the server host name

        :return: The server host name
        """
        ...

    def is_https(self) -> bool:
        """
        Returns True if this is an HTTPS server

        :return: True if this server uses SSL
        """
        ...

    def get_registered_paths(self) -> list[str]:
        """
        Returns the paths registered by servlets

        :return: The paths registered by servlets (sorted list)
        """
        ...

    def get_servlet(self, path: str | None) -> tuple[Servlet, dict[str, Any], str, ServletType] | None:
        """
        Retrieves the servlet matching the given path and its parameters.
        Returns None if no servlet matches the given path.

        :param path: A request URI
        :return: A tuple (servlet, parameters, prefix, type) or None
        """
        ...

    def make_not_found_page(self, path: str) -> str:
        """
        Prepares a "page not found" page for a 404 error

        :param path: Request path
        :return: A HTML page
        """
        ...

    def make_exception_page(self, path: str, stack: str) -> str:
        """
        Prepares a page printing an exception stack trace in a 500 error

        :param path: Request path
        :param stack: Exception stack trace
        :return: A HTML page
        """
        ...

    def register_servlet(
        self,
        path: str,
        servlet: Servlet,
        parameters: dict[str, Any] | None = None,
        servlet_type: ServletType = ServletType.SYNC,
    ) -> bool:
        """
        Registers a servlet

        :param path: Path handled by this servlet
        :param servlet: The servlet instance
        :param parameters: The parameters associated to this path
        :param servlet_type: The type of servlet (sync, async, websocket, ...)
        :return: True if the servlet has been registered, False if it refused the binding.
        :raise ValueError: Invalid path or handler
        """
        ...

    def unregister(self, path: str | None, servlet: Servlet | None = None) -> bool:
        """
        Unregisters the servlet for the given path

        :param path: The path to a servlet
        :param servlet: If given, unregisters all the paths handled by this servlet
        :return: True if at least one path as been unregistered, else False
        """
        ...

    def log(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        """
        Logs the given message

        :param level: Log entry level
        :param message: Log message (Python logging format)
        """
        ...

    def log_exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """
        Logs an exception

        :param message: Log message (Python logging format)
        """
        ...
