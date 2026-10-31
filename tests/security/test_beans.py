#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the identity beans of the Pelix security package: Subject, Credentials,
Permission and Secret.

:author: Thomas Calmant
"""

import copy
import json
import pickle
import sys
import unittest
from types import MappingProxyType
from typing import Any

from pelix.security import (
    ANONYMOUS,
    AUDIT_SECRET_REVEAL,
    Credentials,
    Decision,
    Permission,
    Secret,
    Subject,
    UsernamePassword,
    to_secret,
)

# Reveals seen by the audit hook. Audit hooks can't be removed, so a single one is
# installed for the whole test process and only records the events
REVEALS: list[tuple[Any, ...]] = []


def _record_reveal(event: str, args: tuple[Any, ...]) -> None:
    if event == AUDIT_SECRET_REVEAL:
        REVEALS.append(args)


sys.addaudithook(_record_reveal)

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
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
        subject = Subject("bob", groups, ("admin",))

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
            subject.attributes["claim"] = "other"

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


class SecretTest(unittest.TestCase):
    """
    Tests the Secret value type
    """

    def test_the_value_is_masked(self) -> None:
        """
        Every way of making text from a secret gives the mask, never the value
        """
        for value in ("hunter2", b"hunter2"):
            secret = Secret(value, "owner")
            for name, text in (
                ("repr", repr(secret)),
                ("str", str(secret)),
                ("format", f"{secret:>20}"),
                # What logging does with its arguments
                ("percent", "%s" % secret),  # noqa: UP031
                ("container", repr([secret, {"key": secret}])),
            ):
                with self.subTest(value=value, how=name):
                    self.assertNotIn("hunter2", text)
                    self.assertIn("***", text)

    def test_reveal_raises_the_audit_event(self) -> None:
        """
        The audit event carries the owner and the module which revealed the secret
        """
        for value, owner in (("hunter2", "component"), (b"hunter2", None)):
            with self.subTest(value=value, owner=owner):
                del REVEALS[:]
                self.assertEqual(Secret(value, owner).reveal(), value)
                self.assertEqual(REVEALS, [(owner, __name__)])

    def test_masking_does_not_reveal(self) -> None:
        """
        Comparing, hashing and checking a secret raise no reveal event
        """
        del REVEALS[:]
        secret = Secret("hunter2")
        (
            repr(secret),
            hash(secret),
            bool(secret),
            len(secret),
            secret == Secret("hunter2"),
            secret == "hunter2",
        )
        self.assertEqual(REVEALS, [])

    def test_equality(self) -> None:
        """
        Secrets are compared on their value and its type, never on their owner, and
        never equal to a plain value; equal secrets hash alike, but not like the value
        """
        for value, other, expected in (
            ("hunter2", Secret("hunter2", "other owner"), True),
            ("hunter2", Secret("hunter3"), False),
            ("hunter2", Secret("hunter"), False),
            ("hunter2", Secret(b"hunter2"), False),
            ("hunter2", Secret(1234), False),
            # Non-ASCII values are compared on their UTF-8 form
            ("pâte", Secret("pâte"), True),
            (b"hunter2", Secret(b"hunter2"), True),
            (1234, Secret(1234), True),
            (1234, Secret(4321), False),
            ((1, "a"), Secret((1, "a")), True),
            ({"a": 1}, Secret({"a": 1}), True),
            ("hunter2", "hunter2", False),
            (b"hunter2", b"hunter2", False),
            (1234, 1234, False),
            ("hunter2", None, False),
        ):
            with self.subTest(value=value, other=other):
                secret = Secret(value, "owner")
                self.assertEqual(secret == other, expected)
                self.assertEqual(other == secret, expected)
                self.assertEqual(secret != other, not expected)
                if isinstance(other, Secret) and expected and not isinstance(value, dict):
                    self.assertEqual(hash(secret), hash(other))
                if not isinstance(value, dict):
                    self.assertNotEqual(hash(secret), hash(value))

        self.assertNotIn("x", {Secret("x"): 1})
        self.assertNotEqual({"key": Secret("x")}, {"key": "x"})
        with self.assertRaises(TypeError):
            hash(Secret({"a": 1}))

    def test_equals(self) -> None:
        """
        equals() compares with a plain value and raises the reveal audit event
        """
        for value, plain, expected in (
            ("hunter2", "hunter2", True),
            ("hunter2", "hunter3", False),
            ("hunter2", b"hunter2", False),
            ("pâte", "pâte", True),
            (b"hunter2", b"hunter2", True),
            (1234, 1234, True),
            (1234, "1234", False),
            ({"a": 1}, {"a": 1}, True),
            ("hunter2", None, False),
        ):
            with self.subTest(value=value, plain=plain):
                del REVEALS[:]
                self.assertEqual(Secret(value, "owner").equals(plain), expected)
                self.assertEqual(REVEALS, [("owner", __name__)])

    def test_bool_and_len(self) -> None:
        """
        Whether a secret is set and its length are not confidential
        """
        for value, expected in (("", 0), ("hunter2", 7), (b"", 0), (b"ab", 2), ({}, 0), ([1, 2], 2)):
            with self.subTest(value=value):
                self.assertEqual(len(Secret(value)), expected)
                self.assertEqual(bool(Secret(value)), bool(expected))

        # The truth of the value, even without a length
        self.assertFalse(Secret(0))
        with self.assertRaises(TypeError):
            len(Secret(1234))

    def test_no_persistence(self) -> None:
        """
        Pickle and JSON refuse a secret, copies return the same object
        """
        secret = Secret("hunter2", "owner")
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(protocol=protocol), self.assertRaises(TypeError):
                pickle.dumps(secret, protocol)

        with self.assertRaises(TypeError):
            json.dumps(secret)

        self.assertIs(copy.copy(secret), secret)
        self.assertIs(copy.deepcopy({"a": secret})["a"], secret)

    def test_immutable(self) -> None:
        """
        A secret can't be modified, nor given new attributes
        """
        secret = Secret("hunter2", "owner")
        for name in ("owner", "_Secret__value", "other"):
            with self.subTest(name=name):
                with self.assertRaises(AttributeError):
                    setattr(secret, name, "x")
                with self.assertRaises(AttributeError):
                    delattr(secret, name)

        self.assertEqual(secret.owner, "owner")

    def test_any_value(self) -> None:
        """
        A secret wraps any value, masked the same way, but not another secret
        """
        for value in (None, 1234, bytearray(b"hunter2"), {"user": "hunter2"}, ["hunter2"]):
            with self.subTest(value=value):
                secret = Secret(value, "owner")
                self.assertEqual(str(secret), "***")
                self.assertNotIn("hunter2", repr([secret]))
                self.assertIs(secret.reveal(), value)

        with self.assertRaises(TypeError):
            Secret(Secret("x"))

    def test_to_secret(self) -> None:
        """
        to_secret() wraps plain values and keeps existing secrets and their owner
        """
        existing = Secret("x", "first")
        self.assertIs(to_secret(existing, "second"), existing)
        self.assertIsNone(to_secret(None, "owner"))

        wrapped = to_secret("x", "owner")
        assert wrapped is not None
        self.assertEqual(wrapped, existing)
        self.assertEqual(wrapped.owner, "owner")
