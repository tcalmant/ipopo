from pelix.ipopo.decorators import ComponentFactory,Instantiate,Requires,Validate

@ComponentFactory("remote-hello-consumer-factory")
# The '(service.imported=*)' filter only allows remote services to be injected
@Requires("_helloservice", "org.eclipse.ecf.examples.hello.IHello", False, False, "(service.imported=*)", False)
@Instantiate("remote-hello-consumer")
class RemoteHelloConsumer(object):
    
    def __init__(self):
        self._helloservice = None
        self._name = 'Python'
        self._msg = 'Hello Java'
        
    @Validate
    def _validate(self,bundle_context):
        # call it!
        resp = self._helloservice.sayHello(self._name+'Sync', self._msg)
        print("{0} IHello service consumer received sync response: {1}".format(self._name,resp))
        # call sayHelloAsync which returns Future and we add lambda to print the result when done
        self._helloservice.sayHelloAsync(self._name+'Async', self._msg).add_done_callback(lambda f: print('async response: {0}'.format(f.result())))
        print("done with sayHelloAsync method")
        # call sayHelloAsync which returns Future and we add lambda to print the result when done
        self._helloservice.sayHelloPromise(self._name+'Promise', self._msg).add_done_callback(lambda f: print('promise response: {0}'.format(f.result())))
        print("done with sayHelloPromise method")

    
    