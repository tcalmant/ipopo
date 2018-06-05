from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate
from samples.rsa.hellomsg_pb2 import HelloMsgContent

def create_hellomsgcontent(message):
    resmsg = HelloMsgContent()
    resmsg.h = 'Response from Python'
    resmsg.f = 'Python Impls'
    resmsg.to = 'tojava'
    resmsg.hellomsg = message
    for x in range(0,5):
        resmsg.x.append(float(x))
    return resmsg

@ComponentFactory('pbhelloimpl-provider-factory')
@Provides('org.eclipse.ecf.examples.protobuf.hello.IHello')
@Instantiate('pbhelloimpl-provider-auto', { 'service.exported.interfaces':'*', 
                                         'service.exported.configs': 'ecf.py4j.host.python.pb', 
                                         'service.intents': ['osgi.basic', 'osgi.async'], 
                                         'osgi.basic.timeout':30000})
class PythonHelloImpl(object):

    def sayHello(self, hellomsg):
        print("Python.sayHello called by: {0} with message: '{1}'".format(hellomsg.f,hellomsg))
        return create_hellomsgcontent("Python responds: Howdy {0} that's a nice runtime you got there".format(hellomsg.f))
    
    def sayHelloAsync(self, hellomsg):
        print("Python.sayHelloAsync called by: {0} with message: '{1}'".format(hellomsg.f,hellomsg))
        return create_hellomsgcontent("PythonAsync responds: Howdy {0} that's a nice runtime you got there".format(hellomsg.f))
    