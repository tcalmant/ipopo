#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the file-like objects of the XMPP shell, without an XMPP server

:author: Thomas Calmant
"""

import unittest
from typing import Any, cast

try:
    from slixmpp.jid import JID

    from pelix.shell.xmpp import IPopoXMPPShell, _XmppInStream, _XmppOutStream
except ImportError:
    raise unittest.SkipTest("XMPP client dependency missing: skip test")

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 4)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class _FakeClient:
    """
    Stores the messages sent by the XMPP output stream
    """

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)


class _FakeShell:
    """
    Gives the XMPP input stream predefined messages
    """

    def __init__(self, messages: list[str | None]) -> None:
        self.messages = list(messages)

    def read_from(self, jid: JID) -> str | None:
        return self.messages.pop(0) if self.messages else None


class XmppStreamsTest(unittest.TestCase):
    """
    Tests the XMPP shell streams
    """

    def setUp(self) -> None:
        """
        Prepares the fake XMPP peers
        """
        self.jid = JID("user@localhost")
        self.client = _FakeClient()

    def make_output(self) -> _XmppOutStream:
        return _XmppOutStream(cast(Any, self.client), self.jid)

    def make_input(self, *messages: str | None) -> _XmppInStream:
        return _XmppInStream(cast(IPopoXMPPShell, _FakeShell(list(messages))), self.jid)

    def test_output_flush(self) -> None:
        """
        Tests that the output is sent as a single message on flush
        """
        out = self.make_output()
        self.assertEqual(out.mode, "w")
        self.assertTrue(out.writable())

        self.assertEqual(out.write("Hello, "), 7)
        out.writelines(["World", "!"])
        self.assertEqual(self.client.messages, [])

        out.flush()
        self.assertEqual(len(self.client.messages), 1)
        self.assertEqual(self.client.messages[0]["mbody"], "Hello, World!")
        self.assertEqual(self.client.messages[0]["mto"], self.jid)

        # Nothing to send: no message
        out.flush()
        self.assertEqual(len(self.client.messages), 1)

    def test_output_close(self) -> None:
        """
        Tests that pending output is sent when the stream is closed
        """
        out = self.make_output()
        out.write("pending")
        out.close()
        self.assertTrue(out.closed)
        self.assertEqual([msg["mbody"] for msg in self.client.messages], ["pending"])

        # Closing twice must not send anything else
        out.close()
        self.assertEqual(len(self.client.messages), 1)
        self.assertRaises(ValueError, out.write, "more")

    def test_input(self) -> None:
        """
        Tests reading messages
        """
        stream = self.make_input("first", "second", "third", None)
        self.assertEqual(stream.mode, "r")
        self.assertTrue(stream.readable())

        # The whole message is returned without a limit
        self.assertEqual(stream.readline(), "first")
        self.assertEqual(stream.read(3), "sec")
        self.assertEqual(stream.read(), "third")

        # No more message: end of stream
        self.assertEqual(stream.readline(), "")

    def test_input_iteration(self) -> None:
        """
        Tests that iteration stops at the end of the stream
        """
        self.assertEqual(list(self.make_input("a", "b", None, "c")), ["a", "b"])
        self.assertEqual(self.make_input("a", "b").readlines(), ["a", "b"])


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
