#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining multiple component factories for iPOPO tests

:author: Thomas Calmant
"""

from pelix.constants import BundleActivator, FrameworkException
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo.constants import IPOPO_INSTANCE_NAME, IPopoEvent
from pelix.ipopo.decorators import (
    Bind,
    ComponentFactory,
    HiddenProperty,
    Instantiate,
    Invalidate,
    PostRegistration,
    PostUnregistration,
    Property,
    Provides,
    Requires,
    RequiresBest,
    RequiresBroadcast,
    RequiresMap,
    RequiresVarFilter,
    Temporal,
    Unbind,
    Validate,
)
from tests.interfaces import IEchoService

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

BASIC_FACTORY = "basic-component-factory"
BASIC_INSTANCE = "basic-component"

MAP_SPEC_TEST = "map.spec.test"
FACTORY_MAP = "ipopo.tests.map"

FACTORY_A = "ipopo.tests.a"
FACTORY_B = "ipopo.tests.b"
FACTORY_C = "ipopo.tests.c"
FACTORY_IMMEDIATE = "ipopo.tests.immediate"
FACTORY_PROVIDES_SVC_FACTORY = "ipopo.tests.provides.factory"
FACTORY_PROVIDES_SVC_PROTOTYPE = "ipopo.tests.provides.prototype"
FACTORY_REQUIRES_BEST = "ipopo.tests.best"
FACTORY_REQUIRES_BROADCAST = "ipopo.tests.broadcast"
FACTORY_REQUIRES_BROADCAST_REQUIRED = "ipopo.tests.broadcast.required"
FACTORY_REQUIRES_BROADCAST_UNMUFFLED = "ipopo.tests.broadcast.unmuffled"
FACTORY_REQUIRES_VAR_FILTER = "ipopo.tests.var_filter"
FACTORY_REQUIRES_VAR_FILTER_AGGREGATE = "ipopo.tests.var_filter.multiple"
FACTORY_TEMPORAL = "ipopo.tests.temporal"
FACTORY_ERRONEOUS = "ipopo.tests.erroneous"
FACTORY_HIDDEN_PROPS = "ipopo.tests.properties.hidden"
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
        """ "
        Constructor
        """
        TestComponentFactory.__init__(self)
        self.usable = True
        self.prop_1 = 10
        self._test_ctrl = True
        self.calls_register = []
        self.calls_unregister = []

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

    @PostRegistration
    def post_reg(self, svc_ref):
        """
        Tests the Post-Registration decorator
        """
        self.calls_register.append(svc_ref)

    @PostUnregistration
    def post_unreg(self, svc_ref):
        """
        Tests the Post-Unregistration decorator
        """
        self.calls_unregister.append(svc_ref)


@ComponentFactory(name=FACTORY_B)
@Requires(field="service", specification=IEchoService)
class ComponentFactoryB(TestComponentFactory):
    """
    Sample Component B
    """

    def __init__(self):
        """ "
        Constructor
        """
        super(ComponentFactoryB, self).__init__()
        self.service: IEchoService = None  # type: ignore
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
@Requires(field="services", specification=IEchoService, aggregate=True, optional=True)
class ComponentFactoryC(TestComponentFactory):
    """
    Sample component C
    """

    def __init__(self):
        """ "
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
@RequiresMap("single", MAP_SPEC_TEST, "single.key", False)
@RequiresMap("multiple", MAP_SPEC_TEST, "other.key", False, aggregate=True, optional=True)
@RequiresMap("single_none", MAP_SPEC_TEST, "single.key", True)
@RequiresMap("multiple_none", MAP_SPEC_TEST, "other.key", True, aggregate=True, optional=True)
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


@ComponentFactory(FACTORY_IMMEDIATE)
@Requires("service", IEchoService, immediate_rebind=True)
class ImmediateComponentFactory(TestComponentFactory):
    """
    Component factory with a immediate_rebind flag
    """

    @Bind
    def bind(self, svc, svc_ref):
        """
        Bound
        """
        self.states.append(IPopoEvent.BOUND)

    @Unbind
    def unbind(self, svc, svc_ref):
        """
        Unbound
        """
        self.states.append(IPopoEvent.UNBOUND)


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_REQUIRES_BEST)
@RequiresBest("service", IEchoService)
class RequiresBestComponentFactory(TestComponentFactory):
    """
    Component factory with a RequiresBest requirement
    """

    @Bind
    def bind(self, svc, svc_ref):
        """
        Bound
        """
        self.states.append(IPopoEvent.BOUND)

    @Unbind
    def unbind(self, svc, svc_ref):
        """
        Unbound
        """
        self.states.append(IPopoEvent.UNBOUND)


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_REQUIRES_BROADCAST)
@RequiresBroadcast("service", IEchoService)
class RequiresBroadcastComponentFactory(TestComponentFactory):
    """
    Component factory with a RequiresBroadcast requirement with the default
    flags
    """


@ComponentFactory(FACTORY_REQUIRES_BROADCAST_REQUIRED)
@RequiresBroadcast("service", IEchoService, optional=False)
class RequiresBroadcastRequiredComponentFactory(TestComponentFactory):
    """
    Component factory with a RequiresBroadcast requirement, without the
    optional flag
    """


@ComponentFactory(FACTORY_REQUIRES_BROADCAST_UNMUFFLED)
@RequiresBroadcast("service", IEchoService, muffle_exceptions=False)
class RequiresBroadcastUnMuffleComponentFactory(TestComponentFactory):
    """
    Component factory with a RequiresBroadcast requirement, without the muffle
    exceptions flag
    """


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_REQUIRES_VAR_FILTER)
@RequiresVarFilter("service", IEchoService, spec_filter="(&(s={static})(a={answer}))")
@Property("answer", "answer", 42)
class RequiresVarFilterComponentFactory(TestComponentFactory):
    """
    Component factory with a RequiresVarFilter requirement
    """

    @Bind
    def bind(self, svc, svc_ref):
        """
        Bound
        """
        self.states.append(IPopoEvent.BOUND)

    def change(self, new_value):
        """
        Changes the filter property
        """
        self.answer = new_value

    @Unbind
    def unbind(self, svc, svc_ref):
        """
        Unbound
        """
        self.states.append(IPopoEvent.UNBOUND)


@ComponentFactory(FACTORY_REQUIRES_VAR_FILTER_AGGREGATE)
@RequiresVarFilter("service", IEchoService, aggregate=True, spec_filter="(&(s={static})(a={answer}))")
@Property("answer", "answer", 42)
class RequiresVarFilterAggregateComponentFactory(TestComponentFactory):
    """
    Component factory with a RequiresVarFilter requirement
    """

    @Bind
    def bind(self, svc, svc_ref):
        """
        Bound
        """
        self.states.append(IPopoEvent.BOUND)

    def change(self, new_value):
        """
        Changes the filter property
        """
        self.answer = new_value

    @Unbind
    def unbind(self, svc, svc_ref):
        """
        Unbound
        """
        self.states.append(IPopoEvent.UNBOUND)


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_TEMPORAL)
@Temporal("service", IEchoService, timeout=2)
class TemporalComponentFactory(TestComponentFactory):
    """
    Component factory with a temporal requirement
    """

    service: IEchoService

    @Bind
    def bind(self, svc: IEchoService, svc_ref: ServiceReference[IEchoService]):
        """
        Bound
        """
        self.states.append(IPopoEvent.BOUND)

    @Unbind
    def unbind(self, svc: IEchoService, svc_ref: ServiceReference[IEchoService]):
        """
        Unbound
        """
        self.states.append(IPopoEvent.UNBOUND)

    def call(self):
        """
        Calls the service
        """
        return self.service.method()


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_ERRONEOUS)
@Property("raise_exception", "erroneous", True)
class ErroneousComponentFactory(TestComponentFactory):
    """
    Component factory with a immediate_rebind flag
    """

    def __init__(self):
        """
        Sets up members
        """
        super(ErroneousComponentFactory, self).__init__()
        self.raise_exception = True

    @Validate
    def validate(self, context: BundleContext):
        """
        Validation
        """
        if self.raise_exception:
            raise OSError("Error raised")
        else:
            super(ErroneousComponentFactory, self).validate(context)


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_HIDDEN_PROPS)
@HiddenProperty("hidden", "hidden.prop", "hidden")
@Property("public", "public.prop", "public")
class HiddenPropTest(object):
    """
    Test for hidden properties
    """

    def __init__(self):
        """
        Sets up members
        """
        self.hidden = None
        self.public = None


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_PROVIDES_SVC_FACTORY)
@Provides("factory.service", factory=True)
class SvcFactoryProvider(object):
    """
    Test for providing a service factory
    """

    def __init__(self):
        """
        Sets up members
        """
        self.caller = None
        self.registration = None
        self.service = None

    def get_service(self, bundle, svc_registration):
        self.caller = bundle
        self.registration = svc_registration
        self.service = object()
        return self.service

    def unget_service(self, bundle, svc_registration):
        self.caller = bundle
        self.registration = svc_registration
        self.service = None


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_PROVIDES_SVC_PROTOTYPE)
@Provides("prototype.service", prototype=True)
class SvcPrototypeFactoryProvider(object):
    """
    Test for providing a prototype service factory
    """

    def __init__(self):
        """
        Sets up members
        """
        self.caller = None
        self.registration = None
        self.flag_unget_instance = False
        self.flag_unget_service = False
        self.services = []

    def get_service(self, bundle, svc_registration):
        self.caller = bundle
        self.registration = svc_registration
        svc = object()
        self.services.append(svc)
        return svc

    def unget_service_instance(self, bundle, svc_registration, service):
        """
        Called when a bundle releases an instance of the service
        """
        self.flag_unget_instance = True
        self.caller = bundle
        self.registration = svc_registration
        self.services.remove(service)

    def unget_service(self, bundle, svc_registration):
        self.flag_unget_service = True
        self.caller = bundle
        self.registration = svc_registration
        del self.services[:]


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


# ------------------------------------------------------------------------------
# Inheritance tests


class GrandMother(object):
    """
    Parent class of Mother class: must not appear in specifications
    """

    pass


class Mother(GrandMother):
    """
    Direct parent class: must appear in specifications
    """

    pass


class Father(object):
    """
    Direct parent class: must appear in specifications
    """

    pass


class Child(Father, Mother):
    """
    Implementation class: must not appear in specifications
    """

    pass
