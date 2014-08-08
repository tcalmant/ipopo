#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO shell commands

:author: Thomas Calmant
"""

# Pelix
from pelix.ipopo.constants import use_ipopo
import pelix.framework
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


class IPopoShellTest(unittest.TestCase):
    """
    Tests the iPOPO shell commands
    """
    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core',
             'pelix.shell.core',
             'pelix.shell.ipopo',
             # Some bundles providing
             # factories
             'tests.ipopo.ipopo_bundle',
             'samples.handler.sample'))
        self.framework.start()

        # Get the Shell service
        context = self.framework.get_bundle_context()
        svc_ref = context.get_service_reference(pelix.shell.SERVICE_SHELL)
        self.shell = context.get_service(svc_ref)

    def _run_command(self, command, *args):
        """
        Runs the given command and returns the output stream
        """
        # String output
        str_output = StringIO()

        # Format command
        if args:
            command = command.format(*args)

        # Run command
        self.shell.execute(command, stdout=str_output)
        return str_output.getvalue()

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.shell = None
        self.framework = None

    def testFactoriesListing(self):
        """
        Tests listing of factories
        """
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            # List factories
            output = self._run_command('factories')
            for factory_name in ipopo.get_factories():
                # Check that the factory has been listed
                self.assertIn(factory_name, output)

                details = ipopo.get_factory_details(factory_name)
                for command in ('factory', 'factories'):
                    # Check its details
                    subout = self._run_command(
                        '{0} {1}', command, factory_name)

                    # Check name and bundle
                    self.assertIn(factory_name, subout)
                    self.assertIn(
                        details['bundle'].get_symbolic_name(), subout)

    def testInstancesListing(self):
        """
        Tests listing of instances
        """
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            # List instances
            output = self._run_command('instances')
            for details in ipopo.get_instances():
                # Get instance details
                name = details[0]
                factory = details[1]

                # Check that the instance has been listed
                self.assertIn(name, output)

                details = ipopo.get_instance_details(name)
                for command in ('instance', 'instances'):
                    # Check its details
                    subout = self._run_command('{0} {1}', command, name)

                    # Check name, factory and bundle
                    self.assertIn(name, subout)
                    self.assertIn(factory, subout)

    def testWaitingListing(self):
        """
        Tests listing the waiting instances
        """
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            # List waiting instances
            output = self._run_command('waiting')
            for details in ipopo.get_waiting_components():
                # Get instance details
                name = details[0]
                factory = details[1]

                # Check that the instance has been listed
                self.assertIn(name, output)

                # Check its details
                subout = self._run_command('waiting {0}', name)

                # Check name, factory and bundle
                self.assertIn(name, subout)
                self.assertIn(factory, subout)

    def testUnknownDetails(self):
        """
        Tests details of unknown factory or instance
        """
        for command in ('factory', 'instance'):
            output = self._run_command('{0} <unknown>', command)
            self.assertIn("error", output.lower())

    def testLifeCycle(self):
        """
        Tests the instantiation of a components
        """
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            # Instantiate a dummy component (from test.ipopo.ipopo_bundle)
            factory = "ipopo.tests.a"
            name = "component-shell-test"

            # Check if we're clear
            self.assertFalse(ipopo.is_registered_instance(name))

            # Instantiate the component
            self._run_command("instantiate {0} {1}", factory, name)

            # Check that the component is instantiated
            self.assertTrue(ipopo.is_registered_instance(name))

            # Instantiate it a second time (no exception must raise)
            self._run_command("instantiate {0} {1}", factory, name)

            # Kill it
            self._run_command("kill {0}", name)

            # Check that it is dead
            self.assertFalse(ipopo.is_registered_instance(name))

            # Kill it a second time (no exception must raise)
            self._run_command("kill {0}", name)

    def testInvalidInstantiate(self):
        """
        Tests invalid parameters to instantiate and kill
        """
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            # Bad factory name
            self._run_command("instantiate <badfactory> good_name")
            self.assertFalse(ipopo.is_registered_instance('good_name'))

            # Bad component name
            self._run_command("kill <bad_component>")
