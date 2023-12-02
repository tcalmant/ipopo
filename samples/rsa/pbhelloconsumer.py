# This remote service consumer requires the py4j protobuf distribution provider
# and an implementation service (java or python) that exports the
# org.eclipse.ecf.examples.protobuf.hello.IHello service interface:
# https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/examples/org.eclipse.ecf.examples.protobuf.hello/src/org/eclipse/ecf/examples/protobuf/hello/IHello.java
#
# When the IHello remote service impl is discovered and imported via discovery
# provider and topology manager, or imported via RSA importservice command,
# a IHello proxy will be injected by ipopo into the _helloservice field of the
# RemotePbHelloConsumer instance, and _validate will then be called.
# With the implementation below, the _validate method immediately calls the
# proxy's IHello.sayHello, sayHelloAsync, and sayHelloPromise on the
# remote service.

from typing import Any
from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Requires, Validate
from samples.rsa.hellomsg_pb2 import HelloMsgContent


def create_hellomsgcontent(message: str) -> HelloMsgContent:
    resmsg = HelloMsgContent()
    resmsg.h = "Message from Python"
    resmsg.f = "Python consumer"
    resmsg.to = "tojava"
    resmsg.hellomsg = message
    for x in range(0, 5):
        resmsg.x.append(float(x))
    return resmsg


@ComponentFactory("remote-pbhello-consumer-factory")
# The '(service.imported=*)' filter only allows remote hello service
# proxies to be injected
@Requires(
    "_helloservice",
    "org.eclipse.ecf.examples.protobuf.hello.IHello",
    False,
    False,
    "(service.imported=*)",
    False,
)
@Instantiate("remote_pbhello-consumer")
class RemotePbHelloConsumer:
    _helloservice: Any

    @Validate
    def _validate(self, bcontext: BundleContext) -> None:
        # call it!
        resp = self._helloservice.sayHello(create_hellomsgcontent("pbPython consumer calling pb.sayHello"))
        print("pb sayHello received response: {0}".format(resp))
        # call sayHelloAsync which returns future and we lambda to print the
        # result when done
        self._helloservice.sayHelloAsync(
            create_hellomsgcontent("pbPython consumer calling pb.sayHelloAsynch")
        ).add_done_callback(lambda f: print("pbasync respon: {0}".format(f.result())))
        print("done with pb.sayHelloAsync")
        # call sayHelloAsync which returns Future and we add lambda to print
        # the result when done
        self._helloservice.sayHelloPromise(
            create_hellomsgcontent("pbPython consumer calling pb.sayHelloPromise")
        ).add_done_callback(lambda f: print("pbpromise response: {0}".format(f.result())))
        print("done with sayHelloPromise")
