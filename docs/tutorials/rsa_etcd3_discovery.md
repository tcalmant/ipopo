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
client provider available in the [pelix.rsa.providers.discovery.etcd3](https://github.com/tcalmant/ipopo/blob/v3/pelix/rsa/providers/discovery/etcd3/__init__.py)
module.  This etcd3 client discovery provider uses the etd3 protocol to advertise and discovery endpoint descriptions.

The use of this provider for running this tutorial requires a configured and running [etcd3](https://github.com/etcd-io/etcd) server
for the discovery client provider to connect to. Without any custom config, the default hostname and port for etcd3 servers are etcd.hostname=localhost and etcd.port=2379, and 
these are the defaults in the etcd3 discovery provider (along with other configuration properties) documented [here](https://github.com/tcalmant/ipopo/blob/v3/pelix/rsa/providers/discovery/etcd3/__init__.py#L82).

## Requirements

This tutorial sample requires Python 3.10+, and version 3.0.0+ of iPOPO.

## Using Etcd3 to Advertise an Endpoint Description

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
        "pelix.rsa.providers.discovery.etcd3",
        # HTTP Service
        "pelix.http.basic",
        # XML-RPC distribution provider (opt)
        "pelix.rsa.providers.distribution.xmlrpc",
        # RSA shell commands (opt)
        "pelix.rsa.shell",
    )
```

After starting the framework and creating a basic topology manager, the etcd3 endpoint discovery service is [configured and connected by specifying the etcd.hostname, etcd.por, etcd.connected_callbackt and started](https://github.com/tcalmant/ipopo/blob/v3/samples/run_rsa_etcd3_xmlrpc_impl.py#L88)

```
    # start etcd3 discovery service client now that the basic_topology_manager is running
    from pelix.rsa.providers.discovery.etcd3 import ETCD_HOSTNAME_PROP, \
        ETCD_PORT_PROP, ETCD_CONNECTED_CALLBACK_PROP
    instantiate_etcd3_discovery_provider(context,
                                         {ETCD_HOSTNAME_PROP: ETCD_HOSTNAME,
                                          ETCD_PORT_PROP: ETCD_PORT,
                                          ETCD_CONNECTED_CALLBACK_PROP: connected_cb})
```

Once the etcd3 component is instantiated and connected to the etcd3 server, the example [starts the helloworld_xmlrpc bundle](https://github.com/tcalmant/ipopo/blob/v3/samples/run_rsa_etcd3_xmlrpc_impl.py#L101), which
will instantiate a helloworld impl remote service, and trigger the rsa distribution to export, and the creation 
and advertisement via etcd3 of an endpoint description.  Other clients
connected to this etdc3 server will be notified of the new endpoint, and have the opportunity to import a proxy
and use the IHello service.

## Running the Exporter/Advertiser Sample App

To show the whole process, first run the [samples.run_rsa_etcd3_xmlrpc_impl](https://github.com/tcalmant/ipopo/blob/v3/samples/run_rsa_etcd3_xmlrpc_impl.py) sample application

```
$ python -m samples.run_rsa_etcd3_xmlrpc_impl
** Pelix Shell prompt **
DEBUG:asyncio:Using proactor: IocpProactor
INFO:http-server:Starting HTTP server: [127.0.0.1]:8181 ...
DEBUG:grpc._cython.cygrpc:Using AsyncIOEngine.POLLER as I/O engine
INFO:http-server:HTTP server started: [127.0.0.1]:8181
DEBUG:pelix.rsa.providers.discovery.etcd3:CONNECTED etcd3 session_id=4469111c-91c2-4dba-b64f-750d14243fda to host=localhost port=2379
Etcd3 connected!  <-- this is provided via the connected_cb callback function 
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
If you have debugging turned on for the etcd3 localhost server (start with ./etcd --debug), you will see something like this output to the etcd3 console
```
2025-04-23 11:39:14.935171 D | etcdserver/api/v3rpc: start time = 2025-04-23 11:39:14.927221335 -0700 PDT m=+218.646195160, time spent = 7.93516ms, remote = 127.0.0.1:38726, response type = /etcdserverpb.Lease/LeaseGrant, request count = -1, request size = -1, response count = -1, response size = -1, request content =
2025-04-23 11:39:14.938040 D | etcdserver/api/v3rpc: start time = 2025-04-23 11:39:14.937579953 -0700 PDT m=+218.656553734, time spent = 397.094µs, remote = 127.0.0.1:38726, response type = /etcdserverpb.KV/Range, request count = 0, request size = 134, response count = 0, response size = 29, request content = key:"org.eclipse.ecf.provider.etcd3.container.Etcd3DiscoveryContainer" range_end:"org.eclipse.ecf.provider.etcd3.container.Etcd3DiscoveryContainer\\0"
2025-04-23 11:39:14.939135 D | etcdserver/api/v3rpc: start time = 2025-04-23 11:39:14.938841484 -0700 PDT m=+218.657815267, time spent = 246.662µs, remote = 127.0.0.1:38726, response type = /etcdserverpb.KV/Put, request count = 1, request size = 151, response count = 0, response size = 29, request content = key:"org.eclipse.ecf.provider.etcd3.container.Etcd3DiscoveryContainer/51600bf3-37f1-4870-aeeb-98c23ecb85a0" value_size:36 lease:7587886303146547715
2025-04-23 11:39:14.964578 D | etcdserver/api/v3rpc: start time = 2025-04-23 11:39:14.964363827 -0700 PDT m=+218.683337613, time spent = 188.423µs, remote = 127.0.0.1:38726, response type = /etcdserverpb.KV/Put, request count = 1, request size = 1469, response count = 0, response size = 29, request content = key:"org.eclipse.ecf.provider.etcd3.container.Etcd3DiscoveryContainer/51600bf3-37f1-4870-aeeb-98c23ecb85a0/763b7e97-e87b-4489-a686-fbc11a015bfa" value_size:1315 lease:7587886303146547715
```
The last line (Put request) is the advertisement of the IHello service endpoint description

## Running the Discoverer/Importer/Consumer Sample App

After running the exporter process (as above), start the [consumer application](https://github.com/tcalmant/ipopo/blob/v3/samples/run_rsa_etcd3_xmlrpc_consumer.py)

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

Note that if the remote service exposes async apis (e.g. sayHelloAsync and sayHelloPromise in the IHello service) then the calling of these methods
will not block the consumer's calling thread.
