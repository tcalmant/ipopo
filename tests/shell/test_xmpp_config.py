#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the configuration of the XMPP shell interface.

Unlike test_xmpp.py, this module doesn't need a live XMPP server: the bot is
replaced by a recording stub, so the wiring of the component properties can be
checked anywhere.

:author: Thomas Calmant
"""

import queue
import time
import unittest
import xml.etree.ElementTree as ET
from typing import Any
from unittest import mock

try:
    import pelix.misc.xmpp
    import pelix.shell.xmpp
except ImportError:
    # Missing requirement: not a fatal error
    raise unittest.SkipTest("XMPP client dependency missing: skip test")

from slixmpp.jid import JID

from pelix.framework import FrameworkFactory
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.instance import StoredInstance
from pelix.shell import FACTORY_XMPP_SHELL, CommandPermission, ShellService, beans

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class _FakeBot:
    """
    Records how the bot was constructed and swallows everything else
    """

    def __init__(self, jid: Any, password: Any, **kwargs: Any) -> None:
        self.jid = jid
        self.password = password
        self.kwargs = kwargs
        self.auto_authorize: bool = False

    def add_event_handler(self, *_: Any, **__: Any) -> None:
        pass

    def connect(self, *_: Any, **__: Any) -> bool:
        return True

    def disconnect(self, *_: Any, **__: Any) -> None:
        pass

    def send_presence(self, **_: Any) -> None:
        pass

    def send_message(self, mto: Any, mbody: str, **_: Any) -> None:
        REPLIES.put((str(mto), mbody.strip()))


REPLIES: "queue.Queue[tuple[str, str]]" = queue.Queue()
""" What the stub bots sent, as (recipient, message) """


def message(sender: str, body: str) -> Any:
    """
    Makes a chat message stanza, as the XMPP client gives it
    """
    stanza = mock.MagicMock(xml=ET.Element("message"))
    stanza.__getitem__.side_effect = {"type": "chat", "body": body, "from": JID(sender)}.__getitem__
    return stanza


class XMPPShellConfigTest(unittest.TestCase):
    """
    Tests the properties of the XMPP shell component
    """

    def setUp(self) -> None:
        """
        Starts a framework with the XMPP shell bundle
        """
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(FrameworkFactory.delete_framework)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        self.context.install_bundle("pelix.ipopo.core").start()
        self.context.install_bundle("pelix.shell.core").start()
        self.context.install_bundle("pelix.shell.xmpp").start()

    def instantiate(self, properties: dict[str, Any]) -> _FakeBot:
        """
        Instantiates the XMPP shell with the given properties and returns the
        stub bot it created

        :param properties: Component properties
        :return: The recording bot stub
        """
        return self.instantiate_component(properties)._IPopoXMPPShell__bot  # type: ignore[attr-defined]

    def instantiate_component(self, properties: dict[str, Any]) -> Any:
        """
        Instantiates the XMPP shell with the given properties and the stub bot

        :param properties: Component properties
        :return: The component
        """
        props: dict[str, Any] = {
            "shell.xmpp.jid": "bot@localhost",
            "shell.xmpp.password": "foobar",
        }
        props.update(properties)

        with (
            mock.patch.object(pelix.misc.xmpp, "BasicBot", _FakeBot),
            use_ipopo(self.context) as ipopo,
        ):
            component = ipopo.instantiate(FACTORY_XMPP_SHELL, "xmpp-shell", props)

        # Name-mangled private attribute of IPopoXMPPShell
        assert isinstance(component._IPopoXMPPShell__bot, _FakeBot)  # type: ignore[attr-defined]
        return component

    def test_users(self) -> None:
        """
        Only the mapped JIDs are users, whatever their resource, and never with a message
        the server kept or forwarded late
        """
        component = self.instantiate_component({"shell.xmpp.users": {"Alice@Example.COM": "alice"}})
        get_user = component._IPopoXMPPShell__get_user
        for sender, delayed, expected in (
            ("alice@example.com/phone", False, "alice"),
            ("alice@example.com", False, "alice"),
            ("alice@example.com/phone", True, None),
            ("bob@example.com", False, None),
            ("bot@localhost/other", False, None),
            ("", False, None),
        ):
            with self.subTest(sender=sender, delayed=delayed):
                stanza = mock.Mock(xml=ET.Element("message"))
                if delayed:
                    ET.SubElement(stanza.xml, "{urn:xmpp:delay}delay", stamp="2026-01-01T00:00:00Z")
                self.assertEqual(get_user(JID(sender), stanza), expected)

        # A removal applies without a restart of the component
        with use_ipopo(self.context) as ipopo:
            ipopo.reconfigure("xmpp-shell", {"shell.xmpp.users": {}})
        self.assertIsNone(get_user(JID("alice@example.com"), mock.Mock(xml=ET.Element("message"))))

    def start_sessions(self, properties: dict[str, Any]) -> Any:
        """
        Instantiates the shell for two users, with commands anyone can run

        :return: The method handling a message
        """
        reference = self.context.get_service_reference(ShellService)
        assert reference is not None
        shell = self.context.get_service(reference)

        @CommandPermission(None)
        def ask(session: beans.ShellSession) -> None:
            session.write_line("Got: {0}", session.prompt("Value: ").strip())

        @CommandPermission(None)
        def hello(session: beans.ShellSession) -> None:
            session.write_line("Hello {0}", session.subject.name)

        @CommandPermission(None)
        def slow(session: beans.ShellSession) -> None:
            REPLIES.put(("", "started"))
            time.sleep(0.5)
            session.write_line("Done")

        shell.register_command("test", "ask", ask)
        shell.register_command("test", "hello", hello)
        shell.register_command("test", "slow", slow)
        while not REPLIES.empty():
            REPLIES.get()

        component = self.instantiate_component(
            {"shell.xmpp.users": {"alice@example.com": "alice", "bob@example.com": "bob"}, **properties}
        )
        self.sessions = component._IPopoXMPPShell__sessions
        self.waiting = component._IPopoXMPPShell__waiting
        return component._IPopoXMPPShell__on_message

    def test_sessions(self) -> None:
        """
        Each session has its own thread: a command waiting for input doesn't block the
        others, and gets an end of input when no answer comes in time
        """
        on_message = self.start_sessions({"shell.xmpp.idle_timeout": 1})

        on_message(message("alice@example.com/a", "test.ask"))
        self.assertEqual(REPLIES.get(timeout=5), ("alice@example.com/a", "Value:"))
        on_message(message("bob@example.com/b", "test.hello"))
        self.assertEqual(REPLIES.get(timeout=5), ("bob@example.com/b", "Hello bob"))
        on_message(message("alice@example.com/a", "42"))
        self.assertEqual(REPLIES.get(timeout=5), ("alice@example.com/a", "Got: 42"))
        self.assertEqual(self.waiting, {})

        # Nobody answers: the command ends, then the idle sessions
        on_message(message("alice@example.com/a", "test.ask"))
        self.assertEqual(REPLIES.get(timeout=5), ("alice@example.com/a", "Value:"))
        self.assertEqual(REPLIES.get(timeout=5), ("alice@example.com/a", "Got:"))
        for _ in range(50):
            if not self.sessions:
                break
            time.sleep(0.1)
        self.assertEqual(self.sessions, {})
        self.assertEqual(self.waiting, {})

    def test_stop_waits_for_commands(self) -> None:
        """
        The stop of the shell lets a running command end and send its output
        """
        on_message = self.start_sessions({})
        on_message(message("alice@example.com/a", "test.slow"))
        self.assertEqual(REPLIES.get(timeout=5), ("", "started"))

        with use_ipopo(self.context) as ipopo:
            ipopo.kill("xmpp-shell")
        self.assertEqual(REPLIES.get_nowait(), ("alice@example.com/a", "Done"))

    def test_max_sessions(self) -> None:
        """
        The limit applies to each JID: a user with many resources doesn't take the
        sessions of the others
        """
        on_message = self.start_sessions({"shell.xmpp.max_sessions": 1})
        on_message(message("alice@example.com/a", "test.hello"))
        self.assertEqual(REPLIES.get(timeout=5), ("alice@example.com/a", "Hello alice"))

        with self.assertLogs("pelix.shell.xmpp", "WARNING"):
            on_message(message("alice@example.com/b", "test.hello"))
        # Refused before any session or thread exists, which could reply later
        self.assertEqual(list(self.sessions), [JID("alice@example.com/a")])

        on_message(message("bob@example.com/b", "test.hello"))
        self.assertEqual(REPLIES.get(timeout=5), ("bob@example.com/b", "Hello bob"))
        self.assertTrue(REPLIES.empty())

    def test_revocation(self) -> None:
        """
        A JID which is no longer a user loses its subscription to the presence of the bot
        """
        component = self.instantiate_component({"shell.xmpp.users": {"alice@example.com": "alice"}})
        items = {}
        for jid, subscribed in (
            ("alice@example.com", True),
            ("bob@example.com", True),
            ("carol@example.com", False),
        ):
            items[jid] = mock.MagicMock()
            items[jid].__getitem__.side_effect = {"from": subscribed}.__getitem__
        stanza = mock.MagicMock()
        stanza.stream.client_roster = items

        revoke = component._IPopoXMPPShell__revoke_former_users
        revoke(stanza)
        self.assertEqual([jid for jid, item in items.items() if item.unauthorize.called], ["bob@example.com"])

        with use_ipopo(self.context) as ipopo:
            ipopo.reconfigure("xmpp-shell", {"shell.xmpp.users": {}})
        revoke(stanza)
        self.assertTrue(items["alice@example.com"].unauthorize.called)
        self.assertFalse(items["carol@example.com"].unauthorize.called)

    def test_subscription_requests(self) -> None:
        """
        Only the users see the presence of the bot
        """
        component = self.instantiate_component({"shell.xmpp.users": {"alice@example.com": "alice"}})
        for sender, authorized in (
            ("alice@example.com", True),
            ("alice@example.com/phone", True),
            ("bob@example.com", False),
            ("bot@localhost", False),
        ):
            with self.subTest(sender=sender):
                presence = mock.MagicMock()
                presence.__getitem__.side_effect = {
                    "from": JID(sender),
                    "to": JID("bot@localhost"),
                }.__getitem__
                component._IPopoXMPPShell__on_subscription_request(presence)
                item = presence.stream.roster.__getitem__.return_value.__getitem__.return_value
                self.assertEqual(
                    (item.authorize.called, item.unauthorize.called), (authorized, not authorized)
                )

    def test_bot_is_not_a_user(self) -> None:
        """
        Anyone with the password of the bot could use the shell as that user
        """
        with use_ipopo(self.context) as ipopo:
            ipopo.instantiate(
                FACTORY_XMPP_SHELL,
                "xmpp-shell",
                {
                    "shell.xmpp.jid": "bot@localhost",
                    "shell.xmpp.password": "foobar",
                    "shell.xmpp.users": {"BOT@localhost": "admin"},
                },
            )
            self.assertEqual(ipopo.get_instance_details("xmpp-shell")["state"], StoredInstance.ERRONEOUS)

    def test_tls_verify(self) -> None:
        """
        The certificate of the server is verified unless shell.xmpp.tls.verify is 0
        """
        for value, expected in ((None, True), ("1", True), ("0", False), ("yes please", True)):
            with self.subTest(value=value):
                bot = self.instantiate({} if value is None else {"shell.xmpp.tls.verify": value})
                try:
                    self.assertEqual(bot.kwargs["ssl_verify"], expected)
                finally:
                    with use_ipopo(self.context) as ipopo:
                        ipopo.kill("xmpp-shell")

    def test_main_tls(self) -> None:
        """
        The script uses STARTTLS and verifies the certificate unless told otherwise
        """
        for argv, tls, verify in (
            ([], True, True),
            (["--no-tls"], False, True),
            (["--no-tls-verify"], True, False),
        ):
            with (
                self.subTest(argv=argv),
                mock.patch("pelix.framework.create_framework"),
                mock.patch.object(pelix.shell.xmpp, "use_ipopo") as use_ipopo_mock,
            ):
                pelix.shell.xmpp.main(
                    ["-j", "bot@localhost", "--password", "foobar", "-u", "a@b=alice", *argv]
                )
                ipopo = use_ipopo_mock.return_value.__enter__.return_value
                properties = ipopo.instantiate.call_args.args[2]
                self.assertEqual(properties["shell.xmpp.tls"], tls)
                self.assertEqual(properties["shell.xmpp.tls.verify"], verify)
                self.assertEqual(properties["shell.xmpp.users"], {"a@b": "alice"})

        for user in ("a@b", "=alice", "a@b="):
            with self.subTest(user=user), self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                pelix.shell.xmpp.main(["-j", "bot@localhost", "--password", "foobar", "-u", user])


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
