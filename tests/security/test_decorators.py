#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the declarative security decorators.

Every decorator reads as "allow only": any-of within one, all-of when stacked, and a
method-level declaration replaces a class-level one entirely.

:author: Thomas Calmant
"""

import asyncio
import inspect
import unittest
from typing import Any

from pelix.security import (
    ANONYMOUS,
    AccessDenied,
    AuthenticationRequired,
    Authorization,
    Permission,
    Subject,
    get_current_subject,
    run_as,
)
from pelix.security.decorators import (
    SECURITY_ATTRIBUTE,
    AllowAll,
    AllowAuthenticated,
    AllowGroup,
    AllowPermission,
    AllowRole,
    DenyAll,
    RunAs,
    set_authorization,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------

ALICE = Subject("alice", frozenset({"dev"}), frozenset({"admin"}), authenticated=True)
BOB = Subject("bob", frozenset({"ops"}), frozenset({"operator"}), authenticated=True)
UNAUTHENTICATED = Subject("carol", frozenset({"dev"}), frozenset({"admin"}))

# ------------------------------------------------------------------------------


class FakeAuthorization(Authorization):
    """
    Grants a fixed set of permission specifications, to whoever asks
    """

    def __init__(self, *granted: str) -> None:
        self.granted = [Permission.parse(spec) for spec in granted]
        self.calls: list[tuple[Permission, Subject | None]] = []

    def is_permitted(self, permission: Permission, subject: Subject | None = None) -> bool:
        self.calls.append((permission, subject))
        return any(grant.implies(permission) for grant in self.granted)

    def check_permitted(self, permission: Permission, subject: Subject | None = None) -> None:
        if not self.is_permitted(permission, subject):
            raise AccessDenied(str(permission))

    def has_role(self, role: str, subject: Subject | None = None) -> bool:
        return role in (subject or get_current_subject()).roles

    def in_group(self, group: str, subject: Subject | None = None) -> bool:
        return group in (subject or get_current_subject()).groups


def run(coroutine: Any) -> Any:
    """
    Runs a coroutine to completion, keeping the context of the caller: the whole point
    of the asynchronous wrappers is that they see the subject published around them
    """
    return asyncio.run(coroutine)


# ------------------------------------------------------------------------------


class AllowAuthenticatedTest(unittest.TestCase):
    """
    Tests @AllowAuthenticated
    """

    def setUp(self) -> None:
        @AllowAuthenticated
        def target() -> str:
            return "done"

        self.target = target

    def test_an_authenticated_subject_passes(self) -> None:
        with run_as(ALICE):
            self.assertEqual(self.target(), "done")

    def test_anonymous_is_asked_for_credentials(self) -> None:
        with self.assertRaises(AuthenticationRequired):
            self.target()

    def test_a_named_but_unauthenticated_subject_is_asked_too(self) -> None:
        """
        The flag decides, not the name: a subject carrying groups and roles it asserted
        itself is still not authenticated
        """
        with run_as(UNAUTHENTICATED), self.assertRaises(AuthenticationRequired):
            self.target()


class AllowGroupTest(unittest.TestCase):
    """
    Tests @AllowGroup
    """

    def setUp(self) -> None:
        @AllowGroup("dev", "release")
        def target() -> str:
            return "done"

        self.target = target

    def test_any_of_the_groups_is_enough(self) -> None:
        with run_as(ALICE):
            self.assertEqual(self.target(), "done")

    def test_another_group_is_denied(self) -> None:
        with run_as(BOB), self.assertRaises(AccessDenied):
            self.target()

    def test_anonymous_is_asked_for_credentials(self) -> None:
        """
        Not 403: a challenge may still help an anonymous caller
        """
        with self.assertRaises(AuthenticationRequired):
            self.target()

    def test_group_names_are_compared_exactly(self) -> None:
        with run_as(Subject("dave", frozenset({"Dev"}), authenticated=True)), self.assertRaises(AccessDenied):
            self.target()

    def test_applied_bare_it_refuses_at_import_time(self) -> None:
        """
        Written without parentheses, the decorator would bind the function as the group
        name and fail much later, with a message about __call__ arguments
        """
        with self.assertRaises(TypeError):

            @AllowGroup  # ty: ignore[invalid-argument-type]
            def target() -> None:
                pass

    def test_applied_with_no_name_it_refuses_at_import_time(self) -> None:
        with self.assertRaises(TypeError):
            AllowGroup()  # ty: ignore[missing-argument]


class AllowRoleTest(unittest.TestCase):
    """
    Tests @AllowRole
    """

    def setUp(self) -> None:
        @AllowRole("admin")
        def target() -> str:
            return "done"

        self.target = target

    def test_the_role_holder_passes(self) -> None:
        with run_as(ALICE):
            self.assertEqual(self.target(), "done")

    def test_another_role_is_denied(self) -> None:
        with run_as(BOB), self.assertRaises(AccessDenied):
            self.target()

    def test_applied_bare_it_refuses_at_import_time(self) -> None:
        with self.assertRaises(TypeError):

            @AllowRole  # ty: ignore[invalid-argument-type]
            def target() -> None:
                pass


class AllowAllAndDenyAllTest(unittest.TestCase):
    """
    Tests the two extremes
    """

    def test_allow_all_narrows_nothing(self) -> None:
        @AllowAll
        def target() -> str:
            return "done"

        self.assertEqual(target(), "done")
        with run_as(ALICE):
            self.assertEqual(target(), "done")

    def test_allow_all_returns_the_target_itself(self) -> None:
        """
        There is nothing to check, so there is nothing to wrap: only the mark matters
        """

        def original() -> None:
            pass

        self.assertIs(AllowAll(original), original)

    def test_deny_all_denies_everyone(self) -> None:
        @DenyAll
        def target() -> None:
            pass

        with run_as(ALICE), self.assertRaises(AccessDenied):
            target()

    def test_deny_all_denies_anonymous_with_no_challenge(self) -> None:
        """
        AccessDenied and not AuthenticationRequired: no credential would help, so
        offering a challenge would be a lie
        """

        @DenyAll
        def target() -> None:
            pass

        with self.assertRaises(AccessDenied):
            target()


class AllowPermissionTest(unittest.TestCase):
    """
    Tests @AllowPermission, the only decorator which needs a service
    """

    def setUp(self) -> None:
        self.authorization = FakeAuthorization("jobs.*")
        set_authorization(self.authorization)
        self.addCleanup(set_authorization, None)

        @AllowPermission("jobs.submit")
        def target() -> str:
            return "done"

        self.target = target

    def test_a_granted_permission_passes(self) -> None:
        with run_as(ALICE):
            self.assertEqual(self.target(), "done")

    def test_the_current_subject_is_the_one_checked(self) -> None:
        with run_as(ALICE):
            self.target()

        self.assertEqual(self.authorization.calls[-1], (Permission("jobs.submit"), ALICE))

    def test_a_refused_permission_denies(self) -> None:
        @AllowPermission("config.write")
        def target() -> None:
            pass

        with run_as(ALICE), self.assertRaises(AccessDenied):
            target()

    def test_the_specification_is_parsed_at_decoration_time(self) -> None:
        with self.assertRaises(ValueError):

            @AllowPermission(":queue-a")
            def target() -> None:
                pass

    def test_a_scoped_permission_is_carried_through(self) -> None:
        @AllowPermission("jobs.submit:queue-a")
        def target() -> None:
            pass

        with run_as(ALICE):
            target()

        self.assertEqual(self.authorization.calls[-1][0], Permission("jobs.submit", "queue-a"))


class FailClosedTest(unittest.TestCase):
    """
    With no authorization service published, @AllowPermission denies. The other
    decorators keep working: they are pure context-variable operations
    """

    def setUp(self) -> None:
        set_authorization(None)

    def test_allow_permission_denies(self) -> None:
        @AllowPermission("jobs.submit")
        def target() -> None:
            pass

        with run_as(ALICE), self.assertRaises(AccessDenied):
            target()

    def test_the_denial_is_reported_once_per_permission(self) -> None:
        """
        One warning per distinct permission, not one per call
        """

        @AllowPermission("reported.once")
        def target() -> None:
            pass

        with (
            run_as(ALICE),
            self.assertLogs("pelix.security.decorators", "WARNING") as logs,
        ):
            for _ in range(3):
                with self.assertRaises(AccessDenied):
                    target()

            # Nothing else would be logged, so provoke a second, different warning
            @AllowPermission("reported.too")
            def other() -> None:
                pass

            with self.assertRaises(AccessDenied):
                other()

        self.assertEqual(len(logs.output), 2)
        self.assertIn("reported.once", logs.output[0])
        self.assertIn("reported.too", logs.output[1])

    def test_the_other_decorators_still_work(self) -> None:
        @AllowRole("admin")
        def allowed() -> str:
            return "done"

        @AllowGroup("nobody")
        def refused() -> None:
            pass

        with run_as(ALICE):
            self.assertEqual(allowed(), "done")
            with self.assertRaises(AccessDenied):
                refused()


class RunAsTest(unittest.TestCase):
    """
    Tests @RunAs
    """

    def test_the_body_runs_under_the_declared_identity(self) -> None:
        @RunAs(BOB)
        def target() -> Subject:
            return get_current_subject()

        self.assertEqual(target(), BOB)

    def test_the_identity_is_taken_back_afterwards(self) -> None:
        @RunAs(BOB)
        def target() -> None:
            pass

        with run_as(ALICE):
            target()
            self.assertEqual(get_current_subject(), ALICE)

        self.assertIs(get_current_subject(), ANONYMOUS)

    def test_it_composes_with_a_check(self) -> None:
        """
        Stacked below @AllowRole, the check sees the caller and the body sees the
        assumed identity: the order of the two decorators is what says which
        """

        @AllowRole("admin")
        @RunAs(BOB)
        def target() -> Subject:
            return get_current_subject()

        with run_as(ALICE):
            self.assertEqual(target(), BOB)

        with run_as(BOB), self.assertRaises(AccessDenied):
            target()


class AsyncFlavourTest(unittest.TestCase):
    """
    A synchronous wrapper around a coroutine function checks and restores the context
    before the body ever runs, which turns @RunAs into a no-op looking correct. Both
    flavours therefore ship from day one
    """

    def test_run_as_reaches_the_coroutine_body(self) -> None:
        @RunAs(BOB)
        async def target() -> Subject:
            return get_current_subject()

        self.assertEqual(run(target()), BOB)

    def test_a_check_runs_before_the_coroutine_body(self) -> None:
        calls: list[str] = []

        @AllowRole("admin")
        async def target() -> None:
            calls.append("body")

        async def main() -> None:
            with run_as(BOB), self.assertRaises(AccessDenied):
                await target()

            with run_as(ALICE):
                await target()

        run(main())
        self.assertEqual(calls, ["body"])

    def test_the_wrapper_stays_a_coroutine_function(self) -> None:
        @AllowRole("admin")
        async def target() -> None:
            pass

        self.assertTrue(inspect.iscoroutinefunction(target))


class StackingTest(unittest.TestCase):
    """
    Any-of within one decorator, all-of when stacked
    """

    def setUp(self) -> None:
        @AllowGroup("dev")
        @AllowRole("admin")
        def target() -> str:
            return "done"

        self.target = target

    def test_both_must_be_satisfied(self) -> None:
        with run_as(ALICE):
            self.assertEqual(self.target(), "done")

    def test_one_of_the_two_is_not_enough(self) -> None:
        for subject in (
            Subject("dave", frozenset({"dev"}), authenticated=True),
            Subject("erin", roles=frozenset({"admin"}), authenticated=True),
        ):
            with self.subTest(subject=subject.name), run_as(subject), self.assertRaises(AccessDenied):
                self.target()

    def test_both_declarations_are_recorded(self) -> None:
        """
        The shell must be able to answer "what does this method require" without
        invoking anything
        """
        kinds = [declaration.kind for declaration in getattr(self.target, SECURITY_ATTRIBUTE)]
        self.assertEqual(kinds, ["AllowRole", "AllowGroup"])


class ClassScopeTest(unittest.TestCase):
    """
    A class-level decorator sets the default of the class body
    """

    def test_it_applies_to_the_public_methods_of_the_body(self) -> None:
        @AllowRole("admin")
        class Service:
            def public(self) -> str:
                return "done"

        with run_as(ALICE):
            self.assertEqual(Service().public(), "done")

        with run_as(BOB), self.assertRaises(AccessDenied):
            Service().public()

    def test_it_leaves_the_underscore_names_alone(self) -> None:
        """
        Without that rule a class-level @DenyAll would wrap __init__ and present as a
        construction error rather than an authorization one
        """

        @DenyAll
        class Service:
            def __init__(self) -> None:
                self.built = True

            def _helper(self) -> str:
                return "helper"

            def public(self) -> None:
                pass

        service = Service()
        self.assertTrue(service.built)
        self.assertEqual(service._helper(), "helper")
        with self.assertRaises(AccessDenied):
            service.public()

    def test_a_method_declaration_replaces_the_class_default(self) -> None:
        @DenyAll
        class Service:
            @AllowRole("operator")
            def narrowed(self) -> str:
                return "narrowed"

            def denied(self) -> None:
                pass

        with run_as(BOB):
            self.assertEqual(Service().narrowed(), "narrowed")
            with self.assertRaises(AccessDenied):
                Service().denied()

    def test_allow_all_overrides_the_class_default(self) -> None:
        @DenyAll
        class Service:
            @AllowAll
            def open(self) -> str:
                return "open"

        self.assertEqual(Service().open(), "open")

    def test_it_does_not_reach_the_inherited_methods(self) -> None:
        class Base:
            def inherited(self) -> str:
                return "inherited"

        @DenyAll
        class Service(Base):
            def own(self) -> None:
                pass

        self.assertEqual(Service().inherited(), "inherited")
        with self.assertRaises(AccessDenied):
            Service().own()

    def test_a_subclass_does_not_rewrite_its_parent(self) -> None:
        """
        functools.wraps copies __dict__ entries by reference, so a declaration list
        appended in place would be shared. It is built fresh instead
        """

        class Base:
            @AllowRole("admin")
            def method(self) -> str:
                return "base"

        @AllowRole("operator")
        class Child(Base):
            def method(self) -> str:
                return "child"

        with run_as(ALICE):
            self.assertEqual(Base().method(), "base")
            with self.assertRaises(AccessDenied):
                Child().method()

        with run_as(BOB):
            self.assertEqual(Child().method(), "child")
            with self.assertRaises(AccessDenied):
                Base().method()


class MarkerTest(unittest.TestCase):
    """
    The mark is what a class default and the shell read, rather than the wrapper
    """

    def test_an_undecorated_callable_carries_nothing(self) -> None:
        def target() -> None:
            pass

        self.assertFalse(hasattr(target, SECURITY_ATTRIBUTE))

    def test_the_declaration_names_what_was_asked(self) -> None:
        @AllowGroup("dev", "ops")
        def target() -> None:
            pass

        declarations = getattr(target, SECURITY_ATTRIBUTE)
        self.assertEqual(len(declarations), 1)
        self.assertEqual(declarations[0].kind, "AllowGroup")
        self.assertEqual(declarations[0].values, ("dev", "ops"))
        self.assertEqual(repr(declarations[0]), "AllowGroup('dev', 'ops')")

    def test_allow_all_marks_without_declaring(self) -> None:
        @AllowAll
        def target() -> None:
            pass

        self.assertEqual(getattr(target, SECURITY_ATTRIBUTE), [])

    def test_the_wrapper_keeps_the_identity_of_its_target(self) -> None:
        @AllowRole("admin")
        def named_target() -> None:
            """A docstring"""

        self.assertEqual(named_target.__name__, "named_target")
        self.assertEqual(named_target.__doc__, "A docstring")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
