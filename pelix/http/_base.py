#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Transport-independent part of the Pelix HTTP service implementations.

This module is private: it is shared by :mod:`pelix.http.basic` and
:mod:`pelix.http.basic_async` and is not part of the public API.

It holds everything that does not depend on the underlying HTTP server: the
servlet registry, the path matching, the error pages, the logging helpers and
the iPOPO binding logic.

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

import dataclasses
import hashlib
import html
import ipaddress
import logging
import re
import secrets
import socket
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from typing import Any, cast

import pelix.remote
from pelix import http, utilities
from pelix.http import auth, cors
from pelix.internals.registry import ServiceReference
from pelix.ipopo import constants
from pelix.ipopo.decorators import HiddenProperty, Modified, Property
from pelix.security import ANONYMOUS, ATTRIBUTE_SESSION_ID, Subject

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "DEFAULT_BIND_ADDRESS",
    "DEFAULT_REQUEST_QUEUE_SIZE",
    "HTTP_SERVICE_EXTRA",
    "LOCALHOST_ADDRESS",
    "LOOPBACK_HOST_NAMES",
    "SERVLET_PARAMETERS",
    "SESSION_USER",
    "AbstractHttpService",
    "RequestChecks",
    "RequestRouting",
    "SessionContext",
    "SessionManager",
    "compute_sub_path",
    "normalize_allowed_hosts",
    "normalize_max_body_size",
    "normalize_request_path",
    "normalize_trusted_proxies",
    "split_host_port",
]

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

HTTP_SERVICE_EXTRA = "http.extra"
""" HTTP service extra properties (dictionary) """

DEFAULT_BIND_ADDRESS = "127.0.0.1"
""" By default, bind to the local IPv4 interface only """

LOCALHOST_ADDRESS = "127.0.0.1"
"""
Local address, if None is given as binding address, instead of the default one
"""

LOOPBACK_HOST_NAMES = ("localhost", "127.0.0.1", "[::1]")
""" Default ``pelix.http.allowed_hosts`` of a service bound to a loopback address """

# Property -> field of the properties only read when the server starts
_RESTART_FIELDS = {
    http.HTTP_SERVICE_ADDRESS: "_address",
    http.HTTP_SERVICE_PORT: "_port",
    http.HTTPS_CERT_FILE: "_cert_file",
    http.HTTPS_KEY_FILE: "_key_file",
    http.HTTPS_KEY_PASSWORD: "_key_password",
    http.HTTP_SESSION_ENABLED: "_session_enabled",
    http.HTTP_SESSION_MAX_INACTIVE_INTERVAL: "_session_interval",
    http.HTTP_SESSION_COOKIE_NAME: "_session_cookie",
}

DEFAULT_REQUEST_QUEUE_SIZE = 5
""" Default size of the queue of clients waiting to be handled """

_MULTIPLE_SLASHES = re.compile("/+")
""" Matches a sequence of consecutive slashes """

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
""" Matches a control character, which has no place in a decoded request path """

AnyServlet = http.Servlet | http.AsyncServlet | http.WebSocketHandler
""" Any kind of servlet service (sync, async, web socket, ...) """

ServletEntry = tuple[AnyServlet, dict[str, Any], http.ServletType]
""" Servlet registry entry: (servlet, parameters, type) """

SERVLET_PARAMETERS = (http.HTTP_MAX_BODY_SIZE, *cors.SERVLET_CORS_PARAMETERS, *auth.SERVLET_AUTH_PARAMETERS)
"""
Properties of a servlet service which are copied in the parameters of its
registration, i.e. which a servlet can use to override a configuration of the
HTTP service
"""

# ------------------------------------------------------------------------------


def _to_bool(value: Any) -> bool:
    """
    Normalizes a boolean configuration value, which can be given as a string

    :param value: The raw value
    :return: The boolean value
    """
    if isinstance(value, str):
        return utilities.str2bool(value)

    return bool(value)


def normalize_max_body_size(value: Any) -> int | None:
    """
    Normalizes the value of a ``pelix.http.max_body_size`` configuration

    :param value: The raw value of the configuration
    :return: A size in bytes, or None if there is no limit
    """
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None

    # A non-positive value removes the limit
    return size if size > 0 else None


# ------------------------------------------------------------------------------


def normalize_request_path(raw_path: str) -> str:
    """
    Normalizes the path of an incoming request: removes the query string,
    decodes the percent-encoded characters, collapses the sequences of
    consecutive slashes and resolves the ``.`` and ``..`` segments.

    The result is the single path used both to look for a servlet and to
    compute the path given to that servlet, so that the two can never disagree.

    This must be called once, on the raw request path: as it decodes, applying
    it to its own result would decode a second time.

    :param raw_path: The raw request path, as sent by the client
    :return: The path to use to look for a servlet
    :raise ValueError: The path holds a control character or escapes the root
    """
    path = urllib.parse.unquote(raw_path.split("?", 1)[0])
    if _CONTROL_CHARS.search(path):
        raise ValueError("Control character in request path")

    path = _MULTIPLE_SLASHES.sub("/", path)
    trailing_slash = path.endswith("/") and path != "/"

    segments: list[str] = []
    for segment in path.split("/"):
        if not segment or segment == ".":
            continue

        if segment == "..":
            if not segments:
                # Refuse the request instead of silently clamping it to the root
                raise ValueError("Request path escapes the root")
            segments.pop()
        else:
            segments.append(segment)

    normalized = f"/{'/'.join(segments)}"
    if trailing_slash and normalized != "/":
        normalized += "/"

    return normalized


def compute_sub_path(full_path: str, prefix: str) -> str:
    """
    Computes the servlet-relative path of a request, i.e. the part of the path
    which follows the prefix the servlet has been registered on.

    :param full_path: The full request path
    :param prefix: The path to the servlet root
    :return: The path of the request, relative to the servlet root
    """
    sub_path = full_path[len(prefix) :]
    if not sub_path.startswith("/"):
        sub_path = f"/{sub_path}"

    return _MULTIPLE_SLASHES.sub("/", sub_path)


# ------------------------------------------------------------------------------


def split_host_port(value: str) -> tuple[str, str | None]:
    """
    Splits the value of a ``Host`` header into a lower-case host name and a
    port

    :param value: A ``host``, ``host:port``, ``[ipv6]`` or ``[ipv6]:port`` string
    :return: A (host, port) tuple, the port being None if there is none
    """
    value = value.strip().lower()
    if value.startswith("["):
        # IPv6 literal: the host is kept with its brackets
        end = value.find("]")
        if end < 0:
            return value, None

        host, rest = value[: end + 1], value[end + 1 :]
        return host, rest[1:] if rest.startswith(":") else None

    host, sep, port = value.partition(":")
    # A trailing dot makes an absolute name, the same host
    return host.rstrip("."), (port if sep else None)


def normalize_allowed_hosts(value: Any) -> list[tuple[str, str | None]] | None:
    """
    Normalizes the value of a ``pelix.http.allowed_hosts`` configuration

    :param value: None, a (comma-separated) string or an iterable of strings
    :return: A list of (host, port) tuples, or None if the Host header must
             not be checked (nothing configured, or an empty value)
    """
    if value is None:
        return None

    if isinstance(value, str):
        value = value.split(",")

    # Already normalized entries are kept, as the service can be validated again
    items = (raw if isinstance(raw, tuple) else split_host_port(str(raw)) for raw in value)
    return [item for item in items if item[0]] or None


def normalize_trusted_proxies(value: Any) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """
    Normalizes the value of a ``pelix.http.proxy.trusted`` configuration

    :param value: None, a (comma-separated) string or an iterable of addresses or networks
    :return: The trusted networks
    :raise ValueError: An item is neither an address nor a network
    """
    if not value:
        return []

    if isinstance(value, str):
        value = value.split(",")

    return [ipaddress.ip_network(item, strict=False) for item in (str(raw).strip() for raw in value) if item]


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """
    Parses an address, unwrapping the IPv4 ones mapped in IPv6

    :return: The address, or None if it isn't one
    """
    try:
        address = ipaddress.ip_address(value.strip().strip("[]"))
    except ValueError:
        return None
    return getattr(address, "ipv4_mapped", None) or address


MAX_SESSIONS = 10000
""" Number of sessions of a service above which the least recently used ones are dropped """

SESSION_USER = "pelix.http.session.user"
""" Session attribute holding the name of the user who logged in """


class SessionManager:
    """
    The sessions of an HTTP service, in memory. They are indexed by a hash of
    their identifier: the one the browser knows is the only way to use a session.
    """

    def __init__(self, max_inactive_interval: int) -> None:
        self._interval = max_inactive_interval
        self._lock = threading.Lock()
        self._sessions: dict[str, list[Any]] = {}
        self._next_sweep = time.monotonic() + max_inactive_interval

    @staticmethod
    def _key(session_id: str) -> str:
        return hashlib.sha256(session_id.encode()).hexdigest()

    def find(self, session_id: str) -> http.HttpSession | None:
        """
        Looks for a live session, which is then kept alive
        """
        now = time.monotonic()
        with self._lock:
            entry = self._sessions.get(key := self._key(session_id))
            if entry is None:
                return None
            if now - entry[1] > self._interval:
                del self._sessions[key]
                return None
            entry[1] = now

        session: http.HttpSession = entry[0]
        session._new = False
        return session

    def create(self) -> http.HttpSession:
        """
        Starts a session, with an unguessable identifier
        """
        session = http.HttpSession(secrets.token_urlsafe(32), self._interval, self.drop)
        now = time.monotonic()
        with self._lock:
            if now > self._next_sweep:
                # Expired sessions nobody asks for are only found here
                self._next_sweep = now + self._interval
                for key in [k for k, (_, seen) in self._sessions.items() if now - seen > self._interval]:
                    del self._sessions[key]
            if len(self._sessions) >= MAX_SESSIONS:
                # Anyone can start a session on a public servlet: the oldest anonymous
                # ones give way first, so that this can't log users out
                keys = [k for k, (s, _) in self._sessions.items() if SESSION_USER not in s._attributes]
                del self._sessions[min(keys or self._sessions, key=lambda k: self._sessions[k][1])]
            self._sessions[self._key(session._id)] = [session, now]
        return session

    def drop(self, session: http.HttpSession) -> None:
        """
        Forgets a session
        """
        with self._lock:
            self._sessions.pop(self._key(session._id), None)

    def rename(self, session: http.HttpSession) -> str:
        """
        Gives a new identifier to a session: the former one is of no use any more

        :return: The new identifier
        """
        with self._lock:
            entry = self._sessions.pop(self._key(session._id))
            session._id = secrets.token_urlsafe(32)
            self._sessions[self._key(session._id)] = entry
        return session._id


class SessionContext:
    """
    The sessions of one request: the session its cookie designates, and the
    cookie to send back
    """

    def __init__(self, manager: SessionManager, cookie_name: str, cookie_value: str | None, secure: bool):
        self.cookie_value = cookie_value
        self.cookie: str | None = None
        """ The ``Set-Cookie`` header to send, if the cookie changed """
        self._manager = manager
        self._name = cookie_name
        self._secure = secure
        self.sent = False
        """ True once the headers went out: the cookie can't change any more """
        self._session: http.HttpSession | None = None
        self._loaded = False

    def _check_sent(self) -> None:
        if self.sent:
            raise RuntimeError("The headers are sent: the session cookie can't change any more")

    def _send(self, value: str, max_age: int | None = None) -> None:
        self._check_sent()
        self.cookie = http.format_cookie(self._name, value, max_age=max_age, secure=self._secure)

    def get(self, create: bool) -> http.HttpSession | None:
        """
        Returns the session of the request, an unknown or expired one being none.
        An unknown cookie is left as is: a parallel request still carrying the
        cookie of before a login would delete the new one.
        """
        if not self._loaded:
            self._loaded = True
            if self.cookie_value:
                self._session = self._manager.find(self.cookie_value)
        if self._session is None and create:
            self._check_sent()
            self._session = self._manager.create()
            self._send(self._session.get_id())
        return self._session

    def change_id(self) -> str:
        """
        Replaces the identifier of the session

        :raise RuntimeError: No session, or the headers are sent
        """
        self._check_sent()
        if (session := self.get(False)) is None:
            raise RuntimeError("There is no session")
        try:
            new_id = self._manager.rename(session)
        except KeyError as ex:
            raise RuntimeError("The session has been dropped") from ex
        self._send(new_id)
        return new_id

    def restore(self) -> Subject | None:
        """
        Returns the subject who logged in this session, with its current groups and roles.
        A failure is an anonymous request: a public page must not depend on the session.
        """
        try:
            session = self.get(False)
            if session is None or (user := session.get_attribute(SESSION_USER)) is None:
                return None
            return auth.restore(user, session.get_id())
        except Exception:
            # Membership providers may fail, and a logout may invalidate the session meanwhile
            _logger.exception("Can't restore the user of a session")
            return None

    def login(self, username: str, password: str, source: str | None) -> Subject:
        """
        Checks a password and logs the user in a session with a new identifier,
        against session fixation
        """
        self._check_sent()
        subject = auth.login(username, password, source)
        if (session := self.get(False)) is not None:
            try:
                if session.get_attribute(SESSION_USER) not in (None, subject.name):
                    # Another user on the same browser: nothing of the previous one is kept
                    session.invalidate()
                    self._session = None
                else:
                    self.change_id()
            except RuntimeError:
                # Dropped by a concurrent logout or expiration: start over
                self._session = None
        session = cast(http.HttpSession, self.get(True))
        session.set_attribute(SESSION_USER, subject.name)
        return dataclasses.replace(
            subject, attributes={**subject.attributes, ATTRIBUTE_SESSION_ID: session.get_id()}
        )

    def logout(self) -> None:
        """
        Drops the session and the cookie
        """
        if (session := self.get(False)) is not None:
            session.invalidate()
            self._session = None
            self._send("", 0)


@dataclass(frozen=True)
class RequestRouting:
    """
    Result of the routing of an incoming request: the servlet which must handle
    it, if any, and the normalized path it has been routed on.
    """

    path: str
    """ The normalized request path, used both for routing and by the servlet """

    servlet: Any | None
    """ The servlet which must handle the request, or None """

    parameters: dict[str, Any]
    """ The parameters the servlet has been registered with """

    prefix: str
    """ The path the servlet has been registered on """

    servlet_type: http.ServletType
    """ The kind of servlet which must handle the request """

    error: int | None = None
    """ Error code to answer with, when the path itself has been refused """


@dataclass(frozen=True)
class RequestChecks:
    """
    What the HTTP services decide about a request before looking for its servlet
    (see :meth:`AbstractHttpService.check_request`)
    """

    routing: RequestRouting
    """ The result of the routing of the request """

    cors_decision: cors.CorsDecision | None
    """ The CORS decision for the request, if it is a cross-origin one """

    refused: bool
    """ True if the Host or the Origin of the request is refused: answer a 403 """

    remote: tuple[tuple[str, int], bool]
    """ The client address and the security of its connection (see :meth:`AbstractHttpService.resolve_client`) """

    sessions: "SessionContext | None"
    """ The sessions of the request, if they are enabled """


# ------------------------------------------------------------------------------


@Property("_address", http.HTTP_SERVICE_ADDRESS, DEFAULT_BIND_ADDRESS)
@Property("_port", http.HTTP_SERVICE_PORT, 8080)
@Property("_debug_errors", http.HTTP_DEBUG_ERRORS, False)
@Property("_max_body_size", http.HTTP_MAX_BODY_SIZE, 1024 * 1024)
@Property("_socket_timeout", http.HTTP_SOCKET_TIMEOUT, 60.0)
@Property("_case_sensitive_paths", http.HTTP_CASE_SENSITIVE_PATHS, True)
@Property("_cors_enforce", http.HTTP_CORS_ENFORCE, True)
@Property("_allowed_hosts", http.HTTP_ALLOWED_HOSTS, None)
@Property("_proxy_trusted", http.HTTP_PROXY_TRUSTED, None)
@Property("_session_enabled", http.HTTP_SESSION_ENABLED, False)
@Property("_session_interval", http.HTTP_SESSION_MAX_INACTIVE_INTERVAL, 1800)
@Property("_session_cookie", http.HTTP_SESSION_COOKIE_NAME, "PELIXSESSIONID")
@Property("_auth_required", http.HTTP_AUTH_REQUIRED, False)
@Property("_auth_realm", http.HTTP_AUTH_REALM, auth.DEFAULT_REALM)
@Property("_uses_ssl", http.HTTP_USES_SSL, False)
@Property("_cert_file", http.HTTPS_CERT_FILE, None)
@Property("_key_file", http.HTTPS_KEY_FILE, None)
@HiddenProperty("_key_password", http.HTTPS_KEY_PASSWORD, None)
@Property("_extra", HTTP_SERVICE_EXTRA, None)
@Property("_instance_name", constants.IPOPO_INSTANCE_NAME)
@Property("_logger_name", "pelix.http.logger.name", "")
@Property("_logger_level", "pelix.http.logger.level", None)
class AbstractHttpService(http.HTTPService):
    """
    Transport-independent part of the Pelix HTTP service implementations.
    """

    def __init__(self) -> None:
        # Properties
        self._address = DEFAULT_BIND_ADDRESS
        self._loopback_bind = True
        self._port = 8080
        self._debug_errors = False
        self._max_body_size: int | None = 1024 * 1024
        self._socket_timeout: float | None = 60.0
        self._case_sensitive_paths = True
        self._cors_enforce: bool = True
        self._allowed_hosts: Any = None
        self._proxy_trusted: Any = None
        self._session_enabled: Any = False
        self._session_interval: Any = 1800
        self._session_cookie: Any = "PELIXSESSIONID"
        self._session_manager: SessionManager | None = None
        self._auth_required: bool = False
        self._auth_realm: str = auth.DEFAULT_REALM
        self._uses_ssl = False
        self._extra: dict[str, Any] | None = None
        self._instance_name: str | None = None
        self._logger_name: str | None = None
        self._logger_level: str | int | None = None

        # SSL Parameters
        self._cert_file: str | None = None
        self._key_file: str | None = None
        self._key_password: str | None = None

        # Validation flag
        self._validated = False

        # Logger (placeholder until _setup_logger is called)
        self._logger: logging.Logger = logging.getLogger(__name__)

        # Servlets registry lock
        self._lock = threading.RLock()

        # Path -> (servlet, parameters, type)
        self._servlets: dict[str, ServletEntry] = {}

        # Injected by iPOPO in the subclasses
        self._error_handler: http.ErrorHandler | None = None
        self._cors_handler: http.CorsHandler | None = None
        self._http_authenticators: list[http.HttpAuthenticator] | None = None

        # Configuration issues already reported, to avoid flooding the logs
        self._auth_warnings: set[str] = set()

        # Servlet -> ServiceReference
        self._servlets_refs: dict[AnyServlet, ServiceReference[Any]] = {}
        self._binding_lock = threading.RLock()

    def __str__(self) -> str:
        """
        String representation of the instance
        """
        return f"BasicHttpService({self._address}, {self._port})"

    # --------------------------------------------------------------------------
    # Logging utilities
    # --------------------------------------------------------------------------

    def log(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        """
        Logs the given message

        :param level: Log entry level
        :param message: Log message (Python logging format)
        """
        if self._logger is not None:
            # Log the message
            self._logger.log(level, message, *args, **kwargs)

    def log_exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """
        Logs an exception

        :param message: Log message (Python logging format)
        """
        if self._logger is not None:
            # Log the exception
            self._logger.exception(message, *args, **kwargs)

    # --------------------------------------------------------------------------
    # Configuration
    # --------------------------------------------------------------------------

    def _normalize_configuration(self) -> None:
        """
        Normalizes the values of the properties given to the component: binding
        address, port and extra properties.
        """
        # Check if we'll use an SSL connection
        self._uses_ssl = self._cert_file is not None

        if not self._address:
            # No address given, use the localhost address
            self._address = LOCALHOST_ADDRESS

        if self._port is None:
            # Random port
            self._port = 0
        else:
            # Ensure we have an integer
            self._port = int(self._port)
            # Ensure the port is positive (or set it to 0 for a random port)
            self._port = max(self._port, 0)

        address = _parse_ip(self._address)
        self._loopback_bind = self._address.lower() == "localhost" or (
            address is not None and address.is_loopback
        )

        # Normalize the extra properties
        if not isinstance(self._extra, dict):
            self._extra = {}

        # Normalize the sessions: each start of the service forgets the previous ones
        try:
            interval = int(self._session_interval)
        except (TypeError, ValueError):
            interval = 0
        self._session_manager = (
            SessionManager(interval if interval > 0 else 1800) if _to_bool(self._session_enabled) else None
        )
        self._session_cookie = str(self._session_cookie)
        try:
            http.format_cookie(self._session_cookie, "")
        except ValueError:
            self.log(
                logging.WARNING, "Invalid session cookie name %r: using the default one", self._session_cookie
            )
            self._session_cookie = "PELIXSESSIONID"

        self._normalize_live_configuration()
        if self._allowed_hosts is None and not self._loopback_bind:
            self.log(
                logging.WARNING,
                "The HTTP service is bound to %s without pelix.http.allowed_hosts: it is open to DNS "
                "rebinding. See https://ipopo.readthedocs.io/en/latest/refcards/http.html",
                self._address,
            )

    def _normalize_live_configuration(self) -> None:
        """
        Normalizes the properties applied to each request: limits, header checks
        and authentication. They can change while the server runs.
        """
        # Normalize the resource limits: a non-positive value removes the limit
        self._max_body_size = normalize_max_body_size(self._max_body_size)

        # None: already normalized as "no timeout" by a previous validation
        if self._socket_timeout is not None:
            try:
                self._socket_timeout = float(self._socket_timeout)
            except (TypeError, ValueError):
                # Fail closed: an invalid value must not remove the timeout
                self.log(logging.WARNING, "Invalid socket timeout %r: using 60 seconds", self._socket_timeout)
                self._socket_timeout = 60.0
            else:
                if self._socket_timeout <= 0:
                    self._socket_timeout = None

        # Normalize the origin and host checks
        self._cors_enforce = _to_bool(self._cors_enforce)
        if self._allowed_hosts is None and self._loopback_bind:
            # Only a local client can reach a loopback address: another name is DNS rebinding
            self._allowed_hosts = LOOPBACK_HOST_NAMES
        self._allowed_hosts = normalize_allowed_hosts(self._allowed_hosts)
        self._proxy_trusted = normalize_trusted_proxies(self._proxy_trusted)

        # Normalize the authentication configuration
        self._auth_required = _to_bool(self._auth_required)
        self._auth_realm = str(self._auth_realm or auth.DEFAULT_REALM)
        self._auth_warnings.clear()

    @Modified
    def _modified(self, properties: dict[str, Any], old_properties: dict[str, Any]) -> None:
        """
        Applies an update of the properties (e.g. by ConfigurationAdmin) to the
        running server, except those only read when it starts
        """
        restart = []
        for name in properties.keys() & _RESTART_FIELDS.keys():
            # Still served with the previous value: the component must not tell otherwise
            setattr(self, _RESTART_FIELDS[name], old_properties.get(name))
            # A configuration from the shell gives "8080" for 8080
            if str(properties[name]) != str(old_properties.get(name)):
                restart.append(name)
        if restart:
            self.log(
                logging.WARNING,
                "%s: only applied when the HTTP service starts again (ipopo.update.policy=restart)",
                ", ".join(sorted(restart)),
            )

        self._normalize_live_configuration()

    def get_max_body_size(self) -> int | None:
        """
        Returns the maximum accepted size of the body of a request, in bytes,
        or None if there is no limit

        :return: A size in bytes or None
        """
        return self._max_body_size

    def resolve_max_body_size(self, parameters: dict[str, Any]) -> int | None:
        """
        Returns the maximum accepted size of the body of a request handled by
        the servlet registered with the given parameters.

        A servlet can override the configuration of the HTTP service, to accept
        bigger bodies than the other servlets, or smaller ones.

        :param parameters: The parameters a servlet has been registered with
        :return: A size in bytes or None
        """
        try:
            return normalize_max_body_size(parameters[http.HTTP_MAX_BODY_SIZE])
        except KeyError:
            # The servlet doesn't override the configuration of the service
            return self._max_body_size

    def resolve_cors(
        self,
        routing: "RequestRouting",
        method: str,
        origin: str | None,
        request_method: str | None = None,
        request_headers: str | None = None,
    ) -> cors.CorsDecision | None:
        """
        Decides how to handle a cross-origin request.

        A servlet declaring its own CORS policy in its service properties
        overrides the CORS handler service bound to the HTTP service.

        :param routing: The result of the routing of the request
        :param method: The HTTP method of the request
        :param origin: The value of the ``Origin`` request header, if any
        :param request_method: Value of the ``Access-Control-Request-Method`` header
        :param request_headers: Value of the ``Access-Control-Request-Headers`` header
        :return: None if CORS doesn't apply to this request, else the decision
        """
        if not origin:
            # Fast path: not a cross-origin request
            return None

        policy = cors.policy_from_parameters(routing.parameters) or self._cors_handler
        try:
            return cors.resolve_cors(policy, routing.path, method, origin, request_method, request_headers)
        except Exception as ex:  # noqa: BLE001
            # Refuse the request rather than letting a faulty policy allow it
            self.log_exception("Error computing the CORS policy of %s: %s", routing.path, ex)
            return cors.CorsDecision(bool(request_method) and method.upper() == "OPTIONS", None)

    def check_request(self, method: str, raw_path: str, headers: Any, peer: tuple[str, int]) -> RequestChecks:
        """
        Routes a request and checks its ``Host`` and ``Origin`` headers, before
        any servlet is looked for

        :param method: The HTTP method of the request
        :param raw_path: The path of the request, as received
        :param headers: The headers of the request
        :param peer: The (host, port) of the other end of the connection
        :return: What is known of the request before calling its servlet
        """
        remote = self.resolve_client(peer, headers)
        sessions = self.open_sessions(headers, remote[1])
        host, origin = headers.get("Host"), headers.get("Origin")
        routing = self.resolve_request(raw_path)
        decision = self.resolve_cors(
            routing,
            method,
            origin,
            headers.get("Access-Control-Request-Method"),
            headers.get("Access-Control-Request-Headers"),
        )
        refused = self.is_host_refused(host) or self.is_origin_refused(origin, host, decision, remote[1])
        return RequestChecks(routing, decision, refused, remote, sessions)

    def is_host_refused(self, host: str | None) -> bool:
        """
        Checks the ``Host`` header of a request against the
        ``pelix.http.allowed_hosts`` configuration

        :param host: The value of the ``Host`` header, if any
        :return: True if the request must be refused
        """
        allowed = self._allowed_hosts
        if allowed is None:
            # Not configured: nothing is checked
            return False

        if not host:
            # A browser always sends it: it can only come from a script
            return True

        name, port = split_host_port(host)
        return not any(name == a_name and (a_port is None or a_port == port) for a_name, a_port in allowed)

    def resolve_client(self, peer: tuple[str, int], headers: Any) -> tuple[tuple[str, int], bool]:
        """
        Finds the client of a request when it comes through a trusted reverse
        proxy (``pelix.http.proxy.trusted``): the first address of the
        ``X-Forwarded-For`` chain, from the right, which isn't a trusted proxy.
        Headers from any other peer are ignored, anyone can forge them.

        :param peer: The (host, port) of the other end of the connection
        :param headers: The headers of the request (``get_all`` or ``getall`` is needed)
        :return: The (host, port) of the client (port 0 if it comes from a header),
                 and True if it used HTTPS
        """
        secure = self._uses_ssl
        trusted = self._proxy_trusted or ()
        address = _parse_ip(peer[0])
        if address is None:
            return peer[:2], secure
        # The throttle must see one key per host, whatever the way the address is written
        peer = (str(address), peer[1])
        if not any(address in network for network in trusted):
            return peer, secure

        getall = getattr(headers, "getall", None) or headers.get_all
        protocols = [p.strip().lower() for v in getall("X-Forwarded-Proto", []) for p in v.split(",")]
        if protocols and all(p in ("http", "https") for p in protocols):
            # Like Tomcat: a single hop in clear text makes the request insecure
            secure = all(p == "https" for p in protocols)

        hops = [h for v in getall("X-Forwarded-For", []) for h in v.split(",")]
        for hop in reversed(hops):
            hop_address = _parse_ip(hop)
            if hop_address is None:
                # Garbage in the chain: the proxy can't be trusted to have checked it
                break
            if not any(hop_address in network for network in trusted):
                return (str(hop_address), 0), secure

        return peer[:2], secure

    def open_sessions(self, headers: http.HeadersView, secure: bool) -> SessionContext | None:
        """
        Prepares the sessions of a request

        :param headers: The headers of the request
        :param secure: True if the client used HTTPS (see :meth:`resolve_client`)
        :return: None if the sessions are not enabled
        """
        if self._session_manager is None:
            return None

        cookie = http.parse_cookies(headers.get("Cookie")).get(self._session_cookie)
        return SessionContext(self._session_manager, self._session_cookie, cookie, secure)

    def is_origin_refused(
        self,
        origin: str | None,
        host: str | None,
        decision: cors.CorsDecision | None,
        secure: bool,
    ) -> bool:
        """
        Checks the ``Origin`` header of a request when ``pelix.http.cors.enforce``
        is set. Preflight requests are not concerned.

        :param origin: The value of the ``Origin`` header, if any
        :param host: The value of the ``Host`` header, if any
        :param decision: The result of :meth:`resolve_cors` for this request
        :param secure: True if the client used HTTPS (see :meth:`resolve_client`)
        :return: True if the request must be refused
        """
        if not self._cors_enforce or not origin:
            return False

        if decision is not None and (decision.preflight or decision.allowed):
            return False

        scheme = "https" if secure else "http"
        # A page served by this server is accepted: browsers send Origin on same-origin POST too
        return not host or origin.strip().lower() != f"{scheme}://{host.strip().lower()}"

    def is_auth_required(self, routing: "RequestRouting") -> bool:
        """
        Checks if a request must carry valid credentials

        :param routing: The result of the routing of the request
        :return: True if the request must be authenticated
        """
        try:
            return _to_bool(routing.parameters[http.HTTP_AUTH_REQUIRED])
        except KeyError:
            # The servlet doesn't override the configuration of the service
            return self._auth_required

    def get_auth_realm(self, routing: "RequestRouting") -> str:
        """
        Returns the protection space of the resource targeted by a request

        :param routing: The result of the routing of the request
        :return: The realm to give in the authentication challenges
        """
        return str(routing.parameters.get(http.HTTP_AUTH_REALM) or self._auth_realm or auth.DEFAULT_REALM)

    def _warn_once(self, key: str, message: str, *args: Any) -> None:
        """
        Logs a configuration warning, once per validation of the service

        :param key: Identifier of the warning
        :param message: Log message (Python logging format)
        """
        if key not in self._auth_warnings:
            self._auth_warnings.add(key)
            self.log(logging.WARNING, message, *args)

    def needs_authentication(self, routing: "RequestRouting") -> bool:
        """
        Checks if the authentication of a request has something to do, i.e. if
        :meth:`resolve_authentication` may have to check credentials

        :param routing: The result of the routing of the request
        :return: True if an HTTP authenticator is bound
        """
        return bool(self._http_authenticators)

    def resolve_authentication(
        self,
        routing: "RequestRouting",
        headers: http.HeadersView,
        source: str | None = None,
        sessions: SessionContext | None = None,
        peer: str | None = None,
    ) -> auth.AuthDecision:
        """
        Authenticates a request. This can take time, as checking a password is
        costly by design.

        :param routing: The result of the routing of the request
        :param headers: The headers of the request
        :param source: The address of the client, for the brute-force throttle
        :param sessions: The sessions of the request: a user logged in one takes
                         precedence over the credentials of the headers
        :param peer: The address of the other end of the connection
        :return: The decision: the subject to handle the request as, or a refusal,
                 the subject holding the given addresses
        """
        decision = self.__resolve_authentication(routing, headers, source, sessions)
        if source is None and peer is None:
            return decision

        # A copy of a frozen bean: cheap enough to keep the anonymous subject shared otherwise
        subject = dataclasses.replace(decision.subject, peer_address=peer, client_address=source)
        return dataclasses.replace(decision, subject=subject)

    def __resolve_authentication(
        self,
        routing: "RequestRouting",
        headers: http.HeadersView,
        source: str | None,
        sessions: SessionContext | None,
    ) -> auth.AuthDecision:
        """
        Authenticates a request (see :meth:`resolve_authentication`)
        """
        if sessions is not None and (subject := sessions.restore()) is not None:
            return auth.AuthDecision(subject)

        authenticators = list(self._http_authenticators or ())
        required = self.is_auth_required(routing)
        if not authenticators:
            if required:
                # Fail closed: a protected resource must not become public
                # because its authenticator is gone
                self._warn_once(
                    "no-authenticator",
                    "Authentication is required on %s, but no HTTP authenticator service is bound: "
                    "refusing the requests",
                    routing.path,
                )
            return auth.AuthDecision(ANONYMOUS, required)

        decision = auth.authenticate_request(authenticators, headers, required, source)
        if decision.subject.authenticated and not self._uses_ssl:
            self._warn_once(
                "clear-text",
                "Credentials are received over plain HTTP: they can be read by anyone on the network",
            )
        return decision

    def get_auth_challenge(self, routing: "RequestRouting") -> str | None:
        """
        Returns the value of the ``WWW-Authenticate`` header of a 401 response

        :param routing: The result of the routing of the request
        :return: The challenges of the bound authenticators, or None
        """
        return auth.make_challenges(self._http_authenticators or (), self.get_auth_realm(routing))

    def make_auth_error_page(self, code: int) -> str:
        """
        Prepares the page of a 401 or 403 error.

        It doesn't say why the request was refused: that would tell an attacker
        which user names exist or which permissions are checked.

        :param code: The HTTP error code (401 or 403)
        :return: A HTML page
        """
        title = "Unauthorized" if code == 401 else "Forbidden"
        return f"""<html>
<head>
<title>{code} - {title}</title>
</head>
<body>
<h1>{title}</h1>
</body>
</html>"""

    def get_socket_timeout(self) -> float | None:
        """
        Returns the timeout of the sockets handling the requests, in seconds,
        or None if there is no timeout

        :return: A timeout in seconds or None
        """
        return self._socket_timeout

    def _setup_logger(self) -> logging.Logger:
        """
        Prepares the logger of the component, according to its properties

        :return: The logger to use
        """
        if not self._logger_name:
            # Empty name, use the instance name
            self._logger_name = self._instance_name

        logger = logging.getLogger(self._logger_name)

        level: int | None = None
        if isinstance(self._logger_level, int):
            level = self._logger_level
        elif self._logger_level is not None:
            level = utilities.get_log_level(self._logger_level)
            if level is None:
                try:
                    level = int(self._logger_level)
                except ValueError:
                    # Invalid level
                    level = None

        logger.level = level if level is not None else logging.INFO
        self._logger = logger
        return logger

    # --------------------------------------------------------------------------
    # Server description
    # --------------------------------------------------------------------------

    def get_hostname(self) -> str:
        """
        Retrieves the server host name

        :return: The server host name
        """
        return socket.gethostname()

    def is_https(self) -> bool:
        """
        Returns True if this is an HTTPS server

        :return: True if this server uses SSL
        """
        return self._uses_ssl

    # --------------------------------------------------------------------------
    # Servlets registry
    # --------------------------------------------------------------------------

    def get_registered_paths(self) -> list[str]:
        """
        Returns the paths registered by servlets

        :return: The paths registered by servlets (sorted list)
        """
        return sorted(self._servlets)

    def _servlet_key(self, path: str) -> str:
        """
        Computes the key a path is stored under in the servlets registry.

        :param path: A servlet or request path
        :return: The path itself, unless the folding of paths has been re-enabled
        """
        return path if self._case_sensitive_paths else path.lower()

    def get_servlet(self, path: str | None) -> tuple[Any, dict[str, Any], str, http.ServletType] | None:
        """
        Retrieves the servlet matching the given path and its parameters.
        Returns None if no servlet matches the given path.

        :param path: A request URI
        :return: A tuple (servlet, parameters, prefix, type) or None
        """
        if not path or path[0] != "/":
            # No path, nothing to return
            return None

        path = self._servlet_key(path)

        if path[-1] != "/":
            # Add a trailing slash
            path += "/"

        with self._lock:
            longest_match = ""
            longest_match_len = 0
            for servlet_path in self._servlets:
                tested_path = servlet_path
                if tested_path[-1] != "/":
                    # Add a trailing slash
                    tested_path += "/"

                if path.startswith(tested_path) and len(servlet_path) > longest_match_len:
                    # Found a corresponding servlet
                    # which is deeper than the previous one
                    longest_match = servlet_path
                    longest_match_len = len(servlet_path)

            # Return the found servlet
            if not longest_match:
                # No match found
                return None

            # Retrieve the stored information
            servlet, params, servlet_type = self._servlets[longest_match]
            return servlet, params, longest_match, servlet_type

    def resolve_request(self, raw_path: str) -> "RequestRouting":
        """
        Finds the servlet which must handle the request on the given raw path.

        :param raw_path: The raw request path, as given by the client
        :return: The result of the routing (never None). Its ``servlet`` is
                 None if no servlet matches the path, and its ``error`` is set
                 if the path itself has been refused.
        """
        try:
            normalized_path = normalize_request_path(raw_path)
        except ValueError as ex:
            # Malformed path: it is answered before any servlet is looked for
            self.log(logging.WARNING, "Refused request path %r: %s", raw_path, ex)
            return RequestRouting(raw_path, None, {}, "", http.ServletType.SYNC, error=400)

        found_servlet = self.get_servlet(normalized_path)
        if found_servlet is None:
            return RequestRouting(normalized_path, None, {}, "", http.ServletType.SYNC)

        servlet, params, prefix, servlet_type = found_servlet
        return RequestRouting(normalized_path, servlet, params, prefix, servlet_type)

    def _check_servlet_type(self, servlet_type: http.ServletType) -> None:
        """
        Checks if the given kind of servlet is supported by this implementation.
        Does nothing if it is supported.

        :param servlet_type: The type of servlet to register
        :raise ValueError: The kind of servlet is not supported
        """
        # Everything is supported by default

    def register_servlet(
        self,
        path: str,
        servlet: Any,
        parameters: dict[str, Any] | None = None,
        servlet_type: http.ServletType = http.ServletType.SYNC,
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
        self._check_servlet_type(servlet_type)

        if servlet is None:
            raise ValueError("Invalid servlet instance")

        if not path or path[0] != "/":
            raise ValueError(f"Invalid path given to register the servlet: {path}")

        path = self._servlet_key(path)

        # Prepare the parameters
        if parameters is None:
            parameters = {}

        with self._lock:
            if path in self._servlets:
                # Already registered path
                if self._servlets[path][0] is servlet:
                    # Double-registration: Nothing to do
                    return True
                else:
                    # Path is already taken by another servlet
                    already_taken = True
            else:
                # Path is available
                already_taken = False

            # Add server information in parameters
            parameters[http.PARAM_ADDRESS] = self._address
            parameters[http.PARAM_PORT] = self._port
            parameters[http.PARAM_HTTPS] = self._uses_ssl
            parameters[http.PARAM_NAME] = self._instance_name
            parameters[http.PARAM_EXTRA] = self._extra.copy() if self._extra else None
            self._set_extra_parameters(parameters, servlet_type)

            # The servlet might refuse to be bound to this server
            if not self._safe_callback(servlet, "accept_binding", path, parameters):
                # Server refused: stop right there
                # => No need to raise the "already taken path" exception
                return False

            if already_taken:
                # The path is already taken by another servlet
                raise ValueError(f"A servlet is already registered on {path}")

            # Tell the servlet it can be bound to the path
            if self._safe_callback(servlet, "bound_to", path, parameters):
                # Store the servlet
                self._servlets[path] = (servlet, parameters, servlet_type)
                return True

            # The servlet refused the binding
            return False

    def _set_extra_parameters(self, parameters: dict[str, Any], servlet_type: http.ServletType) -> None:
        """
        Adds the implementation-specific entries to the parameters given to a
        servlet when it is bound.

        :param parameters: The parameters given to the servlet
        :param servlet_type: The type of the servlet being registered
        """
        # Nothing to add by default

    def unregister(self, path: str | None, servlet: http.Servlet | None = None) -> bool:
        """
        Unregisters the servlet for the given path

        :param path: The path to a servlet
        :param servlet: If given, unregisters all the paths handled by this servlet
        :return: True if at least one path as been unregistered, else False
        """
        if servlet is not None:
            with self._lock:
                # Unregister all paths for this servlet
                paths = [
                    servlet_path
                    for (servlet_path, servlet_info) in self._servlets.items()
                    if servlet_info[0] == servlet
                ]

            result = False
            for servlet_path in paths:
                result |= self.unregister(servlet_path)

            return result
        else:
            if not path:
                # Invalid path
                return False

            path = self._servlet_key(path)

            with self._lock:
                # Notify the servlet
                servlet_info = self._servlets.get(path)
                if servlet_info is None:
                    # Unknown path
                    return False

                self._safe_callback(servlet_info[0], "unbound_from", path, servlet_info[1])

                # Remove the servlet
                try:
                    del self._servlets[path]
                except KeyError:
                    self.log(logging.DEBUG, "Tried to remove an unknown servlet path: %s", path)
                return True

    # --------------------------------------------------------------------------
    # Error pages
    # --------------------------------------------------------------------------

    def make_not_found_page(self, path: str) -> str:
        """
        Prepares a "page not found" page for a 404 error

        The registered servlet paths are only listed if the
        :const:`pelix.http.HTTP_DEBUG_ERRORS` property is set: they describe
        the server to any client.

        :param path: Request path
        :return: A HTML page
        """
        page = None
        if self._error_handler is not None:
            page = self._error_handler.make_not_found_page(path)

        if not page:
            registered = ""
            if self._debug_errors:
                registered = f"""<h2>Registered paths:</h2>
{http.make_html_list(self.get_registered_paths())}
"""

            page = f"""<html>
<head>
<title>404 - Page not found</title>
</head>
<body>
<h1>Page not found</h1>
<p>No servlet is associated to this path:</p>
<code>{html.escape(path)}</code>
{registered}</body>
</html>"""
        return page

    def make_exception_page(self, path: str, stack: str) -> str:
        """
        Prepares a page describing an error in a 500 error page.

        The stack trace is only sent to the client if the
        :const:`pelix.http.HTTP_DEBUG_ERRORS` property is set: it gives details
        about the server and about the data it handles. It is always logged,
        along with the error ID shown in the page.

        :param path: Request path
        :param stack: Exception stack trace
        :return: A HTML page
        """
        # Log the details of the error, they are not sent to the client
        error_id = uuid.uuid4().hex
        (self._logger or logging.getLogger(__name__)).error(
            "Error %s handling request upon: %s\n%s", error_id, path, stack
        )

        # Only tell the client how to find the error in the logs
        details = stack if self._debug_errors else f"Error ID: {error_id}"

        page = None
        if self._error_handler is not None:
            page = self._error_handler.make_exception_page(path, details)

        if not page:
            page = f"""<html>
<head>
<title>500 - Internal Server Error</title>
</head>
<body>
<h1>Internal Server Error</h1>
<p>Error handling request upon: <code>{html.escape(path)}</code></p>
<pre>
{html.escape(details)}
</pre>
</body>
</html>"""
        return page

    # --------------------------------------------------------------------------
    # iPOPO bindings
    # --------------------------------------------------------------------------

    def _safe_callback(self, instance: Any, method: str, *args: Any, **kwargs: Any) -> Any:
        """
        Safely calls the given method in the given instance.
        Returns True on method absence.
        Returns False on error.
        Returns the method result if found.

        :param instance: The instance to call
        :param method: The method to call in the instance
        :return: The method result or True on method absence or False on error
        """
        # Call back the method
        if instance is None:
            # Consider invalidity as a failure
            return False

        try:
            callback = getattr(instance, method)
        except AttributeError:
            # Consider absence as a success
            return True

        try:
            result = callback(*args, **kwargs)
            if result is None:
                # Special case: consider None as success
                return True

            return result
        except Exception as ex:  # noqa: BLE001
            self.log_exception("Error calling back an instance: %s", ex)

        return False

    def _get_servlet_parameters(self, service_reference: ServiceReference[Any]) -> dict[str, Any]:
        """
        Returns the registration parameters taken from the properties of a
        servlet service.

        A new dictionary is returned on each call: ``register_servlet()`` keeps
        the one it is given and completes it with the description of the
        server, so it can't be shared by two registrations.

        :param service_reference: The reference of a servlet service
        :return: The parameters to register the servlet with
        """
        parameters = {}
        for name in SERVLET_PARAMETERS:
            value = service_reference.get_property(name)
            if value is not None:
                parameters[name] = value

        return parameters

    def _register_servlet_service(
        self, service: AnyServlet, service_reference: ServiceReference[Any]
    ) -> None:
        """
        Registers a servlet according to its service properties.
        Implemented by the subclasses, as they do not support the same kinds of
        servlet.

        :param service: A servlet service
        :param service_reference: The associated ServiceReference
        """
        raise NotImplementedError

    def _on_bind(self, service: AnyServlet, service_reference: ServiceReference[Any]) -> None:
        """
        A servlet service has been bound

        :param service: A servlet service
        :param service_reference: The associated ServiceReference
        """
        # Ignore imported services
        if self._is_imported(service_reference):
            self.log(logging.DEBUG, "Ignoring service as it is imported: %s", service_reference)
            return

        with self._binding_lock:
            self._servlets_refs[service] = service_reference

            if self._validated:
                # We've been validated, register the service
                self._register_servlet_service(service, service_reference)

    def _on_update(
        self,
        service: AnyServlet,
        service_reference: ServiceReference[Any],
        old_properties: dict[str, Any],
        watched_properties: tuple[str, ...],
    ) -> None:
        """
        The properties of a servlet service have been updated

        :param service: A servlet service
        :param service_reference: The associated ServiceReference
        :param old_properties: The previous properties of the service
        :param watched_properties: Names of the properties which, when modified,
                                   require the servlet to be registered again
        """
        # Ignore imported services
        if self._is_imported(service_reference):
            return

        # Check if the update concerns the registration
        if all(
            old_properties.get(name) == service_reference.get_property(name) for name in watched_properties
        ):
            # Nothing to do
            return

        with self._binding_lock:
            # Unregister the previous paths
            self.unregister(None, cast(http.Servlet, service))

            if self._validated:
                # Register the service with its new properties
                self._register_servlet_service(service, service_reference)

    def _on_unbind(self, service: AnyServlet, service_reference: ServiceReference[Any]) -> None:
        """
        A servlet service is gone

        :param service: A servlet service
        :param service_reference: The associated ServiceReference
        """
        # Ignore imported services
        if self._is_imported(service_reference):
            return

        with self._binding_lock:
            # Servlet gone: unregister all paths associated to this servlet
            self.unregister(None, cast(http.Servlet, service))

            # Remove the service reference
            try:
                del self._servlets_refs[service]
            except KeyError:
                self.log(logging.DEBUG, "Tried to remove an unknown servlet: %s", service)

    def _register_bound_servlets(self) -> None:
        """
        Registers the servlets which have been bound before the component was
        validated. Must be called once the server is ready.
        """
        with self._binding_lock:
            # Set the validation flag up, once the server is ready
            self._validated = True

            # Register bound servlets
            for service, svc_ref in self._servlets_refs.items():
                self._register_servlet_service(service, svc_ref)

    def _unregister_all_servlets(self) -> None:
        """
        Refuses new registrations and unregisters all the bound servlets, to
        notify them with ``unbound_from``.
        """
        with self._binding_lock:
            # Refuse new registrations
            self._validated = False

            # Unregister servlets (to call unbound_from...)
            for service in self._servlets_refs:
                self.unregister(None, cast(http.Servlet, service))

    @staticmethod
    def _is_imported(service_reference: ServiceReference[Any]) -> bool:
        """
        Tests if the given service has been imported by Remote Services

        :param service_reference: The reference of the service to check
        :return: True if the service is flagged as imported
        """
        return cast(bool, service_reference.get_property(pelix.remote.PROP_IMPORTED))
