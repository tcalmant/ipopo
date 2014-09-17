#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining multiple component factories for iPOPO tests

:author: Thomas Calmant
"""

# Pelix
from pelix.constants import BundleActivator, FrameworkException
from pelix.framework import BundleContext

# iPOPO
from pelix.ipopo.decorators import ComponentFactory, Property, Provides, \
    Requires, Validate, Invalidate, Unbind, Bind, Instantiate, RequiresMap
from pelix.ipopo.constants import IPOPO_INSTANCE_NAME, IPopoEvent

# Tests
from tests.interfaces import IEchoService

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

BASIC_FACTORY = "basic-component-factory"
BASIC_INSTANCE = "basic-component"

MAP_SPEC_TEST = "map.spec.test"
FACTORY_MAP = "ipopo.tests.map"

FACTORY_A = "ipopo.tests.a"
FACTORY_B = "ipopo.tests.b"
FACTORY_C = "ipopo.tests.c"
PROP_USABLE = "usable"

# ------------------------------------------------------------------------------
# Auto-instantiated component (tests the decorator)


@ComponentFactory(BASIC_FACTORY)
@Instantiate(BASIC_INSTANCE)
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
        self.ref = None
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
@Property("prop_1", "prop.1")
@Provides(specifications=IEchoService)
@Provides(specifications="TestService", controller="_test_ctrl")
@Requires("_req_1", "dummy", optional=True)
class ComponentFactoryA(TestComponentFactory, IEchoService):
    """
    Sample Component A
    """
    def __init__(self):
        """"
        Constructor
        """
        TestComponentFactory.__init__(self)
        self.usable = True
        self.prop_1 = 10
        self._test_ctrl = True

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

    def change_controller(self, value):
        """
        Change the controller value
        """
        self._test_ctrl = value


@ComponentFactory(name=FACTORY_B)
@Requires(field="service", specification=IEchoService)
class ComponentFactoryB(TestComponentFactory):
    """
    Sample Component B
    """
    def __init__(self):
        """"
        Constructor
        """
        super(ComponentFactoryB, self).__init__()
        self.service = None
        self.raiser = False
        self.fw_raiser = False
        self.fw_raiser_stop = False

    @Bind
    def bind(self, svc, svc_ref):
        """
        Bound
        """
        self.states.append(IPopoEvent.BOUND)
        self.ref = svc_ref

        # Assert that the service is already usable
        assert self.service.echo(True)

        if self.fw_raiser:
            raise FrameworkException("FrameworkException", self.fw_raiser_stop)

        if self.raiser:
            raise Exception("Some exception")

    @Unbind
    def unbind(self, svc, svc_ref):
        """
        Unbound
        """
        self.states.append(IPopoEvent.UNBOUND)

        # Assert that the service is still usable
        assert self.service.echo(True)
        assert self.ref is svc_ref
        self.ref = None

        if self.fw_raiser:
            raise FrameworkException("FrameworkException", self.fw_raiser_stop)

        if self.raiser:
            raise Exception("Some exception")


@ComponentFactory(name=FACTORY_C)
@Requires(field="services", specification=IEchoService, aggregate=True,
          optional=True)
class ComponentFactoryC(TestComponentFactory):
    """
    Sample component C
    """
    def __init__(self):
        """"
        Constructor
        """
        super(ComponentFactoryC, self).__init__()
        self.services = None

    @Bind
    def bind(self, svc, svc_ref):
        """
        Bound
        """
        self.states.append(IPopoEvent.BOUND)

        # Assert that the service is already usable
        assert svc in self.services

    @Unbind
    def unbind(self, svc, svc_ref):
        """
        Unbound
        """
        self.states.append(IPopoEvent.UNBOUND)

        # Assert that the service has been removed
        assert svc in self.services

# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_MAP)
@RequiresMap('single', MAP_SPEC_TEST, 'single.key', False)
@RequiresMap('multiple', MAP_SPEC_TEST, 'other.key', False,
             aggregate=True, optional=True)
@RequiresMap('single_none', MAP_SPEC_TEST, 'single.key', True)
@RequiresMap('multiple_none', MAP_SPEC_TEST, 'other.key', True,
             aggregate=True, optional=True)
class MapComponentFactory(TestComponentFactory):
    """
    Sample RequiresMap component
    """
    def __init__(self):
        """
        Sets up members
        """
        super(MapComponentFactory, self).__init__()

        self.single = None
        self.multiple = None

        self.single_none = None
        self.multiple_none = None

# ------------------------------------------------------------------------------


@BundleActivator
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
