from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate
from samples.rsa.pbhelloimpl import PbHelloImpl

@ComponentFactory('pbhelloimpl-py4j-factory')
@Provides('org.eclipse.ecf.examples.protobuf.hello.IHello') # Provides IHello interface as specified by Java interface.  
#See <a href="https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/examples/org.eclipse.ecf.examples.protobuf.hello/src/org/eclipse/ecf/examples/protobuf/hello/IHello.java">IHello service interface</a>
@Instantiate('pbhelloimpl-py4j', { 'service.exported.interfaces':'*', 
                                   'service.exported.configs': 'ecf.py4j.host.python.pb', 
                                   'service.intents': ['osgi.async'], 
                                   'osgi.basic.timeout':120000})
class Py4jPbPythonHelloImpl(PbHelloImpl):
    '''
    All method impls handled by PbHelloImpl superclass
    '''
    pass