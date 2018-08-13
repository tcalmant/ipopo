.. RSA Remote Services using XmlRpc transport

.. _rsa_tutorial:

RSA Remote Services using XmlRpc transport
###############################################

:Authors: Scott Lewis, Thomas Calmant

Introduction
============
This tutorial shows how to create and run a simple remote service using the XmlRpc provider.  The XmlRpc distribution provider is one of several supported by the OSGi R7 RSA implementation.

Requirements
============
This tutorial sample requires Python 3.4+ or Python 2.7, and version 0.8.0+ of iPOPO.

Defining the Remote Service as a Python class
=============================================

We'll start by defining a Python 'hello' service that can to be exported by RSA for remote access.

In the sample.rsa package is the helloimpl_xmlrpc module, containing the XmlRpcHelloImpl class

.. code-block:: python

    @ComponentFactory("helloimpl-xmlrpc-factory")
    @Provides(
       "org.eclipse.ecf.examples.hello.IHello"
    )  
    @Instantiate(
       "helloimpl-xmlrpc",
       {
           "service.intents": ["osgi.async"],  # Required to use osgi.async intent
           "osgi.basic.timeout": 60000,
       },
    )
    class XmlRpcHelloImpl(HelloImpl):
       pass

The XmlRpcHelloImpl class has no body/implementation as it inherits it's implementation from the HelloImpl class, which we will discuss in a moment.

The important parts of this class declaration for remote services are @Provides class decorator and the 'service.intents' and 'osgi.basic.timeout' properties in the @Instantiate decorator.

The @Provides class decorator gives the **name** of the service provided by this instance.   This is the name that consumers use to get access to this service, even if it's local-only (i.e. not a remote service).

The 'service.intents' property is a standardized service property defined in the `OSGi R7 Remote Services Chapter 100 <https://osgi.org/specification/osgi.cmpn/7.0.0/service.remoteservices.html>`.   'osgi.basic.timeout' gives a maximum time (milliseconds) that the consumer will wait for a response.



The XmlRpcHelloImpl class delegates all the actual implementation to the HelloImpl class, which has the code for the methods defined for the 'org.eclipse.ecf.examples.hello.IHello' service specification name, with the main method 'sayHello':

.. code-block:: python

    class HelloImpl(object):
        def sayHello(self, name='Not given', message='nothing'):
            print(
                "Python.sayHello called by: {0} with message: '{1}'".format(
                    name, message))
            return "PythonSync says: Howdy {0} that's a nice runtime you got there".format(
                name)

The sayHello method is invoked via a remote service consumer once the service has been exporting.

Exporting the XmlRpcHelloImpl Service
=====================================

Go to the pelixhome directory and start the 'run_rsa_xmlrpc.py' main program

.. code-block:: console

    ipopo-0.8.0$ python -m samples.run_rsa_xmlrpc
    ** Pelix Shell prompt **
    $ 
    
To load the XmlRpcHelloImpl class type

    $ start samples.rsa.helloimpl_xmlrpc
    Bundle ID: 18
    Starting bundle 18 (samples.rsa.helloimpl_xmlrpc)...

The bundle number might not be 18...that is fine.

If you list services using the 'sl' console command you should see an instance of IHello service

.. code-block:: console

    $ sl org.eclipse.ecf.examples.hello.IHello
    +----+-------------------------------------------+--------------------------------------------------+---------+
    | ID |              Specifications               |                      Bundle                      | Ranking |
    +====+===========================================+==================================================+=========+
    | 20 | ['org.eclipse.ecf.examples.hello.IHello'] | Bundle(ID=18, Name=samples.rsa.helloimpl_xmlrpc) | 0       |
    +----+-------------------------------------------+--------------------------------------------------+---------+
    1 services registered
    
The service id (20 in this case) may not be the same in your environment, but that is ok.

To export this service instance as remote service and make it available for remote access, use the **exportservice** console command in the pelix console, giving the number (20 from above) of the service to export:

.. code-block:: console

    $ exportservice 20        # use the service id for the org.eclipse.ecf.examples.hello.IHello service if not 20
    Service=ServiceReference(ID=20, Bundle=18, Specs=['org.eclipse.ecf.examples.hello.IHello']) exported by 1 providers. EDEF written to file=edef.xml
    $
    
This means that the service has been successfully exported to localhost, port 8181.   These defaults are set in the run_rsa_xmlrpc.py main program.    

Also as indicated, a file edef.xml has been written to the filesystem containing the OSGi standardized **edef**...that stands for endpoint decription extension language.  This is an xml format that gives all of the remote service meta-data required by OSGi Remote Services/Remote Service Admin.   

Here's the edef.xml for the above export

.. code-block:: xml

    <?xml version='1.0' encoding='cp1252'?>
    <endpoint-descriptions xmlns="http://www.osgi.org/xmlns/rsa/v1.0.0">
            <endpoint-description>
                    <property name="objectClass" value-type="String">
                            <array>
                                    <value>org.eclipse.ecf.examples.hello.IHello</value>
                            </array>
                    </property>
                    <property name="remote.configs.supported" value-type="String">
                            <array>
                                    <value>ecf.xmlrpc.server</value>
                            </array>
                    </property>
                    <property name="service.imported.configs" value-type="String">
                            <array>
                                    <value>ecf.xmlrpc.server</value>
                            </array>
                    </property>
                    <property name="remote.intents.supported" value-type="String">
                            <array>
                                    <value>osgi.basic</value>
                                    <value>osgi.async</value>
                            </array>
                    </property>
                    <property name="service.intents" value-type="String">
                            <array>
                                    <value>osgi.async</value>
                            </array>
                    </property>
                    <property name="endpoint.service.id" value="20" value-type="Long">
                            </property>
                    <property name="service.id" value="20" value-type="Long">
                            </property>
                    <property name="endpoint.framework.uuid" value="4d541077-ee2a-4d68-85f5-be529f89bec0" value-type="String">
                            </property>
                    <property name="endpoint.id" value="b96927ad-1d00-45ad-848a-716d6cde8443" value-type="String">
                            </property>
                    <property name="service.imported" value="true" value-type="String">
                            </property>
                    <property name="ecf.endpoint.id" value="http://127.0.0.1:8181/xml-rpc" value-type="String">
                            </property>
                    <property name="ecf.endpoint.id.ns" value="ecf.namespace.xmlrpc" value-type="String">
                            </property>
                    <property name="ecf.rsvc.id" value="3" value-type="Long">
                            </property>
                    <property name="ecf.endpoint.ts" value="1534119904514" value-type="Long">
                            </property>
                    <property name="osgi.basic.timeout" value="60000" value-type="Long">
                            </property>
            </endpoint-description>
    </endpoint-descriptions>
    
Importing the XmlRpcHelloImpl Remote Service
============================================

For a consumer to use this remote service, another python process should be started using the same command:

.. code-block:: console

    ipopo-0.8.0$ python -m samples.run_rsa_xmlrpc
    ** Pelix Shell prompt **
    $ 
    
If you have started this second python process from the same location, all that's necessary to trigger the import of the remote service, and have a consumer sample start to call it's methods is to use the console **importservice** command:

.. code-block:: console

    $ importservice
    Imported 1 endpoints from EDEF file=edef.xml
    Python IHello service consumer received sync response: PythonSync says: Howdy PythonSync that's a nice runtime you got there
    done with sayHelloAsync method
    done with sayHelloPromise method
    Proxy service=ServiceReference(ID=21, Bundle=7, Specs=['org.eclipse.ecf.examples.hello.IHello']) imported. rsid=http://127.0.0.1:8181/xml-rpc:3
    $ async response: PythonAsync says: Howdy PythonAsync that's a nice runtime you got there
    promise response: PythonPromise says: Howdy PythonPromise that's a nice runtime you got there

This indicates that the remote service was imported, and the methods on the remote service were called by the consumer.

Here is the code for the consumer (also in samples/rsa/helloconsumer_xmlrpc.py)

.. code-block:: python

    from pelix.ipopo.decorators import ComponentFactory, Instantiate, Requires, Validate

    from concurrent.futures import ThreadPoolExecutor

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
            self._executor = ThreadPoolExecutor()

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
            self._executor.submit(
                self._helloservice.sayHelloAsync,
                self._name + 'Async',
                self._msg).add_done_callback(
                lambda f: print(
                    'async response: {0}'.format(
                        f.result())))
            print("done with sayHelloAsync method")
            # call sayHelloAsync which returns Future and we add lambda to print
            # the result when done
            self._executor.submit(
                self._helloservice.sayHelloPromise,
                self._name + 'Promise',
                self._msg).add_done_callback(
                lambda f: print(
                    'promise response: {0}'.format(
                        f.result())))
            print("done with sayHelloPromise method")

For having this remote service injected, the important part of things is the @Requires decorator

.. code-block:: python

    @Requires("_helloservice", "org.eclipse.ecf.examples.hello.IHello",
              False, False, "(service.imported=*)", False)

This gives the specification name required **org.eclipse.ecf.examples.hello.IHello**, and it also gives an OSGi filter

.. code-block:: python

    "(service.imported=*)"
    
As per the `Remote Service spec <https://osgi.org/specification/osgi.cmpn/7.0.0/service.remoteservices.html#i1710847>` this requires that the IHello service is a remote service, as all  proxies must have the **service.imported** property set, indicating that it was imported.

When **importservice** is executed it 

 #. Reads the edef.xml from filesystem (i.e. 'discovers the service')
 #. Create a local proxy for the remote service using the edef.xml
 #. The proxy is injected by iPOPO into the RemoteHelloConsumer._helloservice member
 #. The _activated method is called by iPOPO, which uses the self._helloservice proxy to send the method calls to the remote service, using http and xmlrpc to serialize the sayHello method arguments, send the request via http, get the return value back, and print the return value to the consumer's console.

Note that with Export, rather than using the console's **exportservice** command, it may be invoked programmatically, or automatically by the topology manager (for example upon service registration).   For Import, the **importservice** command may also be invoked automatically, or via remote service discovery (e.g. etcd, zookeeper, zeroconf, custom, etc).   The use of the console commands in this example was to demonstrate the dynamics and flexibility provided by the OSGi R7-compliant RSA implementation.

You can now go back to see other :ref:`Tutorials` or take a look at the
:ref:`refcards`.
