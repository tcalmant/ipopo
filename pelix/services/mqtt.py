#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
MQTT Connection service: Connects to servers described by configurations and
notifies topic listeners.

Requires Paho MQTT client (paho-mqtt).

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
import threading
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Set, cast

import paho.mqtt.client as paho
from paho.mqtt.client import ConnectFlags, DisconnectFlags
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

import pelix.constants as constants
import pelix.services as services
import pelix.threadpool
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    Requires,
    UnbindField,
    UpdateField,
    Validate,
)
from pelix.utilities import to_iterable

if TYPE_CHECKING:
    from pelix.framework import BundleContext
    from pelix.internals.registry import ServiceReference, ServiceRegistration

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

CONNECT_RC = {
    0: "Success",
    1: "Refused - unacceptable protocol version",
    2: "Refused - identifier rejected",
    3: "Refused - server unavailable",
    4: "Refused - bad user name or password (MQTT v3.1 broker only)",
    5: "Refused - not authorized (MQTT v3.1 broker only)",
}

# ------------------------------------------------------------------------------


@ComponentFactory()
@Provides(
    (
        services.MqttConnectorFactory,
        services.IManagedServiceFactory,
    )
)
@Property("_pid", constants.SERVICE_PID, services.MQTT_CONNECTOR_FACTORY_PID)
@Requires("_listeners", services.SERVICE_MQTT_LISTENER, aggregate=True, optional=True)
@Instantiate("mqtt-connection-factory")
class MqttConnectionFactory(services.MqttConnectorFactory):
    """
    Handles connections to MQTT servers
    """

    # Listeners (injected)
    _listeners: List[services.MqttListener]

    def __init__(self) -> None:
        """
        Sets up members
        """
        # ConfigAdmin PID
        self._pid: Optional[str] = None

        # Topics to subscribe to (topic -> nb_references)
        self._topics: Dict[str, Set[services.MqttListener]] = {}

        # Bundle context
        self._context: Optional[BundleContext] = None

        # Active connections (PID -> connection)
        self._clients: Dict[str, paho.Client] = {}

        # Registered service (PID -> service registration)
        self._services: Dict[str, ServiceRegistration[Any]] = {}

        # Client loop thread
        self._thread: Optional[threading.Thread] = None
        self.__lock = threading.RLock()
        self.__stop_event = threading.Event()

        # Notification pool
        self._pool: Optional[pelix.threadpool.ThreadPool] = None

    @Validate
    def _validate(self, context: "BundleContext") -> None:
        """
        Component validated
        """
        self._context = context

        # Start the notification pool
        self._pool = pelix.threadpool.ThreadPool(2, logname="mqtt-notifications")
        self._pool.start()

        # Start the loop thread
        self.__stop_event.clear()
        self._thread = threading.Thread(target=self.__clients_loop, name="mqtt-clients-loop")
        self._thread.daemon = True
        self._thread.start()

        _logger.info("MQTT factory validated")

    @Invalidate
    def _invalidate(self, _: "BundleContext") -> None:
        """
        Component invalidated
        """
        # Stop the loop thread
        self.__stop_event.set()

        # Stop the pool
        if self._pool is not None:
            self._pool.stop()
            self._pool = None

        # Wait for the thread to stop
        if self._thread is not None:
            self._thread.join()
            self._thread = None

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

    def __add_listener(self, topic: str, listener: services.MqttListener) -> None:
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

    def __remove_listener(self, topic: str, listener: services.MqttListener) -> None:
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

    @BindField("_listeners")
    def _bind_listener(
        self, field: str, listener: services.MqttListener, svc_ref: "ServiceReference[services.MqttListener]"
    ) -> None:
        """
        A new MQTT listener has been bound
        """
        topics = cast(Iterable[str], to_iterable(svc_ref.get_property(services.PROP_MQTT_TOPICS), False))
        for topic in topics:
            self.__add_listener(topic, listener)

    @UpdateField("_listeners")
    def _update_listener(
        self,
        field: str,
        listener: services.MqttListener,
        svc_ref: "ServiceReference[services.MqttListener]",
        old_props: Optional[Dict[str, Any]],
    ) -> None:
        """
        A listener has been updated
        """
        old_topics = set(old_props[services.PROP_MQTT_TOPICS] if old_props else [])
        topics = set(cast(Iterable[str], to_iterable(svc_ref.get_property(services.PROP_MQTT_TOPICS), False)))

        # New topics
        for topic in topics.difference(old_topics):
            self.__add_listener(topic, listener)

        # Removed old ones
        for topic in old_topics.difference(topics):
            self.__remove_listener(topic, listener)

    @UnbindField("_listeners")
    def _unbind_listener(
        self, field: str, listener: services.MqttListener, svc_ref: "ServiceReference[services.MqttListener]"
    ) -> None:
        """
        An MQTT listener is gone
        """
        topics = cast(Iterable[str], to_iterable(svc_ref.get_property(services.PROP_MQTT_TOPICS), False))
        for topic in topics:
            self.__remove_listener(topic, listener)

    def __clients_loop(self) -> None:
        """
        Control loop to let each client check its messages
        """
        while not self.__stop_event.wait(0.1) and not self.__stop_event.is_set():
            # Copy clients using the lock
            with self.__lock:
                clients = list(self._clients.items())

            # Loop upon them
            for pid, client in clients:
                rc = client.loop(0)
                if rc != 0:
                    # Reconnect on error
                    # FIXME: do a better job
                    _logger.warning(
                        "Loop error for client %s, reconnecting it (%d)",
                        pid,
                        rc,
                    )
                    # client.reconnect()

    def __on_message(self, client: paho.Client, userdata: Any, msg: paho.MQTTMessage) -> None:
        # pylint: disable=W0613
        """
        A message has been received from a server

        :param client: Client that received the message
        :param userdata: *Unused*
        :param msg: A Message bean
        """
        try:
            # Get the topic
            topic = msg.topic

            # Get all listeners matching this topic
            all_listeners: Set[services.MqttListener] = set()
            for subscription, listeners in self._topics.items():
                if paho.topic_matches_sub(subscription, topic):
                    all_listeners.update(listeners)

            # Notify them using the pool
            assert self._pool is not None
            self._pool.enqueue(
                self.__notify_listeners,
                all_listeners,
                topic,
                msg.payload,
                msg.qos,
            )
        except KeyError:
            # No listener for this topic
            pass

    @staticmethod
    def __notify_listeners(
        listeners: Iterable[services.MqttListener], topic: str, payload: bytes, qos: int
    ) -> None:
        """
        Notifies listeners of an MQTT message
        """
        for listener in listeners:
            try:
                listener.handle_mqtt_message(topic, payload, qos)
            except Exception as ex:
                _logger.exception("Error calling MQTT listener: %s", ex)

    def __subscribe(self, topic: str) -> None:
        """
        Subscribes to a topic in all servers
        """
        for client in self._clients.values():
            client.subscribe(topic, 0)

    def __unsubscribe(self, topic: str) -> None:
        """
        Unsubscribes from the topic from all servers
        """
        for client in self._clients.values():
            client.unsubscribe(topic)

    def updated(self, pid: str, properties: Dict[str, Any]) -> None:
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
            host: str = properties["host"]
            port: int = properties.get("port", 1883)
            keep_alive: int = properties.get("keepalive", 60)

            class Holder:
                """
                Reference holder for the service registration
                """

                registration: Optional["ServiceRegistration[_MqttConnection]"] = None

            holder = Holder()

            # Prepare operations once connected
            def on_connect(
                client: paho.Client,
                userdata: Any,
                flags: ConnectFlags,
                rc: ReasonCode,
                properties: Optional[Properties],
            ) -> None:
                # pylint: disable=W0613
                """
                Connected to the server
                """
                if rc.is_failure:
                    _logger.error("Error connecting to [%s]:%s (%s) - %s", host, port, client, pid)
                    return

                # Success !
                _logger.debug("Connected to [%s]:%s (%s) - %s", host, port, client, pid)

                if self._context is None:
                    _logger.error("Connected but no context available")
                    return

                # Store PID -> Client
                self._clients[pid] = client

                # Subscribe to topics
                # TODO: handle the QOS
                for topic in self._topics:
                    client.subscribe(topic, 0)

                # Stop the Paho thread
                client.loop_stop()

                # Register an mqtt.connection service
                svc = _MqttConnection(client)
                props = {"id": pid, "host": host, "port": port}
                holder.registration = self._context.register_service(_MqttConnection, svc, props)

                # Store PID -> ServiceRegistration
                self._services[pid] = holder.registration

            def on_disconnect(
                client: paho.Client,
                userdata: Any,
                flags: DisconnectFlags,
                rc: ReasonCode,
                properties: Optional[Properties],
            ) -> None:
                # pylint: disable=W0613
                """
                Disconnected from the server
                """
                _logger.warning("Disconnected from %s", host)

                # Clear from the list of clients
                del self._clients[pid]

                # Unregister service and clear reference
                if holder.registration is not None:
                    holder.registration.unregister()
                    holder.registration = None

            # Connect to the server
            client = paho.Client(CallbackAPIVersion.VERSION2)
            client.on_connect = on_connect
            client.on_disconnect = on_disconnect
            client.on_message = self.__on_message

            result_code = client.connect(host, port, keep_alive)
            if result_code != 0:
                # Can't connect to the server
                _logger.error(
                    "Error connecting to the MQTT server: %d - %s",
                    result_code,
                    CONNECT_RC.get(result_code, "Unknown error"),
                )
            else:
                # Start a Paho loop, as it has a specific connection handling
                client.loop_start()

    def deleted(self, pid: str) -> None:
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

    def publish(
        self, topic: str, payload: bytes, qos: int = 0, retain: bool = False, pid: Optional[str] = None
    ) -> None:
        """
        Publishes an MQTT message

        :param topic: Message topic
        :param payload: RAW message content
        :param qos: MQTT quality of service (0 by default)
        :param retain: Message must be retained
        :param pid: Optional connection PID
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


@constants.Specification(services.SERVICE_MQTT_CONNECTION)
class _MqttConnection:
    """
    Represents a connection to an MQTT server
    """

    def __init__(self, connection: paho.Client):
        """
        Sets up members

        :param connection: A Paho Client object
        """
        self._client = connection

    def publish(self, topic: str, payload: bytes, qos: int = 0, retain: bool = False) -> paho.MQTTMessageInfo:
        """
        Publishes an MQTT message
        """
        # TODO: check (full transmission) success
        return self._client.publish(topic, payload, qos, retain)
