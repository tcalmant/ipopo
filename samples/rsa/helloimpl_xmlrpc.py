from pelix.ipopo.decorators import Instantiate, ComponentFactory, Provides
from samples.rsa.helloimpl import HelloImpl
@ComponentFactory('helloimpl-xmlrpc-factory')
@Provides('org.eclipse.ecf.examples.hello.IHello') # Provides IHello interface as specified by Java interface.  
#See <a href="https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/examples/org.eclipse.ecf.examples.hello/src/org/eclipse/ecf/examples/hello/IHello.java">IHello service interface</a>
@Instantiate('helloimpl-xmlrpc', { 'service.intents': ['osgi.async'], # Required to use osgi.async intent
                                   'osgi.basic.timeout':60000}) 
class XmlRpcHelloImpl(HelloImpl):
    '''
    All method impls handled by HelloImpl superclass
    '''
    pass