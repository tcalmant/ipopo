#!/usr/bin/python3
"""
Provides the implementation of the Hello service, reused in RSA samples
"""


class HelloImpl:
    """
    Implementation of Java org.eclipse.ecf.examples.hello.IHello service
    interface.
    This interface declares on normal/synchronous method ('sayHello') and two
    async methods as defined by the OSGi Remote Services osgi.async intent.

    Note that the service.intents property above includes the 'osgi.async'
    intent. It also declares a property 'osgi.basic.timeout' which will be used
    to assure that the remote methods timeout after the given number of
    milliseconds.

    See the OSGi Remote Services specification at:
    https://docs.osgi.org/specification/osgi.cmpn/7.0.0/service.remoteservices.html

    The specification defines the standard properties given above.
    """

    def sayHello(self, name: str = "Not given", message: str = "nothing") -> str:
        """
        Synchronous implementation of IHello.sayHello synchronous method.
        The remote calling thread will be blocked until this is executed and
        responds.
        """
        print(f"Python.sayHello called by: {name} with message: '{message}'")
        return f"PythonSync says: Howdy {name} that's a nice runtime you got there"

    def sayHelloAsync(self, name: str = "Not given", message: str = "nothing") -> str:
        """
        Implementation of IHello.sayHelloAsync.
        This method will be executed via some thread, and the remote caller
        will not block.
        This method should return either a String result (since the return type
        of IHello.sayHelloAsync is CompletableFuture<String>, OR a Future that
        returns a python string.  In this case, it returns the string directly.
        """
        print(f"Python.sayHelloAsync called by: {name} with message: '{message}'")
        return f"PythonAsync says: Howdy {name} that's a nice runtime you got there"

    def sayHelloPromise(self, name: str = "Not given", message: str = "nothing") -> str:
        """
        Implementation of IHello.sayHelloPromise.
        This method will be executed via some thread, and the remote caller
        will not block.
        """
        print(f"Python.sayHelloPromise called by: {name} with message: '{message}'")
        return f"PythonPromise says: Howdy {name} that's a nice runtime you got there"
