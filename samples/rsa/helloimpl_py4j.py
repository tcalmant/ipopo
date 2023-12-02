#!/usr/bin/python3
"""
For export as a remote service, this impl requires the py4j distribution
provider (in pelix.rsa.providers.distribution.py4j) package.
The implementation below exports the org.eclipse.ecf.examples.hello.IHello
service interface:
https://github.com/ECF/AsyncRemoteServiceExamples/blob/master/hello/org.eclipse.ecf.examples.hello.javahost/src/org/eclipse/ecf/examples/hello/javahost/HelloImpl.java
for access via some remote service consumer (java or python).

When the IHello remote service is instantiated, the service properties given
in the Instantiate decorator are used to export via the ecf.py4j.host.python
distribution provider.

On the Java-side, this will typically trigger a HelloConsumer instance e.g.:
https://github.com/ECF/AsyncRemoteServiceExamples/blob/master/hello/org.eclipse.ecf.examples.hello.javahost/src/org/eclipse/ecf/examples/hello/javahost/HelloConsumer.java
to have it's references to the IHello proxy...
see @Reference(target='(service.imported=*)' which may then invoke the
sayHello, sayHelloAsync, and/or sayHelloPromise on this remote service.
"""

from pelix.ipopo.decorators import ComponentFactory, Instantiate, Provides
from samples.rsa.helloimpl import HelloImpl


@ComponentFactory("helloimpl-py4j-factory")
# Provides IHello interface as specified by Java interface.
@Provides("org.eclipse.ecf.examples.hello.IHello")
# See https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/examples/org.eclipse.ecf.examples.hello/src/org/eclipse/ecf/examples/hello/IHello.java
@Instantiate(
    "helloimpl-py4j",
    {
        "service.exported.interfaces": "*",  # Required for export
        # Required to use py4j python provider for export
        "service.exported.configs": "ecf.py4j.host.python",
        # Required to use osgi.async intent
        "service.intents": ["osgi.async"],
        "osgi.basic.timeout": 30000,
    },
)  # Timeout associated with remote calls (in ms)
class Py4jHelloImpl(HelloImpl):
    """
    All method implementations handled by HelloImpl super-class.

    See samples.rsa.helloimpl module.
    """

    pass
