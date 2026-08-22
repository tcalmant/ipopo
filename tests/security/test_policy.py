#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the TOML policy file: roles granted from users and groups, permissions granted
to roles.

:author: Thomas Calmant
"""

import pathlib
import tempfile
import unittest

import pelix.framework
from pelix.ipopo.constants import use_ipopo
from pelix.security import (
    ANONYMOUS,
    FACTORY_ALLOW_ALL,
    FACTORY_POLICY_FILE,
    PROP_POLICY_FILE,
    Decision,
    Permission,
    Subject,
)
from pelix.security.policy import PolicyError, PolicyFile, PolicyTable

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

POLICY = """
[roles.admin]
users  = ["thomas"]
groups = ["dev-leads"]

[roles.operator]
groups = ["dev", "ops"]

[permissions]
admin    = ["jobs.*", "config.*"]
operator = ["jobs.read", "jobs.submit"]
"""

LOGGER = "pelix.security.policy"

# ------------------------------------------------------------------------------


class PolicyTableRolesTest(unittest.TestCase):
    """
    Tests the roles half: a role is granted from the facts an identity source asserted
    """

    def setUp(self) -> None:
        with self.assertLogs(LOGGER, "WARNING"):
            self.table = PolicyTable(POLICY, "policy.toml")

    def test_a_role_granted_by_user_name(self) -> None:
        self.assertIn("admin", self.table.get_roles(Subject("thomas")))

    def test_a_role_granted_by_group(self) -> None:
        self.assertEqual(
            self.table.get_roles(Subject("someone", frozenset({"ops"}))), frozenset({"operator"})
        )

    def test_any_of_the_groups_is_enough(self) -> None:
        for group in ("dev", "ops"):
            with self.subTest(group=group):
                self.assertIn("operator", self.table.get_roles(Subject("someone", frozenset({group}))))

    def test_both_routes_accumulate(self) -> None:
        subject = Subject("thomas", frozenset({"dev"}))
        self.assertEqual(self.table.get_roles(subject), frozenset({"admin", "operator"}))

    def test_nobody_gets_a_role_by_default(self) -> None:
        self.assertEqual(self.table.get_roles(Subject("stranger")), frozenset())
        self.assertEqual(self.table.get_roles(ANONYMOUS), frozenset())

    def test_names_are_compared_exactly(self) -> None:
        """
        The whole reason the format is TOML: its keys are case-sensitive, so the loader
        cannot fold what the rest of the layer forbids anything to fold
        """
        self.assertEqual(self.table.get_roles(Subject("Thomas")), frozenset())
        self.assertEqual(self.table.get_roles(Subject("x", frozenset({"Dev-Leads"}))), frozenset())

    def test_the_policy_asserts_no_group(self) -> None:
        """
        A group is a fact from an identity source, never something a policy invents
        """
        component = PolicyFile()
        self.assertEqual(list(component.get_groups(Subject("thomas"))), [])


class PolicyTablePermissionsTest(unittest.TestCase):
    """
    Tests the permissions half
    """

    def setUp(self) -> None:
        with self.assertLogs(LOGGER, "WARNING"):
            self.table = PolicyTable(POLICY, "policy.toml")

    def permit(self, roles: set[str], spec: str) -> Decision:
        return self.table.is_permitted(Subject("x", roles=frozenset(roles)), Permission.parse(spec))

    def test_a_granted_permission(self) -> None:
        self.assertIs(self.permit({"operator"}, "jobs.submit"), Decision.PERMIT)

    def test_a_wildcard_grant(self) -> None:
        for spec in ("jobs.submit", "jobs.queue.drain", "config.write"):
            with self.subTest(spec=spec):
                self.assertIs(self.permit({"admin"}, spec), Decision.PERMIT)

    def test_a_permission_of_another_role(self) -> None:
        self.assertIs(self.permit({"operator"}, "config.write"), Decision.ABSTAIN)

    def test_no_role_grants_nothing(self) -> None:
        self.assertIs(self.permit(set(), "jobs.read"), Decision.ABSTAIN)

    def test_it_never_denies(self) -> None:
        """
        The format expresses grants only, so this authorizer can never veto what a
        looser one permits. That matters as soon as a second one is registered
        """
        for roles in (set(), {"admin"}, {"operator"}, {"unknown"}):
            for spec in ("jobs.submit", "nothing.at.all", "config.write"):
                with self.subTest(roles=roles, spec=spec):
                    self.assertIsNot(self.permit(roles, spec), Decision.DENY)

    def test_an_empty_permissions_table_denies_everything(self) -> None:
        """
        Safe, and it is what "there is no implicit all-grant" means
        """
        table = PolicyTable("[permissions]\n")
        self.assertIs(
            table.is_permitted(Subject("x", roles=frozenset({"admin"})), Permission("jobs.read")),
            Decision.ABSTAIN,
        )


class PolicyTableWarningsTest(unittest.TestCase):
    """
    Tests what the loader reports.

    Every name is matched exactly against what an identity source provided, so a
    misspelling denies silently. These two shapes are what most misspellings produce
    """

    def test_every_wildcard_is_named(self) -> None:
        with self.assertLogs(LOGGER, "WARNING") as logs:
            PolicyTable('[roles.admin]\nusers = ["thomas"]\n\n[permissions]\nadmin = ["jobs.*", "*"]\n')

        wildcards = [message for message in logs.output if "wildcard" in message]
        self.assertEqual(len(wildcards), 2)
        self.assertTrue(any("'*'" in message for message in wildcards))

    def test_a_role_granted_but_given_no_permission(self) -> None:
        with self.assertLogs(LOGGER, "WARNING") as logs:
            PolicyTable('[roles.typo]\nusers = ["thomas"]\n\n[permissions]\n')

        self.assertIn("typo", logs.output[0])
        self.assertIn("no permission", logs.output[0])

    def test_a_permission_granted_to_nobody(self) -> None:
        with self.assertLogs(LOGGER, "WARNING") as logs:
            PolicyTable('[roles]\n\n[permissions]\ntypo = ["jobs.read"]\n')

        self.assertIn("typo", logs.output[0])
        self.assertIn("granted to nobody", logs.output[0])

    def test_a_coherent_policy_is_quiet(self) -> None:
        policy = '[roles.admin]\nusers = ["thomas"]\n\n[permissions]\nadmin = ["jobs.read"]\n'

        with self.assertNoLogs(LOGGER, "WARNING"):
            PolicyTable(policy)


class PolicyShapeTest(unittest.TestCase):
    """
    tomllib guarantees well-formed TOML, not a well-shaped policy: it would happily
    return {"roles": {"admin": 12}}
    """

    def test_the_shape_failures(self) -> None:
        cases = {
            "roles is not a table": "roles = 12\n",
            "a role is not a table": "[roles]\nadmin = 12\n",
            "an unknown key": '[roles.admin]\nusers = ["a"]\nmembers = ["b"]\n',
            "users is not a list": '[roles.admin]\nusers = "thomas"\n',
            "users holds something else": "[roles.admin]\nusers = [12]\n",
            "permissions is not a table": "permissions = 12\n",
            "a permission list is not a list": '[permissions]\nadmin = "jobs.read"\n',
        }
        for name, text in cases.items():
            with self.subTest(case=name), self.assertRaises(PolicyError):
                PolicyTable(text)

    def test_a_malformed_permission_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            PolicyTable('[roles.admin]\nusers = ["a"]\n\n[permissions]\nadmin = [":queue-a"]\n')

    def test_a_duplicate_key_is_a_parse_error(self) -> None:
        """
        Which an INI file would have kept silently. Granting a role twice is a mistake
        """
        with self.assertRaises(Exception) as context:
            PolicyTable('[permissions]\nadmin = ["a"]\nadmin = ["b"]\n')

        self.assertNotIsInstance(context.exception, PolicyError)

    def test_an_empty_document_is_valid(self) -> None:
        table = PolicyTable("")
        self.assertEqual(table.get_roles(Subject("thomas")), frozenset())


# ------------------------------------------------------------------------------


class PolicyComponentTest(unittest.TestCase):
    """
    Tests the component around the table: validation and reload
    """

    framework: pelix.framework.Framework

    def setUp(self) -> None:
        self.folder = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(self.__remove_folder)

        self.policy_file = self.folder / "policy.toml"
        self.policy_file.write_text(POLICY)

        self.framework = pelix.framework.create_framework(("pelix.ipopo.core", "pelix.security.policy"))
        self.addCleanup(self.framework.delete, True)
        self.framework.start()

    def __remove_folder(self) -> None:
        for path in self.folder.iterdir():
            path.unlink()

        self.folder.rmdir()

    def instantiate(self) -> PolicyFile:
        with use_ipopo(self.framework.get_bundle_context()) as ipopo, self.assertLogs(LOGGER, "WARNING"):
            return ipopo.instantiate(
                FACTORY_POLICY_FILE, "test-policy", {PROP_POLICY_FILE: str(self.policy_file)}
            )

    def test_it_loads_at_validation(self) -> None:
        component = self.instantiate()

        self.assertEqual(set(component.get_roles(Subject("thomas"))), {"admin"})
        self.assertIs(
            component.is_permitted(Subject("x", roles=frozenset({"admin"})), Permission("jobs.submit")),
            Decision.PERMIT,
        )

    def test_no_policy_file_leaves_the_component_invalid(self) -> None:
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            ipopo.instantiate(FACTORY_POLICY_FILE, "no-file", {})
            details = ipopo.get_instance_details("no-file")

        self.assertNotEqual(details["state"], 1, "The component must not be valid without a file")

    def test_a_change_is_picked_up(self) -> None:
        component = self.instantiate()
        self.policy_file.write_text('[roles.admin]\nusers = ["someone-else"]\n\n[permissions]\n')

        with self.assertLogs(LOGGER, "WARNING"):
            component.reload()

        self.assertEqual(set(component.get_roles(Subject("thomas"))), set())
        self.assertEqual(set(component.get_roles(Subject("someone-else"))), {"admin"})

    def test_a_broken_file_keeps_the_previous_policy(self) -> None:
        """
        Higher-stakes than a bad user-list reload, because a truncated file must not be
        mistaken for a policy which genuinely grants nothing
        """
        component = self.instantiate()
        self.policy_file.write_text("[roles.admin\nusers = [")

        with self.assertLogs(LOGGER, "ERROR"):
            component.reload()

        self.assertEqual(set(component.get_roles(Subject("thomas"))), {"admin"})

    def test_a_badly_shaped_file_keeps_the_previous_policy(self) -> None:
        component = self.instantiate()
        self.policy_file.write_text("[roles]\nadmin = 12\n")

        with self.assertLogs(LOGGER, "ERROR"):
            component.reload()

        self.assertEqual(set(component.get_roles(Subject("thomas"))), {"admin"})

    def test_an_empty_file_keeps_the_previous_policy(self) -> None:
        component = self.instantiate()
        self.policy_file.write_text("")

        with self.assertLogs(LOGGER, "ERROR"):
            component.reload()

        self.assertEqual(set(component.get_roles(Subject("thomas"))), {"admin"})

    def test_an_unreadable_file_keeps_the_previous_policy(self) -> None:
        component = self.instantiate()
        self.policy_file.unlink()

        with self.assertLogs(LOGGER, "ERROR"):
            component.reload()

        self.assertEqual(set(component.get_roles(Subject("thomas"))), {"admin"})
        self.policy_file.write_text(POLICY)

    def test_the_watched_folder_is_the_one_holding_the_file(self) -> None:
        self.assertEqual(self.instantiate()._watched_folder, str(self.folder))

    def test_a_change_reported_by_file_install_reloads(self) -> None:
        component = self.instantiate()
        self.policy_file.write_text('[roles.admin]\nusers = ["someone-else"]\n\n[permissions]\n')

        with self.assertLogs(LOGGER, "WARNING"):
            component.folder_change(str(self.folder), [], ["policy.toml"], [])

        self.assertEqual(set(component.get_roles(Subject("someone-else"))), {"admin"})

    def test_a_change_to_a_neighbour_is_ignored(self) -> None:
        component = self.instantiate()
        self.policy_file.write_text('[roles.admin]\nusers = ["someone-else"]\n\n[permissions]\n')
        component.folder_change(str(self.folder), ["other.toml"], [], [])

        self.assertEqual(set(component.get_roles(Subject("thomas"))), {"admin"})


class AllowAllTest(unittest.TestCase):
    """
    Tests the deliberate escape hatch
    """

    framework: pelix.framework.Framework

    def setUp(self) -> None:
        self.framework = pelix.framework.create_framework(("pelix.ipopo.core", "pelix.security.policy"))
        self.addCleanup(self.framework.delete, True)
        self.framework.start()

    def test_it_warns_when_it_validates(self) -> None:
        """
        You cannot get permissive by accident, and you cannot get it quietly either
        """
        with use_ipopo(self.framework.get_bundle_context()) as ipopo, self.assertLogs(LOGGER, "WARNING"):
            ipopo.instantiate(FACTORY_ALLOW_ALL, "allow-all", {})

    def test_it_permits_everything(self) -> None:
        with use_ipopo(self.framework.get_bundle_context()) as ipopo, self.assertLogs(LOGGER, "WARNING"):
            authorizer = ipopo.instantiate(FACTORY_ALLOW_ALL, "allow-all", {})

        for subject in (ANONYMOUS, Subject("thomas", authenticated=True)):
            with self.subTest(subject=subject.name):
                self.assertIs(authorizer.is_permitted(subject, Permission("anything")), Decision.PERMIT)


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
