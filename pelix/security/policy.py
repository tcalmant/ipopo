#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
The policy file: roles granted from users and groups, permissions granted to roles.

One component provides both halves, so the two levels live in one readable file::

    [roles.admin]
    users  = ["thomas"]
    groups = ["dev-leads"]

    [roles.operator]
    groups = ["dev", "ops"]

    [permissions]
    admin    = ["jobs.*", "config.*"]
    operator = ["jobs.read", "jobs.submit"]

Read it as: groups and users are facts asserted by the identity source, roles are
granted from those facts, and permissions are granted to roles.

The format is TOML for one decisive reason: **TOML keys are case-sensitive by
specification**, and role names are keys here. An INI file would have folded ``Admin``
into ``admin`` in the very component held up as the example of folding nothing, and the
defence would have been one easily-lost configuration line. Typed tables also remove the
``user:`` / ``group:`` prefixes an untyped value would have needed, and a duplicate key
becomes a parse error instead of a silently kept last one.

This module also ships the deliberate escape hatch: an allow-all authorizer, which
warns loudly when it validates.

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

import logging
import os
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from pelix import services
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Validate
from pelix.security import (
    FACTORY_ALLOW_ALL,
    FACTORY_POLICY_FILE,
    PROP_POLICY_FILE,
    Authorizer,
    Decision,
    MembershipProvider,
    Permission,
    Subject,
)

try:
    # Only one of the two exists on any given interpreter, so a type checker aimed at
    # the lowest supported version cannot resolve the first one
    import tomllib  # ty: ignore[unresolved-import]
except ImportError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef] # ty: ignore[unresolved-import]

if TYPE_CHECKING:
    from pelix.framework import BundleContext

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class PolicyError(ValueError):
    """
    The file is well-formed TOML but not a well-shaped policy.

    ``tomllib`` guarantees the former only: it will happily return
    ``{"roles": {"admin": 12}}``.
    """


def _as_names(value: Any, where: str) -> frozenset[str]:
    """
    Reads a list of names, refusing anything else.

    :param value: The value read from the file
    :param where: Where it came from, for the message
    :return: The names
    :raise PolicyError: The value is not a list of strings
    """
    if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
        raise PolicyError(f"{where} must be a list of strings")

    return frozenset(value)


class PolicyTable:
    """
    A parsed policy: which roles a subject holds, and what each role may do.

    Plain object, with no framework behind it, so a policy can be checked in a test
    with one ``PolicyTable(text)``.
    """

    def __init__(self, text: str, source: str = "<memory>") -> None:
        """
        :param text: The content of the policy file
        :param source: Where it came from, for the messages
        :raise PolicyError: The file is not a well-shaped policy
        :raise tomllib.TOMLDecodeError: The file is not well-formed TOML
        """
        self._source = source
        self._role_users: dict[str, frozenset[str]] = {}
        self._role_groups: dict[str, frozenset[str]] = {}
        self._permissions: dict[str, list[Permission]] = {}

        self.__load(tomllib.loads(text))
        self.__report_dangling()

    def __load(self, data: dict[str, Any]) -> None:
        """
        Validates the shape of the parsed document and fills the tables.

        Anything unexpected refuses the file as a whole rather than silently dropping
        the malformed half.

        :param data: The parsed TOML document
        :raise PolicyError: The document is not a well-shaped policy
        """
        roles = data.get("roles", {})
        if not isinstance(roles, dict):
            raise PolicyError("[roles] must be a table")

        for role, grants in roles.items():
            if not isinstance(grants, dict):
                raise PolicyError(f"[roles.{role}] must be a table of users and groups")

            unknown = set(grants) - {"users", "groups"}
            if unknown:
                raise PolicyError(f"[roles.{role}] has unknown keys: {sorted(unknown)}")

            self._role_users[role] = _as_names(grants.get("users", []), f"[roles.{role}].users")
            self._role_groups[role] = _as_names(grants.get("groups", []), f"[roles.{role}].groups")

        permissions = data.get("permissions", {})
        if not isinstance(permissions, dict):
            raise PolicyError("[permissions] must be a table")

        for role, specs in permissions.items():
            names = _as_names(specs, f"[permissions].{role}")
            for spec in sorted(names):
                if "*" in spec:
                    # A wildcard is one typo away from full access, so every one of them
                    # is named when the file is loaded
                    _logger.warning(
                        "%s: role '%s' is granted the wildcard permission '%s'", self._source, role, spec
                    )

            self._permissions[role] = [Permission.parse(spec) for spec in sorted(names)]

    def __report_dangling(self) -> None:
        """
        Reports a role granted to somebody but given no permission, and a permission
        given to a role nobody holds.

        Every name here is matched exactly against what an identity source provided, so
        it has to be spelled the way that source spells it. Most spelling mistakes
        produce one of those two shapes, which is what makes this cheap check worth its
        lines: the typo surfaces at load rather than as an unexplained denial later.
        """
        granted = set(self._role_users) | set(self._role_groups)

        for role in sorted(granted - set(self._permissions)):
            _logger.warning("%s: role '%s' is granted to somebody but has no permission", self._source, role)

        for role in sorted(set(self._permissions) - granted):
            _logger.warning("%s: role '%s' has permissions but is granted to nobody", self._source, role)

    def get_roles(self, subject: Subject) -> frozenset[str]:
        """
        Returns the roles the policy grants to the given subject.

        It reads ``subject.groups``, which is complete only because every provider
        contributed its groups before any of them was asked for roles.

        :param subject: The subject being authenticated, with its groups resolved
        :return: The granted role names
        """
        return frozenset(
            role
            for role in set(self._role_users) | set(self._role_groups)
            if subject.name in self._role_users.get(role, frozenset())
            or subject.groups & self._role_groups.get(role, frozenset())
        )

    def is_permitted(self, subject: Subject, permission: Permission) -> Decision:
        """
        Decides whether one of the subject's roles grants the permission.

        **Never returns DENY**, only PERMIT or ABSTAIN: the format expresses grants
        only, so a policy file can never veto a permission another, looser authorizer
        allows. That matters as soon as a second authorizer is registered.

        :param subject: The subject to check
        :param permission: The requested permission
        :return: PERMIT if a role grants it, ABSTAIN otherwise
        """
        for role in subject.roles:
            for grant in self._permissions.get(role, ()):
                if grant.implies(permission):
                    return Decision.PERMIT

        return Decision.ABSTAIN


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_POLICY_FILE)
@Provides([MembershipProvider, Authorizer, services.FileInstallListener])
@Property("_policy_path", PROP_POLICY_FILE)
@Property("_watched_folder", services.PROP_FILEINSTALL_FOLDER)
class PolicyFile(MembershipProvider, Authorizer, services.FileInstallListener):
    """
    Grants roles from users and groups, and permissions to roles, from a TOML file.

    Like the password store, it is reloaded through the File Install service when that
    bundle is available, and read once at validation otherwise.
    """

    def __init__(self) -> None:
        self._policy_path: str = ""
        self._watched_folder: str = ""
        self._table: PolicyTable | None = None

    @Validate
    def _validate(self, _: "BundleContext") -> None:
        """
        Component validated: read the file once
        """
        if not self._policy_path:
            raise ValueError(f"No policy file: set the '{PROP_POLICY_FILE}' property")

        self._policy_path = os.path.abspath(self._policy_path)
        self.reload()

        # Published last, so that File Install does not bind before the file is read
        self._watched_folder = os.path.dirname(self._policy_path)

    @Invalidate
    def _invalidate(self, _: "BundleContext") -> None:
        """
        Component invalidated
        """
        self._watched_folder = ""
        self._table = None

    def reload(self) -> None:
        """
        Reloads the policy file.

        On a parse failure, a shape failure, an empty file or an unreadable one, the
        **previous table is kept** and an error is logged. A bad policy reload is
        higher-stakes than a bad user-list reload precisely because it could silently
        widen access: an empty ``[permissions]`` table parses and denies everything,
        which is safe, but a truncated file must not be mistaken for that.
        """
        try:
            with open(self._policy_path, encoding="utf-8") as file:
                text = file.read()
        except OSError as ex:
            _logger.error("Error reading %s: %s. Keeping the previous policy", self._policy_path, ex)
            return

        if not text.strip():
            _logger.error("%s is empty: keeping the previous policy", self._policy_path)
            return

        try:
            table = PolicyTable(text, self._policy_path)
        except (tomllib.TOMLDecodeError, PolicyError, ValueError) as ex:
            _logger.error("Error loading %s: %s. Keeping the previous policy", self._policy_path, ex)
            return

        self._table = table

    # ------------------------------------------------------------------------

    def get_groups(self, subject: Subject) -> Iterable[str]:
        """
        A policy asserts no group membership: a group is a fact from an identity source
        """
        return ()

    def get_roles(self, subject: Subject) -> Iterable[str]:
        """
        Returns the roles the policy grants to the given subject
        """
        return self._table.get_roles(subject) if self._table is not None else frozenset()

    def is_permitted(self, subject: Subject, permission: Permission) -> Decision:
        """
        Decides whether one of the subject's roles grants the permission
        """
        return self._table.is_permitted(subject, permission) if self._table is not None else Decision.ABSTAIN

    def folder_change(
        self, folder: str, added: Iterable[str], updated: Iterable[str], deleted: Iterable[str]
    ) -> None:
        """
        The File Install service reports a change in the watched folder
        """
        if os.path.basename(self._policy_path) in set(added) | set(updated) | set(deleted):
            _logger.info("Reloading %s", self._policy_path)
            self.reload()


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_ALLOW_ALL)
@Provides(Authorizer)
class AllowAllAuthorizer(Authorizer):
    """
    Permits everything, to everybody.

    The deliberate escape hatch: with no authorizer registered every permission is
    denied, so a test or a development deployment which genuinely wants a permissive
    answer gets it in one line rather than by weakening a default. It warns every time
    it validates, so it cannot sit unnoticed in a production configuration.
    """

    @Validate
    def _validate(self, _: "BundleContext") -> None:
        _logger.warning(
            "The allow-all authorizer is active: every permission is granted to everybody, "
            "including anonymous callers"
        )

    def is_permitted(self, subject: Subject, permission: Permission) -> Decision:
        return Decision.PERMIT
