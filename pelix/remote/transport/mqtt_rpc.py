#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: MQTT pseudo RPC

An remote service protocol based on MQTT.
This implementation tries to mimic the MQTT-RPC Javascript project:
https://github.com/wolfeidau/mqtt-rpc

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

import json
import logging
import threading
import uuid
from typing import Any, Callable, Dict, Iterable, Optional, Union

import pelix.remote
import pelix.remote.transport.commons as commons
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Validate
from pelix.misc.mqtt_client import MqttClient, MqttMessage
from pelix.remote import RemoteServiceError
from pelix.remote.beans import ImportEndpoint
from pelix.utilities import to_str

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

MQTTRPC_CONFIGURATION = "mqttrpc"
""" Remote Service configuration constant """

PROP_MQTT_TOPIC = "mqttrpc.topic"
""" Remote Service property: topic to use to contact the service """

_logger = logging.getLogger(__name__)

# Topic suffixes
TOPIC_REQUEST = "request"
TOPIC_RESPONSE = "reply"

# JSON dictionary keys
KEY_ERROR = "err"
KEY_DATA = "data"
KEY_CORRELATION_ID = "_correlationId"
KEY_SENDER = pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID

# ------------------------------------------------------------------------------


def make_topic(topic: str, suffix: str) -> str:
    # pylint: disable=W0613
    """
    Prepares a topic with the given suffix

    :param topic: MQTT topic
    :param suffix: String to append to the topic
    :return: The suffixed topic
    """
    return f"{topic}/{suffix}".replace("//", "/")


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_MQTTRPC_EXPORTER)
@Provides(pelix.remote.RemoteServiceExportProvider)
@Property("_topic", PROP_MQTT_TOPIC, "pelix/remote-services/mqttrpc/{fw_uid}")
@Property(
    "_kinds",
    pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
    (MQTTRPC_CONFIGURATION,),
)
@Property("_host", "mqtt.host", "localhost")
@Property("_port", "mqtt.port", 1883)
class MqttRpcServiceExporter(commons.AbstractRpcServiceExporter):
    """
    MQTT-RPC Remote Services exporter
    """

    def __init__(self) -> None:
        """
        Sets up the exporter
        """
        # Call parent
        super(MqttRpcServiceExporter, self).__init__()

        # MQTT topic
        self._topic = ""
        self.__real_topic = ""

        # Topic to reply to requests
        self.__reply_topic = ""

        # MQTT server
        self._host = ""
        self._port = 0

        # MQTT client
        self.__mqtt: Optional[MqttClient] = None

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        # Call the parent
        super(MqttRpcServiceExporter, self).validate(context)

        # Format the topic prefix
        self.__real_topic = self._topic.format(fw_uid=self._framework_uid)

        # Normalize topic
        self.__reply_topic = make_topic(self.__real_topic, TOPIC_RESPONSE)

        # Create the MQTT client
        self.__mqtt = MqttClient()

        # Customize callbacks
        self.__mqtt.on_connect = self.__on_connect
        self.__mqtt.on_message = self.__on_message

        # Prepare the connection
        self.__mqtt.connect(self._host, self._port)

    @Invalidate
    def invalidate(self, context: BundleContext) -> None:
        """
        Component invalidated
        """
        # Disconnect from the server (this stops the loop)
        if self.__mqtt is not None:
            self.__mqtt.disconnect()

        # Call the parent
        super(MqttRpcServiceExporter, self).invalidate(context)

        # Clean up members
        self.__mqtt = None

    def __on_connect(self, client: MqttClient, result_code: int) -> None:
        # pylint: disable=W0613
        """
        Client connected to the server
        """
        if not result_code:
            # Connection is OK, subscribe to the topic
            # Subscribe to endpoints calls
            request_topic_filter = make_topic(self.__real_topic, TOPIC_REQUEST)
            client.subscribe(request_topic_filter)

    def __on_message(self, client: MqttClient, message: MqttMessage) -> None:
        # pylint: disable=W0613
        """
        An MQTT message has been received

        :param client: MQTT client
        :param message: A MQTTMessage bean
        """
        try:
            # Parse the message
            data = json.loads(to_str(message.payload))
        except ValueError as ex:
            # Bad content
            _logger.error("Error reading MQTT-RPC request: %s", ex)
            return

        try:
            if data[KEY_SENDER] == self._framework_uid:
                # We published this message
                return
        except KeyError:
            # Not sent by us
            pass

        # Handle the request in a different thread
        threading.Thread(name="MQTT-RPC-Exporter", target=self.__handle_rpc, args=(data,)).start()

    def __handle_rpc(self, data: Dict[str, Any]) -> None:
        """
        Handles an RPC request (should be called in a specific thread)

        :param data: RPC description
        """
        assert self.__mqtt is not None

        # Prepare the result dictionary
        result = {
            KEY_ERROR: None,
            KEY_DATA: None,
            KEY_CORRELATION_ID: data.get(KEY_CORRELATION_ID),
            KEY_SENDER: self._framework_uid,
        }

        # Extract parameters
        try:
            call_info = data[KEY_DATA]
            if not call_info:
                raise ValueError("No call information given")

            method = call_info[0]
            params = call_info[1:]
        except (KeyError, IndexError, ValueError) as ex:
            result[KEY_ERROR] = f"Endpoint name is missing: {ex}"
        else:
            try:
                # Call the service
                result[KEY_DATA] = self.dispatch(method, params)
            except Exception as ex:
                # An error occurred
                result[KEY_ERROR] = str(ex)

        try:
            # Publish the result
            self.__mqtt.publish(self.__reply_topic, json.dumps(result), qos=2)
        except (ValueError, AttributeError) as ex:
            _logger.error("Error replying an RPC request: %s", ex)

    def make_endpoint_properties(
        self, svc_ref: ServiceReference[Any], name: str, fw_uid: Optional[str]
    ) -> Dict[str, Any]:
        """
        Prepare properties for the ExportEndpoint to be created

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: A dictionary of extra endpoint properties
        """
        return {PROP_MQTT_TOPIC: self.__real_topic}


# ------------------------------------------------------------------------------


class _MqttCallableProxy:
    # pylint: disable=R0903
    """
    Callable object that makes the real request to the MQTT server
    """

    def __init__(
        self,
        uid: str,
        topic: str,
        method: str,
        publish_method: Callable[[str, Any, str, Union[Iterable[Any], Dict[str, Any]]], Any],
    ) -> None:
        """
        Stores parameters

        :param uid: Endpoint UID
        :param topic: Endpoint topic
        :param method: Name of the method to call
        :param publish_method: Method to call to publish the request message
        """
        # Local information
        self.__uid = uid
        self.__topic = topic
        self.__method_name = method
        self.__publish = publish_method

        # Event to wait for the result
        self._event = threading.Event()

        # Result
        self._error: Optional[str] = None
        self._result: Any = None

    def handle_result(self, result: Any, error: Optional[str]) -> None:
        """
        The result has been received

        :param result: Call result
        :param error: Error message
        """
        if not self._error and not self._result:
            # Store results, if not already set
            self._error = error
            self._result = result

        # Unlock the call
        self._event.set()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Method call
        """
        # Send a request
        request = [self.__method_name]
        if args:
            request.extend(args)

        # Keyword arguments are ignores
        self.__publish(self.__uid, self, self.__topic, request)

        # Wait for an answer
        self._event.wait()

        # Act accordingly
        if self._error:
            raise RemoteServiceError(self._error)
        else:
            return self._result


class _ServiceCallProxy:
    # pylint: disable=R0903
    """
    Service call proxy
    """

    def __init__(
        self,
        uid: str,
        name: str,
        topic_prefix: str,
        publish_method: Callable[[str, Any, str, Union[Iterable[Any], Dict[str, Any]]], Any],
    ) -> None:
        """
        Sets up the call proxy

        :param uid: End point UID
        :param name: End point name
        :param topic_prefix: Prefix for MQTT topics
        :param publish_method: Method to call to publish the request message
        """
        self.__uid = uid
        self.__name = name
        self.__topic_prefix = topic_prefix
        self.__publish = publish_method

    def __getattr__(self, name: str) -> Any:
        """
        Prefixes the requested attribute name by the endpoint name
        """
        # Make a proxy for this call
        # This is an ugly trick to handle multi-threaded calls, as the
        # underlying proxy re-uses the same connection when possible: sometimes
        # it means sending a request before retrieving a result
        return _MqttCallableProxy(
            self.__uid,
            self.__topic_prefix,
            f"{self.__name}.{name}",
            self.__publish,
        )


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_MQTTRPC_IMPORTER)
@Provides(pelix.remote.RemoteServiceImportEndpointListener)
@Property(
    "_kinds",
    pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
    (MQTTRPC_CONFIGURATION,),
)
@Property("_host", "mqtt.host", "localhost")
@Property("_port", "mqtt.port", 1883)
class MqttRpcServiceImporter(commons.AbstractRpcServiceImporter):
    """
    MQTT-RPC Remote Services importer
    """

    def __init__(self) -> None:
        """
        Sets up the exporter
        """
        # Call parent
        super(MqttRpcServiceImporter, self).__init__()

        # MQTT server
        self._host = ""
        self._port = 0

        # MQTT client
        self.__mqtt: Optional[MqttClient] = None

        # Proxies waiting for an answer (correlation ID -> _MqttCallableProxy)
        self.__waiting: Dict[str, Any] = {}

        # Endpoints in use: Endpoint UID -> _MqttCallableProxy
        self.__waiting_endpoints: Dict[str, Any] = {}

    def make_service_proxy(self, endpoint: ImportEndpoint) -> Any:
        """
        Creates the proxy for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        :return: A service proxy
        """
        # Get the request topic
        topic_prefix = endpoint.properties.get(PROP_MQTT_TOPIC)
        if not topic_prefix:
            # No topic information
            _logger.warning("No MQTT topic given: %s", endpoint)
            return None

        if not endpoint.name:
            _logger.warning("Endpoint doesn't have a name: %s", endpoint)
            return None

        return _ServiceCallProxy(endpoint.uid, endpoint.name, topic_prefix, self.__send_request)

    def clear_service_proxy(self, endpoint: ImportEndpoint) -> None:
        """
        Destroys the proxy made for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        """
        try:
            # Free waiting calls
            for proxy in self.__waiting_endpoints.pop(endpoint.uid):
                proxy.handle_result(None, "Endpoint removed")
        except KeyError:
            # Unused endpoint
            return

    def __send_request(
        self,
        endpoint_uid: str,
        proxy: Any,
        topic_prefix: str,
        request_parameters: Union[Iterable[Any], Dict[str, Any]],
    ) -> None:
        """
        Sends a request to the given topic

        :param endpoint_uid: Endpoint UID
        :param proxy: Callable proxy to notify on response
        :param topic_prefix: Prefix of MQTT topics to use
        :param request_parameters: Call parameters
        """
        assert self.__mqtt is not None

        # Prepare the correlation ID
        correlation_id = str(uuid.uuid4())

        try:
            # Prepare the data
            request = json.dumps(
                {
                    KEY_DATA: request_parameters,
                    KEY_CORRELATION_ID: correlation_id,
                    KEY_SENDER: self._framework_uid,
                }
            )
        except ValueError as ex:
            raise RemoteServiceError(f"Cannot convert request to JSON: {ex}")

        # Keep the callable in the waiting list
        self.__waiting[correlation_id] = proxy
        self.__waiting_endpoints.setdefault(endpoint_uid, set()).add(proxy)

        # Subscribe to the reply
        self.__mqtt.subscribe(make_topic(topic_prefix, TOPIC_RESPONSE))

        # Send the request
        self.__mqtt.publish(make_topic(topic_prefix, TOPIC_REQUEST), request, qos=2)

    def __on_message(self, client: MqttClient, message: MqttMessage) -> None:
        # pylint: disable=W0613
        """
        An MQTT reply has been received
        """
        try:
            # Parse data
            data = json.loads(to_str(message.payload))

            # Check if we are the sender
            try:
                if data[KEY_SENDER] == self._framework_uid:
                    # We published this message
                    return
            except KeyError:
                # Not sent by us
                pass

            # Extract the correlation ID
            correlation_id = data[KEY_CORRELATION_ID]
        except ValueError as ex:
            # Unreadable reply
            _logger.error("Error reading MQTT-RPC reply: %s", ex)
            return
        except KeyError as ex:
            # No correlation ID
            _logger.error("Incomplete MQTT-RPC reply: missing %s", ex)
            return

        try:
            # Extract result
            result = data[KEY_DATA]
            error = data[KEY_ERROR]
        except KeyError as ex:
            # Incomplete result
            result = None
            error = f"Missing MQTT-RPC reply field: {ex}"

        try:
            # Find the matching proxy
            proxy = self.__waiting.pop(correlation_id)
        except KeyError:
            # No a correlation ID we know
            pass
        else:
            # Notify the proxy
            proxy.handle_result(result, error)

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        # Call the parent
        super(MqttRpcServiceImporter, self).validate(context)

        # Create the MQTT client
        self.__mqtt = MqttClient()

        # Customize callbacks
        self.__mqtt.on_message = self.__on_message

        # Prepare the connection
        self.__mqtt.connect(self._host, self._port)

    @Invalidate
    def invalidate(self, context: BundleContext) -> None:
        """
        Component invalidated
        """
        # Disconnect from the server (this stops the loop)
        if self.__mqtt is not None:
            self.__mqtt.disconnect()

        # Unlock proxies
        for proxy in self.__waiting.values():
            proxy.handle_result(None, "MQTT-RPC Importer stopped")

        # Clean up the storage
        self.__waiting.clear()

        # Call the parent
        super(MqttRpcServiceImporter, self).invalidate(context)

        # Clean up members
        self.__mqtt = None
