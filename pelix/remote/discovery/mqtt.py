#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: MQTT discovery provider

A discovery packet contains JSON representation of an ImportEndpoint bean.
This module depends on the paho-mqtt package (ex-mosquitto), provided by the
Eclipse Foundation: see http://www.eclipse.org/paho

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 0.1.0
:status: Alpha

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

# ------------------------------------------------------------------------------

# MQTT client
import pelix.misc.mqtt_client

# Pelix & Remote services
import pelix.framework
import pelix.remote
import pelix.remote.beans as beans
from pelix.remote.edef_io import EDEFWriter, EDEFReader

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Provides, \
    Validate, Property, Invalidate

# Standard library
import logging

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# Result codes from MQTT
CONNECT_RC = {0: "Success",
              1: "Refused - unacceptable protocol version",
              2: "Refused - identifier rejected",
              3: "Refused - server unavailable",
              4: "Refused - bad user name or password (MQTT v3.1 broker only)",
              5: "Refused - not authorized (MQTT v3.1 broker only)"}

TOPIC_ADD = "add"
TOPIC_UPDATE = "update"
TOPIC_REMOVE = "remove"
TOPIC_LOST = "lost"
TOPIC_DISCOVER = "discover"

# ------------------------------------------------------------------------------

@ComponentFactory(pelix.remote.FACTORY_DISCOVERY_MQTT)
@Provides(pelix.remote.SERVICE_EXPORT_ENDPOINT_LISTENER, "_controller")
@Requires("_dispatcher", pelix.remote.SERVICE_DISPATCHER)
@Requires("_registry", pelix.remote.SERVICE_REGISTRY)
@Property("_host", "mqtt.host", "localhost")
@Property("_port", "mqtt.port", 1883)
@Property("_prefix", "topic.prefix", "pelix/{appid}/remote-services")
@Property("_appid", "application.id", None)
class MqttDiscovery(object):
    """
    Remote Service discovery provider based on MQTT
    """
    def __init__(self):
        """
        Sets up members
        """
        # Imports registry
        self._registry = None

        # Exports registry
        self._dispatcher = None

        # Service controller
        self._controller = False

        # Framework UID
        self._framework_uid = None

        # MQTT server properties
        self._host = "localhost"
        self._port = 1883

        # MQTT topic Properties
        self._prefix = ""
        self._appid = None

        # MQTT client
        self.__mqtt = None

        # Real prefix
        self._real_prefix = ""


    @Validate
    def _validate(self, context):
        """
        Component validated
        """
        # Format the topic prefix
        self._real_prefix = self._prefix.format(appid=self._appid or "")

        # Avoid double slashes
        self._real_prefix = self._real_prefix.replace("//", "/")

        # Get the framework UID
        self._framework_uid = context.get_property(\
                                                pelix.framework.FRAMEWORK_UID)

        # Create the MQTT client
        client_id = "pelix-discovery-{0}".format(self._framework_uid)
        self.__mqtt = pelix.misc.mqtt_client.MqttClient(client_id)

        # Customize callbacks
        self.__mqtt.on_connect = self.__on_connect
        self.__mqtt.on_disconnect = self.__on_disconnect
        self.__mqtt.on_message = self.__on_message

        # Prepare the will packet
        self.__mqtt.set_will(self._make_topic(TOPIC_LOST),
                             self._framework_uid, qos=2)

        # Prepare the connection
        self.__mqtt.connect(self._host, self._port)


    @Invalidate
    def _invalidate(self, context):
        """
        Component invalidated
        """
        # Disconnect from the server (this stops the loop)
        self.__mqtt.disconnect()

        # Clean up
        self._framework_uid = None
        self.__mqtt = None


    def _make_topic(self, event):
        """
        Prepares a MQTT topic name for the given event

        :param event: An event type (add, update, remove)
        :return: A MQTT topic
        """
        return "{0}/{1}".format(self._real_prefix, event)


    def __on_connect(self, client, rc):
        """
        Client connected to the server
        """
        if not rc:
            # Connection is OK, subscribe to the topic
            client.subscribe(self._make_topic("#"))

            # Provide the service
            self._controller = True
            _logger.info("Connected to the MQTT server")

            # Send a discovery packet
            self.__send_message(self._make_topic(TOPIC_DISCOVER),
                                self._framework_uid)


    def __on_disconnect(self, client, rc):
        """
        Client has been disconnected from the server
        """
        # Disconnected: stop providing the service
        self._controller = False


    def __on_message(self, client, msg):
        """
        A message has been received from a server

        :param client: Client that received the message
        :param msg: A MQTTMessage bean
        """
        try:
            # Get the topic
            topic = msg.topic

            # Extract the event
            event = topic.rsplit("/", 1)[1]

            try:
                getattr(self, "_handle_{0}".format(event))(msg.payload)
            except AttributeError:
                _logger.error("Unhandled MQTT event: %s", event)

        except Exception as ex:
            _logger.exception("Error handling an MQTT message '%s': %s",
                              topic, ex)


    def __send_message(self, topic, payload):
        """
        Sends a message through the MQTT connection

        :param topic: Message topic
        :param payload: Message content
        """
        # Publish the MQTT message (QoS 2 - Exactly Once)
        self.__mqtt.publish(topic, payload, qos=2)


    def _handle_add(self, payload):
        """
        A set of endpoints have been registered

        :param payload: An EDEF XML
        """
        # Parse the endpoints
        endpoints_descr = EDEFReader().parse(payload)
        endpoints = [endpoint.to_import() for endpoint in endpoints_descr]

        # Notify the import registry
        for endpoint in endpoints:
            self._registry.add(endpoint)


    def _handle_update(self, payload):
        """
        A set of endpoints have been updated

        :param payload: An EDEF XML
        """
        # Parse the endpoints
        endpoints_descr = EDEFReader().parse(payload)
        endpoints = [endpoint.to_import() for endpoint in endpoints_descr]

        # Notify the import registry
        for endpoint in endpoints:
            self._registry.update(endpoint.uid, endpoint.properties)


    def _handle_remove(self, payload):
        """
        An endpoint has been removed

        :param payload: The UID of the endpoint
        """
        # Endpoint removed
        self._registry.remove(payload)


    def _handle_discover(self, payload):
        """
        A framework wants to discover all services

        :param payload: The UID of the sender
        """
        if payload == self._framework_uid:
            # We are the sender, ignore this message
            return

        # Get the list of our exported services
        endpoints = self._dispatcher.get_endpoints()
        if not endpoints:
            # Nothing to say
            return

        # Convert the beans to XML (EDEF format)
        xml_string = EDEFWriter().to_string(
                                beans.EndpointDescription.from_export(endpoint)
                                for endpoint in endpoints)

        # Send the message
        self.__send_message(self._make_topic(TOPIC_ADD), xml_string)


    def _handle_lost(self, payload):
        """
        A framework has been lost

        :param payload: The UID of the lost framework
        """
        self._registry.lost_framework(payload)


    def endpoints_added(self, endpoints):
        """
        Multiple endpoints have been added

        :param endpoint: A list of ExportEndpoint beans
        """
        # Convert the beans to XML (EDEF format)
        xml_string = EDEFWriter().to_string(
                                beans.EndpointDescription.from_export(endpoint)
                                for endpoint in endpoints)

        # Send the message
        self.__send_message(self._make_topic(TOPIC_ADD), xml_string)


    def endpoint_updated(self, endpoint, old_properties):
        """
        An end point is updated
        """
        # Convert the endpoint into an EndpointDescription bean
        endpoint_desc = beans.EndpointDescription.from_export(endpoint)

        # Convert the bean to XML (EDEF format)
        xml_string = EDEFWriter().to_string([endpoint_desc])

        # Send the message
        self.__send_message(self._make_topic(TOPIC_UPDATE), xml_string)


    def endpoint_removed(self, endpoint):
        """
        An end point is removed
        """
        # Only send the UID here
        self.__send_message(self._make_topic(TOPIC_REMOVE), endpoint.uid)
