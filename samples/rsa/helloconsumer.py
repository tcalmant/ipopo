#!/usr/bin/python3
"""
This remote service consumer requires some java or python distribution provider
(e.g. py4j or xmlrpc) and an implementation service (java or python) that
exports the org.eclipse.ecf.examples.hello.IHello service interface:
https://github.com/ECF/AsyncRemoteServiceExamples/blob/master/hello/org.eclipse.ecf.examples.hello.javahost/src/org/eclipse/ecf/examples/hello/javahost/HelloImpl.java

When the IHello remote service impl is discovered and imported via discovery
provider and topology manager, or imported via RSA importservice command,
a IHello proxy will be injected by ipopo into the _helloservice field of the
RemoteHelloConsumer instance, and _validate will then be called.
With the implementation below, the _validate method then calls the proxy's
IHello.sayHello, sayHelloAsync, and sayHelloPromise on the remote service.
"""

from typing import Any

from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Requires, Validate


@ComponentFactory("remote-hello-consumer-factory")
# The '(service.imported=*)' filter only allows remote services to be injected
@Requires(
    "_helloservice",
    "org.eclipse.ecf.examples.hello.IHello",
    False,
    False,
    "(service.imported=*)",
    False,
)
@Instantiate("remote-hello-consumer")
class RemoteHelloConsumer:
    _helloservice: Any

    def __init__(self) -> None:
        self._name = "Python"
        self._msg = "Hello Java"

    @Validate
    def _validate(self, bundle_context: BundleContext) -> None:
        # call it!
        resp = self._helloservice.sayHello(self._name + "Sync", self._msg)
        print(self._name, "IHello service consumer received sync response:", resp)

        # call sayHelloAsync which returns Future and we add lambda to print
        # the result when done
        self._helloservice.sayHelloAsync(self._name + "Async", self._msg).add_done_callback(
            lambda f: print("async response:", f.result())
        )
        print("done with sayHelloAsync method")

        # call sayHelloAsync which returns Future and we add lambda to print
        # the result when done
        self._helloservice.sayHelloPromise(self._name + "Promise", self._msg).add_done_callback(
            lambda f: print("promise response:", f.result())
        )
        print("done with sayHelloPromise method")
