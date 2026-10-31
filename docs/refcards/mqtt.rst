Pelix MQTT client service
#########################

.. note::

   This reference card represents the current state of the MQTT service, which
   is subject to change.

   Since the initial version of this service (in 2014), the usage and API of
   this service is not clear enough.
   `Issue #18 <https://github.com/tcalmant/ipopo/issues/18>`__, created at
   that time, can be a place to discuss about enhancements or removal of this
   service.

Pelix provides a service to be notified of MQTT messages from different servers.
It abstracts the underlying MQTT library (Eclipse Paho) to ensure the API stays
the same despite library upgrades or changes.

.. _mqtt-connection:

Connection to the broker
------------------------

The MQTT components of Pelix (MQTT discovery and MQTT-RPC of the remote
services, EventAdmin MQTT bridge) read the same instance properties to connect
to their broker.
They are parsed by :class:`pelix.misc.mqtt_client.MqttConnectionConfig`, which
can also be used to configure a :class:`~pelix.misc.mqtt_client.MqttClient` in
custom code.

======================== =================== =============================================================
Property                 Default             Description
======================== =================== =============================================================
mqtt.host                ``localhost``       Broker host name
mqtt.port                1883, 8883 with TLS Broker port
mqtt.keepalive           60                  Maximum delay (in seconds) between two exchanges
mqtt.client_id           random              Client ID: it must be unique on the broker
mqtt.max_queued_messages 1000                Maximum QoS 1 and 2 messages waiting to be sent (0: no limit)
mqtt.username                                User name to authenticate on the broker
mqtt.password                                Password of the user (hidden property)
mqtt.tls                 ``False``           Connect with TLS
mqtt.tls.ca_file         system authorities  Authorities trusted to verify the broker (PEM)
mqtt.tls.cert_file                           Client certificate (PEM)
mqtt.tls.key_file                            Private key of the client certificate (PEM)
======================== =================== =============================================================

TLS is enabled by ``mqtt.tls`` or by any of the ``mqtt.tls.*`` files.
The broker certificate and its host name are always verified: give the
certificate of a private authority with ``mqtt.tls.ca_file``.
An invalid or missing TLS file stops the component at validation.

``mqtt.password`` is declared as a hidden property: it is never visible in the
service properties of the component.

.. code-block:: python

   ipopo.instantiate(
       pelix.remote.FACTORY_DISCOVERY_MQTT,
       "mqtt-discovery",
       {
           "mqtt.host": "broker.example.com",
           "mqtt.tls.ca_file": "/etc/pelix/broker-ca.pem",
           "mqtt.username": "pelix",
           "mqtt.password": password,
       },
   )

.. autoclass:: pelix.misc.mqtt_client.MqttConnectionConfig
   :members: from_properties, make_client, connect

Reconnection and disconnected publications
------------------------------------------

:class:`~pelix.misc.mqtt_client.MqttClient` reconnects to its broker when the
connection is lost or can't be established, with a delay growing from 1 to 120
seconds (Paho's reconnection). Each failed attempt is logged as a warning with
its cause, a TLS verification error included. After a reconnection without the
previous session, the client subscribes again to the topics given to
:meth:`~pelix.misc.mqtt_client.MqttClient.subscribe`.

While disconnected, :meth:`~pelix.misc.mqtt_client.MqttClient.publish` queues
the QoS 1 and 2 messages, up to ``mqtt.max_queued_messages`` (the
``max_queued_messages`` argument of the client), and sends them once connected:
it returns their message ID, and
:meth:`~pelix.misc.mqtt_client.MqttClient.wait_publication` tells when they
are sent. A QoS 0 message while disconnected, or any message when the queue is
full, is refused: ``publish()`` returns ``None``.

The client also supports MQTT v5 (``protocol=MQTTv5``).

MQTT service
------------

The MQTT service provides the :class:`pelix.services.MqttConnectorFactory`
specification (named ``pelix.mqtt.factory``).

You can use this service to publish a message to all connected brokers at once
using its :meth:`~pelix.services.MqttConnectorFactory.publish` method.

Configuring brokers
-------------------

The Pelix MQTT service is configured using :ref:`configadmin`, with the
``mqtt.connector`` factory PID.

The configuration can contain the following entries:

========= ======= ===========
Property  Default Description
========= ======= ===========
host              Broker host name (mandatory)
port      1883    Broker port
keepalive 60      Connection keepalive (in seconds)
========= ======= ===========

For now, the MQTT service doesn't support other configuration properties.
`Issue #18 <https://github.com/tcalmant/ipopo/issues/18>`__ can be used to
discuss about further developments of that service, for example to support
TLS configuration, authentication, etc.


MQTT connections
----------------

The MQTT service registers a service of specification named
``pelix.mqtt.connection`` for each broker it connects to.
This service allows to publish a message to its specific broker.

There is no *public* typed specification for that service yet as it depends on types
from the Paho library.
The current *protected* specification is
:class:`pelix.services.mqtt._MqttConnection` and is subject to change.

Each service has the following properties:

======== ====== ===========
Property Type   Description
======== ====== ===========
id       string Broker configuration PID
host     string Broker host name
port     int    Broker port
======== ====== ===========


Setting up listeners
--------------------

The MQTT service follows the whiteboard pattern: listeners are declared as
services providing the :class:`pelix.services.MqttListener` specification
(name: ``pelix.mqtt.listener``).

This service can hold the ``pelix.mqtt.topics`` containing either a string or
a list of strings: the MQTT service will subscribe to those topics to all the
brokers it is or will be connected to.
The topics can be given as MQTT topic filter strings.
The list can be updated dynamically: the MQTT service will un/subscribe
accordingly.

API
---

.. autoclass:: pelix.services.MqttConnectorFactory
   :members:

.. autoclass:: pelix.services.MqttListener
   :members:

.. py:class:: pelix.services.mqtt._MqttConnection

   Represents a connection to a specific broker.

   .. warning:: This API is subject to changes

   .. py:method:: publish(topic: str, payload: bytes, qos: int = 0, retain: bool = False) -> paho.MQTTMessageInfo:

      Publishes an MQTT message to the connected broker

      :param topic: Topic to send the message on
      :param payload: Raw message payload
      :param qos: Message Quality of service:
      :param retain: If true, ask the broker to retain the message for that topic
      :return: A Paho message information
