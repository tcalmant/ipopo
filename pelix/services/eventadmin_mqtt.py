#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
A bridge to publish and subscribe to EventAdmin events over the network using
MQTT

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

# Standard library
import json
import logging

# Pelix
from pelix.ipopo.decorators import (
    ComponentFactory,
    Provides,
    Property,
    Validate,
    Invalidate,
    Requires,
)
from pelix.utilities import to_str
import pelix.constants as constants
import pelix.misc.mqtt_client
import pelix.services as services

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

DEFAULT_MQTT_TOPIC = "pelix/eventadmin"
""" Default MQTT topic to use to propagate events """

EVENT_PROP_SOURCE_UID = "pelix.eventadmin.mqtt.source"
""" UID of the framework that sent the event """

EVENT_PROP_STARTING_SLASH = "pelix.eventadmin.mqtt.start_slash"
""" Flag to indicate that the EventAdmin topic starts with a '/' """

# ------------------------------------------------------------------------------


@ComponentFactory(services.FACTORY_EVENT_ADMIN_MQTT)
@Provides(services.SERVICE_EVENT_HANDLER, "_controller")
@Requires("_event", services.SERVICE_EVENT_ADMIN)
@Property("_event_topics", services.PROP_EVENT_TOPICS, "*")
@Property("_host", "mqtt.host", "localhost")
@Property("_port", "mqtt.port", 1883)
@Property("_mqtt_topic", "mqtt.topic.prefix", DEFAULT_MQTT_TOPIC)
class MqttEventAdminBridge(object):
    """
    The EventAdmin MQTT bridge
    """

    def __init__(self):
        """
        Sets up the members
        """
        # MQTT configuration
        self._host = "localhost"
        self._port = 1883
        self._mqtt_topic = None

        # MQTT Client
        self._mqtt = None

        # EventAdmin
        self._event = None
        self._event_topics = None

        # EventHandler service controller
        self._controller = False

        # Framework UID
        self._framework_uid = None

    @Validate
    def _validate(self, context):
        """
        Component validated
        """
        # Store the framework UID
        self._framework_uid = context.get_property(constants.FRAMEWORK_UID)

        if not self._mqtt_topic:
            # No topic given, use the default one
            self._mqtt_topic = DEFAULT_MQTT_TOPIC

        if self._mqtt_topic[-1] == "/":
            # Remove trailing slash
            self._mqtt_topic = self._mqtt_topic[:-1]

        # Create the MQTT client
        self._mqtt = pelix.misc.mqtt_client.MqttClient()

        # Customize callbacks
        self._mqtt.on_connect = self.__on_connect
        self._mqtt.on_disconnect = self.__on_disconnect
        self._mqtt.on_message = self.__on_message

        # Do not provide the EventHandler service before being connected
        self._controller = False

        # Prepare the connection
        self._mqtt.connect(self._host, self._port)

    @Invalidate
    def _invalidate(self, _):
        """
        Component invalidated
        """
        # Disconnect from the server (this stops the loop)
        self._mqtt.disconnect()

        # Clean up
        self._framework_uid = None
        self._mqtt = None

    def _make_topic(self, suffix):
        """
        Prepares a MQTT topic with the given suffix

        :param suffix: Suffix to the MQTT bridge topic
        :return: A MQTT topic
        """
        return "{0}/{1}".format(self._mqtt_topic, suffix)

    def __on_connect(self, client, result_code):
        """
        Client connected to the server
        """
        if not result_code:
            # Connection is OK, subscribe to the topic
            client.subscribe(self._make_topic("#"))

            # Provide the service
            self._controller = True

    def __on_disconnect(self, client, result_code):
        # pylint: disable=W0613
        """
        Client has been disconnected from the server
        """
        # Disconnected: stop providing the service
        self._controller = False

    def __on_message(self, client, msg):
        # pylint: disable=W0613
        """
        A message has been received from a server

        :param client: Client that received the message
        :param msg: A MQTTMessage bean
        """
        try:
            self.handle_mqtt_message(msg.topic, msg.payload)
        except Exception as ex:
            _logger.exception(
                "Error handling an MQTT EventAdmin message: %s", ex
            )

    def handle_event(self, topic, properties):
        """
        An EventAdmin event has been received
        """
        # Check that the event wasn't sent by us
        if EVENT_PROP_SOURCE_UID in properties:
            # A bridge posted this event, ignore it
            return
        elif services.EVENT_PROP_PROPAGATE not in properties:
            # Propagation flag is not set, ignore
            _logger.warning("No propagate")
            return

        # Remove starting '/' in the event, and set up the flag
        if topic[0] == "/":
            topic = topic[1:]
            properties[EVENT_PROP_STARTING_SLASH] = True

        # Prepare MQTT data
        mqtt_topic = self._make_topic(topic)
        payload = json.dumps(properties)

        # Publish the event to everybody, with QOS 2
        self._mqtt.publish(mqtt_topic, payload, qos=2)

    def handle_mqtt_message(self, mqtt_topic, payload):
        """
        An MQTT message has been received

        :param mqtt_topic: MQTT message topic
        :param payload: Payload of the message
        """
        # +1 to ignore the joining slash (prefix => prefix/)
        evt_topic = mqtt_topic[len(self._mqtt_topic) + 1 :]
        if not evt_topic:
            # Empty EventAdmin topic
            _logger.debug("Empty EventAdmin topic: %s", mqtt_topic)
            return

        try:
            # Ensure that the payload is a string
            payload = to_str(payload)

            # Parse the event payload
            properties = json.loads(payload)
        except ValueError as ex:
            # Oops...
            _logger.error("Error parsing the payload of %s: %s", evt_topic, ex)
            return

        # Check framework UID of the sender
        try:
            sender_uid = to_str(properties[services.EVENT_PROP_FRAMEWORK_UID])
            if sender_uid == self._framework_uid:
                # Loop back
                return

            # Set up source UID as an extra property
            properties[EVENT_PROP_SOURCE_UID] = sender_uid
        except KeyError:
            # Not sent by us... continue
            pass

        # Update the topic if necessary
        if properties.pop(EVENT_PROP_STARTING_SLASH, False):
            # Topic has a starting '/'
            evt_topic = "/{0}".format(evt_topic)

        # Post the event
        self._event.post(evt_topic, properties)
