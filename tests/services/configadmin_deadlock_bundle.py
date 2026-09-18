#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining the components of the ConfigurationAdmin deadlock tests
(issue #114): managed services changing the properties of the services they
provide from their configuration callback.

:author: Thomas Calmant
"""

import threading
from typing import Any

from pelix import constants, services
from pelix.framework import BundleContext
from pelix.ipopo.constants import IPopoService
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Requires, Validate

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

FACTORY_MANAGED = "test-ca-deadlock-managed"
""" Factory of the managed service described in issue #114 """

FACTORY_VALIDATE = "test-ca-deadlock-validate"
""" Factory of the managed service which updates configurations when validated """

FACTORY_MSF = "test-ca-deadlock-msf"
""" Factory of the managed service factory """

FACTORY_CHILD = "test-ca-deadlock-child"
""" Factory of the components instantiated by the managed service factory """

SPEC_MANAGED = "test.ca.deadlock.managed"
SPEC_VALIDATE = "test.ca.deadlock.validate"
SPEC_MSF = "test.ca.deadlock.msf"
SPEC_CHILD = "test.ca.deadlock.child"

# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_MANAGED)
@Provides(SPEC_MANAGED)
@Property("_name", "name", "asd")
@Provides(services.SERVICE_CONFIGADMIN_MANAGED)
@Property("_service_pid", constants.SERVICE_PID, "any_pid")
class ManagedComponent:
    """
    The component of issue #114: its configuration callback changes a property
    of a service it provides
    """

    _name: str
    _service_pid: str

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Set each time updated() has returned
        self.updated_event = threading.Event()
        self.calls: list[dict[str, Any] | None] = []

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        # Changing a provided service property makes iPOPO fire a service event
        if properties is None:
            self._name = "None"
        else:
            self._name = properties.get("name", "None")

        self.calls.append(properties)
        self.updated_event.set()


@ComponentFactory(FACTORY_VALIDATE)
@Requires("_config_admin", services.IConfigurationAdmin)
@Provides(SPEC_VALIDATE)
@Property("_name", "name", "initial")
@Property("_other_pid", "other.pid", None)
@Provides(services.SERVICE_CONFIGADMIN_MANAGED)
@Property("_service_pid", constants.SERVICE_PID, "validate_pid")
class ValidateComponent:
    """
    Rarer variant of issue #114: the component uses ConfigurationAdmin while
    being validated and changes its provided properties
    """

    _config_admin: services.IConfigurationAdmin
    _name: str
    _other_pid: str | None
    _service_pid: str

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.updated_event = threading.Event()
        self.validated = threading.Event()
        self.calls: list[dict[str, Any] | None] = []

    @Validate
    def _validate(self, _: BundleContext) -> None:
        """
        Component validated: updates configurations from the iPOPO callback
        """
        self._name = "validating"

        # Its own configuration: its service is not registered yet
        self._config_admin.get_configuration(self._service_pid).update({"name": "from-validate"})

        if self._other_pid:
            # A managed service which is already registered: it is notified
            # synchronously, in this thread
            self._config_admin.get_configuration(self._other_pid).update({"name": "from-other-validate"})

        self.validated.set()

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        """
        Component invalidated
        """
        self.validated.clear()

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        if properties is not None:
            self._name = properties.get("name", "None")

        self.calls.append(properties)
        self.updated_event.set()


@ComponentFactory(FACTORY_CHILD)
@Provides(SPEC_CHILD)
@Property("_config_pid", "config.pid", None)
@Property("_value", "value", None)
class ChildComponent:
    """
    Component instantiated by the managed service factory
    """

    _config_pid: str | None
    _value: Any


@ComponentFactory(FACTORY_MSF)
@Requires("_ipopo", IPopoService)
@Provides(SPEC_MSF)
@Property("_count", "count", 0)
@Provides(services.SERVICE_CONFIGADMIN_MANAGED_FACTORY)
@Property("_factory_pid", constants.SERVICE_PID, "any_factory_pid")
class ManagedFactoryComponent:
    """
    Managed service factory which changes its provided properties and
    instantiates a component for each configuration
    """

    _ipopo: IPopoService
    _count: int
    _factory_pid: str

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.updated_event = threading.Event()
        self.deleted_event = threading.Event()

        # Configuration PID -> properties
        self.configurations: dict[str, dict[str, Any] | None] = {}

    def get_name(self) -> str:
        """
        Returns the name of the factory
        """
        return self._factory_pid

    def updated(self, pid: str, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        self._count += 1
        self.configurations[pid] = properties

        value = (properties or {}).get("value")
        try:
            instance = self._ipopo.get_instance(pid)
        except KeyError:
            # First configuration: instantiate the component it describes
            self._ipopo.instantiate(FACTORY_CHILD, pid, {"config.pid": pid, "value": value})
        else:
            instance._value = value

        self.updated_event.set()

    def deleted(self, pid: str) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        self._count += 1
        self.configurations.pop(pid, None)

        try:
            self._ipopo.kill(pid)
        except ValueError:
            # Unknown instance
            pass

        self.deleted_event.set()
