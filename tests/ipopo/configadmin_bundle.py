#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining components managed by ConfigurationAdmin

:author: Thomas Calmant
"""

from pelix.constants import SERVICE_PID
from pelix.framework import BundleContext
from pelix.ipopo.constants import UPDATE_POLICY_RESTART
from pelix.ipopo.decorators import (
    ComponentFactory,
    HiddenProperty,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    RequiresConfiguration,
    Validate,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

FACTORY_BASIC = "ipopo.tests.configadmin.basic"
FACTORY_PID = "ipopo.tests.configadmin.pid"
FACTORY_GATED = "ipopo.tests.configadmin.gated"
FACTORY_OPTIONAL = "ipopo.tests.configadmin.optional"
FACTORY_OWN_PID = "ipopo.tests.configadmin.own_pid"
FACTORY_RESTART = "ipopo.tests.configadmin.restart"
FACTORY_NO_PID = "ipopo.tests.configadmin.no_pid"
FACTORY_HIDDEN = "ipopo.tests.configadmin.hidden"
FACTORY_UNDECLARED_PID = "ipopo.tests.configadmin.undeclared_pid"
FACTORY_UNSET_PID = "ipopo.tests.configadmin.unset_pid"

SPEC_BASIC = "ipopo.tests.configadmin.spec"
SPEC_UNDECLARED_PID = "ipopo.tests.configadmin.undeclared.spec"

PID_INSTANCE = "test.ipopo.ca.instance"
PID_GATED = "test.ipopo.ca.gated"
PID_OPTIONAL = "test.ipopo.ca.optional"
PID_OWN = "test.ipopo.ca.own"
PID_RESTART = "test.ipopo.ca.restart"
PID_HIDDEN = "test.ipopo.ca.hidden"
PID_UNDECLARED = "test.ipopo.ca.undeclared"

# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_BASIC)
@Provides(SPEC_BASIC)
@Property("_name", "name", "default")
class Basic:
    """
    Component instantiated from a factory configuration
    """

    _name: str

    def __init__(self) -> None:
        self.validated = 0
        self.invalidated = 0

    @Validate
    def validate(self, _: BundleContext) -> None:
        self.validated += 1

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        self.invalidated += 1


@ComponentFactory(FACTORY_PID)
@Property("_name", "name", "default")
@Property("_pid", SERVICE_PID, PID_INSTANCE)
@Instantiate("configadmin-pid")
class WithPid:
    """
    Component declaring its own configuration PID
    """

    _name: str
    _pid: str

    def __init__(self) -> None:
        self.validated = 0
        self.invalidated = 0

    @Validate
    def validate(self, _: BundleContext) -> None:
        self.validated += 1

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        self.invalidated += 1


@ComponentFactory(FACTORY_GATED)
@Property("_name", "name", "default")
@RequiresConfiguration(PID_GATED)
@Instantiate("configadmin-gated")
class Gated:
    """
    Component which requires a configuration to be validated
    """

    _name: str

    def __init__(self) -> None:
        self.validated = 0
        self.invalidated = 0

    @Validate
    def validate(self, _: BundleContext) -> None:
        self.validated += 1

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        self.invalidated += 1


@ComponentFactory(FACTORY_OPTIONAL)
@Property("_name", "name", "default")
@RequiresConfiguration(PID_OPTIONAL, optional=True)
@Instantiate("configadmin-optional")
class Optional:
    """
    Component which uses a configuration if there is one
    """

    _name: str

    def __init__(self) -> None:
        self.validated = 0
        self.invalidated = 0

    @Validate
    def validate(self, _: BundleContext) -> None:
        self.validated += 1

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        self.invalidated += 1


@ComponentFactory(FACTORY_OWN_PID)
@Property("_name", "name", "default")
@Property("_pid", SERVICE_PID)
@RequiresConfiguration()
@Instantiate("configadmin-own-pid", {SERVICE_PID: PID_OWN})
class OwnPid:
    """
    Component which gives the PID of its configuration in its properties
    """

    _name: str
    _pid: str

    def __init__(self) -> None:
        self.validated = 0
        self.invalidated = 0

    @Validate
    def validate(self, _: BundleContext) -> None:
        self.validated += 1

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        self.invalidated += 1


@ComponentFactory(FACTORY_RESTART)
@Property("_name", "name", "default")
@RequiresConfiguration(PID_RESTART, update_policy=UPDATE_POLICY_RESTART)
@Instantiate("configadmin-restart")
class Restarted:
    """
    Component invalidated then validated again on each configuration update
    """

    _name: str

    def __init__(self) -> None:
        self.validated = 0
        self.invalidated = 0

    @Validate
    def validate(self, _: BundleContext) -> None:
        self.validated += 1

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        self.invalidated += 1


@ComponentFactory(FACTORY_NO_PID)
@Property("_name", "name", "default")
@RequiresConfiguration()
@Instantiate("configadmin-no-pid")
class NoPid:
    """
    Component which requires a configuration but gives no PID at all
    """

    _name: str

    def __init__(self) -> None:
        self.validated = 0
        self.invalidated = 0

    @Validate
    def validate(self, _: BundleContext) -> None:
        self.validated += 1

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        self.invalidated += 1


@ComponentFactory(FACTORY_HIDDEN)
@Property("_name", "name", "default")
@HiddenProperty("_secret", "secret", "declared-secret")
@Property("_pid", SERVICE_PID, PID_HIDDEN)
@Instantiate("configadmin-hidden")
class Hidden:
    """
    Component with a hidden property, which a configuration must not modify
    """

    _name: str
    _secret: str
    _pid: str

    def __init__(self) -> None:
        self.validated = 0
        self.invalidated = 0

    @Validate
    def validate(self, _: BundleContext) -> None:
        self.validated += 1

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        self.invalidated += 1


@ComponentFactory(FACTORY_UNDECLARED_PID)
@Provides(SPEC_UNDECLARED_PID)
@Property("_name", "name", "default")
@Instantiate("configadmin-undeclared-pid", {SERVICE_PID: PID_UNDECLARED})
class UndeclaredPid:
    """
    Component whose configuration PID is given at instantiation, without any
    matching ``@Property`` declaration: the factory doesn't know that value
    """

    _name: str

    def __init__(self) -> None:
        self.validated = 0
        self.invalidated = 0

    @Validate
    def validate(self, _: BundleContext) -> None:
        self.validated += 1

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        self.invalidated += 1


@ComponentFactory(FACTORY_UNSET_PID)
@Property("_name", "name", "default")
@Property("_pid", SERVICE_PID)
@Instantiate("configadmin-unset-pid")
class UnsetPid:
    """
    Component which declares a ``service.pid`` property but is instantiated
    without giving it a value: it must not follow any configuration
    """

    _name: str
    _pid: str

    def __init__(self) -> None:
        self.validated = 0
        self.invalidated = 0

    @Validate
    def validate(self, _: BundleContext) -> None:
        self.validated += 1

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        self.invalidated += 1
