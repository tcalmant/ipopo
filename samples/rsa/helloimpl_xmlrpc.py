#!/usr/bin/python
# -- Content-Encoding: UTF-8 --

"""
For export as a remote service, this impl requires the some distribution
provider that supports the osgi.async service intent (e.g. py4j or xmlrpc).
This implementation exports the org.eclipse.ecf.examples.hello.IHello service
interface:
https://github.com/ECF/AsyncRemoteServiceExamples/blob/master/hello/org.eclipse.ecf.examples.hello.javahost/src/org/eclipse/ecf/examples/hello/javahost/HelloImpl.java
for access via some remote service consumer (java or python).

"""

from pelix.ipopo.decorators import ComponentFactory, Instantiate, Provides
from samples.rsa.helloimpl import HelloImpl


@ComponentFactory("helloimpl-xmlrpc-factory")
@Provides("org.eclipse.ecf.examples.hello.IHello")
@Instantiate(
    "helloimpl-xmlrpc",
    {
        "osgi.basic.timeout": 60000,
        # uncomment to automatically export upon creation
        "service.exported.interfaces": "*",
        "service.exported.configs": "ecf.xmlrpc.server",
    },
)
class XmlRpcHelloImpl(HelloImpl):
    pass
