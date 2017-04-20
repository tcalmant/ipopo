.. _refcard_eventadmin:

EventAdmin service
##################

Description
===========

The EventAdmin service defines an inter-bundle communication mechanism.

.. note:: This service is inspired from the EventAdmin specification in OSGi,
   but without the ``Event`` class.

It is a publish/subscribe communication service, using the whiteboard pattern,
that allows to send an *event*:

* the publisher of an event uses the EventAdmin service to send its event
* the handler (or subscriber or listener) publishes a service with filtering
  properties

An event is the association of:

* a topic, a URI-like string that defines the nature of the event
* a set of properties associated to the event

Some properties are defined by the EventAdmin service:

========================== ===== ===============================================
Property                   Type  Description
========================== ===== ===============================================
event.sender.framework.uid str    UID of the framework that emitted the event. Useful in remote services
event.timestamp            float Time stamp of the event, computed when the event is given to EventAdmin
========================== ===== ===============================================

Usage
=====

Instantiation
-------------

The EventAdmin service is implemented in ``pelix.services.eventadmin`` bundle,
as a single iPOPO component.
This component must be instantiated programmatically, by using the iPOPO
service and the ``pelix-services-eventadmin-factory`` factory name.

.. code-block:: python

    from pelix.ipopo.constants import use_ipopo
    import pelix.framework

    # Start the framework (with iPOPO)
    framework = pelix.framework.create_framework(['pelix.ipopo.core'])
    framework.start()
    context = framework.get_bundle_context()

    # Install & start the EventAdmin bundle
    context.install_bundle('pelix.services.eventadmin').start()

    # Get the iPOPO the service
    with use_ipopo(context) as ipopo:
       # Instantiate the EventAdmin component
       ipopo.instantiate('pelix-services-eventadmin-factory',
                         'EventAdmin', {})

It can also be instantiated via the Pelix Shell:

.. code-block:: bash

    $ install pelix.services.eventadmin
    Bundle ID: 12
    $ start 12
    Starting bundle 12 (pelix.services.eventadmin)...
    $ instantiate pelix-services-eventadmin-factory eventadmin
    Component 'eventadmin' instantiated.


The EventAdmin component accepts the following property as a configuration:

============ ============= =====================================================
Property     Default value Description
============ ============= =====================================================
pool.threads 10            Number of threads in the pool used for asynchronous delivery
============ ============= =====================================================

Interfaces
----------

EventAdmin service
^^^^^^^^^^^^^^^^^^

The EventAdmin service provides the ``pelix.services.eventadmin`` specification:

.. autoclass:: pelix.services.eventadmin.EventAdmin
   :members: post, send

Both ``send`` and ``post`` methods get the topic as first parameter, which must
be a URI-like string, *e.g.* ``sensor/temperature/changed`` and a dictionary
as second parameter, which can be ``None``.

When sending an event, each handler is notified with a different copy of the
property dictionary, avoiding to propagate changes done by a handler.


EventHandler service
^^^^^^^^^^^^^^^^^^^^

An event handler must provide the ``pelix.services.eventadmin.handler``
specification, which defines by the following method:

.. py:method:: handle_event(topic, properties)

   Called by the EventAdmin service to notify a handler of a new event

   :param topic: The topic of the event (str)
   :param properties: The properties associated to the event (dict)


.. warning:: Events sent using the ``post()`` are delivered from another thread.
   It is unlikely but possible that sometimes the ``handle_event()`` method may
   be called whereas the handler service has been unregistered, for example
   after the handler component has been invalidated.

   It is therefore recommended to check that the injected dependencies used in
   this method are not ``None`` before handling the event.

An event handler must associate at least one the following properties to its
service:

============ =========== =======================================================
Property     Type        Description
============ =========== =======================================================
event.topics List of str A list of strings that indicates the topics the topics this handler expects. EventAdmin supports "file name" filters, i.e. with  ``*`` or ``?`` jokers.
event.filter str         A LDAP filter string that will be tested on the event properties
============ =========== =======================================================


Example
-------

In this example, a component will publish an event when it is validated or
invalidated.
These events will be:

  * ``example/publisher/validated``
  * ``example/publisher/invalidated``

The event handler component will provide a service with a topic filter that
accepts both topics: ``example/publisher/*``

Publisher
^^^^^^^^^

The publisher requires the EventAdmin service, which specification is defined
in the ``pelix.services`` module.

.. code-block:: python

    # iPOPO
    from pelix.ipopo.decorators import *
    import pelix.ipopo.constants as constants

    # EventAdmin constants
    import pelix.services

    @ComponentFactory('publisher-factory')
    # Require the EventAdmin service
    @Requires('_event', pelix.services.SERVICE_EVENT_ADMIN)
    # Inject our component name in a field
    @Property('_name', constants.IPOPO_INSTANCE_NAME)
    # Auto-instantiation
    @Instantiate('publisher')
    class Publisher(object):
      """
      A sample publisher
      """
      def __init__(self):
          """
          Set up members, to be OK with PEP-8
          """
          # EventAdmin (injected)
          self._event = None

          # Component name (injected property)
          self._name = None

      @Validate
      def validate(self, context):
          """
          Component validated
          """
          # Send a "validated" event
          self._event.send("example/publisher/validated",
                           {"name": self._name})

      @Invalidate
      def invalidate(self, context):
          """
          Component invalidated
          """
          # Post an "invalidated" event
          self._event.send("example/publisher/invalidated",
                           {"name": self._name})


Handler
^^^^^^^

The event handler has no dependency requirement.
It has to provide the EventHandler specification, which is defined in the
``pelix.services`` module.

.. code-block:: python

    # iPOPO
    from pelix.ipopo.decorators import *
    import pelix.ipopo.constants as constants

    # EventAdmin constants
    import pelix.services

    @ComponentFactory('handler-factory')
    # Provide the EventHandler service
    @Provides(pelix.services.SERVICE_EVENT_HANDLER)
    # The event topic filters, injected as a component property that will be
    # propagated to its services
    @Property('_event_handler_topic', pelix.services.PROP_EVENT_TOPICS,
            ['example/publisher/*'])
    # The event properties filter (optional, here set to None by default)
    @Property('_event_handler_filter', pelix.services.PROP_EVENT_FILTER)
    # Auto-instantiation
    @Instantiate('handler')
    class Handler(object):
      """
      A sample event handler
      """
      def __init__(self):
          """
          Set up members
          """
          self._event_handler_topic = None
          self._event_handler_filter = None


      def handle_event(self, topic, properties):
          """
          Event received
          """
          print('Got a {0} event from {1} at {2}' \
                .format(topic, properties['name'],
                        properties[pelix.services.EVENT_PROP_TIMESTAMP]))

It is recommended to define an event filter property, even if it is set to
``None`` by default: it allows to customize the event handler when it is
instantiated using the iPOPO API:

.. code-block:: python

    # This handler will be notified only of events with a topic matching
    # 'example/publisher/*' (default value of 'event.topics'), and in which
    # the 'name' property is 'foobar'.
    ipopo.instantiate('handler-factory', 'customized-handler',
                      {pelix.services.PROP_EVENT_FILTER: '(name=foobar)'})


Shell Commands
==============

It is possible to send events from the Pelix shell, after installing the
``pelix.shell.eventadmin`` bundle.

This bundle defines two commands, in the ``event`` scope:

========================================= ======================================
Command                                   Description
========================================= ======================================
``post <topic> [<property=value> [...]]`` Posts an event on the given topic, with the given properties
``send <topic> [<property=value> [...]]`` Sends an event on the given topic, with the given properties
========================================= ======================================

Here is a sample shell session, considering the sample event handler above has
been started.
It installs and start the EventAdmin shell bundle:

.. code-block:: bash

    $ install pelix.shell.eventadmin
    13
    $ start 13
    $ event.send example/publisher/activated name=foobar
    Got a example/publisher/activated from foobar at 1369125501.028135


Events printer utility component
================================

A ``pelix-misc-eventadmin-printer-factory`` component factory is provided by the
``pelix.misc.eventadmin_printer`` bundle.
It can be used to instantiate components that will print and/or log the event
matching a given filter.

Here is a Pelix Shell snippet to instantiate a printer and to send it some
events:

.. code-block:: bash

    $ install pelix.shell.eventadmin
    13
    $ start 13
    $ install pelix.misc.eventadmin_printer
    14
    $ start 14
    $ instantiate pelix-misc-eventadmin-printer-factory printerA event.topics=foo/*
    Component 'printerA' instantiated.
    $ instantiate pelix-misc-eventadmin-printer-factory printerB evt.log=True event.topics=foo/bar/*
    Component 'printerB' instantiated.
    $ send foo/abc
    Event: foo/abc
    Properties:
    {'event.sender.framework.uid': 'aa180e9b-bb45-4cbf-8092-d45fbe12464f',
     'event.timestamp': 1492698306.1903257}
    $ send foo/bar/def
    Event: foo/bar/def
    Properties:
    {'event.sender.framework.uid': 'aa180e9b-bb45-4cbf-8092-d45fbe12464f',
     'event.timestamp': 1492698324.9549854}
    Event: foo/bar/def
    Properties:
    {'event.sender.framework.uid': 'aa180e9b-bb45-4cbf-8092-d45fbe12464f',
     'event.timestamp': 1492698324.9549854}

The second event is printed twice as it is handled by both printers.

MQTT Bridge
===========

Pelix provides a bridge to send EventAdmin events to an MQTT server and
vice-versa.
This can be used to send events between various Pelix frameworks, without the
need of the remote services layer, or between different entities sharing an
MQTT server.

The component factory, ``pelix-services-eventadmin-mqtt-factory``, is provided
by the ``pelix.services.eventadmin_mqtt`` bundle.
It can be configured with the following properties:

================= ===================== ========================================
Property          Default Value         Description
================= ===================== ========================================
event.topics      ``*``                 The filter to select the events to share
mqtt.host         localhost             The host name of the MQTT server
mqtt.port         1883                  The port the MQTT server is bound to
mqtt.topic.prefix ``/pelix/eventadmin`` The prefix to add to events before sending them over MQTT
================= ===================== ========================================

Events handled by this component, i.e. matching the filter given at
instantiation time, and having the ``event.propagate`` property set to any
value (even ``False``) will be sent as messages to the MQTT server with the
following modifications:

* the MQTT message topic will be the event topic prefixed by the value of the
  ``mqtt.topic.prefix`` property
* if the event topic starts with a slash (``/``), a
  ``pelix.eventadmin.mqtt.start_slash`` property is added to the event and is
  set to ``True``
* a ``pelix.eventadmin.mqtt.source`` is added to the event, containing the UUID
  of the emitting framework, to avoid loops.

The event properties are then converted to JSON and used as the body the MQTT
message.

When an MQTT message starting with the configured prefix is received, it is
converted back to an event, given to EventAdmin.
Loopback messages are detected and ignored to avoid loops.
