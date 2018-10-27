#!/usr/bin/python3
# This remote service consumer requires some java or python distribution
# provider (e.g. py4j or xmlrpc) and an implementation service (java or python)
# that exports the org.eclipse.ecf.examples.hello.IHello service interface:
# https://github.com/ECF/AsyncRemoteServiceExamples/blob/master/hello/org.eclipse.ecf.examples.hello.javahost/src/org/eclipse/ecf/examples/hello/javahost/HelloImpl.java
#
# When the IHello remote service impl is discovered and imported via discovery
# provider and topology manager, or imported via RSA importservice command, a
# IHello proxy will be injected by ipopo into the _helloservice field of the
# RemoteHelloConsumer instance, and _validate will then be called.
# With the implementation below, the _validate method then calls the proxy's
# IHello.sayHello, sayHelloAsync, and sayHelloPromise on the remote service.

from concurrent.futures import ThreadPoolExecutor

from pelix.ipopo.decorators import (
    ComponentFactory,
    Instantiate,
    Requires,
    Validate,
)


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
class RemoteHelloConsumer(object):
    def __init__(self):
        self._helloservice = None
        self._name = "Python"
        self._msg = "Hello Java"
        self._executor = ThreadPoolExecutor()

    @Validate
    def _validate(self, bundle_context):
        # call it!
        resp = self._helloservice.sayHello(self._name + "Sync", self._msg)
        print(
            "{0} IHello service consumer received sync response: {1}".format(
                self._name, resp
            )
        )
        # call sayHelloAsync which returns Future and we add lambda to print
        # the result when done
        self._executor.submit(
            self._helloservice.sayHelloAsync, self._name + "Async", self._msg
        ).add_done_callback(
            lambda f: print("async response: {0}".format(f.result()))
        )
        print("done with sayHelloAsync method")
        # call sayHelloAsync which returns Future and we add lambda to print
        # the result when done
        self._executor.submit(
            self._helloservice.sayHelloPromise,
            self._name + "Promise",
            self._msg,
        ).add_done_callback(
            lambda f: print("promise response: {0}".format(f.result()))
        )
        print("done with sayHelloPromise method")
