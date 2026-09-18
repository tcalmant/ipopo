#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the audit events the security core posts through EventAdmin.

:author: Thomas Calmant
"""

import importlib
import unittest
from typing import Any

import pelix.framework
from pelix.security import (
    EVENT_PROP_AUTHENTICATED,
    EVENT_PROP_DECLARATION,
    EVENT_PROP_KIND,
    EVENT_PROP_METHOD,
    EVENT_PROP_PERMISSION,
    EVENT_PROP_REASON,
    EVENT_PROP_SOURCE,
    EVENT_PROP_USER,
    PROP_CREDENTIAL_KINDS,
    TOPIC_ACCESS_DENIED,
    TOPIC_AUTH_FAILURE,
    TOPIC_AUTH_SUCCESS,
    AccessDenied,
    AuthenticationFailed,
    AuthenticationRequired,
    Authenticator,
    Authorization,
    Authorizer,
    ClientCertificate,
    Credentials,
    Decision,
    Permission,
    Subject,
    UsernamePassword,
    run_as,
)
from pelix.security.core import Throttle
from pelix.security.decorators import AllowGroup, AllowPermission, DenyAll
from pelix.services import EventAdmin

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

SECRET = "correct horse battery staple"

# ------------------------------------------------------------------------------


class FakeEventAdmin(EventAdmin):
    """
    Records the posted events
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def send(self, topic: str, properties: dict[str, Any] | None = None) -> None:
        raise AssertionError("Audit events must be posted, not sent")

    def post(self, topic: str, properties: dict[str, Any] | None = None) -> None:
        self.events.append((topic, dict(properties or {})))

    def topics(self) -> list[str]:
        return [topic for topic, _ in self.events]


class BrokenEventAdmin(FakeEventAdmin):
    """
    Fails every post
    """

    def post(self, topic: str, properties: dict[str, Any] | None = None) -> None:
        raise RuntimeError("the event bus is down")


class FakeAuthenticator(Authenticator):
    """
    Knows alice, whose password is SECRET
    """

    def authenticate(self, credentials: Credentials) -> Subject | None:
        if not isinstance(credentials, UsernamePassword) or credentials.username != "alice":
            return None

        if credentials.password != SECRET:
            raise AuthenticationFailed("alice")

        return Subject("alice")


class FakeAuthorizer(Authorizer):
    """
    Permits jobs.read only
    """

    def is_permitted(self, subject: Subject, permission: Permission) -> Decision:
        return Decision.PERMIT if permission.action == "jobs.read" else Decision.ABSTAIN


class Guarded:
    """
    Methods refused by the decorators
    """

    @AllowGroup("dev")
    def for_devs(self) -> str:
        return "ok"

    @AllowPermission("jobs.submit")
    def submit(self) -> str:
        return "ok"

    @DenyAll
    def nobody(self) -> str:
        return "ok"


# ------------------------------------------------------------------------------


class AuditTestCase(unittest.TestCase):
    """
    The security core bundle, an authenticator, an authorizer and a fake EventAdmin
    """

    framework: pelix.framework.Framework

    def setUp(self) -> None:
        self.framework = pelix.framework.create_framework(("pelix.security.core",))
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()
        self.core: Any = importlib.import_module("pelix.security.core")

        self.context.register_service(
            Authenticator, FakeAuthenticator(), {PROP_CREDENTIAL_KINDS: ("password",)}
        )
        self.context.register_service(Authorizer, FakeAuthorizer(), {})

        self.events = FakeEventAdmin()
        self.event_admin_registration = self.context.register_service(EventAdmin, self.events, {})

    def assertNoSecret(self) -> None:
        for topic, properties in self.events.events:
            with self.subTest(topic=topic):
                self.assertNotIn(SECRET, repr(properties))


class AuthenticationEventsTest(AuditTestCase):
    """
    Tests the events of authenticate()
    """

    def test_a_success(self) -> None:
        subject = self.core.authenticate(
            UsernamePassword("alice", SECRET), "10.0.0.1", method="shell-password"
        )

        self.assertEqual(subject.method, "shell-password")
        self.assertEqual(
            self.events.events,
            [
                (
                    TOPIC_AUTH_SUCCESS,
                    {
                        EVENT_PROP_USER: "alice",
                        EVENT_PROP_KIND: "password",
                        EVENT_PROP_METHOD: "shell-password",
                        EVENT_PROP_SOURCE: "10.0.0.1",
                    },
                )
            ],
        )
        self.assertNoSecret()

    def test_the_method_is_optional(self) -> None:
        self.assertIsNone(self.core.authenticate(UsernamePassword("alice", SECRET)).method)
        self.assertIsNone(self.events.events[0][1][EVENT_PROP_METHOD])

    def test_a_wrong_password(self) -> None:
        with self.assertRaises(AuthenticationFailed):
            self.core.authenticate(UsernamePassword("alice", "wrong " + SECRET), "10.0.0.1")

        topic, properties = self.events.events[0]
        self.assertEqual(topic, TOPIC_AUTH_FAILURE)
        self.assertEqual(properties[EVENT_PROP_USER], "alice")
        self.assertEqual(properties[EVENT_PROP_REASON], "rejected")
        self.assertEqual(properties[EVENT_PROP_SOURCE], "10.0.0.1")
        self.assertNoSecret()

    def test_an_unknown_certificate_names_no_user(self) -> None:
        with self.assertLogs("pelix.security.core", "WARNING"), self.assertRaises(AuthenticationFailed):
            self.core.authenticate(ClientCertificate("ab" * 32))

        topic, properties = self.events.events[0]
        self.assertEqual(topic, TOPIC_AUTH_FAILURE)
        self.assertIsNone(properties[EVENT_PROP_USER])
        self.assertEqual(properties[EVENT_PROP_KIND], "certificate")

    def test_a_throttled_attempt(self) -> None:
        self.core._throttle = Throttle(max_failures=1)
        with self.assertLogs("pelix.security.core", "WARNING"), self.assertRaises(AuthenticationFailed):
            self.core.authenticate(UsernamePassword("alice", "wrong"))

        with self.assertRaises(AuthenticationFailed):
            self.core.authenticate(UsernamePassword("alice", SECRET))

        self.assertEqual(self.events.topics(), [TOPIC_AUTH_FAILURE, TOPIC_AUTH_FAILURE])
        self.assertEqual(
            [properties[EVENT_PROP_REASON] for _, properties in self.events.events], ["rejected", "throttled"]
        )
        self.assertNoSecret()

    def test_no_event_admin_changes_nothing(self) -> None:
        self.event_admin_registration.unregister()
        self.assertEqual(self.core.authenticate(UsernamePassword("alice", SECRET)).name, "alice")

    def test_a_broken_event_admin_changes_nothing(self) -> None:
        self.event_admin_registration.unregister()
        self.context.register_service(EventAdmin, BrokenEventAdmin(), {})

        with self.assertLogs("pelix.security.core", "ERROR"):
            self.assertEqual(self.core.authenticate(UsernamePassword("alice", SECRET)).name, "alice")

        with self.assertLogs("pelix.security.core", "ERROR"), self.assertRaises(AuthenticationFailed):
            self.core.authenticate(UsernamePassword("alice", "wrong"))


class AccessDeniedEventsTest(AuditTestCase):
    """
    Tests the events of the authorization facade and of the decorators
    """

    def setUp(self) -> None:
        super().setUp()
        reference = self.context.get_service_reference(Authorization)
        assert reference is not None
        self.authorization: Authorization = self.context.get_service(reference)
        self.alice = Subject("alice", authenticated=True)

    def test_check_permitted_reports_a_refusal(self) -> None:
        with self.assertRaises(AccessDenied):
            self.authorization.check_permitted(Permission("jobs.submit"), self.alice)

        self.assertEqual(
            self.events.events,
            [
                (
                    TOPIC_ACCESS_DENIED,
                    {
                        EVENT_PROP_USER: "alice",
                        EVENT_PROP_AUTHENTICATED: True,
                        EVENT_PROP_PERMISSION: "jobs.submit",
                    },
                )
            ],
        )

    def test_check_permitted_reports_the_current_subject(self) -> None:
        with run_as(self.alice), self.assertRaises(AccessDenied):
            self.authorization.check_permitted(Permission("jobs.submit"))

        self.assertEqual(self.events.events[0][1][EVENT_PROP_USER], "alice")

    def test_a_grant_reports_nothing(self) -> None:
        self.authorization.check_permitted(Permission("jobs.read"), self.alice)
        self.assertEqual(self.events.events, [])

    def test_a_question_reports_nothing(self) -> None:
        """
        is_permitted() asks, it does not refuse anything
        """
        self.assertFalse(self.authorization.is_permitted(Permission("jobs.submit"), self.alice))
        self.assertEqual(self.events.events, [])

    def test_a_group_refusal(self) -> None:
        with run_as(self.alice), self.assertRaises(AccessDenied):
            Guarded().for_devs()

        topic, properties = self.events.events[0]
        self.assertEqual(topic, TOPIC_ACCESS_DENIED)
        self.assertEqual(properties[EVENT_PROP_USER], "alice")
        self.assertEqual(properties[EVENT_PROP_DECLARATION], "AllowGroup('dev',)")

    def test_an_anonymous_refusal(self) -> None:
        with self.assertRaises(AuthenticationRequired):
            Guarded().for_devs()

        self.assertEqual(self.events.events[0][1][EVENT_PROP_USER], "anonymous")
        self.assertFalse(self.events.events[0][1][EVENT_PROP_AUTHENTICATED])

    def test_a_permission_refusal_is_reported_once(self) -> None:
        with run_as(self.alice), self.assertRaises(AccessDenied):
            Guarded().submit()

        self.assertEqual(len(self.events.events), 1)
        properties = self.events.events[0][1]
        self.assertEqual(properties[EVENT_PROP_PERMISSION], "jobs.submit")
        self.assertEqual(properties[EVENT_PROP_DECLARATION], "AllowPermission('jobs.submit',)")

    def test_deny_all(self) -> None:
        with run_as(self.alice), self.assertRaises(AccessDenied):
            Guarded().nobody()

        self.assertEqual(self.events.events[0][1][EVENT_PROP_DECLARATION], "DenyAll")

    def test_an_allowed_call_reports_nothing(self) -> None:
        with run_as(Subject("bob", frozenset({"dev"}), authenticated=True)):
            self.assertEqual(Guarded().for_devs(), "ok")

        self.assertEqual(self.events.events, [])

    def test_the_listener_goes_with_the_bundle(self) -> None:
        from pelix.security import decorators

        self.assertIsNotNone(decorators._denial_listener)
        self.framework.stop()
        self.assertIsNone(decorators._denial_listener)


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
