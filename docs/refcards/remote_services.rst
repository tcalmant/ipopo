.. _refcard_remote_services:
.. module:: pelix.remote

Remote Services
===============

Pelix/iPOPO provides support for *remote services*, *i.e.* consuming services
provided from another framework instance.
This provider can run on the same machine as the consumer, or on another one.

Discovery
---------

A framework must discover a service before being able to use it.
Pelix/iPOPO provides a set of discovery protocols:

* a home-made protocol based on UDP multicast packets, which supports addition,
  update and removal of services;
* a home-made protocol based on MQTT, which supports addition, update and
  removal of services;
* mDNS, which is a standard but doesn't support service update.

Transports
----------

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
