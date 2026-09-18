#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
The core of the security layer: the identity pipeline and the authorization facade.

This bundle owns two things. :func:`authenticate` turns credentials into a
:class:`~pelix.security.Subject` by sequencing the registered
:class:`~pelix.security.Authenticator` and
:class:`~pelix.security.MembershipProvider` services; it is transport-neutral, so an
HTTP filter, a shell login and an MQTT ``CONNECT`` handler all call the same one. The
:class:`~pelix.security.Authorization` facade combines the registered
:class:`~pelix.security.Authorizer` services under a fixed rule, and is what
``@AllowPermission`` and application code use.

One rule runs through both: **an exception never grants**. An authorizer which raises
denies, and a provider which raises stops the authentication rather than returning a
subject whose roles are quietly incomplete.

:func:`authenticate` also throttles brute force: after too many failures for an
account or a source, that key is locked out for a while and refused without any
authenticator being consulted.

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
import logging
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Generator, Iterable
from typing import TYPE_CHECKING, Any

from pelix.constants import ActivatorProto, BundleActivator, BundleException
from pelix.ldapfilter import escape_LDAP
from pelix.security import (
    PROP_CREDENTIAL_KINDS,
    PROP_THROTTLE_LOCKOUT,
    PROP_THROTTLE_MAX_FAILURES,
    PROP_THROTTLE_MAX_LOCKOUT,
    PROP_THROTTLE_WINDOW,
    AccessDenied,
    AuthenticationFailed,
    Authenticator,
    Authorization,
    Authorizer,
    ClientCertificate,
    Credentials,
    Decision,
    MembershipProvider,
    Permission,
    Subject,
    UsernamePassword,
    get_current_subject,
)
from pelix.security.decorators import set_authorization

if TYPE_CHECKING:
    from pelix.framework import BundleContext
    from pelix.internals.registry import ServiceReference, ServiceRegistration

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

# The context of this bundle, which is how the module-level authenticate() reaches the
# service registry: one writer, the activator below
_context: "BundleContext | None" = None

# Credential kinds already reported as having no authenticator, so that a
# misconfiguration costs one warning rather than one per request
_warned_kinds: set[str] = set()

# Set once the absence of any authorizer has been reported
_warned_no_authorizer = False

# The brute-force throttle of authenticate(), or None when it is disabled: one writer,
# the activator below
_throttle: "Throttle | None" = None

# ------------------------------------------------------------------------------

DEFAULT_MAX_FAILURES = 5
""" Failures of a key within the window which lock it out """

DEFAULT_WINDOW = 900.0
""" Length of the sliding window failures are counted in, in seconds """

DEFAULT_LOCKOUT = 60.0
""" Length of the first lockout of a key, in seconds """

DEFAULT_MAX_LOCKOUT = 900.0
""" Upper bound of a lockout, however many times it doubled, in seconds """

DEFAULT_MAX_KEYS = 10000
""" Number of keys the throttle tracks at most """


class _KeyState:
    """
    What the throttle knows about one key
    """

    __slots__ = ("failures", "locked_until", "lockouts")

    def __init__(self, max_failures: int) -> None:
        # Only the latest max_failures timestamps matter to the sliding window
        self.failures: deque[float] = deque(maxlen=max_failures)
        self.locked_until = 0.0
        self.lockouts = 0


class Throttle:
    """
    Tracks authentication failures per key and locks out the keys which fail too often.

    A key is an account or a source. After ``max_failures`` failures within ``window``
    seconds, the key is locked out for ``lockout`` seconds, doubling on each new lockout
    up to ``max_lockout``. The count is a sliding window: once a lockout ends, one more
    failure within the window locks the key again, for twice as long.

    Everything is in memory, and bounded: past ``max_keys`` tracked keys, the least
    recently touched one is forgotten, so that a flood of sources costs a fixed amount
    of memory. The price is that such a flood can also make the throttle forget a key
    early.
    """

    def __init__(
        self,
        max_failures: int = DEFAULT_MAX_FAILURES,
        window: float = DEFAULT_WINDOW,
        lockout: float = DEFAULT_LOCKOUT,
        max_lockout: float = DEFAULT_MAX_LOCKOUT,
        max_keys: int = DEFAULT_MAX_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        :param max_failures: Failures within the window which lock a key out
        :param window: Length of the sliding window, in seconds
        :param lockout: Length of the first lockout, in seconds
        :param max_lockout: Upper bound of a lockout, in seconds
        :param max_keys: Number of keys tracked at most
        :param clock: A monotonic clock, in seconds: the wall clock can jump
        :raise ValueError: max_failures or max_keys is not strictly positive
        """
        if max_failures <= 0 or max_keys <= 0:
            raise ValueError("max_failures and max_keys must be strictly positive")

        self.max_failures = max_failures
        self.window = window
        self.lockout = lockout
        self.max_lockout = max(max_lockout, lockout)
        self.max_keys = max_keys
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: OrderedDict[str, _KeyState] = OrderedDict()

    def __len__(self) -> int:
        with self._lock:
            return len(self._keys)

    def __is_stale(self, state: _KeyState, now: float) -> bool:
        """
        A key whose lockout is over and which has not failed within the window has
        nothing left to remember, not even how many times it was locked out
        """
        return state.locked_until <= now and (not state.failures or state.failures[-1] <= now - self.window)

    def is_locked(self, keys: Iterable[str]) -> bool:
        """
        Tells whether any of the given keys is locked out.

        :param keys: The keys of an authentication attempt
        :return: True if at least one of them is locked out
        """
        now = self._clock()
        with self._lock:
            return any(
                state is not None and state.locked_until > now
                for state in (self._keys.get(key) for key in keys)
            )

    def record_failure(self, keys: Iterable[str]) -> None:
        """
        Counts a failure against each of the given keys, locking out those which failed
        too often.

        :param keys: The keys of the failed attempt
        """
        now = self._clock()
        with self._lock:
            for key in keys:
                state = self._keys.get(key)
                if state is None or self.__is_stale(state, now):
                    state = _KeyState(self.max_failures)
                    self._keys[key] = state
                    while len(self._keys) > self.max_keys:
                        self._keys.popitem(last=False)

                self._keys.move_to_end(key)
                state.failures.append(now)

                if (
                    state.locked_until <= now
                    and len(state.failures) >= self.max_failures
                    and state.failures[0] > now - self.window
                ):
                    duration = min(self.lockout * 2**state.lockouts, self.max_lockout)
                    state.lockouts += 1
                    state.locked_until = now + duration
                    _logger.warning(
                        "%d authentication failures within %d seconds for %s: locked out for %d seconds",
                        len(state.failures),
                        self.window,
                        key,
                        duration,
                    )

    def record_success(self, key: str) -> None:
        """
        Forgets the failures of a key, after a successful authentication.

        Only the account key is cleared this way: a source which guessed one password
        right is not cleared of the failures it made on other accounts.

        :param key: The account key of the successful attempt
        """
        with self._lock:
            self._keys.pop(key, None)


def throttle_keys(credentials: Credentials, source: str | None) -> tuple[str | None, str | None]:
    """
    Computes the throttle keys of an authentication attempt.

    :param credentials: The presented credentials
    :param source: Where they came from, if the transport knows
    :return: A tuple: the account key (None for credentials naming no account), the
             source key (None without a source)
    """
    account: str | None = None
    if isinstance(credentials, UsernamePassword):
        account = f"{credentials.KIND}:{credentials.username}"
    elif isinstance(credentials, ClientCertificate):
        account = f"{credentials.KIND}:{credentials.fingerprint}"

    return account, (f"source:{source}" if source is not None else None)


def _read_setting(
    context: "BundleContext", name: str, default: float, convert: Callable[[Any], float]
) -> float:
    """
    Reads one numeric framework property, falling back to its default when it is
    absent or unreadable.

    :param context: The bundle context
    :param name: The property name
    :param default: The value used when the property is absent or invalid
    :param convert: int or float
    :return: The value
    """
    value = context.get_property(name)
    if value is None or value == "":
        return default

    try:
        return convert(value)
    except (TypeError, ValueError):
        _logger.error("Invalid value for %s: %r. Using %s", name, value, default)
        return default


def _make_throttle(context: "BundleContext") -> Throttle | None:
    """
    Builds the throttle the framework properties describe.

    :param context: The bundle context
    :return: The throttle, or None if it is disabled
    """
    max_failures = int(_read_setting(context, PROP_THROTTLE_MAX_FAILURES, DEFAULT_MAX_FAILURES, int))
    if max_failures <= 0:
        _logger.warning(
            "Brute-force throttling of authentication is disabled (%s)", PROP_THROTTLE_MAX_FAILURES
        )
        return None

    return Throttle(
        max_failures,
        _read_setting(context, PROP_THROTTLE_WINDOW, DEFAULT_WINDOW, float),
        _read_setting(context, PROP_THROTTLE_LOCKOUT, DEFAULT_LOCKOUT, float),
        _read_setting(context, PROP_THROTTLE_MAX_LOCKOUT, DEFAULT_MAX_LOCKOUT, float),
    )


# ------------------------------------------------------------------------------


@contextlib.contextmanager
def _use_services(specification: Any, ldap_filter: str | None = None) -> Generator[list[Any], None, None]:
    """
    Looks up every service of a specification, in descending ``service.ranking`` order,
    and releases them when the block ends.

    The registry is queried rather than the services injected, because an aggregate
    injection only orders its *initial* content: a service registered later is appended,
    and the authenticator contract depends on the ranking at every call. The same query
    also applies the credential-kind filter, which an injection could not.

    :param specification: The specification to look for
    :param ldap_filter: An optional filter over the service properties
    :return: The matching services, best-ranked first
    """
    context = _context
    if context is None:
        yield []
        return

    # Sorted explicitly: a filtered lookup is rebuilt from a set and loses the registry's ranking order
    references: list[ServiceReference[Any]] = sorted(
        context.get_all_service_references(specification, ldap_filter) or []
    )
    taken: list[ServiceReference[Any]] = []
    try:
        services = []
        for reference in references:
            services.append(context.get_service(reference))
            taken.append(reference)

        yield services
    finally:
        for reference in taken:
            with contextlib.suppress(BundleException):
                context.unget_service(reference)


def _warn_about_missing_authenticator(kind: str) -> None:
    """
    Reports that no authenticator accepts a kind of credentials.

    Declaring the accepted kinds is mandatory, so the most likely cause is an
    authenticator which forgot the property rather than one which is genuinely absent.
    Saying which of the two it is costs one extra query, in the failing case only.

    :param kind: The kind of credentials which found no authenticator
    """
    if kind in _warned_kinds:
        return

    _warned_kinds.add(kind)

    context = _context
    others = (context.get_all_service_references(Authenticator, None) or []) if context is not None else []
    if others:
        _logger.warning(
            "No Authenticator accepts credentials of kind '%s', although %d are registered. "
            "An Authenticator must declare the kinds it accepts in its '%s' property",
            kind,
            len(others),
            PROP_CREDENTIAL_KINDS,
        )
    else:
        _logger.warning("No Authenticator is registered: refusing to authenticate '%s' credentials", kind)


def authenticate(credentials: Credentials, source: str | None = None) -> Subject:
    """
    Turns credentials into a subject, with its groups and roles resolved.

    The pipeline, which is the same whatever the transport was:

    1. every :class:`~pelix.security.Authenticator` accepting this kind of credentials
       is consulted in ranking order, under the three-state contract: a subject stops
       the loop, None abstains, and ``AuthenticationFailed`` stops it without letting a
       lower-ranked store answer;
    2. every :class:`~pelix.security.MembershipProvider` contributes groups, and the
       results are unioned;
    3. the subject is rebuilt with those groups, and only then does every provider
       contribute roles. The two passes are what lets a policy grant a role from a group
       a *different* provider asserted: with a single pass that rule would silently
       never fire;
    4. the final subject is returned, authenticated, with ``method`` left unset.

    ``method`` names the mechanism, which is exactly what a transport-neutral pipeline
    cannot know: the caller stamps it with ``dataclasses.replace``.

    Failures are throttled per account and, when ``source`` is given, per source. A
    locked-out key is refused before any authenticator is consulted, with the same
    exception as a wrong password: telling the caller that an account is locked would
    tell it that the account exists.

    :param credentials: What a transport extracted
    :param source: Where the credentials came from, such as the client IP address, if
                   the transport knows
    :return: The authenticated subject
    :raise AuthenticationFailed: The credentials are wrong, no authenticator accepted
                                 them, or they are locked out
    """
    throttle = _throttle
    account_key, source_key = throttle_keys(credentials, source)
    keys = [key for key in (account_key, source_key) if key is not None]

    if throttle is not None and throttle.is_locked(keys):
        raise AuthenticationFailed("Authentication failed")

    try:
        subject = _authenticate(credentials)
    except AuthenticationFailed:
        if throttle is not None:
            throttle.record_failure(keys)
        raise

    if throttle is not None and account_key is not None:
        throttle.record_success(account_key)

    return subject


def _authenticate(credentials: Credentials) -> Subject:
    """
    The pipeline of :func:`authenticate`, with no throttling.

    :param credentials: What a transport extracted
    :return: The authenticated subject
    :raise AuthenticationFailed: The credentials are wrong, or no authenticator
                                 accepted them
    """
    kind = credentials.KIND
    ldap_filter = f"({PROP_CREDENTIAL_KINDS}={escape_LDAP(kind)})"

    with _use_services(Authenticator, ldap_filter) as authenticators:
        if not authenticators:
            # Not ANONYMOUS: a caller which presented credentials and got back an
            # unauthenticated subject cannot tell that apart from a wrong password
            _warn_about_missing_authenticator(kind)
            raise AuthenticationFailed(f"No Authenticator accepts '{kind}' credentials")

        subject: Subject | None = None
        for authenticator in authenticators:
            candidate = authenticator.authenticate(credentials)
            if candidate is not None:
                subject = candidate
                break

    if subject is None:
        raise AuthenticationFailed("No Authenticator recognized these credentials")

    with _use_services(MembershipProvider) as providers:
        groups = set(subject.groups)
        for provider in providers:
            groups.update(provider.get_groups(subject))

        # Rebuilt before the second pass, or a role granted from a group contributed by
        # another provider would never be seen
        enriched = Subject(subject.name, frozenset(groups), attributes=subject.attributes)

        roles = set(subject.roles)
        for provider in providers:
            roles.update(provider.get_roles(enriched))

    # The pipeline owns the final bean: an authenticator which forgets authenticated=True
    # cannot produce a subject which passes nothing
    return Subject(
        subject.name,
        frozenset(groups),
        frozenset(roles),
        subject.attributes,
        authenticated=True,
    )


# ------------------------------------------------------------------------------


class _AuthorizationImpl(Authorization):
    """
    Combines the registered authorizers under one fixed rule: any DENY denies,
    otherwise any PERMIT permits, otherwise the request is denied.

    The rule is deliberately not configurable. Someone will ask for permit-overrides,
    and the answer is to write one authorizer: a pluggable combining algorithm is how a
    small authorization layer turns into XACML.
    """

    def is_permitted(self, permission: Permission, subject: Subject | None = None) -> bool:
        if subject is None:
            subject = get_current_subject()

        with _use_services(Authorizer) as authorizers:
            if not authorizers:
                self.__warn_about_missing_authorizer()
                return False

            permitted = False
            for authorizer in authorizers:
                try:
                    decision = authorizer.is_permitted(subject, permission)
                except Exception:
                    # An authorizer which cannot decide has not decided, and continuing
                    # would let a broken policy open a door
                    _logger.exception("Error asking %s about %s: denying", authorizer, permission)
                    return False

                if decision is Decision.DENY:
                    return False

                if decision is Decision.PERMIT:
                    permitted = True

            return permitted

    def check_permitted(self, permission: Permission, subject: Subject | None = None) -> None:
        if not self.is_permitted(permission, subject):
            raise AccessDenied(f"Not permitted: {permission}")

    def has_role(self, role: str, subject: Subject | None = None) -> bool:
        return role in (get_current_subject() if subject is None else subject).roles

    def in_group(self, group: str, subject: Subject | None = None) -> bool:
        return group in (get_current_subject() if subject is None else subject).groups

    @staticmethod
    def __warn_about_missing_authorizer() -> None:
        """
        Reports, once, that nothing can decide a permission.

        Reported on the first denial rather than at startup, because at startup the
        bundle providing the policy has usually not been started yet.
        """
        global _warned_no_authorizer
        if not _warned_no_authorizer:
            _warned_no_authorizer = True
            _logger.warning(
                "No Authorizer is registered: every permission is denied. Start a policy "
                "bundle, or instantiate the allow-all authorizer if that is really wanted"
            )


# ------------------------------------------------------------------------------


@BundleActivator
class Activator(ActivatorProto):
    """
    Publishes the authorization service and the bundle context the pipeline uses
    """

    def __init__(self) -> None:
        self.__registration: ServiceRegistration[Authorization] | None = None

    def start(self, context: "BundleContext") -> None:
        """
        Bundle started: publish the facade and fill the single decorator slot
        """
        global _context, _throttle
        _context = context
        _throttle = _make_throttle(context)

        authorization = _AuthorizationImpl()
        self.__registration = context.register_service(Authorization, authorization, {})
        set_authorization(authorization)

    def stop(self, context: "BundleContext") -> None:
        """
        Bundle stopped: from here on, @AllowPermission denies
        """
        global _context, _throttle

        set_authorization(None)
        if self.__registration is not None:
            self.__registration.unregister()
            self.__registration = None

        _context = None
        _throttle = None
