#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the console shell helpers and interactive shell wiring

:author: Thomas Calmant
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from typing import Any
from unittest import mock

import pelix.framework
import pelix.shell.completion.core as completion_core
from pelix.framework import Bundle
from pelix.shell import console
from pelix.shell.console import (
    PROP_INIT_FILE,
    PROP_RUN_FILE,
    Activator,
    InteractiveShell,
    _resolve_file,
    handle_common_arguments,
    main,
    make_common_parser,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
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

    def _handle(self, arguments: list[str]) -> Any:
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
        with tempfile.NamedTemporaryFile("w", suffix=".pelix", delete=False) as self.script:
            self.script.write("echo hello from script\n")
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
            shell_bundle = next(
                bundle
                for bundle in self.context.get_bundles()
                if bundle.get_symbolic_name() == "pelix.shell.core"
            )
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
        with tempfile.NamedTemporaryFile("w", suffix=".pelix", delete=False) as self.script:
            self.script.write("echo hello from main\n")
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
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("hello from main", process.stdout)


class FakeReadline:
    """
    Stand-in for the readline module: gives the line being completed
    """

    def __init__(self) -> None:
        self.line = ""
        self.begidx = 0
        self.hooks: list[Any] = []

    def get_line_buffer(self) -> str:
        return self.line

    def get_begidx(self) -> int:
        return self.begidx

    def set_completion_display_matches_hook(self, hook: Any) -> None:
        self.hooks.append(hook)

    def set_completer(self, completer: Any) -> None:
        pass

    def redisplay(self) -> None:
        pass


class NoHookReadline(FakeReadline):
    """
    Readline without display hooks support (e.g. libedit)
    """

    def __getattribute__(self, name: str) -> Any:
        if name == "set_completion_display_matches_hook":
            raise AttributeError(name)
        return super().__getattribute__(name)


class InteractiveLoopTest(unittest.TestCase):
    """
    Tests the interactive input loop, with a mocked standard input
    """

    def setUp(self) -> None:
        self.framework = pelix.framework.create_framework(["pelix.shell.core"])
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)
        self.framework.start()
        self.addCleanup(self.framework.delete, True)
        self.context = self.framework.get_bundle_context()
        self.output = io.StringIO()

    def make_shell(self) -> InteractiveShell:
        """
        Creates a shell writing to our output
        """
        # The session output stream is the one active at construction time
        with contextlib.redirect_stdout(self.output):
            shell = InteractiveShell(self.context)
        self.addCleanup(shell.stop)
        return shell

    def run_loop(self, shell: InteractiveShell, inputs: Any, use_readline: bool) -> list[tuple[Any, ...]]:
        """
        Runs the input loop until the inputs are consumed

        :param inputs: A list of input results or a function (mock side effect)

        :return: The arguments given to each input() call
        """
        quit_flag: list[bool] = []
        with (
            mock.patch.object(console, "HAS_READLINE", use_readline),
            mock.patch("builtins.input", side_effect=inputs) as fake_input,
            contextlib.redirect_stdout(self.output),
        ):
            shell.loop_input(lambda: quit_flag.append(True))

        self.assertEqual([True], quit_flag)
        self.assertTrue(self.output.getvalue().endswith("Bye !\n"))
        return [call.args for call in fake_input.call_args_list]

    def test_readline_loop(self) -> None:
        """
        The readline prompt uses the session PS1 variable when it is set
        """
        shell = self.make_shell()
        assert shell._shell is not None
        default_ps1 = shell._shell.get_ps1()

        prompts = self.run_loop(shell, ["set PS1=custom>", "echo hello", EOFError()], True)
        self.assertEqual([(default_ps1,), ("custom>",), ("custom>",)], prompts)

        output = self.output.getvalue()
        self.assertTrue(output.startswith(shell._shell.get_banner()))
        self.assertIn("hello\n", output)

    def test_normal_loop(self) -> None:
        """
        Without readline, the prompt is written before reading the input
        """
        shell = self.make_shell()
        assert shell._shell is not None
        ps1 = shell._shell.get_ps1()

        prompts = self.run_loop(shell, ["echo hello", KeyboardInterrupt()], False)
        self.assertEqual([(), ()], prompts)
        self.assertIn(f"{ps1}hello\n{ps1}", self.output.getvalue())

    def test_shell_lost(self) -> None:
        """
        A line read while the shell service is gone isn't executed
        """
        shell = self.make_shell()
        shell_bundle = next(
            bundle
            for bundle in self.context.get_bundles()
            if bundle.get_symbolic_name() == "pelix.shell.core"
        )

        def lose_shell(*_: Any) -> str:
            shell_bundle.stop()
            # Without shell, the loop waits until the console is stopped
            threading.Timer(0.3, shell.stop).start()
            return "echo not executed"

        self.run_loop(shell, lose_shell, True)
        output = self.output.getvalue()
        self.assertIn("Shell service lost.", output)
        self.assertNotIn("not executed", output)


class CompleterTest(unittest.TestCase):
    """
    Tests the readline completer of the interactive shell
    """

    def setUp(self) -> None:
        self.framework = pelix.framework.create_framework(
            ["pelix.ipopo.core", "pelix.shell.core", "pelix.shell.ipopo", "pelix.shell.completion.pelix"]
        )
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)
        self.framework.start()
        self.addCleanup(self.framework.delete, True)

        self.shell = InteractiveShell(self.framework.get_bundle_context())
        self.addCleanup(self.shell.stop)

        # Patched after the shell creation to let it clean up the real
        # readline module when stopped
        self.readline = FakeReadline()
        for module in (console, completion_core):
            patcher = mock.patch.object(module, "readline", self.readline)
            patcher.start()
            self.addCleanup(patcher.stop)

    def complete(self, line: str, begidx: int = 0) -> list[str]:
        """
        Returns all the completions readline would get for the given line
        """
        self.readline.line = line
        self.readline.begidx = begidx
        text = line[begidx:]

        matches: list[str] = []
        while True:
            match = self.shell.readline_completer(text, len(matches))
            if match is None:
                return matches
            matches.append(match)

    def test_commands(self) -> None:
        """
        Completes command names, from the default name space first
        """
        self.assertEqual(["echo ", "exit "], self.complete("e"))
        self.assertEqual(["install ", "instance ", "instances ", "instantiate "], self.complete("inst"))
        self.assertEqual([], self.complete("zzz"))

        # The display hook is reset for each new completion
        self.assertEqual([None, None, None], self.readline.hooks)

    def test_namespaces(self) -> None:
        """
        Completes name spaces, then the commands they contain
        """
        self.assertEqual(["ipopo."], self.complete("ip"))
        self.assertEqual(
            ["ipopo.instance", "ipopo.instances", "ipopo.instantiate"], self.complete("ipopo.in")
        )
        self.assertEqual([], self.complete("unknown.x"))

    def test_arguments(self) -> None:
        """
        Completes arguments with the completer associated to the command
        """
        bundle_ids = [
            f"{bundle.get_bundle_id()} " for bundle in self.framework.get_bundle_context().get_bundles()
        ]
        self.assertEqual(bundle_ids, self.complete("bd ", 3))
        self.assertEqual([bid for bid in bundle_ids if bid.startswith("1")], self.complete("bd 1", 3))

        # The bundle completer installs its own display hook
        self.assertIsNotNone(self.readline.hooks[-1])

    def test_no_argument_completion(self) -> None:
        """
        Commands without completer, unknown commands and invalid lines give
        nothing
        """
        self.assertEqual([], self.complete("echo ", 5))
        self.assertEqual([], self.complete("unknown ", 8))
        self.assertEqual([], self.complete("unknown.cmd ", 12))
        self.assertEqual([], self.complete('echo "unclosed ', 15))

    def test_no_display_hook(self) -> None:
        """
        A readline without display hooks can still complete
        """
        with mock.patch.object(console, "readline", NoHookReadline()) as readline:
            readline.line = "ec"
            self.assertEqual("echo ", self.shell.readline_completer("ec", 0))

    def test_no_readline(self) -> None:
        """
        Nothing is completed when readline isn't available
        """
        self.readline.line = "e"
        with mock.patch.object(console, "HAS_READLINE", False):
            self.assertIsNone(self.shell.readline_completer("e", 0))

    def test_empty_line(self) -> None:
        """
        Completing an empty or blank line lists the commands
        """
        self.assertIn("echo ", self.complete(""))
        self.assertIn("echo ", self.complete("  ", 2))


class ActivatorTest(unittest.TestCase):
    """
    Tests the console bundle activator
    """

    def setUp(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".pelix", delete=False) as self.script:
            self.script.write("echo hello from activator\n")
        self.addCleanup(os.unlink, self.script.name)
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)

    def test_script_stops_framework(self) -> None:
        """
        The framework is stopped once the console script has been run
        """
        framework = pelix.framework.create_framework(
            ["pelix.shell.core", "pelix.shell.console"], {PROP_RUN_FILE: self.script.name}
        )
        framework.start()
        try:
            self.assertTrue(framework.wait_for_stop(10))
            self.assertEqual(Bundle.RESOLVED, framework.get_state())
        finally:
            framework.delete(True)

    def test_stop_bundle(self) -> None:
        """
        Stopping the activator ends the console without stopping the
        framework
        """
        framework = pelix.framework.create_framework(["pelix.shell.core"])
        framework.start()
        self.addCleanup(framework.delete, True)
        context = framework.get_bundle_context()

        reading = threading.Event()
        release = threading.Event()

        def blocking_input(*_: Any) -> str:
            reading.set()
            release.wait(10)
            return "echo after stop"

        # Any: the activator decorator hides the members of the class
        activator: Any = Activator()
        with (
            mock.patch("builtins.input", blocking_input),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            activator.start(context)
            thread = activator._thread
            assert thread is not None
            self.assertTrue(reading.wait(10))

            activator.stop(context)
            release.set()
            thread.join(10)

        self.assertFalse(thread.is_alive())
        self.assertIsNone(activator._shell)
        self.assertNotIn("after stop", output.getvalue())
        self.assertEqual(Bundle.ACTIVE, framework.get_state())


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
