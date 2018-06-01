# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory,Instantiate,Requires,Validate,Property

@ComponentFactory("remote-hello-consumer-factory")
# The '(service.imported=*)' filter only allows remote hello service proxies to be injected
@Requires("_helloservice", "sample.hello", False, False, "(service.imported=*)", False)
@Property("_name","helloconsumer.name","Scott")
@Instantiate("hello-consumer")
class HelloConsumer(object):
    
    def __init__(self):
        self._helloservice = None
        self._name = None
        
    @Validate
    def _validate(self,ctxt):
        # call it!
        print("Consumer received: {0}".format(self._helloservice.hello(self._name)))
    