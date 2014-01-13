#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
A bridge to publish and subscribe to EventAdmin events over the network using
MQTT

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 0.1
:status: Beta

..

    Copyright 2014 isandlaTech

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

# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

#-------------------------------------------------------------------------------

# Pelix
from pelix.ipopo.decorators import ComponentFactory, Provides, Property, \
    Validate, Invalidate, Requires, Instantiate
from pelix.utilities import to_str
import pelix.constants as constants
import pelix.services as services

# Standard library
import json
import logging

#-------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

DEFAULT_MQTT_TOPIC = 'pelix/eventadmin'
""" Default MQTT topic to use to propagate events """

EVENT_PROP_SOURCE_UID = 'pelix.eventadmin.mqtt.source'
""" UID of the framework that sent the event """

EVENT_PROP_STARTING_SLASH = 'pelix.eventadmin.mqtt.start_slash'
""" Flag to indicate that the EventAdmin topic starts with a '/' """

#-------------------------------------------------------------------------------

@ComponentFactory(services.FACTORY_EVENT_ADMIN_MQTT)
@Provides((services.SERVICE_MQTT_LISTENER,
           services.SERVICE_EVENT_HANDLER))
@Requires('_event', services.SERVICE_EVENT_ADMIN)
@Requires('_mqtt', services.SERVICE_MQTT_CONNECTOR_FACTORY)
@Property('_mqtt_topic', 'mqtt.bridge.topic', DEFAULT_MQTT_TOPIC)
@Property('_event_topics', services.PROP_EVENT_TOPICS, '*')
@Property('_mqtt_topics', services.PROP_MQTT_TOPICS)
@Instantiate('pelix-eventadmin-mqtt')
class MqttEventAdminBridge(object):
    """
    The EventAdmin MQTT bridge
    """
    def __init__(self):
        """
        Sets up the members
        """
        # Component configuration: MQTT topic prefix
        self._mqtt_topic = None

        # Topics service properties
        self._mqtt_topics = None
        self._event_topics = None

        # EventAdmin
        self._event = None

        # MQTT Connection factory
        self._mqtt = None

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

        if self._mqtt_topic[-1] != '/':
            # End the topic with a '/'
            self._mqtt_topic += '/'

        # Setup the MQTT topics filter
        self._mqtt_topics = [self._mqtt_topic + '#']


    @Invalidate
    def _invalidate(self, context):
        """
        Component invalidated
        """
        self._framework_uid = None
        self._mqtt_topics = None


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
            return


        # Remove starting '/' in the event, and set up the flag
        if topic[0] == '/':
            topic = topic[1:]
            properties[EVENT_PROP_STARTING_SLASH] = True

        # Prepare MQTT data
        mqtt_topic = '{0}{1}'.format(self._mqtt_topic, topic)
        payload = json.dumps(properties)

        # Publish the event to everybody, with default QOS
        self._mqtt.publish(mqtt_topic, payload)


    def handle_mqtt_message(self, mqtt_topic, payload, qos):
        """
        An MQTT message has been received
        """
        # Compute the EventAdmin topic
        if not mqtt_topic.startswith(self._mqtt_topic):
            # Not a valid EventAdmin topic
            _logger.debug("Ignoring MQTT topic: %s", mqtt_topic)
            return

        evt_topic = mqtt_topic[len(self._mqtt_topic):]
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
            # Oups...
            _logger.error("Error parsing the payload of %s: %s", evt_topic, ex)
            return

        # Check framework UID of the sender
        try:
            sender_uid = to_str(properties[services.EVENT_PROP_FRAMEWORK_UID])
            if sender_uid == self._framework_uid:
                # Loop back
                return

        except KeyError:
            # Not sent by us... continue
            pass

        # Update the topic if necessary
        if properties.pop(EVENT_PROP_STARTING_SLASH, False):
            # Topic has a starting '/'
            evt_topic = '/{0}'.format(evt_topic)

        # Set up source UID as an extra property
        properties[EVENT_PROP_SOURCE_UID] = sender_uid

        # Post the event
        self._event.post(evt_topic, properties)
