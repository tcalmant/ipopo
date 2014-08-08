#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
MQTT Connection service: Connects to servers described by configurations and
notifies topic listeners.

Requires Paho MQTT client (paho-mqtt).

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 0.5.7
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
__version_info__ = (0, 5, 7)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# MQTT client
import paho.mqtt.client as paho

# Pelix
from pelix.ipopo.decorators import ComponentFactory, Provides, Requires, \
    Validate, Invalidate, Instantiate, BindField, UnbindField, UpdateField, \
    Property
from pelix.utilities import to_iterable
import pelix.constants as constants
import pelix.services as services
import pelix.threadpool

# Standard library
import logging
import threading
import uuid

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

CONNECT_RC = {0: "Success",
              1: "Refused - unacceptable protocol version",
              2: "Refused - identifier rejected",
              3: "Refused - server unavailable",
              4: "Refused - bad user name or password (MQTT v3.1 broker only)",
              5: "Refused - not authorized (MQTT v3.1 broker only)"}

# ------------------------------------------------------------------------------


@ComponentFactory()
@Provides((services.SERVICE_MQTT_CONNECTOR_FACTORY,
           services.SERVICE_CONFIGADMIN_MANAGED_FACTORY))
@Property('_pid', constants.SERVICE_PID, services.MQTT_CONNECTOR_FACTORY_PID)
@Requires('_listeners', services.SERVICE_MQTT_LISTENER,
          aggregate=True, optional=True)
@Instantiate('mqtt-connection-factory')
class MqttConnectionFactory(object):
    """
    Handles connections to MQTT servers
    """
    def __init__(self):
        """
        Sets up members
        """
        # ConfigAdmin PID
        self._pid = None

        # Injected topic listeners
        self._listeners = []

        # Topics to subscribe to (topic -> nb_references)
        self._topics = {}

        # Bundle context
        self._context = None

        # Client ID
        self.__client_id = str(uuid.uuid4())

        # Active connections (PID -> connection)
        self._clients = {}

        # Registered service (PID -> service registration)
        self._services = {}

        # Client loop thread
        self._thread = None
        self.__lock = threading.RLock()
        self.__stop_event = threading.Event()

        # Notification pool
        self._pool = None

    @Validate
    def _validate(self, context):
        """
        Component validated
        """
        self._context = context

        # Start the notification pool
        self._pool = pelix.threadpool.ThreadPool(2,
                                                 "mqtt-notifications")
        self._pool.start()

        # Start the loop thread
        self.__stop_event.clear()
        self._thread = threading.Thread(target=self.__clients_loop,
                                        name="mqtt-clients-loop")
        self._thread.daemon = True
        self._thread.start()

        _logger.info("MQTT factory validated")

    @Invalidate
    def _invalidate(self, context):
        """
        Component invalidated
        """
        # Stop the loop thread
        self.__stop_event.set()

        # Stop the pool
        self._pool.stop()

        # Wait for the thread to stop
        self._thread.join()

        with self.__lock:
            # Unregister all services
            for reg in self._services.values():
                try:
                    reg.unregister()
                except:
                    # Ignore errors
                    pass

            # Disconnect from all servers
            for client in self._clients.values():
                client.disconnect()

            # Clean up
            self._clients.clear()
            self._services.clear()
            self._pool = None
            self._context = None

        _logger.info("MQTT factory invalidated")

    def __add_listener(self, topic, listener):
        """
        Adds a topic listener
        """
        try:
            # Get current listeners
            listeners = self._topics[topic]

        except KeyError:
            # New topic: subscribe to it
            listeners = self._topics[topic] = set()
            self.__subscribe(topic)

        # Store the listener
        listeners.add(listener)

    def __remove_listener(self, topic, listener):
        """
        Removes a topic listener
        """
        try:
            listeners = self._topics[topic]
            listeners.remove(listener)
            if not listeners:
                # No more reference to the topic, unsubscribe
                del self._topics[topic]
                self.__unsubscribe(topic)

        except KeyError:
            # Unused topic or listener not registered for it
            pass

    @BindField('_listeners')
    def _bind_listener(self, field, listener, svc_ref):
        """
        A new MQTT listener has been bound
        """
        topics = to_iterable(svc_ref.get_property(services.PROP_MQTT_TOPICS),
                             False)
        for topic in topics:
            self.__add_listener(topic, listener)

    @UpdateField('_listeners')
    def _update_listener(self, field, listener, svc_ref, old_props):
        """
        A listener has been updated
        """
        old_topics = set(old_props[services.PROP_MQTT_TOPICS])
        topics = set(to_iterable(
            svc_ref.get_property(services.PROP_MQTT_TOPICS), False))

        # New topics
        for topic in topics.difference(old_topics):
            self.__add_listener(topic, listener)

        # Removed old ones
        for topic in old_topics.difference(topics):
            self.__remove_listener(topic, listener)

    @UnbindField('_listeners')
    def _unbind_listener(self, field, listener, svc_ref):
        """
        An MQTT listener is gone
        """
        topics = to_iterable(svc_ref.get_property(services.PROP_MQTT_TOPICS),
                             False)
        for topic in topics:
            self.__remove_listener(topic, listener)

    def __clients_loop(self):
        """
        Control loop to let each client check its messages
        """
        while not self.__stop_event.wait(.1) \
                and not self.__stop_event.is_set():
            # Copy clients using the lock
            with self.__lock:
                clients = list(self._clients.items())

            # Loop upon them
            for pid, client in clients:
                rc = client.loop(0)
                if rc != 0:
                    # Reconnect on error
                    # FIXME: do a better job
                    _logger.warning("Loop error for client %s, "
                                    "reconnecting it", pid)
                    client.reconnect()

    def __on_message(self, client, obj, msg):
        """
        A message has been received from a server

        :param client: Client that received the message
        :param obj: *Unused*
        :param msg: A Message bean
        """
        try:
            # Get the topic
            topic = msg.topic

            # Get all listeners matching this topic
            all_listeners = set()
            for subscription, listeners in self._topics.items():
                if paho.topic_matches_sub(subscription, topic):
                    all_listeners.update(listeners)

            # Notify them using the pool
            self._pool.enqueue(self.__notify_listeners, all_listeners,
                               topic, msg.payload, msg.qos)

        except KeyError:
            # No listener for this topic
            pass

    def __notify_listeners(self, listeners, topic, payload, qos):
        """
        Notifies listeners of an MQTT message
        """
        for listener in listeners:
            try:
                listener.handle_mqtt_message(topic, payload, qos)

            except Exception as ex:
                _logger.exception("Error calling MQTT listener: %s", ex)

    def __subscribe(self, topic):
        """
        Subscribes to a topic in all servers
        """
        for client in self._clients.values():
            client.subscribe(topic, 0)

    def __unsubscribe(self, topic):
        """
        Unsubscribes from the topic from all servers
        """
        for client in self._clients.values():
            client.unsubscribe(topic)

    def updated(self, pid, properties):
        """
        Configuration updated

        :param pid: Configuration PID
        :param properties: Configuration properties
        """
        with self.__lock:
            if pid in self._clients:
                # Server is already known, ignore
                # TODO: reconnect to the server
                _logger.debug("Reconfiguration not yet handled")
                return

            # Extract properties
            host = properties['host']
            port = properties.get('port', 1883)
            keepalive = properties.get('keepalive', 60)

            # Connect to the server
            client = paho.Client(self.__client_id)
            rc = client.connect(host, port, keepalive)
            if rc == 0:
                # Success !
                _logger.debug("Connected to [%s]:%s (%s) - %s",
                              host, port, client, pid)

                # Customize callbacks
                client.on_message = self.__on_message

                # Store PID -> Client
                self._clients[pid] = client

                # Subscribe to topics
                # TODO: handle the QOS
                for topic in self._topics:
                    client.subscribe(topic, 0)

                # Register an mqtt.connection service
                svc = _MqttConnection(self, client)
                props = {'id': pid, 'host': host, 'port': port}
                svc_reg = self._context.register_service(
                    services.SERVICE_MQTT_CONNECTION, svc, props)

                # Store PID -> ServiceRegistration
                self._services[pid] = svc_reg

            else:
                # Can't connect to the server
                _logger.error("Error connecting to the MQTT server: %d - %s",
                              rc, CONNECT_RC.get(rc, "Unknown error"))

    def deleted(self, pid):
        """
        Configuration deleted

        :param pid: PID of the deleted configuration
        """
        with self.__lock:
            try:
                # Pop from storage
                client = self._clients.pop(pid)
                reg = self._services.pop(pid)

            except KeyError:
                # Not found...
                _logger.error("Unknown connection ID: %s", pid)

            else:
                # Unregister mqtt.connection service
                reg.unregister()

                # Disconnect from server
                client.disconnect()
                _logger.debug("Disconnected from %s", client)

    def publish(self, topic, payload, qos=0, retain=False, pid=None):
        """
        Publishes an MQTT message

        :raise KeyError: Invalid PID
        """
        if pid:
            # Targeted server
            # TODO: check for success
            self._clients[pid].publish(topic, payload, qos, retain)

        else:
            for client in self._clients.values():
                # TODO: check for success of at least one publication
                client.publish(topic, payload, qos, retain)

# ------------------------------------------------------------------------------


class _MqttConnection(object):
    """
    Represents a connection to an MQTT server
    """
    def __init__(self, factory, connection):
        """
        Sets up members

        :param factory: The parent MqttConnectionFactory object
        :param connection: A Paho Client object
        """
        self.__factory = factory
        self._client = connection

    def publish(self, topic, payload, qos=0, retain=False):
        """
        Publishes an MQTT message
        """
        # TODO: check (full transmission) success
        self._client.publish(topic, payload, qos, retain)
