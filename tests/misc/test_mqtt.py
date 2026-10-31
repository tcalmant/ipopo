#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the MQTT client module

:author: Thomas Calmant
"""

import logging
import socket
import threading
import time
import unittest
import uuid
from typing import cast

from pelix.utilities import EventData, to_str

try:
    import pelix.misc.mqtt_client as mqtt
except ImportError:
    # Missing requirement: not a fatal error
    raise unittest.SkipTest("MQTT client dependency missing: skip test")

from tests.mqtt_utilities import (
    MQTT_CERTS,
    MQTT_PASSWORD,
    MQTT_PORT_MTLS,
    MQTT_PORT_PASSWORD,
    MQTT_PORT_TLS,
    MQTT_USERNAME,
    find_mqtt_server,
    has_mqtt_secure_listeners,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
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
    sock = cast(socket.socket, client.raw_client._sock)
    pair_r = client.raw_client._sockpairR
    pair_w = client.raw_client._sockpairW

    # Explicitly set the them to None: Paho doesn't create new sockets if they are still set
    client.raw_client._sock = None
    client.raw_client._sockpairR = None
    client.raw_client._sockpairW = None

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


def _find_free_port() -> int:
    """
    Returns a local TCP port nothing listens on
    """
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


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
        event = EventData[mqtt.MqttClient]()

        def on_connect(clt: mqtt.MqttClient, result_code: int) -> None:
            if event.is_set():
                event.raise_exception(RuntimeError("Unexpected connection callback"))

            if result_code == 0:
                event.set(clt)
            else:
                event.raise_exception(RuntimeError(f"Connection failed with code {result_code}"))

        def on_disconnect(clt: mqtt.MqttClient, result_code: int) -> None:
            if event.is_set():
                event.raise_exception(RuntimeError("Unexpected disconnection callback"))

            if result_code == 0:
                event.set(clt)
            else:
                event.raise_exception(RuntimeError(f"Disconnection failed with code {result_code}"))

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
        assert event.data is not None
        self.assertEqual(event.data, client)

        # Clear event
        event.clear()

        # Disconnect
        client.disconnect()
        if not event.wait(5):
            self.fail("MQTT disconnection timeout")

        # Check client
        assert event.data is not None
        self.assertEqual(event.data, client)

    def test_events(self) -> None:
        """
        Tests notifications from client for different protocol versions

        This test tests all the possible callbacks of the Pelix MQTT client
        """
        assert MQTT_SERVER is not None

        for protocol in (mqtt.MQTTv31, mqtt.MQTTv311, mqtt.MQTTv5):
            with self.subTest(protocol=protocol):
                # Create client
                client = mqtt.MqttClient()
                event_connected = EventData[None]()
                event_disconnected = EventData[None]()
                event_message = EventData[mqtt.MqttMessage]()
                event_publish = EventData[int]()
                event_subscribe = EventData[tuple[int, list[int]]]()
                event_unsubscribe = EventData[int]()

                def on_connect(clt: mqtt.MqttClient, result_code: int) -> None:
                    if result_code == 0:
                        event_connected.set()  # noqa: B023
                    else:
                        event_connected.raise_exception(  # noqa: B023
                            RuntimeError(f"Connection failed with code {result_code}")
                        )

                def on_disconnect(clt: mqtt.MqttClient, result_code: int) -> None:
                    if result_code == 0:
                        event_disconnected.set()  # noqa: B023
                    else:
                        event_disconnected.raise_exception(  # noqa: B023
                            RuntimeError(f"Disconnection failed with code {result_code}")
                        )

                def on_message(clt: mqtt.MqttClient, msg: mqtt.MqttMessage) -> None:
                    event_message.set(msg)  # noqa: B023

                def on_publish(clt: mqtt.MqttClient, mid: int) -> None:
                    event_publish.set(mid)  # noqa: B023

                def on_subscribe(clt: mqtt.MqttClient, mid: int, granted_qos: list[int]) -> None:
                    event_subscribe.set((mid, granted_qos))  # noqa: B023

                def on_unsubscribe(clt: mqtt.MqttClient, mid: int) -> None:
                    event_unsubscribe.set(mid)  # noqa: B023

                client.on_connect = on_connect
                client.on_disconnect = on_disconnect
                client.on_message = on_message
                client.on_publish = on_publish
                client.on_subscribe = on_subscribe
                client.on_unsubscribe = on_unsubscribe

                # Connect
                client.connect(MQTT_SERVER)
                try:
                    if not event_connected.wait(5):
                        # Connection failed
                        self.fail("MQTT connection timeout")

                    # Subscribe
                    mid = client.subscribe("/pelix/test", 2)
                    if not event_subscribe.wait(5):
                        self.fail("MQTT subscription timeout")

                    if mid is None:
                        self.fail("Subscription failed")

                    # Check parameters
                    assert event_subscribe.data is not None
                    self.assertListEqual(list(event_subscribe.data), [mid, [2]])

                    # Publish
                    mid = client.publish("/pelix/test", "dummy", 2)
                    if not event_publish.wait(5):
                        self.fail("MQTT publication timeout")

                    # Check publication event
                    assert event_publish.data is not None
                    self.assertEqual(event_publish.data, mid)

                    # Wait for the reception event
                    if not event_message.wait(5):
                        self.fail("MQTT reception timeout")
                    assert event_message.data is not None
                    self.assertEqual(event_message.data.topic, "/pelix/test")
                    self.assertEqual(to_str(event_message.data.payload), "dummy")
                    self.assertEqual(event_message.data.qos, 2)

                    # Unsubscribe
                    mid = client.unsubscribe("/pelix/test")
                    if not event_unsubscribe.wait(5):
                        self.fail("MQTT unsubscription timeout")
                    assert event_unsubscribe.data is not None
                    self.assertEqual(event_unsubscribe.data, mid)
                finally:
                    # Disconnect
                    client.disconnect()

                if not event_disconnected.wait(5):
                    self.fail("MQTT disconnection timeout")

    def test_reconnect(self) -> None:
        """
        Tests the reconnection after a disconnection by the broker, and the
        renewal of the subscriptions the broker forgot
        """
        assert MQTT_SERVER is not None
        topic = f"pelix/test/mqtt/reconnect/{uuid.uuid4()!s}"
        client_id = mqtt.MqttClient.generate_id("rc-")

        client = mqtt.MqttClient(client_id)
        connections = threading.Semaphore(0)
        messages: list[bytes] = []
        client.on_connect = lambda clt, rc: connections.release() if rc == 0 else None
        client.on_message = lambda clt, msg: messages.append(msg.payload)

        sender = mqtt.MqttClient()
        client.connect(MQTT_SERVER, 1883, 10)
        sender.connect(MQTT_SERVER, blocking=True)
        try:
            self.assertTrue(connections.acquire(timeout=5), "Connection timeout")

            # Subscribed once, outside of on_connect
            client.subscribe(topic, 1)
            time.sleep(0.5)
            sender.wait_publication(cast(int, sender.publish(topic, "before", 1, wait=True)), 5)

            # Same client ID with a clean session: the broker disconnects the client
            # and forgets its session, subscriptions included
            intruder = mqtt.MqttClient(client_id, clean_session=True)
            intruder.connect(MQTT_SERVER, blocking=True)
            time.sleep(0.5)
            intruder.disconnect()

            self.assertTrue(connections.acquire(timeout=20), "No reconnection")
            time.sleep(0.5)
            sender.wait_publication(cast(int, sender.publish(topic, "after", 1, wait=True)), 5)
            time.sleep(1)
            self.assertEqual(messages, [b"before", b"after"])
        finally:
            sender.disconnect()
            client.disconnect()

    def test_disconnected_publish(self) -> None:
        """
        Messages published while disconnected: QoS 1 and 2 are queued, up to a
        limit, and sent once connected; QoS 0 is refused
        """
        assert MQTT_SERVER is not None
        topic = f"pelix/test/mqtt/queued/{uuid.uuid4()!s}"

        listener = mqtt.MqttClient()
        received: list[bytes] = []
        subscribed = threading.Event()
        listener.on_subscribe = lambda clt, mid, codes: subscribed.set()
        listener.on_message = lambda clt, msg: received.append(msg.payload)
        listener.connect(MQTT_SERVER, blocking=True)
        listener.subscribe(topic, 2)

        client = mqtt.MqttClient(max_queued_messages=2)
        try:
            self.assertTrue(subscribed.wait(5))

            # Never connected yet
            self.assertIsNone(client.publish(topic, "qos0", 0))
            queued = [client.publish(topic, f"qos{qos}", qos, wait=True) for qos in (1, 2)]
            self.assertNotIn(None, queued)
            self.assertIsNone(client.publish(topic, "full", 1), "Queue limit ignored")

            client.connect(MQTT_SERVER)
            for mid in queued:
                self.assertTrue(client.wait_publication(cast(int, mid), 10))
            time.sleep(1)
            self.assertEqual(sorted(received), [b"qos1", b"qos2"])
        finally:
            client.disconnect()
            listener.disconnect()

    def test_connection_failure(self) -> None:
        """
        A failed connection is logged as a warning and retried, TLS failures included
        """
        assert MQTT_SERVER is not None
        cases: list[tuple[str, dict[str, object]]] = [
            ("nothing listening", {"mqtt.port": _find_free_port()}),
        ]
        if has_mqtt_secure_listeners():
            cases.append(("untrusted broker", {"mqtt.port": MQTT_PORT_TLS, "mqtt.tls": True}))

        for name, props in cases:
            with self.subTest(name=name):
                config = mqtt.MqttConnectionConfig.from_properties({"mqtt.host": MQTT_SERVER, **props})
                client = config.make_client()
                try:
                    with self.assertLogs("pelix.misc.mqtt_client", logging.WARNING) as log_ctx:
                        config.connect(client)
                        # Retried after 1 second, then 2
                        time.sleep(4)
                finally:
                    client.disconnect()
                failures = [line for line in log_ctx.output if "Can't connect" in line]
                self.assertGreaterEqual(len(failures), 2, log_ctx.output)

    def test_mqtt_v5(self) -> None:
        """
        Tests a client using MQTT v5
        """
        assert MQTT_SERVER is not None
        topic = f"pelix/test/mqtt/v5/{uuid.uuid4()!s}"
        client = mqtt.MqttClient(protocol=mqtt.MQTTv5)
        received = EventData[mqtt.MqttMessage]()
        subscribed = threading.Event()
        client.on_subscribe = lambda clt, mid, codes: subscribed.set()
        client.on_message = lambda clt, msg: received.set(msg)
        client.connect(MQTT_SERVER, blocking=True)
        try:
            client.subscribe(topic, 1)
            self.assertTrue(subscribed.wait(5))
            self.assertTrue(client.wait_publication(cast(int, client.publish(topic, "v5", 1, wait=True)), 5))
            self.assertTrue(received.wait(5))
            assert received.data is not None
            self.assertEqual(received.data.payload, b"v5")
        finally:
            client.disconnect()

    def test_will(self) -> None:
        """
        Tests the will message configuration
        """
        assert MQTT_SERVER is not None

        will_topic = f"pelix/test/mqtt/will/{uuid.uuid4()!s}"
        will_value = str(uuid.uuid4())

        # Create client 1
        client = mqtt.MqttClient()
        event_connect = EventData[None]()

        def on_connect(clt: mqtt.MqttClient, result_code: int) -> None:
            if result_code == 0:
                event_connect.set()
            else:
                event_connect.raise_exception(RuntimeError(f"Connection failed with code {result_code}"))

        client.on_connect = on_connect

        # Create client 2
        client_2 = mqtt.MqttClient()
        event_connect_2 = EventData[None]()
        event_subscribe_2 = EventData[int]()
        event_message_2 = EventData[mqtt.MqttMessage]()

        def on_connect_2(clt: mqtt.MqttClient, result_code: int) -> None:
            if result_code == 0:
                # Client 2 subscribes to the will message
                clt.subscribe(will_topic)
                event_connect_2.set()
            else:
                event_connect_2.raise_exception(RuntimeError(f"Connection failed with code {result_code}"))

        def on_subscribe_2(clt: mqtt.MqttClient, mid: int, granted_qos: list[int]) -> None:
            event_subscribe_2.set(mid)

        def on_message_2(clt: mqtt.MqttClient, msg: mqtt.MqttMessage) -> None:
            event_message_2.set(msg)

        client_2.on_connect = on_connect_2
        client_2.on_subscribe = on_subscribe_2
        client_2.on_message = on_message_2

        # Check clients IDs
        self.assertNotEqual(client.client_id, client_2.client_id)

        # Set the will for client 1
        client.set_will(will_topic, will_value)

        # Connect clients
        client.connect(MQTT_SERVER, 1883, 10)
        client_2.connect(MQTT_SERVER, 1883)
        try:
            if not event_connect.wait(5):
                client.disconnect()
                self.fail("Client 1 timed out")

            if not event_connect_2.wait(5):
                client_2.disconnect()
                self.fail("Client 2 timed out")

            # Wait for its subscription
            if not event_subscribe_2.wait(5):
                self.fail("Client 2 subscription timed out")

            # Disconnect client 1
            _disconnect_client(client)

            # Check client 2
            if not event_message_2.wait(30):
                client_2.disconnect()
                self.fail("Will not received within 30 seconds")
        finally:
            client.disconnect()
            client_2.disconnect()

        # Check message
        msg = event_message_2.data
        assert msg is not None
        self.assertEqual(msg.topic, will_topic)
        self.assertEqual(to_str(msg.payload), will_value)

    def test_wait_publish(self) -> None:
        """
        Tests the wait_publish method
        """
        assert MQTT_SERVER is not None

        msg_topic = f"pelix/test/mqtt/wait/{uuid.uuid4()!s}"
        msg_value = str(uuid.uuid4())

        # Create client
        client = mqtt.MqttClient()
        event_connect = EventData[None]()
        event_msg = EventData[mqtt.MqttMessage]()

        def on_connect(clt: mqtt.MqttClient, result_code: int) -> None:
            if result_code == 0:
                clt.subscribe(msg_topic)
                event_connect.set()
            else:
                event_connect.raise_exception(RuntimeError(f"Connection failed with code {result_code}"))

        def on_message(clt: mqtt.MqttClient, msg: mqtt.MqttMessage) -> None:
            event_msg.set(msg)

        client.on_connect = on_connect
        client.on_message = on_message

        # Connect
        client.connect(MQTT_SERVER)
        try:
            if not event_connect.wait(5):
                self.fail("Connection timeout")

            # Send message
            mid = client.publish(msg_topic, msg_value, wait=True)
            assert mid is not None
            client.wait_publication(mid, 30)

            # Wait for the message to be received
            if not event_msg.wait(5):
                self.fail("Message not received after publication")
        finally:
            # Disconnect
            client.disconnect()

        # Get the message
        msg = event_msg.data
        assert msg is not None
        self.assertEqual(msg.topic, msg_topic)
        self.assertEqual(to_str(msg.payload), msg_value)

    def test_wait_publish_not_missed(self) -> None:
        """
        Tests that a publication notified while publish() is still running is
        not missed: the network loop thread can call back before the event of
        the message has been stored, which used to block the caller until the
        end of its timeout
        """
        assert MQTT_SERVER is not None

        msg_topic = f"pelix/test/mqtt/wait-race/{uuid.uuid4()!s}"

        client = mqtt.MqttClient()
        event_connect = EventData[None]()

        def on_connect(clt: mqtt.MqttClient, result_code: int) -> None:
            if result_code == 0:
                event_connect.set()
            else:
                event_connect.raise_exception(RuntimeError(f"Connection failed with code {result_code}"))

        client.on_connect = on_connect
        client.connect(MQTT_SERVER)
        try:
            if not event_connect.wait(5):
                self.fail("Connection timeout")

            for qos in (0, 1, 2):
                with self.subTest(qos=qos):
                    # Publish in a tight loop: the shorter the delay between the call to
                    # the Paho client and the storage of the event, the more likely the
                    # publication is notified in between
                    for idx in range(100):
                        mid = client.publish(msg_topic, f"value-{idx}", qos, wait=True)
                        self.assertIsNotNone(mid)
                        assert mid is not None
                        self.assertTrue(
                            client.wait_publication(mid, 5),
                            f"Publication {idx} (mid={mid}) was not notified",
                        )

            # Acknowledgements received while other threads publish used to dead lock
            def burst_loop(end: float = time.monotonic() + 2) -> None:
                while time.monotonic() < end:
                    client.publish(msg_topic, "burst", 1)

            bursts = [threading.Thread(target=burst_loop, daemon=True) for _ in range(4)]
            for burst in bursts:
                burst.start()
            for burst in bursts:
                burst.join(20)
                self.assertFalse(burst.is_alive(), "Publication burst blocked")

        finally:
            client.disconnect()

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
        client_id: str | None

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

        with self.assertLogs(level=logging.WARNING) as cm:
            client = mqtt.MqttClient(long_id)

        for line in cm.output:
            if long_id in line and "too long" in line:
                break
        else:
            self.fail("No warning for long client ID")

        # Client ID must be kept as is
        self.assertEqual(client.client_id, long_id)

    def test_clean_session(self) -> None:
        """
        Tests that a generated client ID implies a clean session: the broker
        would keep the session of a random ID forever, without any way to
        resume it
        """
        client_id: str | None

        def is_clean(client: mqtt.MqttClient) -> bool:
            """
            Returns the clean session flag given to the underlying Paho client
            """
            paho_client = vars(client)["_MqttClient__mqtt"]
            return bool(paho_client._clean_session)

        # No ID given: the session can't be resumed, it must be cleaned
        for client_id in (None, ""):
            self.assertTrue(is_clean(mqtt.MqttClient(client_id)))

        # Explicit ID: the caller decides
        self.assertFalse(is_clean(mqtt.MqttClient("custom_id")))
        self.assertTrue(is_clean(mqtt.MqttClient("custom_id", clean_session=True)))

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


class MqttConnectionConfigTest(unittest.TestCase):
    """
    Tests the connection configuration shared by the MQTT components
    """

    def test_from_properties(self) -> None:
        """
        Tests the parsing of the ``mqtt.*`` properties
        """
        ca = "/some/ca.crt"
        cases: list[tuple[dict[str, object], str, int, bool]] = [
            ({}, "localhost", 1883, False),
            ({"mqtt.host": "broker", "mqtt.port": "1884"}, "broker", 1884, False),
            ({"mqtt.tls": True}, "localhost", 8883, True),
            ({"mqtt.tls": "true"}, "localhost", 8883, True),
            ({"mqtt.tls": "false"}, "localhost", 1883, False),
            # A TLS file without the flag must not fall back to clear text
            ({"mqtt.tls.ca_file": ca}, "localhost", 8883, True),
            ({"mqtt.tls": False, "mqtt.tls.cert_file": "c.pem", "mqtt.port": 9883}, "localhost", 9883, True),
        ]
        for props, host, port, tls in cases:
            with self.subTest(props=props):
                config = mqtt.MqttConnectionConfig.from_properties(props, "secret")
                self.assertEqual(config.host, host)
                self.assertEqual(config.port or (8883 if config.use_tls else 1883), port)
                self.assertEqual(config.use_tls, tls)
                self.assertEqual(config.keepalive, 60)
                self.assertNotIn("secret", repr(config))
                self.assertEqual(config.max_queued_messages, mqtt.DEFAULT_MAX_QUEUED_MESSAGES)

        self.assertEqual(
            mqtt.MqttConnectionConfig.from_properties({"mqtt.max_queued_messages": "5"}).max_queued_messages,
            5,
        )

    def test_connect(self) -> None:
        """
        Tests the connection to the TLS and password listeners of the broker
        """
        if not has_mqtt_secure_listeners():
            self.skipTest("The MQTT broker has no TLS nor password listener")

        ca = str(MQTT_CERTS / "ca.crt")
        user = {"mqtt.username": MQTT_USERNAME}
        mtls = {
            "mqtt.port": MQTT_PORT_MTLS,
            "mqtt.tls.ca_file": ca,
            "mqtt.tls.cert_file": str(MQTT_CERTS / "client.crt"),
            "mqtt.tls.key_file": str(MQTT_CERTS / "client.key"),
            **user,
        }
        cases: list[tuple[dict[str, object], str | None, bool]] = [
            ({"mqtt.port": MQTT_PORT_PASSWORD}, None, False),
            ({"mqtt.port": MQTT_PORT_PASSWORD, **user}, "wrong", False),
            ({"mqtt.port": MQTT_PORT_PASSWORD, **user}, MQTT_PASSWORD, True),
            ({"mqtt.tls.ca_file": ca}, None, True),
            # The broker certificate is checked against the system authorities
            ({"mqtt.port": MQTT_PORT_TLS, "mqtt.tls": True}, None, False),
            # Host name not in the broker certificate
            ({"mqtt.host": "127.0.0.2", "mqtt.tls.ca_file": ca}, None, False),
            ({**mtls, "mqtt.tls.cert_file": None, "mqtt.tls.key_file": None}, MQTT_PASSWORD, False),
            (mtls, MQTT_PASSWORD, True),
        ]
        for props, password, expected in cases:
            with self.subTest(props=props, password=password):
                config = mqtt.MqttConnectionConfig.from_properties(props, password)
                connected = threading.Event()
                client = config.make_client()
                client.on_connect = lambda clt, rc, evt=connected: evt.set() if rc == 0 else None
                config.connect(client)
                try:
                    self.assertEqual(connected.wait(5 if expected else 2), expected)
                finally:
                    client.disconnect()

        # Invalid TLS files are refused before connecting
        with self.assertRaises(OSError):
            mqtt.MqttConnectionConfig.from_properties({"mqtt.tls.ca_file": "/missing/ca.crt"}).make_client()


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
