#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the identity pipeline and the authorization facade of the security core.

:author: Thomas Calmant
"""

import importlib
import unittest
from collections.abc import Iterable
from typing import Any

import pelix.framework
from pelix.constants import SERVICE_RANKING
from pelix.security import (
    ANONYMOUS,
    PROP_CREDENTIAL_KINDS,
    AccessDenied,
    AuthenticationFailed,
    Authenticator,
    Authorization,
    Authorizer,
    Credentials,
    Decision,
    MembershipProvider,
    Permission,
    Subject,
    UsernamePassword,
    run_as,
    use_authorization,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class FakeAuthenticator(Authenticator):
    """
    Knows a fixed set of user names and passwords
    """

    def __init__(self, users: dict[str, str]) -> None:
        self.users = users
        self.calls: list[str] = []

    def authenticate(self, credentials: Credentials) -> Subject | None:
        assert isinstance(credentials, UsernamePassword)
        self.calls.append(credentials.username)

        try:
            expected = self.users[credentials.username]
        except KeyError:
            # Unknown user: abstain, so that a lower-ranked store may still answer
            return None

        if expected != credentials.password:
            # Known user, wrong password: stop the loop, or the next store becomes an
            # oracle for the credentials this one just rejected
            raise AuthenticationFailed(credentials.username)

        return Subject(credentials.username)


class FakeGroups(MembershipProvider):
    """
    Contributes groups, from a fixed table
    """

    def __init__(self, groups: dict[str, set[str]]) -> None:
        self.groups = groups
        self.seen_by_get_roles: list[Subject] = []

    def get_groups(self, subject: Subject) -> Iterable[str]:
        return self.groups.get(subject.name, set())

    def get_roles(self, subject: Subject) -> Iterable[str]:
        self.seen_by_get_roles.append(subject)
        return ()


class FakeRolesFromGroups(MembershipProvider):
    """
    Contributes roles derived from the groups another provider asserted
    """

    def __init__(self, roles: dict[str, set[str]]) -> None:
        self.roles = roles

    def get_groups(self, subject: Subject) -> Iterable[str]:
        return ()

    def get_roles(self, subject: Subject) -> Iterable[str]:
        granted: set[str] = set()
        for group in subject.groups:
            granted.update(self.roles.get(group, set()))

        return granted


class FakeAuthorizer(Authorizer):
    """
    Answers a fixed decision, whatever it is asked
    """

    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        self.calls: list[Permission] = []

    def is_permitted(self, subject: Subject, permission: Permission) -> Decision:
        self.calls.append(permission)
        return self.decision


class BrokenAuthorizer(Authorizer):
    """
    Raises rather than deciding
    """

    def is_permitted(self, subject: Subject, permission: Permission) -> Decision:
        raise RuntimeError("the policy backend is down")


# ------------------------------------------------------------------------------


def live_core() -> Any:
    """
    Returns the pelix.security.core module the running framework loaded.

    Uninstalling a bundle drops its module from ``sys.modules`` to force a complete
    reload if it is re-installed, so a reference taken when this test module was
    imported would go stale after the first framework is deleted.

    Typed as Any rather than ModuleType, so that a test may reach the module-level
    state it has to reset between runs.

    :return: The module currently backing the bundle
    """
    return importlib.import_module("pelix.security.core")


class CoreTestCase(unittest.TestCase):
    """
    Common framework fixture: the security core bundle, and nothing else
    """

    framework: pelix.framework.Framework

    def setUp(self) -> None:
        self.framework = pelix.framework.create_framework(("pelix.security.core",))
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()
        self.core = live_core()

        # The "warn once" state is module-level, so a test which expects a warning must
        # not depend on which tests ran before it
        self.core._warned_kinds.clear()
        self.core._warned_no_authorizer = False

    def register(self, specification: Any, service: Any, ranking: int = 0, **properties: Any) -> Any:
        """
        Registers a service at a chosen ranking

        :param specification: The specification to register under
        :param service: The service object
        :param ranking: Its service.ranking
        :param properties: Other service properties
        :return: The service registration
        """
        return self.context.register_service(specification, service, {SERVICE_RANKING: ranking, **properties})

    def register_authenticator(self, users: dict[str, str], ranking: int = 0) -> FakeAuthenticator:
        authenticator = FakeAuthenticator(users)
        self.register(Authenticator, authenticator, ranking, **{PROP_CREDENTIAL_KINDS: ("password",)})
        return authenticator


class AuthenticateTest(CoreTestCase):
    """
    Tests the authentication half of the pipeline
    """

    def test_a_good_password_gives_an_authenticated_subject(self) -> None:
        self.register_authenticator({"alice": "good"})

        subject = self.core.authenticate(UsernamePassword("alice", "good"))

        self.assertEqual(subject.name, "alice")
        self.assertTrue(subject.authenticated)

    def test_the_pipeline_owns_the_authenticated_flag(self) -> None:
        """
        An authenticator is responsible for the name only: one which forgets the flag
        cannot produce a subject which passes nothing
        """
        self.register_authenticator({"alice": "good"})

        self.assertTrue(self.core.authenticate(UsernamePassword("alice", "good")).authenticated)

    def test_the_method_is_left_to_the_transport(self) -> None:
        """
        It names the mechanism, which is what a transport-neutral pipeline cannot know
        """
        self.register_authenticator({"alice": "good"})

        self.assertIsNone(self.core.authenticate(UsernamePassword("alice", "good")).method)

    def test_a_wrong_password_is_refused(self) -> None:
        self.register_authenticator({"alice": "good"})

        with self.assertRaises(AuthenticationFailed):
            self.core.authenticate(UsernamePassword("alice", "wrong"))

    def test_no_authenticator_refuses_rather_than_answering_anonymous(self) -> None:
        """
        A caller which presented credentials and got back an unauthenticated subject
        cannot tell that apart from a wrong password, and the two need different
        diagnostics
        """
        with self.assertRaises(AuthenticationFailed), self.assertLogs(self.core.__name__, "WARNING"):
            self.core.authenticate(UsernamePassword("alice", "good"))

    def test_an_authenticator_not_declaring_its_kinds_is_reported(self) -> None:
        """
        The kind property is mandatory, so the likely cause is a store which forgot it
        rather than one which is absent. The message has to say which
        """
        self.register(Authenticator, FakeAuthenticator({"alice": "good"}))

        with self.assertRaises(AuthenticationFailed), self.assertLogs(self.core.__name__, "WARNING") as logs:
            self.core.authenticate(UsernamePassword("alice", "good"))

        self.assertIn(PROP_CREDENTIAL_KINDS, logs.output[0])

    def test_an_unknown_user_falls_through_to_the_next_store(self) -> None:
        """
        Returning None abstains, which is what lets several stores compose
        """
        first = self.register_authenticator({"alice": "good"}, ranking=10)
        second = self.register_authenticator({"bob": "good"}, ranking=0)

        subject = self.core.authenticate(UsernamePassword("bob", "good"))

        self.assertEqual(subject.name, "bob")
        self.assertEqual(first.calls, ["bob"])
        self.assertEqual(second.calls, ["bob"])

    def test_a_rejection_stops_the_loop(self) -> None:
        """
        The heart of the three-state contract. Without it, an emergency store holding an
        old password for a user the main store already rejected keeps working forever:
        a credential oracle the loop itself creates
        """
        main = self.register_authenticator({"alice": "good"}, ranking=10)
        emergency = self.register_authenticator({"alice": "old-password"}, ranking=0)

        with self.assertRaises(AuthenticationFailed):
            self.core.authenticate(UsernamePassword("alice", "old-password"))

        self.assertEqual(main.calls, ["alice"])
        self.assertEqual(emergency.calls, [], "The lower-ranked store must not be consulted")

    def test_the_stores_are_consulted_in_ranking_order(self) -> None:
        low = self.register_authenticator({"alice": "low"}, ranking=0)
        high = self.register_authenticator({"alice": "high"}, ranking=10)

        subject = self.core.authenticate(UsernamePassword("alice", "high"))

        self.assertEqual(subject.name, "alice")
        self.assertEqual(high.calls, ["alice"])
        self.assertEqual(low.calls, [])

    def test_a_store_registered_later_is_still_ranked(self) -> None:
        """
        The registry is queried on every call rather than injected once, because an
        aggregate injection appends what arrives later instead of ordering it
        """
        self.register_authenticator({"alice": "low"}, ranking=0)
        high = self.register_authenticator({"alice": "high"}, ranking=10)

        self.core.authenticate(UsernamePassword("alice", "high"))
        self.assertEqual(high.calls, ["alice"])


class MembershipTest(CoreTestCase):
    """
    Tests the two membership passes
    """

    def setUp(self) -> None:
        super().setUp()
        self.register_authenticator({"alice": "good"})

    def test_groups_are_unioned(self) -> None:
        self.register(MembershipProvider, FakeGroups({"alice": {"dev"}}))
        self.register(MembershipProvider, FakeGroups({"alice": {"ops"}}))

        subject = self.core.authenticate(UsernamePassword("alice", "good"))
        self.assertEqual(subject.groups, {"dev", "ops"})

    def test_roles_are_unioned(self) -> None:
        self.register(MembershipProvider, FakeRolesFromGroups({"dev": {"admin"}}))
        self.register(MembershipProvider, FakeGroups({"alice": {"dev"}}))

        subject = self.core.authenticate(UsernamePassword("alice", "good"))
        self.assertEqual(subject.roles, {"admin"})

    def test_the_roles_pass_sees_the_complete_groups(self) -> None:
        """
        This is what the two passes buy, and it is the step a single pass would silently
        lose: the provider granting roles is registered *first*, so with one pass it
        would look at a subject whose groups are still empty and answer nothing
        """
        self.register(MembershipProvider, FakeRolesFromGroups({"dev": {"admin"}}), ranking=100)
        self.register(MembershipProvider, FakeGroups({"alice": {"dev"}}), ranking=0)

        subject = self.core.authenticate(UsernamePassword("alice", "good"))

        self.assertEqual(subject.groups, {"dev"})
        self.assertEqual(subject.roles, {"admin"})

    def test_the_groups_pass_sees_no_role(self) -> None:
        """
        Stated the other way round: derivation goes one way only, and get_groups() must
        not look at subject.roles, which is empty there by construction
        """
        groups = FakeGroups({"alice": {"dev"}})
        self.register(MembershipProvider, groups)
        self.register(MembershipProvider, FakeRolesFromGroups({"dev": {"admin"}}))

        self.core.authenticate(UsernamePassword("alice", "good"))

        self.assertEqual(len(groups.seen_by_get_roles), 1)
        self.assertEqual(groups.seen_by_get_roles[0].groups, {"dev"})
        self.assertEqual(groups.seen_by_get_roles[0].roles, frozenset())

    def test_names_are_taken_verbatim(self) -> None:
        """
        The union is a plain set union: the core does not transform what a provider
        returned, because only the provider knows the matching rule of its own source
        """
        self.register(MembershipProvider, FakeGroups({"alice": {"Dev-Leads"}}))

        subject = self.core.authenticate(UsernamePassword("alice", "good"))
        self.assertEqual(subject.groups, {"Dev-Leads"})

    def test_no_provider_gives_an_empty_membership(self) -> None:
        subject = self.core.authenticate(UsernamePassword("alice", "good"))

        self.assertEqual(subject.groups, frozenset())
        self.assertEqual(subject.roles, frozenset())


class AuthorizationTest(CoreTestCase):
    """
    Tests the authorization facade and its combining rule
    """

    def setUp(self) -> None:
        super().setUp()
        reference = self.context.get_service_reference(Authorization)
        assert reference is not None
        self.authorization: Authorization = self.context.get_service(reference)

    def test_the_service_is_published(self) -> None:
        with use_authorization(self.context) as authorization:
            self.assertIsNotNone(authorization)

    def test_no_authorizer_denies(self) -> None:
        """
        You cannot get permissive by accident
        """
        with self.assertLogs(self.core.__name__, "WARNING"):
            self.assertFalse(self.authorization.is_permitted(Permission("jobs.submit")))

    def test_a_permit_permits(self) -> None:
        self.register(Authorizer, FakeAuthorizer(Decision.PERMIT))
        self.assertTrue(self.authorization.is_permitted(Permission("jobs.submit")))

    def test_an_abstention_alone_denies(self) -> None:
        self.register(Authorizer, FakeAuthorizer(Decision.ABSTAIN))
        self.assertFalse(self.authorization.is_permitted(Permission("jobs.submit")))

    def test_an_abstention_lets_another_policy_decide(self) -> None:
        self.register(Authorizer, FakeAuthorizer(Decision.ABSTAIN))
        self.register(Authorizer, FakeAuthorizer(Decision.PERMIT))

        self.assertTrue(self.authorization.is_permitted(Permission("jobs.submit")))

    def test_any_deny_wins(self) -> None:
        """
        Whatever its ranking: the rule is not "the best-ranked one decides"
        """
        self.register(Authorizer, FakeAuthorizer(Decision.PERMIT), ranking=0)
        self.register(Authorizer, FakeAuthorizer(Decision.DENY), ranking=-10)

        self.assertFalse(self.authorization.is_permitted(Permission("jobs.submit")))

    def test_a_deny_wins_over_a_lower_ranked_permit(self) -> None:
        self.register(Authorizer, FakeAuthorizer(Decision.DENY), ranking=10)
        self.register(Authorizer, FakeAuthorizer(Decision.PERMIT), ranking=0)

        self.assertFalse(self.authorization.is_permitted(Permission("jobs.submit")))

    def test_a_broken_authorizer_denies(self) -> None:
        """
        An authorizer which cannot decide has not decided, and continuing would let a
        broken policy open a door
        """
        self.register(Authorizer, BrokenAuthorizer())
        self.register(Authorizer, FakeAuthorizer(Decision.PERMIT))

        with self.assertLogs(self.core.__name__, "ERROR"):
            self.assertFalse(self.authorization.is_permitted(Permission("jobs.submit")))

    def test_the_current_subject_is_used_by_default(self) -> None:
        authorizer = FakeAuthorizer(Decision.PERMIT)
        self.register(Authorizer, authorizer)

        alice = Subject("alice", authenticated=True)
        with run_as(alice):
            self.assertTrue(self.authorization.is_permitted(Permission("jobs.submit")))

    def test_check_permitted_raises(self) -> None:
        self.register(Authorizer, FakeAuthorizer(Decision.DENY))

        with self.assertRaises(AccessDenied):
            self.authorization.check_permitted(Permission("jobs.submit"))

    def test_check_permitted_returns_on_success(self) -> None:
        self.register(Authorizer, FakeAuthorizer(Decision.PERMIT))
        self.assertIsNone(self.authorization.check_permitted(Permission("jobs.submit")))

    def test_has_role_and_in_group_read_the_subject(self) -> None:
        alice = Subject("alice", frozenset({"dev"}), frozenset({"admin"}), authenticated=True)

        self.assertTrue(self.authorization.has_role("admin", alice))
        self.assertFalse(self.authorization.has_role("operator", alice))
        self.assertTrue(self.authorization.in_group("dev", alice))
        self.assertFalse(self.authorization.in_group("ops", alice))

    def test_has_role_and_in_group_compare_exactly(self) -> None:
        alice = Subject("alice", frozenset({"Dev"}), frozenset({"Admin"}), authenticated=True)

        self.assertFalse(self.authorization.has_role("admin", alice))
        self.assertFalse(self.authorization.in_group("dev", alice))

    def test_the_default_subject_is_anonymous(self) -> None:
        self.assertFalse(self.authorization.has_role("admin"))
        self.assertFalse(self.authorization.in_group("dev"))


class LifecycleTest(unittest.TestCase):
    """
    Tests what starting and stopping the bundle does to the single decorator slot
    """

    def test_the_slot_is_filled_and_cleared(self) -> None:
        from pelix.security import decorators

        self.assertIsNone(decorators._authorization)

        framework = pelix.framework.create_framework(())
        framework.start()
        try:
            bundle = framework.get_bundle_context().install_bundle("pelix.security.core")
            bundle.start()
            self.assertIsNotNone(decorators._authorization)

            bundle.stop()
            self.assertIsNone(decorators._authorization)
        finally:
            framework.delete(True)

    def test_authenticate_needs_the_bundle(self) -> None:
        """
        With the bundle stopped there is no registry to consult, so authentication
        refuses rather than answering anonymous
        """
        with self.assertRaises(AuthenticationFailed):
            live_core().authenticate(UsernamePassword("alice", "good"))


class AnonymousTest(CoreTestCase):
    """
    The anonymous subject holds nothing, so it satisfies nothing
    """

    def test_it_holds_no_role_and_no_group(self) -> None:
        reference = self.context.get_service_reference(Authorization)
        assert reference is not None
        authorization: Authorization = self.context.get_service(reference)

        self.assertFalse(authorization.has_role("admin", ANONYMOUS))
        self.assertFalse(authorization.in_group("dev", ANONYMOUS))


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
