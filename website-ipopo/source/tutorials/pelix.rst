.. Tutorial Pelix

Pelix: the SOA framework
########################

This tutorial shows how to start the framework, how to work with bundles and
how to work with services.
If you are only interested in iPOPO, you can skip the last section.


Concepts
********

Pelix is the base service-oriented architecture (SOA) framework that is used
by iPOPO.
It defines two main concepts: service and bundle.

Service
=======

A *service* is an object that is registered for given specifications and
associated to some properties.

The bundle that registers the service must keep the *service registration*
object, which represents the service registration in the framework.
It allows to modify the service properties and to unregister the service.
This object shall not be accessible by other bundles/services.
All services must be unregistered when their bundle is stopped.


A consumer can request a service from the framework that matches a specification
and a set of properties. The framework will return a *service reference*, which
provides a read-only access to the description of its associated service:
properties, registering bundle, bundles using it...


Bundle
======

A bundle is a Python module installed using a Pelix Framework instance.

All bundles have a unique symbolic name (their module name) and an integer
identifier that is unique for a framework instance.

.. note:: The framework itself is always the framework with ID 0.


Bundle life cycle
-----------------

The bundle life cycle depends on framework's one, but must be handled
programmatically.

.. figure:: /_static/bundle_lifecycle.png
   :scale: 50%
   :alt: Bundle life cycle
   :align: center
   
   Bundle life cycle

+-------------+---------------------------------------------------------+
| State       | Description                                             |
+=============+=========================================================+
| INSTALLED   | The module has been correctly imported.                 |
|             | Its activator has not yet been called.                  |
+-------------+---------------------------------------------------------+
| ACTIVE      | The bundle has been called and didn't raised any error. |
+-------------+---------------------------------------------------------+
| UNINSTALLED | The bundle is being removed of the framework.           |
+-------------+---------------------------------------------------------+


Bundle activator
----------------

A bundle activator is an object with a ``start()`` and a ``stop()`` method,
which are called by the framework according to the bundle life-cycle.

The activator is always the variable ``activator`` at the module-level.
It shall be the only instantiation done during the module loading.

Bundle context
--------------

A context is associated to each bundle, to allow it to interact with the
framework.

It must be used to register and request services, to request framework state,
etc.

The API of the bundle context can found here:
`BundleContext <http://ipopo.coderxpress.net/api/pelix.framework.BundleContext-class.html>`_.

Start the framework
*******************

To create a Pelix instance, you need to use the ``FrameworkFactory`` class.
A framework can be instantiated with a set of properties which will be
then accessible by bundles and services.

.. important:: Currently, it is not possible to run two Pelix frameworks in the
   same Python interpreter instance, as it would cause problems to manage
   modules versionning.

Be sure to destroy the framework before starting a new one. Calling
``get_framework()`` twice without calling ``delete_framework()`` will return the
same framework instance.

.. code-block:: python
   :linenos:
   
   # Import the Pelix module
   import pelix.framework as pelix
   # Start the framework with the given properties
   framework = pelix.FrameworkFactory.get_framework({'debug': True})
   # Start the framework
   framework.start()
   # Stop the framework
   framework.stop()
   # Destroy it
   pelix.FrameworkFactory.delete_framework(framework)


The framework instance is considered as a bundle, with a context,
life-cycle, ... and can be used as any other bundles by the framework starter.


Wait for the framework to stop
==============================

In multithreaded applications, it is possible to wait for the framework
to completely stop using the ``Framework.wait_for_stop(timeout)`` method.

The method will block until the framework has stopped or if the time out is
reached.
The time out is given in seconds, and None means that method will wait forever.

.. code-block:: python
   :linenos:
   
   # Import the Pelix module
   import pelix.framework as pelix
   # Start the framework with the given properties
   framework = pelix.FrameworkFactory.get_framework({'debug': True})
   
   # [...] Start a thread / install bundles / ... [...]
    
   # Wait the framework to stop
   framework.wait_for_stop()
   print("Framework stopped.")


The framework can be stopped in two ways:

* By calling the ``stop()`` method of the framework

* By raising a ``FrameworkException`` with the ``needs_stop`` flag set up
  in a bundle activator, while the framework is calling it.


Work with bundles
*****************

A bundle is a Python module, loaded by Pelix. It can have an activator, i.e. an
instance of a class that has a ``start()`` and a ``stop()`` method.
This instance must exactly be named ``activator``.

Here is a bundle with an activator:

.. code-block:: python
   :linenos:
   
   #!/usr/bin/python
   #-- Content-Encoding: utf-8 --
   
   def foo():
       ''' Some method '''
       print("Foo !")
   
   class Bar(object):
       ''' Some class '''
       pass
   
   class Activator(object):
       '''
       The bundle activator
       '''
       def __init__(self):
           '''
           The activator constructor. No functional code should be here
           '''
           self.context = None
           print("Activator initialization")
       
       def start(self, context):
           '''
           This method is called when the bundle is started. Registrations
           should occur here.
           '''
           # Store the bundle context
           self.context = context
           print("Bundle started")
       
       def stop(self, context):
           '''
           This method is called when the bundle is stopped. Unregistrations
           should occur here.
           '''
           # Clean up the references
           self.context = None
           print("Bundle stopped")

   # This is the activator module variable, that is used by Pelix to start and
   # stop the bundle.
   activator = Activator()

.. note:: There should be no executable code at module-level except the creation
   of the activator variable.
   Nothing should initiated before the start() method is called, and nothing
   should stay active after the stop() method has been called.


If the sample bundle is saved in a file called *simple.py*, visible in the
Python path, then it can be loaded in Pelix with the following snippet:

.. code-block:: python
   :linenos:

   >>> # Import the Pelix module
   >>> import pelix.framework as pelix
   >>> # Start the framework with the given properties
   >>> framework = pelix.FrameworkFactory.get_framework({'debug': True})
   >>> framework.start()
   
   >>> # Get the bundle context of the framework
   >>> context = framework.get_bundle_context()
   >>> # Install our bundle
   >>> bundle_id = context.install_bundle("simple")
   Activator initialization
   
   >>> # Start the bundle
   >>> bundle = context.get_bundle(bundle_id)
   >>> bundle.start()
   Bundle started
   
   >>> # Get the Python module associated to the bundle
   >>> module = bundle.get_module()
   >>> module.foo()
   Foo !
   
   >>> # Update the module (stop, reload, start)
   >>> bundle.update()
   Bundle stopped
   Activator initialization
   Bundle started
   
   >>> # The module object is reloaded in-place
   >>> module.foo()
   Foo !
   
   >>> # Stop the framework, the bundle will be stopped automatically
   >>> framework.stop()
   Bundle stopped
   
   >>> # Destroy the framework
   >>> pelix.FrameworkFactory.delete_framework(framework)


Work with services
******************

Services should be registered and unregistered by the bundle activator or by
a service.
When a bundle is stopped, the framework automatically unregisters the
corresponding services.

Register a service
==================

A service is registered for one or more specifications and with some properties.
The registrar stores a ServiceRegistration object, which will be used later for
unregistration.

.. code-block:: python
   :linenos:

   #!/usr/bin/python
   #-- Content-Encoding: utf-8 --
   import threading

   class Service(object):
      """
      A service implementation
      """
      def __init__(self):
         """ Constructor """
         self.count = 0
      
      def increment(self):
         """
         A service method
         """
         self.count += 1
         return self.count

   class ServiceLocked(object):
      """
      A service implementation
      """
      def __init__(self):
         """ Constructor """
         self.count = 0
         self.lock = threading.Lock()
      
      def increment(self):
         """
         A service method
         """
         with self.lock:
            self.count += 1
            return self.count

   class Activator(object):
      """
      The bundle activator class
      """
      def start(self, context):
         """
         Called by the framework when the bundle is started
         
         :param context: The bundle context
         """
         # Instantiate the services implementations
         self.svc = Service()
         self.svc2 = ServiceLocked()
         
         # Register them
         self.reg1 = context.register_service("my.incrementer", self.svc,
                                              {"thread.safe": False})
         self.reg2 = context.register_service("my.incrementer", self.svc2,
                                              {"thread.safe": True})
     
     
      def stop(self, context):
         """
         Called by the framework when the bundle is stopped
         
         :param context: The bundle context
         """
         # Unregister the services
         self.reg1.unregister()
         self.reg2.unregister()
         
         # Clean up the references
         self.svc = None
         self.svc2 = None
         self.reg1 = None
         self.reg2 = None

   activator = Activator()

For the next part, we will consider that the above code is stored in a Python
module named *service_provider*.


Consume a service
=================

To consume a service, the first thing to do is to enumerate the existing
services registered in Pelix that corresponds to a required specification and
to a property filter: the result will be a list of ServiceReference objects.
Then Pelix can return the service instance associated to a service reference.

When a consumer doesn't need a service anymore, it must release the reference
using the ``unget_service()`` method of its bundle context.

.. code-block:: python
   :linenos:

   >>> # Import the Pelix module
   >>> import pelix.framework as pelix
   >>> # Start the framework
   >>> framework = pelix.FrameworkFactory.get_framework()
   >>> framework.start()
   >>> context = framework.get_bundle_context()
   
   >>> # Install the bundle
   >>> bundle_id = context.install_bundle("service_provider")
   >>> bundle = context.get_bundle(bundle_id)
   >>> bundle.start()
   
   >>> # At this point, the services have been registered by the activator
   >>> # Get the last registered increment service
   >>> ref = context.get_service_reference("my.incrementer")
   >>> print(ref)
   ServiceReference(2, 1, ['my.incrementer'])
   >>> print(ref.get_properties())
   {'objectClass': ['my.incrementer'], 'service.id': 2, 'thread.safe': True}
   
   >>> # Get the service
   >>> svc = context.get_service(ref)
   >>> svc.increment()
   1
   
   >>> # Release the service
   >>> context.unget_service(ref)
   >>> ref = None
   >>> svc = None
   
   >>> # Get the last registered service matching specific properties
   >>> ref = context.get_service_reference("my.incrementer",
                                           "(thread.safe=False)")
   >>> print(ref)
   ServiceReference(1, 1, ['my.incrementer'])
   >>> svc = context.get_service(ref)
   >>> svc.increment()
   1
   
   >>> # Get multiple references at once, matching the given filter
   >>> refs = context.get_all_service_references("my.incrementer",
                                                 "(thread.safe=*)")
   >>> [str(ref) for ref in refs]
   ["ServiceReference(2, 1, ['my.incrementer'])",
    "ServiceReference(1, 1, ['my.incrementer'])"]
   
   >>> # References instances are unique in the framework
   >>> ref is refs[1]
   True

   >>> # Stopping the framework will unregister all services
   >>> # References can't be accessed after this point
   >>> framework.stop()
   >>> svc = context.get_service(refs[1])
   pelix.framework.BundleException: Service not found
   (reference: ServiceReference(1, 1, ['my.incrementer']))


Handle events
*************

The framework fires an event when the state of a bundle is modified.
Listeners must register themselves to the framework, using their bundle context,
to be notified when a given kind of event happens.
The listeners are notified with a specific method for each kind of event and
must implemented it.

All listeners exceptions are logged, but doesn't stop the notification loops.


Bundle listeners
================

A bundle listener will be notified of the following events, declared in
``pelix.framework.BundleEvent``.

A ``BundleEvent`` object provides the following methods:

* ``get_bundle()``: retrieves the Bundle object that caused this event,
* ``get_kind()``: retrieves the kind of bundle event, one of the following:

  +-------------------+---------------------------------------------------+
  | Kind              | Description                                       |
  +===================+===================================================+
  | INSTALLED         | the bundle has just been installed.               |
  +-------------------+---------------------------------------------------+
  | STARTING          | the bundle is about to be activated,              |
  |                   | its activator will be called.                     |
  +-------------------+---------------------------------------------------+
  | STARTED           | the bundle has been successfully started.         |
  +-------------------+---------------------------------------------------+
  | STOPPING          | the bundle is about to be stopped,                |
  |                   | its activator will be called.                     |
  +-------------------+---------------------------------------------------+
  | STOPPING_PRECLEAN | the bundle activator has been called, but not all |
  |                   | of the services may have been unregistered.       |
  +-------------------+---------------------------------------------------+
  | STOPPED           | the bundle has been stopped, all of its services  |
  |                   | have been unregistered.                           |
  +-------------------+---------------------------------------------------+
  | UNINSTALLED       | the bundle has been uninstalled.                  |
  +-------------------+---------------------------------------------------+

Listeners must implement a ``bundle_changed(self, event)`` method, where
``event`` is BundleEvent object.

To (un)register a bundle listener, the bundle context provides the following
methods:

* ``bundle_context.add_bundle_listener(listener)``
* ``bundle_context.remove_bundle_listener(listener)``


Service listeners
=================

A service listener will be notified of the following events, declared in
``pelix.framework.ServiceEvent``.

A ``ServiceEvent`` object provides the following methods:

* ``get_service_reference()``: retrieves the ServiceReference object of the
  service that caused this event,

* ``get_previous_properties()``: retrieves the previous value of the service
  properties, if the event is MODIFIED or MODIFIED_ENDMATCH.

* ``get_type()``: retrieves the kind of bundle event, one of the following:

  +-------------------+-----------------------------------------------+
  | Type              | Description                                   |
  +===================+===============================================+
  | REGISTERED        | the service has just been registered.         |
  +-------------------+-----------------------------------------------+
  | MODIFIED          | the service properties have been modified.    |
  +-------------------+-----------------------------------------------+
  | MODIFIED_ENDMATCH | the service properties have been modified and |
  |                   | does not match the listener filter anymore.   |
  +-------------------+-----------------------------------------------+
  | UNREGISTERING     | the service has been unregistered.            |
  +-------------------+-----------------------------------------------+


Listeners must implement a ``service_changed(self, event)`` method, where
``event`` is ServiceEvent object.

To (un)register a service listener, the bundle context provides the following
methods:

* ``bundle_context.add_service_listener(listener, ldap_filter=None)``.
  Only services that matches the given LDAP filter will be notified to the
  listener.

* ``bundle_context.remove_service_listener(listener)``


Framework stop listeners
========================

A listener can be notified when the framework itself is stopping, before it
stops all its bundles.

Listeners must implement a ``framework_stopping(self)`` method.

To register a framework stop listener, the bundle context provides the
following methods:

* ``bundle_context.add_framework_stop_listener(listener)``
* ``bundle_context.remove_framework_stop_listener(listener)``
