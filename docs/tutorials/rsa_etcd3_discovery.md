(rsa_tutorial_xmlrpc)=

# Using Etcd3 Endpoint Discovery

:::{admonition} Authors
Scott Lewis, Thomas Calmant
:::

## Introduction

This tutorial shows how to use an etd3 server to advertise remote service endpoints via a [OSGI-specified meta-data format called an endpoint description](https://docs.osgi.org/specification/osgi.cmpn/7.0.0/service.remoteserviceadmin.html#service.remoteserviceadmin.endpointdescription).
A discovery provider can advertise 'endpoint descriptions' on remote service export, and immediately discovered and imported by a consumer process
to use/consume that remote service.

A popular industry service discovery protocol used in [kubernetes](https://kubernetes.io/) is
[etcd3](https://github.com/etcd-io/etcd).  ipopo has an etcd3 endpoint discovery
client provider available in the [pelix.rsa.providers.discovery.etcd3.discovery_etcd3](https://github.com/tcalmant/ipopo/blob/v3/pelix/rsa/providers/discovery/etcd3/discovery_etcd3.py)
module.  This etcd3 client discovery provider uses the etd3 protocol to advertise and discovery endpoint descriptions.

The use of this provider for running this tutorial requires a configured and running [etcd3](https://github.com/etcd-io/etcd) server
for the discovery client provider to connect to. Without any custom config, the default hostname and port for etcd3 servers are 'localhost' and 2379, and 
these are the defaults in the etcd3 discovery provider (along with other configuration properties) documented [here](https://github.com/tcalmant/ipopo/blob/v3/pelix/rsa/providers/discovery/etcd3/discovery_etcd3.py#L82).

## Requirements

This tutorial sample requires Python 3.10+, and version 3.0.0+ of iPOPO.

The sample program `samples.run_rsa_etcd3_xmlrpc_impl` (remote service implementation/server, using etcd3 discovery and xmlrpc distribution) contains the following [set of bundles](https://github.com/tcalmant/ipopo/blob/v3/samples/run_rsa_etcd3_xmlrpc_impl.py#L60))

```
    bundles = (
        "pelix.ipopo.core",
        "pelix.shell.core",
        "pelix.shell.ipopo",
        "pelix.shell.console",
        # RSA implementation
        "pelix.rsa.remoteserviceadmin",
        # topology manager 
        "pelix.rsa.topologymanagers.basic",
        # etcd3 discovery  
        "pelix.rsa.providers.discovery.etcd3.discovery_etcd3",
        # HTTP Service
        "pelix.http.basic",
        # XML-RPC distribution provider (opt)
        "pelix.rsa.providers.distribution.xmlrpc",
        # RSA shell commands (opt)
        "pelix.rsa.shell",
    )
```

The framework is then [created and started](https://github.com/tcalmant/ipopo/blob/v3/samples/run_rsa_etcd3_xmlrpc_impl.py#L80)

```
    framework = pelix.create_framework(
        bundles,
        {
            "ecf.xmlrpc.server.hostname": HTTP_HOSTNAME,
        },
    )
    framework.start()

```

the etcd3 endpoint discovery service is then [configured by specifying the etcd.hostname, etcd.por, etcd.connected_callbackt and started](https://github.com/tcalmant/ipopo/blob/v3/samples/run_rsa_etcd3_xmlrpc_impl.py#L88)

```
    # start etcd3 discovery service client
    with use_ipopo(framework.get_bundle_context()) as ipopo:
        ipopo.instantiate(
            "etcd3-endpoint-discovery-factory",
            "etcd3-endpoint-discovery",
            {"etcd.hostname": ETCD_HOSTNAME, "etcd.port": ETCD_PORT, "etcd.connected_callback": connected_cb},
        )
```

After the discovery provider is configured and started/connected to the etcd3 server, the example [starts the helloworld_xmlrpc bundle](https://github.com/tcalmant/ipopo/blob/v3/samples/run_rsa_etcd3_xmlrpc_impl.py#L101), which
will instantiate a helloworld impl component, and trigger the rsa remote services export, that will trigger the etd3 endpoint advertising.  Other clients
connected to this etdc3 server will then be notified of the new endpoint, and have the opportunity to import and use a remote
service proxy.

```
    # install helloimpl_xmlrpc module, instantiate component and should result
    # in export via xmlrpc distribution provider and advertisement of endpoint
    # description via etcd3
    framework.get_bundle_context().install_bundle("samples.rsa.helloimpl_xmlrpc").start()
```

Let's run the samples.run_rsa_etcd3_xmlrpc_impl program

```
$ python -m samples.run_rsa_etcd3_xmlrpc_impl
** Pelix Shell prompt **
DEBUG:asyncio:Using proactor: IocpProactor
$ INFO:http-server:Starting HTTP server: [127.0.0.1]:8181 ...
DEBUG:grpc._cython.cygrpc:Using AsyncIOEngine.POLLER as I/O engine
INFO:http-server:HTTP server started: [127.0.0.1]:8181
DEBUG:pelix.rsa.providers.discovery.etcd3.discovery_etcd3:CONNECTED etcd3 session_id=4469111c-91c2-4dba-b64f-750d14243fda to host=localhost port=2379
Etcd3 connected!
$ sl org.eclipse.ecf.examples.hello.IHello
+----+-------------------------------------------+--------------------------------------------------+---------+
| ID |              Specifications               |                      Bundle                      | Ranking |
+====+===========================================+==================================================+=========+
| 22 | ['org.eclipse.ecf.examples.hello.IHello'] | Bundle(ID=19, Name=samples.rsa.helloimpl_xmlrpc) | 0       |
+----+-------------------------------------------+--------------------------------------------------+---------+
1 services registered
$ listexports
+--------------------------------------+-------------------------------+------------+
|             Endpoint ID              |         Container ID          | Service ID |
+======================================+===============================+============+
| 9c808ee4-dd85-4077-93db-1bf93859c34a | http://127.0.0.1:8181/xml-rpc | 22         |
+--------------------------------------+-------------------------------+------------+
```

Then start a consumer to discover and import the remote service endpoint via etc3

```
$ python -m samples.run_rsa_etcd3_xmlrpc_consumer
** Pelix Shell prompt **
$ Python IHello service consumer received sync response: PythonSync says: Howdy PythonSync that's a nice runtime you got there
done with sayHelloAsync method
done with sayHelloPromise method
async response: PythonAsync says: Howdy PythonAsync that's a nice runtime you got there
promise response: PythonPromise says: Howdy PythonPromise that's a nice runtime you got there
```

The consumer uses etcd3 to discover the `IHello` remote service, advertised by the previously-started run_rsa_etcd3_xmlrpc_impl program, the discovered endpoint
description is used to create a proxy for the remote service, and the proxy is then injected by ipopo into the consumer.  The consumer then [calls the proxy's methods](https://github.com/tcalmant/ipopo/blob/v3/samples/rsa/helloconsumer_xmlrpc.py#L41) producing the text
output above on the consumer console and this output on the remote service implementation console:

```
Consumer IHello service consumer received sync response: PythonSync says: Howdy ConsumerSync that's a nice runtime you got there
done with sayHelloAsync method
done with sayHelloPromise method
```

The remote service implementation also produces text output on both the consumer and above, and the remote service
implementation as below

```
$ Python.sayHello called by: ConsumerSync with message: 'Hello Impl'
Python.sayHelloAsync called by: ConsumerAsync with message: 'Hello Impl'
Python.sayHelloPromise called by: ConsumerPromise with message: 'Hello Impl'
```

Note that if the remote service exposes async apis (e.g. sayHelloAsync and sayHelloPromise) then the calling of these methods
will not block the calling thread.
