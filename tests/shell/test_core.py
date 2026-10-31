#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the shell core module

:author: Thomas Calmant
"""

import os
import random
import sys
import unittest
from io import StringIO
from typing import Any, cast
from unittest import mock

from pelix import constants
from pelix.framework import Bundle, BundleContext, Framework, FrameworkFactory, create_framework
from pelix.internals.registry import ServiceReference
from pelix.ipopo.constants import use_ipopo
from pelix.security import Secret
from pelix.shell import (
    PERMISSION_ADMIN,
    PERMISSION_READ,
    CommandPermission,
    ShellCommandMethod,
    ShellCommandsProvider,
    ShellService,
    ShellUtils,
    beans,
    parser,
)
from pelix.shell import core as shell_core

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def local_session() -> beans.ShellSession:
    """
    Makes a session of the console kind, where no permission is checked
    """
    return beans.ShellSession(beans.IOHandler(sys.stdin, sys.stdout), trusted=True)


class ShellUtilsTest(unittest.TestCase):
    """
    Tests the shell utility service
    """

    framework: Framework
    context: BundleContext
    utility: ShellUtils

    def setUp(self) -> None:
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Install the bundle
        self.context.install_bundle("pelix.shell.core").start()

        # Get the utility service
        svc_ref = self.context.get_service_reference(ShellUtils)
        assert svc_ref is not None
        self.utility = self.context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()
        self.utility = None
        self.context = None  # type: ignore
        self.framework = None  # type: ignore

    def testTableSimple(self) -> None:
        """
        Tests a valid table creation
        """
        headers = ("ID", "Name", "Properties")
        lines = [(12, "Toto", {"valid": True}), (True, [1, 2, 3], (1, 2, 3))]

        # Test without prefix
        result = """+------+-----------+-----------------+
|  ID  |   Name    |   Properties    |
+======+===========+=================+
| 12   | Toto      | {'valid': True} |
+------+-----------+-----------------+
| True | [1, 2, 3] | (1, 2, 3)       |
+------+-----------+-----------------+
"""
        self.assertEqual(self.utility.make_table(headers, lines), result, "Different outputs")

        # Test with prefix
        result = """  +------+-----------+-----------------+
  |  ID  |   Name    |   Properties    |
  +======+===========+=================+
  | 12   | Toto      | {'valid': True} |
  +------+-----------+-----------------+
  | True | [1, 2, 3] | (1, 2, 3)       |
  +------+-----------+-----------------+
"""
        self.assertEqual(self.utility.make_table(headers, lines, "  "), result, "Different outputs")

    def testTableEmpty(self) -> None:
        """
        Tests the creation of an empty table
        """
        headers = ("ID", "Name", "Properties")

        result = """+----+------+------------+
| ID | Name | Properties |
+====+======+============+
"""
        self.assertEqual(self.utility.make_table(headers, []), result, "Different outputs")

    def testTableBadCount(self) -> None:
        """
        Tests the creation of table with different headers/columns count
        """
        headers = ("ID", "Name", "Properties")
        bad_columns_1 = [(1, 2, 3, 4)]
        bad_columns_2 = [(1, 2, 3), (4, 5)]

        self.assertRaises(
            ValueError, self.utility.make_table, headers, bad_columns_1, "Too many columns accepted"
        )

        self.assertRaises(
            ValueError, self.utility.make_table, headers, bad_columns_2, "Missing columns accepted"
        )

    def testTableBadType(self) -> None:
        """
        Tests invalid types of line
        """
        headers = ("ID", "Name", "Properties")

        for bad_line in (None, 12, object()):
            self.assertRaises(
                ValueError, self.utility.make_table, headers, [bad_line], "Bad line type accepted"
            )

    def testTableLayout(self) -> None:
        """
        Tests the cells which are not plain text, and the width
        """
        cells = shell_core._cells
        long_row = ("pelix.ipopo.handlers.requiresbroadcast", "a long description of the bundle, with words")
        cases: list[tuple[str, tuple[str, ...], list[Any], int | None]] = [
            ("newline", ("A", "B"), [("x\ny", "z")], None),
            ("wide", ("A", "B"), [("\u65e5\u672c\u8a9e", "z"), ("abc", "z")], None),
            ("combining", ("A", "B"), [("e\u0301", "z"), ("e", "z")], None),
            ("tab", ("A", "B"), [("a\tb", "z"), ("a    b", "z")], None),
            ("fits", ("Name", "Text"), [long_row], 200),
            ("wrap", ("Name", "Text"), [long_row], 60),
            ("narrow", ("Name", "Text"), [long_row], 40),
            ("floor", ("Name", "Text"), [long_row], 20),
            ("wide-cut", ("A",), [("\u65e5" * 20,)], 12),
        ]
        for name, headers, lines, width in cases:
            with self.subTest(name):
                table = self.utility.make_table(headers, lines, None, width)
                physical = table.splitlines()

                # Aligned in terminal cells
                self.assertEqual(1, len({cells(line) for line in physical}), table)

                # Nothing lost
                joined = "".join(table.split())
                for entry in "".join(str(e) for line in lines for e in line).expandtabs(4).split():
                    for char in entry:
                        self.assertIn(char, joined)

                # Narrower than asked, unless the floors (header or 8 cells) prevent it
                if width is not None and name in ("wrap", "narrow"):
                    self.assertLessEqual(cells(physical[0]), width)

        # No width: the table is only as wide as its content
        self.assertEqual(
            self.utility.make_table(("Name", "Text"), [long_row]),
            self.utility.make_table(("Name", "Text"), [long_row], None, None),
        )
        self.assertEqual(
            "| pelix.ipopo.handlers.requiresbroadcast | a long",
            self.utility.make_table(("Name", "Text"), [long_row]).splitlines()[3][:49],
        )

        # The break prefers a separator
        wrapped = self.utility.make_table(("Name", "Text"), [long_row], None, 60)
        self.assertIn("pelix.ipopo.handlers.  ", wrapped)
        self.assertIn("requiresbroadcast", wrapped)

    def testTableBadTypeMessage(self) -> None:
        """
        Tests that the error message is formatted
        """
        with self.assertRaisesRegex(ValueError, "^Invalid type of line: int$"):
            self.utility.make_table(("A",), [12])

    def testTableFuzz(self) -> None:
        """
        Tests random tables: aligned, nothing lost
        """
        rnd = random.Random(42)
        alphabet = "abcdefghij./_- \n\t\u65e5\u672ce\u0301"
        for _ in range(300):
            cols = rnd.randint(1, 5)
            headers = ["".join(rnd.choices("ABCDEFGH", k=rnd.randint(1, 8))) for _ in range(cols)]
            rows = [
                ["".join(rnd.choices(alphabet, k=rnd.randint(0, 60))) for _ in range(cols)]
                for _ in range(rnd.randint(0, 4))
            ]
            width = rnd.choice([None, 10, 20, 40, 80])
            table = self.utility.make_table(headers, rows, rnd.choice([None, "  "]), width)
            self.assertEqual(1, len({shell_core._cells(line) for line in table.splitlines()}), table)
            joined = "".join(table.split())
            for text in (text for row in rows for text in row):
                for char in "".join(text.expandtabs(4).split()):
                    self.assertIn(char, joined)


# ------------------------------------------------------------------------------


class ShellCoreTest(unittest.TestCase):
    """
    Tests the shell core service
    """

    framework: Framework
    context: BundleContext
    shell: ShellService

    def setUp(self) -> None:
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Install the bundle
        self.context.install_bundle("pelix.shell.core").start()

        # Get the utility service
        svc_ref = self.context.get_service_reference(ShellService)
        assert svc_ref is not None
        self.shell = self.context.get_service(svc_ref)

        # Command flags
        self._flag = False

    def tearDown(self) -> None:
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()
        self.shell = None
        self.context = None  # type: ignore
        self.framework = None  # type: ignore
        self._flag = False

    def _command1(self, io_handler: beans.ShellSession) -> None:
        """
        Test command
        """
        self._flag = True

    def testRegister(self) -> None:
        """
        Tests registration method
        """
        # 1st registration
        self.assertTrue(
            self.shell.register_command("test", "command", self._command1), "Command not registered"
        )

        # 2nd registration
        self.assertFalse(
            self.shell.register_command("test", "command", self._command1), "Command registered twice"
        )

        # Invalid command
        for invalid in (None, "", "  "):
            self.assertFalse(
                self.shell.register_command("test", invalid, self._command1),
                f"Invalid command registered: '{invalid}'",
            )

        # Invalid method
        self.assertFalse(
            self.shell.register_command("test", "invalid", None),
            "Invalid method registered",
        )

    def testExecute(self) -> None:
        """
        Tests the execute() method
        """
        # Registration
        self.shell.register_command("test", "command", self._command1)
        self.assertFalse(self._flag, "Bad flag value")

        # Call it (complete name)
        self.assertTrue(
            self.shell.execute("test.command", local_session()), "Error in executing 'test.command'"
        )
        self.assertTrue(self._flag, "Command not called")

        # Call it (simple name)
        self._flag = False
        self.assertTrue(self.shell.execute("command", local_session()), "Error in executing 'command'")
        self.assertTrue(self._flag, "Command not called")

    def testExecuteInvalid(self) -> None:
        """
        Tests execution of empty or unknown commands
        """
        # Empty line
        for empty in (None, "", "   "):
            self.assertFalse(self.shell.execute(empty, local_session()), f"No error executing '{empty}'")

        # Unknown command
        for unknown in ("unknown", "test.unknown", "unknown.unknown"):
            self.assertFalse(
                self.shell.execute(unknown, local_session()), "No error executing unknown command"
            )

    def testUnregister(self) -> None:
        """
        Tests command unregistration
        """
        # Registration
        self.shell.register_command("test", "command", self._command1)
        self.assertFalse(self._flag, "Bad flag value")

        # Call it (complete name)
        self.assertTrue(
            self.shell.execute("test.command", local_session()), "Error in executing 'test.command'"
        )
        self.assertTrue(self._flag, "Command not called")

        # Unregister the command
        self._flag = False
        self.assertTrue(self.shell.unregister("test", "command"), "Failed unregistration")
        self.assertFalse(self.shell.unregister("test", "command"), "Unregistered twice")

        # Check next call
        self.assertFalse(
            self.shell.execute("test.command", local_session()), "Succeeded executing 'test.command'"
        )
        self.assertFalse(self._flag, "Command called")

    def testGetters(self) -> None:
        """
        Tests get_*() methods
        """
        # No exception here
        self.assertIsNotNone(self.shell.get_ps1(), "No PS1")
        self.assertIsNotNone(self.shell.get_banner(), "No banner")

        # Name spaces
        self.assertEqual(self.shell.get_namespaces(), [], "Invalid name spaces")
        self.assertIn("help", self.shell.get_commands(None), "No help in default commands")
        self.assertEqual(self.shell.get_commands("test"), [], "Test commands should be []")

        # Register a command
        self.shell.register_command("test", "command", self._command1)
        self.assertEqual(self.shell.get_namespaces(), ["test"], "Invalid name spaces")
        self.assertIn("command", self.shell.get_commands("test"), "Registered command not in get_commands")

    def testMultiplePossibilities(self) -> None:
        """
        Tests the execution of multiple command possibilities
        """
        self.shell.register_command("test", "command", self._command1)
        self.shell.register_command("test2", "command", self._command1)

        # Call them (complete name)
        for name in ("test.command", "test2.command"):
            self._flag = False
            self.assertTrue(self.shell.execute(name, local_session()), f"Error in executing '{name}'")
            self.assertTrue(self._flag, "Command not called")

        # Simple name must fail
        self._flag = False
        self.assertFalse(self.shell.execute("command", local_session()), "Error in executing 'command'")
        self.assertFalse(self._flag, "Command called")


# ------------------------------------------------------------------------------


class CommandPermissionTest(unittest.TestCase):
    """
    Tests the permission a command declares
    """

    def test_required_permission(self) -> None:
        """
        Only an explicit declaration lowers the default admin permission
        """

        def undeclared(session: beans.ShellSession) -> None:
            pass

        for method, expected in (
            (CommandPermission(PERMISSION_READ)(lambda session: None), PERMISSION_READ),
            (CommandPermission(None)(lambda session: None), None),
            (undeclared, PERMISSION_ADMIN),
            # A proxy answering any attribute declares nothing
            (mock.Mock(), PERMISSION_ADMIN),
        ):
            with self.subTest(method=method):
                self.assertEqual(parser._required_permission(method), expected)


class ShellCommandTest(unittest.TestCase):
    """
    Tests the shell core service
    """

    framework: Framework
    context: BundleContext
    shell: ShellService

    def setUp(self) -> None:
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Install the bundle
        self.context.install_bundle("pelix.shell.core").start()

        # Get the utility service
        svc_ref = self.context.get_service_reference(ShellService)
        assert svc_ref is not None
        self.shell = self.context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()
        self.shell = None
        self.context = None  # type: ignore
        self.framework = None  # type: ignore

    def testPositional(self) -> None:
        """
        Tests positional arguments
        """

        def command(io_handler: beans.ShellSession, arg1: Any, arg2: Any) -> tuple[Any, Any]:
            """
            Sample command
            """
            return arg1, arg2

        # Register the command
        self.shell.register_command("test", "command", command)

        # Valid execution
        session = beans.ShellSession(beans.IOHandler(sys.stdin, sys.stdout), trusted=True)
        self.assertTrue(self.shell.execute("test.command a 2", session))
        result = session.last_result
        self.assertEqual(result, ("a", "2"))

        # Invalid call
        for invalid in ([1], (1, 2, 3)):
            args = " ".join(str(arg) for arg in invalid)
            self.assertFalse(
                self.shell.execute(f"test.command {args}", local_session()), "Invalid call passed"
            )

    def testKeywords(self) -> None:
        """
        Tests positional arguments
        """

        def command(io_handler: beans.ShellSession, arg1: Any = "15", **kwargs: Any) -> tuple[Any, Any]:
            """
            Sample command
            """
            return arg1, kwargs

        # Register the command
        self.shell.register_command("test", "command", command)

        # Prepare the session
        session = beans.ShellSession(beans.IOHandler(sys.stdin, sys.stdout), trusted=True)

        # Valid execution
        self.shell.execute("test.command arg1=12 a=2 b=abc", session)
        result = session.last_result
        self.assertEqual(result, ("12", {"a": "2", "b": "abc"}), f"Invalid result: {result}")

        self.shell.execute("test.command 12", session)
        result = session.last_result
        self.assertEqual(result, ("12", {}), f"Invalid result: {result}")

        self.shell.execute("test.command a=12", session)
        result = session.last_result
        self.assertEqual(result, ("15", {"a": "12"}), f"Invalid result: {result}")

        # First '=' sign is the assignment  one,
        # shlex.split removes slashes
        self.shell.execute(r"test.command a=a=b b\=a=b", session)
        result = session.last_result
        self.assertEqual(result, ("15", {"a": "a=b", "b": "a=b"}), f"Invalid result: {result}")

        # Invalid call (2 arguments)
        self.assertFalse(self.shell.execute("test.command 1 2", local_session()), "Invalid call passed")

    def testWhiteboard(self) -> None:
        """
        Tests commands registered by a service
        """

        class CommandService(ShellCommandsProvider):
            """
            Command service
            """

            def __init__(self) -> None:
                self.flag = False

            def get_namespace(self) -> str:
                return "test"

            def get_methods(self) -> list[tuple[str, ShellCommandMethod]]:
                return [("command", self._command)]

            def _command(self, io_handler: beans.ShellSession) -> None:
                self.flag = True

        # Create the service object
        service = CommandService()

        # Check state
        self.assertFalse(self.shell.execute("test.command", local_session()), "'test.command' can be called")
        self.assertFalse(service.flag, "Bad flag value")

        # Register the service
        svc_reg = self.context.register_service(ShellCommandsProvider, service, {})

        # Test execution
        self.assertTrue(
            self.shell.execute("test.command", local_session()), "Error in executing 'test.command'"
        )
        self.assertTrue(service.flag, "Command not called")
        service.flag = False

        # Unregister the service
        svc_reg.unregister()
        svc_reg = None

        # Check state
        self.assertFalse(
            self.shell.execute("test.command", local_session()), "'test.command' can still be called"
        )
        self.assertFalse(service.flag, "Bad flag value")


# ------------------------------------------------------------------------------


class ShellCoreCommandsTest(unittest.TestCase):
    """
    Tests the shell core commands
    """

    framework: Framework
    context: BundleContext
    shell: ShellService

    def setUp(self) -> None:
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = create_framework(["pelix.shell.core"])
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        svc_ref = self.context.get_service_reference(ShellService)
        assert svc_ref is not None
        self.shell = self.context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()
        self.shell = None
        self.context = None  # type: ignore
        self.framework = None  # type: ignore

    def _make_session(self) -> tuple[beans.ShellSession, StringIO]:
        """
        Prepares a ShellSession object for _run_command
        """
        # String output
        str_output = StringIO()

        # Session bean
        session = beans.ShellSession(beans.IOHandler(None, str_output), trusted=True)
        return session, str_output

    def _run_command(self, command: str, *args: Any, **kwargs: Any) -> str:
        """
        Runs the given command and returns the output stream. A keyword
        argument 'session' can be given to use a custom ShellSession.
        """
        # Format command
        if args:
            command = command.format(*args)

        try:
            # Get the given session
            session = kwargs["session"]
            str_output = kwargs["output"]
            str_output.truncate(0)
            str_output.seek(0)
        except KeyError:
            # No session given
            str_output = StringIO()
            session = beans.ShellSession(beans.IOHandler(None, str_output), trusted=True)

        # Run command
        self.shell.execute(command, session)
        return cast(str, str_output.getvalue())

    def testHelp(self) -> None:
        """
        Tests the help command
        """
        # Register some commands
        self.shell.register_command("test", "dummy", self.testHelp)

        # All commands
        output = self._run_command("help")
        for namespace in self.shell.get_namespaces():
            self.assertIn(namespace, output)
            for command in self.shell.get_commands(namespace):
                self.assertIn(command, output)

        # Namespace commands
        for namespace in self.shell.get_namespaces():
            output = self._run_command("help {0}", namespace)
            self.assertIn(namespace, output)
            for command in self.shell.get_commands(namespace):
                self.assertIn(command, output)

        # Commands
        for namespace in self.shell.get_namespaces():
            for command in self.shell.get_commands(namespace):
                output = self._run_command("help {0}", command)
                self.assertIn(namespace, output)
                self.assertIn(command, output)

    def testEcho(self) -> None:
        """
        Tests the echo command
        """
        echo_value = "Hello, World !"
        output = self._run_command("echo {0}", echo_value)
        self.assertEqual(output.strip(), echo_value)

    def test_variables(self) -> None:
        """
        Tests the set and unset commands. Also tests the substitution of
        variables
        """
        var_name = "toto"

        session, str_output = self._make_session()
        kwargs = {"session": session, "output": str_output}

        # No value set yet
        output = self._run_command("set", **kwargs)
        self.assertNotIn(var_name, output)
        self.assertRaises(KeyError, session.get, var_name)

        output = self._run_command("echo ${0}", var_name, **kwargs)
        self.assertEqual(output.strip(), "")

        old_value = None
        for value in ("Some value", "Another value"):
            # Set a value
            output = self._run_command(f"set {var_name}='{value}'", **kwargs)
            self.assertEqual(session.get(var_name), value)

            self.assertIn(var_name, output)
            self.assertIn(value, output)

            output = self._run_command("set", **kwargs)
            self.assertIn(var_name, output)
            self.assertIn(value, output)
            if old_value is not None:
                self.assertNotIn(old_value, output)

            # Test the output
            output = self._run_command("echo ${0}", var_name, **kwargs)
            self.assertEqual(output.strip(), value)
            old_value = value

        # Unset the value
        self._run_command("unset {0}", var_name, **kwargs)
        self.assertRaises(KeyError, session.get, var_name)

        output = self._run_command("echo ${0}", var_name, **kwargs)
        self.assertEqual(output.strip(), "")

        output = self._run_command("set", **kwargs)
        self.assertNotIn(var_name, output)

    def test_run_file(self) -> None:
        """
        Tests the run shell command
        """
        # Check bad file error
        self.assertFalse(self.shell.execute("run __fake_file__", local_session()))

        # Compute test file name
        filename = os.path.join(os.path.dirname(__file__), "rshell_starter.pelix")

        # Install iPOPO
        self.context.install_bundle("pelix.ipopo.core").start()
        self.context.install_bundle("pelix.shell.ipopo").start()

        # Prepare a session
        session = beans.ShellSession(beans.IOHandler(sys.stdin, sys.stdout), {"port": 0}, trusted=True)

        # Run the file a first time
        self.assertTrue(self.shell.execute(f"run '{filename}'", session))

        # Check the result
        self.assertEqual(session.get("rshell.name"), "rshell")

        # Check the bundle
        rshell_bundle = int(session.get("rshell.bundle"))
        bundle = self.context.get_bundle(rshell_bundle)
        self.assertEqual(bundle.get_symbolic_name(), "pelix.shell.remote")

        # Check the instance properties: the requested port was 0 (OS-assigned),
        # so check that a real port was bound instead of comparing against it
        with use_ipopo(self.context) as ipopo:
            details = ipopo.get_instance_details(session.get("rshell.name"))
            port = int(details["properties"]["pelix.shell.port"])
            self.assertGreater(port, 0)
            self.assertLess(port, 65536)

        # Run the file a second time: it must fail
        self.assertFalse(self.shell.execute(f"run '{filename}'", session))

    def testTableWidthFromColumns(self) -> None:
        """
        Tests that the COLUMNS variable of the session sets the width of the tables
        """
        self.context.install_bundle("tests.interfaces")
        session, output = self._make_session()
        widths = {}
        for columns in (None, 40, "40", 10, 1000, "bad"):
            with self.subTest(columns=columns):
                if columns is not None:
                    session.set("COLUMNS", columns)
                widths[columns] = max(
                    len(line) for line in self._run_command("bl", session=session, output=output).splitlines()
                )

        self.assertEqual(40, widths[40])
        self.assertEqual(40, widths["40"])
        # Ignored values: same as without the variable
        for columns in (10, 1000, "bad"):
            self.assertEqual(widths[None], widths[columns])
        self.assertGreater(widths[None], 40)

    def testBundlesInfo(self) -> None:
        """
        Tests the bd and bl commands
        """
        # Install a bundle with another prefix
        self.context.install_bundle("tests.interfaces")

        # List of bundles
        output = self._run_command("bl")

        # Ensure that all bundles have been listed
        for bundle in self.context.get_bundles():
            self.assertIn(str(bundle.get_bundle_id()), output)
            self.assertIn(bundle.get_symbolic_name(), output)
            self.assertIn(str(bundle.get_version()), output)

        # Test filter by name: all pelix bundles
        for prefix in ("pelix", "tests", "pelix.shell"):
            output = self._run_command("bl {0}", prefix)
            for bundle in self.context.get_bundles():
                name = bundle.get_symbolic_name()
                if name.startswith(prefix):
                    self.assertIn(name, output)

        # Test bundle details
        for bundle in self.context.get_bundles():
            for selector in (bundle.get_bundle_id(), bundle.get_symbolic_name()):
                output = self._run_command("bd {0}", selector)
                self.assertIn(str(bundle.get_bundle_id()), output)
                self.assertIn(bundle.get_symbolic_name(), output)
                self.assertIn(str(bundle.get_version()), output)

        # Test invalid bundle
        output = self._run_command("bd {0}", -1)
        self.assertIn("Unknown bundle", output)
        output = self._run_command("bd aaa")
        self.assertIn("Unknown bundle", output)

    def testUpdateFailure(self) -> None:
        """
        Tests that the update command reports a failed update
        """
        bundle_id = self.context.get_bundle().get_bundle_id()
        with mock.patch.object(Framework, "update", side_effect=constants.BundleException("boom")):
            output = self._run_command("update {0}", bundle_id)
        self.assertIn("Update failed: boom", output)

    def testBundlesCommands(self) -> None:
        """
        Tests the install, start, update, stop and uninstall commands
        """
        # Install a bundle
        output = self._run_command("install pelix.http.basic")

        # Find it
        bundle = self.context.get_bundles()[-1]
        bundle_id = bundle.get_bundle_id()

        # The bundle ID should have been printed
        # and the bundle must be installed or resolved
        self.assertIn(str(bundle_id), output)
        self.assertIn(bundle.get_state(), (Bundle.INSTALLED, Bundle.RESOLVED))

        # Start the bundle
        self._run_command("start {0}", bundle_id)
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE)

        # Update the bundle
        self._run_command("update {0}", bundle_id)
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE)

        # Stop it
        self._run_command("stop {0}", bundle_id)
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED)

        # Uninstall it
        self._run_command("uninstall {0}", bundle_id)
        self.assertEqual(bundle.get_state(), Bundle.UNINSTALLED)
        self.assertNotIn(bundle, self.context.get_bundles())

        # Test invalid command arguments
        for command in ("update", "stop", "uninstall"):
            output = self._run_command("{0} aaa", command)
            self.assertIn("Invalid bundle ID", output)

            output = self._run_command("{0} {1}", command, -1)
            self.assertIn("Unknown bundle", output)

    def testBundleNameStart(self) -> None:
        """
        Tests the bundle start feature with
        :return:
        """
        # Install a bundle
        output = self._run_command("start pelix.http.basic")

        # Find it and check its state
        bundle = self.context.get_bundles()[-1]
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE)

        # Check command output
        bundle_id = bundle.get_bundle_id()
        self.assertIn(str(bundle_id), output)

    def testServicesInfo(self) -> None:
        """
        Tests the sl and sd commands
        """
        # Get all services references
        svc_refs: list[ServiceReference[Any]] | None = self.context.get_all_service_references(None, None)
        assert svc_refs is not None
        specs = set()
        for svc_ref in svc_refs:
            specs.update(svc_ref.get_property(constants.OBJECTCLASS))

        # List all services
        output = self._run_command("sl")

        # Check their presence
        for svc_ref in svc_refs:
            self.assertIn(str(svc_ref.get_property(constants.SERVICE_ID)), output)
            for spec in svc_ref.get_property(constants.OBJECTCLASS):
                self.assertIn(spec, output)

        # Check the specification filter
        for spec in specs:
            output = self._run_command(f"sl {spec}")
            self.assertIn(spec, output)
            for svc_ref in svc_refs:
                svc_id = str(svc_ref.get_property(constants.SERVICE_ID))
                if spec in svc_ref.get_property(constants.OBJECTCLASS):
                    self.assertIn(svc_id, output)

        # Check unknown specification
        output = self._run_command("sl inexistent.spec")
        self.assertIn("No service provides", output)

        # Check invalid specification name
        output = self._run_command("sl <inexistent>")
        self.assertIn("Invalid specification", output)

        # Check details
        for svc_ref in svc_refs:
            svc_id = str(svc_ref.get_property(constants.SERVICE_ID))
            output = self._run_command(f"sd {svc_id}")
            self.assertIn(svc_id, output)
            self.assertIn(str(svc_ref.get_bundle()), output)
            for spec in svc_ref.get_property(constants.OBJECTCLASS):
                self.assertIn(spec, output)

        # Unknown IDs
        for unknown in (-1, "-10", 999999):
            output = self._run_command(f"sd {unknown}")
            self.assertIn("Service not found", output)

        # Invalid IDs, including filter injections
        for invalid in ("<invalid>", "*", "1)(|(service.id>0)", "1.5"):
            output = self._run_command(f"sd {invalid}")
            self.assertIn("Invalid service ID", output)
            self.assertNotIn("Specifications", output)

    def testProperties(self) -> None:
        """
        Tests the properties and property commands
        """
        output = self._run_command("properties")

        # Extract all properties
        props = {}
        for line in output.split("\n"):
            if line.startswith("|"):
                # Value line, name column
                values = line.split("|")
                name, value = values[1].strip(), values[2].strip()
                if name and name != "Property Name":
                    props[name] = value

        # Check their values
        for name, value in self.framework.get_properties().items():
            self.assertEqual(str(props[name]), value)

        # Check each property
        for name, value in props.items():
            output = self._run_command(f"property {name}")
            self.assertIn(value, output.strip())

        # Check invalid property
        output = self._run_command("property <<invalid>>")
        self.assertEqual("", output.strip())

    def testEnvironment(self) -> None:
        """
        Tests the sysprops and sysprop commands
        """
        output = self._run_command("sysprops")

        # Extract all variables
        props = {}
        for line in output.split("\n"):
            if line.startswith("|"):
                # Value line, name column
                idx_separator = line.find("|", 1)
                name = line[1:idx_separator].strip()
                value = line[idx_separator + 1 : -1].strip()
                if name and name != "Environment Variable":
                    props[name] = value

        # Check their values
        for name, value in os.environ.items():
            if "\n" not in value and "\\n" not in value:
                self.assertEqual(str(props[name]), value.strip())

        # Check each variable
        for name, value in props.items():
            output = self._run_command(f"sysprop {name}")
            self.assertIn(value, output.strip())

        # Check invalid variable
        output = self._run_command("sysprop <<invalid>>")
        self.assertEqual("", output.strip())

    def testThreads(self) -> None:
        """
        Tests the threads and thread commands
        """
        if not hasattr(sys, "_current_frames"):
            self.skipTest("sys._current_frames() isn't supported in this interpreter")

        output = self._run_command("threads")

        # Get all threads
        threads = []
        for line in output.split("\n"):
            if line.startswith("Thread ID:"):
                thread_id = int(line.split(":")[1].split("-")[0])
                threads.append(thread_id)

        # Check each thread
        for thread_id in threads:
            output = self._run_command(f"thread {thread_id}")

        # Check invalid thread
        output = self._run_command("thread -1")
        self.assertIn("Unknown thread", output)

        output = self._run_command("thread aaa")
        self.assertIn("Invalid thread", output)


class PromptSecretTest(unittest.TestCase):
    """
    Tests the reading of a secret in a shell session
    """

    def test_stream(self) -> None:
        """
        A stream front end (remote, XMPP) gives the line without its end of line
        """
        for line, expected in (("hunter2\n", "hunter2"), (" pass word \r\n", " pass word "), ("\n", "")):
            with self.subTest(line=line):
                output = StringIO()
                session = beans.ShellSession(beans.IOHandler(StringIO(line), output))
                secret = session.prompt_secret("Password: ")
                self.assertIsInstance(secret, Secret)
                self.assertEqual(secret, Secret(expected))
                self.assertEqual(output.getvalue(), "Password: ")

        # Nothing to read: no input stream, or its end
        for in_stream in (None, StringIO("")):
            with self.subTest(in_stream=in_stream), self.assertRaises(EOFError):
                beans.ShellSession(beans.IOHandler(in_stream, StringIO())).prompt_secret()

    def test_console(self) -> None:
        """
        The console reads the secret without echo
        """
        for prompt, expected_prompt in ((None, "Password: "), ("Key: ", "Key: ")):
            with (
                self.subTest(prompt=prompt),
                mock.patch("getpass.getpass", return_value="hunter2") as getpass,
            ):
                session = beans.ShellSession(beans.IOHandler(sys.stdin, sys.stdout), trusted=True)
                self.assertEqual(session.prompt_secret(prompt), Secret("hunter2"))
                getpass.assert_called_once_with(expected_prompt)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
