from pelix.ipopo.decorators import ComponentFactory,Instantiate,Requires,Validate

from samples.rsa.hellomsg_pb2 import HelloMsgContent

def create_hellomsgcontent(message):
    resmsg = HelloMsgContent()
    resmsg.h = 'Message from Python'
    resmsg.f = 'Python consumer'
    resmsg.to = 'tojava'
    resmsg.hellomsg = message
    for x in range(0,5):
        resmsg.x.append(float(x))
    return resmsg


@ComponentFactory("remote-pbhello-consumer-factory")
# The '(service.imported=*)' filter only allows remote hello service proxies to be injected
@Requires("_helloservice", "org.eclipse.ecf.examples.protobuf.hello.IHello", False, False, "(service.imported=*)", False)
@Instantiate("remote_pbhello-consumer")
class RemotePbHelloConsumer(object):
    
    def __init__(self):
        self._helloservice = None
        
    @Validate
    def _validate(self,bcontext):
        # call it!
        resp = self._helloservice.sayHello(create_hellomsgcontent("I'm calling sayHello"))
        print("IHello service consumer received response: {0}".format(resp))
        # call sayHelloAsync which returns future and we lambda to print the result when done
        self._helloservice.sayHelloAsync(create_hellomsgcontent("I'm calling sayHelloAsynch")).add_done_callback(lambda f: print('async respon: {0}'.format(f.result())))
        print("done with helloimpl _validate method")
