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
from pelix.utilities import to_str
from pelix.remote import RemoteServiceError
import pelix.constants as constants
import pelix.remote

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Property, Provides, \
    Validate, Invalidate

# Standard library
import json
import logging
import threading
import uuid

# ------------------------------------------------------------------------------

MQTTRPC_CONFIGURATION = 'mqttrpc'
""" Remote Service configuration constant """

PROP_MQTT_TOPIC = 'mqttrpc.topic'
""" Remote Service property: topic to use to contact the service """

_logger = logging.getLogger(__name__)

# Topic suffixes
TOPIC_REQUEST = "request"
TOPIC_RESPONSE = "reply"

# JSON dictionary keys
KEY_ERROR = 'err'
KEY_DATA = 'data'
KEY_CORRELATION_ID = '_correlationId'
KEY_SENDER = pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID

# ------------------------------------------------------------------------------

def make_topic(topic, suffix):
    """
    Prepares a topic with the given suffix

    :param topic: MQTT topic
    :param suffix: String to append to the topic
    :return: The suffixed topic
    """
    return "{0}/{1}".format(topic, TOPIC_REQUEST).replace("//", "/")


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_MQTTRPC_EXPORTER)
@Provides(pelix.remote.SERVICE_EXPORT_PROVIDER)
@Property('_topic', PROP_MQTT_TOPIC, "pelix/remote-services/mqttrpc/{fw_uid}")
@Property('_kinds', pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
          (MQTTRPC_CONFIGURATION,))
@Property("_host", "mqtt.host", "localhost")
@Property("_port", "mqtt.port", 1883)
class MqttRpcServiceExporter(object):
    """
    MQTT-RPC Remote Services exporter
    """
    def __init__(self):
        """
        Sets up the exporter
        """
        # Bundle context
        self._context = None

        # Framework UID
        self._framework_uid = None

        # Handled configurations
        self._kinds = None

        # MQTT topic
        self._topic = None
        self.__real_topic = None

        # MQTT server
        self._host = None
        self._port = None

        # MQTT client
        self.__mqtt = None

        # Exported services: Name -> ExportEndpoint
        self.__endpoints = {}


    @Validate
    def _validate(self, context):
        """
        Component validated
        """
        # Store the context
        self._context = context

        # Get the framework UID
        self._framework_uid = context.get_property(constants.FRAMEWORK_UID)

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
    def _invalidate(self, context):
        """
        Component invalidated
        """
        # Disconnect from the server (this stops the loop)
        self.__mqtt.disconnect()

        # Clean up the storage
        self.__endpoints.clear()

        # Clean up members
        self._context = None
        self._framework_uid = None
        self.__mqtt = None


    def _dispatch(self, method, params):
        """
        Called by the servlet: calls the method of an exported service
        """
        # Get the best matching name
        matching = None
        len_found = 0
        for name in self.__endpoints:
            if len(name) > len_found and method.startswith(name + "."):
                # Better matching end point name (longer that previous one)
                matching = name
                len_found = len(matching)

        if matching is None:
            # No end point name match
            raise KeyError("No end point found for: {0}".format(method))

        # Extract the method name. (+1 for the trailing dot)
        method_name = method[len_found + 1:]

        # Get the service
        try:
            service = self.__endpoints[matching].instance
        except KeyError:
            raise RemoteServiceError("Unknown endpoint: {0}".format(matching))

        # Get the method
        method_ref = getattr(service, method_name, None)
        if method_ref is None:
            raise RemoteServiceError("Unknown method {0}".format(method))

        # Call it (let the errors be propagated)
        return method_ref(*params)


    def __on_connect(self, client, rc):
        """
        Client connected to the server
        """
        if not rc:
            # Connection is OK, subscribe to the topic
            # Subscribe to endpoints calls
            request_topic_filter = make_topic(self.__real_topic, TOPIC_REQUEST)
            self.__mqtt.subscribe(request_topic_filter)


    def __on_message(self, client, msg):
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

        try:
            if data[KEY_SENDER] == self._framework_uid:
                # We published this message
                return
        except KeyError:
            # Not sent by us
            pass

        # Handle the request in a different thread
        threading.Thread(name="MQTT-RPC-Exporter",
                         target=self.__handle_rpc, args=(data,)).start()


    def __handle_rpc(self, data):
        """
        Handles an RPC request (should be called in a specific thread)

        :param data: RPC description
        """
        # Prepare the result dictionary
        result = {KEY_ERROR: None,
                  KEY_DATA: None,
                  KEY_CORRELATION_ID: data.get(KEY_CORRELATION_ID),
                  KEY_SENDER: self._framework_uid}

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
                result[KEY_DATA] = self._dispatch(method, params)

            except Exception as ex:
                # An error occurred
                result[KEY_ERROR] = str(ex)

        try:
            # Publish the result
            self.__mqtt.publish(self.__reply_topic, json.dumps(result),
                                qos=2)

        except (ValueError, AttributeError) as ex:
            _logger.error("Error replying an RPC request: %s", ex)


    def handles(self, configurations):
        """
        Checks if this provider handles the given configuration types

        :param configurations: Configuration types
        """
        if configurations is None or configurations == '*':
            # 'Matches all'
            return True

        return bool(set(configurations).intersection(self._kinds))


    def export_service(self, svc_ref, name, fw_uid):
        """
        Prepares an export endpoint

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: An ExportEndpoint bean
        :raise NameError: Already known name
        :raise BundleException: Error getting the service
        """
        if name in self.__endpoints:
            # Already known end point
            raise NameError("Already known end point {0} for JSON-RPC" \
                            .format(name))

        # Get the service (let it raise a BundleException if any
        service = self._context.get_service(svc_ref)

        # Prepare extra properties
        properties = {PROP_MQTT_TOPIC: self.__real_topic}

        # Prepare the export endpoint
        try:
            endpoint = pelix.remote.beans.ExportEndpoint(str(uuid.uuid4()),
                                                         fw_uid, self._kinds,
                                                         name, svc_ref, service,
                                                         properties)
        except ValueError:
            # No specification to export (specifications filtered, ...)
            return None

        # Store information
        self.__endpoints[name] = endpoint

        # Return the endpoint bean
        return endpoint


    def update_export(self, endpoint, new_name, old_properties):
        """
        Updates an export endpoint

        :param endpoint: An ExportEndpoint bean
        :param new_name: Future endpoint name
        :param old_properties: Previous properties
        :raise NameError: Rename refused
        """
        try:
            if self.__endpoints[new_name] is not endpoint:
                # Reject the new name, as an endpoint uses it
                raise NameError("New name of {0} already used: {1}" \
                                .format(endpoint.name, new_name))

            else:
                # Name hasn't changed
                pass

        except KeyError:
            # No endpoint matches the new name: update the storage
            self.__endpoints[new_name] = self.__endpoints.pop(endpoint.name)

            # Update the endpoint
            endpoint.name = new_name


    def unexport_service(self, endpoint):
        """
        Deletes an export endpoint

        :param endpoint: An ExportEndpoint bean
        """
        # Clean up storage
        del self.__endpoints[endpoint.name]

        # Release the service
        svc_ref = endpoint.reference
        self._context.unget_service(svc_ref)

# ------------------------------------------------------------------------------

class _MqttCallableProxy(object):
    """
    Callable object that makes the real request to the MQTT server
    """
    def __init__(self, topic, method, publish_method):
        """
        Stores parameters

        :param topic: Endpoint topic
        :param method: Name of the method to call
        :param publish_method: Method to call to publish the request message
        """
        # Local information
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
        # Store results
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
        self.__publish(self, self.__topic, request)

        # Wait for an answer
        self._event.wait()
        self._event = None

        # Act accordingly
        if self._error:
            raise RemoteServiceError(self._error)

        else:
            return self._result


class _ServiceCallProxy(object):
    """
    Service call proxy
    """
    def __init__(self, name, topic_prefix, publish_method):
        """
        Sets up the call proxy

        :param name: End point name
        :param topic_prefix: Prefix for MQTT topics
        :param publish_method: Method to call to publish the request message
        """
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
        return _MqttCallableProxy(self.__topic_prefix,
                                  "{0}.{1}".format(self.__name, name),
                                  self.__publish)


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_MQTTRPC_IMPORTER)
@Provides(pelix.remote.SERVICE_IMPORT_ENDPOINT_LISTENER)
@Property('_kinds', pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
          (MQTTRPC_CONFIGURATION,))
@Property("_host", "mqtt.host", "localhost")
@Property("_port", "mqtt.port", 1883)
class MqttRpcServiceImporter(object):
    """
    MQTT-RPC Remote Services importer
    """
    def __init__(self):
        """
        Sets up the exporter
        """
        # Bundle context
        self._context = None

        # Framework UID
        self._framework_uid = None

        # Component properties
        self._kinds = None

        # MQTT server
        self._host = None
        self._port = None

        # MQTT client
        self.__mqtt = None

        # Proxies waiting for an answer (correlation ID -> _MqttCallableProxy)
        self.__waiting = {}

        # Registered services (endpoint UID -> ServiceReference)
        self.__registrations = {}


    def endpoint_added(self, endpoint):
        """
        An end point has been imported
        """
        configs = set(endpoint.configurations)
        if '*' not in configs and not configs.intersection(self._kinds):
            # Not for us
            return

        # Get the request topic
        topic_prefix = endpoint.properties.get(PROP_MQTT_TOPIC)
        if not topic_prefix:
            # No topic information
            _logger.warning("No MQTT topic given: %s", endpoint)
            return

        # Register the service
        svc = _ServiceCallProxy(endpoint.name, topic_prefix,
                                self.__send_request)
        svc_reg = self._context.register_service(endpoint.specifications, svc,
                                                 endpoint.properties)

        # Store references
        self.__registrations[endpoint.uid] = svc_reg


    def endpoint_updated(self, endpoint, old_properties):
        """
        An end point has been updated
        """
        try:
            # Update service registration properties
            self.__registrations[endpoint.uid].set_properties(
                                                          endpoint.properties)

        except KeyError:
            # Unknown end point
            return


    def endpoint_removed(self, endpoint):
        """
        An end point has been removed
        """
        try:
            # Pop reference and unregister the service
            self.__registrations.pop(endpoint.uid).unregister()

        except KeyError:
            # Unknown end point
            return


    def __send_request(self, proxy, topic_prefix, request_parameters):
        """
        Sends a request to the given topic
        """
        # Prepare the correlation ID
        correlation_id = str(uuid.uuid4())

        try:
            # Prepare the data
            request = json.dumps({KEY_DATA: request_parameters,
                                  KEY_CORRELATION_ID: correlation_id,
                                  KEY_SENDER: self._framework_uid})

        except ValueError as ex:
            raise RemoteServiceError("Cannot convert request to JSON: {0}" \
                                     .format(ex))

        # Keep the callable in the waiting list
        self.__waiting[correlation_id] = proxy

        # Subscribe to the reply
        self.__mqtt.subscribe(make_topic(topic_prefix, TOPIC_RESPONSE))

        # Send the request
        self.__mqtt.publish(make_topic(topic_prefix, TOPIC_REQUEST), request,
                            qos=2)


    def __on_message(self, client, msg):
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

        except KeyError as ex:
            # No correlation ID
            _logger.error("Incomplete MQTT-RPC reply: missing %s", ex)

        try:
            # Extract result
            result = data[KEY_DATA]
            error = data[KEY_ERROR]

        except KeyError as ex:
            # Incomplete result
            result = None
            error = "Missing MQTT-RPC reply field: {0}".format(ex)

        # Notify the matching proxy
        self.__waiting.pop(correlation_id).handle_result(result, error)


    @Validate
    def _validate(self, context):
        """
        Component validated
        """
        # Store the bundle context
        self._context = context

        # Get the framework UID
        self._framework_uid = context.get_property(constants.FRAMEWORK_UID)

        # Create the MQTT client
        self.__mqtt = pelix.misc.mqtt_client.MqttClient()

        # Customize callbacks
        self.__mqtt.on_message = self.__on_message

        # Prepare the connection
        self.__mqtt.connect(self._host, self._port)


    @Invalidate
    def _invalidate(self, context):
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

        # Clean up members
        self._context = None
        self._framework_uid = None
        self.__mqtt = None
