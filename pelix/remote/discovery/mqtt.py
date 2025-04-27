#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: MQTT discovery provider

A discovery packet contains JSON representation of an ImportEndpoint bean.
This module depends on the paho-mqtt package (ex-mosquitto), provided by the
Eclipse Foundation: see http://www.eclipse.org/paho

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2025 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import logging
from typing import Any, Dict, Iterable, List, Optional

import pelix.constants as constants
import pelix.remote
import pelix.remote.beans as beans
from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Requires, Validate
from pelix.misc.mqtt_client import MqttClient, MqttMessage
from pelix.remote.edef_io import EDEFReader, EDEFWriter
from pelix.utilities import to_bytes, to_str

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

EVENT_ADD = "add"
EVENT_UPDATE = "update"
EVENT_REMOVE = "remove"
EVENT_LOST = "lost"
EVENT_DISCOVER = "discover"

ENDPOINT_EVENTS = (EVENT_ADD, EVENT_UPDATE, EVENT_REMOVE)

# ------------------------------------------------------------------------------


@ComponentFactory(pelix.remote.FACTORY_DISCOVERY_MQTT)
@Provides(pelix.remote.RemoteServiceExportEndpointListener, "_controller")
@Requires("_dispatcher", pelix.remote.RemoteServiceDispatcher)
@Requires("_registry", pelix.remote.RemoteServiceRegistry)
@Property("_host", "mqtt.host", "localhost")
@Property("_port", "mqtt.port", 1883)
@Property("_prefix", "topic.prefix", "pelix/{appid}/remote-services")
@Property("_appid", "application.id", None)
class MqttDiscovery(pelix.remote.RemoteServiceExportEndpointListener):
    """
    Remote Service discovery provider based on MQTT
    """

    # Imports registry
    _dispatcher: pelix.remote.RemoteServiceDispatcher
    # Exports registry
    _registry: pelix.remote.RemoteServiceRegistry

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Service controller
        self._controller = False

        # Framework UID
        self._framework_uid: str = ""

        # MQTT server properties
        self._host = "localhost"
        self._port = 1883

        # MQTT topic Properties
        self._prefix = ""
        self._appid: Optional[str] = None

        # MQTT client
        self.__mqtt: Optional[MqttClient] = None

        # Real prefix
        self._real_prefix = ""

    @Validate
    def _validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        # Format the topic prefix
        self._real_prefix = self._prefix.format(appid=self._appid or "")

        # Avoid double slashes
        self._real_prefix = self._real_prefix.replace("//", "/")

        # Get the framework UID
        self._framework_uid = context.get_property(constants.FRAMEWORK_UID)
        if not self._framework_uid:
            raise ValueError(f"A Framework UID must be set with property {constants.FRAMEWORK_UID}")

        # Create the MQTT client
        self.__mqtt = MqttClient()

        # Customize callbacks
        self.__mqtt.on_connect = self.__on_connect
        self.__mqtt.on_disconnect = self.__on_disconnect
        self.__mqtt.on_message = self.__on_message

        # Prepare the will packet
        self.__mqtt.set_will(self._make_topic(EVENT_LOST), to_bytes(self._framework_uid), qos=2)

        # Prepare the connection
        self.__mqtt.connect(self._host, self._port)

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        """
        Component invalidated
        """
        if self.__mqtt is not None:
            # Send the "lost" message
            mid = self.__send_message(EVENT_LOST, self._framework_uid, True)
            if mid is not None:
                self.__mqtt.wait_publication(mid, 10)
            # Disconnect from the server (this stops the loop)
            self.__mqtt.disconnect()

        # Clean up
        self.__mqtt = None

    def _make_topic(self, event: str) -> str:
        """
        Prepares a MQTT topic name for the given event

        :param event: An event type (add, update, remove) or a filter
        :return: A MQTT topic
        """
        return f"{self._real_prefix}/{event}"

    def __on_connect(self, client: MqttClient, result_code: int) -> None:
        """
        Client connected to the server
        """
        if not result_code:
            # Connection is OK, subscribe to the topic
            client.subscribe(self._make_topic("#"))

            # Provide the service
            self._controller = True

            # Send a discovery packet
            self.__send_message(EVENT_DISCOVER, self._framework_uid)

    def __on_disconnect(self, client: MqttClient, result_code: int) -> None:
        # pylint: disable=W0613
        """
        Client has been disconnected from the server
        """
        # Disconnected: stop providing the service
        self._controller = False

    def __on_message(self, client: MqttClient, message: MqttMessage) -> None:
        # pylint: disable=W0613
        """
        A message has been received from a server

        :param client: Client that received the message
        :param message: A MQTTMessage bean
        """
        # Get the topic
        topic = message.topic

        # Extract the event
        event = topic.rsplit("/", 1)[1]

        try:
            parameter: Any
            if event in ENDPOINT_EVENTS:
                # Parse the endpoints (from EDEF XML to ImportEndpoint)
                endpoints_descr = EDEFReader().parse(message.payload)
                endpoints = [endpoint.to_import() for endpoint in endpoints_descr]

                if not endpoints or endpoints[0].framework == self._framework_uid:
                    # No enpoints to read or Loopback message
                    return

                # Give the list of endpoints to the handler
                parameter = endpoints
            else:
                # Give the payload as is to other event handlers
                parameter = message.payload

            try:
                getattr(self, f"_handle_{event}")(parameter)
            except AttributeError:
                _logger.error("Unhandled MQTT event: %s", event)

        except Exception as ex:
            _logger.exception("Error handling an MQTT message '%s': %s", topic, ex)

    def __send_message(self, event: str, payload: Any, wait: bool = False) -> Optional[int]:
        """
        Sends a message through the MQTT connection

        :param event: Remote service event name
        :param payload: Message content
        :return: The local message ID
        """
        assert self.__mqtt is not None

        # Publish the MQTT message (QoS 2 - Exactly Once)
        return self.__mqtt.publish(self._make_topic(event), payload, qos=2, wait=wait)

    def _handle_add(self, endpoints: Iterable[beans.ImportEndpoint]) -> None:
        """
        A set of endpoints have been registered

        :param endpoints: Parsed ImportEndpoint beans
        """
        # Notify the import registry
        for endpoint in endpoints:
            self._registry.add(endpoint)

    def _handle_update(self, endpoints: Iterable[beans.ImportEndpoint]) -> None:
        """
        A set of endpoints have been updated

        :param endpoints: Parsed ImportEndpoint beans
        """
        # Notify the import registry
        for endpoint in endpoints:
            self._registry.update(endpoint.uid, endpoint.properties)

    def _handle_remove(self, endpoints: Iterable[beans.ImportEndpoint]) -> None:
        """
        A set of endpoints has been removed

        :param endpoints: Parsed ImportEndpoint beans
        """
        # Notify the import registry
        for endpoint in endpoints:
            self._registry.remove(endpoint.uid)

    def _handle_discover(self, payload: bytes) -> None:
        """
        A framework wants to discover all services

        :param payload: The UID of the sender
        """
        if to_str(payload) == self._framework_uid:
            # We are the sender, ignore this message
            return

        # Get the list of our exported services
        endpoints = self._dispatcher.get_endpoints()
        if not endpoints:
            # Nothing to say
            return

        # Convert the beans to XML (EDEF format)
        xml_string = EDEFWriter().to_string(
            beans.EndpointDescription.from_export(endpoint) for endpoint in endpoints
        )

        # Send the message
        self.__send_message(EVENT_ADD, xml_string)

    def _handle_lost(self, payload: bytes) -> None:
        """
        A framework has been lost

        :param payload: The UID of the lost framework
        """
        self._registry.lost_framework(to_str(payload))

    def endpoints_added(self, endpoints: List[beans.ExportEndpoint]) -> None:
        """
        Multiple endpoints have been added

        :param endpoints: A list of ExportEndpoint beans
        """
        # Convert the beans to XML (EDEF format)
        xml_string = EDEFWriter().to_string(
            beans.EndpointDescription.from_export(endpoint) for endpoint in endpoints
        )

        # Send the message
        self.__send_message(EVENT_ADD, xml_string)

    def endpoint_updated(
        self, endpoint: beans.ExportEndpoint, old_properties: Optional[Dict[str, Any]]
    ) -> None:
        # pylint: disable=W0613
        """
        An end point is updated

        :param endpoint: The updated endpoint
        :param old_properties: Previous properties of the endpoint
        """
        # Convert the endpoint into an EndpointDescription bean
        endpoint_desc = beans.EndpointDescription.from_export(endpoint)

        # Convert the bean to XML (EDEF format)
        xml_string = EDEFWriter().to_string([endpoint_desc])

        # Send the message
        self.__send_message(EVENT_UPDATE, xml_string)

    def endpoint_removed(self, endpoint: beans.ExportEndpoint) -> None:
        """
        An end point is removed

        :param endpoint: Endpoint being removed
        """
        # Convert the endpoint into an EndpointDescription bean
        endpoint_desc = beans.EndpointDescription.from_export(endpoint)

        # Convert the bean to XML (EDEF format)
        xml_string = EDEFWriter().to_string([endpoint_desc])

        # Send the message
        self.__send_message(EVENT_REMOVE, xml_string)
