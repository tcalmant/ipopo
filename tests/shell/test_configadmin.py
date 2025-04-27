#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the ConfigurationAdmin shell commands

:author: Thomas Calmant
"""

import os
import unittest
from io import StringIO
from typing import Any, Dict, Mapping, Optional

import pelix.framework
import pelix.services
import pelix.shell
import pelix.shell.beans as beans

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class ConfigAdminShellTest(unittest.TestCase):
    """
    Tests the EventAdmin shell commands
    """

    framework: pelix.framework.Framework
    shell: pelix.shell.ShellService

    def assertDictContains(self, subset: Dict[str, Any], tested: Optional[Dict[str, Any]]) -> None:
        assert tested is not None
        self.assertEqual(tested, tested | subset)

    def setUp(self) -> None:
        """
        Prepares a framework and a registers a service to export
        """
        # Use a local configuration folder
        conf_folder = os.path.join(os.path.dirname(__file__), "conf")

        # Create the framework
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.shell.core", "pelix.services.configadmin", "pelix.shell.configadmin"),
            {"configuration.folder": conf_folder},
        )
        self.framework.start()

        # Get the Shell service
        context = self.framework.get_bundle_context()
        svc_ref = context.get_service_reference(pelix.shell.ShellService)
        assert svc_ref is not None
        self.shell = context.get_service(svc_ref)

        # Instantiate the EventAdmin component
        context = self.framework.get_bundle_context()

        # Get the service
        self.config_ref = context.get_service_reference(pelix.services.IConfigurationAdmin)
        assert self.config_ref is not None
        self.config = context.get_service(self.config_ref)

        # Remove existing configurations
        for config in self.config.list_configurations():
            config.delete()

    def _run_command(self, command: str, *args: str) -> str:
        """
        Runs the given shell command
        """
        # String output
        str_output = StringIO()

        # Format command
        if args:
            command = command.format(*args)

        # Add the namespace prefix
        command = f"config.{command}"

        # Run command
        session = beans.ShellSession(beans.IOHandler(None, str_output))
        self.shell.execute(command, session)
        return str_output.getvalue()

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Remove existing configurations
        for config in self.config.list_configurations():
            config.delete()

        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework()
        self.framework = None  # type: ignore

    def testLifeCycle(self) -> None:
        """
        Tests a configuration life cycle
        """
        # Create a factory configuration
        key = "testConfig"
        first_value = "first"
        factory_name = "testFactory"
        output = self._run_command(f"create {factory_name} {key}={first_value}")

        # Get the generated configuration
        config = next(iter(self.config.list_configurations()))

        # Check validity
        self.assertIn(config.get_pid(), output)
        self.assertEqual(factory_name, config.get_factory_pid())
        self.assertDictContains({key: first_value}, config.get_properties())

        # Update it
        second_value = "second"
        self._run_command(f"update {config.get_pid()} {key}={second_value}")
        self.assertDictContains({key: second_value}, config.get_properties())

        # Reload it
        self._run_command(f"reload {config.get_pid()}")

        # List it
        output = self._run_command("list")
        self.assertIn(config.get_pid(), output)

        output = self._run_command(f"list {config.get_pid()}")
        self.assertIn(config.get_pid(), output)

        # Delete it
        self._run_command(f"delete {config.get_pid()}")
        self.assertEqual(self.config.list_configurations(), set())

    def testInvalidPid(self) -> None:
        """
        Tests commands with invalid PIDs
        """
        self._run_command("delete <invalid>")
        self._run_command("list <invalid>")
        self._run_command("reload <invalid>")

    def testUpdate(self) -> None:
        """
        Tests the update command
        """
        pid = "testPid"
        key = "testConfig"
        value = "testValue"

        # Create the configuration, with no property
        self._run_command(f"update {pid}")

        # Get the generated configuration
        config = next(iter(self.config.list_configurations()))
        self.assertEqual(config.get_pid(), pid)
        self.assertIsNone(config.get_properties())

        # Set a key
        self._run_command(f"update {pid} {key}={value}")
        self.assertDictContains({key: value}, config.get_properties())

        # Remove a key
        self._run_command(f"update {pid} {key}=None")
        self.assertNotIn(key, config.get_properties() or {})

    def testList(self) -> None:
        """
        Other tests for the list command
        """
        pid = "testPid"
        pid2 = "testPidBis"
        key = "testConfig"
        value = "testValue"

        # Nothing at first
        output = self._run_command("list")
        self.assertIn("No configuration", output)

        # List inexistent PID
        output = self._run_command(f"list {pid}")
        self.assertIn("No configuration", output)

        # Create a configuration without properties
        config = self.config.get_configuration(pid)

        # List it
        output = self._run_command(f"list {pid}")
        self.assertIn("Not yet updated", output)

        # Update it
        config.update({key: value})
        output = self._run_command(f"list {pid}")
        self.assertIn(pid, output)
        self.assertIn(key, output)
        self.assertIn(value, output)

        # Create a second one
        config2 = self.config.get_configuration(pid2)

        # Delete the first one
        config.delete()
        self.assertNotIn(config, self.config.list_configurations())
        self.assertIn(config2, self.config.list_configurations())

        # List it
        output = self._run_command(f"list {pid}")
        self.assertIn("No configuration", output)
        self.assertIn(pid, output)
