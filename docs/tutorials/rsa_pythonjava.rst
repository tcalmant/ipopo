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
services from a OSGi/Java process.   

Requirements
============
This sample requires Python 3

The requirement for running this sample is launching the Java sample 
prior to starting the Python sample.

This `ECF tutorial page <https://wiki.eclipse.org/OSGi_R7_Remote_Services_between_Python_and_Java>`_ describes how to launch the Java-side sample.   
One can `start via Bndtools project template <https://wiki.eclipse.org/OSGi_R7_Remote_Services_between_Python_and_Java#Running_via_Bndtools_Project_Template>`_, or `start via Apache Karaf <https://wiki.eclipse.org/OSGi_R7_Remote_Services_between_Python_and_Java#Running_via_Apache_Karaf>`_

Once the Java sample has been successfully started, proceed below.

Starting the Python Sample
==========================

In the ipopo home directory, start the top-level script for this sample:

$ samples/run_rsa_py4java.py

or

$ python samples/run_rsa_py4java.py

This should produce output to the Python std out like the following:

.. code-block:: none
    ** Pelix Shell prompt **
    Python IHello service consumer received sync response: Java says: Hi PythonSync, nice to see you
    done with sayHelloAsync method
    done with sayHelloPromise method
    async response: JavaAsync says: Hi PythonAsync, nice to see you
    promise response: JavaPromise says: Hi PythonPromise, nice to see you

This output indicates that the Python process connected to the Java process using the Py4j distribution provider, imported
the Java-exported HelloImpl service, created a Python proxy for the IHello service instance hosted from Java, and injected that
proxy into the sample consumer in samples/rsa/helloconsumer.py by using iPOPO to set the self._helloservice to the proxy,
and calling the _validate method.   

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

When the _validate method is called it calls the self._helloservice.sayHello method and prints
out the resp to the console:

.. code-block:: python

    @Validate
    def _validate(self, bundle_context):
        # call it!
        resp = self._helloservice.sayHello(self._name + 'Sync', self._msg)
        print(
            "{0} IHello service consumer received sync response: {1}".format(
                self._name,
                resp))

The print is responsible for the console output

.. code-block:: none

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

.. code-block:: none

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

.. code-block:: none

    done with sayHelloPromise method
     
Note that the async response and promise response are received sometime later, after the
remote (Java) call is completed and the lambda expression is executed via Future.add_done_callback.  This results
in the output ordering of:

.. code-block:: none

    Python IHello service consumer received sync response: Java says: Hi PythonSync, nice to see you
    done with sayHelloAsync method
    done with sayHelloPromise method
    async response: JavaAsync says: Hi PythonAsync, nice to see you
    promise response: JavaPromise says: Hi PythonPromise, nice to see you
    
You can now go back to see other :ref:`Tutorials` or take a look at the
:ref:`refcards`.
