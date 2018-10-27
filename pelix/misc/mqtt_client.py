#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
MQTT client utility: Tries to hide Paho client details to ease MQTT usage.
Reconnects to the MQTT server automatically.

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
import logging
import os
import sys
import threading

# MQTT client
import paho.mqtt.client as paho

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class MqttClient(object):
    """
    Remote Service discovery provider based on MQTT
    """

    def __init__(self, client_id=None):
        """
        Sets up members

        :param client_id: ID of the MQTT client
        """
        # No ID
        if not client_id:
            # Randomize client ID
            self._client_id = self.generate_id()
        elif len(client_id) > 23:
            # ID too large
            _logger.warning(
                "MQTT Client ID '%s' is too long (23 chars max): "
                "generating a random one",
                client_id,
            )
            # Keep the client ID as it might be accepted
            self._client_id = client_id
        else:
            # Keep the ID as is
            self._client_id = client_id

        # Reconnection timer
        self.__timer = threading.Timer(5, self.__reconnect)

        # Publication events
        self.__in_flight = {}

        # MQTT client
        self.__mqtt = paho.Client(self._client_id)

        # Give access to Paho methods to configure TLS
        self.tls_set = self.__mqtt.tls_set

        # Paho callbacks
        self.__mqtt.on_connect = self.__on_connect
        self.__mqtt.on_disconnect = self.__on_disconnect
        self.__mqtt.on_message = self.__on_message
        self.__mqtt.on_publish = self.__on_publish

    @property
    def raw_client(self):
        """
        Returns the raw client object, depending on the underlying library
        """
        return self.__mqtt

    @staticmethod
    def on_connect(client, result_code):
        """
        User callback: called when the client is connected

        :param client: The Pelix MQTT client which connected
        :param result_code: The MQTT result code
        """
        pass

    @staticmethod
    def on_disconnect(client, result_code):
        """
        User callback: called when the client is disconnected

        :param client: The Pelix MQTT client which disconnected
        :param result_code: The MQTT result code
        """
        pass

    @staticmethod
    def on_message(client, message):
        """
        User callback: called when the client has received a message

        :param client: The Pelix MQTT client which received a message
        :param message: The MQTT message
        """
        pass

    @classmethod
    def generate_id(cls, prefix="pelix-"):
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
        if sys.version_info[0] >= 3:
            random_ints = [char for char in random_bytes]
        else:
            random_ints = [ord(char) for char in random_bytes]

        random_id = "".join("{0:02x}".format(value) for value in random_ints)
        return "{0}{1}".format(prefix, random_id)

    @classmethod
    def topic_matches(cls, subscription_filter, topic):
        """
        Checks if the given topic matches the given subscription filter

        :param subscription_filter: A MQTT subscription filter
        :param topic: A topic
        :return: True if the topic matches the filter
        """
        return paho.topic_matches_sub(subscription_filter, topic)

    @property
    def client_id(self):
        """
        The MQTT client ID
        """
        return self._client_id

    def set_credentials(self, username, password):
        """
        Sets the user name and password to be authenticated on the server

        :param username: Client username
        :param password: Client password
        """
        self.__mqtt.username_pw_set(username, password)

    def set_will(self, topic, payload, qos=0, retain=False):
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

    def connect(self, host="localhost", port=1883, keepalive=60):
        """
        Connects to the MQTT server. The client will automatically try to
        reconnect to this server when the connection is lost.

        :param host: MQTT server host
        :param port: MQTT server port
        :param keepalive: Maximum period in seconds between communications with
                          the broker
        :raise ValueError: Invalid host or port
        """
        # Disconnect first (it also stops the timer)
        self.disconnect()

        # Prepare the connection
        self.__mqtt.connect(host, port, keepalive)

        # Start the MQTT loop
        self.__mqtt.loop_start()

    def disconnect(self):
        """
        Disconnects from the MQTT server
        """
        # Stop the timer
        self.__stop_timer()

        # Unlock all publishers
        for event in self.__in_flight.values():
            event.set()

        # Disconnect from the server
        self.__mqtt.disconnect()

        # Stop the MQTT loop thread
        # Use a thread to avoid a dead lock in Paho
        thread = threading.Thread(target=self.__mqtt.loop_stop)
        thread.daemon = True
        thread.start()

        # Give it some time
        thread.join(4)

    def publish(self, topic, payload, qos=0, retain=False, wait=False):
        """
        Sends a message through the MQTT connection

        :param topic: Message topic
        :param payload: Message content
        :param qos: Quality of Service
        :param retain: Retain flag
        :param wait: If True, prepares an event to wait for the message to be
                     published
        :return: The local message ID, None on error
        """
        result = self.__mqtt.publish(topic, payload, qos, retain)
        if wait and not result[0]:
            # Publish packet sent, wait for it to return
            self.__in_flight[result[1]] = threading.Event()
            _logger.debug("Waiting for publication of %s", topic)

        return result[1]

    def wait_publication(self, mid, timeout=None):
        """
        Wait for a publication to be validated

        :param mid: Local message ID (result of publish)
        :param timeout: Wait timeout (in seconds)
        :return: True if the message was published, False if timeout was raised
        :raise KeyError: Unknown waiting local message ID
        """
        return self.__in_flight[mid].wait(timeout)

    def subscribe(self, topic, qos=0):
        """
        Subscribes to a topic on the server

        :param topic: Topic filter string(s)
        :param qos: Desired quality of service
        :raise ValueError: Invalid topic or QoS
        """
        self.__mqtt.subscribe(topic, qos)

    def unsubscribe(self, topic):
        """
        Unscribes from a topic on the server

        :param topic: Topic(s) to unsubscribe from
        :raise ValueError: Invalid topic parameter
        """
        self.__mqtt.unsubscribe(topic)

    def __start_timer(self, delay):
        """
        Starts the reconnection timer

        :param delay: Delay (in seconds) before calling the reconnection method
        """
        self.__timer = threading.Timer(delay, self.__reconnect)
        self.__timer.daemon = True
        self.__timer.start()

    def __stop_timer(self):
        """
        Stops the reconnection timer, if any
        """
        if self.__timer is not None:
            self.__timer.cancel()
            self.__timer = None

    def __reconnect(self):
        """
        Tries to connect to the MQTT server
        """
        # Cancel the timer, if any
        self.__stop_timer()

        try:
            # Try to reconnect the server
            result_code = self.__mqtt.reconnect()
            if result_code:
                # Something wrong happened
                message = "Error connecting the MQTT server: {0} ({1})".format(
                    result_code, paho.error_string(result_code)
                )
                _logger.error(message)
                raise ValueError(message)
        except Exception as ex:
            # Something went wrong: log it
            _logger.error("Exception connecting server: %s", ex)
        finally:
            # Prepare a reconnection timer. It will be cancelled by the
            # on_connect callback
            self.__start_timer(10)

    def __on_connect(self, client, userdata, flags, result_code):
        # pylint: disable=W0613
        """
        Client connected to the server

        :param client: Connected Paho client
        :param userdata: User data (unused)
        :param flags: Response flags sent by the broker
        :param result_code: Connection result code (0: success, others: error)
        """
        if result_code:
            # result_code != 0: something wrong happened
            _logger.error(
                "Error connecting the MQTT server: %s (%d)",
                paho.connack_string(result_code),
                result_code,
            )
        else:
            # Connection is OK: stop the reconnection timer
            self.__stop_timer()

        # Notify the caller, if any
        if self.on_connect is not None:
            try:
                self.on_connect(self, result_code)
            except Exception as ex:
                _logger.exception("Error notifying MQTT listener: %s", ex)

    def __on_disconnect(self, client, userdata, result_code):
        # pylint: disable=W0613
        """
        Client has been disconnected from the server

        :param client: Client that received the message
        :param userdata: User data (unused)
        :param result_code: Disconnection reason (0: expected, 1: error)
        """
        if result_code:
            # rc != 0: unexpected disconnection
            _logger.error(
                "Unexpected disconnection from the MQTT server: %s (%d)",
                paho.connack_string(result_code),
                result_code,
            )

            # Try to reconnect
            self.__stop_timer()
            self.__start_timer(2)

        # Notify the caller, if any
        if self.on_disconnect is not None:
            try:
                self.on_disconnect(self, result_code)
            except Exception as ex:
                _logger.exception("Error notifying MQTT listener: %s", ex)

    def __on_message(self, client, userdata, msg):
        # pylint: disable=W0613
        """
        A message has been received from a server

        :param client: Client that received the message
        :param userdata: User data (unused)
        :param msg: A MQTTMessage bean
        """
        # Notify the caller, if any
        if self.on_message is not None:
            try:
                self.on_message(self, msg)
            except Exception as ex:
                _logger.exception("Error notifying MQTT listener: %s", ex)

    def __on_publish(self, client, userdata, mid):
        # pylint: disable=W0613
        """
        A message has been published by a server

        :param client: Client that received the message
        :param userdata: User data (unused)
        :param mid: Message ID
        """
        try:
            self.__in_flight[mid].set()
        except KeyError:
            pass
