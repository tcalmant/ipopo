#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the XMPP client module

This module considers there is an XMPP server listening on localhost with two
users (user1 and user2) with "foobar" as password.

:author: Thomas Calmant
"""

import random
import socket
import string
import threading
try:
    import unittest2 as unittest
except ImportError:
    import unittest

try:
    import pelix.misc.xmpp as xmpp
except ImportError:
    # Missing requirement: not a fatal error
    raise unittest.SkipTest("XMPP client dependency missing: skip test")

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class XMPPClientTest(unittest.TestCase):
    """
    Tests the XMPP client provided by Pelix
    """
    def test_communication(self):
        """
        Tests basic XMPP communication
        """
        bot1 = xmpp.BasicBot("user1@localhost", "foobar")
        bot2 = xmpp.BasicBot("user2@localhost", "foobar")

        # Connect server
        bot1.connect(socket.gethostbyname(socket.gethostname()), 5222)
        bot2.connect(socket.gethostbyname(socket.gethostname()), 5222)

        # Ensure both bots can talk to each other
        bot1.update_roster("user2@localhost", subscription="both")
        bot2.update_roster("user1@localhost", subscription="both")

        # Register the message event handler
        bot1_msg = []
        bot2_msg = []
        event1 = threading.Event()
        event2 = threading.Event()

        def on_message(data, msg_list, event):
            if data['type'] in ('normal', 'chat'):
                # Got a message
                sender = data['from'].full
                body = data['body'].strip()

                msg_list.append((sender, body))
                event.set()

        bot1.add_event_handler(
            "message", lambda data: on_message(data, bot1_msg, event1))
        bot2.add_event_handler(
            "message", lambda data: on_message(data, bot2_msg, event2))

        # Generate messages
        shuffle_data = list(string.ascii_letters)
        random.shuffle(shuffle_data)
        message1 = ''.join(shuffle_data)
        random.shuffle(shuffle_data)
        message2 = ''.join(shuffle_data)

        # Send'em
        bot1.send_message("user2@localhost", message1)
        bot2.send_message("user1@localhost", message2)

        # Check what has been received
        event2.wait()
        sender2, msg2 = bot2_msg.pop()
        self.assertEqual(sender2, bot1.fulljid)
        self.assertEqual(msg2, message1)

        event1.wait()
        sender1, msg1 = bot1_msg.pop()
        self.assertEqual(sender1, bot2.fulljid)
        self.assertEqual(msg1, message2)

        # Clean up
        bot1.disconnect()
        bot2.disconnect()
