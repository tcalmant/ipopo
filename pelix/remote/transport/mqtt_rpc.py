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
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.3.0

..

    Copyright 2026 Thomas Calmant

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
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pelix.remote
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo import constants
from pelix.ipopo.decorators import (
    ComponentFactory,
    HiddenProperty,
    Invalidate,
    Property,
    Provides,
    ValidateComponent,
)
from pelix.misc.mqtt_client import PROP_MQTT_PASSWORD, MqttClient, MqttConnectionConfig, MqttMessage
from pelix.remote import RemoteServiceError, security
from pelix.remote.beans import ImportEndpoint
from pelix.remote.transport import commons
from pelix.security import ANONYMOUS, Secret, SecurityError, run_as
from pelix.security.core import restore_subject
from pelix.utilities import to_str

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "KEY_CORRELATION_ID",
    "KEY_DATA",
    "KEY_ERROR",
    "KEY_SENDER",
    "MQTTRPC_CONFIGURATION",
    "PROP_MQTT_PEER_NAME",
    "PROP_MQTT_TOPIC",
    "TOPIC_REQUEST",
    "TOPIC_RESPONSE",
    "TRANSPORT_MQTTRPC",
    "make_topic",
]

# ------------------------------------------------------------------------------

MQTTRPC_CONFIGURATION = "mqttrpc"
""" Remote Service configuration constant """

PROP_MQTT_TOPIC = "mqttrpc.topic"
""" Remote Service property: topic to use to contact the service """

PROP_MQTT_PEER_NAME = "mqttrpc.peer.name"
"""
Exporter property: name of the subject the calls run as, i.e. every broker
client allowed to publish requests. Anonymous if not set.
"""

TRANSPORT_MQTTRPC = "remote.mqttrpc"
""" Transport of the subjects of the MQTT-RPC calls """

_logger = logging.getLogger(__name__)

# Topic suffixes
TOPIC_REQUEST = "request"
TOPIC_RESPONSE = "reply"

# Bounds of the requests handled at once by an exporter: a flood of requests
# must not start an unlimited number of threads
_MAX_THREADS = 10
_MAX_PENDING = 100  # running and queued

# Characters which can't be in a single MQTT topic level
_TOPIC_SPECIAL_CHARS = frozenset("/+#\0")

# JSON dictionary keys
KEY_ERROR = "err"
KEY_DATA = "data"
KEY_CORRELATION_ID = "_correlationId"
KEY_SENDER = pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID

# ------------------------------------------------------------------------------


def make_topic(topic: str, suffix: str) -> str:
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
@Property("_peer_name", PROP_MQTT_PEER_NAME, None)
@HiddenProperty("_mqtt_password", PROP_MQTT_PASSWORD, None)
class MqttRpcServiceExporter(commons.AbstractRpcServiceExporter):
    """
    MQTT-RPC Remote Services exporter
    """

    def __init__(self) -> None:
        """
        Sets up the exporter
        """
        # Call parent
        super().__init__()

        # MQTT topic
        self._topic = ""
        self.__real_topic = ""

        # MQTT broker password (hidden property)
        self._mqtt_password: Secret[str] | None = None

        # Subject of the callers
        self._peer_name: str | None = None

        # MQTT client
        self.__mqtt: MqttClient | None = None
        self.__broker_host: str | None = None

        # Requests handling
        self.__pool: ThreadPoolExecutor | None = None
        self.__pending = threading.BoundedSemaphore(_MAX_PENDING)

    @ValidateComponent(constants.ARG_BUNDLE_CONTEXT, constants.ARG_PROPERTIES)
    def validate(self, context: BundleContext, properties: dict[str, Any] | None = None) -> None:
        """
        Component validated
        """
        # Call the parent
        super().validate(context)

        # Format the topic prefix
        self.__real_topic = self._topic.format(fw_uid=self._framework_uid)

        self.__pool = ThreadPoolExecutor(_MAX_THREADS, thread_name_prefix="MQTT-RPC-Exporter")

        # Create the MQTT client
        config = MqttConnectionConfig.from_properties(properties or {}, self._mqtt_password)
        self.__broker_host = config.host
        self.__mqtt = config.make_client()

        # Customize callbacks
        self.__mqtt.on_connect = self.__on_connect
        self.__mqtt.on_message = self.__on_message

        # Prepare the connection
        config.connect(self.__mqtt)

    @Invalidate
    def invalidate(self, context: BundleContext) -> None:
        """
        Component invalidated
        """
        # Disconnect from the server (this stops the loop)
        if self.__mqtt is not None:
            self.__mqtt.disconnect()

        if self.__pool is not None:
            self.__pool.shutdown(wait=False, cancel_futures=True)

        # Call the parent
        super().invalidate(context)

        # Clean up members
        self.__mqtt = None
        self.__pool = None

    def __on_connect(self, client: MqttClient, result_code: int) -> None:
        """
        Client connected to the server
        """
        if not result_code:
            # Connection is OK, subscribe to the topic
            # Subscribe to endpoints calls
            request_topic_filter = make_topic(self.__real_topic, TOPIC_REQUEST)
            client.subscribe(request_topic_filter)

    def __on_message(self, client: MqttClient, message: MqttMessage) -> None:
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

        sender = data.get(KEY_SENDER) if isinstance(data, dict) else None
        if sender == self._framework_uid:
            # We published this message
            return

        if not sender or not isinstance(sender, str) or not _TOPIC_SPECIAL_CHARS.isdisjoint(sender):
            # The reply topic is made of the sender UID: it must be a single topic level
            _logger.debug("Ignoring an MQTT-RPC request without a valid sender")
            return

        # Each caller has its own reply topic, which the broker can restrict
        reply_topic = make_topic(self.__real_topic, f"{TOPIC_RESPONSE}/{sender}")

        if self.__pool is None or not self.__pending.acquire(blocking=False):
            # Too many requests: tell the caller instead of letting it wait
            _logger.warning("Too many pending MQTT-RPC requests: refusing one from %s", sender)
            self.__reply(reply_topic, data, None, "Server busy")
            return

        try:
            self.__pool.submit(self.__handle_rpc, data, reply_topic)
        except RuntimeError:
            # Pool shut down while invalidating
            self.__pending.release()

    def __reply(self, topic: str, request: dict[str, Any], data: Any, error: str | None) -> None:
        """
        Publishes the reply to a request

        :param topic: Reply topic of the caller
        :param request: The request
        :param data: Result of the call
        :param error: Error message, if any
        """
        result = {
            KEY_ERROR: error,
            KEY_DATA: data,
            KEY_CORRELATION_ID: request.get(KEY_CORRELATION_ID),
            KEY_SENDER: self._framework_uid,
        }

        mqtt = self.__mqtt
        if mqtt is None:
            return

        try:
            mqtt.publish(topic, json.dumps(result), qos=2)
        except (ValueError, TypeError) as ex:
            _logger.error("Error replying an RPC request: %s", ex)

    def __handle_rpc(self, data: dict[str, Any], reply_topic: str) -> None:
        """
        Handles an RPC request (called in a thread of the pool)

        :param data: RPC description
        :param reply_topic: Topic to publish the result to
        """
        result: Any = None
        error: str | None = None
        try:
            # Extract parameters
            try:
                call_info = data[KEY_DATA]
                if not call_info:
                    raise ValueError("No call information given")

                method = call_info[0]
                params = call_info[1:]
            except (KeyError, IndexError, TypeError, ValueError) as ex:
                error = f"Endpoint name is missing: {ex}"
            else:
                # The broker hands no identity: every caller is the configured peer
                subject = (
                    restore_subject(self._peer_name, transport=TRANSPORT_MQTTRPC)
                    if self._peer_name
                    else ANONYMOUS
                )
                try:
                    # Call the service
                    with run_as(subject):
                        result = self.dispatch(method, params)
                except SecurityError as ex:
                    error = security.refusal_message(ex)
                except Exception:
                    # The details describe the server: only the log gets them
                    error_id = uuid.uuid4().hex
                    _logger.exception("Error %s calling %s", error_id, method)
                    error = f"Internal error. Error ID: {error_id}"

            self.__reply(reply_topic, data, result, error)
        finally:
            self.__pending.release()

    def is_local_only(self) -> bool:
        """
        Only the local processes can call when the broker is on a loopback address
        """
        return security.is_loopback_host(self.__broker_host)

    def make_endpoint_properties(
        self, svc_ref: ServiceReference[Any], name: str, fw_uid: str | None
    ) -> dict[str, Any]:
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
    """
    Callable object that makes the real request to the MQTT server
    """

    def __init__(
        self,
        uid: str,
        topic: str,
        method: str,
        publish_method: Callable[[str, Any, str, Iterable[Any] | dict[str, Any]], Any],
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
        self._error: str | None = None
        self._result: Any = None

    def handle_result(self, result: Any, error: str | None) -> None:
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
    """
    Service call proxy
    """

    def __init__(
        self,
        uid: str,
        name: str,
        topic_prefix: str,
        publish_method: Callable[[str, Any, str, Iterable[Any] | dict[str, Any]], Any],
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
        # underlying proxy reuses the same connection when possible: sometimes
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
@HiddenProperty("_mqtt_password", PROP_MQTT_PASSWORD, None)
class MqttRpcServiceImporter(commons.AbstractRpcServiceImporter):
    """
    MQTT-RPC Remote Services importer
    """

    def __init__(self) -> None:
        """
        Sets up the exporter
        """
        # Call parent
        super().__init__()

        # MQTT broker password (hidden property)
        self._mqtt_password: Secret[str] | None = None

        # MQTT client
        self.__mqtt: MqttClient | None = None

        # Proxies waiting for an answer (correlation ID -> _MqttCallableProxy)
        self.__waiting: dict[str, Any] = {}

        # Endpoints in use: Endpoint UID -> _MqttCallableProxy
        self.__waiting_endpoints: dict[str, Any] = {}

        # Timeout of the calls
        self.__timeout: float | None = None

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
        request_parameters: Iterable[Any] | dict[str, Any],
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

        # Subscribe to our own reply topic
        self.__mqtt.subscribe(make_topic(topic_prefix, f"{TOPIC_RESPONSE}/{self._framework_uid}"))

        # Send the request
        self.__mqtt.publish(make_topic(topic_prefix, TOPIC_REQUEST), request, qos=2)

        # Wait here, where the client limits are known: a lost reply must not block forever
        replied = proxy._event.wait(self.__timeout)
        self.__waiting_endpoints.get(endpoint_uid, set()).discard(proxy)
        if not replied:
            self.__waiting.pop(correlation_id, None)
            raise RemoteServiceError("MQTT-RPC call timed out")

    def __on_message(self, client: MqttClient, message: MqttMessage) -> None:
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

    @ValidateComponent(constants.ARG_BUNDLE_CONTEXT, constants.ARG_PROPERTIES)
    def validate(self, context: BundleContext, properties: dict[str, Any] | None = None) -> None:
        """
        Component validated
        """
        # Call the parent
        super().validate(context)
        self.__timeout = commons.get_client_limits(context).timeout

        # Create the MQTT client
        config = MqttConnectionConfig.from_properties(properties or {}, self._mqtt_password)
        self.__mqtt = config.make_client()

        # Customize callbacks
        self.__mqtt.on_message = self.__on_message

        # Prepare the connection
        config.connect(self.__mqtt)

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
        super().invalidate(context)

        # Clean up members
        self.__mqtt = None
