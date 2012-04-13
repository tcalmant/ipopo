#!/usr/bin/env python
#-- Content-Encoding: UTF-8 --
"""
Bundle defining multiple component factories for iPOPO tests

:author: Thomas Calmant
"""
from pelix.ipopo.constants import IPOPO_INSTANCE_NAME
from pelix.ipopo.decorators import ComponentFactory, Property, Provides, \
    Requires, Validate, Invalidate, Unbind, Bind, Instantiate
from pelix.ipopo.core import IPopoEvent
from pelix.framework import BundleContext
from tests.interfaces import IEchoService

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

FACTORY_A = "ipopo.tests.a"
FACTORY_B = "ipopo.tests.b"
PROP_USABLE = "usable"

# ------------------------------------------------------------------------------

# Auto-instantiated component (tests the decorator)
@ComponentFactory("basic-component-factory")
@Instantiate("basic-component")
@Provides("basic-component-svc")
class BasicComponent(object):
    """
    Dummy instantiated component
    """
    def __init__(self):
        """
        Constructor
        """
        self.states = []
        self.states.append(IPopoEvent.INSTANTIATED)


    @Validate
    def validate(self, context):
        """
        Validation
        """
        self.states.append(IPopoEvent.VALIDATED)


    @Invalidate
    def invalidate(self, context):
        """
        Invalidation
        """
        self.states.append(IPopoEvent.INVALIDATED)

# ------------------------------------------------------------------------------

# Inherited property
@Property("name", IPOPO_INSTANCE_NAME)
class TestComponentFactory(object):
    """
    Parent class of components
    """
    def __init__(self):
        """
        Constructor
        """
        self.name = None
        self.states = []
        self.states.append(IPopoEvent.INSTANTIATED)

    @Validate
    def validate(self, context):
        """
        Validation
        """
        self.states.append(IPopoEvent.VALIDATED)

    @Invalidate
    def invalidate(self, context):
        """
        Invalidation
        """
        self.states.append(IPopoEvent.INVALIDATED)


    def reset(self):
        """
        Resets the states list
        """
        del self.states[:]

# ------------------------------------------------------------------------------

@ComponentFactory(name=FACTORY_A)
@Property("usable", PROP_USABLE, True)
@Provides(specifications=IEchoService)
class ComponentFactoryA(TestComponentFactory, IEchoService):
    """
    Sample Component A
    """
    def echo(self, value):
        """
        Implementation of IEchoService
        """
        return value


    def change(self, usable):
        """
        Changes the usable property
        """
        self.usable = usable


@ComponentFactory(name=FACTORY_B)
@Requires(field="service", specification=IEchoService)
class ComponentFactoryB(TestComponentFactory):
    """
    Sample Component B
    """
    @Bind
    def bind(self, svc, svc_ref):
        """
        Bound
        """
        self.states.append(IPopoEvent.BOUND)

        # Assert that the service is already usable
        assert self.service.echo(True)

    @Unbind
    def unbind(self, svc):
        """
        Unbound
        """
        self.states.append(IPopoEvent.UNBOUND)

        # Assert that the service is still usable
        assert self.service.echo(True)

# ------------------------------------------------------------------------------

class ActivatorTest:
    """
    Test activator
    """

    def __init__(self):
        """
        Constructor
        """
        self.context = None


    def start(self, context):
        """
        Bundle started
        """
        assert isinstance(context, BundleContext)
        self.context = context

        global started
        started = True


    def stop(self, context):
        """
        Bundle stopped
        """
        assert isinstance(context, BundleContext)
        assert self.context is context

        global stopped
        stopped = True

# Prepare the activator
activator = ActivatorTest()
