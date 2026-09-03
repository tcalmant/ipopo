#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bridge between ConfigurationAdmin and iPOPO

Lets an administrator manage a composition at runtime: each factory
configuration created with the ``pelix.ipopo.component`` PID describes a
component instance, and any component declaring a ``service.pid`` property is
reconfigured by the configuration with that PID.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.2.2

..

    Copyright 2026 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import itertools
import logging
import threading
from typing import Any, NamedTuple

from pelix import services
from pelix.constants import SERVICE_PID
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceRegistration
from pelix.ipopo.constants import (
    HANDLER_CONFIGADMIN,
    IPOPO_CONFIG_FACTORY_NAME,
    IPOPO_CONFIG_UPDATE_POLICY,
    IPOPO_CONFIGADMIN_FACTORY_PID,
    IPOPO_INSTANCE_NAME,
    UPDATE_POLICY_RESTART,
    IPopoEvent,
    IPopoEventListener,
    IPopoService,
    IPopoWaitingList,
)
from pelix.ipopo.decorators import (
    ComponentFactory,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    Requires,
    Validate,
)

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

_MANAGED_SPECIFICATIONS = frozenset(
    (
        services.SERVICE_CONFIGADMIN_MANAGED,
        services.SERVICE_CONFIGADMIN_MANAGED_FACTORY,
    )
)
""" Specifications of the components which handle their configuration themselves """

_CONFIG_DIRECTIVES = frozenset((IPOPO_CONFIG_FACTORY_NAME, IPOPO_CONFIG_UPDATE_POLICY))
""" Configuration entries which drive the bridge and are not component properties """

# ------------------------------------------------------------------------------


def _factory_defaults(ipopo: IPopoService, factory: str, keys: set[str]) -> dict[str, Any]:
    """
    Returns the values declared by a factory for the given property names.
    A missing property maps to None; a dot-prefixed key (e.g. ``.password``)
    maps to the declared default of the ``@HiddenProperty`` named without its
    leading dot.

    :param ipopo: The iPOPO service
    :param factory: Name of a component factory
    :param keys: Names of the properties to look for
    :return: A dictionary: property name -> declared value
    """
    try:
        details = ipopo.get_factory_details(factory)
        declared = details["properties"]
        hidden_declared = details["hidden_properties"]
    except ValueError:
        # Factory has gone away
        declared = {}
        hidden_declared = {}

    result: dict[str, Any] = {}
    for key in keys:
        if key.startswith(".") and key[1:] in hidden_declared:
            result[key] = hidden_declared[key[1:]]
        else:
            result[key] = declared.get(key)
    return result


# ------------------------------------------------------------------------------


class _ComponentConfig(NamedTuple):
    """
    Description of the component asked for by a factory configuration
    """

    factory: str
    """ Name of the iPOPO component factory """

    name: str
    """ Name of the component instance """

    properties: dict[str, Any]
    """ Properties given by the configuration """

    restart: bool
    """ True if an update of the configuration must restart the component """


@ComponentFactory("ipopo-configadmin-instantiator-factory")
@Provides(services.IManagedServiceFactory)
@Property("_pid", SERVICE_PID, IPOPO_CONFIGADMIN_FACTORY_PID)
@Requires("_ipopo", IPopoService)
@Requires("_waiting", IPopoWaitingList)
@Instantiate("ipopo-configadmin-instantiator")
class ConfigAdminInstantiator(services.IManagedServiceFactory):
    """
    Instantiates a component per factory configuration of the
    ``pelix.ipopo.component`` PID, through the iPOPO waiting list.
    """

    # Injected services
    _ipopo: IPopoService
    _waiting: IPopoWaitingList

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Handled PID of this managed service factory
        self._pid: str = IPOPO_CONFIGADMIN_FACTORY_PID

        # Configuration PID -> component described by the configuration
        self._wanted: dict[str, _ComponentConfig] = {}

        # Configuration PID -> component which has been created for it
        self._applied: dict[str, _ComponentConfig] = {}

        # PIDs a thread is currently working on
        self._applying: set[str] = set()

        # True between the validation and the invalidation of the component
        self._active = False

        # Protects the state above. It is never held while calling iPOPO:
        # instantiating or killing a component runs its callbacks, which can
        # notify this service back from another thread
        self.__lock = threading.Lock()

    @Validate
    def _validate(self, _: BundleContext) -> None:
        """
        Component validated
        """
        with self.__lock:
            self._active = True

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        """
        Component invalidated: kill the components created from configurations,
        as ConfigurationAdmin doesn't notify the deletion of this service
        """
        with self.__lock:
            self._active = False
            pids = set(self._wanted).union(self._applied)

        for pid in pids:
            self.__reconcile(pid, None)

    def get_name(self) -> str:
        """
        Returns the PID of this managed service factory
        """
        return self._pid

    def updated(self, pid: str, properties: dict[str, Any] | None) -> None:
        """
        A configuration describing a component has been created or updated

        :param pid: PID of the configuration
        :param properties: Properties of the configuration
        """
        if properties is None:
            self.deleted(pid)
            return

        factory = properties.get(IPOPO_CONFIG_FACTORY_NAME)
        if not factory:
            _logger.error(
                "Configuration %s doesn't give the name of the iPOPO factory to instantiate (%s)",
                pid,
                IPOPO_CONFIG_FACTORY_NAME,
            )

            # The configuration doesn't describe a component anymore: an
            # update replaces the whole set of properties, so the factory name
            # can be dropped by a caller which forgot to give it back
            self.deleted(pid)
            return

        self.__reconcile(
            pid,
            _ComponentConfig(
                factory,
                # The instance name defaults to the configuration PID
                properties.get(IPOPO_INSTANCE_NAME) or pid,
                # The entries driving the bridge are directives, not component
                # properties
                {key: value for key, value in properties.items() if key not in _CONFIG_DIRECTIVES},
                properties.get(IPOPO_CONFIG_UPDATE_POLICY) == UPDATE_POLICY_RESTART,
            ),
        )

    def deleted(self, pid: str) -> None:
        """
        A configuration describing a component has been deleted: kill it

        :param pid: PID of the configuration
        """
        self.__reconcile(pid, None)

    def __reconcile(self, pid: str, wanted: _ComponentConfig | None) -> None:
        """
        Makes the running components match the configuration with the given
        PID. Only one thread works on a given PID at a time: a concurrent
        call just stores the new target state, which that thread picks up
        before returning. Never holds the lock across an iPOPO call, since a
        component callback can notify this service back from another thread.

        :param pid: PID of the configuration
        :param wanted: The component the configuration asks for, None if the
                       configuration is gone
        """
        with self.__lock:
            if wanted is None:
                self._wanted.pop(pid, None)
            elif not self._active:
                # Ignore: received after invalidation, the component must not
                # outlive this service
                return
            else:
                self._wanted[pid] = wanted

            if pid in self._applying:
                # Another thread is on it, it will see the new target state
                return

            self._applying.add(pid)

        try:
            while True:
                with self.__lock:
                    target = self._wanted.get(pid)
                    current = self._applied.get(pid)
                    if target == current:
                        self._applying.discard(pid)
                        return

                applied, forget = self.__apply(current, target)

                with self.__lock:
                    if applied is None:
                        self._applied.pop(pid, None)
                    else:
                        self._applied[pid] = applied

                    if forget and self._wanted.get(pid) is target:
                        # Couldn't apply the configuration: align the target
                        # on what's running, else this would retry forever
                        if applied is None:
                            del self._wanted[pid]
                        else:
                            self._wanted[pid] = applied
        except BaseException:
            with self.__lock:
                self._applying.discard(pid)
            raise

    def __apply(
        self, current: _ComponentConfig | None, target: _ComponentConfig | None
    ) -> tuple[_ComponentConfig | None, bool]:
        """
        Applies a change of configuration. Doesn't raise exceptions.

        :param current: The component which is running, None if there is none
        :param target: The component to run, None to kill the running one
        :return: The component running afterwards (None if none), and whether
                 the target state must be given up and aligned on it instead
        """
        if target is None:
            # Configuration deleted
            if current is not None:
                self.__remove(current.name)
            return None, False

        if (
            current is None
            or current.factory != target.factory
            or current.name != target.name
            or target.restart
        ):
            # Nothing running yet, or a component which must be created again
            if current is not None:
                self.__remove(current.name)
            return (target, False) if self.__add(target) else (None, True)

        # Give back their declared value to the properties which are not in the
        # configuration anymore
        properties = dict(target.properties)
        removed = set(current.properties).difference(properties)
        if removed:
            properties.update(_factory_defaults(self._ipopo, target.factory, removed))

        try:
            self._waiting.update(target.name, properties, removed)
        except KeyError:
            # Component has been forgotten by the waiting list: start it again
            return (target, False) if self.__add(target) else (None, True)
        except ValueError as ex:
            # The waiting list has lost its context: its bundle is stopping,
            # which will invalidate this component too. The component is still
            # running: keep tracking it, else the deletion of its
            # configuration wouldn't kill it
            _logger.error("Can't update the component %s: %s", target.name, ex)
            return current, True

        return target, False

    def __remove(self, name: str) -> None:
        """
        Removes a component from the waiting list, which kills it. Hides the
        errors of an already forgotten component.

        :param name: A component instance name
        """
        try:
            self._waiting.remove(name)
        except (KeyError, ValueError):
            # Component was already forgotten, or the waiting list is gone
            pass

    def __add(self, config: _ComponentConfig) -> bool:
        """
        Adds a component to the waiting list. Hides the error of a name which
        is already in use.

        :param config: Description of the component to instantiate
        :return: True if the component has been added to the waiting list
        """
        try:
            self._waiting.add(config.factory, config.name, dict(config.properties))
        except ValueError as ex:
            _logger.error("Can't instantiate the component %s: %s", config.name, ex)
            return False

        return True


# ------------------------------------------------------------------------------


class _ManagedInstance(services.IManagedService):
    """
    Applies the properties of a configuration to an existing component.

    A property which leaves the configuration goes back to the value declared
    by the factory: the values given when the component was instantiated are
    unknown here, contrary to the handler of ``@RequiresConfiguration``.
    """

    def __init__(self, ipopo: IPopoService, factory: str, name: str) -> None:
        """
        :param ipopo: The iPOPO service
        :param factory: Name of the factory of the component
        :param name: Name of the component instance
        """
        self._ipopo = ipopo
        self._factory = factory
        self._name = name

        # Properties given by the configuration
        self._configured: set[str] = set()

        # Serializes the updates: the initial notification is given by the
        # pool of ConfigurationAdmin while the next ones are given in the
        # thread of the caller of Configuration.update()
        self.__lock = threading.RLock()

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        The configuration of the component has been updated or deleted

        :param properties: The new configuration properties, None if the
                           configuration has been deleted
        """
        with self.__lock:
            self.__updated(properties)

    def __updated(self, properties: dict[str, Any] | None) -> None:
        """
        Computes and applies the update of the properties of the component.
        Must be called with the update lock held.

        :param properties: The new configuration properties, None if the
                           configuration has been deleted
        """
        if properties is None:
            # Configuration deleted: give back their declared value
            update = _factory_defaults(self._ipopo, self._factory, self._configured)
            self._configured = set()
        else:
            # The entries describing the configuration itself are not component
            # properties: the factory doesn't declare the PID of the component,
            # so it couldn't be restored when the configuration goes away
            update = {
                key: value for key, value in properties.items() if key not in services.CONFIG_ADMIN_PROPERTIES
            }
            configured = set(update)

            # Give back their declared value to the properties which are not in
            # the configuration anymore
            removed = self._configured.difference(configured)
            if removed:
                update.update(_factory_defaults(self._ipopo, self._factory, removed))

            self._configured = configured

        try:
            self._ipopo.reconfigure(self._name, update)
        except ValueError:
            # Component has been killed in the meantime
            pass


@ComponentFactory("ipopo-configadmin-configurator-factory")
@Requires("_ipopo", IPopoService)
@Instantiate("ipopo-configadmin-configurator")
class ConfigAdminConfigurator(IPopoEventListener):
    """
    Binds every component declaring a ``service.pid`` property to the
    configuration with that PID: its entries are injected in the properties of
    the component.

    Components created from a factory configuration (see
    :class:`ConfigAdminInstantiator`), those using the
    ``@RequiresConfiguration`` decorator and those providing a managed service
    are ignored: they already follow their own configuration.
    """

    # Injected services
    _ipopo: IPopoService

    def __init__(self) -> None:
        """
        Sets up members
        """
        self._context: BundleContext | None = None

        # Component name -> registration of its managed service
        self._registrations: dict[str, ServiceRegistration[services.IManagedService]] = {}

        # Component name -> identifier of the tracking in progress
        self._tracking: dict[str, int] = {}
        self.__counter = itertools.count()
        self.__lock = threading.RLock()

    @Validate
    def _validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        self._context = context
        self._ipopo.add_listener(self)

        # Handle the components which are already running
        for name, factory, _ in self._ipopo.get_instances():
            self.__track(factory, name)

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        """
        Component invalidated
        """
        self._ipopo.remove_listener(self)

        with self.__lock:
            registrations = list(self._registrations.values())
            self._registrations.clear()

            # Abort the trackings in progress
            self._tracking.clear()

        for registration in registrations:
            registration.unregister()

        self._context = None

    def handle_ipopo_event(self, event: IPopoEvent) -> None:
        """
        Handles an iPOPO event

        :param event: The iPOPO event
        """
        name = event.get_component_name()
        if name is None:
            return

        kind = event.get_kind()
        if kind == IPopoEvent.INSTANTIATED:
            self.__track(event.get_factory_name(), name)
        elif kind == IPopoEvent.KILLED:
            self.__forget(name)

    def __track(self, factory: str, name: str) -> None:
        """
        Registers a managed service for the given component, if it declares a
        PID and doesn't already follow a configuration

        :param factory: Name of the factory of the component
        :param name: Name of the component instance
        """
        with self.__lock:
            if self._context is None or name in self._registrations or name in self._tracking:
                # Not running, component already followed or already looked at
                return

            # Remember this tracking: the properties of the component are read
            # outside of the lock, and the component can be killed meanwhile
            tracking = next(self.__counter)
            self._tracking[name] = tracking

        pid = self.__component_pid(factory, name)

        with self.__lock:
            if self._tracking.get(name) != tracking:
                # The component has been killed while its properties were read
                return

            del self._tracking[name]
            if pid is None or self._context is None or name in self._registrations:
                return

            self._registrations[name] = self._context.register_service(
                services.IManagedService,
                _ManagedInstance(self._ipopo, factory, name),
                {SERVICE_PID: pid},
            )

    def __component_pid(self, factory: str, name: str) -> str | None:
        """
        Returns the PID of the configuration the given component must follow,
        None if it declares none or if it already follows a configuration by
        itself

        :param factory: Name of the factory of the component
        :param name: Name of the component instance
        :return: A configuration PID or None
        """
        try:
            # Read the real properties: get_instance_details() converts them to
            # their string representation, which would turn a declared but
            # unset PID into the "None" string
            properties = self._ipopo.get_instance_properties(name)
        except ValueError:
            # Component is not running (anymore)
            return None

        pid = properties.get(SERVICE_PID)
        if not pid:
            # Nothing to follow
            return None

        if not isinstance(pid, str):
            _logger.warning(
                "Component %s declares a non-string %s property (%r): it is ignored",
                name,
                SERVICE_PID,
                pid,
            )
            return None

        if properties.get(services.CONFIG_PROP_FACTORY_PID) == IPOPO_CONFIGADMIN_FACTORY_PID:
            # Component created from a factory configuration
            return None

        try:
            details = self._ipopo.get_factory_details(factory)
        except ValueError:
            # Factory has gone away
            return None

        if HANDLER_CONFIGADMIN in details["handlers"]:
            # Component uses @RequiresConfiguration
            return None

        provided = {spec for specifications in details["services"] for spec in specifications}
        if provided.intersection(_MANAGED_SPECIFICATIONS):
            # Component talks to ConfigurationAdmin by itself
            return None

        return pid

    def __forget(self, name: str) -> None:
        """
        Unregisters the managed service associated to the given component

        :param name: Name of the component instance
        """
        with self.__lock:
            # Abort the tracking in progress, if any
            self._tracking.pop(name, None)
            registration = self._registrations.pop(name, None)

        if registration is not None:
            registration.unregister()
