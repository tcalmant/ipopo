.. Tutorial iPOPO

iPOPO: the component framework
##############################

This tutorial shows how to work with the iPOPO framework.

Install the iPOPO bundle
************************

iPOPO is a simple bundle that has to be installed in a Pelix framework instance.

.. code-block:: python

   >>> # Import the Pelix module
   >>> import pelix.framework as pelix
   >>> # Start the framework
   >>> framework = pelix.FrameworkFactory.get_framework()   
   >>> # Get the bundle context
   >>> context = framework.get_bundle_context()
   
   >>> # Install and start the bundle
   >>> bundle_id = context.install_bundle("pelix.ipopo.core")
   >>> bundle = context.get_bundle(bundle_id)
   >>> bundle.start()
   
   >>> # Get the iPOPO service
   >>> from pelix.ipopo.constants import IPOPO_SERVICE_SPECIFICATION
   >>> ipopo_ref = context.get_service_reference(IPOPO_SERVICE_SPECIFICATION)
   >>> ipopo = context.get_service(ipopo_ref)


Write a component factory
*************************

The principle of iPOPO is to handle the life cycle of components which are
instances of factory classes.

Here is a sample factory class:

.. code-block:: python

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


When the bundle containing this class will be started, its factories will be
loaded and the requested components will be instantiated, if possible.

.. code-block:: python

     >>> bid = context.install_bundle("test_ipopo")
     >>> bundle = context.get_bundle(bid)
     >>> bundle.start()
     MyIncrementer: Ready...


Use the iPOPO service
*********************

The iPOPO service provides three methods:

* ``instantiate(factory_name, name, properties)``: starts a new component from
  the given factory, with the given name and properties. If a component with
  the same name already exists, the instantiation fails.

  .. code-block:: python

     >>> # Starts a new incrementer
     >>> compo = ipopo.instantiate("MyIncrementerFactory", "incr2",
                                   {"usable": False})
     MyIncrementer: Ready...
     >>> compo.increment()
     1

* ``invalidate(name)``: invalidates the component with the given name. This
  is a test method, as the component will be automatically re-validated when a
  new service event will be triggered.

* ``kill(name)``: destroys the component with the given name. The component is
  invalidated then removed from the iPOPO registry.

  .. code-block:: python

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
