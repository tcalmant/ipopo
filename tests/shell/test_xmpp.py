#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the XMPP shell interface

This module considers there is an XMPP server listening on localhost with two
users (user1 and user2) with "foobar" as password.

:author: Thomas Calmant
"""

import pathlib
import shutil
import socket
import tempfile
import unittest
from io import StringIO
from typing import Any

try:
    from slixmpp.jid import JID

    from pelix.misc import xmpp
except ImportError:
    # Missing requirement: not a fatal error
    raise unittest.SkipTest("XMPP client dependency missing: skip test")


from pelix.framework import FrameworkFactory
from pelix.ipopo.constants import use_ipopo
from pelix.security import FACTORY_POLICY_FILE, PROP_POLICY_FILE, Subject
from pelix.shell import FACTORY_XMPP_SHELL, ShellService
from pelix.shell.beans import IOHandler, ShellSession
from pelix.threadpool import EventData
from tests.utilities import is_server_reachable

if not is_server_reachable("localhost", 5222):
    raise unittest.SkipTest("No XMPP server on localhost:5222: can't test the XMPP shell")

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
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
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Install the shell bundle
        for bundle in (
            "pelix.ipopo.core",
            "pelix.shell.core",
            "pelix.security.core",
            "pelix.security.policy",
        ):
            self.context.install_bundle(bundle).start()

        # The user of the XMPP client may run the listings only
        folder = pathlib.Path(tempfile.mkdtemp(prefix="ipopo-tests-shell-xmpp"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        (folder / "policy.toml").write_text(
            '[roles.reader]\nusers = ["reader"]\n\n[permissions]\nreader = ["pelix.shell.read"]\n'
        )
        with use_ipopo(self.context) as ipopo:
            ipopo.instantiate(FACTORY_POLICY_FILE, "policy", {PROP_POLICY_FILE: str(folder / "policy.toml")})

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
        self.shell = None
        self.context = None
        self.framework = None

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
                    # The test server has a self-signed certificate
                    "shell.xmpp.tls.verify": "0",
                    "shell.xmpp.users": {"user2@localhost": "reader"},
                },
            )

        # Prepare a client
        client = xmpp.BasicBot("user2@localhost", "foobar", ssl_verify=False)
        self.assertTrue(client.connect(localhost, 5222))

        # Ensure both bots can talk to each other
        client.update_roster(JID("user1@localhost"), subscription="both")

        # Register the message event handler
        msg_event = EventData()

        def on_message(data: dict[str, Any]) -> None:
            if data["type"] in ("normal", "chat"):
                # Got a message
                body = data["body"].strip()
                msg_event.set(body)

        client.add_event_handler("message", on_message)

        # Send commands: the last one needs the admin level
        for command in ("echo test 1", "bl", "bd 0", "sl", "sd 1", "install pelix.shell.log"):
            # Send command via XMPP
            msg_event.clear()
            client.send_message(shell_jid, command)

            # Execute it locally, as the reader, and remove the trailing newline
            str_output = StringIO()
            session = ShellSession(IOHandler(None, str_output), subject=Subject("reader", authenticated=True))
            self.shell.execute(command, session)
            local_result = str_output.getvalue().rstrip()

            # Wait for the XMPP result
            self.assertTrue(msg_event.wait(5), f"Response not received for command '{command}'")
            xmpp_result = msg_event.data

            # Assert results are the same
            self.assertEqual(xmpp_result, local_result)

        # Disconnect local client
        client.disconnect()
