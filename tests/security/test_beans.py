#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the identity beans of the Pelix security package: Subject, Credentials and
Permission.

:author: Thomas Calmant
"""

import unittest
from types import MappingProxyType

from pelix.security import (
    ANONYMOUS,
    Credentials,
    Decision,
    Permission,
    Subject,
    UsernamePassword,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class SubjectTest(unittest.TestCase):
    """
    Tests the Subject bean
    """

    def test_defaults(self) -> None:
        """
        A bare subject is anonymous-shaped: no group, no role, not authenticated
        """
        subject = Subject("bob")
        self.assertEqual(subject.name, "bob")
        self.assertEqual(subject.groups, frozenset())
        self.assertEqual(subject.roles, frozenset())
        self.assertEqual(dict(subject.attributes), {})
        self.assertFalse(subject.authenticated)
        self.assertIsNone(subject.method)

    def test_anonymous_is_not_authenticated(self) -> None:
        """
        The shared anonymous subject must never pass an authentication check
        """
        self.assertEqual(ANONYMOUS.name, "anonymous")
        self.assertFalse(ANONYMOUS.authenticated)

    def test_groups_and_roles_are_frozen(self) -> None:
        """
        Any iterable is accepted and stored as a frozenset, so a caller cannot keep a
        mutable reference to the collections of a frozen bean
        """
        # Deliberately untyped input: the declared type is frozenset, and the
        # coercion is what keeps the bean hashable when a caller ignores that
        groups = ["dev", "ops"]
        subject = Subject("bob", groups, ("admin",))  # ty: ignore[invalid-argument-type]

        self.assertIsInstance(subject.groups, frozenset)
        self.assertIsInstance(subject.roles, frozenset)
        self.assertEqual(subject.groups, {"dev", "ops"})
        self.assertEqual(subject.roles, {"admin"})

        groups.append("root")
        self.assertEqual(subject.groups, {"dev", "ops"})

    def test_attributes_are_a_read_only_copy(self) -> None:
        """
        frozen=True is not immutability: the caller may still hold the mapping it gave
        """
        attributes = {"claim": "value"}
        subject = Subject("bob", attributes=attributes)

        self.assertIsInstance(subject.attributes, MappingProxyType)

        attributes["claim"] = "other"
        attributes["added"] = "later"
        self.assertEqual(dict(subject.attributes), {"claim": "value"})

    def test_attributes_cannot_be_written(self) -> None:
        """
        The proxy refuses a write, rather than accepting one nobody else would see
        """
        subject = Subject("bob", attributes={"claim": "value"})
        with self.assertRaises(TypeError):
            subject.attributes["claim"] = "other"  # ty: ignore[invalid-assignment]

    def test_a_subject_is_hashable(self) -> None:
        """
        Which is what compare=False on the unhashable attributes buys
        """
        subject = Subject("bob", frozenset({"dev"}), frozenset({"admin"}), {"claim": "value"})
        self.assertEqual({subject: 1}[subject], 1)
        self.assertIn(subject, {subject})

    def test_attributes_are_out_of_the_comparison(self) -> None:
        """
        The cost of compare=False, stated as a test: two subjects differing only in
        their attributes are equal, so a session-aware cache keys on the session
        identifier rather than on the subject
        """
        first = Subject("bob", attributes={"pelix.security.session.id": "one"})
        second = Subject("bob", attributes={"pelix.security.session.id": "two"})

        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))

    def test_repr_names_the_attribute_keys_only(self) -> None:
        """
        The attributes hold raw claims and session handles, so the representation names
        the keys and never their values
        """
        text = repr(Subject("bob", attributes={"id_token": "eyJ-secret", "sub": "1234"}))

        self.assertIn("attributes=[id_token, sub]", text)
        self.assertNotIn("eyJ-secret", text)
        self.assertNotIn("1234", text)

    def test_repr_shows_the_rest(self) -> None:
        """
        Everything but the attribute values stays visible: the bean must remain
        debuggable
        """
        subject = Subject("bob", frozenset({"dev"}), frozenset({"admin"}), authenticated=True, method="basic")
        text = repr(subject)

        self.assertIn("name='bob'", text)
        self.assertIn("groups=['dev']", text)
        self.assertIn("roles=['admin']", text)
        self.assertIn("authenticated=True", text)
        self.assertIn("method='basic'", text)

    def test_names_are_compared_exactly(self) -> None:
        """
        No folding, anywhere: two spellings are two identities
        """
        self.assertNotEqual(Subject("Bob"), Subject("bob"))
        self.assertNotIn("dev", Subject("bob", frozenset({"Dev"})).groups)
        self.assertNotIn("admin", Subject("bob", roles=frozenset({"Admin"})).roles)


class CredentialsTest(unittest.TestCase):
    """
    Tests the credential beans
    """

    def test_kinds(self) -> None:
        """
        The kind is what an Authenticator is selected on, so it is read off the object
        """
        self.assertEqual(Credentials.KIND, "unknown")
        self.assertEqual(UsernamePassword.KIND, "password")
        self.assertEqual(UsernamePassword("bob", "hunter2").KIND, "password")

    def test_the_password_is_not_printed(self) -> None:
        """
        The generated representation lands in the first log line or traceback which
        touches the bean
        """
        text = repr(UsernamePassword("bob", "hunter2"))

        self.assertIn("bob", text)
        self.assertNotIn("hunter2", text)

    def test_the_password_is_still_readable(self) -> None:
        """
        repr=False hides the field, it does not remove it
        """
        self.assertEqual(UsernamePassword("bob", "hunter2").password, "hunter2")


class PermissionParseTest(unittest.TestCase):
    """
    Tests the parsing of a permission specification
    """

    def test_action_only(self) -> None:
        permission = Permission.parse("jobs.submit")
        self.assertEqual(permission.action, "jobs.submit")
        self.assertIsNone(permission.resource)

    def test_action_and_resource(self) -> None:
        permission = Permission.parse("jobs.submit:queue-a")
        self.assertEqual(permission.action, "jobs.submit")
        self.assertEqual(permission.resource, "queue-a")

    def test_empty_resource_is_not_absent(self) -> None:
        """
        A trailing separator names an empty resource, which matches nothing but itself.
        The distinction matters: an absent resource is the unscoped grant
        """
        permission = Permission.parse("jobs.submit:")
        self.assertEqual(permission.resource, "")

    def test_empty_action_is_refused(self) -> None:
        for spec in ("", ":queue-a"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                Permission.parse(spec)

    def test_str_is_the_parsed_form(self) -> None:
        for spec in ("jobs.submit", "jobs.submit:queue-a", "*"):
            with self.subTest(spec=spec):
                self.assertEqual(str(Permission.parse(spec)), spec)


class PermissionImpliesTest(unittest.TestCase):
    """
    Tests the matching rule of a permission: three action forms, four resource cases,
    and both halves must match
    """

    def test_exact_action(self) -> None:
        grant = Permission("jobs.submit")

        self.assertTrue(grant.implies(Permission("jobs.submit")))
        for action in ("jobs", "jobs.submitted", "jobs.submit.now", "Jobs.submit", "config.write"):
            with self.subTest(action=action):
                self.assertFalse(grant.implies(Permission(action)))

    def test_prefix_action(self) -> None:
        grant = Permission("jobs.*")

        for action in ("jobs.submit", "jobs.queue.drain", "jobs."):
            with self.subTest(action=action):
                self.assertTrue(grant.implies(Permission(action)))

        # "jobs.*" does not cover "jobs" itself, and does not leak into a sibling prefix
        for action in ("jobs", "jobsx.submit", "Jobs.submit"):
            with self.subTest(action=action):
                self.assertFalse(grant.implies(Permission(action)))

    def test_the_single_all_grant_form(self) -> None:
        grant = Permission("*")

        for action in ("jobs", "jobs.submit", "config.write.everything"):
            with self.subTest(action=action):
                self.assertTrue(grant.implies(Permission(action)))

    def test_unscoped_grant_matches_any_resource(self) -> None:
        grant = Permission("jobs.submit")

        self.assertTrue(grant.implies(Permission("jobs.submit")))
        self.assertTrue(grant.implies(Permission("jobs.submit", "queue-a")))

    def test_wildcard_resource_matches_any_resource(self) -> None:
        grant = Permission("jobs.submit", "*")

        self.assertTrue(grant.implies(Permission("jobs.submit")))
        self.assertTrue(grant.implies(Permission("jobs.submit", "queue-a")))

    def test_scoped_grant_matches_that_resource_only(self) -> None:
        grant = Permission("jobs.submit", "queue-a")

        self.assertTrue(grant.implies(Permission("jobs.submit", "queue-a")))
        self.assertFalse(grant.implies(Permission("jobs.submit", "queue-b")))
        self.assertFalse(grant.implies(Permission("jobs.submit", "Queue-a")))

    def test_scoped_grant_does_not_satisfy_an_unscoped_request(self) -> None:
        """
        The safe direction, and the one a method-level declaration relies on: a
        per-queue grant does not satisfy a plain "jobs.submit"
        """
        self.assertFalse(Permission("jobs.submit", "queue-a").implies(Permission("jobs.submit")))

    def test_both_halves_must_match(self) -> None:
        self.assertFalse(Permission("jobs.*", "queue-a").implies(Permission("config.write", "queue-a")))
        self.assertFalse(Permission("jobs.*", "queue-a").implies(Permission("jobs.submit", "queue-b")))
        self.assertTrue(Permission("jobs.*", "queue-a").implies(Permission("jobs.submit", "queue-a")))


class DecisionTest(unittest.TestCase):
    """
    Tests the decision enumeration
    """

    def test_the_three_values(self) -> None:
        """
        Three and not two: abstain is what lets independent policies compose
        """
        self.assertEqual({decision.value for decision in Decision}, {"permit", "deny", "abstain"})


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
