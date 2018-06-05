from concurrent.futures.thread import ThreadPoolExecutor

class HelloImpl(object):
    '''
    Implementation of Java org.eclipse.ecf.examples.hello.IHello service interface.
    This interface declares on normal/synchronous method ('sayHello') and two
    async methods as defined by the OSGi Remote Services osgi.async intent.  Note
    that the service.intents property above includes the 'osgi.async' intent.  It
    also declares a property 'osgi.basic.timeout' which will be used to assure that
    the remote methods timeout after the given number of milliseconds.
    
    See the OSGi Remote Services specification at
    
    https://osgi.org/specification/osgi.cmpn/7.0.0/service.remoteservices.html
    
    The specification defines the standard properties given above.
    
    '''
    def sayHello(self, name='Not given', message = 'nothing'):
        '''
        Synchronous implementation of IHello.sayHello synchronous method.  The remote
        calling thread will be blocked until this is executed and responds
        '''
        print("Python.sayHello called by: {0} with message: '{1}'".format(name,message))
        return "PythonSync says: Howdy {0} that's a nice runtime you got there".format(name)
    
    def sayHelloAsync(self, name='Not given', message = 'nothing'):
        '''
        Implementation of IHello.sayHelloAsync.  This method will be executed via 
        some thread, and the remote caller will not block.  This method should return
        either a String result (since the return type of IHello.sayHelloAsync is
        CompletableFuture<String>, OR a Future that returns a python string.  In this case,
        it returns the string directly.
        '''
        print("Python.sayHelloAsync called by: {0} with message: '{1}'".format(name,message))
        return "PythonAsync says: Howdy {0} that's a nice runtime you got there".format(name)

    def _sayHelloFuture(self, name, message):
        '''
        Function that is executed via a Future in 'sayHelloPromise'.
        '''
        print("Python._sayHelloFuture called by: {0} with message: '{1}'".format(name,message))
        return "PythonFuture says: Howdy {0} that's a nice runtime you got there".format(name)
    
    def sayHelloPromise(self, name='Not given', message = 'nothing'):
        '''
        This method in IHello java interface has return type Promise<String>.  It can either return
        a string directly, or return a Future that results in a string.  In this case,
        a Future is submitted and returned.   
        '''
        # Use thread pool executor
        with ThreadPoolExecutor(2) as executor:
            # submit self_sayHelloFuture method and return Future
            return executor.submit(self._sayHelloFuture, name, message)
