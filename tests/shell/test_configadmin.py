#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the ConfigurationAdmin shell commands

:author: Thomas Calmant
"""

# Pelix
import pelix.framework
import pelix.services
import pelix.shell

# Standard library
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class ConfigAdminShellTest(unittest.TestCase):
    """
    Tests the EventAdmin shell commands
    """
    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core',
             'pelix.shell.core',
             'pelix.services.configadmin',
             'pelix.shell.configadmin'))
        self.framework.start()

        # Get the Shell service
        context = self.framework.get_bundle_context()
        svc_ref = context.get_service_reference(pelix.shell.SERVICE_SHELL)
        self.shell = context.get_service(svc_ref)

        # Instantiate the EventAdmin component
        context = self.framework.get_bundle_context()

        # Get the service
        self.config_ref = context.get_service_reference(
            pelix.services.SERVICE_CONFIGURATION_ADMIN)
        self.config = context.get_service(self.config_ref)

        # Remove existing configurations
        for config in self.config.list_configurations():
            config.delete()

    def _run_command(self, command, *args):
        """
        Runs the given shell command
        """
        # String output
        str_output = StringIO()

        # Format command
        if args:
            command = command.format(*args)

        # Add the namespace prefix
        command = 'config.{0}'.format(command)

        # Run command
        self.shell.execute(command, stdout=str_output)
        return str_output.getvalue()

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Remove existing configurations
        for config in self.config.list_configurations():
            config.delete()

        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.framework = None

    def testLifeCycle(self):
        """
        Tests a configuration life cycle
        """
        # Create a factory configuration
        key = "testConfig"
        first_value = "first"
        factory_name = "testFactory"
        output = self._run_command("create {0} {1}={2}", factory_name,
                                   key, first_value)

        # Get the generated configuration
        config = next(iter(self.config.list_configurations()))

        # Check validity
        self.assertIn(config.get_pid(), output)
        self.assertEqual(factory_name, config.get_factory_pid())
        self.assertDictContainsSubset({key: first_value},
                                      config.get_properties())

        # Update it
        second_value = "second"
        self._run_command("update {0} {1}={2}", config.get_pid(),
                          key, second_value)
        self.assertDictContainsSubset({key: second_value},
                                      config.get_properties())

        # Reload it
        self._run_command("reload {0}", config.get_pid())

        # List it
        output = self._run_command('list')
        self.assertIn(config.get_pid(), output)

        output = self._run_command('list {0}', config.get_pid())
        self.assertIn(config.get_pid(), output)

        # Delete it
        self._run_command("delete {0}", config.get_pid())
        self.assertEqual(self.config.list_configurations(), set())

    def testInvalidPid(self):
        """
        Tests commands with invalid PIDs
        """
        self._run_command("delete <invalid>")
        self._run_command("list <invalid>")
        self._run_command("reload <invalid>")

    def testUpdate(self):
        """
        Tests the update command
        """
        pid = "testPid"
        key = "testConfig"
        value = "testValue"

        # Create the configuration, with no property
        self._run_command("update {0}", pid)

        # Get the generated configuration
        config = next(iter(self.config.list_configurations()))
        self.assertEqual(config.get_pid(), pid)
        self.assertIsNone(config.get_properties())

        # Set a key
        self._run_command("update {0} {1}={2}", pid, key, value)
        self.assertDictContainsSubset({key: value}, config.get_properties())

        # Remove a key
        self._run_command("update {0} {1}=None", pid, key)
        self.assertNotIn(key, config.get_properties())

    def testList(self):
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
        output = self._run_command("list {0}", pid)
        self.assertIn("No configuration", output)

        # Create a configuration without properties
        config = self.config.get_configuration(pid)

        # List it
        output = self._run_command("list {0}", pid)
        self.assertIn("Not yet updated", output)

        # Update it
        config.update({key: value})
        output = self._run_command("list {0}", pid)
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
        output = self._run_command("list {0}", pid)
        self.assertIn("No configuration", output)
        self.assertIn(pid, output)
