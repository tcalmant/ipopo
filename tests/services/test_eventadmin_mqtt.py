#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the EventAdmin MQTT bridge service

:author: Thomas Calmant
"""

# Pelix
from pelix.ipopo.constants import use_ipopo
import pelix.framework
import pelix.misc.mqtt_client
import pelix.services

# Standard library
import json
import threading
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class MQTTListener:
    """
    An MQTT message listener
    """
    def __init__(self, host, port, prefix):
        """
        :param host: MQTT Server host
        :param port: MQTT Server port
        :param prefix: Event Admin Bridge topic prefix
        """
        self.host = host
        self.port = port
        self.prefix = prefix

        # Prepare a Mqtt Client
        self._client = pelix.misc.mqtt_client.MqttClient()
        self._client.on_connect = self.on_connect
        self._client.on_disconnect = self.on_disconnect
        self._client.on_message = self.on_message

        # Received messages
        self.messages = []

        # Some control event
        self.connect_event = threading.Event()
        self.message_event = threading.Event()

    def start(self):
        """
        Connect the client
        """
        # Connect to server
        self._client.connect(self.host, self.port)

    def stop(self):
        """
        Disconnects the client
        """
        self._client.disconnect()

    def on_connect(self, client, rc):
        """
        Connected to server
        """
        client.subscribe("{}/#".format(self.prefix))
        self.connect_event.set()

    def on_disconnect(self, client, rc):
        """
        Disconnected from server
        """
        self.connect_event.clear()

    def on_message(self, client, message):
        """
        Got an MQTT message
        """
        self.messages.append(message)
        self.message_event.set()

    def publish(self, topic, payload):
        """
        Sends an MQTT message

        :param topic: Message topic
        :param payload: Message content
        """
        return self._client.publish(topic, payload, qos=1)


class DummyEventHandler(object):
    """
    Dummy event handler
    """
    def __init__(self):
        """
        Sets up members
        """
        # Topic of the last received event
        self.last_event = None
        self.last_props = {}
        self.__event = threading.Event()

    def handle_event(self, topic, properties):
        """
        Handles an event received from EventAdmin
        """
        # Keep received values
        self.last_event = topic
        self.last_props = properties
        self.__event.set()

    def pop_event(self):
        """
        Pops the list of events
        """
        # Clear the event for next try
        self.__event.clear()

        # Reset last event
        event, self.last_event = self.last_event, None
        props, self.last_props = self.last_props, {}
        return event, props

    def wait(self, timeout=5):
        """
        Waits for the event to be received
        """
        self.__event.wait(timeout)

# ------------------------------------------------------------------------------


class EventAdminMqttBridgeTest(unittest.TestCase):
    """
    Tests the EventAdmin MQTT bridge service
    """
    HOST = "test.mosquitto.org"
    PORT = 1883

    def assertDictContains(self, subset, container):
        """
        Ensures that the given subset exists in the container

        :param subset: A subset dictionary
        :param container: The dictionary that should container the other one
        """
        try:
            for key, value in subset.items():
                container_value = container[key]
                self.assertEqual(
                    value, container_value,
                    "Different values for {}: {} != {}".format(
                        key, value, container_value))
        except KeyError as ex:
            self.fail("{} misses from container".format(ex))

    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core',
             'pelix.services.eventadmin'))
        self.framework.start()

        # Instantiate the EventAdmin component
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            self.event_admin = ipopo.instantiate(
                pelix.services.FACTORY_EVENT_ADMIN,
                "event-admin", {})

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.framework = None

    def _setup_bridge(self, event_filter, mqtt_prefix):
        """
        Instantiates the MQTT Event Admin bridge

        :param event_filter: Filter on EventAdmin topics
        :param mqtt_prefix: Prefix to use in MQTT topics
        """
        context = self.framework.get_bundle_context()
        context.install_bundle("pelix.services.eventadmin_mqtt").start()

        name = "mqtt-bridge"
        with use_ipopo(context) as ipopo:
            ipopo.instantiate(
                pelix.services.FACTORY_EVENT_ADMIN_MQTT,
                "mqtt-bridge",
                {pelix.services.PROP_EVENT_TOPICS: event_filter,
                 "mqtt.host": self.HOST, "mqtt.port": self.PORT,
                 "mqtt.topic.prefix": mqtt_prefix}
            )

        # Wait for it
        svc_ref = None
        while svc_ref is None:
            svc_ref = context.get_service_reference(
                pelix.services.SERVICE_EVENT_HANDLER,
                "(instance.name={})".format(name))

    def _register_handler(self, topics, evt_filter=None):
        """
        Registers an event handler

        :param topics: Event topics
        :param evt_filter: Event filter
        """
        svc = DummyEventHandler()
        context = self.framework.get_bundle_context()
        svc_reg = context.register_service(
            pelix.services.SERVICE_EVENT_HANDLER, svc,
            {pelix.services.PROP_EVENT_TOPICS: topics,
             pelix.services.PROP_EVENT_FILTER: evt_filter})
        return svc, svc_reg

    def test_bridge_emit(self):
        """
        Tests the MQTT bridge emission behaviour
        """
        # Prepare a handler
        handler, _ = self._register_handler('/mqtt/*')

        # Configuration
        bridge_prefix = "pelix/test/emit"
        bridge_event_filter = "/mqtt/propagate/*"

        # Setup a client
        client = MQTTListener(self.HOST, self.PORT, bridge_prefix)
        client.start()
        if not client.connect_event.wait(10):
            self.fail("Couldn't connect to MQTT server")

        try:
            # Instantiate the MQTT Event Admin bridge
            self._setup_bridge(bridge_event_filter, bridge_prefix)

            # Send an event in the filter and that can be propagate
            topic = "/mqtt/propagate/foobar"
            props = {"answer": 42, "foo": "bar", "list": list(range(5)),
                     pelix.services.EVENT_PROP_PROPAGATE: True}
            self.event_admin.send(topic, props)

            # Check if it has been received by the handler
            handler.wait()
            last_topic, last_props = handler.pop_event()
            self.assertEqual(last_topic, topic, "Bad topic")
            self.assertDictContains(props, last_props)

            # Wait for it in the MQTT client
            if not client.message_event.wait(10):
                self.fail("No message received from MQTT")

            # Ensure we find the properties in the payload
            message = client.messages.pop()
            self.assertIn(topic, message.topic)
            self.assertDictContains(
                props, json.loads(message.payload.decode('utf-8')))
        finally:
            client.stop()

    def test_bridge_filter(self):
        """
        Tests the MQTT bridge emission behaviour
        """
        # Prepare a handler
        handler, _ = self._register_handler('/mqtt/*')

        # Configuration
        bridge_prefix = "pelix/test/filter"
        bridge_event_filter = "/mqtt/propagate/*"

        # Setup a client
        client = MQTTListener(self.HOST, self.PORT, bridge_prefix)
        client.start()
        if not client.connect_event.wait(10):
            self.fail("Couldn't connect to MQTT server")

        try:
            # Instantiate the MQTT Event Admin bridge
            self._setup_bridge(bridge_event_filter, bridge_prefix)

            # Send an event in the filter without propagation flag
            topic = "/mqtt/propagate/foobar"
            props = {"test_id": 1}
            self.event_admin.send(topic, props)

            # Check if it has been received by the handler
            handler.wait()
            last_topic, last_props = handler.pop_event()
            self.assertEqual(last_topic, topic, "Bad topic")

            # Wait for it in the MQTT client
            if client.message_event.wait(5):
                self.fail("Message received from MQTT while it shouldn't")

            # -------------------------------------------------
            # Send an event in the filter with propagation flag
            # (to ensure this works)
            topic = "/mqtt/propagate/another"
            props = {"test_id": 2, pelix.services.EVENT_PROP_PROPAGATE: True}
            self.event_admin.send(topic, props)

            # Check if it has been received by the handler
            handler.wait()
            last_topic, last_props = handler.pop_event()
            self.assertEqual(last_topic, topic, "Bad topic")

            # Wait for it in the MQTT client
            if not client.message_event.wait(5):
                self.fail("Message not received from MQTT")

            # Ensure we find the properties in the payload
            message = client.messages.pop()
            self.assertIn(topic, message.topic)
            self.assertDictContains(
                props, json.loads(message.payload.decode('utf-8')))

            # -------------------------------------------------
            # Send an event in the filter with propagation flag
            # (to ensure this works)
            client.message_event.clear()
            topic = "/mqtt/no-propagate/another"
            props = {"test_id": 3}
            self.event_admin.send(topic, props)

            # Check if it has been received by the handler
            handler.wait()
            last_topic, last_props = handler.pop_event()
            self.assertEqual(last_topic, topic, "Bad topic")

            # Wait for it in the MQTT client
            for _ in range(5):
                if client.message_event.wait(1):
                    while True:
                        try:
                            msg = client.messages.pop()
                            if msg.topic == topic:
                                self.fail("Got an unexpected message")
                        except IndexError:
                            # No message in queue
                            client.message_event.clear()
        finally:
            client.stop()

    def test_from_mqtt(self):
        """
        Tests the events received from MQTT
        """
        # Prepare a handler
        handler, _ = self._register_handler('from-mqtt/*')

        # Configuration
        bridge_prefix = "pelix/test/filter"
        bridge_event_filter = "/mqtt/*"

        # Instantiate the MQTT Event Admin bridge
        self._setup_bridge(bridge_event_filter, bridge_prefix)

        # Setup a client
        client = MQTTListener(self.HOST, self.PORT, bridge_prefix)
        client.start()
        if not client.connect_event.wait(10):
            self.fail("Couldn't connect to MQTT server")

        try:
            # Send a forged message
            topic = "from-mqtt/foobar"
            props = {pelix.services.EVENT_PROP_FRAMEWORK_UID: "custom-client",
                     "test": "from mqtt",
                     "some": "answer"}

            payload = json.dumps(props).encode("utf-8")
            client.publish("{}/{}".format(bridge_prefix, topic), payload)

            # Wait for the message
            handler.wait(10)
            last_topic, last_props = handler.pop_event()
            if not last_topic:
                self.fail("Message not received by local handler")

            # Check topic
            self.assertEqual(last_topic, topic, "Bad topic")

            # The bridge changes the properties a bit
            client_id = props.pop(pelix.services.EVENT_PROP_FRAMEWORK_UID)
            fw_uid = self.framework.get_property(pelix.framework.FRAMEWORK_UID)

            # Check untouched properties
            self.assertDictContains(props, last_props)

            # Check the source UID (changed to avoid loops)
            self.assertEqual(
                last_props[pelix.services.EVENT_PROP_FRAMEWORK_UID], fw_uid)

            # Check that we still can be find the real source UID
            self.assertIn(client_id, last_props.values())
            self.assertDictContains(props, last_props)
        finally:
            client.stop()
