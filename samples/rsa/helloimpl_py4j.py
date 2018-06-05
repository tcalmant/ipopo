from pelix.ipopo.decorators import Instantiate, ComponentFactory, Provides
from samples.rsa.helloimpl import HelloImpl
@ComponentFactory('helloimpl-py4j-factory')
@Provides('org.eclipse.ecf.examples.hello.IHello') # Provides IHello interface as specified by Java interface.  
#See <a href="https://github.com/ECF/Py4j-RemoteServicesProvider/blob/master/examples/org.eclipse.ecf.examples.hello/src/org/eclipse/ecf/examples/hello/IHello.java">IHello service interface</a>
@Instantiate('helloimpl-py4j', { 'service.exported.interfaces':'*', # Required for export                                         
                                 'service.exported.configs': 'ecf.py4j.host.python', # Required to use py4j python provider for export
                                 'service.intents': ['osgi.async'], # Required to use osgi.async intent
                                 'osgi.basic.timeout':30000}) # Timeout associated with remote calls (in ms)
class HelloImplPy4J(HelloImpl):
    '''
    All method impls handled by HelloImpl superclass
    '''
    pass