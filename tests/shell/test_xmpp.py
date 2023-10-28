#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the XMPP shell interface

This module considers there is an XMPP server listening on localhost with two
users (user1 and user2) with "foobar" as password.

:author: Thomas Calmant
"""

import socket
import threading

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

try:
    import unittest2 as unittest
except ImportError:
    import unittest

try:
    import pelix.misc.xmpp as xmpp
except ImportError:
    # Missing requirement: not a fatal error
    raise unittest.SkipTest("XMPP client dependency missing: skip test")

from pelix.framework import FrameworkFactory
from pelix.ipopo.constants import use_ipopo
from pelix.shell import FACTORY_XMPP_SHELL, SERVICE_SHELL
from pelix.shell.beans import ShellSession, IOHandler

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class XMPPShellTest(unittest.TestCase):
    """
    Tests the XMPP shell interface
    """
    def setUp(self):
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Install the shell bundle
        self.context.install_bundle("pelix.ipopo.core").start()
        self.context.install_bundle("pelix.shell.core").start()

        # Get the local shell
        self.shell = self.context.get_service(
            self.context.get_service_reference(SERVICE_SHELL))

    def tearDown(self):
        """
        Cleans up the framework
        """
        self.shell = None
        self.framework.stop()
        FrameworkFactory.delete_framework()
        self.context = None
        self.framework = None

    def test_commands(self):
        """
        Tests basic commands through XMPP shell
        """
        # Get host name
        localhost = socket.gethostbyname(socket.gethostname())
        shell_jid = "user1@localhost"

        # Setup the XMPP shell
        self.context.install_bundle("pelix.shell.xmpp").start()
        with use_ipopo(self.context) as ipopo:
            ipopo.instantiate(
                FACTORY_XMPP_SHELL, "xmpp-shell",
                {
                    "shell.xmpp.server": localhost,
                    "shell.xmpp.jid": shell_jid,
                    "shell.xmpp.password": "foobar"
                })

        # Prepare a client
        client = xmpp.BasicBot("user2@localhost", "foobar")
        client.connect(localhost, 5222)

        # Ensure both bots can talk to each other
        client.update_roster("user1@localhost", subscription="both")

        # Register the message event handler
        client_results = []
        msg_event = threading.Event()

        def on_message(data):
            if data['type'] in ('normal', 'chat'):
                # Got a message
                sender = data['from'].full
                body = data['body'].strip()

                client_results.append(body)
                msg_event.set()

        client.add_event_handler("message", on_message)

        # Send commands
        for command in ('echo test 1', 'bl', 'bd 0', 'sl', 'sl 0'):
            # Send command via XMPP
            client.send_message(shell_jid, command)

            # Execute it locally, and remove the trailing newline
            str_output = StringIO()
            session = ShellSession(IOHandler(None, str_output))
            self.shell.execute(command, session)
            local_result = str_output.getvalue().rstrip()

            # Wait for the XMPP result
            msg_event.wait()
            xmpp_result = client_results.pop()

            # Assert results are the same
            self.assertEqual(xmpp_result, local_result)

            # Clean up
            msg_event.clear()

        # Disconnect local client
        client.disconnect()
