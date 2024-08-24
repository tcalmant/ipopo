#!/usr/bin/env python3
"""
Implementation of a component that provides the Hello World service
"""

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Provides

# Import the specification, if we want to use its type
from specification import HelloWorld


# Manipulates the class and sets its (unique) factory name
@ComponentFactory("hello-provider-factory")
# Indicate that the components will provide a service
@Provides(HelloWorld)
# Like in iPOPOv1, We could also use the specification name directly:
# @Provides("sample.hello")
# Tell iPOPO to instantiate a component instance as soon as the file is loaded
@Instantiate("hello-provider-auto")
# When using Python protocols, it is recommended to inherit from it to
# benefit from types handling of IDEs.
class HelloProvider(HelloWorld):
    """
    A sample service provider
    """

    def hello(self, name="world"):
        """
        Says hello
        """
        print("Hello,", name, "!")

    def bye(self, name="cruel world"):
        """
        Says bye
        """
        print("Bye,", name, "!")
