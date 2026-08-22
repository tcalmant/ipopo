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
from collections.abc import Generator, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from pelix.constants import BundleException, Specification

if TYPE_CHECKING:
    from pelix.framework import BundleContext

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

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
            f"authenticated={self.authenticated}, method={self.method!r})"
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
