.. Tutorial Pelix

Pelix: the SOA framework
########################

.. todo:: To be completed

Pelix is the base service framework that is used by iPOPO.
It defines two main concepts :

* bundles, the deployment units. A bundle is a Python module installed using
  a Pelix Framework object. It has a life-cycle of its own and it can register
  services to the framework.

* service, an object that is registered for given specifications, associated to
  some properties. A consumer can request a service from the framework that
  matches a specification and a filter on its properties.


This tutorial shows how to start the framework, how to work with the bundles and
how to work with the services.
If you are only interested in iPOPO, you can skip the last section.


Start the framework
*******************

The following snippet shows how to start the Pelix framework.

Currently, it is not possible to run two Pelix frameworks in the same Python
interpreter instance, as it would cause problems to manage modules versionning.

Be sure to destroy the framework before starting a new one. Calling
``get_framework()`` twice without calling ``delete_framework()`` will return the
same framework instance.

.. code-block:: python
   
   >>> # Import the Pelix module
   >>> import pelix.framework as pelix
   >>> # Start the framework with the given properties
   >>> framework = pelix.FrameworkFactory.get_framework({'debug': True})
   >>> # Stop the framework
   >>> framework.stop()
   >>> # Destroy it
   >>> pelix.FrameworkFactory.delete_framework(framework)


Work with bundles
*****************

A bundle is a Python module, loaded by Pelix. It can have an activator, an
instance of a class that has a ``start()`` and a ``stop()`` method.

Here is a simple bundle :

.. code-block:: python
   
   #!/usr/bin/python
   #-- Content-Encoding: utf-8 --
   
   def foo():
       ''' Some method '''
       print "Foo !"
   
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
           print "Activator initialization"
       
       def start(self, context):
           '''
           This method is called when the bundle is started. Registrations
           should occur here.
           '''
           # Store the bundle context
           self.context = context
           print "Bundle started"
       
       def stop(self, context):
           '''
           This method is called when the bundle is stopped. Unregistrations
           should occur here.
           '''
           # Clean up the references
           self.context = None
           print "Bundle stopped"

   # This is the activator module variable, that is used by Pelix to start and
   # stop the bundle.
   activator = Activator()

.. note:: There should be no executable code at module-level except the creation
   of the activator variable.
   Nothing should initiated before the start() method is called, and nothing
   should stay active after the stop() method has been called


If the sample bundle is saved in a file called *simple.py*, visible in the
Python path, then it can be loaded in Pelix with the following snippet :

.. code-block:: python

   >>> # Import the Pelix module
   >>> import pelix.framework as pelix
   >>> # Start the framework with the given properties
   >>> framework = pelix.FrameworkFactory.get_framework({'debug': True})
   
   >>> # Get the bundle context
   >>> context = framework.get_bundle_context()
   >>> # Install the bundle
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
a service. When a bundle is stopped, the framework automatically unregisters the
corresponding services.

Service registration
====================

A service is registered for one or more specifications and with some properties.
The registrar stores a ServiceRegistration object, which will be used later for
unregistration.

.. code-block:: python

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
   
     def start(self, context):
         # Instantiate the services implementations
         self.svc = Service()
         self.svc2 = ServiceLocked()
         
         # Register them
         self.reg1 = context.register_service("my.incrementer", self.svc, \
                                              {"thread.safe": False})
         self.reg2 = context.register_service("my.incrementer", self.svc2, \
                                              {"thread.safe": True})
     
     
     def stop(self, context):
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
to a property filter : the result will be a list of ServiceReference objects.
Then Pelix can return the service instance associated to a service reference.

When a consumer doesn't need a service anymore, it may release the reference
using the ``unget_service()`` method of its bundle context.

.. code-block:: python

   >>> # Import the Pelix module
   >>> import pelix.framework as pelix
   >>> # Start the framework
   >>> framework = pelix.FrameworkFactory.get_framework()
   >>> context = framework.get_bundle_context()
   >>> # Install the bundle
   >>> bundle_id = context.install_bundle("service_provider")
   >>> bundle = context.get_bundle(bundle_id)
   >>> bundle.start()
   
   >>> # At this point, the services have been registered
   >>> # Get the first matching incrementer service
   >>> ref = context.get_service_reference("my.incrementer")
   >>> print ref
   ServiceReference(2, 1, ['my.incrementer'])
   >>> print ref.get_properties()
   {'objectClass': ['my.incrementer'], 'service.id': 2, 'thread.safe': True}
   >>> # Get the service
   >>> svc = context.get_service(ref)
   >>> svc.increment()
   1
   
   >>> # Free the service
   >>> context.unget_service(ref)
   >>> ref = None
   >>> svc = None
   
   >>> # Request a specific service
   >>> ref = context.get_service_reference("my.incrementer",
                                           "(thread.safe=False)")
   >>> print ref
   ServiceReference(1, 1, ['my.incrementer'])
   >>> svc = context.get_service(ref)
   >>> svc.increment()
   1
   
   >>> # Get multiple references at once
   >>> refs = context.get_all_service_references("my.incrementer",
                                                 "(thread.safe=*)")
   >>> [str(ref) for ref in refs]
   ["ServiceReference(2, 1, ['my.incrementer'])", "ServiceReference(1, 1, ['my.incrementer'])"]
   
   >>> # References instances are unique in the framework
   >>> ref is refs[1]
   True

   >>> # Stopping the framework will unregister all services
   >>> # references can't be accessed after this point
   >>> framework.stop()
   >>> svc = context.get_service(refs[1])
   pelix.framework.BundleException: Service not found
   (reference: ServiceReference(1, 1, ['my.incrementer']))
