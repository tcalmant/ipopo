.. OSGi R7 Remote Services between Python and Java

OSGi R7 Remote Services between Python and Java
###################

:Authors: Scott Lewis, Thomas Calmant

Introduction
============
This tutorial shows how to launch and use the sample application for `OSGi R7
Remote Services Admin (RSA) between Python and Java <https://wiki.eclipse.org/OSGi_R7_Remote_Services_between_Python_and_Java>`_.  
This sample shows
how to use the iPOPO RSA impl to export and/or import remote
services from/to a OSGi/Java process to a Python iPOPO process.   

Requirements
============
This sample requires Python 3 and launching the Java sample
prior to proceeding with Starting the Python Sample below.

This `ECF tutorial page <https://wiki.eclipse.org/OSGi_R7_Remote_Services_between_Python_and_Java>`_ describes how to launch the Java-side sample.   
One can `start via Bndtools project template <https://wiki.eclipse.org/OSGi_R7_Remote_Services_between_Python_and_Java#Launching_via_Bndtools_Project_Template>`_, or `start via Apache Karaf <https://wiki.eclipse.org/OSGi_R7_Remote_Services_between_Python_and_Java#Launching_via_Apache_Karaf>`_

Once the Java sample has been successfully started, proceed below.

Starting the Python Sample
==========================

In the ipopo home directory, start the top-level script for this sample:

.. code-block:: console

    $ samples/run_rsa_py4java.py

or

.. code-block:: console

    $ python samples/run_rsa_py4java.py

This should produce output to the console like the following:

.. code-block:: console

    ** Pelix Shell prompt **
    Python IHello service consumer received sync response: Java says: Hi PythonSync, nice to see you
    done with sayHelloAsync method
    done with sayHelloPromise method
    async response: JavaAsync says: Hi PythonAsync, nice to see you
    promise response: JavaPromise says: Hi PythonPromise, nice to see you

This output indicates that 

1) The Python process connected to the Java process using the Py4j distribution provider
2) RSA discovered and imported the Java-exported HelloImpl service
3) RSA created a Python proxy for the IHello service instance hosted from Java
4) iPOPO injected the IHello proxy into the sample consumer by setting the self._helloservice requirement to the IHello proxy
5) Calling the _validate method of the RemoteHelloConsumer class (in samples/rsa/helloconsumer.py)

.. code-block:: python

	from pelix.ipopo.decorators import ComponentFactory, Instantiate, Requires, Validate
	
	@ComponentFactory("remote-hello-consumer-factory")
	# The '(service.imported=*)' filter only allows remote services to be injected
	@Requires("_helloservice", "org.eclipse.ecf.examples.hello.IHello",
	          False, False, "(service.imported=*)", False)
	@Instantiate("remote-hello-consumer")
	class RemoteHelloConsumer(object):
	
	    def __init__(self):
	        self._helloservice = None
	        self._name = 'Python'
	        self._msg = 'Hello Java'
	
	    @Validate
	    def _validate(self, bundle_context):
	        # call it!
	        resp = self._helloservice.sayHello(self._name + 'Sync', self._msg)
	        print(
	            "{0} IHello service consumer received sync response: {1}".format(
	                self._name,
	                resp))
	        # call sayHelloAsync which returns Future and we add lambda to print
	        # the result when done
	        self._helloservice.sayHelloAsync(
	            self._name + 'Async',
	            self._msg).add_done_callback(
	            lambda f: print(
	                'async response: {0}'.format(
	                    f.result())))
	        print("done with sayHelloAsync method")
	        # call sayHelloAsync which returns Future and we add lambda to print
	        # the result when done
	        self._helloservice.sayHelloPromise(
	            self._name + 'Promise',
	            self._msg).add_done_callback(
	            lambda f: print(
	                'promise response: {0}'.format(
	                    f.result())))
	        print("done with sayHelloPromise method")

When the _validate method is called by iPOPO, it calls the self._helloservice.sayHello synchronous method and 
prints out the result (resp) to the console:

.. code-block:: python

    @Validate
    def _validate(self, bundle_context):
        # call it!
        resp = self._helloservice.sayHello(self._name + 'Sync', self._msg)
        print(
            "{0} IHello service consumer received sync response: {1}".format(
                self._name,
                resp))

The print in the code above is responsible for the console output

.. code-block:: console

    Python IHello service consumer received sync response: Java says: Hi PythonSync, nice to see you    

Then the sayHelloAsync method is called

.. code-block:: python

    self._helloservice.sayHelloAsync(
        self._name + 'Async',
        self._msg).add_done_callback(
        lambda f: print(
            'async response: {0}'.format(
                f.result())))
    print("done with sayHelloAsync method")

The print is responsible for the console output

.. code-block:: console

    done with sayHelloAsync method
    
Then the sayHelloPromise method is called

.. code-block:: python

    self._helloservice.sayHelloPromise(
        self._name + 'Promise',
        self._msg).add_done_callback(
        lambda f: print(
            'promise response: {0}'.format(
                f.result())))
    print("done with sayHelloPromise method")
   
Resulting in the console output

.. code-block:: console

    done with sayHelloPromise method
     
Note that the async response and promise response are received after the print('done with sayHelloPromise')
statement   Once the remote (Java) call is completed, the lambda expression callback is executed via Future.add_done_callback.  
This results in the output ordering of:

.. code-block:: console

    Python IHello service consumer received sync response: Java says: Hi PythonSync, nice to see you
    done with sayHelloAsync method
    done with sayHelloPromise method
    async response: JavaAsync says: Hi PythonAsync, nice to see you
    promise response: JavaPromise says: Hi PythonPromise, nice to see you
    
The 'done...' prints out prior to the execution of the print in the lambda expression callback passed to `Future.add_done_callback <https://docs.python.org/3/library/concurrent.futures.html>`_.

Note that at the same time as the Python-side console output above, in the Java console this will appear:

.. code-block:: console

    Java.sayHello called by PythonSync with message: 'Hello Java'
    Java.sayHelloAsync called by PythonAsync with message: 'Hello Java'
    Java.sayHelloPromise called by PythonPromise with message: 'Hello Java'

This is the output from the Java HelloImpl implementation code...e.g. 

.. code-block:: java

    public String sayHello(String from, String message) {
        System.out.println("Java.sayHello called by "+from+" with message: '"+message+"'");
        return "Java says: Hi "+from + ", nice to see you";
    }
    
Exporting a Hello implementation from Python to Java
=============================

In the iPOPO console, give the following command to register and export a 
IHello service instance from Python impl to Java consumer.

.. code-block:: console

    $ start samples.rsa.helloimpl_py4j
    
This should result in the Python console output

.. code-block:: console

    $ start samples.rsa.helloimpl_py4j
    Bundle ID: 18
    Starting bundle 18 (samples.rsa.helloimpl_py4j)...
    Python.sayHello called by: Java with message: 'Hello Python'
    Python.sayHelloAsync called by: JavaAsync with message: 'Howdy Python'
    Python.sayHelloPromise called by: JavaPromise with message: 'Howdy Python'

Here is the Python hello impl (samples/helloimpl_py4j.py))

.. code-block:: python

	from pelix.ipopo.decorators import Instantiate, ComponentFactory, Provides
	from samples.rsa.helloimpl import HelloImpl
	
	@ComponentFactory('helloimpl-py4j-factory')
	# Provides IHello interface as specified by Java interface.
	@Provides('org.eclipse.ecf.examples.hello.IHello')
	# See <a
	# href="https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/examples/org.eclipse.ecf.examples.hello/src/org/eclipse/ecf/examples/hello/IHello.java">IHello
	# service interface</a>
	@Instantiate('helloimpl-py4j', {'service.exported.interfaces': '*',  # Required for export
	                                # Required to use py4j python provider for
	                                # export
	                                'service.exported.configs': 'ecf.py4j.host.python',
	                                # Required to use osgi.async intent
	                                'service.intents': ['osgi.async'],
	                                'osgi.basic.timeout': 30000})  # Timeout associated with remote calls (in ms)
	class Py4jHelloImpl(HelloImpl):
	    '''
	    All method impls handled by HelloImpl superclass.  See samples.rsa.helloimpl module.
	    '''
	    pass

and here is the HelloImpl superclass (samples/helloimpl.py)

.. code-block:: python

	class HelloImpl(object):
	    '''
	    Implementation of Java org.eclipse.ecf.examples.hello.IHello service interface.
	    This interface declares on normal/synchronous method ('sayHello') and two
	    async methods as defined by the OSGi Remote Services osgi.async intent.  Note
	    that the service.intents property above includes the 'osgi.async' intent.  It
	    also declares a property 'osgi.basic.timeout' which will be used to assure that
	    the remote methods timeout after the given number of milliseconds.
	
	    See the OSGi Remote Services specification at
	
	    https://osgi.org/specification/osgi.cmpn/7.0.0/service.remoteservices.html
	
	    The specification defines the standard properties given above.
	
	    '''
	
	    def sayHello(self, name='Not given', message='nothing'):
	        '''
	        Synchronous implementation of IHello.sayHello synchronous method.  The remote
	        calling thread will be blocked until this is executed and responds
	        '''
	        print(
	            "Python.sayHello called by: {0} with message: '{1}'".format(
	                name, message))
	        return "PythonSync says: Howdy {0} that's a nice runtime you got there".format(
	            name)
	
	    def sayHelloAsync(self, name='Not given', message='nothing'):
	        '''
	        Implementation of IHello.sayHelloAsync.  This method will be executed via
	        some thread, and the remote caller will not block.  This method should return
	        either a String result (since the return type of IHello.sayHelloAsync is
	        CompletableFuture<String>, OR a Future that returns a python string.  In this case,
	        it returns the string directly.
	        '''
	        print(
	            "Python.sayHelloAsync called by: {0} with message: '{1}'".format(
	                name,
	                message))
	        return "PythonAsync says: Howdy {0} that's a nice runtime you got there".format(
	            name)
	
	    def sayHelloPromise(self, name='Not given', message='nothing'):
	        '''
	        Implementation of IHello.sayHelloPromise.  This method will be executed via
	        some thread, and the remote caller will not block.
	        '''
	        print(
	            "Python.sayHelloPromise called by: {0} with message: '{1}'".format(
	                name,
	                message))
	        return "PythonPromise says: Howdy {0} that's a nice runtime you got there".format(
	            name)

You can now go back to see other :ref:`Tutorials` or take a look at the
:ref:`refcards`.
