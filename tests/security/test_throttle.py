#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the brute-force throttling of the security core.

:author: Thomas Calmant
"""

import importlib
import unittest
from typing import Any

import pelix.framework
from pelix.security import (
    PROP_CREDENTIAL_KINDS,
    PROP_THROTTLE_LOCKOUT,
    PROP_THROTTLE_MAX_FAILURES,
    PROP_THROTTLE_MAX_LOCKOUT,
    PROP_THROTTLE_WINDOW,
    AuthenticationFailed,
    Authenticator,
    ClientCertificate,
    Credentials,
    Subject,
    UsernamePassword,
)
from pelix.security.core import Throttle, throttle_keys

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

LOGGER = "pelix.security.core"

# ------------------------------------------------------------------------------


class FakeClock:
    """
    A monotonic clock which only moves when told to
    """

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeAuthenticator(Authenticator):
    """
    Knows a fixed set of user names and passwords, and counts the calls
    """

    def __init__(self, users: dict[str, str]) -> None:
        self.users = users
        self.calls = 0

    def authenticate(self, credentials: Credentials) -> Subject | None:
        assert isinstance(credentials, UsernamePassword)
        self.calls += 1

        expected = self.users.get(credentials.username)
        if expected is None:
            return None

        if expected != credentials.password:
            raise AuthenticationFailed(credentials.username)

        return Subject(credentials.username)


# ------------------------------------------------------------------------------


class ThrottleTest(unittest.TestCase):
    """
    Tests the throttle on its own, with a fake clock
    """

    def setUp(self) -> None:
        self.clock = FakeClock()
        self.throttle = Throttle(max_failures=3, window=100, lockout=10, max_lockout=35, clock=self.clock)

    def record(self, key: str, times: int) -> None:
        """
        Records failures which must not lock the key out
        """
        with self.assertNoLogs(LOGGER, "WARNING"):
            for _ in range(times):
                self.throttle.record_failure([key])

    def lock(self, *keys: str) -> None:
        """
        Fails the keys until they get locked out
        """
        with self.assertLogs(LOGGER, "WARNING"):
            for _ in range(3):
                self.throttle.record_failure(keys)

    def test_nothing_is_locked_by_default(self) -> None:
        self.assertFalse(self.throttle.is_locked(["a"]))
        self.assertEqual(len(self.throttle), 0, "A check must not track anything")

    def test_a_key_is_locked_after_too_many_failures(self) -> None:
        self.record("a", 2)
        self.assertFalse(self.throttle.is_locked(["a"]))

        self.lock("a")
        self.assertTrue(self.throttle.is_locked(["a"]))
        self.assertFalse(self.throttle.is_locked(["b"]))

    def test_any_locked_key_locks_the_attempt(self) -> None:
        self.lock("a")
        self.assertTrue(self.throttle.is_locked(["b", "a"]))

    def test_failures_outside_the_window_do_not_count(self) -> None:
        with self.assertNoLogs(LOGGER, "WARNING"):
            for _ in range(5):
                self.throttle.record_failure(["a"])
                self.clock.advance(60)

        self.assertFalse(self.throttle.is_locked(["a"]))

    def test_a_lockout_ends(self) -> None:
        self.lock("a")
        self.clock.advance(9.9)
        self.assertTrue(self.throttle.is_locked(["a"]))

        self.clock.advance(0.1)
        self.assertFalse(self.throttle.is_locked(["a"]))

    def test_the_lockout_doubles_up_to_its_bound(self) -> None:
        """
        The count is a sliding window: once a lockout is over, one more failure within
        the window locks the key again, for twice as long
        """
        self.lock("a")
        for expected in (20, 35, 35):
            self.clock.advance(self.__remaining("a"))
            self.assertFalse(self.throttle.is_locked(["a"]))

            with self.assertLogs(LOGGER, "WARNING") as logs:
                self.throttle.record_failure(["a"])

            self.assertIn(f"locked out for {expected} seconds", logs.output[0])
            self.assertTrue(self.throttle.is_locked(["a"]))

    def __remaining(self, key: str) -> float:
        # Reaches the state directly: the public API deliberately does not tell how long a lock lasts
        return self.throttle._keys[key].locked_until - self.clock()

    def test_the_warning_is_logged_once_per_lockout(self) -> None:
        self.lock("a")

        # Attempts during the lockout are refused before they could be recorded, but
        # even a recorded one must neither extend it nor warn again
        with self.assertNoLogs(LOGGER, "WARNING"):
            self.throttle.record_failure(["a"])

        self.assertAlmostEqual(self.__remaining("a"), 10)

    def test_a_quiet_key_is_forgiven(self) -> None:
        """
        Once its lockout is over and the window has passed with no failure, a key
        starts again from scratch, escalation included
        """
        self.lock("a")
        self.clock.advance(200)
        self.assertFalse(self.throttle.is_locked(["a"]))

        self.record("a", 2)
        self.assertFalse(self.throttle.is_locked(["a"]))

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.throttle.record_failure(["a"])

        self.assertIn("locked out for 10 seconds", logs.output[0])

    def test_a_success_clears_the_key(self) -> None:
        self.lock("a")
        self.throttle.record_success("a")

        self.assertFalse(self.throttle.is_locked(["a"]))
        self.assertEqual(len(self.throttle), 0)

    def test_the_tracked_keys_are_bounded(self) -> None:
        throttle = Throttle(max_failures=2, max_keys=10, clock=self.clock)
        for index in range(100):
            throttle.record_failure([f"source:{index}"])

        self.assertEqual(len(throttle), 10)

        # The least recently touched keys are the ones forgotten
        self.assertEqual(list(throttle._keys), [f"source:{index}" for index in range(90, 100)])

    def test_invalid_settings(self) -> None:
        with self.assertRaises(ValueError):
            Throttle(max_failures=0)

        with self.assertRaises(ValueError):
            Throttle(max_keys=0)


class ThrottleKeysTest(unittest.TestCase):
    """
    Tests which keys an attempt is counted against
    """

    def test_a_password_is_counted_against_its_user(self) -> None:
        self.assertEqual(throttle_keys(UsernamePassword("thomas", "x"), None), ("password:thomas", None))

    def test_a_certificate_is_counted_against_its_fingerprint(self) -> None:
        self.assertEqual(
            throttle_keys(ClientCertificate("ab" * 32), None), (f"certificate:{'ab' * 32}", None)
        )

    def test_the_source(self) -> None:
        self.assertEqual(
            throttle_keys(UsernamePassword("thomas", "x"), "10.0.0.1"), ("password:thomas", "source:10.0.0.1")
        )

    def test_credentials_naming_no_account(self) -> None:
        self.assertEqual(throttle_keys(Credentials(), "10.0.0.1"), (None, "source:10.0.0.1"))


# ------------------------------------------------------------------------------


class ThrottledAuthenticateTest(unittest.TestCase):
    """
    Tests authenticate() behind the throttle
    """

    framework: pelix.framework.Framework

    def setUp(self) -> None:
        self.framework = pelix.framework.create_framework(("pelix.security.core",))
        self.addCleanup(self.framework.delete, True)
        self.framework.start()

        self.core: Any = importlib.import_module("pelix.security.core")
        self.clock = FakeClock()
        self.core._throttle = Throttle(
            max_failures=3, window=100, lockout=10, max_lockout=40, clock=self.clock
        )

        self.authenticator = FakeAuthenticator({"alice": "good", "bob": "good"})
        self.framework.get_bundle_context().register_service(
            Authenticator, self.authenticator, {PROP_CREDENTIAL_KINDS: ("password",)}
        )

    def attempt(self, username: str, password: str, source: str | None = None) -> bool:
        """
        :return: True if the attempt succeeded
        """
        try:
            self.core.authenticate(UsernamePassword(username, password), source)
            return True
        except AuthenticationFailed:
            return False

    def lock_alice(self, source: str | None = None) -> None:
        with self.assertLogs(LOGGER, "WARNING"):
            for _ in range(3):
                self.assertFalse(self.attempt("alice", "bad", source))

    def test_the_default_signature_still_works(self) -> None:
        self.assertEqual(self.core.authenticate(UsernamePassword("alice", "good")).name, "alice")

    def test_a_locked_account_is_refused_without_consulting_anybody(self) -> None:
        self.lock_alice()
        calls = self.authenticator.calls

        with self.assertRaises(AuthenticationFailed) as context:
            self.core.authenticate(UsernamePassword("alice", "good"))

        self.assertEqual(self.authenticator.calls, calls)

        # Nothing tells the caller that the account exists and is locked
        self.assertNotIn("lock", str(context.exception).lower())

    def test_a_locked_account_does_not_lock_another(self) -> None:
        self.lock_alice()
        self.assertTrue(self.attempt("bob", "good"))

    def test_the_account_is_unlocked_after_the_lockout(self) -> None:
        self.lock_alice()
        self.clock.advance(10)
        self.assertTrue(self.attempt("alice", "good"))

    def test_a_success_clears_the_account(self) -> None:
        with self.assertNoLogs(LOGGER, "WARNING"):
            for _ in range(2):
                self.attempt("alice", "bad")

            self.assertTrue(self.attempt("alice", "good"))

            # Had the success not cleared the account, this would be its third failure
            self.attempt("alice", "bad")

        self.assertTrue(self.attempt("alice", "good"))

    def test_a_source_is_locked_across_accounts(self) -> None:
        """
        Spraying one password over many accounts is what the per-source key catches
        """
        with self.assertLogs(LOGGER, "WARNING"):
            for user in ("alice", "bob", "carol"):
                self.assertFalse(self.attempt(user, "bad", "10.0.0.1"))

        self.assertFalse(self.attempt("bob", "good", "10.0.0.1"))
        self.assertTrue(self.attempt("bob", "good", "10.0.0.2"))

    def test_a_success_does_not_clear_the_source(self) -> None:
        with self.assertNoLogs(LOGGER, "WARNING"):
            self.attempt("alice", "bad", "10.0.0.1")
            self.attempt("carol", "bad", "10.0.0.1")
            self.assertTrue(self.attempt("bob", "good", "10.0.0.1"))

        with self.assertLogs(LOGGER, "WARNING"):
            self.attempt("dave", "bad", "10.0.0.1")

        self.assertFalse(self.attempt("bob", "good", "10.0.0.1"))

    def test_a_locked_account_is_locked_from_every_source(self) -> None:
        self.lock_alice("10.0.0.1")
        self.assertFalse(self.attempt("alice", "good", "10.0.0.2"))


class ThrottleConfigurationTest(unittest.TestCase):
    """
    Tests how the framework properties configure the throttle
    """

    def start(self, properties: dict[str, Any]) -> Any:
        framework = pelix.framework.create_framework(("pelix.security.core",), properties)
        self.addCleanup(framework.delete, True)
        framework.start()
        return importlib.import_module("pelix.security.core")

    def test_the_defaults(self) -> None:
        throttle = self.start({})._throttle

        self.assertEqual(
            (throttle.max_failures, throttle.window, throttle.lockout, throttle.max_lockout),
            (5, 900, 60, 900),
        )

    def test_the_properties(self) -> None:
        throttle = self.start(
            {
                PROP_THROTTLE_MAX_FAILURES: "10",
                PROP_THROTTLE_WINDOW: 60,
                PROP_THROTTLE_LOCKOUT: "5",
                PROP_THROTTLE_MAX_LOCKOUT: 3600.0,
            }
        )._throttle

        self.assertEqual(
            (throttle.max_failures, throttle.window, throttle.lockout, throttle.max_lockout),
            (10, 60, 5, 3600),
        )

    def test_zero_failures_disables_it(self) -> None:
        with self.assertLogs(LOGGER, "WARNING"):
            core = self.start({PROP_THROTTLE_MAX_FAILURES: 0})

        self.assertIsNone(core._throttle)

    def test_an_invalid_value_falls_back_to_the_default(self) -> None:
        with self.assertLogs(LOGGER, "ERROR"):
            throttle = self.start({PROP_THROTTLE_WINDOW: "a while"})._throttle

        self.assertEqual(throttle.window, 900)

    def test_the_throttle_goes_with_the_bundle(self) -> None:
        core = self.start({})
        self.assertIsNotNone(core._throttle)

        for bundle in pelix.framework.FrameworkFactory.get_framework().get_bundles():
            if bundle.get_symbolic_name() == "pelix.security.core":
                bundle.stop()

        self.assertIsNone(core._throttle)


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
