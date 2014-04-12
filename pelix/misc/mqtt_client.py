#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
MQTT client utility: Tries to hide Paho client details to ease MQTT usage.
Reconnects to the MQTT server automatically.

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
import paho.mqtt.client as paho

# Standard library
import logging
import threading
import uuid

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# Result codes from MQTT
CONNECT_RC = {0: "Success",
              1: "Refused - unacceptable protocol version",
              2: "Refused - identifier rejected",
              3: "Refused - server unavailable",
              4: "Refused - bad user name or password (MQTT v3.1 broker only)",
              5: "Refused - not authorized (MQTT v3.1 broker only)"}

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
        # Reconnection timer
        self.__timer = threading.Timer(5, self.__reconnect)

        # MQTT client
        self.__mqtt = paho.Client(client_id or str(uuid.uuid4()))

        # Paho callbacks
        self.__mqtt.on_connect = self.__on_connect
        self.__mqtt.on_disconnect = self.__on_disconnect
        self.__mqtt.on_message = self.__on_message

        # User callbacks
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None


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
        self.__mqtt.will_set(topic, payload, qos)


    def connect(self, host="localhost", port=1883):
        """
        Connects to the MQTT server. The client will automatically try to
        reconnect to this server when the connection is lost.

        :param host: MQTT server host
        :param port: MQTT server port
        """
        # Prepare the connection
        self.__mqtt.connect_async(host, port)

        # Start the MQTT loop
        self.__mqtt.loop_start()

        # Try to connect the server
        self.__reconnect()


    def disconnect(self):
        """
        Disconnects from the MQTT server
        """
        # Stop the timer
        self.__stop_timer()

        # Disconnect from the server (this stops the loop)
        self.__mqtt.disconnect()


    def publish(self, topic, payload, qos=0, retain=False):
        """
        Sends a message through the MQTT connection

        :param topic: Message topic
        :param payload: Message content
        :param qos: Quality of Service
        :param retain: Retain flag
        :return: The local message ID, None on error
        """
        result = self.__mqtt.publish(topic, payload, qos, retain)
        return result[1]


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
            rc = self.__mqtt.reconnect()
            if rc:
                # Something wrong happened
                _logger.error("Error connecting the MQTT server: %s (%s)",
                              rc, CONNECT_RC[rc])
                raise ValueError("MQTT protocol error: {0}".format(rc))

            else:
                _logger.info("Connection without error")

        except Exception as ex:
            _logger.error("Exception connecting server: %s", ex)

            # Error connecting the server, try again later
            self.__timer = threading.Timer(10, self.__reconnect)
            self.__timer.start()


    def __on_connect(self, client, obj, rc):
        """
        Client connected to the server

        :param client: Connected Paho client
        :parma obj: User data (unused)
        :param rc: Connection result code (0: success, others: error)
        """
        if rc:
            # rc != 0: something wrong happened
            _logger.error("Error connecting the MQTT server: %s",
                          CONNECT_RC[rc])

        else:
            # Connection is OK: stop the reconnection timer
            self.__stop_timer()

        # Notify the caller, if any
        if self.on_connect is not None:
            try:
                self.on_connect(self, rc)

            except Exception as ex:
                _logger.exception("Error notifying MQTT listener: %s", ex)


    def __on_disconnect(self, client, obj, rc):
        """
        Client has been disconnected from the server

        :param client: Client that received the message
        :param obj: *Unused*
        :param rc: Disconnection reason (0: expected, 1: error)
        """
        if rc:
            # rc != 0: unexpected disconnection
            _logger.error("Unexpected disconnection from the MQTT server: %s",
                          rc)

            # Try to reconnect
            self.__stop_timer()
            self.__timer = threading.Timer(2, self.__reconnect)
            self.__timer.start()

        # Notify the caller, if any
        if self.on_disconnect is not None:
            try:
                self.on_disconnect(self, rc)

            except Exception as ex:
                _logger.exception("Error notifying MQTT listener: %s", ex)



    def __on_message(self, client, obj, msg):
        """
        A message has been received from a server

        :param client: Client that received the message
        :param obj: *Unused*
        :param msg: A MQTTMessage bean
        """
        # Notify the caller, if any
        if self.on_message is not None:
            try:
                self.on_message(self, msg)

            except Exception as ex:
                _logger.exception("Error notifying MQTT listener: %s", ex)
