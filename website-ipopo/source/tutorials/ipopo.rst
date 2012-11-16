.. Tutorial iPOPO

iPOPO: the component framework
##############################

This tutorial shows how to work with the iPOPO framework.


Concepts
********

iPOPO is a service-oriented component model.

A component is an object with a life-cycle, requiring services and providing
ones, and associated to properties.
The code of a component is reduced to its functional purpose: life-cycle,
dependencies, etc, are handled by iPOPO.

In iPOPO, a component is an instance of component factory, i.e. a Python class
manipulated with the iPOPO decorators.
The usage of decorators is described in :ref:`decorators`.
The manipulation process is explained in :ref:`manipulation`.


Component life cycle
====================

The component life cycle is handled by an instance manager created by the iPOPO
service.

This instance manager will inject control methods, inject dependencies,
register the component services.
All changes will be notified to the component using the callback methods it
declared.


.. figure:: /_static/component_lifecycle.png
   :scale: 50%
   :alt: Component life cycle
   :align: center
   
   Component life cycle

+--------------+---------------------------------------------------------------+
| State        | Description                                                   |
+==============+===============================================================+
| INSTANTIATED | The component has been instantiated.                          |
|              | Its constructor has been called.                              |
+--------------+---------------------------------------------------------------+
| VALIDATED    | All required dependencies have been injected.                 |
|              | All services provided by the component have been registered.  |
+--------------+---------------------------------------------------------------+
| KILLED       | The component has been invalidated and won't be usable again. |
+--------------+---------------------------------------------------------------+


Callback methods
================

A component can defined four callback methods, using decorators.
The name of the methods can be anything but a *private* method (prefix with
two underscores `__`)

+-------------+------------------------+---------------------------------------+
| Decorator   | Signature              | Description                           |
+=============+========================+=======================================+
| @Validate   | ``def validate(self,   | The component is validating: all its  |
|             | context)``             | dependencies have been injected.      |
|             |                        | The component will go in VALIDATED    |
|             |                        | state if this method doesn't raise an |
|             |                        | exception.                            |
+-------------+------------------------+---------------------------------------+
| @Invalidate | ``def invalidate(self, | The component is invalidating: its    |
|             | context)``             | services are still there.             |
|             |                        | The component will go in INVALIDATED  |
|             |                        | state even if an exception is raised. |
+-------------+------------------------+---------------------------------------+
| @Bind       | ``def bind(self,       | This method is called after a         |
|             | service, reference)``  | dependency has been injected.         |
+-------------+------------------------+---------------------------------------+
| @Unbind     | ``def unbind(self,     | This method is called before a        |
|             | service,reference)``   | dependency is removed.                |
+-------------+------------------------+---------------------------------------+


Install the iPOPO bundle
************************

iPOPO is a bundle, named ``pelix.ipopo.core``.
It needs to be installed in a Pelix framework instance, like any bundle.

.. code-block:: python
   :linenos:

   # Import the Pelix module
   import pelix.framework as pelix
   
   # Start the framework
   framework = pelix.FrameworkFactory.get_framework()
   framework.start()   
   
   # Get the bundle context
   context = framework.get_bundle_context()
   
   # Install and iPOPO the bundle
   bundle_id = context.install_bundle("pelix.ipopo.core")
   bundle = context.get_bundle(bundle_id)
   bundle.start()


Get the iPOPO service
*********************

If you use the ``@Instantiate`` decorator to start all your components, you
might not need to use the iPOPO service itself.


There are two equivalent ways to retrieve the iPOPO service:

* the standard Pelix way:

  .. code-block:: python
     :linenos:

     # Get the iPOPO service specification
     from pelix.ipopo.constants import IPOPO_SERVICE_SPECIFICATION

     # Find the service (context is a BundleContext)
     ipopo_ref = context.get_service_reference(IPOPO_SERVICE_SPECIFICATION)
     if ipopo_ref is None:
          print("iPOPO service not present")
          return

     try:
          # Use it
          ipopo = context.get_service(ipopo_ref)

     except pelix.framework.BundleException as ex:
          print("Error retrieving the iPOPO service: {0}".format(ex))
          return


* with the iPOPO utility method, which wraps the Pelix way:

  .. code-block:: python
     :linenos:

     # Get the iPOPO utility method
     from pelix.ipopo.constants import get_ipopo_svc_ref

     # Get the service (context is a BundleContext)
     ipopo = get_ipopo_svc_ref(context)
     if ipopo is None:
          print("iPOPO service not found")


.. _decorators:

Write a component factory
*************************

The principle of iPOPO is to handle the life cycle of components which are
instances of factory classes.

Here is a sample factory class:

.. code-block:: python
   :linenos:
   
   from pelix.ipopo.decorators import *
   import pelix.ipopo.constants as constants

   # The component manipulator
   @ComponentFactory(name="MyIncrementerFactory")
   # Tell we want an instance of this factory
   @Instantiate("MyIncrementer")
   # An injected property field, here the component instance name
   @Property("name", constants.IPOPO_INSTANCE_NAME)
   # A component specific property, with a default value
   @Property("thread_safe", "thread.safe", False)
   @Property("usable", "usable", True)
   @Provides(specifications="my.incrementer")
   class ComponentIncrementer(object):
       """
       Sample Incrementer
       """
       def change(self, usable):
           """
           Changes the usable property
           """
           self.usable = usable 

       def increment(self):
           """
           Service implementation
           """
           self.count += 1
           return self.count
       
       @Validate
       def validate(self, context):
           """
           Component validated
           """
           self.count = 0
           print "%s: Ready..." % self.name
         
       @Invalidate
       def invalidate(self, context):
           """
           Component invalidated
           """
           self.count = 0
           print "%s: Gone." % self.name


* Lines 5-13: the decorators manipulates the class

  +-------------------+---------------------------------------------------+
  | Decorator         | Description                                       |
  +===================+===================================================+
  | @ComponentFactory | Finalizes the manipulation                        |
  +-------------------+---------------------------------------------------+
  | @Instantiate      | Tells iPOPO to instantiate the component          |
  |                   | "MyIncrementer" as soon as the factory is loaded  |
  +-------------------+---------------------------------------------------+
  | @Property         | Defines the properties of the component and their |
  |                   | associated field                                  |
  +-------------------+---------------------------------------------------+
  | @Provides         | Defines the service provided by the component     |
  +-------------------+---------------------------------------------------+

* Lines 14-30: Implementation of the component

* Lines 31-45: Definition of callback methods, called when iPOPO validates or
  invalidates the component


When the bundle containing this class will be started, its factories will be
loaded and the indicated component will be instantiated, if possible.

.. code-block:: python
   :linenos:
   
   >>> bid = context.install_bundle("test_ipopo")
   >>> bundle = context.get_bundle(bid)
   >>> bundle.start()
   MyIncrementer: Ready...


Use the iPOPO service
*********************

The iPOPO service provides four important methods:

* ``register_factory(context, factory_class)``: registers the given
  **manipulated** class as a factory. The name of the factory is found in
  the manipulation attributes.
  If the class has not been manipulated or if the factory name has already
  been used, an error is raised.
  The given bundle context will be used for services registration and retrieval.

* ``unregister_factory(factory_name)``: unregisters the factory of the given
  name.

* ``instantiate(factory_name, name, properties)``: starts a new component using
  the given factory, with the given name and properties.
  The instantiation fails if a component with the same name already exists.

  .. code-block:: python
     :linenos:

     >>> # Starts a new incrementer
     >>> compo = ipopo.instantiate("MyIncrementerFactory", "incr2",
                                   {"usable": False})
     MyIncrementer: Ready...
     >>> compo.increment()
     1

* ``kill(name)``: destroys the component with the given name.
  The component is invalidated then removed from the iPOPO registry.

  .. code-block:: python
     :linenos:

     >>> # Invalidates the started incrementer
     >>> ipopo.kill("incr2")
     MyIncrementer: Gone.


Component dependencies
**********************

Component dependencies is based on services, provided by ones and consumed by
others.

Validation and invalidation
===========================

A component is validated when all of its required dependencies have been
injected, and is invalidated when one of its required dependencies is gone.

Both methods take only one parameter: the context of the bundle that
registered the component.

In the following example, the consumer requires an incrementer:

.. code-block:: python
   :linenos:

   @ComponentFactory("ConsumerFactory")
   @Requires("svc", "my.incrementer", spec_filter="(usable=True)")
   class ConsumerFactory(object):
   
      @Validate
      def validate(self, context):
          print "Start:", self.svc.increment()
      
      @Invalidate
      def invalidate(self, context):
          print "Stopped:", self.svc.increment()
      

The service is injected before the component is validated and after it is
invalidated. That way, it can be used by the consumer can use it a last time
when the service or the consumer is invalidated.

A sample run, considering all bundles are started:

.. code-block:: python
   :linenos:

   >>> # Remember, a component named "MyIncrementer" has automatically been
   >>> # started by iPOPO (@Instantiate decorator on the factory)
   >>> consumer = ipopo.instantiate("ConsumerFactory", "consumer")
   Start: 1
   
   >>> # Start the second incrementer
   >>> incr2 = ipopo.instantiate("MyIncrementerFactory", "incr2",
                                 {"usable": True})
   incr2: Ready...
   
   >>> # Set the first incrementer unusable: the injection will be updated.
   >>> # As the injection is not optional, the consumer will be invalidated
   >>> # during the re-injection
   >>> consumer.svc.change(False)
   Stopped: 2
   Start: 1
   
   >>> # Set the second incrementer unusable, it will invalidate the consumer
   >>> incr2.change(False)
   Stopped: 2
   
   >>> # Set the second incrementer usable again
   >>> incr2.change(True)
   Start: 3


Bind  and unbind
================

Additionally, a component can be notified when a dependency (required or not)
has been injected, using a bind method, or removed, using an unbind method.

Both methods take two parameters:

* the injected service object, to work directly with it
* the ServiceReference object for the injected service, to have access to the
  service information, properties, etc.

If the injection allows to validate the component, the bind method is called
before the validation one.
Conversely, if the injection implies to invalidate the component, the unbind
method is called after the invalidation one.

If the requirement is an aggregation, the bind and unbind methods are called
for each injected service.

Here is the previous service consumer, printing a line each time a service is
bound or unbound:

.. code-block:: python
   :linenos:

   @ComponentFactory("ConsumerFactory")
   @Requires("svc", "my.incrementer", spec_filter="(usable=True)")
   class ConsumerFactory(object):
   
      @Validate
      def validate(self, context):
          print "Start:", self.svc.increment()
      
      @Invalidate
      def invalidate(self, context):
          print "Stopped:", self.svc.increment()
      
      @Bind
      def bind(self, service, reference):
          print "Bound to", reference.get_property("instance.name")
      
      @Unbind
      def unbind(self, service, reference):
          print "Component lost", reference.get_property("instance.name")

          
Provide a service
*****************

.. todo:: @Provides + service controller
