#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Declarative security decorators.

Read every one of them as "allow only": ``@AllowGroup("dev")`` means "allow only the
dev group". Each decorator narrows who can reach the target, and the names listed
inside one decorator are alternatives. The rule follows from that reading: any-of
within one decorator, all-of when they are stacked, and a method-level declaration
replaces a class-level one entirely.

They work on plain classes, with no iPOPO and, for all but ``@AllowPermission``, with
no bundle started at all: they read or write the current subject and nothing else.

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

import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any

from pelix.security import (
    AccessDenied,
    AuthenticationRequired,
    Authorization,
    Permission,
    Subject,
    get_current_subject,
    run_as,
)

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

SECURITY_ATTRIBUTE = "__pelix_security__"
""" Attribute holding the security declarations of a decorated callable """

# The one global. Only @AllowPermission needs a service, and this is the single slot
# holding it: one writer, the activator of the pelix.security.core bundle
_authorization: Authorization | None = None

# Permissions already reported as undecidable, so that a stopped bundle costs one
# warning per distinct permission rather than one per call
_warned_permissions: set[str] = set()

# ------------------------------------------------------------------------------


def set_authorization(service: Authorization | None) -> None:
    """
    Publishes the authorization service used by ``@AllowPermission``.

    There is exactly one writer, the activator of the ``pelix.security.core`` bundle,
    which sets it on start and clears it on stop.

    :param service: The authorization service, or None to clear the slot
    """
    global _authorization
    _authorization = service


def _refuse(subject: Subject, reason: str) -> None:
    """
    Raises the refusal which fits the subject.

    The choice is mechanical: an unauthenticated caller can still be helped by a
    challenge, an authenticated one cannot, and a transport maps the two exceptions to
    401 and 403.

    :param subject: The subject which was refused
    :param reason: Why it was refused
    :raise AuthenticationRequired: The subject is not authenticated
    :raise AccessDenied: The subject is authenticated and still not allowed
    """
    if not subject.authenticated:
        raise AuthenticationRequired(reason)

    raise AccessDenied(reason)


class _Declaration:
    """
    One application of a decorator: what it checks, and what the shell must be able to
    print without invoking anything
    """

    __slots__ = ("check", "kind", "subject", "values")

    def __init__(
        self,
        kind: str,
        values: tuple[Any, ...] = (),
        check: Callable[[Subject], None] | None = None,
        subject: Subject | None = None,
    ) -> None:
        """
        :param kind: Name of the decorator which produced this declaration
        :param values: The names it was given
        :param check: What to run against the current subject before the call
        :param subject: The identity to publish around the call, for @RunAs
        """
        self.kind = kind
        self.values = values
        self.check = check
        self.subject = subject

    def __repr__(self) -> str:
        return f"{self.kind}{self.values}" if self.values else self.kind


def _decorate(target: Any, declaration: _Declaration | None) -> Any:
    """
    Wraps and marks a target, or sets a class default.

    Two flavours of wrapper are emitted, because a synchronous wrapper around a
    coroutine function checks and restores the context before the body ever runs: that
    turns ``@RunAs`` into a no-op which looks correct.

    :param target: The class or callable being decorated
    :param declaration: What was declared, or None for "no narrowing"
    :return: The class, or a wrapper around the callable
    """
    if isinstance(target, type):
        return _decorate_class(target, declaration)

    existing: list[_Declaration] = list(getattr(target, SECURITY_ATTRIBUTE, ()))
    if declaration is None:
        # @AllowAll: nothing to wrap. The mark is what makes a class-level default skip
        # this method
        setattr(target, SECURITY_ATTRIBUTE, existing)
        return target

    subject = declaration.subject
    check = declaration.check

    if inspect.iscoroutinefunction(target):

        @functools.wraps(target)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if subject is not None:
                with run_as(subject):
                    return await target(*args, **kwargs)

            if check is not None:
                check(get_current_subject())

            return await target(*args, **kwargs)

    else:

        @functools.wraps(target)
        def wrapper(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
            if subject is not None:
                with run_as(subject):
                    return target(*args, **kwargs)

            if check is not None:
                check(get_current_subject())

            return target(*args, **kwargs)

    # Built fresh: mutating in place would rewrite the wrapped function's own declaration too
    setattr(wrapper, SECURITY_ATTRIBUTE, [*existing, declaration])
    return wrapper


def _decorate_class(clazz: type, declaration: _Declaration | None) -> type:
    """
    Sets a class default.

    It applies to every function defined in that class body whose name does not start
    with an underscore: without that rule, a class-level ``@DenyAll`` would also wrap
    ``__init__`` and present as a construction error rather than an authorization one.

    :param clazz: The decorated class
    :param declaration: What was declared, or None for "no narrowing"
    :return: The class itself
    """
    for name, member in list(vars(clazz).items()):
        if name.startswith("_") or not inspect.isfunction(member):
            # Not a public method defined in this body: inherited methods, nested
            # classes, static and class methods are all left alone
            continue

        if hasattr(member, SECURITY_ATTRIBUTE):
            # Method-level replaces class-level entirely. Method decorators run first,
            # so this falls out of the order of evaluation rather than needing a merge
            continue

        setattr(clazz, name, _decorate(member, declaration))

    return clazz


def _reject_bare_use(decorator: str, first: Any, example: str) -> None:
    """
    Refuses an argument-taking decorator applied without its argument.

    Written bare, the decorator would bind the decorated function as its first name and
    fail much later with a confusing message. This is a callable check used to refuse an
    unsupported form loudly, never to choose silently between two supported ones.

    :param decorator: Name of the decorator, for the message
    :param first: The value given as the first name
    :param example: How to write it properly
    :raise TypeError: The decorator was applied bare
    """
    if callable(first):
        raise TypeError(f"@{decorator} takes at least one name: write {example}")


# ------------------------------------------------------------------------------


def AllowAuthenticated(target: Any) -> Any:
    """
    Allows only authenticated subjects. Written bare, without parentheses.
    """

    def check(subject: Subject) -> None:
        if not subject.authenticated:
            _refuse(subject, "Authentication required")

    return _decorate(target, _Declaration("AllowAuthenticated", check=check))


def AllowAll(target: Any) -> Any:
    """
    No narrowing. Written bare, without parentheses.

    Its point is to override a class-level default: it marks the target, which is what
    makes the class decorator skip it.
    """
    return _decorate(target, None)


def DenyAll(target: Any) -> Any:
    """
    Total narrowing. Written bare, without parentheses.

    It always raises :class:`~pelix.security.AccessDenied`, even for an anonymous
    subject: no credential would help, so offering a challenge would be a lie.
    """

    def check(subject: Subject) -> None:
        raise AccessDenied("Denied to everyone")

    return _decorate(target, _Declaration("DenyAll", check=check))


class AllowGroup:
    """
    Allows only members of the given groups. Any of them is enough.

    Group names are compared exactly, as they are everywhere else in this layer.
    """

    __slots__ = ("_groups",)

    def __init__(self, group: str, *more: str) -> None:
        """
        :param group: A group name, mandatory
        :param more: Other acceptable group names
        :raise TypeError: The decorator was applied without a group name
        """
        _reject_bare_use("AllowGroup", group, '@AllowGroup("dev")')
        self._groups = (group, *more)

    def __call__(self, target: Any) -> Any:
        groups = self._groups

        def check(subject: Subject) -> None:
            if not subject.groups.intersection(groups):
                _refuse(subject, f"Not a member of any of the groups {groups}")

        return _decorate(target, _Declaration("AllowGroup", groups, check))


class AllowRole:
    """
    Allows only holders of the given roles. Any of them is enough.

    Role names are compared exactly.
    """

    __slots__ = ("_roles",)

    def __init__(self, role: str, *more: str) -> None:
        """
        :param role: A role name, mandatory
        :param more: Other acceptable role names
        :raise TypeError: The decorator was applied without a role name
        """
        _reject_bare_use("AllowRole", role, '@AllowRole("admin")')
        self._roles = (role, *more)

    def __call__(self, target: Any) -> Any:
        roles = self._roles

        def check(subject: Subject) -> None:
            if not subject.roles.intersection(roles):
                _refuse(subject, f"Does not hold any of the roles {roles}")

        return _decorate(target, _Declaration("AllowRole", roles, check))


class AllowPermission:
    """
    Allows only holders of the given permission.

    The specification is parsed once, at decoration time, and this is the only decorator
    which needs a service: with the ``pelix.security.core`` bundle stopped it denies,
    logging one warning per distinct permission. That is correct behaviour and it has to
    be known in advance: installing a library whose methods carry this decorator, and
    not starting the bundle, means those methods raise.
    """

    __slots__ = ("_permission",)

    def __init__(self, permission: str) -> None:
        """
        :param permission: A permission specification, ``action`` or ``action:resource``
        :raise ValueError: The specification has no action
        """
        self._permission = Permission.parse(permission)

    def __call__(self, target: Any) -> Any:
        permission = self._permission

        def check(subject: Subject) -> None:
            authorization = _authorization
            if authorization is None:
                # Fail closed, and warn once per permission rather than once per call
                key = str(permission)
                if key not in _warned_permissions:
                    _warned_permissions.add(key)
                    _logger.warning(
                        "No authorization service: denying %s. Is the pelix.security.core bundle started?",
                        key,
                    )

                raise AccessDenied(f"No authorization service to decide {permission}")

            if not authorization.is_permitted(permission, subject):
                _refuse(subject, f"Not permitted: {permission}")

        return _decorate(target, _Declaration("AllowPermission", (str(permission),), check))


class RunAs:
    """
    Runs the target under another identity.

    This is privilege escalation by construction: in a framework with no sandbox,
    anyone who can import it can elevate. It is a readability tool, not a security
    boundary, and the absence of an all-powerful built-in subject keeps it at worst a
    lateral move.
    """

    __slots__ = ("_subject",)

    def __init__(self, subject: Subject) -> None:
        """
        :param subject: The identity to publish around every call
        """
        self._subject = subject

    def __call__(self, target: Any) -> Any:
        return _decorate(target, _Declaration("RunAs", (self._subject.name,), subject=self._subject))
