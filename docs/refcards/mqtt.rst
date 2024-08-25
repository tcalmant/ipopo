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
from the Paho libary.
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
