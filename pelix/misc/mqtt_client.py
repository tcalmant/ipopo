#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
MQTT client utility: Tries to hide Paho client details to ease MQTT usage.
Reconnects to the MQTT server automatically.

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

import logging
import os
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import paho.mqtt.client as paho
from paho.mqtt.client import ConnectFlags, DisconnectFlags
from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from pelix.utilities import str2bool

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "DEFAULT_MAX_QUEUED_MESSAGES",
    "PROP_MQTT_CLIENT_ID",
    "PROP_MQTT_HOST",
    "PROP_MQTT_KEEPALIVE",
    "PROP_MQTT_MAX_QUEUED",
    "PROP_MQTT_PASSWORD",
    "PROP_MQTT_PORT",
    "PROP_MQTT_TLS",
    "PROP_MQTT_TLS_CA",
    "PROP_MQTT_TLS_CERT",
    "PROP_MQTT_TLS_KEY",
    "PROP_MQTT_USERNAME",
    "MQTTv5",
    "MQTTv31",
    "MQTTv311",
    "MqttClient",
    "MqttConnectionConfig",
    "MqttMessage",
]

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

# Ensure we export the Paho constants we use in parameters
MqttMessage = paho.MQTTMessage
MQTTv31 = paho.MQTTv31
MQTTv311 = paho.MQTTv311
MQTTv5 = paho.MQTTv5

DEFAULT_MAX_QUEUED_MESSAGES = 1000
""" Default maximum number of QoS 1 and 2 messages waiting to be sent """

PROP_MQTT_HOST = "mqtt.host"
""" Host name of the MQTT broker (``localhost`` by default) """

PROP_MQTT_PORT = "mqtt.port"
""" Port of the MQTT broker (1883 by default, 8883 with TLS) """

PROP_MQTT_KEEPALIVE = "mqtt.keepalive"
""" Maximum period in seconds between two exchanges with the broker (60 by default) """

PROP_MQTT_MAX_QUEUED = "mqtt.max_queued_messages"
""" Maximum number of QoS 1 and 2 messages waiting to be sent, including while disconnected """

PROP_MQTT_CLIENT_ID = "mqtt.client_id"
""" MQTT client ID (a random one by default): it must be unique on the broker """

PROP_MQTT_USERNAME = "mqtt.username"
""" User name to authenticate on the broker """

PROP_MQTT_PASSWORD = "mqtt.password"
""" Password to authenticate on the broker: always declared as a hidden property """

PROP_MQTT_TLS = "mqtt.tls"
""" If true, connect using TLS, implied by the other ``mqtt.tls.*`` properties """

PROP_MQTT_TLS_CA = "mqtt.tls.ca_file"
""" Certificate authorities trusted to verify the broker (the system ones by default) """

PROP_MQTT_TLS_CERT = "mqtt.tls.cert_file"
""" Client certificate file (PEM) """

PROP_MQTT_TLS_KEY = "mqtt.tls.key_file"
""" Private key file (PEM) of the client certificate, if not in the certificate file """


@dataclass(frozen=True, kw_only=True)
class MqttConnectionConfig:
    """
    Configuration of the connection to an MQTT broker, shared by all the MQTT
    components of Pelix.

    The broker certificate and host name are always verified when TLS is used.
    """

    host: str = "localhost"
    port: int | None = None
    keepalive: int = 60
    client_id: str | None = None
    max_queued_messages: int = DEFAULT_MAX_QUEUED_MESSAGES
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    tls: bool = False
    ca_file: str | None = None
    cert_file: str | None = None
    key_file: str | None = None

    @classmethod
    def from_properties(
        cls, properties: Mapping[str, Any], password: str | None = None
    ) -> "MqttConnectionConfig":
        """
        Reads the ``mqtt.*`` entries of the given properties

        :param properties: Component properties
        :param password: Value of the hidden ``mqtt.password`` property
        :return: The connection configuration
        """
        tls = properties.get(PROP_MQTT_TLS) or False
        port = properties.get(PROP_MQTT_PORT)
        return cls(
            host=properties.get(PROP_MQTT_HOST) or "localhost",
            port=int(port) if port else None,
            keepalive=int(properties.get(PROP_MQTT_KEEPALIVE) or 60),
            client_id=properties.get(PROP_MQTT_CLIENT_ID) or None,
            max_queued_messages=int(properties.get(PROP_MQTT_MAX_QUEUED, DEFAULT_MAX_QUEUED_MESSAGES)),
            username=properties.get(PROP_MQTT_USERNAME) or None,
            password=password or None,
            tls=str2bool(tls) if isinstance(tls, str) else bool(tls),
            ca_file=properties.get(PROP_MQTT_TLS_CA) or None,
            cert_file=properties.get(PROP_MQTT_TLS_CERT) or None,
            key_file=properties.get(PROP_MQTT_TLS_KEY) or None,
        )

    @property
    def use_tls(self) -> bool:
        """
        True if the connection uses TLS
        """
        # Giving a TLS file without the flag must not end up in clear text
        return bool(self.tls or self.ca_file or self.cert_file or self.key_file)

    def make_client(self) -> "MqttClient":
        """
        Creates an MQTT client, with credentials and TLS set up

        :return: A disconnected MQTT client
        :raise OSError: A TLS file can't be read
        :raise ssl.SSLError: Invalid TLS file
        """
        client = MqttClient(self.client_id, max_queued_messages=self.max_queued_messages)
        if self.username:
            client.set_credentials(self.username, self.password)

        if self.use_tls:
            # Paho requires the certificate and verifies the host name by default
            client.tls_set(ca_certs=self.ca_file, certfile=self.cert_file, keyfile=self.key_file)

        return client

    def connect(self, client: "MqttClient") -> None:
        """
        Connects the given client to the configured broker, in the background

        :param client: A client made by :meth:`make_client`
        """
        port = self.port or (8883 if self.use_tls else 1883)
        _logger.debug(
            "Connecting to MQTT broker %s:%d (TLS: %s, user: %s)",
            self.host,
            port,
            self.use_tls,
            self.username,
        )
        client.connect(self.host, port, self.keepalive)


class MqttClient:
    """
    Remote Service discovery provider based on MQTT
    """

    def __init__(
        self,
        client_id: str | None = None,
        clean_session: bool = False,
        protocol: int = MQTTv311,
        transport: Literal["tcp", "websockets", "unix"] = "tcp",
        max_queued_messages: int = DEFAULT_MAX_QUEUED_MESSAGES,
    ) -> None:
        """
        :param client_id: ID of the MQTT client
        :param clean_session: If True, the broker will clean the client session on disconnect.
                              Forced to True if no client ID is given.
                              With MQTT v5, the session starts clean on each connection instead.
        :param protocol: MQTT protocol version (MQTTv31, MQTTv311 or MQTTv5)
        :param transport: Transport protocol (tcp or websockets)
        :param max_queued_messages: Maximum number of QoS 1 and 2 messages waiting to be sent,
                                    including while disconnected (0 for no limit)
        """
        # No ID
        if not client_id:
            # Randomize client ID
            self._client_id = self.generate_id()

            # A generated ID is different on each run: the session kept by the
            # broker could never be resumed, it would only pile up there
            # (MQTT 3.1.1 sessions have no expiry), along with the messages
            # queued for it. Only an explicit client ID can make use of it.
            clean_session = True
        elif len(client_id) > 23:
            # ID too large
            _logger.warning(
                "MQTT Client ID '%s' is too long (23 chars max): generating a random one",
                client_id,
            )
            # Keep the client ID as it might be accepted
            self._client_id = client_id
        else:
            # Keep the ID as is
            self._client_id = client_id

        # Subscriptions to renew when the broker forgot them (topic -> QoS)
        self.__subscriptions: dict[str, int] = {}

        # Publications to wait for. Paho tracks their state itself: notifying
        # them from on_publish would need a lock shared with publish(), but Paho
        # calls on_publish while holding the lock publish() needs (dead lock)
        self.__in_flight: dict[int, paho.MQTTMessageInfo] = {}
        self.__in_flight_lock = threading.Lock()

        # Set while disconnected, to stop waiting for publications
        self.__stopped = threading.Event()

        # Assert protocol version
        try:
            protocol_version = MQTTProtocolVersion(protocol)
        except ValueError:
            _logger.error("Unsupported MQTT protocol version")
            raise

        # MQTT client: Paho reconnects it, with a growing delay (1 to 120 s)
        v5 = protocol_version == MQTTProtocolVersion.MQTTv5
        self.__clean_start: paho.CleanStartOption = clean_session if v5 else paho.MQTT_CLEAN_START_FIRST_ONLY
        self.__mqtt = paho.Client(
            CallbackAPIVersion.VERSION2,
            client_id=self._client_id,
            # MQTT v5 has a clean start flag instead, given to connect()
            clean_session=None if v5 else clean_session,
            protocol=protocol_version,
            transport=transport,
            reconnect_on_failure=True,
        )
        self.__mqtt.max_queued_messages_set(max_queued_messages)

        # Give access to Paho methods to configure TLS
        self.tls_set = self.__mqtt.tls_set

        # Paho callbacks
        self.__mqtt.on_connect = self.__on_connect
        self.__mqtt.on_connect_fail = self.__on_connect_fail
        self.__mqtt.on_disconnect = self.__on_disconnect
        self.__mqtt.on_message = self.__on_message
        self.__mqtt.on_publish = self.__on_publish
        self.__mqtt.on_subscribe = self.__on_subscribe
        self.__mqtt.on_unsubscribe = self.__on_unsubscribe

        # Pelix callbacks
        self.__on_connect_cb: Callable[[MqttClient, int], None] | None = None
        self.__on_disconnect_cb: Callable[[MqttClient, int], None] | None = None
        self.__on_subscribe_cb: Callable[[MqttClient, int, list[int]], None] | None = None
        self.__on_unsubscribe_cb: Callable[[MqttClient, int], None] | None = None
        self.__on_message_cb: Callable[[MqttClient, MqttMessage], None] | None = None
        self.__on_publish_cb: Callable[[MqttClient, int], None] | None = None

    @property
    def raw_client(self) -> paho.Client:
        """
        Returns the raw client object, depending on the underlying library
        """
        return self.__mqtt

    @property
    def on_connect(self) -> Callable[["MqttClient", int], None] | None:
        """
        The MQTT connection callback
        """
        return self.__on_connect_cb

    @on_connect.setter
    def on_connect(self, callback: Callable[["MqttClient", int], None] | None) -> None:
        """
        Sets the MQTT connection callback
        """
        self.__on_connect_cb = callback

    @property
    def on_disconnect(self) -> Callable[["MqttClient", int], None] | None:
        """
        The MQTT disconnection callback
        """
        return self.__on_disconnect_cb

    @on_disconnect.setter
    def on_disconnect(self, callback: Callable[["MqttClient", int], None] | None) -> None:
        """
        Sets the MQTT disconnection callback
        """
        self.__on_disconnect_cb = callback

    @property
    def on_subscribe(self) -> Callable[["MqttClient", int, list[int]], None] | None:
        """
        The MQTT connection callback
        """
        return self.__on_subscribe_cb

    @on_subscribe.setter
    def on_subscribe(self, callback: Callable[["MqttClient", int, list[int]], None] | None) -> None:
        """
        Sets the MQTT connection callback
        """
        self.__on_subscribe_cb = callback

    @property
    def on_unsubscribe(self) -> Callable[["MqttClient", int], None] | None:
        """
        The MQTT connection callback
        """
        return self.__on_unsubscribe_cb

    @on_unsubscribe.setter
    def on_unsubscribe(self, callback: Callable[["MqttClient", int], None] | None) -> None:
        """
        Sets the MQTT connection callback
        """
        self.__on_unsubscribe_cb = callback

    @property
    def on_message(self) -> Callable[["MqttClient", MqttMessage], None] | None:
        """
        The MQTT message reception callback
        """
        return self.__on_message_cb

    @on_message.setter
    def on_message(self, callback: Callable[["MqttClient", MqttMessage], None] | None) -> None:
        """
        Sets the MQTT message reception callback
        """
        self.__on_message_cb = callback

    @property
    def on_publish(self) -> Callable[["MqttClient", int], None] | None:
        """
        The MQTT message reception callback
        """
        return self.__on_publish_cb

    @on_publish.setter
    def on_publish(self, callback: Callable[["MqttClient", int], None] | None) -> None:
        """
        Sets the MQTT message reception callback
        """
        self.__on_publish_cb = callback

    @classmethod
    def generate_id(cls, prefix: str | None = "pelix-") -> str:
        """
        Generates a random MQTT client ID

        :param prefix: Client ID prefix (truncated to 8 chars)
        :return: A client ID of 22 or 23 characters
        """
        if not prefix:
            # Normalize string
            prefix = ""
        else:
            # Truncate long prefixes
            prefix = prefix[:8]

        # Prepare the missing part
        nb_bytes = (23 - len(prefix)) // 2

        random_bytes = os.urandom(nb_bytes)
        random_ints = [char for char in random_bytes]

        random_id = "".join(f"{value:02x}" for value in random_ints)
        return f"{prefix}{random_id}"

    @classmethod
    def topic_matches(cls, subscription_filter: str, topic: str) -> bool:
        """
        Checks if the given topic matches the given subscription filter

        :param subscription_filter: A MQTT subscription filter
        :param topic: A topic
        :return: True if the topic matches the filter
        """
        return paho.topic_matches_sub(subscription_filter, topic)

    @property
    def client_id(self) -> str:
        """
        The MQTT client ID
        """
        return self._client_id

    def set_credentials(self, username: str, password: str | None) -> None:
        """
        Sets the user name and password to be authenticated on the server

        :param username: Client username
        :param password: Client password
        """
        self.__mqtt.username_pw_set(username, password)

    def set_will(
        self, topic: str, payload: None | bytes | bytearray | str, qos: int = 0, retain: bool = False
    ) -> None:
        """
        Sets up the will message

        :param topic: Topic of the will message
        :param payload: Content of the message
        :param qos: Quality of Service
        :param retain: The message will be retained
        :raise ValueError: Invalid topic
        :raise TypeError: Invalid payload
        """
        self.__mqtt.will_set(topic, payload, qos, retain=retain)

    def connect(
        self, host: str = "localhost", port: int = 1883, keepalive: int = 60, blocking: bool = False
    ) -> None:
        """
        Connects to the MQTT server. The client will automatically try to
        reconnect to this server when the connection is lost.

        :param host: MQTT server host
        :param port: MQTT server port
        :param keepalive: Maximum period in seconds between communications with the broker
        :param blocking: If True, block until connecting, else be notified with on_connect
        :raise ValueError: Invalid host or port
        """
        # Disconnect first
        self.disconnect()
        self.__stopped.clear()

        # Prepare the connection
        if blocking:
            self.__mqtt.connect(host, port, keepalive, clean_start=self.__clean_start)
        else:
            self.__mqtt.connect_async(host, port, keepalive, clean_start=self.__clean_start)

        # Start the MQTT loop
        self.__mqtt.loop_start()

    def disconnect(self) -> None:
        """
        Disconnects from the MQTT server
        """
        # Unlock all publishers
        self.__stopped.set()

        # Disconnect from the server
        self.__mqtt.disconnect()

        # Stop the MQTT loop thread
        # Use a thread to avoid a dead lock in Paho
        thread = threading.Thread(target=self.__mqtt.loop_stop)
        thread.daemon = True
        thread.start()

        # Give it some time
        thread.join(4)

    def publish(
        self,
        topic: str,
        payload: None | bytes | str,
        qos: int = 0,
        retain: bool = False,
        wait: bool = False,
    ) -> int | None:
        """
        Sends a message through the MQTT connection

        :param topic: Message topic
        :param payload: Message content
        :param qos: Quality of Service
        :param retain: Retain flag
        :param wait: If True, prepares an event to wait for the message to be published
        :return: The local message ID, also when a QoS 1 or 2 message is queued while
                 disconnected (sent on reconnection, see :meth:`wait_publication`),
                 None if the message is refused (QoS 0 while disconnected, full queue)
        """
        result = self.__mqtt.publish(topic, payload, qos, retain)
        if result.rc == paho.MQTT_ERR_NO_CONN and qos > 0:
            # Paho keeps it and sends it once connected again. Paho marks the
            # messages queued for its in-flight limit the same way
            _logger.debug("Not connected: message on %s queued", topic)
            result.rc = paho.MQTT_ERR_SUCCESS
        elif result.rc != paho.MQTT_ERR_SUCCESS:
            _logger.debug("Message on %s refused: %s", topic, paho.error_string(result.rc))
            return None

        if wait:
            with self.__in_flight_lock:
                self.__in_flight[result.mid] = result

        return result.mid

    def wait_publication(self, mid: int, timeout: float | None = None) -> bool:
        """
        Wait for a publication to be validated

        :param mid: Local message ID (result of publish)
        :param timeout: Wait timeout (in seconds)
        :return: True if the message was published, False on timeout or disconnection
        :raise KeyError: Unknown waiting local message ID
        """
        with self.__in_flight_lock:
            info = self.__in_flight[mid]

        deadline = None if timeout is None else time.monotonic() + timeout
        while not info.is_published() and not self.__stopped.is_set():
            # Wait by slices, as the Paho wait can't be interrupted on disconnection
            delay = 0.1 if deadline is None else min(0.1, deadline - time.monotonic())
            if delay <= 0:
                # Publication not sent yet
                return False
            info.wait_for_publish(delay)

        with self.__in_flight_lock:
            self.__in_flight.pop(mid, None)
        return info.is_published()

    def subscribe(self, topic: str, qos: int = 0) -> int | None:
        """
        Subscribes to a topic on the server

        :param topic: Topic filter string(s)
        :param qos: Desired quality of service
        :return: The local message ID, None on error
        :raise ValueError: Invalid topic or QoS
        """
        # Also sent on each new connection: the broker forgets it with a clean session
        self.__subscriptions[topic] = qos
        result = self.__mqtt.subscribe(topic, qos)
        if result is not None:
            return result[1]
        return None

    def unsubscribe(self, topic: str) -> int | None:
        """
        Unscribes from a topic on the server

        :param topic: Topic(s) to unsubscribe from
        :return: The local message ID, None on error
        :raise ValueError: Invalid topic parameter
        """
        self.__subscriptions.pop(topic, None)
        result = self.__mqtt.unsubscribe(topic)
        if result is not None:
            return result[1]
        return None

    def __on_connect_fail(self, client: paho.Client, userdata: Any) -> None:
        """
        Paho failed to connect the server and will try again (called while handling the error)
        """
        _logger.warning("Can't connect to the MQTT server, retrying: %s", sys.exception())

    def __on_connect(
        self,
        client: paho.Client,
        userdata: Any,
        flags: ConnectFlags,
        rc: ReasonCode,
        properties: Properties | None,
    ) -> None:
        """
        Client connected to the server

        :param client: Connected Paho client
        :param userdata: User data (unused)
        :param flags: Response flags sent by the broker
        :param result_code: Connection result code (0: success, others: error)
        """
        if rc.is_failure:
            # result_code != 0: something wrong happened
            _logger.error("Error connecting the MQTT server: %s", rc)
        elif not flags.session_present:
            # New session: renew the subscriptions
            for topic, qos in list(self.__subscriptions.items()):
                client.subscribe(topic, qos)

        # Notify the caller, if any
        if self.__on_connect_cb is not None:
            try:
                self.__on_connect_cb(self, rc.value)
            except Exception:
                _logger.exception("Error executing MQTT connection callback")

    def __on_disconnect(
        self,
        client: paho.Client,
        userdata: Any,
        flags: DisconnectFlags,
        rc: ReasonCode,
        properties: Properties | None,
    ) -> None:
        """
        Client has been disconnected from the server

        :param client: Client that received the message
        :param userdata: User data (unused)
        :param result_code: Disconnection reason (0: expected, 1: error)
        """
        if rc.is_failure:
            # rc != 0: unexpected disconnection, Paho reconnects
            _logger.error("Unexpected disconnection from the MQTT server: %s", rc)

        # Notify the caller, if any
        if self.__on_disconnect_cb is not None:
            try:
                self.__on_disconnect_cb(self, rc.value)
            except Exception:
                _logger.exception("Error executing MQTT disconnection callback")

    def __on_message(self, client: paho.Client, userdata: Any, msg: paho.MQTTMessage) -> None:
        """
        A message has been received from a server

        :param client: Client that received the message
        :param userdata: User data (unused)
        :param msg: A MQTTMessage bean
        """
        # Notify the caller, if any
        if self.__on_message_cb is not None:
            try:
                self.__on_message_cb(self, msg)
            except Exception:
                _logger.exception("Error notifying MQTT message listener")

    def __on_publish(
        self, client: paho.Client, userdata: Any, mid: int, reason_code: ReasonCode, properties: Properties
    ) -> None:
        """
        A message has been published by a server

        :param client: Client that received the message
        :param userdata: User data (unused)
        :param mid: Message ID
        """
        # Notify the explicit callback, if any
        if self.__on_publish_cb is not None:
            try:
                self.__on_publish_cb(self, mid)
            except Exception:
                _logger.exception("Error notifying MQTT publish listener")

    def __on_subscribe(
        self,
        client: paho.Client,
        userdata: Any,
        mid: int,
        reason_code_list: list[ReasonCode],
        properties: Properties,
    ) -> None:
        """
        A subscription has been accepted by the server

        :param client: Client that received the message
        :param userdata: User data (unused)
        :param mid: Message ID
        :param granted_qos: List of granted QoS
        :param reasonCodes: the MQTT v5.0 reason codes received from the broker for each subscribe topic
        :param properties: the MQTT v5.0 properties received from the broker
        """
        # Notify the caller, if any
        if self.__on_subscribe_cb is not None:
            try:
                self.__on_subscribe_cb(self, mid, [r.value for r in reason_code_list])
            except Exception:
                _logger.exception("Error executing MQTT subscribe callback")

    def __on_unsubscribe(
        self,
        client: paho.Client,
        userdata: Any,
        mid: int,
        properties: Properties,
        reasonCodes: ReasonCode | list[ReasonCode],
    ) -> None:
        """
        A subscription has been accepted by the server

        :param client: Client that received the message
        :param userdata: User data (unused)
        :param mid: Message ID
        :param properties: the MQTT v5.0 properties received from the broker
        :param reasonCodes: the MQTT v5.0 reason codes received from the broker for each unsubscribe topic
        """
        # Notify the caller, if any
        if self.__on_unsubscribe_cb is not None:
            try:
                self.__on_unsubscribe_cb(self, mid)
            except Exception:
                _logger.exception("Error executing MQTT unsubscribe callback")
