#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: authentication and authorization shared by the transports
and the discoveries.

Server side, a transport runs each call under the subject of the caller (the HTTP
service does it for the HTTP based transports) and the exporters call
:func:`check_call` and :func:`get_remote_method` before calling the service.
Client side, the importers ask :func:`get_auth_headers` for the credentials of a peer,
given by the :class:`RemoteCredentialsProvider` services. The discoveries sign and check
their announcements with a :class:`DiscoverySigner`.

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

import base64
import collections
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import threading
import time
import tomllib
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlsplit

import pelix.utilities
from pelix.constants import PELIX_SPECIFICATION_FIELD, SERVICE_RANKING, BundleException, Specification
from pelix.ipopo.decorators import ComponentFactory, Property, Provides, Validate
from pelix.ldapfilter import get_ldap_filter
from pelix.security import (
    AccessDenied,
    AuthenticationRequired,
    Credentials,
    Permission,
    UsernamePassword,
    get_current_subject,
    use_authorization,
)
from pelix.security.htpasswd import _warn_about_file_mode

if TYPE_CHECKING:
    from collections.abc import Callable

    from pelix.framework import BundleContext

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "DEFAULT_IMPORT_MAX_RANKING",
    "FACTORY_CREDENTIALS_FILE",
    "PERMISSION_CALL",
    "PERMISSION_ENDPOINTS_PUBLISH",
    "PERMISSION_ENDPOINTS_READ",
    "PROP_AUTH_REQUIRED",
    "PROP_CREDENTIALS_FILE",
    "PROP_DISCOVERY_KEY_FILE",
    "PROP_IMPORT_FILTER",
    "PROP_IMPORT_MAX_RANKING",
    "PROP_PERMISSION",
    "SERVICE_CREDENTIALS_PROVIDER",
    "CredentialsFile",
    "DiscoverySigner",
    "RemoteCredentialsProvider",
    "accept_import",
    "cap_ranking",
    "check_call",
    "check_permission",
    "get_auth_headers",
    "get_remote_method",
    "is_loopback_host",
]

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

PROP_PERMISSION = "pelix.remote.permission"
"""
Export property: the permission a caller needs to call the exported service, as
``action`` or ``action:resource``. ``"*"`` allows every caller, anonymous included.

Without it, the service can be called by anybody when the transport is only reachable
from the local host, and needs :data:`PERMISSION_CALL` scoped to the endpoint name
otherwise.
"""

PERMISSION_CALL = "pelix.remote.call"
"""
Permission to call an exported service, scoped to its endpoint name
(``pelix.remote.call:<endpoint name>``). A grant without resource covers every export
"""

PERMISSION_ENDPOINTS_READ = "pelix.remote.endpoints.read"
""" Permission to read the endpoints exported by the dispatcher servlet """

PERMISSION_ENDPOINTS_PUBLISH = "pelix.remote.endpoints.publish"
""" Permission to send endpoints to the dispatcher servlet """

PROP_AUTH_REQUIRED = "pelix.remote.auth.required"
"""
Exporter property: if True, the requests to the transport must carry valid credentials,
else they are answered with a 401 error. Not set: the setting of the HTTP service applies
"""

PROP_IMPORT_FILTER = "pelix.remote.import.filter"
"""
Framework property: LDAP filter the properties of an endpoint must match to be imported
"""

PROP_IMPORT_MAX_RANKING = "pelix.remote.import.max_ranking"
""" Framework property: highest ``service.ranking`` an imported service can have """

DEFAULT_IMPORT_MAX_RANKING = -1
""" Below the default ranking, so that a local service always wins over an imported one """

PROP_CREDENTIALS_FILE = "pelix.remote.credentials.file"
""" Path to the TOML file of the credentials sent to the peers (see :class:`CredentialsFile`) """

FACTORY_CREDENTIALS_FILE = "pelix.remote.credentials.file.factory"
""" Name of the component factory of :class:`CredentialsFile` """

PROP_DISCOVERY_KEY_FILE = "pelix.remote.discovery.key.file"
"""
Discovery property: path to the file holding the key shared by the frameworks of a
discovery group. When set, announcements are signed and unsigned ones are ignored
"""

SERVICE_CREDENTIALS_PROVIDER = "pelix.remote.credentials.provider"
""" Specification of the services giving the credentials to send to a peer """

# Key of the signature in a signed announcement
_SIGNATURE_KEY = "pelix.remote.signature"

# Shortest key accepted: a group key is a secret, not a password to remember
_MIN_KEY_SIZE = 16

# Log a missing authorization service once, not once per call
_warned_no_authorization = False

# Peers already warned about, to avoid flooding the log on each call
_warned_peers: set[str] = set()

# ------------------------------------------------------------------------------


@Specification(SERVICE_CREDENTIALS_PROVIDER)
class RemoteCredentialsProvider(Protocol):
    """
    Gives the credentials an importer sends to a peer.

    Providers are asked in ranking order; the first one which doesn't abstain wins.
    """

    def get_credentials(self, transport: str, url: str, endpoint: Mapping[str, Any]) -> Credentials | None:
        """
        Returns the credentials to send to the given peer

        :param transport: Name of the transport: "remote.jsonrpc", "remote.dispatcher", ...
        :param url: URL the request will be sent to
        :param endpoint: Properties of the endpoint, if any (empty for discovery requests)
        :return: The credentials, or None to abstain
        """
        ...


# ------------------------------------------------------------------------------


def is_loopback_host(host: str | None) -> bool:
    """
    Tells whether a host name or address can only be reached from the local host

    :param host: A host name or an IPv4/IPv6 address, with optional brackets and scope
    :return: True for "localhost" and the loopback addresses
    """
    if not host:
        return False

    host = host.strip("[]").split("%", 1)[0].lower()
    if host == "localhost":
        return True

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Any other name can resolve to anything
        return False

    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback


def check_permission(context: "BundleContext", permission: Permission) -> None:
    """
    Checks that the current subject holds a permission.

    :param context: A bundle context, to reach the authorization service
    :param permission: The required permission
    :raise AuthenticationRequired: Refused, and the subject is not authenticated
    :raise AccessDenied: Refused, and the subject is authenticated
    """
    subject = get_current_subject()
    try:
        with use_authorization(context) as authorization:
            authorization.check_permitted(permission, subject)
            return
    except BundleException:
        # Fail closed: a remote call must not be allowed because the policy is gone
        global _warned_no_authorization
        if not _warned_no_authorization:
            _warned_no_authorization = True
            _logger.warning(
                "No authorization service: denying the remote calls which need a permission. "
                "Is the pelix.security.core bundle started?"
            )
    except AccessDenied:
        pass

    if not subject.authenticated:
        raise AuthenticationRequired(f"Not permitted: {permission}")
    raise AccessDenied(f"Not permitted: {permission}")


def check_call(
    context: "BundleContext", properties: Mapping[str, Any], resource: str, local_only: bool
) -> None:
    """
    Checks that the current subject can call an exported service.

    :param context: The bundle context of the exporter
    :param properties: The properties of the exported service
    :param resource: Resource of the default permission: the endpoint name
    :param local_only: True if the transport can only be reached from the local host
    :raise AuthenticationRequired: Refused, and the subject is not authenticated
    :raise AccessDenied: Refused, and the subject is authenticated
    """
    declared = properties.get(PROP_PERMISSION)
    if declared == "*":
        return

    if declared is None:
        if local_only:
            # Only local processes can call: the 3.2 behaviour, kept
            return
        permission = Permission(PERMISSION_CALL, resource)
    else:
        permission = Permission.parse(str(declared))

    check_permission(context, permission)


def _specification_methods(clazz: type, specifications: Iterable[str]) -> set[str] | None:
    """
    Lists the public members of the specification classes of a service class

    :param clazz: Class of the service
    :param specifications: Exported specifications
    :return: The member names, or None if no exported specification is a class in the MRO
    """
    specifications = set(specifications)
    names: set[str] | None = None
    for parent in clazz.__mro__:
        # vars(), not getattr(): the field is inherited by the implementation classes too
        declared = vars(parent).get(PELIX_SPECIFICATION_FIELD)
        if declared and specifications.intersection(declared):
            names = (names or set()).union(name for name in dir(parent) if not name.startswith("_"))
    return names


def get_remote_method(
    service: Any, method_name: str, specifications: Iterable[str]
) -> "Callable[..., Any] | None":
    """
    Looks for a method a remote caller is allowed to call on an exported service.

    On top of the rules of :func:`pelix.utilities.get_remote_method`, when an exported
    specification is a class found in the MRO of the service (a ``Protocol`` decorated
    with ``@Specification``), only the members of those classes can be called.

    :param service: The exported service instance
    :param method_name: Name of the method given by the caller
    :param specifications: Specifications exported by the endpoint
    :return: The method to call, or None if it can't be called remotely
    """
    method = pelix.utilities.get_remote_method(service, method_name)
    if method is None:
        return None

    allowed = _specification_methods(type(service), specifications)
    if allowed is not None and method_name not in allowed:
        return None
    return method


# ------------------------------------------------------------------------------


def _get_origin(url: str) -> str | None:
    """
    Normalizes the origin of a URL: ``scheme://host:port``

    :param url: A URL
    :return: The origin, or None for an invalid URL
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.hostname:
        return None

    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"{scheme}://{host}:{port or (443 if scheme == 'https' else 80)}"


def get_auth_headers(
    context: "BundleContext", transport: str, url: str, endpoint: Mapping[str, Any]
) -> dict[str, str]:
    """
    Prepares the authentication headers of a request to a peer.

    Credentials are only sent over HTTPS, where the client verifies the certificate of
    the server, or to a loopback host: else a spoofed announcement could collect them.

    :param context: A bundle context, to reach the credentials providers
    :param transport: Name of the transport
    :param url: URL the request will be sent to
    :param endpoint: Properties of the endpoint, if any
    :return: The headers to add to the request (can be empty)
    """
    credentials = None
    for reference in sorted(context.get_all_service_references(RemoteCredentialsProvider) or []):
        try:
            provider = context.get_service(reference)
        except BundleException:
            continue

        try:
            credentials = provider.get_credentials(transport, url, endpoint)
        except Exception:
            _logger.exception("Error getting the credentials of %s from %s", url, provider)
        finally:
            context.unget_service(reference)

        if credentials is not None:
            break
    else:
        return {}

    parts = urlsplit(url)
    if parts.scheme.lower() != "https" and not is_loopback_host(parts.hostname):
        origin = _get_origin(url) or url
        if origin not in _warned_peers:
            _warned_peers.add(origin)
            _logger.warning("Not sending credentials to %s: it is neither HTTPS nor a loopback host", origin)
        return {}

    if isinstance(credentials, UsernamePassword):
        token = base64.b64encode(f"{credentials.username}:{credentials.password}".encode()).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    _logger.warning("Unsupported kind of credentials for %s: %s", transport, credentials.KIND)
    return {}


@ComponentFactory(FACTORY_CREDENTIALS_FILE)
@Provides(RemoteCredentialsProvider)
@Property("_path", PROP_CREDENTIALS_FILE)
class CredentialsFile(RemoteCredentialsProvider):
    """
    Credentials read from a TOML file, keyed by the origin of the peer::

        [[peer]]
        origin = "https://peer.example:8443"
        username = "batch"
        password = "..."

    Only the origin selects credentials: a framework UID or a specification comes from
    discovery, so keying on them would hand the credentials to whoever announces them.
    The file is read when the component is validated.
    """

    def __init__(self) -> None:
        self._path: str | None = None
        self.__credentials: dict[str, UsernamePassword] = {}

    @Validate
    def _validate(self, _: "BundleContext") -> None:
        """
        Component validated: loads the file
        """
        if not self._path:
            raise ValueError(f"No {PROP_CREDENTIALS_FILE} given")

        _warn_about_file_mode(self._path)
        with open(self._path, "rb") as file:
            content = tomllib.load(file)

        credentials: dict[str, UsernamePassword] = {}
        for index, peer in enumerate(content.get("peer", [])):
            origin = _get_origin(str(peer.get("origin", "")))
            if origin is None or not isinstance(peer.get("username"), str) or "password" not in peer:
                # Never log the entry itself: it holds a password
                _logger.warning(
                    "%s: ignoring peer #%d, it needs an origin, a username and a password", self._path, index
                )
                continue
            credentials[origin] = UsernamePassword(peer["username"], str(peer["password"]))
        self.__credentials = credentials

    def get_credentials(self, transport: str, url: str, endpoint: Mapping[str, Any]) -> Credentials | None:
        origin = _get_origin(url)
        return self.__credentials.get(origin) if origin else None


# ------------------------------------------------------------------------------


def cap_ranking(context: "BundleContext", properties: Mapping[str, Any]) -> dict[str, Any]:
    """
    Caps the ranking of a service to import, so that a peer cannot outrank local services

    :param context: A bundle context, to read the framework property
    :param properties: Properties of the imported service
    :return: A copy of the properties, with the capped ranking
    """
    try:
        cap = int(context.get_property(PROP_IMPORT_MAX_RANKING) or DEFAULT_IMPORT_MAX_RANKING)
    except (TypeError, ValueError):
        _logger.error("Invalid %s: using %d", PROP_IMPORT_MAX_RANKING, DEFAULT_IMPORT_MAX_RANKING)
        cap = DEFAULT_IMPORT_MAX_RANKING

    ranking = properties.get(SERVICE_RANKING)
    if not isinstance(ranking, int) or isinstance(ranking, bool):
        ranking = 0
    return {**properties, SERVICE_RANKING: min(ranking, cap)}


def accept_import(context: "BundleContext", properties: dict[str, Any]) -> bool:
    """
    Checks an endpoint against the import filter of the framework

    :param context: A bundle context, to read the framework property
    :param properties: Properties of the endpoint
    :return: True if the endpoint can be imported
    """
    ldap_filter = context.get_property(PROP_IMPORT_FILTER)
    if not ldap_filter:
        return True

    try:
        parsed = get_ldap_filter(ldap_filter)
    except (TypeError, ValueError) as ex:
        # Fail closed: a typo must not open the imports to everybody
        _logger.error("Invalid %s, refusing every import: %s", PROP_IMPORT_FILTER, ex)
        return False

    return parsed is None or parsed.matches(properties)


# ------------------------------------------------------------------------------


class DiscoverySigner:
    """
    Signs and checks discovery announcements with a key shared by a group of frameworks
    (HMAC-SHA256).

    It proves that the sender holds the key, not which framework it is: any member can
    announce for any framework. A timestamp and a nonce bound the replay of a captured
    announcement, so the clocks of the group must be synchronized within ``max_age``.
    """

    def __init__(self, key: bytes, max_age: float = 60.0) -> None:
        """
        :param key: The group key
        :param max_age: Maximum age of an announcement, and clock skew allowed, in seconds
        :raise ValueError: The key is too short
        """
        if len(key) < _MIN_KEY_SIZE:
            raise ValueError(f"A discovery key must be at least {_MIN_KEY_SIZE} bytes long")

        self.__key = key
        self.__max_age = max_age
        # Nonces seen within max_age: (timestamp, nonce), oldest first
        self.__nonces: collections.deque[tuple[float, str]] = collections.deque()
        self.__seen: set[str] = set()
        self.__lock = threading.Lock()

    @classmethod
    def from_file(cls, path: str) -> "DiscoverySigner":
        """
        Reads the group key from a file: its content, without the surrounding blanks

        :param path: Path to the key file
        :return: The signer
        :raise OSError: Error reading the file
        :raise ValueError: The key is too short
        """
        _warn_about_file_mode(path)
        with open(path, "rb") as file:
            return cls(file.read().strip())

    def __mac(self, payload: Mapping[str, Any], timestamp: float, nonce: str) -> str:
        """
        Computes the signature of a payload: sorted keys make the JSON form canonical
        """
        data = json.dumps([payload, timestamp, nonce], sort_keys=True, separators=(",", ":"))
        return hmac.new(self.__key, data.encode("utf-8"), hashlib.sha256).hexdigest()

    def sign(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """
        Signs an announcement

        :param payload: The announcement, which must be serializable in JSON
        :return: A copy of the announcement, with its signature
        """
        timestamp = time.time()
        nonce = secrets.token_hex(16)
        signature = {"ts": timestamp, "nonce": nonce, "mac": self.__mac(payload, timestamp, nonce)}
        return {**payload, _SIGNATURE_KEY: signature}

    def verify(self, payload: Any) -> dict[str, Any] | None:
        """
        Checks a signed announcement

        :param payload: The announcement, as parsed from JSON
        :return: The announcement without its signature, or None if it must be ignored
        """
        if not isinstance(payload, dict):
            return None

        content = dict(payload)
        signature = content.pop(_SIGNATURE_KEY, None)
        try:
            timestamp = float(signature["ts"])
            nonce = str(signature["nonce"])
            mac = str(signature["mac"])
        except (KeyError, TypeError, ValueError):
            return None

        if not hmac.compare_digest(mac, self.__mac(content, signature["ts"], nonce)):
            return None

        now = time.time()
        if abs(now - timestamp) > self.__max_age:
            return None

        with self.__lock:
            # Forget the nonces too old to be accepted anyway, which bounds the cache
            while self.__nonces and self.__nonces[0][0] < now - 2 * self.__max_age:
                self.__seen.discard(self.__nonces.popleft()[1])

            if nonce in self.__seen:
                return None

            self.__seen.add(nonce)
            self.__nonces.append((max(timestamp, now), nonce))
        return content
