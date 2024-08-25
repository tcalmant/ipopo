.. _refcard_remote_services:
.. module:: pelix.remote

Remote Services
###############

Pelix/iPOPO provides support for *remote services*, *i.e.* consuming services
provided from another framework instance.
This provider can run on the same machine as the consumer, or on another one.

Concepts
========

Pelix/iPOPO remote services implementation is a based on a set of services.
This architecture eases the development of new providers and allows to plug in
or update protocols providers at run time.

In this section, we will shortly describe the basic concepts of Pelix Remote
Services, *i.e.*:

* the concept of import and export endpoints
* the core services required to activate remote services
* the discovery providers
* the transport providers

The big picture of the Pelix Remote Services can be seen as:

.. image:: /_static/rs_arch.svg
   :alt: Architecture of Pelix Remote Services
   :align: center
   :scale: 100%

Note that Pelix Remote Services implementation has been inspired from the
OSGi Remote Services specification, and tries to reuse most of its constants,
to ease compatibility.

Before that, it is necessary to see the big picture: how does Pelix Remote
Services works.


How does it work?
-----------------

The export and import of a service follows this sequence diagram, described
below:

.. image:: /_static/rs_sequence.svg
   :alt: Sequence of the export and import of a service
   :align: center
   :scale: 100%

When a service declares it can be exported, the *export dispatcher* detects
it (as it is a service listener) notifies all *transport providers* which
matches the service properties.
Each transport provider then tests if it can/must create an endpoint for it
and, if so, returns an *export endpoint* description to the
*exports dispatcher*.
The endpoint implementation is transport-dependent: it can be a servlet
(HTTP-based protocols), a serial-port listener, ...
As a result, there can be multiple *export endpoints* for a single service:
(at least) one per transport provider.
The description of each *export endpoint* is then stored in the
*exports dispatcher*, one of the core services of Pelix Remote Services.

When an endpoint (or a set of endpoints) is stored in the *exports dispatcher*,
the discovery providers are notified and send there protocol-specific events.
They can target other Pelix frameworks, but also any other kind of frameworks
(OSGi/Java, ...) or of software (like a Node.js server with mDNS support).
Those events indicate that new export endpoints are available: they can point
to the description of this endpoint or contain its serialized form.
Note that the description sent over the network must be an import-side
description: it should contain all information required to connect and use the
endpoint, stored in import properties so that the newly imported services don't
get exported by mistake.

Another framework using the same discovery provider can capture this event and
handle the new set of *import endpoints*.
Those endpoints will be stored in the *imports registry*, the other core
service of Pelix Remote Services.
If multiple discovery providers find the same endpoints, don't worry, they will
be filtered out according to their unique identifier (UUID).

The *imports registry* then notifies the *transport providers* to let them
create a local proxy to the remote service and register it as a local service
(with import properties).
This remote service is now usable by local consumers.


.. note:: In the current implementation of Pelix Remote Services, the same
   remote service can be imported multiple times by the same consumer framework.
   This is due to the fact that the imported service is created by the transport
   providers and not by the centralized imports registry.

   This behaviour is useful when you want to consume a service from a specific
   provider, or if you can sort transport providers by efficiency.
   This has to been taken into account in some cases, like when consuming
   multiple services of the same specification while multiple transport
   providers are active.

   This behaviour is subject to debate but is also used in some projects.
   It could be modified if enough problems are reported either on the
   `mailing list <https://groups.google.com/forum/#!forum/ipopo-users>`_ or
   in `GitHub issues <https://github.com/tcalmant/ipopo/issues>`_.

Finally, Pelix Remote Services also supports the update of service properties,
which can be handled as a minimalist event by the discovery providers, *e.g.*
containing only the endpoint UID and the new properties.
The unregistration is often the simplest event of a discovery provider, sending
only the endpoint UID.

Export/Import Endpoints
-----------------------

The endpoints objects are declared in ``pelix.remote.beans`` by the
:class:`~pelix.remote.beans.ExportEndpoint` and
:class:`~pelix.remote.beans.ImportEndpoint` classes.

Both contain the following information:

* UID: the unique identifier of the endpoint. It is a class-4 UUID, which
  should be unique across frameworks.
* Framework: the UID of the framework providing the endpoint. It is mainly
  used to clean up the endpoints of a lost framework.
  If too many endpoint UID collisions are reported, it could be used as a
  secondary key.
* Name: the name of the endpoint. It can have a meaning for the transport
  provider, but isn't used by Pelix itself.
* Properties: a copy of the current properties of the remote service.
* Specifications: the list of service exported specifications. A service can
  choose to export a subset of its specifications, as some could be private or
  using non-serializable types.
* Configurations: the list of transports allowed to export this endpoint or
  used for importing it.

Finally, the :class:`~pelix.remote.beans.ExportEndpoint` object also gives
access to the service reference and implementation, in order to let transport
providers access the methods and properties of the service.


Core Services
-------------

The core services of the Pelix Remote Services implementation is based on two
services:

* the *exports dispatcher* which keeps track of and notifies the discovery
  providers about the export endpoints created/updated/deleted by transport
  providers.
  If a discovery provider appears after the creation of an export endpoint,
  it will still be notified by the exports dispatcher.

  This service is provided by an auto-instantiated component from the
  ``pelix.remote.dispatcher`` bundle.
  It provides a
  :class:`pelix.remote.dispatcher <pelix.remote.dispatcher.Dispatcher>`
  service.

* the *imports registry* which keeps track of and notifies the transports
  providers about the import endpoints, according to the notifications from
  the discovery providers.
  If a transport provider appears after the registration of an import endpoint,
  it will nevertheless be notified by the imports registry of existing
  endpoints.

  This service is provided by an auto-instantiated component from the
  ``pelix.remote.registry`` bundle.
  It provides a
  :class:`pelix.remote.registry <pelix.remote.registry.ImportsRegistry>`
  service.


Dispatcher Servlet
------------------

The content of the *exports dispatcher* can be exposed by the
*dispatcher servlet*, provided by the same bundle as the *exports dispatcher*,
``pelix.remote.dispatcher``.
Most discovery providers rely on this servlet as it allows to get the list of
exported endpoints, or the details of a single one, in JSON format.

This servlet must be instantiated explicitly using its
``pelix-remote-dispatcher-servlet-factory`` factory.
As it is a servlet, it requires the HTTP service to be up and running to
provide it to clients.

Its API is very simple:

* ``/framework``: returns the framework UID as a JSON string
* ``/endpoints``: returns the whole list of the export endpoints registered in
  the exports dispatcher, as a JSON array of JSON objects.
* ``/endpoint/<uid>``: returns the export endpoint with the given UID as a
  JSON object.

Discovery Providers
-------------------

A framework must discover a service before being able to use it.
Pelix/iPOPO provides a set of discovery protocols:

* a home-made protocol based on UDP multicast packets, which supports addition,
  update and removal of services;
* a home-made protocol based on MQTT, which supports addition, update and
  removal of services;
* mDNS, which is a standard but doesn't support service update;
* a discovery service based on `Redis <https://redis.io>`_.

Transport Providers
-------------------

The *remote services* implementation supports XML-RPC (using the
`xmlrpc <https://docs.python.org/3/library/xmlrpc.html>`_ standard package), but
it is recommended to use JSON-RPC instead (using the
`jsonrpclib-pelix <https://github.com/tcalmant/jsonrpclib/>`__ third-party module).
Indeed, the JSON-RPC layer has a better handling of dictionaries and custom
types.
iPOPO also supports a variant of JSON-RPC, *Jabsorb-RPC*, which adds Java type
information to the arguments and results.
As long as a Java interface is correctly implementing, this protocol allows a
Python service to be used by a remote OSGi Java framework, and vice-versa.
The OSGi framework must host the
`Java implementation <https://github.com/cohorte/cohorte-remote-services>`_
of the Pelix Remote Services.

All those protocols require the HTTP service to be up and running to work.
Finally, iPOPO also supports a kind of *MQTT-RPC* protocol, *i.e.* JSON-RPC
over MQTT.


Providers included with Pelix/iPOPO
===================================

This section gives more details about the usage of the discovery and transport
providers included in Pelix/iPOPO.
You'll need at least a discovery and a compatible transport provider for
Pelix Remote Services to work.

Apart MQTT, the discovery and transport providers are independent and can be
used with one another.

Multicast Discovery
-------------------

:Bundle: pelix.remote.discovery.multicast
:Factory: pelix-remote-discovery-multicast-factory
:Requires: HTTP Service, Dispatcher Servlet
:Libraries: *nothing* (based on the Python Standard Library)

Pelix comes with a home-made UDP multicast discovery protocol, implemented in
the ``pelix.remote.discovery.multicast`` bundle.
This is the original discovery protocol of Pelix/iPOPO and the most reliable
one in small local area networks.
A Java version of this protocol is provided by the
`Cohorte Remote Services implementation <https://github.com/cohorte/cohorte-remote-services>`_.

This protocol consists in minimalist packets on remote service registration,
update and unregistration.
They mainly contain the notification event type, the port of the HTTP server of
the framework and the path to the dispatcher servlet.
The IP of the framework is the source IP of the multicast packet: this allows
to get a valid address for frameworks on servers with multiple network
interfaces.

This provider relies on the HTTP server and the *dispatcher servlet*.
It doesn't have external dependencies.

The bundle provides a ``pelix-remote-discovery-multicast-factory`` iPOPO
factory, which **must** be instantiated to work.
It can be configured with the following properties:

=============== ============= =================================================
Property        Default value Description
=============== ============= =================================================
multicast.group 239.0.0.1     The multicast group (address) to join to send and receive discovery messages.
multicast.port  42000         The multicast port to listen to
=============== ============= =================================================

To use this discovery provider, you'll need to install the following bundles
and instantiate the associated components:

.. code-block:: shell

   # Start the HTTP service with default parameters
   install pelix.http.basic
   start $?
   instantiate pelix.http.service.basic.factory httpd

   # Install Remote Services Core
   install pelix.remote.registry
   start $?
   install pelix.remote.dispatcher
   start $?

   # Instantiate the dispatcher servlet
   instantiate pelix-remote-dispatcher-servlet-factory dispatcher-servlet

   # Install and start the multicast discovery with the default parameters
   install pelix.remote.discovery.multicast
   start $?
   instantiate pelix-remote-discovery-multicast-factory discovery-mcast


mDNS Discovery
--------------

:Bundle: pelix.remote.discovery.mdns
:Factory: pelix-remote-discovery-zeroconf-factory
:Requires: HTTP Service, Dispatcher Servlet
:Libraries: `pyzeroconf <https://github.com/mcfletch/pyzeroconf>`_

The mDNS protocol, also known as Zeroconf, is a standard protocol based on
multicast packets.
It provides a Service Discovery layer (mDNS-SD) based on the DNS-SD
specification.

Unlike the home-made multicast protocol, this one doesn't support service
updates and gives troubles with service unregistrations (frameworks lost, ...).
As a result, it should be used only if it is required to interact with other
mDNS devices.

In order to work with the mDNS discovery from the
Eclipse Communication Framework, the ``pyzeroconf`` library must be patched:
the ``.local.`` check in ``zeroconf.mdns.DNSQuestion`` must be removed
(around line 220).

This provider is implemented in the ``pelix.remote.discovery.mdns`` bundle,
which provides a ``pelix-remote-discovery-zeroconf-factory`` iPOPO
factory, which **must** be instantiated to work.
It can be configured with the following properties:

===================== ===================== ===================================
Property              Default value         Description
===================== ===================== ===================================
zeroconf.service.type _pelix_rs._tcp.local. Zeroconf service type of exported services
zeroconf.ttl          60                    Time To Live of services (in seconds)
===================== ===================== ===================================

To use this discovery provider, you'll need to install the following bundles
and instantiate the associated components:

.. code-block:: shell

   # Start the HTTP service with default parameters
   install pelix.http.basic
   start $?
   instantiate pelix.http.service.basic.factory httpd

   # Install Remote Services Core
   install pelix.remote.registry
   start $?
   install pelix.remote.dispatcher
   start $?

   # Instantiate the dispatcher servlet
   instantiate pelix-remote-dispatcher-servlet-factory dispatcher-servlet

   # Install and start the mDNS discovery with the default parameters
   install pelix.remote.discovery.mdns
   start $?
   instantiate pelix-remote-discovery-zeroconf-factory discovery-mdns


Redis Discovery
---------------

:Bundle: pelix.remote.discovery.redis
:Factory: pelix-remote-discovery-redis-factory
:Requires: *nothing* (all is stored in the Redis database)
:Libraries: `redis <https://pypi.org/project/redis/>`__

The Redis discovery is the only one working well in Docker (Swarm) networks.
It uses a `Redis database <https://redis.io/>`__ to store the host name of each
framework and the description of each exported endpoint of each framework.
Those description are stored in the OSGi standard EDEF XML format, so it should
be possible to implement a Java version of this discovery provider.
The Redis discovery uses the *key events* of the database to be notified by
the latter when a framework or an exported service is registered, updated,
unregistered or timed out, which makes it both robust and reactive.

This provider is implemented in the ``pelix.remote.discovery.redis`` bundle,
which provides a ``pelix-remote-discovery-redis-factory`` iPOPO factory, which
**must** be instantiated to work.
It can be configured with the following properties:

=============== ============= =================================================
Property        Default value Description
=============== ============= =================================================
redis.host      localhost     The hostname of the Redis server
redis.port      46379         The port the Redis server listens to
redis.db        0             The Redis database to use (integer)
redis.password  None          Password to access the Redis database
heartbeat.delay 10            Delay in seconds between framework heart beats
=============== ============= =================================================

To use this discovery provider, you'll need to install the following bundles
and instantiate the associated components:

.. code-block:: shell

   # Install Remote Services Core
   install pelix.remote.registry
   start $?
   install pelix.remote.dispatcher
   start $?

   # Install and start the Redis discovery with the default parameters
   install pelix.remote.discovery.redis
   start $?
   instantiate pelix-remote-discovery-redis-factory discovery-redis


XML-RPC Transport
-----------------

:Bundle: pelix.remote.xml_rpc
:Factories: pelix-xmlrpc-exporter-factory, pelix-xmlrpc-importer-factory
:Requires: HTTP Service
:Libraries: *nothing* (based on the Python Standard Library)

The XML-RPC transport is the first one having been implemented in Pelix/iPOPO.
Its main advantage is that is doesn't depend on an external library, XML-RPC
being supported by the Python Standard Library.

It has some troubles with complex and custom types (dictionaries, ...), but can
be used without problems on primitive types.
The JSON-RPC transport can be preferred in most cases.

Like most of the transport providers, this one is split in two components:
the exporter and the importer.
Both must be instantiated manually.

The exporter instance can be configured with the following property:

=============== ============= =================================================
Property        Default value Description
=============== ============= =================================================
pelix.http.path /XML-RPC      The path to the XML-RPC exporter servlet
=============== ============= =================================================

To use this transport provider, you'll need to install the following bundles
and instantiate the associated components:

.. code-block:: shell

   # Start the HTTP service with default parameters
   install pelix.http.basic
   start $?
   instantiate pelix.http.service.basic.factory httpd

   # Install Remote Services Core
   install pelix.remote.registry
   start $?
   install pelix.remote.dispatcher
   start $?

   # Install and start the XML-RPC importer and exporter with the default
   # parameters
   install pelix.remote.xml_rpc
   start $?
   instantiate pelix-xmlrpc-exporter-factory xmlrpc-exporter
   instantiate pelix-xmlrpc-importer-factory xmlrpc-importer


JSON-RPC Transport
------------------

:Bundle: pelix.remote.json_rpc
:Factories: pelix-jsonrpc-exporter-factory, pelix-jsonrpc-importer-factory
:Requires: HTTP Service
:Libraries: `jsonrpclib-pelix <https://github.com/tcalmant/jsonrpclib>`__
            (installation requirement of iPOPO)

The JSON-RPC transport is the recommended one in Pelix/iPOPO.
It depends on an external library,
`jsonrpclib-pelix <https://github.com/tcalmant/jsonrpclib>`__
which has no transient dependency.
It has way less troubles with complex and custom types than the XML-RPC
transport, which eases the development of most of Pelix/iPOPO applications.

Like most of the transport providers, this one is split in two components:
the exporter and the importer.
Both must be instantiated manually.

The exporter instance can be configured with the following property:

=============== ============= =================================================
Property        Default value Description
=============== ============= =================================================
pelix.http.path /JSON-RPC      The path to the JSON-RPC exporter servlet
=============== ============= =================================================

To use this transport provider, you'll need to install the following bundles
and instantiate the associated components:

.. code-block:: shell

   # Start the HTTP service with default parameters
   install pelix.http.basic
   start $?
   instantiate pelix.http.service.basic.factory httpd

   # Install Remote Services Core
   install pelix.remote.registry
   start $?
   install pelix.remote.dispatcher
   start $?

   # Install and start the JSON-RPC importer and exporter with the default
   # parameters
   install pelix.remote.json_rpc
   start $?
   instantiate pelix-jsonrpc-exporter-factory jsonrpc-exporter
   instantiate pelix-jsonrpc-importer-factory jsonrpc-importer


Jabsorb-RPC Transport
---------------------

:Bundle: pelix.remote.transport.jabsorb_rpc
:Factories: pelix-jabsorbrpc-exporter-factory,
            pelix-jabsorbrpc-importer-factory
:Requires: HTTP Service
:Libraries: `jsonrpclib-pelix <https://github.com/tcalmant/jsonrpclib>`__
            (installation requirement of iPOPO)

The JABSORB-RPC transport is based on a variant of the JSON-RPC protocol.
It adds Java typing hints to ease unmarshalling on Java clients, like the
`Cohorte Remote Services implementation <https://github.com/cohorte/cohorte-remote-services>`_.
The additional information comes at small cost, but this transport shouldn't be
used when no Java frameworks are expected: it doesn't provide more features
than JSON-RPC in a 100% Python environment.

Like the JSON-RPC transport, it depends on an external library,
`jsonrpclib-pelix <https://github.com/tcalmant/jsonrpclib>`__ which has no
transient dependency.

Like most of the transport providers, this one is split in two components:
the exporter and the importer.
Both must be instantiated manually.

The exporter instance can be configured with the following property:

=============== ============= =================================================
Property        Default value Description
=============== ============= =================================================
pelix.http.path /JABSORB-RPC  The path to the JABSORB-RPC exporter servlet
=============== ============= =================================================

To use this transport provider, you'll need to install the following bundles
and instantiate the associated components:

.. code-block:: shell

   # Start the HTTP service with default parameters
   install pelix.http.basic
   start $?
   instantiate pelix.http.service.basic.factory httpd

   # Install Remote Services Core
   install pelix.remote.registry
   start $?
   install pelix.remote.dispatcher
   start $?

   # Install and start the JABSORB-RPC importer and exporter with the default
   # parameters
   install pelix.remote.transport.jabsorb_rpc
   start $?
   instantiate pelix-jabsorbrpc-exporter-factory jabsorbrpc-exporter
   instantiate pelix-jabsorbrpc-importer-factory jabsorbrpc-importer


MQTT discovery and MQTT-RPC Transport
-------------------------------------

:Bundle: pelix.remote.discovery.mqtt, pelix.remote.transport.mqtt_rpc
:Factories: pelix-remote-discovery-mqtt-factory,
            pelix-mqttrpc-exporter-factory, pelix-mqttrpc-importer-factory
:Requires: *nothing* (everything goes through MQTT messages)
:Libraries: `paho-mqtt <https://eclipse.dev/paho/>`_

Finally, the MQTT discovery and transport protocols have been developed as a
proof of concept with the
`fabMSTIC <https://2007-2020.liglab.fr/fr/la-recherche/plates-formes-du-lig/fablab-campus-recherche-pole-mstic.html>`_
fablab of the Grenoble Alps University.

The idea was to rely on the lightweight MQTT messages to provide both discovery
and transport mechanisms, and to let them be handled by low-power devices like
small Arduino boards.
Mixed results were obtained: it worked but the performances were not those
intended, mainly in terms of latencies.

Those providers are kept in Pelix/iPOPO as they work and provide a non-HTTP way
to communicate, but they won't be updated without new contributions
(pull requests, ...).

They rely on the `Eclipse Paho <https://eclipse.dev/paho/>`_ library,
previously known as the `Mosquitto <https://mosquitto.org/>`_ library.

The discovery instance can be configured with the following properties:

============== ============================= ==================================
Property       Default value Description
============== ============================= ==================================
mqtt.host      localhost                     Host of the MQTT server
mqtt.port      1883                          Port of the MQTT server
topic.prefix   pelix/{appid}/remote-services Prefix of all MQTT messages (format string accepting the ``appid`` entry)
application.id None                          Application ID, to allow multiple applications on the same server
============== ============================= ==================================

The transport exporter and importer instances should be configured with the
same ``mqtt.host`` and ``mqtt.port`` properties as the discovery service.

To use the MQTT providers, you'll need to install the following bundles and
instantiate the associated components:

.. code-block:: shell

   # Install Remote Services Core
   install pelix.remote.registry
   start $?
   install pelix.remote.dispatcher
   start $?

   # Install and start the MQTT discovery and the MQTT-RPC importer and exporter
   # with the default parameters
   install pelix.remote.discovery.mqtt
   start $?
   instantiate pelix-remote-discovery-mqtt-factory mqttrpc-discovery

   install pelix.remote.transport.mqtt_rpc
   start $?
   instantiate pelix-mqttrpc-exporter-factory mqttrpc-exporter
   instantiate pelix-mqttrpc-importer-factory mqttrpc-importer


API
===

Endpoints
---------

``ExportEndpoint`` objects are created by transport providers and stored in the
registry of the *exports dispatcher*.
It is used by discovery providers to create a description of the endpoint to
send over the network and suitable for the import-side.

.. autoclass:: pelix.remote.beans.ExportEndpoint
   :members:


``ImportEndpoint`` objects are the description of an endpoint on the consumer
side.
They are given by the *imports registry* to the *transport providers* on the
import side.

.. autoclass:: pelix.remote.beans.ImportEndpoint
   :members:


Core Services
-------------

The *exports dispatcher* service provides the ``pelix.remote.dispatcher``
(constant string stored in ``pelix.remote.SERVICE_DISPATCHER``) service, with
the following API:

.. autoclass:: pelix.remote.dispatcher.Dispatcher
   :members: get_endpoint, get_endpoints


The *import registry* service provides the ``pelix.remote.registry``
(constant string stored in ``pelix.remote.SERVICE_REGISTRY``) service, with
the following API:

.. autoclass:: pelix.remote.registry.ImportsRegistry
   :members:
