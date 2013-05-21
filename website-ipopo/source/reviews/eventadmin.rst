.. EventAdmin tutorial

.. _eventadmin:

EventAdmin service
##################

Description
***********

The EventAdmin service defines an inter-bundle communication mechanism.

.. note:: This service is inspired from the EventAdmin specification in OSGi,
   but without the ``Event`` class.

It is a publish/subscribe communication service, using the whiteboard pattern,
that allows to send an *Event*:

* the publisher of an event uses the EventAdmin service to send its event
* the handler (or subscriber or listener) publishes a service with filtering
  properties

An event is the association of:

* a topic, a URI-like string that defines the nature of the event
* a set of properties associated to the event

Some properties are defined by the EventAdmin service:

+----------------------------+--------+----------------------------------------+
| Property                   | Type   | Description                            |
+============================+========+========================================+
| event.sender.framework.uid | String | UID of the framework that emitted the  |
|                            |        | event. Useful in remote services.      |
+----------------------------+--------+----------------------------------------+
| event.timestamp            | float  | Time stamp of the event, computed when |
|                            |        | the event is given to EventAdmin       |
+----------------------------+--------+----------------------------------------+

Usage
*****

Instantiation
=============

The EventAdmin service is implemented in ``pelix.services.eventadmin`` bundle,
as a single iPOPO component.
This component must be instantiated programmatically, by using the iPOPO service
and the ``pelix-services-eventadmin-factory`` factory name.

.. code-block:: python
   :linenos:
   
   # Start the framework (with iPOPO)
   framework = pelix.framework.create_framework(['pelix.ipopo.core'])
   framework.start()
   context = framework.get_bundle_context()
   
   # Install & start the EventAdmin bundle
   context.install_bundle('pelix.services.eventadmin').start()
   
   # Get the iPOPO the service
   ipopo_ref, ipopo = get_ipopo_svc_ref(context)
   
   # Instantiate the EventAdmin component
   ipopo.instantiate('pelix-services-eventadmin-factory', 'EventAdmin', {})
   
   # ...

The EventAdmin component accepts the following property as a configuration:

+--------------+---------------+----------------------------------------+
| Property     | Default value | Description                            |
+==============+===============+========================================+
| pool.threads | 10            | Number of threads in the pool used for |
|              |               | asynchronous delivery                  |
+--------------+---------------+----------------------------------------+

Interfaces
==========

EventAdmin service
------------------

The EventAdmin service provides the ``pelix.services.eventadmin`` specification,
which defines the following methods:

+-------------------------+----------------------------------------------+
| Method                  | Description                                  |
+=========================+==============================================+
| post(topic, properties) | Adds an event to asynchronous delivery queue |
+-------------------------+----------------------------------------------+
| send(topic, properties) | Notifies the event handlers synchronously    |
+-------------------------+----------------------------------------------+

Both methods get the topic as first parameter, which must be a URI-like string,
e.g. *sensor/temperature/changed*, and a dictionary as second parameter, which
can be None.

When sending an event, each handler is notified with a different copy of the
property dictionary, avoiding to propagate changes done by a handler.


EventHandler service
--------------------

An event handler must provide the ``pelix.services.eventadmin.handler``
specification, which defines by the following method:

+---------------------------------+-------------------------------------+
| Method                          | Description                         |
+=================================+=====================================+
| handle_event(topic, properties) | The handler is notified of an event |
+---------------------------------+-------------------------------------+

.. warning:: Events sent using the post() are delivered from another thread.
   It is unlikely but possible that sometimes the handle_event() method may be
   called whereas the handler service has been unregistered, for example after
   the handler component has been invalidated.
   
   It is therefore recommended to check that the injected dependencies used in
   this method are not None before handling the event.

An event handler must associate at least one the following properties to its
service:

+--------------+-----------------+---------------------------------------------+
| Property     | Type            | Description                                 |
+==============+=================+=============================================+
| event.topics | List of strings | A list of strings that indicates the topics |
|              |                 | the topics this handler expects. EventAdmin |
|              |                 | supports "file name" filters, i.e. with     |
|              |                 | **\*** or **?** jokers.                     |
+--------------+-----------------+---------------------------------------------+
| event.filter | String          | A LDAP filter string that will be tested on |
|              |                 | the event properties.                       |
+--------------+-----------------+---------------------------------------------+


Example
=======

In this example, a component will publish an event when it is validated or
invalidated.
These events will be:

* *example/publisher/validated*
* *example/publisher/invalidated*

The event handler component will provide a service with a topic filter that
accepts both topics: *example/publisher/\**

Publisher
---------

The publisher requires the EventAdmin service, which specification is defined
in the ``pelix.services`` module.

.. code-block:: python
   :linenos:
   
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
-------

The event handler has no dependency requirement.
It has to provide the EventHandler specification, which is defined in the
``pelix.services`` module.

.. code-block:: python
   :linenos:
   
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
**************

It is possible to send events from the Pelix shell, after installing the
``pelix.shell.eventadmin`` bundle.

This bundle defines two commands, in the ``event`` scope:

+---------------------------------------+------------------------------------+
| Command                               | Description                        |
+=======================================+====================================+
| post <topic> [<property=value> [...]] | Posts an event on the given topic, |
|                                       | with the given properties          |
+---------------------------------------+------------------------------------+
| send <topic> [<property=value> [...]] | Sends an event on the given topic, |
|                                       | with the given properties          |
+---------------------------------------+------------------------------------+

Here is a sample shell session, considering the sample event handler above has
been started.
It installs and start the EventAdmin shell bundle:

.. code-block:: console
   
   $ install pelix.shell.eventadmin
   10
   $ start 10
   $ event.send example/publisher/activated name=foobar
   Got a example/publisher/activated from foobar at 1369125501.028135
