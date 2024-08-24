#!/usr/bin/env python3
"""
Implementation of a component that consumes an Hello World service
"""

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Invalidate, Requires, Validate

from specification import HelloWorld


# Manipulates the class and sets its (unique) factory name
@ComponentFactory("hello-consumer-factory")
# Indicate that the components require a sample.hello service to work
# and to inject the found service in the _svc field
# We could also use the specification name instead of the type
@Requires("_svc", HelloWorld)
# Tell iPOPO to instantiate a component instance as soon as the file is loaded
@Instantiate("hello-consumer-auto")
class HelloConsumer:
    """
    A sample service consumer
    """

    # Define the injected field type for static typing (optional)
    _svc: HelloWorld

    @Validate
    def validate(self, context):
        """
        Component validated: all its requirements have been injected
        """
        self._svc.hello("Consumer")

    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated: one of its requirements is going away
        """
        self._svc.bye("Consumer")
