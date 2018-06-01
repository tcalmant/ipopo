# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate
# Manipulates the class and sets its (unique) factory name
@ComponentFactory("helloimpl-provider-factory")
# Indicate that the components will provide a service
@Provides("sample.hello")
# Tell iPOPO to instantiate a component instance as soon as the file is loaded
@Instantiate("helloimpl-provider-auto")
# A component class must always inherit from object (new-style class)
class HelloImpl(object):

    def hello(self, name='Not given'):
        print("Service received:  Hello from {0} to HelloImpl".format(name))
        return "HelloImpl2 responds 'hi' to "+name
 
    