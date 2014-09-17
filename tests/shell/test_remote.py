#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the remote shell

:author: Thomas Calmant
"""

# Pelix
from pelix.framework import FrameworkFactory, create_framework
from pelix.utilities import to_str, to_bytes
from pelix.ipopo.constants import use_ipopo

# Shell constants
from pelix.shell import SERVICE_SHELL, FACTORY_REMOTE_SHELL

# Standard library
import socket
import time
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


class ShellClient(object):
    """
    Simple client of the remote shell
    """
    def __init__(self, banner, ps1, fail):
        """
        Sets up the client
        """
        self._socket = None
        self._banner = banner
        self._ps1 = ps1
        self.fail = fail
        self.__wait_prompt = True
        self.__prefix = ""

    def connect(self, access):
        """
        Connects to the remote shell
        """
        # Connect to the server
        self._socket = socket.create_connection(access)

        # Ignore the banner
        banner = to_str(self._socket.recv(len(self._banner)))
        if banner != self._banner:
            self.fail("Incorrect banner read from remote shell")

    def close(self):
        """
        Close the connection
        """
        self._socket.close()

    def wait_prompt(self, raise_error=True):
        """
        Waits for the prompt to be read
        """
        data = ""
        # Wait for the prompt
        for _ in range(1, 10):
            spared = to_str(self._socket.recv(4096))
            if self._ps1 in spared:
                # Found it
                data += spared[:spared.index(self._ps1)]
                break

            else:
                # Prompt not yet found
                data += spared

        else:
            # Prompt not found
            if raise_error:
                self.fail("Didn't get the prompt")

        return data

    def run_command(self, command, disconnect=False):
        """
        Runs a command on the remote shell
        """
        # Wait for the first prompt
        if self.__wait_prompt:
            self.wait_prompt()
            self.__wait_prompt = False

        # Run the command
        self._socket.send(to_bytes(command + "\n"))

        # Disconnect if required
        if disconnect:
            self.close()
            return

        # Get its result
        data = self.wait_prompt(False)
        return data.strip()

# ------------------------------------------------------------------------------


class RemoteShellTest(unittest.TestCase):
    """
    Tests the remote shell by comparing local and remote outputs
    """
    def setUp(self):
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = create_framework(('pelix.ipopo.core',
                                           'pelix.shell.core',
                                           'pelix.shell.remote'))
        self.framework.start()
        context = self.framework.get_bundle_context()
        # Get the core shell service
        svc_ref = context.get_service_reference(SERVICE_SHELL)
        self.shell = context.get_service(svc_ref)

        # Start the remote shell
        with use_ipopo(context) as ipopo:
            self.remote = ipopo.instantiate(
                FACTORY_REMOTE_SHELL, "remoteShell",
                {'pelix.shell.address': '127.0.0.1',
                 'pelix.shell.port': 9000})

    def tearDown(self):
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)
        self.remote = None
        self.shell = None
        self.framework = None

    def _run_local_command(self, command, *args):
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
        return str_output.getvalue().strip()

    def testCoreVsRemoteCommands(self):
        """
        Tests the output of commands, through the shell service and the remote
        shell
        """
        # Create a client
        client = ShellClient(self.remote.get_banner(), self.remote.get_ps1(),
                             self.fail)
        client.connect(self.remote.get_access())

        try:
            for command in ('bl', 'bd 0', 'sl', 'sd 1'):
                # Get local & remote outputs
                local_output = self._run_local_command(command)
                remote_output = client.run_command(command)

                # Compare them
                self.assertEqual(remote_output, local_output)
        finally:
            # Close the client in any case
            client.close()

    def testRemoteVsRemoteCommands(self):
        """
        Tests the output for two clients
        """
        # Create clients
        client_1 = ShellClient(self.remote.get_banner(), self.remote.get_ps1(),
                               self.fail)
        client_2 = ShellClient(self.remote.get_banner(), self.remote.get_ps1(),
                               self.fail)

        # Connect them to the remote shell
        client_1.connect(self.remote.get_access())
        client_2.connect(self.remote.get_access())

        try:
            for command in ('bl', 'bd 0', 'sl', 'sd 1'):
                # Get clients outputs
                client_1_output = client_1.run_command(command)
                client_2_output = client_2.run_command(command)

                # Compare them
                self.assertEqual(client_1_output, client_2_output)
        finally:
            # Close the client in any case
            client_1.close()
            client_2.close()

    def testDualRemoteShell(self):
        """
        Tests with a second remote shell component
        """
        # Start the remote shell, on a random port
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            remote_2 = ipopo.instantiate(FACTORY_REMOTE_SHELL, "remoteShell_2",
                                         {'pelix.shell.address': '127.0.0.1',
                                          'pelix.shell.port': 0})

        # Accesses should be different
        self.assertNotEqual(self.remote.get_access(), remote_2.get_access())

        # Create clients
        client_1 = ShellClient(self.remote.get_banner(), self.remote.get_ps1(),
                               self.fail)
        client_2 = ShellClient(remote_2.get_banner(), remote_2.get_ps1(),
                               self.fail)

        # Connect them to the remote shell
        client_1.connect(self.remote.get_access())
        client_2.connect(remote_2.get_access())

        try:
            for command in ('bl', 'bd 0', 'sl', 'sd 1'):
                # Get clients outputs
                client_1_output = client_1.run_command(command)
                client_2_output = client_2.run_command(command)

                # Compare them
                self.assertEqual(client_1_output, client_2_output)
        finally:
            # Close the client in any case
            client_1.close()
            client_2.close()

    def testInvalidConfiguration(self):
        """
        Tests the instantiation of the remote shell with invalid port
        """
        import logging
        logging.basicConfig(level=logging.DEBUG)

        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            # Check invalid ports
            for port in (-1, 100000, '-100', '65536', 'Abc', None):
                remote = ipopo.instantiate(FACTORY_REMOTE_SHELL,
                                           "remoteShell_test",
                                           {'pelix.shell.port': port})

                # Check that the port is in a valid range
                self.assertGreater(remote.get_access()[1], 0)
                self.assertLess(remote.get_access()[1], 65536)
                ipopo.kill("remoteShell_test")

            # Check empty addresses
            for address in (None, ''):
                remote = ipopo.instantiate(FACTORY_REMOTE_SHELL,
                                           "remoteShell_test",
                                           {'pelix.shell.address': address,
                                            'pelix.shell.port': 0})

                # Check that the address has been selected anyway
                self.assertTrue(remote.get_access()[0])
                ipopo.kill("remoteShell_test")

    def testClientDisconnect(self):
        """
        Tests the behavior of the server when a client disconnects before
        reading results
        """
        # Create clients
        client_1 = ShellClient(self.remote.get_banner(), self.remote.get_ps1(),
                               self.fail)
        client_2 = ShellClient(self.remote.get_banner(), self.remote.get_ps1(),
                               self.fail)

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

        # Close clients
        client_2.close()
        client_1.close()

    def testClientInactive(self):
        """
        Inactive client test: no packet sent during 1 second
        """
        # Create a client
        client = ShellClient(self.remote.get_banner(), self.remote.get_ps1(),
                             self.fail)
        client.connect(self.remote.get_access())

        # Wait a little (server poll time is 0.5s)
        time.sleep(1)

        # Send a command
        local_output = self._run_local_command("bl")
        remote_output = client.run_command("bl")

        # Compare them
        self.assertEqual(remote_output, local_output)

        # Close the client
        client.close()
