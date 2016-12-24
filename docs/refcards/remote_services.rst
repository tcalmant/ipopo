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
Each transport provider then tests if it can/must create an endpoint for it and,
if so, returns an *export endpoint* description to the *exports dispatcher*.
The endpoint implementation is transport-dependent: it can be a servlet
(HTTP-based procotols), a serial-port listener, ...
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
Those endpoints will be stored in the *imports registry*, the other core service
of Pelix Remote Services.
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

* UID: the unique identifier of the endpoint. It is a class-4 UUID, which should
  be unique across frameworks.
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
access to the service reference and implemnetation, in order to let transport
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
  :class:`pelix.remote.dispatcher <pelix.remote.dispatcher.Dispatcher>` service.

* the *imports registry* which keeps track of and notifies the transports
  providers about the import endpoints, according to the notifications from
  the discovery providers.
  If a transport provider appears after the registration of an import endpoint,
  it will nevertheless be notified by the imports registry of existing endpoints.

  This service is provided by an auto-instantiated component from the
  ``pelix.remote.registry`` bundle.
  It provides a
  :class:`pelix.remote.registry <pelix.remote.registry.ImportsRegistry>` service.


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
`jsonrpclib-pelix <https://github.com/tcalmant/jsonrpclib/>`_ third-party module).
Indeed, the JSON-RPC layer has a better handling of dictionaries and custom
types.
iPOPO also supports a variant of JSON-RPC, *Jabsorb-RPC*, which adds Java type
information to the arguments and results.
As long as a Java interface is correctly implementing, this protocol allows a
Python service to be used by a remote OSGi Java framework, and vice-versa.
The OSGi framework must host the
`Java implementation <https://github.com/isandlaTech/cohorte-remote-services>`_
of the Pelix Remote Services.

All those protocols require the HTTP service to be up and running to work.
Finally, iPOPO also supports a kind of *MQTT-RPC* protocol, *i.e.* JSON-RPC over
MQTT.


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
