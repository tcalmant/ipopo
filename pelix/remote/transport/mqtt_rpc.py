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
import threading
import uuid

# MQTT client
import pelix.misc.mqtt_client

# iPOPO decorators
from pelix.ipopo.decorators import (
    ComponentFactory,
    Property,
    Provides,
    Validate,
    Invalidate,
)

# Pelix & Remote services
from pelix.utilities import to_str
from pelix.remote import RemoteServiceError
import pelix.remote
import pelix.remote.transport.commons as commons

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
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


def make_topic(topic, suffix):
    # pylint: disable=W0613
    """
    Prepares a topic with the given suffix

    :param topic: MQTT topic
    :param suffix: String to append to the topic
    :return: The suffixed topic
    """
    return "{0}/{1}".format(topic, TOPIC_REQUEST).replace("//", "/")


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_MQTTRPC_EXPORTER)
@Provides(pelix.remote.SERVICE_EXPORT_PROVIDER)
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

    def __init__(self):
        """
        Sets up the exporter
        """
        # Call parent
        super(MqttRpcServiceExporter, self).__init__()

        # Handled configurations
        self._kinds = None

        # MQTT topic
        self._topic = ""
        self.__real_topic = ""

        # Topic to reply to requests
        self.__reply_topic = ""

        # MQTT server
        self._host = None
        self._port = None

        # MQTT client
        self.__mqtt = None

    @Validate
    def validate(self, context):
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
        self.__mqtt = pelix.misc.mqtt_client.MqttClient()

        # Customize callbacks
        self.__mqtt.on_connect = self.__on_connect
        self.__mqtt.on_message = self.__on_message

        # Prepare the connection
        self.__mqtt.connect(self._host, self._port)

    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        """
        # Disconnect from the server (this stops the loop)
        self.__mqtt.disconnect()

        # Call the parent
        super(MqttRpcServiceExporter, self).invalidate(context)

        # Clean up members
        self.__mqtt = None

    def __on_connect(self, client, result_code):
        # pylint: disable=W0613
        """
        Client connected to the server
        """
        if not result_code:
            # Connection is OK, subscribe to the topic
            # Subscribe to endpoints calls
            request_topic_filter = make_topic(self.__real_topic, TOPIC_REQUEST)
            self.__mqtt.subscribe(request_topic_filter)

    def __on_message(self, client, msg):
        # pylint: disable=W0613
        """
        An MQTT message has been received

        :param client: MQTT client
        :param msg: A MQTTMessage bean
        """
        try:
            # Parse the message
            data = json.loads(to_str(msg.payload))
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
        threading.Thread(
            name="MQTT-RPC-Exporter", target=self.__handle_rpc, args=(data,)
        ).start()

    def __handle_rpc(self, data):
        """
        Handles an RPC request (should be called in a specific thread)

        :param data: RPC description
        """
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
            result[KEY_ERROR] = "Endpoint name is missing: {0}".format(ex)
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

    def make_endpoint_properties(self, svc_ref, name, fw_uid):
        """
        Prepare properties for the ExportEndpoint to be created

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: A dictionary of extra endpoint properties
        """
        return {PROP_MQTT_TOPIC: self.__real_topic}


# ------------------------------------------------------------------------------


class _MqttCallableProxy(object):
    # pylint: disable=R0903
    """
    Callable object that makes the real request to the MQTT server
    """

    def __init__(self, uid, topic, method, publish_method):
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
        self._error = None
        self._result = None

    def handle_result(self, result, error):
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

    def __call__(self, *args, **kwargs):
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


class _ServiceCallProxy(object):
    # pylint: disable=R0903
    """
    Service call proxy
    """

    def __init__(self, uid, name, topic_prefix, publish_method):
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

    def __getattr__(self, name):
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
            "{0}.{1}".format(self.__name, name),
            self.__publish,
        )


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_MQTTRPC_IMPORTER)
@Provides(pelix.remote.SERVICE_IMPORT_ENDPOINT_LISTENER)
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

    def __init__(self):
        """
        Sets up the exporter
        """
        # Call parent
        super(MqttRpcServiceImporter, self).__init__()

        # Component properties
        self._kinds = None

        # MQTT server
        self._host = None
        self._port = None

        # MQTT client
        self.__mqtt = None

        # Proxies waiting for an answer (correlation ID -> _MqttCallableProxy)
        self.__waiting = {}

        # Endpoints in use: Endpoint UID -> _MqttCallableProxy
        self.__waiting_endpoints = {}

    def make_service_proxy(self, endpoint):
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

        return _ServiceCallProxy(
            endpoint.uid, endpoint.name, topic_prefix, self.__send_request
        )

    def clear_service_proxy(self, endpoint):
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
        self, endpoint_uid, proxy, topic_prefix, request_parameters
    ):
        """
        Sends a request to the given topic

        :param endpoint_uid: Endpoint UID
        :param proxy: Callable proxy to notify on response
        :param topic_prefix: Prefix of MQTT topics to use
        :param request_parameters: Call parameters
        """
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
            raise RemoteServiceError(
                "Cannot convert request to JSON: {0}".format(ex)
            )

        # Keep the callable in the waiting list
        self.__waiting[correlation_id] = proxy
        self.__waiting_endpoints.setdefault(endpoint_uid, set()).add(proxy)

        # Subscribe to the reply
        self.__mqtt.subscribe(make_topic(topic_prefix, TOPIC_RESPONSE))

        # Send the request
        self.__mqtt.publish(
            make_topic(topic_prefix, TOPIC_REQUEST), request, qos=2
        )

    def __on_message(self, client, msg):
        # pylint: disable=W0613
        """
        An MQTT reply has been received
        """
        try:
            # Parse data
            data = json.loads(to_str(msg.payload))

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
            error = "Missing MQTT-RPC reply field: {0}".format(ex)

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
    def validate(self, context):
        """
        Component validated
        """
        # Call the parent
        super(MqttRpcServiceImporter, self).validate(context)

        # Create the MQTT client
        self.__mqtt = pelix.misc.mqtt_client.MqttClient()

        # Customize callbacks
        self.__mqtt.on_message = self.__on_message

        # Prepare the connection
        self.__mqtt.connect(self._host, self._port)

    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        """
        # Disconnect from the server (this stops the loop)
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
