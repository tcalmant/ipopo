#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the shell core module

:author: Thomas Calmant
"""

# Pelix
from pelix.framework import FrameworkFactory, create_framework, Bundle
import pelix.constants as constants

# Shell constants
from pelix.shell import SERVICE_SHELL, SERVICE_SHELL_COMMAND, \
    SERVICE_SHELL_UTILS

# Standard library
import os
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

# Tests
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class ShellUtilsTest(unittest.TestCase):
    """
    Tests the shell utility service
    """
    def setUp(self):
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Install the bundle
        self.context.install_bundle("pelix.shell.core").start()

        # Get the utility service
        svc_ref = self.context.get_service_reference(SERVICE_SHELL_UTILS)
        self.utility = self.context.get_service(svc_ref)

    def tearDown(self):
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)
        self.utility = None
        self.context = None
        self.framework = None

    def testTableSimple(self):
        """
        Tests a valid table creation
        """
        headers = ('ID', 'Name', 'Properties')
        lines = [(12, 'Toto', {'valid': True}),
                 (True, [1, 2, 3], (1, 2, 3))]

        # Test without prefix
        result = """+------+-----------+-----------------+
|  ID  |   Name    |   Properties    |
+======+===========+=================+
| 12   | Toto      | {'valid': True} |
+------+-----------+-----------------+
| True | [1, 2, 3] | (1, 2, 3)       |
+------+-----------+-----------------+
"""
        self.assertEqual(self.utility.make_table(headers, lines),
                         result, "Different outputs")

        # Test with prefix
        result = """  +------+-----------+-----------------+
  |  ID  |   Name    |   Properties    |
  +======+===========+=================+
  | 12   | Toto      | {'valid': True} |
  +------+-----------+-----------------+
  | True | [1, 2, 3] | (1, 2, 3)       |
  +------+-----------+-----------------+
"""
        self.assertEqual(self.utility.make_table(headers, lines, '  '),
                         result, "Different outputs")

    def testTableEmpty(self):
        """
        Tests the creation of an empty table
        """
        headers = ('ID', 'Name', 'Properties')

        result = """+----+------+------------+
| ID | Name | Properties |
+====+======+============+
"""
        self.assertEqual(self.utility.make_table(headers, []),
                         result, "Different outputs")

    def testTableBadCount(self):
        """
        Tests the creation of table with different headers/columns count
        """
        headers = ('ID', 'Name', 'Properties')
        bad_columns_1 = [(1, 2, 3, 4)]
        bad_columns_2 = [(1, 2, 3),
                         (4, 5)]

        self.assertRaises(ValueError, self.utility.make_table,
                          headers, bad_columns_1,
                          "Too many columns accepted")

        self.assertRaises(ValueError, self.utility.make_table,
                          headers, bad_columns_2,
                          "Missing columns accepted")

    def testTableBadType(self):
        """
        Tests invalid types of line
        """
        headers = ('ID', 'Name', 'Properties')

        for bad_line in (None, 12, object()):
            self.assertRaises(ValueError, self.utility.make_table,
                              headers, [bad_line],
                              "Bad line type accepted")

# ------------------------------------------------------------------------------


class ShellCoreTest(unittest.TestCase):

    """
    Tests the shell core service
    """

    def setUp(self):
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Install the bundle
        self.context.install_bundle("pelix.shell.core").start()

        # Get the utility service
        svc_ref = self.context.get_service_reference(SERVICE_SHELL)
        self.shell = self.context.get_service(svc_ref)

        # Command flags
        self._flag = False

    def tearDown(self):
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)
        self.shell = None
        self.context = None
        self.framework = None
        self._flag = False

    def _command1(self, io_handler):
        """
        Test command
        """
        self._flag = True

    def testRegister(self):
        """
        Tests registration method
        """
        # 1st registration
        self.assertTrue(self.shell.register_command("test", "command",
                                                    self._command1),
                        "Command not registered")

        # 2nd registration
        self.assertFalse(self.shell.register_command("test", "command",
                                                     self._command1),
                         "Command registered twice")

        # Invalid command
        for invalid in (None, "", "  "):
            self.assertFalse(
                self.shell.register_command("test", invalid, self._command1),
                "Invalid command registered: '{0}'".format(invalid))

        # Invalid method
        self.assertFalse(self.shell.register_command("test", "invalid", None),
                         "Invalid method registered")

    def testExecute(self):
        """
        Tests the execute() method
        """
        # Registration
        self.shell.register_command("test", "command", self._command1)
        self.assertFalse(self._flag, "Bad flag value")

        # Call it (complete name)
        self.assertTrue(self.shell.execute("test.command"),
                        "Error in executing 'test.command'")
        self.assertTrue(self._flag, "Command not called")

        # Call it (simple name)
        self._flag = False
        self.assertTrue(self.shell.execute("command"),
                        "Error in executing 'command'")
        self.assertTrue(self._flag, "Command not called")

    def testExecuteInvalid(self):
        """
        Tests execution of empty or unknown commands
        """
        # Empty line
        for empty in (None, "", "   "):
            self.assertFalse(self.shell.execute(empty),
                             "No error executing '{0}'".format(empty))

        # Unknown command
        for unknown in ("unknown", "test.unknown", "unknown.unknown"):
            self.assertFalse(self.shell.execute(unknown),
                             "No error executing unknown command")

    def testUnregister(self):
        """
        Tests command unregistration
        """
        # Registration
        self.shell.register_command("test", "command", self._command1)
        self.assertFalse(self._flag, "Bad flag value")

        # Call it (complete name)
        self.assertTrue(self.shell.execute("test.command"),
                        "Error in executing 'test.command'")
        self.assertTrue(self._flag, "Command not called")

        # Unregister the command
        self._flag = False
        self.assertTrue(self.shell.unregister("test", "command"),
                        "Failed unregistration")
        self.assertFalse(self.shell.unregister("test", "command"),
                         "Unregistered twice")

        # Check next call
        self.assertFalse(self.shell.execute("test.command"),
                         "Succeeded executing 'test.command'")
        self.assertFalse(self._flag, "Command called")

    def testGetters(self):
        """
        Tests get_*() methods
        """
        # No exception here
        self.assertIsNotNone(self.shell.get_ps1(), "No PS1")
        self.assertIsNotNone(self.shell.get_banner(), "No banner")

        # Name spaces
        self.assertEqual(self.shell.get_namespaces(), [],
                         "Invalid name spaces")
        self.assertIn("help", self.shell.get_commands(None),
                      "No help in default commands")
        self.assertEqual(self.shell.get_commands("test"), [],
                         "Test commands should be []")

        # Register a command
        self.shell.register_command("test", "command", self._command1)
        self.assertEqual(self.shell.get_namespaces(), ['test'],
                         "Invalid name spaces")
        self.assertIn("command", self.shell.get_commands('test'),
                      "Registered command not in get_commands")

    def testMultiplePossibilities(self):
        """
        Tests the execution of multiple command possibilities
        """
        self.shell.register_command("test", "command", self._command1)
        self.shell.register_command("test2", "command", self._command1)

        # Call them (complete name)
        for name in ("test.command", "test2.command"):
            self._flag = False
            self.assertTrue(self.shell.execute(name),
                            "Error in executing '{0}'".format(name))
            self.assertTrue(self._flag, "Command not called")

        # Simple name must fail
        self._flag = False
        self.assertFalse(self.shell.execute('command'),
                         "Error in executing 'command'")
        self.assertFalse(self._flag, "Command called")

# ------------------------------------------------------------------------------


class ShellCommandTest(unittest.TestCase):

    """
    Tests the shell core service
    """

    def setUp(self):
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Install the bundle
        self.context.install_bundle("pelix.shell.core").start()

        # Get the utility service
        svc_ref = self.context.get_service_reference(SERVICE_SHELL)
        self.shell = self.context.get_service(svc_ref)

    def tearDown(self):
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)
        self.shell = None
        self.context = None
        self.framework = None

    def testPositional(self):
        """
        Tests positional arguments
        """
        def command(io_handler, arg1, arg2):
            """
            Sample command
            """
            return arg1, arg2

        # Register the command
        self.shell.register_command('test', 'command', command)

        # Valid execution
        result = self.shell.execute('test.command a 2')
        self.assertEqual(result, ('a', '2'),
                         "Invalid result: {0}".format(result))

        # Invalid call
        for invalid in ([1], (1, 2, 3)):
            args = ' '.join(str(arg) for arg in invalid)
            self.assertFalse(self.shell.execute('test.command {0}'
                                                .format(args)),
                             "Invalid call passed")

    def testKeywords(self):
        """
        Tests positional arguments
        """
        def command(io_handler, arg1='15', **kwargs):
            """
            Sample command
            """
            return arg1, kwargs

        # Register the command
        self.shell.register_command('test', 'command', command)

        # Valid execution
        result = self.shell.execute('test.command arg1=12 a=2 b=abc')
        self.assertEqual(result, ('12', {'a': '2', 'b': 'abc'}),
                         "Invalid result: {0}".format(result))

        result = self.shell.execute('test.command 12')
        self.assertEqual(result, ('12', {}),
                         "Invalid result: {0}".format(result))

        result = self.shell.execute('test.command a=12')
        self.assertEqual(result, ('15', {'a': '12'}),
                         "Invalid result: {0}".format(result))

        # First '=' sign is the assignment  one,
        # shlex.split removes slashes
        result = self.shell.execute('test.command a=a=b b\=a=b')
        self.assertEqual(result, ('15', {'a': 'a=b', 'b': 'a=b'}),
                         "Invalid result: {0}".format(result))

        # Invalid call (2 arguments)
        self.assertFalse(self.shell.execute('test.command 1 2'),
                         "Invalid call passed")

    def testWhiteboard(self):
        """
        Tests commands registered by a service
        """
        class CommandService(object):

            """
            Command service
            """

            def __init__(self):
                self.flag = False

            def get_namespace(self):
                return "test"

            def get_methods(self):
                return [("command", self._command)]

            def _command(self, io_handler):
                self.flag = True

        # Create the service object
        service = CommandService()

        # Check state
        self.assertFalse(self.shell.execute("test.command"),
                         "'test.command' can be called")
        self.assertFalse(service.flag, "Bad flag value")

        # Register the service
        svc_reg = self.context.register_service(SERVICE_SHELL_COMMAND,
                                                service, {})

        # Test execution
        self.assertTrue(self.shell.execute("test.command"),
                        "Error in executing 'test.command'")
        self.assertTrue(service.flag, "Command not called")
        service.flag = False

        # Unregister the service
        svc_reg.unregister()
        svc_reg = None

        # Check state
        self.assertFalse(self.shell.execute("test.command"),
                         "'test.command' can still be called")
        self.assertFalse(service.flag, "Bad flag value")

# ------------------------------------------------------------------------------


class ShellCoreCommandsTest(unittest.TestCase):

    """
    Tests the shell core commands
    """

    def setUp(self):
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = create_framework(['pelix.shell.core'])
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        svc_ref = self.context.get_service_reference(SERVICE_SHELL)
        self.shell = self.context.get_service(svc_ref)

    def tearDown(self):
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)
        self.shell = None
        self.context = None
        self.framework = None

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

    def testHelp(self):
        """
        Tests the help command
        """
        # Register some commands
        self.shell.register_command("test", "dummy", self.testHelp)

        # All commands
        output = self._run_command('help')
        for namespace in self.shell.get_namespaces():
            self.assertIn(namespace, output)
            for command in self.shell.get_commands(namespace):
                self.assertIn(command, output)

        # Namespace commands
        for namespace in self.shell.get_namespaces():
            output = self._run_command('help {0}', namespace)
            self.assertIn(namespace, output)
            for command in self.shell.get_commands(namespace):
                self.assertIn(command, output)

        # Commands
        for namespace in self.shell.get_namespaces():
            for command in self.shell.get_commands(namespace):
                output = self._run_command('help {0}', command)
                self.assertIn(namespace, output)
                self.assertIn(command, output)

    def testEcho(self):
        """
        Tests the echo command
        """
        echo_value = "Hello, World !"
        output = self._run_command("echo {0}", echo_value)
        self.assertEqual(output.strip(), echo_value)

    def testBundlesInfo(self):
        """
        Tests the bd and bl commands
        """
        # Install a bundle with another prefix
        self.context.install_bundle("tests.interfaces")

        # List of bundles
        output = self._run_command('bl')

        # Ensure that all bundles have been listed
        for bundle in self.context.get_bundles():
            self.assertIn(str(bundle.get_bundle_id()), output)
            self.assertIn(bundle.get_symbolic_name(), output)
            self.assertIn(str(bundle.get_version()), output)

        # Test filter by name: all pelix bundles
        for prefix in ('pelix', 'tests', 'pelix.shell'):
            output = self._run_command('bl {0}', prefix)
            for bundle in self.context.get_bundles():
                name = bundle.get_symbolic_name()
                if name.startswith(prefix):
                    self.assertIn(name, output)

        # Test bundle details
        for bundle in self.context.get_bundles():
            for selector in (bundle.get_bundle_id(),
                             bundle.get_symbolic_name()):
                output = self._run_command('bd {0}', selector)
                self.assertIn(str(bundle.get_bundle_id()), output)
                self.assertIn(bundle.get_symbolic_name(), output)
                self.assertIn(str(bundle.get_version()), output)

        # Test invalid bundle
        output = self._run_command('bd {0}', -1)
        self.assertIn("Unknown bundle", output)
        output = self._run_command('bd aaa')
        self.assertIn("Unknown bundle", output)

    def testBundlesCommands(self):
        """
        Tests the install, start, update, stop and uninstall commands
        """
        # Install a bundle
        output = self._run_command('install pelix.ipopo.core')

        # Find it
        bundle = self.context.get_bundles()[-1]
        bundle_id = bundle.get_bundle_id()

        # The bundle ID should have been printed
        # and the bundle must be installed or resolved
        self.assertIn(str(bundle_id), output)
        self.assertIn(bundle.get_state(), (Bundle.INSTALLED, Bundle.RESOLVED))

        # Start the bundle
        self._run_command('start {0}', bundle_id)
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE)

        # Update the bundle
        self._run_command('update {0}', bundle_id)
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE)

        # Stop it
        self._run_command('stop {0}', bundle_id)
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED)

        # Uninstall it
        self._run_command('uninstall {0}', bundle_id)
        self.assertEqual(bundle.get_state(), Bundle.UNINSTALLED)
        self.assertNotIn(bundle, self.context.get_bundles())

        # Test invalid command arguments
        for command in ('start', 'update', 'stop', 'uninstall'):
            output = self._run_command('{0} aaa', command)
            self.assertIn("Invalid bundle ID", output)

            output = self._run_command('{0} {1}', command, -1)
            self.assertIn("Unknown bundle", output)

    def testServicesInfo(self):
        """
        Tests the sl and sd commands
        """
        # Get all services references
        svc_refs = self.context.get_all_service_references(None, None)
        specs = set()
        for svc_ref in svc_refs:
            specs.update(svc_ref.get_property(constants.OBJECTCLASS))

        # List all services
        output = self._run_command('sl')

        # Check their presence
        for svc_ref in svc_refs:
            self.assertIn(str(svc_ref.get_property(constants.SERVICE_ID)),
                          output)
            for spec in svc_ref.get_property(constants.OBJECTCLASS):
                self.assertIn(spec, output)

        # Check the specification filter
        for spec in specs:
            output = self._run_command('sl {0}', spec)
            self.assertIn(spec, output)
            for svc_ref in svc_refs:
                svc_id = str(svc_ref.get_property(constants.SERVICE_ID))
                if spec in svc_ref.get_property(constants.OBJECTCLASS):
                    self.assertIn(svc_id, output)

        # Check invalid filter
        output = self._run_command('sl <inexistent>')
        self.assertIn("No service provides", output)

        # Check details
        for svc_ref in svc_refs:
            svc_id = str(svc_ref.get_property(constants.SERVICE_ID))
            output = self._run_command('sd {0}', svc_id)
            self.assertIn(svc_id, output)
            self.assertIn(str(svc_ref.get_bundle()), output)
            for spec in svc_ref.get_property(constants.OBJECTCLASS):
                self.assertIn(spec, output)

        # Invalid IDs
        for invalid in (-1, '<invalid>', '-10'):
            output = self._run_command('sd {0}', invalid)
            self.assertIn('Service not found', output)

    def testProperties(self):
        """
        Tests the properties and property commands
        """
        output = self._run_command("properties")

        # Extract all properties
        props = {}
        for line in output.split('\n'):
            if line.startswith('|'):
                # Value line, name column
                values = line.split('|')
                name, value = values[1].strip(), values[2].strip()
                if name and name != 'Property Name':
                    props[name] = value

        # Check their values
        for name, value in self.framework.get_properties().items():
            self.assertEqual(str(props[name]), value)

        # Check each property
        for name, value in props.items():
            output = self._run_command("property {0}", name)
            self.assertIn(value, output.strip())

        # Check invalid property
        output = self._run_command('property <<invalid>>')
        self.assertEqual("", output.strip())

    def testEnvironment(self):
        """
        Tests the sysprops and sysprop commands
        """
        output = self._run_command("sysprops")

        # Extract all variables
        props = {}
        for line in output.split('\n'):
            if line.startswith('|'):
                # Value line, name column
                idx_separator = line.find('|', 1)
                name = line[1:idx_separator].strip()
                value = line[idx_separator + 1:-1].strip()
                if name and name != 'Environment Variable':
                    props[name] = value

        # Check their values
        for name, value in os.environ.items():
            self.assertEqual(str(props[name]), value)

        # Check each variable
        for name, value in props.items():
            output = self._run_command("sysprop {0}", name)
            self.assertIn(value, output.strip())

        # Check invalid variable
        output = self._run_command('sysprop <<invalid>>')
        self.assertEqual("", output.strip())

    def testThreads(self):
        """
        Tests the threads and thread commands
        """
        output = self._run_command('threads')

        # Get all threads
        threads = []
        for line in output.split('\n'):
            if line.startswith('Thread ID:'):
                thread_id = int(line.split(':')[1].split('-')[0])
                threads.append(thread_id)

        # Check each thread
        for thread_id in threads:
            output = self._run_command('thread {0}', thread_id)

        # Check invalid thread
        output = self._run_command('thread -1')
        self.assertIn("Unknown thread", output)

        output = self._run_command('thread aaa')
        self.assertIn("Invalid thread", output)

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
