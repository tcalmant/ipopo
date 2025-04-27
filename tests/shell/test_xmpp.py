#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the XMPP shell interface

This module considers there is an XMPP server listening on localhost with two
users (user1 and user2) with "foobar" as password.

:author: Thomas Calmant
"""

import socket
import unittest
from io import StringIO
from typing import Any, Dict

try:
    from slixmpp.jid import JID

    import pelix.misc.xmpp as xmpp
except ImportError:
    # Missing requirement: not a fatal error
    raise unittest.SkipTest("XMPP client dependency missing: skip test")


from pelix.framework import FrameworkFactory
from pelix.ipopo.constants import use_ipopo
from pelix.shell import FACTORY_XMPP_SHELL, ShellService
from pelix.shell.beans import IOHandler, ShellSession
from pelix.threadpool import EventData

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class XMPPShellTest(unittest.TestCase):
    """
    Tests the XMPP shell interface
    """

    def setUp(self) -> None:
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
        svc_ref = self.context.get_service_reference(ShellService)
        if svc_ref is None:
            raise AssertionError("No shell service found")
        self.shell = self.context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up the framework
        """
        if self.framework is not None:
            self.framework.stop()
        FrameworkFactory.delete_framework()
        self.shell = None  # type: ignore
        self.context = None  # type: ignore
        self.framework = None  # type: ignore

    def test_commands(self) -> None:
        """
        Tests basic commands through XMPP shell
        """
        assert self.context is not None
        assert self.shell is not None

        # Get host name
        localhost = socket.gethostbyname(socket.gethostname())
        shell_jid = JID("user1@localhost")

        # Setup the XMPP shell
        self.context.install_bundle("pelix.shell.xmpp").start()
        with use_ipopo(self.context) as ipopo:
            ipopo.instantiate(
                FACTORY_XMPP_SHELL,
                "xmpp-shell",
                {
                    "shell.xmpp.server": localhost,
                    "shell.xmpp.jid": shell_jid,
                    "shell.xmpp.password": "foobar",
                },
            )

        # Prepare a client
        client = xmpp.BasicBot("user2@localhost", "foobar")
        self.assertTrue(client.connect(localhost, 5222))

        # Ensure both bots can talk to each other
        client.update_roster(JID("user1@localhost"), subscription="both")

        # Register the message event handler
        msg_event = EventData()

        def on_message(data: Dict[str, Any]) -> None:
            if data["type"] in ("normal", "chat"):
                # Got a message
                body = data["body"].strip()
                msg_event.set(body)

        client.add_event_handler("message", on_message)

        # Send commands
        for command in ("echo test 1", "bl", "bd 0", "sl", "sd 1"):
            # Send command via XMPP
            msg_event.clear()
            client.send_message(shell_jid, command)

            # Execute it locally, and remove the trailing newline
            str_output = StringIO()
            session = ShellSession(IOHandler(None, str_output))
            self.shell.execute(command, session)
            local_result = str_output.getvalue().rstrip()

            # Wait for the XMPP result
            self.assertTrue(msg_event.wait(5), f"Response not received for command '{command}'")
            xmpp_result = msg_event.data

            # Assert results are the same
            self.assertEqual(xmpp_result, local_result)

        # Disconnect local client
        client.disconnect()
