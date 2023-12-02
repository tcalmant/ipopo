#!/usr/bin/python
# -- Content-Encoding: UTF-8 --

"""
For export as a remote service, this impl requires the some distribution
provider that supports the osgi.async service intent (e.g. py4j or xmlrpc).
This implementation exports the org.eclipse.ecf.examples.hello.IHello service
interface:
https://github.com/ECF/AsyncRemoteServiceExamples/blob/master/hello/org.eclipse.ecf.examples.hello.javahost/src/org/eclipse/ecf/examples/hello/javahost/HelloImpl.java
for access via some remote service consumer (java or python).

When the XmlRpcHelloImpl remote service is instantiated, it is *not*
immediately exported, since it is missing the OSGi-required
service.exported.interfaces property.
For this example, this service is expected to be exported after service
registration via the rsa exportservice console command.  Once exported, remote
service consumers may be notified via either discovery provider publishing
(e.g. etcd) or via the rsa importservice command.
"""


from pelix.ipopo.decorators import ComponentFactory, Instantiate, Provides
from samples.rsa.helloimpl import HelloImpl


@ComponentFactory("helloimpl-xmlrpc-factory")
@Provides(
    "org.eclipse.ecf.examples.hello.IHello"
)  # Provides IHello interface as specified by Java interface.
# See <a
# href="https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/examples/org.eclipse.ecf.examples.hello/src/org/eclipse/ecf/examples/hello/IHello.java">IHello
# service interface</a>
@Instantiate(
    "helloimpl-xmlrpc",
    {
        "osgi.basic.timeout": 60000,
        # uncomment to automatically export upon creation
        # "service.exported.interfaces":"*",
    },
)
class XmlRpcHelloImpl(HelloImpl):
    pass
