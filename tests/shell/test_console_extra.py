#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the console shell helpers and interactive shell wiring

:author: Thomas Calmant
"""

import os
import subprocess
import sys
import tempfile
import unittest
from typing import Any, List

import pelix.framework
from pelix.shell.console import (
    PROP_INIT_FILE,
    PROP_RUN_FILE,
    InteractiveShell,
    _resolve_file,
    handle_common_arguments,
    main,
    make_common_parser,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class ResolveFileTest(unittest.TestCase):
    """
    Tests the _resolve_file() utility
    """

    def test_resolve_file(self) -> None:
        with tempfile.NamedTemporaryFile() as tmp_file:
            self.assertEqual(_resolve_file(tmp_file.name), os.path.realpath(tmp_file.name))

        self.assertIsNone(_resolve_file(""))
        self.assertIsNone(_resolve_file("/no/such/file.txt"))


class CommonArgumentsTest(unittest.TestCase):
    """
    Tests the common shell argument parsing
    """

    def _handle(self, arguments: List[str]) -> Any:
        parser = make_common_parser()
        return handle_common_arguments(parser.parse_args(arguments))

    def test_version(self) -> None:
        """
        Tests the --version argument (argparse exits)
        """
        parser = make_common_parser()
        with self.assertRaises(SystemExit) as ctx:
            parser.parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_properties(self) -> None:
        """
        Tests the -D framework properties definition
        """
        init = self._handle(["-e", "-D", "some.key=some.value", "other.key=2"])
        self.assertEqual(init.properties["some.key"], "some.value")
        self.assertEqual(init.properties["other.key"], "2")

    def test_exclusive_conf(self) -> None:
        """
        Tests the -C exclusive configuration file
        """
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as tmp_file:
            tmp_file.write('{"properties": {"conf.prop": 42}, "bundles": ["pelix.shell.core"]}')
            conf_name = tmp_file.name

        try:
            init = self._handle(["-C", conf_name])
            self.assertEqual(init.properties["conf.prop"], 42)
            self.assertIn("pelix.shell.core", init.bundles)
        finally:
            os.unlink(conf_name)

    def test_scripts(self) -> None:
        """
        Tests the --init and --run script arguments
        """
        with tempfile.NamedTemporaryFile("w", suffix=".pelix", delete=False) as tmp_file:
            tmp_file.write("echo init\n")
            script_name = tmp_file.name

        try:
            init = self._handle(["-e", "--init", script_name, "--run", script_name])
            self.assertEqual(init.properties[PROP_INIT_FILE], os.path.realpath(script_name))
            self.assertEqual(init.properties[PROP_RUN_FILE], os.path.realpath(script_name))
        finally:
            os.unlink(script_name)

        # Missing files must raise an error
        self.assertRaises(IOError, self._handle, ["-e", "--init", "/no/such/script.pelix"])
        self.assertRaises(IOError, self._handle, ["-e", "--run", "/no/such/script.pelix"])


class InteractiveShellTest(unittest.TestCase):
    """
    Tests the InteractiveShell service binding and scripted run
    """

    def setUp(self) -> None:
        # Script to run instead of the interactive loop
        self.script = tempfile.NamedTemporaryFile("w", suffix=".pelix", delete=False)
        self.script.write("echo hello from script\n")
        self.script.close()
        self.addCleanup(os.unlink, self.script.name)

        self.framework = pelix.framework.create_framework(
            ["pelix.shell.core"], {PROP_RUN_FILE: self.script.name}
        )
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

    def test_scripted_run(self) -> None:
        """
        Tests loop_input() executing the configured script
        """
        shell = InteractiveShell(self.context)
        quit_flag = []

        try:
            shell.loop_input(lambda: quit_flag.append(True))
            self.assertListEqual(quit_flag, [True])
        finally:
            shell.stop()

    def test_shell_binding(self) -> None:
        """
        Tests the binding/unbinding of the shell service
        """
        shell = InteractiveShell(self.context)
        try:
            # The shell service is already bound (shell.core is started)
            self.assertTrue(shell._shell_event.is_set())

            # Stopping the shell bundle unbinds the service
            shell_bundle = [
                bundle
                for bundle in self.context.get_bundles()
                if bundle.get_symbolic_name() == "pelix.shell.core"
            ][0]
            shell_bundle.stop()
            self.assertFalse(shell._shell_event.is_set())

            # Restarting it binds the service again
            shell_bundle.start()
            self.assertTrue(shell._shell_event.is_set())
        finally:
            shell.stop()


class MainTest(unittest.TestCase):
    """
    Tests the console entry point
    """

    def setUp(self) -> None:
        self.script = tempfile.NamedTemporaryFile("w", suffix=".pelix", delete=False)
        self.script.write("echo hello from main\n")
        self.script.close()
        self.addCleanup(os.unlink, self.script.name)

    def test_main(self) -> None:
        """
        Tests an in-process scripted run of main()
        """
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)
        self.assertEqual(main(["-e", "--run", self.script.name]), 0)

    def test_main_module(self) -> None:
        """
        Tests a scripted run of python -m pelix.shell
        """
        process = subprocess.run(
            [sys.executable, "-m", "pelix.shell", "-e", "--run", self.script.name],
            capture_output=True,
            timeout=60,
            text=True,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("hello from main", process.stdout)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
