#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the MQTT client module

:author: Thomas Calmant
"""

import logging
import os
import socket
import sys
import threading
import time
import unittest
import uuid
from typing import Optional, cast

from pelix.utilities import to_str

try:
    import pelix.misc.mqtt_client as mqtt
except ImportError:
    # Missing requirement: not a fatal error
    raise unittest.SkipTest("MQTT client dependency missing: skip test")

from tests.mqtt_utilities import find_mqtt_server

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

MQTT_SERVER = find_mqtt_server()
if not MQTT_SERVER:
    raise unittest.SkipTest("No valid MQTT server found")

# ------------------------------------------------------------------------------


def _disconnect_client(client: mqtt.MqttClient) -> None:
    """
    Disconnects the client (implementation specific)

    :param client: MQTT Client
    """
    # Get all the socket references
    sock = cast(Optional[socket.socket], getattr(client.raw_client, "_sock"))
    pair_r = cast(Optional[socket.socket], getattr(client.raw_client, "_sockpairR"))
    pair_w = cast(Optional[socket.socket], getattr(client.raw_client, "_sockpairW"))

    # Explicitly set the them to None: Paho doesn't create new sockets if they are still set
    setattr(client.raw_client, "_sock", None)
    setattr(client.raw_client, "_sockpairR", None)
    setattr(client.raw_client, "_sockpairW", None)

    # Shutdown sockets (unblocks the underlying select() call) and close them
    if sock is not None:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()

    if pair_w is not None:
        pair_w.shutdown(socket.SHUT_RDWR)
        pair_w.close()

    if pair_r is not None:
        pair_r.shutdown(socket.SHUT_RDWR)
        pair_r.close()


class MqttClientTest(unittest.TestCase):
    """
    Tests the MQTT client provided by Pelix
    """

    def test_connect(self) -> None:
        """
        Test the client connection
        """
        assert MQTT_SERVER is not None

        # Create client
        client = mqtt.MqttClient()
        event = threading.Event()
        shared = []

        def on_connect(clt, result_code):
            if result_code == 0:
                shared.append(clt)
                event.set()

        def on_disconnect(clt, result_code):
            if result_code == 0:
                shared.append(clt)
                event.set()

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect

        # Check length of client ID
        self.assertLessEqual(len(client.client_id), 23)

        # Connect
        client.connect(MQTT_SERVER)
        if not event.wait(5):
            # Connection failed ?
            client.disconnect()
            self.fail("MQTT connection timeout")

        # Check client (and single call)
        self.assertListEqual(shared, [client])

        # Clear
        del shared[:]
        event.clear()

        # Disconnect
        client.disconnect()
        if not event.wait(5):
            self.fail("MQTT disconnection timeout")

        # Check client (and single call)
        self.assertListEqual(shared, [client])

    def test_reconnect(self) -> None:
        """
        Tests client reconnection
        """
        assert MQTT_SERVER is not None

        if os.name == "posix":
            # FIXME: try harder
            self.skipTest("This test doesn't work on POSIX...")

        # Avoid typo
        topic = "/pelix/test"

        # Create clients
        client = mqtt.MqttClient()
        client_2 = mqtt.MqttClient()

        # Enable Paho logging as this test can fail easily
        client.raw_client.enable_logger()

        event_connect = threading.Event()
        event_disconnect = threading.Event()
        event_message = threading.Event()

        client_2_connected = threading.Event()

        def on_connect(clt: mqtt.MqttClient, result_code: int) -> None:
            # Subscribe to test messages
            clt.subscribe(topic, 2)

            # Continue the test
            event_connect.set()

        def on_disconnect(clt: mqtt.MqttClient, result_code: int) -> None:
            event_disconnect.set()

        def on_message(clt: mqtt.MqttClient, msg: mqtt.MqttMessage) -> None:
            event_message.set()

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        # Setup client 2
        client_2.on_connect = lambda *_: client_2_connected.set()

        # Connect
        client.connect(MQTT_SERVER, 1883, 10)
        client_2.connect(MQTT_SERVER, 1883)

        try:
            if not event_connect.wait(5):
                # Connection failed
                self.fail("MQTT connection timeout")

            if not client_2_connected.wait(5):
                self.fail("Second client connection timeout")

            # Send something from client 2 to test client
            mid = client_2.publish(topic, "dummy1", qos=2, wait=True)
            assert mid is not None
            client_2.wait_publication(mid, 5)

            # Ensure we get it
            if not event_message.wait(5):
                self.fail("Message not received")
            event_message.clear()

            # Disconnect test client
            event_connect.clear()
            _disconnect_client(client)

            # Wait for the reconnection event
            if not event_connect.wait(20):
                self.fail("Connection event not received")

            # Test a new message
            mid = client_2.publish(topic, "dummy2", qos=2, wait=True)
            assert mid is not None
            client_2.wait_publication(mid, 5)

            # Ensure we get it
            if not event_message.wait(5):
                self.fail("Message not received")
            event_message.clear()

            # NOTE: Disconnection event is not received on reconnect
            if not event_disconnect.is_set():
                logging.warning("Disconnection event not received")
        finally:
            # Clean up
            client_2.disconnect()
            client.disconnect()

    def test_will(self) -> None:
        """
        Tests the will message configuration
        """
        assert MQTT_SERVER is not None

        will_topic = "pelix/test/mqtt/will/{0}".format(str(uuid.uuid4()))
        will_value = str(uuid.uuid4())

        # Create client 1
        client = mqtt.MqttClient()
        event = threading.Event()

        def on_connect(clt: mqtt.MqttClient, result_code: int) -> None:
            if result_code == 0:
                event.set()

        def on_disconnect(clt: mqtt.MqttClient, result_code: int) -> None:
            if result_code != 0:
                # Disconnected unwillingly: stop the timer
                # -- IMPLEMENTATION SPECIFIC --
                getattr(clt, "_MqttClient__stop_timer")()
                # == IMPLEMENTATION SPECIFIC ==

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect

        # Create client 2
        client_2 = mqtt.MqttClient()
        event_2 = threading.Event()
        shared_2 = []

        def on_connect_2(clt, result_code):
            if result_code == 0:
                event_2.set()

        def on_message_2(clt, msg):
            event_2.set()
            shared_2.append(msg)

        client_2.on_connect = on_connect_2
        client_2.on_message = on_message_2

        # Check clients IDs
        self.assertNotEqual(client.client_id, client_2.client_id)

        # Set the will for client 1
        client.set_will(will_topic, will_value)

        # Connect client 1
        client.connect(MQTT_SERVER, 1883, 10)
        if not event.wait(5):
            client.disconnect()
            self.fail("Client 1 timed out")

        # Connect client 2
        client_2.connect(MQTT_SERVER, 1883)
        if not event_2.wait(5):
            client_2.disconnect()
            self.fail("Client 2 timed out")

        # Clear events
        event.clear()
        event_2.clear()

        # Client 2 subscribes to the will message
        client_2.subscribe(will_topic)

        # Wait a little, so that the subscription is activated
        time.sleep(5)

        # Disconnect client 1
        _disconnect_client(client)

        # Check client 2
        if not event_2.wait(30):
            client_2.disconnect()
            self.fail("Will not received within 30 seconds")

        # Disconnect client 2
        client_2.disconnect()

        # Check message
        msg = shared_2[0]
        self.assertEqual(msg.topic, will_topic)
        self.assertEqual(to_str(msg.payload), will_value)

    def test_wait_publish(self) -> None:
        """
        Tests the wait_publish method
        """
        assert MQTT_SERVER is not None

        msg_topic = "pelix/test/mqtt/wait/{0}".format(str(uuid.uuid4()))
        msg_value = str(uuid.uuid4())

        # Create client
        client = mqtt.MqttClient()
        event = threading.Event()
        shared = []

        def on_connect(clt: mqtt.MqttClient, result_code: int) -> None:
            if result_code == 0:
                event.set()

        def on_message(clt: mqtt.MqttClient, msg: mqtt.MqttMessage) -> None:
            shared.append(msg)
            event.set()

        client.on_connect = on_connect
        client.on_message = on_message

        # Connect
        client.connect(MQTT_SERVER)
        client.subscribe(msg_topic)

        if not event.wait(5):
            client.disconnect()
            self.fail("Connection timeout")

        # Send message
        event.clear()
        mid = client.publish(msg_topic, msg_value, wait=True)
        assert mid is not None
        client.wait_publication(mid)

        # Wait for the message to be received
        if not event.wait(5):
            client.disconnect()
            self.fail("Message not received after publication")

        # Disconnect
        client.disconnect()

        # Get the message
        msg = shared[0]
        self.assertEqual(msg.topic, msg_topic)
        self.assertEqual(to_str(msg.payload), msg_value)

    def test_client_id(self) -> None:
        """
        Tests the generation of a client ID
        """
        # With default prefix
        clt_id = mqtt.MqttClient.generate_id()

        # Check length of ID
        self.assertLessEqual(len(clt_id), 23)

        # With a given prefix
        for prefix in (None, "", "+", "prefix"):
            clt_id = mqtt.MqttClient.generate_id(prefix)

            # Check length of ID
            self.assertLessEqual(len(clt_id), 23)

            # Check prefix
            if prefix:
                self.assertTrue(clt_id.startswith(prefix), "Prefix not in client ID")

        # With a long prefix, around the maximum length
        for length in (20, 23, 25):
            prefix = "a" * length
            clt_id = mqtt.MqttClient.generate_id(prefix)

            # Check length of ID
            self.assertLessEqual(len(clt_id), 23)

            # Check uniqueness
            self.assertNotEqual(clt_id, mqtt.MqttClient.generate_id(prefix))

    def test_constructor(self) -> None:
        """
        Tests the client ID handling in the constructor
        """
        # Valid ID given
        for client_id in ("custom_id", "other-id", mqtt.MqttClient.generate_id()):
            client = mqtt.MqttClient(client_id)
            self.assertEqual(client.client_id, client_id)

        # No ID given
        for client_id in (None, ""):
            client = mqtt.MqttClient(client_id)

            # Check length of ID
            self.assertLessEqual(len(client.client_id), 23)
            self.assertGreater(len(client.client_id), 0)

        # Long ID
        long_id = "a" * 30

        if sys.version_info[:2] >= (3, 4):
            # assertLogs has been added in Python 3.4
            with self.assertLogs(level=logging.WARNING) as cm:
                client = mqtt.MqttClient(long_id)

            for line in cm.output:
                if long_id in line and "too long" in line:
                    break
            else:
                self.fail("No warning for long client ID")
        else:
            # Log test not available
            client = mqtt.MqttClient(long_id)

        # Client ID must be kept as is
        self.assertEqual(client.client_id, long_id)

    def test_topic_matches(self) -> None:
        """
        Tests the topic_matches() method
        """
        simple_topics = ("test", "other_test", "some-test", "1234")

        # Basic test (single level)
        for topic in simple_topics:
            # Identity
            self.assertTrue(mqtt.MqttClient.topic_matches(topic, topic), topic)

            # All
            self.assertTrue(mqtt.MqttClient.topic_matches("#", topic), topic)
            self.assertFalse(mqtt.MqttClient.topic_matches("/#", topic), topic)

            # First level
            self.assertTrue(mqtt.MqttClient.topic_matches("+", topic), topic)
            self.assertFalse(mqtt.MqttClient.topic_matches("/+", topic), topic)

        # With a starting '/'
        for topic in simple_topics:
            topic = "/" + topic

            # Identity
            self.assertTrue(mqtt.MqttClient.topic_matches(topic, topic), topic)

            # All
            self.assertTrue(mqtt.MqttClient.topic_matches("#", topic), topic)

            # Second level
            self.assertTrue(mqtt.MqttClient.topic_matches("/+", topic), topic)
            self.assertFalse(mqtt.MqttClient.topic_matches("+", topic), topic)

        # Check wildcards
        for topic in ("first/second/third/fourth", "first/third/second/fourth"):
            self.assertTrue(mqtt.MqttClient.topic_matches("#", topic))
            self.assertTrue(mqtt.MqttClient.topic_matches("first/#", topic))
            self.assertFalse(mqtt.MqttClient.topic_matches("first/+", topic))

            for part in topic.split("/"):
                # Single part...
                self.assertFalse(mqtt.MqttClient.topic_matches(part, topic))

            # Single-level wildcard
            self.assertTrue(mqtt.MqttClient.topic_matches("first/+/+/fourth", topic))
            self.assertFalse(mqtt.MqttClient.topic_matches("first/+/fourth", topic))

            # Invalid filters (text after wildcard
            for invalid_filter in ("first/#/fourth", "#/second/#", "#/third/#", "#/fourth"):
                self.assertFalse(mqtt.MqttClient.topic_matches(invalid_filter, topic))


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
