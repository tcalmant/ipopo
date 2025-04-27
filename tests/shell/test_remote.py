#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the remote shell

:author: Thomas Calmant
"""

import socket
import sys
import threading
import time
import unittest
from io import StringIO
from typing import Any, Callable, Optional, Tuple

import pelix.shell.beans as beans
from pelix.framework import Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import use_ipopo
from pelix.shell import FACTORY_REMOTE_SHELL, RemoteShell, ShellService
from pelix.utilities import to_bytes, to_str

try:
    import coverage

    has_coverage = True
except ImportError:
    has_coverage = False

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class ShellClient:
    """
    Simple client of the remote shell
    """

    def __init__(self, banner: Optional[str], ps1: str, fail: Callable[[str], None]) -> None:
        """
        Sets up the client
        """
        self._socket: Optional[socket.socket] = None
        self._banner = banner
        self._ps1 = ps1
        self.fail = fail
        self.__wait_prompt = True

    def connect(self, access: Tuple[str, int]) -> None:
        """
        Connects to the remote shell
        """
        # Connect to the server
        self._socket = socket.create_connection(access)

        # Check the banner
        if self._banner:
            banner = to_str(self._socket.recv(len(self._banner)))
            if banner != self._banner:
                self.fail("Incorrect banner read from remote shell")

    def close(self) -> None:
        """
        Close the connection
        """
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def wait_prompt(self, raise_error: bool = True) -> str:
        """
        Waits for the prompt to be read
        """
        assert self._socket is not None

        data = ""
        # Wait for the prompt
        for _ in range(1, 10):
            spared = to_str(self._socket.recv(4096))
            if self._ps1 in spared:
                # Found it
                data += spared[: spared.index(self._ps1)]
                break

            else:
                # Prompt not yet found
                data += spared

        else:
            # Prompt not found
            if raise_error:
                self.fail("Didn't get the prompt")

        return data

    def run_command(self, command: str, disconnect: bool = False) -> Optional[str]:
        """
        Runs a command on the remote shell
        """
        assert self._socket is not None

        # Wait for the first prompt
        if self.__wait_prompt:
            self.wait_prompt()
            self.__wait_prompt = False

        # Run the command
        self._socket.send(to_bytes(command + "\n"))

        # Disconnect if required
        if disconnect:
            self.close()
            return None

        # Get its result
        data = self.wait_prompt(False)
        return data.strip()


# ------------------------------------------------------------------------------


try:
    import subprocess
except ImportError:
    # Can't run the test if we can't start another process
    pass
else:

    class RemoteShellStandaloneTest(unittest.TestCase):
        """
        Tests the remote shell when started as a script
        """

        def test_remote_main(self) -> None:
            """
            Tests the remote shell 'main' method
            """
            # Get shell PS1 (static method)
            import pelix.shell.core

            ps1 = pelix.shell.core._ShellService.get_ps1()

            # Start the remote shell process
            port = 9000
            args = [sys.executable, "-m"]
            if has_coverage:
                args += ["coverage", "run", "-m"]
            args += ["pelix.shell.remote", "-a", "127.0.0.1", "-p", str(port)]
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait a little to ensure that the socket is here
            time.sleep(1)

            client = ShellClient(None, ps1, self.fail)
            try:
                # Check if the remote shell port has been opened
                client.connect(("127.0.0.1", port))

                test_string = "running"
                self.assertEqual(client.run_command("echo {0}".format(test_string)), test_string)

                # Good enough: stop there
                client.close()

                # Avoid being blocked...
                timer = threading.Timer(5, process.terminate)
                timer.start()

                # Stop the interpreter with a result code
                rc_code = 42
                stop_line = "import sys; sys.exit({0})".format(rc_code)
                process.communicate(to_bytes(stop_line))

                # We should be good
                timer.cancel()

                # Check result code
                self.assertEqual(process.returncode, rc_code)

                # The ShellClient must fail a new connection
                self.assertRaises(IOError, client.connect, ("localhost", port))
            finally:
                # Close connection
                client.close()

                try:
                    # Kill it in any case
                    process.terminate()
                    process.wait(1)
                except OSError:
                    # Process was already stopped
                    pass


# ------------------------------------------------------------------------------


class RemoteShellTest(unittest.TestCase):
    """
    Tests the remote shell by comparing local and remote outputs
    """

    framework: Framework
    shell: ShellService
    remote: RemoteShell

    def setUp(self) -> None:
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = create_framework(("pelix.ipopo.core", "pelix.shell.core", "pelix.shell.remote"))
        self.framework.start()
        context = self.framework.get_bundle_context()
        # Get the core shell service
        svc_ref = context.get_service_reference(ShellService)
        assert svc_ref is not None
        self.shell = context.get_service(svc_ref)

        # Start the remote shell
        with use_ipopo(context) as ipopo:
            self.remote = ipopo.instantiate(
                FACTORY_REMOTE_SHELL,
                "remoteShell",
                {"pelix.shell.address": "127.0.0.1", "pelix.shell.port": 9000},
            )

    def tearDown(self) -> None:
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()
        self.remote = None  # type: ignore
        self.shell = None  # type: ignore
        self.framework = None  # type: ignore

    def _run_local_command(self, command: str, *args: Any) -> str:
        """
        Runs the given command and returns the output stream
        """
        # String output
        str_output = StringIO()

        # Format command
        if args:
            command = command.format(*args)

        # Run command
        session = beans.ShellSession(beans.IOHandler(None, str_output))
        self.shell.execute(command, session)
        return str_output.getvalue().strip()

    def testCoreVsRemoteCommands(self) -> None:
        """
        Tests the output of commands, through the shell service and the remote
        shell
        """
        # Create a client
        client = ShellClient(self.remote.get_banner(), self.remote.get_ps1(), self.fail)
        try:
            client.connect(self.remote.get_access())
            for command in ("bl", "bd 0", "sl", "sd 1"):
                # Get local & remote outputs
                local_output = self._run_local_command(command)
                remote_output = client.run_command(command)

                # Compare them
                self.assertEqual(remote_output, local_output)
        finally:
            # Close the client in any case
            client.close()

    def testRemoteVsRemoteCommands(self) -> None:
        """
        Tests the output for two clients
        """
        # Create clients
        client_1 = ShellClient(self.remote.get_banner(), self.remote.get_ps1(), self.fail)
        client_2 = ShellClient(self.remote.get_banner(), self.remote.get_ps1(), self.fail)

        try:
            # Connect them to the remote shell
            client_1.connect(self.remote.get_access())
            client_2.connect(self.remote.get_access())

            for command in ("bl", "bd 0", "sl", "sd 1"):
                # Get clients outputs
                client_1_output = client_1.run_command(command)
                client_2_output = client_2.run_command(command)

                # Compare them
                self.assertEqual(client_1_output, client_2_output)
        finally:
            # Close the client in any case
            client_1.close()
            client_2.close()

    def testDualRemoteShell(self) -> None:
        """
        Tests with a second remote shell component
        """
        # Start the remote shell, on a random port
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            remote_2 = ipopo.instantiate(
                FACTORY_REMOTE_SHELL,
                "remoteShell_2",
                {"pelix.shell.address": "127.0.0.1", "pelix.shell.port": 0},
            )

        # Accesses should be different
        self.assertNotEqual(self.remote.get_access(), remote_2.get_access())

        # Create clients
        client_1 = ShellClient(self.remote.get_banner(), self.remote.get_ps1(), self.fail)
        client_2 = ShellClient(remote_2.get_banner(), remote_2.get_ps1(), self.fail)

        try:
            # Connect them to the remote shell
            client_1.connect(self.remote.get_access())
            client_2.connect(remote_2.get_access())

            for command in ("bl", "bd 0", "sl", "sd 1"):
                # Get clients outputs
                client_1_output = client_1.run_command(command)
                client_2_output = client_2.run_command(command)

                # Compare them
                self.assertEqual(client_1_output, client_2_output)
        finally:
            # Close the client in any case
            client_1.close()
            client_2.close()

    def testInvalidConfiguration(self) -> None:
        """
        Tests the instantiation of the remote shell with invalid port
        """
        import logging

        logging.basicConfig(level=logging.DEBUG)

        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            # Check invalid ports
            for port in (-1, 100000, "-100", "65536", "Abc", None):
                remote = ipopo.instantiate(
                    FACTORY_REMOTE_SHELL, "remoteShell_test", {"pelix.shell.port": port}
                )

                # Check that the port is in a valid range
                self.assertGreater(remote.get_access()[1], 0)
                self.assertLess(remote.get_access()[1], 65536)
                ipopo.kill("remoteShell_test")

            # Check empty addresses
            for address in (None, ""):
                remote = ipopo.instantiate(
                    FACTORY_REMOTE_SHELL,
                    "remoteShell_test",
                    {"pelix.shell.address": address, "pelix.shell.port": 0},
                )

                # Check that the address has been selected anyway
                self.assertTrue(remote.get_access()[0])
                ipopo.kill("remoteShell_test")

    def testClientDisconnect(self) -> None:
        """
        Tests the behavior of the server when a client disconnects before
        reading results
        """
        # Create clients
        client_1 = ShellClient(self.remote.get_banner(), self.remote.get_ps1(), self.fail)
        client_2 = ShellClient(self.remote.get_banner(), self.remote.get_ps1(), self.fail)

        try:
            # Connect them to the remote shell
            client_1.connect(self.remote.get_access())
            client_2.connect(self.remote.get_access())

            # Run commands
            client_1.run_command("bl")
            first_output = client_2.run_command("bl")

            # Disconnect when running command (this might print/log an error)
            client_1.run_command("bl", True)
            second_output = client_2.run_command("bl")

            # Ensure that the results are not modified by the error
            self.assertEqual(second_output, first_output)
        finally:
            # Close clients
            client_2.close()
            client_1.close()

    def testClientInactive(self) -> None:
        """
        Inactive client test: no packet sent during 1 second
        """
        # Create a client
        client = ShellClient(self.remote.get_banner(), self.remote.get_ps1(), self.fail)
        try:
            client.connect(self.remote.get_access())

            # Wait a little (server poll time is 0.5s)
            time.sleep(1)

            # Send a command
            local_output = self._run_local_command("bl")
            remote_output = client.run_command("bl")

            # Compare them
            self.assertEqual(remote_output, local_output)
        finally:
            # Close the client
            client.close()
