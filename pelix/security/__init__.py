#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix security package.

Defines the identity beans, the exceptions, the service specifications and the current
subject of the authentication and authorization layer.

This module is importable with no framework running: like :mod:`pelix.constants` and
:mod:`pelix.utilities`, it imports nothing but the standard library and
:mod:`pelix.constants`. That is what lets a credential store or a set of decorated
methods be unit-tested with a bare ``import``.

**Stated non-goal**: Pelix has no code-level permission model, no sandbox and no
signed-bundle verification. Any bundle which gets installed can register a
higher-ranked :class:`Authorizer`, or simply import :func:`run_as`. This layer protects
against remote callers, not against locally installed bundles.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.2.2

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

import contextlib
import contextvars
import hashlib
from collections.abc import Generator, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from pelix.constants import BundleException, Specification

if TYPE_CHECKING:
    import ssl

    from pelix.framework import BundleContext

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "ANONYMOUS",
    "ATTRIBUTE_SESSION_ID",
    "EVENT_PROP_AUTHENTICATED",
    "EVENT_PROP_DECLARATION",
    "EVENT_PROP_KIND",
    "EVENT_PROP_METHOD",
    "EVENT_PROP_PERMISSION",
    "EVENT_PROP_REASON",
    "EVENT_PROP_SOURCE",
    "EVENT_PROP_TRANSPORT",
    "EVENT_PROP_USER",
    "FACTORY_ALLOW_ALL",
    "FACTORY_HTPASSWD",
    "FACTORY_POLICY_FILE",
    "PROP_CREDENTIAL_KINDS",
    "PROP_HTPASSWD_FILE",
    "PROP_HTPASSWD_GROUPS",
    "PROP_HTPASSWD_PLAINTEXT",
    "PROP_POLICY_FILE",
    "PROP_THROTTLE_LOCKOUT",
    "PROP_THROTTLE_MAX_FAILURES",
    "PROP_THROTTLE_MAX_LOCKOUT",
    "PROP_THROTTLE_WINDOW",
    "SERVICE_AUTHENTICATOR",
    "SERVICE_AUTHORIZATION",
    "SERVICE_AUTHORIZER",
    "SERVICE_MEMBERSHIP_PROVIDER",
    "TOPIC_ACCESS_DENIED",
    "TOPIC_AUTH_FAILURE",
    "TOPIC_AUTH_SUCCESS",
    "AccessDenied",
    "AuthenticationFailed",
    "AuthenticationRequired",
    "Authenticator",
    "Authorization",
    "Authorizer",
    "ClientCertificate",
    "Credentials",
    "Decision",
    "MembershipProvider",
    "Permission",
    "SecurityError",
    "Subject",
    "UsernamePassword",
    "get_current_subject",
    "run_as",
    "use_authorization",
]

# ------------------------------------------------------------------------------

SERVICE_AUTHENTICATOR = "pelix.security.authenticator"
""" Specification of a credential store: are these credentials valid, and who is it """

SERVICE_MEMBERSHIP_PROVIDER = "pelix.security.membership"
""" Specification of a provider of the groups and roles of a subject """

SERVICE_AUTHORIZER = "pelix.security.authorizer"
""" Specification of a policy: may this subject do this """

SERVICE_AUTHORIZATION = "pelix.security.authorization"
""" Specification of the authorization facade, the service application code uses """

# ------------------------------------------------------------------------------

PROP_CREDENTIAL_KINDS = "pelix.security.credentials"
""" Kinds of credentials an Authenticator accepts, as an iterable of strings """

PROP_HTPASSWD_FILE = "pelix.security.htpasswd.file"
""" Path to the .htpasswd file of the htpasswd component """

PROP_HTPASSWD_GROUPS = "pelix.security.htpasswd.groups"
""" Path to the .htgroup file of the htpasswd component """

PROP_HTPASSWD_PLAINTEXT = "pelix.security.htpasswd.allow_plaintext"
""" Accept plaintext passwords in a .htpasswd file. Default: False """

PROP_POLICY_FILE = "pelix.security.policy.file"
""" Path to the TOML policy file of the policy component """

PROP_THROTTLE_MAX_FAILURES = "pelix.security.throttle.max_failures"
""" Framework property: failures of an account or a source which lock it out. Default: 5, 0 disables """

PROP_THROTTLE_WINDOW = "pelix.security.throttle.window"
""" Framework property: seconds within which failures are counted. Default: 900 """

PROP_THROTTLE_LOCKOUT = "pelix.security.throttle.lockout"
""" Framework property: seconds of the first lockout, doubling on each new one. Default: 60 """

PROP_THROTTLE_MAX_LOCKOUT = "pelix.security.throttle.max_lockout"
""" Framework property: upper bound of a lockout, in seconds. Default: 900 """

# ------------------------------------------------------------------------------

FACTORY_HTPASSWD = "pelix.security.htpasswd.factory"
""" Name of the component factory of the .htpasswd credential store """

FACTORY_POLICY_FILE = "pelix.security.policy.file.factory"
""" Name of the component factory of the TOML policy file """

FACTORY_ALLOW_ALL = "pelix.security.authorizer.allow-all.factory"
""" Name of the component factory of the allow-all Authorizer escape hatch """

# ------------------------------------------------------------------------------

ATTRIBUTE_SESSION_ID = "pelix.security.session.id"
""" Reserved Subject.attributes key, holding the handle of a session mechanism """

TOPIC_AUTH_SUCCESS = "pelix/security/AUTH_SUCCESS"
""" EventAdmin topic of a successful authentication """

TOPIC_AUTH_FAILURE = "pelix/security/AUTH_FAILURE"
""" EventAdmin topic of a rejected authentication """

TOPIC_ACCESS_DENIED = "pelix/security/ACCESS_DENIED"
""" EventAdmin topic of a refused authorization """

EVENT_PROP_USER = "user"
""" Event property: name of the subject, or the user name an authentication tried """

EVENT_PROP_KIND = "kind"
""" Event property: kind of the credentials of an authentication """

EVENT_PROP_METHOD = "method"
""" Event property: mechanism of an authentication: "password", "certificate", "basic", ... """

EVENT_PROP_TRANSPORT = "transport"
""" Event property: transport an authentication came through: "http", "shell", ... """

EVENT_PROP_SOURCE = "source"
""" Event property: where an authentication came from, as its transport named it """

EVENT_PROP_REASON = "reason"
""" Event property: generic reason of a failure: "rejected" or "throttled" """

EVENT_PROP_AUTHENTICATED = "authenticated"
""" Event property: whether the refused subject was authenticated """

EVENT_PROP_PERMISSION = "permission"
""" Event property: the refused permission, as a string """

EVENT_PROP_DECLARATION = "declaration"
""" Event property: the security decorator which refused a call """

# ------------------------------------------------------------------------------


class SecurityError(Exception):
    """
    Root of the security exception family
    """


class AuthenticationFailed(SecurityError):
    """
    Credentials were presented and are wrong
    """


class AuthenticationRequired(SecurityError):
    """
    The caller is anonymous and needs a challenge: an HTTP transport answers 401
    """


class AccessDenied(SecurityError):
    """
    The caller is authenticated but not permitted: an HTTP transport answers 403
    """


# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Subject:
    """
    A complete and immutable snapshot of who is calling: a person, a service account, a
    device, a peer framework or the anonymous caller.

    The three levels are flat and immutable: ``name`` is the user, ``groups`` is the
    membership asserted by an identity source, and ``roles`` is the entitlement level
    granted from those facts. There is no membership graph and no nesting.

    Every identifier is compared exactly, with no case folding and no Unicode
    normalization: a source whose matching rule is case-insensitive applies that rule
    itself and emits a single documented canonical form.
    """

    name: str
    groups: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()
    # compare=False: a Mapping is unhashable, so attributes must be excluded to keep Subject hashable
    attributes: Mapping[str, Any] = field(default_factory=dict, compare=False)
    authenticated: bool = False
    method: str | None = None
    """ Name of the mechanism which authenticated this subject: "basic", "oidc", ... """
    transport: str | None = None
    """
    Name of the transport this subject authenticated through: "http", "shell", ...

    Kept apart from ``method``: two transports can use the same mechanism, and an audit
    must tell an administration shell login from a service call.
    """

    def __post_init__(self) -> None:
        # frozen=True is not immutability: the caller may still hold the mapping it gave
        if not isinstance(self.attributes, MappingProxyType):
            object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))

        object.__setattr__(self, "groups", frozenset(self.groups))
        object.__setattr__(self, "roles", frozenset(self.roles))

    def __repr__(self) -> str:
        # Name the attribute keys only: printing their values could leak raw claims or session handles
        return (
            f"Subject(name={self.name!r}, groups={sorted(self.groups)}, "
            f"roles={sorted(self.roles)}, attributes=[{', '.join(sorted(self.attributes))}], "
            f"authenticated={self.authenticated}, method={self.method!r}, transport={self.transport!r})"
        )


ANONYMOUS = Subject("anonymous")
""" The caller of a request which carried no identity """


@dataclass(frozen=True)
class Credentials:
    """
    Base class of what a transport extracted, before it is validated.

    ``KIND`` is what an :class:`Authenticator` is selected on: it registers with the
    kinds it accepts in its :data:`PROP_CREDENTIAL_KINDS` property, and the core builds
    an LDAP filter from the kind of the object it was handed.
    """

    KIND: ClassVar[str] = "unknown"


@dataclass(frozen=True)
class UsernamePassword(Credentials):
    """
    A user name and a password, as HTTP Basic or a shell login produces them
    """

    KIND: ClassVar[str] = "password"

    username: str
    # repr=False, or the first traceback which touches this prints the password
    password: str = field(repr=False)


# Short names RFC 4514 section 3 defines, keyed by the long names the ssl module uses.
# Anything else keeps its ssl name, which is why the output is only "RFC 4514 style"
_RFC4514_NAMES = {
    "commonName": "CN",
    "localityName": "L",
    "stateOrProvinceName": "ST",
    "organizationName": "O",
    "organizationalUnitName": "OU",
    "countryName": "C",
    "streetAddress": "STREET",
    "domainComponent": "DC",
    "userId": "UID",
}


def _escape_dn_value(value: str) -> str:
    """
    Escapes an attribute value as RFC 4514 section 2.4 requires.

    Without it, a subject whose CN contains ``,O=Acme`` would print exactly like a
    certificate issued to organization Acme.

    :param value: The raw attribute value
    :return: The escaped value
    """
    last = len(value) - 1
    escaped: list[str] = []
    for index, char in enumerate(value):
        if char == "\x00":
            escaped.append("\\00")
        elif char in ',+"\\<>;' or (index == 0 and char in " #") or (index == last and char == " "):
            escaped.append("\\" + char)
        else:
            escaped.append(char)

    return "".join(escaped)


def _format_dn(rdns: Iterable[Iterable[tuple[str, str]]]) -> str:
    """
    Formats a distinguished name, as the ssl module decodes it, as an RFC 4514 style
    string.

    The ssl module lists the RDNs in certificate order, most significant first, while
    RFC 4514 writes them the other way round: ``CN=batch,O=Acme,C=FR``.

    :param rdns: The ``subject`` entry of ``SSLSocket.getpeercert()``
    :return: The distinguished name as a string
    """
    return ",".join(
        "+".join(f"{_RFC4514_NAMES.get(name, name)}={_escape_dn_value(value)}" for name, value in rdn)
        for rdn in reversed(list(rdns))
    )


@dataclass(frozen=True)
class ClientCertificate(Credentials):
    """
    A client certificate, as a TLS transport received it.

    **Only build one from a certificate the TLS layer already verified** (a server
    context with ``verify_mode = ssl.CERT_REQUIRED`` and a trusted authority chain).
    Nothing here checks a signature, a validity period or a revocation: presenting this
    object means "the TLS handshake proved the peer holds the private key of this
    certificate, issued by an authority I trust". An authenticator only maps it to a
    user.

    ``fingerprint`` identifies this very certificate, whoever issued it. ``subject``
    and ``alt_names`` are only as trustworthy as every authority the transport trusts,
    since any of them can issue another certificate with the same names.
    """

    KIND: ClassVar[str] = "certificate"

    fingerprint: str
    """ SHA-256 of the DER certificate, in lowercase hexadecimal, with no separator """

    subject: str = ""
    """ The subject, as an RFC 4514 style string: ``CN=batch,O=Acme,C=FR`` """

    alt_names: tuple[str, ...] = ()
    """ The subject alternative names, as ``type:value`` strings: ``DNS:host.example.com`` """

    @classmethod
    def from_der(cls, der: bytes, details: Mapping[str, Any] | None = None) -> "ClientCertificate":
        """
        Builds the credentials of a verified certificate.

        The standard library cannot decode a DER certificate, so the subject and the
        alternative names come from the dictionary form of
        ``SSLSocket.getpeercert()``, which the ssl module only fills for a verified
        certificate. Without it, only the fingerprint is known.

        :param der: The certificate, in DER form: ``getpeercert(binary_form=True)``
        :param details: The certificate as ``getpeercert()`` decoded it, if available
        :return: The credentials
        """
        subject = ""
        alt_names: tuple[str, ...] = ()
        if details:
            subject = _format_dn(details.get("subject", ()))
            alt_names = tuple(f"{kind}:{value}" for kind, value in details.get("subjectAltName", ()))

        return cls(hashlib.sha256(der).hexdigest(), subject, alt_names)

    @classmethod
    def from_socket(cls, sock: "ssl.SSLSocket") -> "ClientCertificate | None":
        """
        Builds the credentials of the certificate the peer of a TLS socket presented.

        The socket must come from a context which verified that certificate: see the
        class documentation.

        :param sock: A TLS socket, after its handshake
        :return: The credentials, or None if the peer presented no certificate
        """
        der = sock.getpeercert(binary_form=True)
        if not der:
            return None

        return cls.from_der(der, sock.getpeercert())


@dataclass(frozen=True)
class Permission:
    """
    One action, optionally scoped to a resource: ``jobs.submit``, ``jobs.submit:queue-a``.

    Strings are parsed at the edges, once, so that a single type flows through the
    service specifications.
    """

    action: str
    resource: str | None = None

    @classmethod
    def parse(cls, spec: str) -> "Permission":
        """
        Parses a permission specification.

        :param spec: An action, optionally followed by ``:`` and a resource
        :return: The parsed permission
        :raise ValueError: The action half is empty
        """
        action, separator, resource = spec.partition(":")
        if not action:
            raise ValueError(f"Empty permission action in {spec!r}")

        return cls(action, resource if separator else None)

    def implies(self, other: "Permission") -> bool:
        """
        Tells if this permission, read as a grant, satisfies the given request.

        This is a pure string-matching helper on the bean, deliberately not the
        authorization decision: that one is :meth:`Authorization.is_permitted`.

        :param other: The requested permission
        :return: True if the grant covers the request
        """
        return self.__action_implies(other.action) and self.__resource_implies(other.resource)

    def __action_implies(self, action: str) -> bool:
        """
        Matches the action half: exactly, by prefix, or the single all-grant form
        """
        if self.action == "*":
            return True

        if self.action.endswith(".*"):
            # "jobs.*" covers "jobs.submit" and "jobs.queue.drain", but not "jobs"
            return action.startswith(self.action[:-1])

        return self.action == action

    def __resource_implies(self, resource: str | None) -> bool:
        """
        Matches the resource half. A grant scoped to a resource never satisfies a
        request naming none, which is the safe direction
        """
        if self.resource is None or self.resource == "*":
            return True

        return self.resource == resource

    def __str__(self) -> str:
        return self.action if self.resource is None else f"{self.action}:{self.resource}"


class Decision(Enum):
    """
    What an :class:`Authorizer` answers.

    ABSTAIN is what lets independent policies compose: the combining rule is fixed, any
    DENY denies, otherwise any PERMIT permits, otherwise the request is denied.
    """

    PERMIT = "permit"
    DENY = "deny"
    ABSTAIN = "abstain"


# ------------------------------------------------------------------------------


@Specification(SERVICE_AUTHENTICATOR)
class Authenticator(Protocol):
    """
    Specification of a credential store.

    Authenticators are consulted in ``service.ranking`` order and the contract has three
    states, not two: without the third one, a lower-ranked store becomes an oracle for
    credentials a higher-ranked store already rejected.
    """

    def authenticate(self, credentials: Credentials) -> Subject | None:
        """
        Validates the given credentials.

        :param credentials: What a transport extracted
        :return: A Subject on success, None to abstain (not my kind, not my user)
        :raise AuthenticationFailed: The credentials were presented and are wrong. No
                                     lower-ranked store is consulted
        """
        ...


@Specification(SERVICE_MEMBERSHIP_PROVIDER)
class MembershipProvider(Protocol):
    """
    Specification of a provider of the groups and roles of a subject.

    Every registered provider is consulted in both passes and the results are unioned. A
    provider may answer only one of the two, returning an empty iterable for the other.
    """

    def get_groups(self, subject: Subject) -> Iterable[str]:
        """
        Returns the groups of the given subject.

        This runs on every provider before :meth:`get_roles` runs on any, so
        ``subject.roles`` is empty here by construction and must not be looked at.

        :param subject: The subject being authenticated
        :return: The group names this provider asserts, verbatim
        """
        ...

    def get_roles(self, subject: Subject) -> Iterable[str]:
        """
        Returns the roles of the given subject.

        The subject received here has its ``groups`` already complete, which is what
        lets a policy grant a role from a group another provider contributed.

        :param subject: The subject being authenticated, with its groups resolved
        :return: The role names this provider grants, verbatim
        """
        ...


@Specification(SERVICE_AUTHORIZER)
class Authorizer(Protocol):
    """
    Specification of a policy.

    The combining rule over the registered authorizers is fixed and not configurable.
    """

    def is_permitted(self, subject: Subject, permission: Permission) -> Decision:
        """
        Decides whether the given subject holds the given permission.

        :param subject: The subject to check
        :param permission: The requested permission
        :return: PERMIT, DENY, or ABSTAIN to let another policy decide
        """
        ...


@Specification(SERVICE_AUTHORIZATION)
class Authorization(Protocol):
    """
    The authorization facade: the one service application code injects, or reaches
    through :func:`use_authorization`.

    ``subject=None`` everywhere means the current subject.
    """

    def is_permitted(self, permission: Permission, subject: Subject | None = None) -> bool:
        """
        Tells whether a subject holds a permission.

        :param permission: The requested permission
        :param subject: The subject to check, or None for the current one
        :return: True if the permission is granted
        """
        ...

    def check_permitted(self, permission: Permission, subject: Subject | None = None) -> None:
        """
        Checks that a subject holds a permission.

        :param permission: The requested permission
        :param subject: The subject to check, or None for the current one
        :raise AccessDenied: The permission is not granted
        """
        ...

    def has_role(self, role: str, subject: Subject | None = None) -> bool:
        """
        Tells whether a subject holds a role. The name is compared exactly.

        :param role: The role to look for
        :param subject: The subject to check, or None for the current one
        :return: True if the subject holds the role
        """
        ...

    def in_group(self, group: str, subject: Subject | None = None) -> bool:
        """
        Tells whether a subject belongs to a group. The name is compared exactly.

        :param group: The group to look for
        :param subject: The subject to check, or None for the current one
        :return: True if the subject belongs to the group
        """
        ...


# ------------------------------------------------------------------------------

_SUBJECT: contextvars.ContextVar[Subject] = contextvars.ContextVar("pelix.security.subject")
""" The current subject. Read through get_current_subject(), written through run_as() """


def get_current_subject() -> Subject:
    """
    Returns the subject of the current execution path.

    The current subject follows the standard Python context: wherever a context
    propagates, the subject propagates, and code crossing a boundary a context does not
    cross copies the context explicitly.

    :return: The current subject, or ANONYMOUS when nothing was published
    """
    return _SUBJECT.get(ANONYMOUS)


@contextlib.contextmanager
def run_as(subject: Subject) -> Generator[None, None, None]:
    """
    Runs the body of the ``with`` block as the given subject.

    This is privilege escalation by construction: in a framework with no sandbox,
    anyone who can import it can elevate. It is a readability tool, not a security
    boundary.

    :param subject: The subject to publish
    """
    token = _SUBJECT.set(subject)
    try:
        yield
    finally:
        _SUBJECT.reset(token)


@contextlib.contextmanager
def use_authorization(bundle_context: "BundleContext") -> Generator[Authorization, None, None]:
    """
    Utility context to use the authorization service safely in a "with" block.
    It looks after the authorization service and releases its reference when exiting
    the context.

    :param bundle_context: The calling bundle context
    :return: The authorization service
    :raise BundleException: Service not found
    """
    reference = bundle_context.get_service_reference(Authorization)
    if reference is None:
        raise BundleException("No authorization service available")

    try:
        yield bundle_context.get_service(reference)
    finally:
        try:
            bundle_context.unget_service(reference)
        except BundleException:
            # Service might have already been unregistered
            pass
