from samples.rsa.hellomsg_pb2 import HelloMsgContent
from concurrent.futures.thread import ThreadPoolExecutor
from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate

def create_hellomsgcontent(message):
    resmsg = HelloMsgContent()
    resmsg.h = 'Response from Python'
    resmsg.f = 'Python Impls'
    resmsg.to = 'tojava'
    resmsg.hellomsg = message
    for x in range(0,5):
        resmsg.x.append(float(x))
    return resmsg

@ComponentFactory('pbhelloimpl-py4j-factory')
@Provides('org.eclipse.ecf.examples.protobuf.hello.IHello') # Provides IHello interface as specified by Java interface.  
#See <a href="https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/examples/org.eclipse.ecf.examples.protobuf.hello/src/org/eclipse/ecf/examples/protobuf/hello/IHello.java">IHello service interface</a>
@Instantiate('pbhelloimpl-py4j', { 'service.exported.interfaces':'*', 
                                   'service.exported.configs': 'ecf.py4j.python.protobuf.host', 
                                   'service.intents': ['osgi.async'], 
                                   'osgi.basic.timeout':120000})
class PbHelloImpl(object):
    '''
    Implementation of Java org.eclipse.ecf.examples.protobuf.hello.IHello service interface.
    This interface declares on normal/synchronous method ('sayHello') and two
    async methods as defined by the OSGi Remote Services osgi.async intent.  Note
    that the service.intents property above includes the 'osgi.async' intent.  It
    also declares a property 'osgi.basic.timeout' which will be used to assure that
    the remote methods timeout after the given number of milliseconds.
    
    See the OSGi Remote Services specification at
    
    https://osgi.org/specification/osgi.cmpn/7.0.0/service.remoteservices.html
    
    The specification defines the standard properties given above.
    
    '''
    def sayHello(self, hellomsg):
        '''
        Synchronous implementation of IHello.sayHello synchronous method.  The remote
        calling thread will be blocked until this is executed and responds
        '''
        print("pbPython.sayHello called by: {0} with message: '{1}'".format(hellomsg.f,hellomsg))
        return create_hellomsgcontent("pythonpbhello responds: Howdy {0} that's a nice runtime you got there".format(hellomsg.f))
    
    def sayHelloAsync(self, hellomsg):
        print("Python.sayHelloAsync called by: {0} with message: '{1}'".format(hellomsg.f,hellomsg))
        return create_hellomsgcontent("pythonpbhello responds: Howdy {0} that's a nice runtime you got there".format(hellomsg.f))
    
    def _sayHelloFuture(self,hellomsg):
        print("Python.sayHelloFuture called by: {0} with message: '{1}'".format(hellomsg.f,hellomsg))
        return create_hellomsgcontent("pythonpbhello responds: Howdy {0} that's a nice runtime you got there".format(hellomsg.f))
        
    def sayHelloPromise(self, hellomsg):
        print("Python.sayHelloPromise called by: {0} with message: '{1}'".format(hellomsg.f,hellomsg))
        with ThreadPoolExecutor(2) as executor:
            return executor.submit(self._sayHelloFuture,hellomsg)