(rsa_tutorial_xmlrpc)=

# RSA Remote Services using XmlRpc transport

:::{admonition} Authors
Scott Lewis, Thomas Calmant
:::

## Introduction

This tutorial shows how to create and run a simple remote service using
the XmlRpc provider. The XmlRpc distribution provider is one of several
supported by the RSA Remote Services (OSGi R7-compliant) implementation.

## Requirements

This tutorial sample requires Python 3.4+ or Python 2.7, and version
0.8.0+ of iPOPO.

## Defining the Remote Service with a Python Class

We'll start by defining a Python *hello* service that can to be
exported by RSA for remote access.

In the `sample.rsa` package is the `helloimpl_xmlrpc` module, containing
the `XmlRpcHelloImpl` class

```python
@ComponentFactory("helloimpl-xmlrpc-factory")
@Provides(
    "org.eclipse.ecf.examples.hello.IHello"
)
@Instantiate(
    "helloimpl-xmlrpc",
    {
        # uncomment to automatically export upon creation
        # "service.exported.interfaces":"*",
        "osgi.basic.timeout": 60000,
    },
)
class XmlRpcHelloImpl(HelloImpl):
    pass
```

The `XmlRpcHelloImpl` class has no body/implementation as it inherits
its implementation from the `HelloImpl` class, which we will discuss in
a moment.

The important parts of this class declaration for remote services are
the `@Provides` class decorator and the commented-out
**`service.exported.interfaces`** and **`osgi.basic.timeout`** properties in
the `@Instantiate` decorator.

The `@Provides` class decorator gives the **name** of the service
specification provided by this instance. This is the name that both
local and remote consumers use to lookup this service, even if it's
local-only (*i.e.* not a remote service). In this case, since the
original `IHello` interface is a java interface class, the
fully-qualified name of the
[interface class is used](https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/examples/org.eclipse.ecf.examples.hello/src/org/eclipse/ecf/examples/hello/IHello.java).
For an example of Java↔Python remote services see
[this tutorial](./rsa_pythonjava.md).

For Python-only remote services it's not really necessary for this
service specification be the name of a Java class, any unique String
could have been used.

The **`osgi.basic.timeout`** is an optional property that gives a maximum
time (in milliseconds) that the consumer will wait for a response before
timing out.

The **`service.exported.interfaces`** property is a
[required property for remote service export](https://docs.osgi.org/specification/osgi.cmpn/7.0.0/service.remoteservices.html#i1710847).
If one wants to have a remote service exported immediately upon
instantiation and registration as an iPOPO service, this property can be
set to value `*` which means to export all service interfaces.

The **`service.exported.interfaces`** property is commented out so that it
is **not** exported immediately upon instantiation and registration.
Instead, for this tutorial the export is performed via iPOPO console
commands. If these comments were to be removed, the RSA impl will export
this service as soon as it is instantiated and registered, making it
unnecessary to explicitly export the service as shown in the
Exporting the XmlRpcHelloImpl as a Remote Servicesection below.

## The HelloImpl Implementation

The `XmlRpcHelloImpl` class delegates all the actual implementation to
the `HelloImpl` class, which has the code for the methods defined for
the *"org.eclipse.ecf.examples.hello.IHello"* service specification
name, with the main method `sayHello`:

```python
class HelloImpl:
    def sayHello(self, name='Not given', message='nothing'):
        print(
            "Python.sayHello called by: {0} with message: '{1}'".format(
                name, message))
        return "PythonSync says: Howdy {0} that's a nice runtime you got there".format(
            name)
```

The `sayHello` method is invoked via a remote service consumer once the
service has been exporting.

(xml_rpc_hello_export)=
## Exporting the XmlRpcHelloImpl as a Remote Service

Go to the pelix home directory and start the `run_rsa_xmlrpc.py` main
program

```
bash$ python -m samples.run_rsa_xmlrpc
** Pelix Shell prompt **
$
```

To load the module and instantiate and register an `XmlRpcHelloImpl`
instance type

```
$ start samples.rsa.helloimpl_xmlrpc
Bundle ID: 18
Starting bundle 18 (samples.rsa.helloimpl_xmlrpc)...
```

In your environment, bundle number might not be 18... that is fine.

If you list services using the `sl` console command you should see an
instance of `IHello` service

```
$ sl org.eclipse.ecf.examples.hello.IHello
+----+-------------------------------------------+--------------------------------------------------+---------+
| ID |              Specifications               |                      Bundle                      | Ranking |
+====+===========================================+==================================================+=========+
| 20 | ['org.eclipse.ecf.examples.hello.IHello'] | Bundle(ID=18, Name=samples.rsa.helloimpl_xmlrpc) | 0       |
+----+-------------------------------------------+--------------------------------------------------+---------+
1 services registered
```

The service ID (20 in this case) may not be the same in your
environment... again that is ok... but **make a note of what the service ID is**.

To export this service instance as remote service and make it available
for remote access, use the `exportservice` command in the pelix console,
giving the number (20 from above) of the service to export:

```
$ exportservice 20        # use the service id for the org.eclipse.ecf.examples.hello.IHello service if not 20
Service=ServiceReference(ID=20, Bundle=18, Specs=['org.eclipse.ecf.examples.hello.IHello']) exported by 1 providers. EDEF written to file=edef.xml
$
```

This means that the service has been successfully exported. To see this
use the `listexports` console command:

```
$ listexports
+--------------------------------------+-------------------------------+------------+
|             Endpoint ID              |         Container ID          | Service ID |
+======================================+===============================+============+
| b96927ad-1d00-45ad-848a-716d6cde8443 | http://127.0.0.1:8181/xml-rpc | 20         |
+--------------------------------------+-------------------------------+------------+
$ listexports b96927ad-1d00-45ad-848a-716d6cde8443
Endpoint description for endpoint.id=b96927ad-1d00-45ad-848a-716d6cde8443:
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
$
```

Note that `listexports` produced a small table with **Endpoint ID**,
**Container ID**, and **Service ID** columns. As shown above, if the
Endpoint ID is copied and used in listexports, it will then print out
the endpoint description (XML) for the newly-created endpoint.

Also as indicated in the `exportservice` command output, a file
*edef.xml* has also been written to the filesystem containing the
endpoint description XML known as EDEF.
[EDEF is a standardized XML format](https://docs.osgi.org/specification/osgi.cmpn/7.0.0/service.remoteserviceadmin.html#i1889341)
that gives all of the remote service meta-data required for a consumer
to import an endpoint. The *edef.xml* file will contain the same XML
printed to the console via the
`listexports b96927ad-1d00-45ad-848a-716d6cde8443` console command.

## Importing the XmlRpcHelloImpl Remote Service

For a consumer to use this remote service, another python process should
be started using the same command:

```
bash$ python -m samples.run_rsa_xmlrpc
** Pelix Shell prompt **
$
```

If you have started this second python process from the same location,
all that's necessary to trigger the import of the remote service, and
have a consumer sample start to call it's methods is to use the
`importservice` console command:

```
$ importservice
Imported 1 endpoints from EDEF file=edef.xml
Python IHello service consumer received sync response: PythonSync says: Howdy PythonSync that's a nice runtime you got there
done with sayHelloAsync method
done with sayHelloPromise method
Proxy service=ServiceReference(ID=21, Bundle=7, Specs=['org.eclipse.ecf.examples.hello.IHello']) imported. rsid=http://127.0.0.1:8181/xml-rpc:3
$ async response: PythonAsync says: Howdy PythonAsync that's a nice runtime you got there
promise response: PythonPromise says: Howdy PythonPromise that's a nice runtime you got there
```

This indicates that the remote service was imported, and the methods on
the remote service were called by the consumer.

Here is the code for the consumer (also in `samples/rsa/helloconsumer_xmlrpc.py`)

```python
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Requires, Validate

from concurrent.futures import ThreadPoolExecutor

@ComponentFactory("remote-hello-consumer-factory")
# The '(service.imported=*)' filter only allows remote services to be injected
@Requires("_helloservice", "org.eclipse.ecf.examples.hello.IHello",
          False, False, "(service.imported=*)", False)
@Instantiate("remote-hello-consumer")
class RemoteHelloConsumer:

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
```

For having this remote service injected, the important part of things is
the `@Requires` decorator

```python
@Requires("_helloservice", "org.eclipse.ecf.examples.hello.IHello",
          False, False, "(service.imported=*)", False)
```

This gives the specification name required
**org.eclipse.ecf.examples.hello.IHello**, and it also gives an OSGi
filter

```python
"(service.imported=*)"
```

As per the [Remote Service spec](https://docs.osgi.org/specification/osgi.cmpn/7.0.0/service.remoteservices.html#i1710847)
this requires that the `IHello` service is a remote service, as all
proxies must have the **service.imported** property set, indicating that
it was imported.

When `importservice` is executed the RSA implementation does the
following:

1.  Reads the edef.xml from filesystem (i.e. 'discovers the service')
2.  Create a local proxy for the remote service using the edef.xml file
3.  The proxy is injected by iPOPO into the
    `RemoteHelloConsumer._helloservice` member
4.  The `_activated` method is called by iPOPO, which uses the
    `self._helloservice` proxy to send the method calls to the remote
    service, using HTTP and XML-RPC to serialize the `sayHello` method
    arguments, send the request via HTTP, get the return value back, and
    print the return value to the consumer's console.

Note that with Export, rather than using the console's `exportservice`
command, it may be invoked programmatically, or automatically by the
topology manager (for example upon service registration). For Import,
the `importservice` command may also be invoked automatically, or via
remote service discovery (e.g. etcd, zookeeper, zeroconf, custom, etc).
The use of the console commands in this example was to demonstrate the
dynamics and flexibility provided by the OSGi R7-compliant RSA
implementation.

## Exporting Automatically upon Service Registration

To export automatically upon service registration, all that need be done
is to un-comment the setting the **service.exported.interfaces**
property in the `Instantiate` decorator:

```python
@ComponentFactory("helloimpl-xmlrpc-factory")
@Provides(
   "org.eclipse.ecf.examples.hello.IHello"
)
@Instantiate(
   "helloimpl-xmlrpc",
   {
       "service.exported.interfaces": "*",
       "osgi.basic.timeout": 60000,
   },
)
class XmlRpcHelloImpl(HelloImpl):
   pass
```

Unlike in the example above, when this service is instantiated and
registered, it will also be automatically exported, making unnecessary
to use the `exportservice` command.

