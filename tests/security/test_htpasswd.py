#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the .htpasswd credential store and its .htgroup membership half.

:author: Thomas Calmant
"""

import os
import pathlib
import tempfile
import time
import unittest

import pelix.framework
from pelix.ipopo.constants import use_ipopo
from pelix.security import (
    FACTORY_HTPASSWD,
    PROP_HTPASSWD_FILE,
    PROP_HTPASSWD_GROUPS,
    PROP_HTPASSWD_PLAINTEXT,
    AuthenticationFailed,
    Subject,
    UsernamePassword,
    _crypt,
)
from pelix.security.htpasswd import HtpasswdStore, parse_htgroup, parse_htpasswd

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# "good", hashed with SHA-crypt over SHA-512
GOOD_SHA512 = (
    "$6$FGkY6bLp$FLRsAi6byimzKD0qdHddj.KT3zGYn0YAQb1fz92.0iRT7oOWSxlrqtRH5PsV2.O54EGWS.YTWcL/GI.oOsXnx."
)

# "good", hashed with the Apache MD5 construction
GOOD_APR1 = "$apr1$FGkY6bLp$IKkCuz1P..KyQ0FL0L7Ir0"

# "abc", as htpasswd -s writes it
ABC_SHA1 = "{SHA}qZk+NkcGgWq6PiVxeFDCbJzQ2J0="

# ------------------------------------------------------------------------------


class ParseHtpasswdTest(unittest.TestCase):
    """
    Tests the parsing of a password file, which happens once at load rather than
    entry by entry at login
    """

    def test_a_plain_file(self) -> None:
        users, skipped = parse_htpasswd([f"thomas:{GOOD_SHA512}", f"batch:{GOOD_APR1}"], "test")

        self.assertEqual(set(users), {"thomas", "batch"})
        self.assertEqual(skipped, 0)

    def test_comments_and_blank_lines(self) -> None:
        users, skipped = parse_htpasswd(["# a comment", "", "   ", f"thomas:{GOOD_SHA512}"], "test")

        self.assertEqual(set(users), {"thomas"})
        self.assertEqual(skipped, 0)

    def test_a_malformed_line_is_skipped(self) -> None:
        with self.assertLogs("pelix.security.htpasswd", "WARNING"):
            users, skipped = parse_htpasswd(["not-a-pair", f"thomas:{GOOD_SHA512}"], "test")

        self.assertEqual(set(users), {"thomas"})
        self.assertEqual(skipped, 1)

    def test_an_unsupported_entry_leaves_the_user_absent(self) -> None:
        """
        Absent rather than present and unverifiable, and reported with its file and
        line number so that the operator meets it at deploy time
        """
        lines = [f"thomas:{GOOD_SHA512}", "old:rEK1ecacw.rKc"]

        with self.assertLogs("pelix.security.htpasswd", "WARNING") as logs:
            users, skipped = parse_htpasswd(lines, "/etc/pelix/.htpasswd")

        self.assertNotIn("old", users)
        self.assertEqual(skipped, 1)
        self.assertIn("/etc/pelix/.htpasswd:2", logs.output[0])
        self.assertIn("old", logs.output[0])

    def test_a_hash_is_never_logged(self) -> None:
        """
        A warning names what the entry is and where it is, never what it holds
        """
        with self.assertLogs("pelix.security.htpasswd", "WARNING") as logs:
            parse_htpasswd(["old:rEK1ecacw.rKc", f"weak:{ABC_SHA1}"], "test")

        for message in logs.output:
            self.assertNotIn("rEK1ecacw.rKc", message)
            self.assertNotIn("qZk+", message)

    def test_a_weak_scheme_is_reported(self) -> None:
        with self.assertLogs("pelix.security.htpasswd", "WARNING") as logs:
            users, _ = parse_htpasswd([f"weak:{ABC_SHA1}"], "test")

        # Reported, but kept: it exists in the wild, and refusing it locks people out
        self.assertIn("weak", users)
        self.assertIn("htpasswd -5", logs.output[0])

    def test_plaintext_is_refused_by_default(self) -> None:
        with self.assertLogs("pelix.security.htpasswd", "WARNING") as logs:
            users, skipped = parse_htpasswd(["thomas:hunter2"], "test")

        self.assertEqual(users, {})
        self.assertEqual(skipped, 1)
        self.assertIn(PROP_HTPASSWD_PLAINTEXT, logs.output[0])

    def test_plaintext_is_accepted_when_asked_for(self) -> None:
        """
        "Support plaintext" and "refuse unknown formats" are the same branch with
        opposite defaults
        """
        with self.assertLogs("pelix.security.htpasswd", "WARNING"):
            users, skipped = parse_htpasswd(["thomas:hunter2"], "test", allow_plaintext=True)

        self.assertEqual(users, {"thomas": "hunter2"})
        self.assertEqual(skipped, 0)

    def test_user_names_are_kept_verbatim(self) -> None:
        """
        Which is what Apache itself does with these files: on this point the store is
        format-correct by doing nothing
        """
        users, _ = parse_htpasswd([f"Thomas:{GOOD_SHA512}"], "test")

        self.assertIn("Thomas", users)
        self.assertNotIn("thomas", users)


class ParseHtgroupTest(unittest.TestCase):
    """
    Tests the parsing of a group file
    """

    def test_a_plain_file(self) -> None:
        groups = parse_htgroup(["dev-leads: thomas", "ops: batch thomas"], "test")

        self.assertEqual(groups["thomas"], {"dev-leads", "ops"})
        self.assertEqual(groups["batch"], {"ops"})

    def test_comments_and_blank_lines(self) -> None:
        groups = parse_htgroup(["# groupname: user", "", "ops: batch"], "test")

        self.assertEqual(set(groups), {"batch"})

    def test_a_group_may_span_several_lines(self) -> None:
        groups = parse_htgroup(["ops: batch", "ops: thomas"], "test")

        self.assertEqual(groups["batch"], {"ops"})
        self.assertEqual(groups["thomas"], {"ops"})

    def test_a_malformed_line_is_skipped(self) -> None:
        with self.assertLogs("pelix.security.htpasswd", "WARNING"):
            groups = parse_htgroup(["not-a-group", "ops: batch"], "test")

        self.assertEqual(set(groups), {"batch"})

    def test_an_empty_group_holds_nobody(self) -> None:
        self.assertEqual(parse_htgroup(["empty:"], "test"), {})


# ------------------------------------------------------------------------------


class StoreTestCase(unittest.TestCase):
    """
    Common fixture: a temporary folder holding the two files, and a store over them
    """

    framework: pelix.framework.Framework

    users_content = f"thomas:{GOOD_SHA512}\nbatch:{GOOD_APR1}\n"
    groups_content = "dev-leads: thomas\nops: thomas batch\n"

    def setUp(self) -> None:
        self.folder = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(self.__remove_folder)

        self.users_file = self.folder / ".htpasswd"
        self.groups_file = self.folder / ".htgroup"
        self.users_file.write_text(self.users_content)
        self.groups_file.write_text(self.groups_content)
        self.users_file.chmod(0o600)

        self.framework = pelix.framework.create_framework(("pelix.ipopo.core", "pelix.security.htpasswd"))
        self.addCleanup(self.framework.delete, True)
        self.framework.start()

    def __remove_folder(self) -> None:
        for path in self.folder.iterdir():
            path.unlink()

        self.folder.rmdir()

    def instantiate(self, **properties: object) -> HtpasswdStore:
        """
        Instantiates the store over the temporary files

        :param properties: Extra component properties
        :return: The store instance
        """
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            return ipopo.instantiate(
                FACTORY_HTPASSWD,
                "test-htpasswd",
                {
                    PROP_HTPASSWD_FILE: str(self.users_file),
                    PROP_HTPASSWD_GROUPS: str(self.groups_file),
                    **properties,
                },
            )


class AuthenticateTest(StoreTestCase):
    """
    Tests the Authenticator half
    """

    def setUp(self) -> None:
        super().setUp()
        self.store = self.instantiate()

    def test_a_good_password(self) -> None:
        subject = self.store.authenticate(UsernamePassword("thomas", "good"))

        assert subject is not None
        self.assertEqual(subject.name, "thomas")

    def test_every_supported_scheme_of_the_file(self) -> None:
        for name in ("thomas", "batch"):
            with self.subTest(user=name):
                self.assertIsNotNone(self.store.authenticate(UsernamePassword(name, "good")))

    def test_a_wrong_password_stops_the_loop(self) -> None:
        """
        A store which knows the user and rejects the password raises rather than
        abstaining: that is what closes the credential oracle
        """
        with self.assertRaises(AuthenticationFailed):
            self.store.authenticate(UsernamePassword("thomas", "wrong"))

    def test_an_unknown_user_abstains(self) -> None:
        """
        Abstain and not fail: raising for a name this store never heard of would stop
        the loop and make every lower-ranked store unreachable for that name
        """
        self.assertIsNone(self.store.authenticate(UsernamePassword("nobody", "good")))

    def test_another_kind_of_credentials_abstains(self) -> None:
        class OtherCredentials:
            KIND = "token"

        self.assertIsNone(self.store.authenticate(OtherCredentials()))  # ty: ignore[invalid-argument-type]

    def test_user_names_are_compared_exactly(self) -> None:
        self.assertIsNone(self.store.authenticate(UsernamePassword("Thomas", "good")))

    def test_passwords_are_not_transformed(self) -> None:
        """
        The stored hash was computed over exact bytes, so touching the candidate would
        break every non-ASCII password
        """
        for password in ("GOOD", " good", "good "):
            with self.subTest(password=password), self.assertRaises(AuthenticationFailed):
                self.store.authenticate(UsernamePassword("thomas", password))


class TimingTest(StoreTestCase):
    """
    An unknown user must not answer instantly while a known one burns thousands of
    rounds: the difference alone enumerates the file
    """

    def setUp(self) -> None:
        super().setUp()
        self.store = self.instantiate()

    def measure(self, username: str) -> float:
        start = time.perf_counter()
        for _ in range(5):
            try:
                self.store.authenticate(UsernamePassword(username, "some-password"))
            except AuthenticationFailed:
                pass

        return time.perf_counter() - start

    def test_an_unknown_user_costs_about_what_a_known_one_costs(self) -> None:
        known = self.measure("thomas")
        unknown = self.measure("nobody")

        # Generous, because a wall clock in a test suite is not a measuring instrument:
        # what it catches is the shape of the leak, an instant answer against a
        # thousands-of-rounds one
        self.assertGreater(unknown, known / 4, "The unknown user answered far too quickly")

    def test_the_dummy_hash_follows_the_file(self) -> None:
        """
        The fake check uses the most expensive scheme the file really holds, or it would
        be visibly cheaper than a real one
        """
        self.assertEqual(self.store._dummy_scheme, _crypt.Scheme.SHA512)


class MembershipTest(StoreTestCase):
    """
    Tests the MembershipProvider half
    """

    def setUp(self) -> None:
        super().setUp()
        self.store = self.instantiate()

    def test_the_groups_of_a_user(self) -> None:
        self.assertEqual(set(self.store.get_groups(Subject("thomas"))), {"dev-leads", "ops"})
        self.assertEqual(set(self.store.get_groups(Subject("batch"))), {"ops"})

    def test_an_unknown_user_has_no_group(self) -> None:
        self.assertEqual(set(self.store.get_groups(Subject("nobody"))), set())

    def test_a_password_file_grants_no_role(self) -> None:
        """
        Roles are the policy's job
        """
        self.assertEqual(set(self.store.get_roles(Subject("thomas"))), set())

    def test_without_a_group_file_nobody_has_a_group(self) -> None:
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            ipopo.kill("test-htpasswd")

        store = self.instantiate(**{PROP_HTPASSWD_GROUPS: ""})
        self.assertEqual(set(store.get_groups(Subject("thomas"))), set())


class ReloadTest(StoreTestCase):
    """
    Tests what a reload does, and above all what a failed one does not do
    """

    def setUp(self) -> None:
        super().setUp()
        self.store = self.instantiate()

    def test_a_new_user_is_picked_up(self) -> None:
        self.users_file.write_text(f"{self.users_content}added:{GOOD_SHA512}\n")
        self.store.reload()

        self.assertIsNotNone(self.store.authenticate(UsernamePassword("added", "good")))

    def test_a_removed_user_is_revoked(self) -> None:
        """
        A successfully parsed file with a user removed does revoke that user: that is
        the whole point of the distinction below
        """
        self.users_file.write_text(f"batch:{GOOD_APR1}\n")
        self.store.reload()

        self.assertIsNone(self.store.authenticate(UsernamePassword("thomas", "good")))

    def test_an_empty_file_keeps_the_previous_table(self) -> None:
        """
        Far more likely a partial write than an intentional revocation of everyone.
        This is the one place where failing closed is the wrong instinct
        """
        self.users_file.write_text("")

        with self.assertLogs("pelix.security.htpasswd", "ERROR"):
            self.store.reload()

        self.assertIsNotNone(self.store.authenticate(UsernamePassword("thomas", "good")))

    def test_an_unreadable_file_keeps_the_previous_table(self) -> None:
        self.users_file.unlink()

        with self.assertLogs("pelix.security.htpasswd", "ERROR"):
            self.store.reload()

        self.assertIsNotNone(self.store.authenticate(UsernamePassword("thomas", "good")))

        # Put it back, so that the cleanup finds what it expects
        self.users_file.write_text(self.users_content)

    def test_a_file_with_no_usable_entry_keeps_the_previous_table(self) -> None:
        self.users_file.write_text("thomas:rEK1ecacw.rKc\n")

        with self.assertLogs("pelix.security.htpasswd", "WARNING"):
            self.store.reload()

        self.assertIsNotNone(self.store.authenticate(UsernamePassword("thomas", "good")))

    def test_the_group_file_is_reloaded_too(self) -> None:
        self.groups_file.write_text("release: thomas\n")
        self.store.reload()

        self.assertEqual(set(self.store.get_groups(Subject("thomas"))), {"release"})


class FileInstallTest(StoreTestCase):
    """
    Tests the whiteboard registration on the File Install service
    """

    def setUp(self) -> None:
        super().setUp()
        self.store = self.instantiate()

    def test_the_watched_folder_is_the_one_holding_the_file(self) -> None:
        self.assertEqual(self.store._watched_folder, str(self.folder))

    def test_a_change_to_a_watched_file_reloads(self) -> None:
        self.users_file.write_text(f"{self.users_content}added:{GOOD_SHA512}\n")
        self.store.folder_change(str(self.folder), [], [".htpasswd"], [])

        self.assertIsNotNone(self.store.authenticate(UsernamePassword("added", "good")))

    def test_a_change_to_a_neighbour_is_ignored(self) -> None:
        """
        File Install watches a whole folder and reports base names, so everything living
        next to the two files of interest has to be filtered out
        """
        self.users_file.write_text(f"{self.users_content}added:{GOOD_SHA512}\n")
        self.store.folder_change(str(self.folder), ["something-else.txt"], [], [])

        self.assertIsNone(self.store.authenticate(UsernamePassword("added", "good")))

    def test_the_whole_round_trip(self) -> None:
        """
        With the File Install bundle started, writing the file is enough. Without it,
        the file is simply read once at validation: that is documented degradation, not
        a failure, and every other test here runs in that mode
        """
        context = self.framework.get_bundle_context()
        context.install_bundle("pelix.services.fileinstall").start()

        # The watcher diffs on (mtime, checksum), so the content really has to change
        self.users_file.write_text(f"{self.users_content}added:{GOOD_SHA512}\n")

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if self.store.authenticate(UsernamePassword("added", "good")) is not None:
                return

            time.sleep(0.2)

        self.fail("The store was not reloaded within 10 seconds")


class ConfigurationTest(StoreTestCase):
    """
    Tests the properties of the component
    """

    def test_no_password_file_leaves_the_component_invalid(self) -> None:
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            ipopo.instantiate(FACTORY_HTPASSWD, "no-file", {})
            details = ipopo.get_instance_details("no-file")

        self.assertNotEqual(details["state"], 1, "The component must not be valid without a file")

    def test_the_accepted_credential_kinds_are_published(self) -> None:
        """
        Declaring them is mandatory: the core selects an authenticator on that property
        """
        self.instantiate()

        reference = self.framework.get_bundle_context().get_service_reference("pelix.security.authenticator")
        assert reference is not None
        self.assertEqual(tuple(reference.get_property("pelix.security.credentials")), ("password",))

    def test_the_file_mode_is_reported(self) -> None:
        if os.name != "posix":
            self.skipTest("POSIX file modes only")

        self.users_file.chmod(0o644)

        with self.assertLogs("pelix.security.htpasswd", "WARNING") as logs:
            self.instantiate()

        self.assertTrue(any("chmod 600" in message for message in logs.output))


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
