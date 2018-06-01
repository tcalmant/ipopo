from pelix.ipopo.decorators import ComponentFactory,Instantiate,Requires,Validate

@ComponentFactory("remote-hello-consumer-factory")
# The '(service.imported=*)' filter only allows remote hello service proxies to be injected
@Requires("_helloservice", "org.eclipse.ecf.examples.hello.IHello", False, False, "(service.imported=*)", False)
@Instantiate("hello-consumer")
class HelloConsumer(object):
    
    def __init__(self):
        self._helloservice = None
        self._name = 'Python'
        self._message = 'Hello Java'
        
    @Validate
    def _validate(self,bcontext):
        # call it!
        resp = self._helloservice.sayHello(self._name, self._message)
        print("{0} IHello service consumer received response: {1}".format(self._name,resp))
    