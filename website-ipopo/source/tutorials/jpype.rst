.. Run a JVM inside a Pelix process

Run a Java OSGi framework inside a Pelix process
################################################

Description
***********

This tutorial shows how to load a Java Virtual Machine (JVM) inside a Python
process using jPype.
Then, it shows how to run an OSGi framework inside the loaded JVM and how to
share services between Pelix and OSGi, and vice versa.

.. note:: This is not an OSGi tutorial, you might take a look on
   `Felix OSGi tutorials <http://felix.apache.org/site/apache-felix-osgi-tutorial.html>`_
   before following this tutorial.

Requirements
************

This tutorial has been written on a Fedora 18 machine, using Java OpenJDK 1.7.0.

As it is a compiled extension, you also need to have installed:

* a C++ compiler (*gcc-c++*)
* the Java development files (JDK packages should have the required files)
  
  * a well defined ``JAVA_HOME`` environment property

* the Python development files (*python-dev*)

jPype
=====

jPype is a Python module, written part in C, that uses JNI
(Java Native Interface) to interact with a Java Virtual Machine loaded inside
the Python process.

.. note:: The Oracle/Sun Java virtual machine have a bogus behavior: the
   JVM shutdown is not clean enough to allow a second JVM to be create in the
   same process afterwards. 

.. note:: **Not tested:** You might only have to download the setup executable
   for Windows


#. Download the latest version of the sources of jPype on sourceforge.net:
   `JPype-0.5.4.2.zip <http://sourceforge.net/projects/jpype/files/JPype/0.5.4/>`_

#. Extract it
#. Update your JAVA_HOME environment property

   .. code-block:: console
   
      $ export JAVA_HOME=/usr/lib/jvm/java-1.7.0-openjdk.x86_64

#. Compile and install the module:

   .. code-block:: console
   
      $ python setup.py build
      $ su -c 'python setup.py install'


Run a JVM with jPype
********************

#. Start the JVM, given it some arguments:

   .. code-block:: python

      import jpype
      jpype.startJVM(jpype.getDefaultJVMPath(), "-Djava.class.path=some_file.jar")


#. Use Java classes

   .. code-block:: python

      # java and javax have an alias in the jPype module
      jpype.java.lang.System.out.prinln("Hi !")
   
      # or use the class loader
      HashMap = jpype._jclass.JClass("java.util.HashMap")
      javaMap = HashMap()
      javaMap.put("answer", 42)
      print("JavaMap=" + javaMap.toString())


#. Shutdown the JVM

   .. code-block:: python

      jpype.shutdownJVM()


   .. warning:: ``jpype.shutdownJVM()`` won't return until all of the Java threads
      have stopped.


A sample jPype usage script is avaialable here:
`jpype_sample.py <../_static/jpype/jpype_sample.py>`_


Run OSGi inside jPype
*********************

.. _start_osgi:

Start a OSGi framework
======================

In this example, we will use the
`Felix OSGi framework <http://felix.apache.org/>`_.
To simplify, we will direcly use the Felix framework factory class name, 
``org.apache.felix.framework.FrameworkFactory``, instead of reading it from the
``/META-INF/services/org.osgi.framework.launch.FrameworkFactory`` file inside
OSGi framework JAR file.

An OSGi framework is created by calling the ``newFramework()`` method of an
instance of a ``FrameworkFactory`` implementation.

.. code-block:: python

   import jpype
   
   # Add the OSGi framework JAR file in the JVM class path
   jar_file = "felix.jar"
   jpype.startJVM(jpype.getDefaultJVMPath(),
                  "-Djava.class.path={0}".format(jar_file))
   
   # Get the framework factory class
   framework_factory_name = "org.apache.felix.framework.FrameworkFactory"
   FrameworkFactory = jpype._jclass.JClass(framework_factory_name)
   factory = FrameworkFactory()
   
   # Prepare some properties (strings only)
   HashMap = jpype._jclass.JClass("java.util.HashMap")
   osgi_props = HashMap()
   osgi_props.put("from.python", "true") 
   
   # Create the framework
   osgi = factory.newFramework(osgi_props)
   
   # Play with it...
   osgi.start()
   context = osgi.getBundleContext()
   print("Execution environement = " \
         + str(context.getProperty('org.osgi.framework.executionenvironment')))

   # ...
   
   # Stop the framework
   osgi.stop()
   
   # Clear the JVM
   jpype.shutdownJVM()


Implementations
===============

This tutorial being about Pelix and not OSGi, I won't explain how to build an
OSGi bundle.
You can take a look to
`Felix OSGi tutorials <http://felix.apache.org/site/apache-felix-osgi-tutorial.html>`_
for more information.

We will develop five bundles:

* A Java API bundle, declaring the signature of te service we will implement
* A Java implementation bundle, providing the service
* A Java consumer bundle, which will use the ``IHelloWorld`` services when they
  appear
* A Python implementation bundle, providing the service in the Java
* A Python consumer bundle, registering a ``ServiceListener`` inside OSGi

Java API
--------

We will consider the following Java service interface:

.. code-block:: java

   package pelix.demo;
   
   public interface IHelloWorld {
      
      /**
       * Prints a nice message on the standard output
       *
       * @param name Name of the guy to greet
       */
      void sayHello(String name);
   }

This must be exported by the API bundle.


Java implementation
-------------------

Simplest thing that can be:

.. code-block:: java

   package pelix.demo.impl;
   
   import pelix.demo.IHelloWorld;
   
   public class HelloWorldImpl implements IHelloWorld {

      public void sayHello(String name) {
         
         System.out.println("Hi " + name + "!");
      }   
   }


Python implementation
---------------------

The Python implementation of the Java service is really simple:

.. code-block:: python

   class HelloWorldImpl(object):
      """
      Java service implemtation
      """
      def sayHello(name):
         """
         Prints Hello
         """
         print("Hello {0} !".format(name))


Providing services in OSGi
==========================

Class path hell
---------------

As Java is a typed language, it is necessary to declare the interface of the
shared Python objects through interfaces.
These interfaces must be available by jPype, i.e. by the top-level class loader.
   
This means that the API bundle must be added to the JVM class path:

.. code-block:: python

   # Creating the JVM: add the API jar file
   java_args = []
   classpath = []
   
   classpath.append(osgi_framework_jar_file)
   classpath.append(api_bundle_jar_file)
   
   # ... format the argument
   java_args.append("-Djava.class.path={0}".format(os.path.pathsep.join(classpath)))
   
   # ... start the JVM
   jpype.startJVM(jpype.getDefaultJVMPath(), *java_args)


The packages provided by this bundle must be added to the OSGi
*system packages*:

.. code-block:: python

   # Constant from the OSGi specification
   FRAMEWORK_SYSTEMPACKAGES_EXTRA = "org.osgi.framework.system.packages.extra"
   
   # List of packages exported, with a version number, in OSGi format
   packages = ["pelix.demo; version=1.0.0"]
   
   # Add the formatted list to the framework properties
   HashMap = jpype._jclass.JClass("java.util.HashMap")
   osgi_props = HashMap()
   osgi_props.put(FRAMEWORK_SYSTEMPACKAGES_EXTRA, ','.join(packages))
   
   # Get the framework factory class
   framework_factory_name = "org.apache.felix.framework.FrameworkFactory"
   FrameworkFactory = jpype._jclass.JClass(framework_factory_name)
   factory = FrameworkFactory() 
   
   # Create the framework
   osgi = factory.newFramework(osgi_props)


Java service
------------

In the activator of the implementation bundle, we have to register the service:

.. code-block:: java

   // ...
   private ServiceRegistration<?> svcReg;
   
   public void start(BundleContext context) {
   
      IHelloWorld instance = new HelloWorldImpl();
      this.svcReg = context.registerService(IHelloWorld.class, instance, null);
   }
   
   public void stop(BundleContext context) {
      this.svcReg.unregister();
      this.svcReg = null;
   }
   
   // ...


Python service
--------------

We will use the same OSGi API, using a framework created like shown in
:ref:`start_osgi`.

.. code-block:: python

   # First: prepare an instance of the implementation to be usable in Java
   python_inst = HelloWorldImpl()
   java_inst = jpype.JProxy("pelix.demo.IHelloWorld", inst=python_inst)
   
   # Register the service (consider osgi a running framework)
   context = osgi.getBundleContext()
   svc_reg = context.registerService("pelix.demo.IHelloWorld", java_inst, None)
   
   # ...
   
   # Unregister it
   svc_reg.unregister()
   svc_reg = None


Consume the service
===================

In both cases, we will register a ``ServiceListener`` to the framework.

Java consumer
-------------

.. code-block:: java

   // ... package, imports, ...

   public class Consumer implements ServiceListener {
   
      /** The bundle context */
      private BundleContext context;
      
      public Consumer(BundleContext bundleContext) {
         context = bundleContext;
      }
   
      /**
       * ServiceListener API
       */
      public void serviceChanged(ServiceEvent event) {
         if(event.getType() == ServiceEvent.REGISTERED) {
            // Yes... the implementation bundles must come after this one has
            // been started
            
            // Get the service
            ServiceReference<?> ref = event.getServiceReference();
            IHelloWord svc = (IHelloWorld) context.getService(ref);
            
            // Use it
            svc.sayHello("World from Java");
            
            // Release it
            context.ungetService(ref);
         }
      }
   }

An instance of this class must be registered to the framework, in the activator
of the consuming bundle, using:

.. code-block:: java

   bundleContext.addServiceListener(new Consumer(bundleContext),
                                    "(objectClass=pelix.demo.IHelloWorld)");


Python consumer
---------------

Here is the consumer implementation, having the same signature than the Java
one.

.. code-block:: python

   class Consumer(object):
      """
      Python servlice listener, registered in Python
      """
      def __init__(self, context):
         self.context = context
      
      def serviceChanged(event):
         """
         Called by OSGi on service events
         """
         if event.getType() == event.REGISTERED:
            ref = event.getServiceReference()
            svc = self.context.getService(ref)
            
            svc.sayHello("World from Python")
            
            self.context.ungetService(ref)


The registration of the service listener in the OSGi world needs the creation
of a proxy:

.. code-block:: python

   # Prepare the consumer object and its Java proxy
   consumer = Consumer()
   consumer_proxy = jpype.JProxy("org.osgi.framework.ServiceListener", inst=consumer)
   
   # Register it
   context = osgi.getBundleContext()
   context.addServiceListener(consumer_proxy, "(objectClass=pelix.demo.IHelloWorld)")

If you install both implementation bundles (Python and Java) after having
started the consumers, both consumer will call both implementations.
