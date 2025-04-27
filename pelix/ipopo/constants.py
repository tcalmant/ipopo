#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Defines some iPOPO constants

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2025 Thomas Calmant

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

import contextlib
from typing import Any, Dict, Generator, List, Optional, Protocol, Set, Tuple, Type, cast

from pelix.constants import BundleException, Specification
from pelix.framework import Bundle, BundleContext
from pelix.internals.registry import ServiceReference

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

SERVICE_IPOPO: str = "pelix.ipopo.core"
""" iPOPO service specification """

IPOPO_SERVICE_SPECIFICATION: str = SERVICE_IPOPO
""" Compatibility constant """

SERVICE_IPOPO_WAITING_LIST = "pelix.ipopo.waiting_list"
""" iPOPO waiting list service specification """

# ------------------------------------------------------------------------------

HANDLER_REQUIRES = "ipopo.requires"
""" The @Requires handler ID """

HANDLER_REQUIRES_BEST = "ipopo.requires.best"
""" The @RequiresBest handler ID """

HANDLER_REQUIRES_BROADCAST = "ipopo.requires.broadcast"
""" The @RequiresBroadcast handler ID """

HANDLER_REQUIRES_MAP = "ipopo.requires.map"
""" The @RequiresMap handler ID """

HANDLER_REQUIRES_VARIABLE_FILTER = "ipopo.requires.variable_filter"
""" The @RequiresVarFilter handler ID """

HANDLER_TEMPORAL = "ipopo.temporal"
""" The @Temporal handler ID """

HANDLER_PROVIDES = "ipopo.provides"
""" The @Provides handler ID """

HANDLER_PROPERTY = "ipopo.properties"
""" The @Property handler ID """

# ------------------------------------------------------------------------------

# Injected class fields
IPOPO_METHOD_CALLBACKS = "__ipopo_callbacks__"
""" Contains the list of callback types this method is decorated for """

IPOPO_METHOD_FIELD_CALLBACKS = "__ipopo_field_callbacks__"
""" Contains a list of tuples (field, callback type) """

IPOPO_FACTORY_CONTEXT = "__ipopo_factory_context__"
""" Storage of the FactoryContext object """

# Method called by the injected property (must be injected in the instance)
IPOPO_GETTER_SUFFIX = "_getter"
IPOPO_SETTER_SUFFIX = "_setter"
IPOPO_PROPERTY_PREFIX = "_ipopo_property"
IPOPO_HIDDEN_PROPERTY_PREFIX = "_ipopo_hidden_property"
IPOPO_CONTROLLER_PREFIX = "_ipopo_controller"

# Other injected information
IPOPO_VALIDATE_ARGS = "__ipopo_validate_args__"
""" Storage of the arguments for ``@ValidateComponent`` """

ARG_BUNDLE_CONTEXT = "bundle_context"
""" Represents the bundle context argument in ``@ValidateContext`` """

ARG_COMPONENT_CONTEXT = "component_context"
""" Represents the component context argument in ``@ValidateContext`` """

ARG_PROPERTIES = "properties"
""" Represents the component properties argument in ``@ValidateContext`` """

# ------------------------------------------------------------------------------

# Callbacks
IPOPO_CALLBACK_BIND = "BIND"
""" Bind: called when a dependency is injected """

IPOPO_CALLBACK_BIND_FIELD = "BIND_FIELD"
""" BindField: called when a dependency is injected in the given field """

IPOPO_CALLBACK_UPDATE = "UPDATE"
"""
Update: called when the properties of an injected dependency have been updated
"""

IPOPO_CALLBACK_UPDATE_FIELD = "UPDATE_FIELD"
"""
UpdateField: called when the properties of a dependency injected in the given
field have been updated
"""

IPOPO_CALLBACK_UNBIND = "UNBIND"
""" Unbind: called when a dependency is about to be removed """

IPOPO_CALLBACK_UNBIND_FIELD = "UNBIND_FIELD"
"""
UnbindField: called when a dependency is about to be removed from the given
field
"""

IPOPO_CALLBACK_VALIDATE = "VALIDATE"
"""
ValidateComponent: Called once all mandatory dependencies have been bound,
with component-specific parameters
"""

IPOPO_CALLBACK_INVALIDATE = "INVALIDATE"
"""
InvalidateComponent: Called when one the mandatory dependencies is unbound,
with component-specific parameters
"""

IPOPO_CALLBACK_POST_REGISTRATION = "POST_REGISTRATION"
"""
Post-Registration: called when a service of the component has been registered
"""

IPOPO_CALLBACK_POST_UNREGISTRATION = "POST_UNREGISTRATION"
"""
Post-Unregistration: called when a service of the component has been
unregistered.
"""

# Properties
IPOPO_INSTANCE_NAME = "instance.name"
""" Name of the component instance """

IPOPO_REQUIRES_FILTERS = "requires.filters"
""" Dictionary (field → filter) to override @Requires filters """

IPOPO_TEMPORAL_TIMEOUTS = "temporal.timeouts"
""" Dictionary (field → timeout) to override @Temporal timeouts """

IPOPO_AUTO_RESTART = "pelix.ipopo.auto_restart"
"""
If True, the component will be re-instantiated after its bundle has been
updated
"""

# ------------------------------------------------------------------------------


class IPopoEvent:
    """
    An iPOPO event descriptor.
    """

    REGISTERED = 1
    """ A component factory has been registered """

    INSTANTIATED = 2
    """ A component has been instantiated, but not yet validated """

    VALIDATED = 3
    """ A component has been validated """

    INVALIDATED = 4
    """ A component has been invalidated """

    BOUND = 5
    """ A reference has been injected in the component """

    UNBOUND = 6
    """ A reference has been removed from the component """

    KILLED = 9
    """ A component has been killed (removed from the list of instances) """

    UNREGISTERED = 10
    """ A component factory has been unregistered """

    def __init__(self, kind: int, factory_name: str, component_name: Optional[str]) -> None:
        """
        Sets up the iPOPO event

        :param kind: Kind of event
        :param factory_name: Name of the factory associated to the event
        :param component_name: Name of the component instance associated to the event
        """
        self.__kind = kind
        self.__factory_name = factory_name
        self.__component_name = component_name

    def get_component_name(self) -> Optional[str]:
        """
        Retrieves the name of the component associated to the event

        :return: the name of the component
        """
        return self.__component_name

    def get_factory_name(self) -> str:
        """
        Retrieves the name of the factory associated to the event

        :return: the name of the component factory
        """
        return self.__factory_name

    def get_kind(self) -> int:
        """
        Retrieves the kind of event

        :return: the kind of event
        """
        return self.__kind


class IPopoEventListener(Protocol):
    """
    Interface of iPOPO events listeners
    """

    def handle_ipopo_event(self, event: IPopoEvent) -> None:
        """
        Handles an iPOPO event

        :param event: Event to handle
        """
        ...


@Specification(SERVICE_IPOPO)
class IPopoService(Protocol):
    """
    Interface of the iPOPO core service
    """

    def instantiate(self, factory_name: str, name: str, properties: Optional[Dict[str, Any]] = None) -> Any:
        """
        Instantiates a component from the given factory, with the given name

        :param factory_name: Name of the component factory
        :param name: Name of the instance to be started
        :param properties: Initial properties of the component instance
        :return: The component instance
        :raise TypeError: The given factory is unknown
        :raise ValueError: The given name or factory name is invalid, or an
                           instance with the given name already exists
        :raise Exception: Something wrong occurred in the factory
        """
        ...

    def retry_erroneous(self, name: str, properties_update: Optional[Dict[str, Any]] = None) -> int:
        """
        Removes the ERRONEOUS state of the given component, and retries a validation

        :param name: Name of the component to retry
        :param properties_update: A dictionary to update the initial properties of the component
        :return: The new state of the component
        :raise ValueError: Invalid component name
        """
        ...

    def invalidate(self, name: str) -> None:
        """
        Invalidates the given component

        :param name: Name of the component to invalidate
        :raise ValueError: Invalid component name
        """
        ...

    def is_registered_factory(self, name: str) -> bool:
        """
        Tests if the given name is in the factory registry

        :param name: A factory name to be tested
        """
        ...

    def is_registered_instance(self, name: str) -> bool:
        """
        Tests if the given name is in the instance registry or in the waiting
        queue

        :param name: A component name to be tested
        """
        ...

    def kill(self, name: str) -> None:
        """
        Kills the given component

        :param name: Name of the component to kill
        :raise ValueError: Invalid component name
        """
        ...

    def register_factory(self, bundle_context: "BundleContext", factory: Type[Any]) -> bool:
        """
        Registers a manually created factory, using decorators programmatically

        :param bundle_context: The factory bundle context
        :param factory: A manipulated class
        :return: True if the factory has been registered
        :raise ValueError: Invalid parameter, or factory already registered
        :raise TypeError: Invalid factory type (not a manipulated class)
        """
        ...

    def unregister_factory(self, factory_name: str) -> bool:
        """
        Unregisters the given component factory

        :param factory_name: Name of the factory to unregister
        :return: True the factory has been removed, False if the factory is unknown
        """
        ...

    def add_listener(self, listener: IPopoEventListener) -> bool:
        """
        Register an iPOPO event listener.

        The event listener must have a method with the following prototype::

           def handle_ipopo_event(self, event):
               '''
               event: A IPopoEvent object
               '''
               # ...

        :param listener: The listener to register
        :return: True if the listener has been added to the registry
        """
        ...

    def remove_listener(self, listener: IPopoEventListener) -> bool:
        """
        Unregister an iPOPO event listener.

        :param listener: The listener to register
        :return: True if the listener has been removed from the registry
        """
        ...

    def get_instances(self) -> List[Tuple[str, str, int]]:
        """
        Retrieves the list of the currently registered component instances

        :return: A list of (name, factory name, state) tuples.
        """
        ...

    def get_instance(self, name: str) -> Any:
        """
        Returns the instance of the component with the given name

        :param name: A component name
        :return: The component instance
        :raise KeyError: Unknown instance
        """
        ...

    def get_waiting_components(self) -> List[Tuple[str, str, Set[str]]]:
        """
        Returns the list of the instances waiting for their handlers

        :return: A list of (name, factory name, missing handlers) tuples
        """
        ...

    def get_instance_details(self, name: str) -> Dict[str, Any]:
        """
        Retrieves a snapshot of the given component instance.
        The result dictionary has the following keys:

        * ``name``: The component name
        * ``factory``: The name of the component factory
        * ``bundle_id``: The ID of the bundle providing the component factory
        * ``state``: The current component state
        * ``services``: A ``{Service ID → Service reference}`` dictionary, with
          all services provided by the component
        * ``dependencies``: A dictionary associating field names with the
          following dictionary:

          * ``handler``: The name of the type of the dependency handler
          * ``filter`` (optional): The requirement LDAP filter
          * ``optional``: A flag indicating whether the requirement is optional
            or not
          * ``aggregate``: A flag indicating whether the requirement is a set
            of services or not
          * ``binding``: A list of the ServiceReference the component is bound
            to

        * ``properties``: A dictionary key → value, with all properties of the
          component. The value is converted to its string representation, to
          avoid unexpected behaviours.

        :param name: The name of a component instance
        :return: A dictionary of details
        :raise ValueError: Invalid component name
        """
        ...

    def get_factories(self) -> List[str]:
        """
        Retrieves the names of the registered factories

        :return: A list of factories. Can be empty.
        """
        ...

    def get_factory_bundle(self, name: str) -> "Bundle":
        """
        Retrieves the Pelix Bundle object that registered the given factory

        :param name: The name of a factory
        :return: The Bundle that registered the given factory
        :raise ValueError: Invalid factory
        """
        ...

    def get_factory_details(self, name: str) -> Dict[str, Any]:
        """
        Retrieves a dictionary with details about the given factory

        * ``name``: The factory name
        * ``bundle``: The Bundle object of the bundle providing the factory
        * ``properties``: Copy of the components properties defined by the factory
        * ``requirements``: List of the requirements defined by the factory

          * ``id``: Requirement ID (field where it is injected)
          * ``specification``: Specification of the required service
          * ``aggregate``: If True, multiple services will be injected
          * ``optional``: If True, the requirement is optional

        * ``services``: List of the specifications of the services provided by components of this factory
        * ``handlers``: Dictionary of the non-built-in handlers required by this factory.
          The dictionary keys are handler IDs, and it contains a tuple with:

          * A copy of the configuration of the handler (0)
          * A flag indicating if the handler is present or not

        :param name: The name of a factory
        :return: A dictionary describing the factory
        :raise ValueError: Invalid factory
        """
        ...


@Specification(SERVICE_IPOPO_WAITING_LIST)
class IPopoWaitingList(Protocol):
    """
    iPOPO instantiation waiting list
    """

    def add(self, factory: str, component: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """
        Enqueues the instantiation of the given component

        :param factory: Factory name
        :param component: Component name
        :param properties: Component properties
        :raise ValueError: Component name already reserved in the queue
        :raise Exception: Error instantiating the component
        """
        ...

    def remove(self, component: str) -> None:
        """
        Kills/Removes the component with the given name

        :param component: A component name
        :raise KeyError: Unknown component
        """
        ...


# ------------------------------------------------------------------------------


def get_ipopo_svc_ref(
    bundle_context: "BundleContext",
) -> Optional[Tuple["ServiceReference[IPopoService]", "IPopoService"]]:
    """
    Retrieves a tuple containing the service reference to iPOPO and the service
    itself

    :param bundle_context: The calling bundle context
    :return: The reference to the iPOPO service and the service itself, None if not available
    """
    # Look after the service
    ref = cast("ServiceReference[IPopoService]", bundle_context.get_service_reference(SERVICE_IPOPO))
    if ref is None:
        return None

    try:
        # Get it
        svc = bundle_context.get_service(ref)
    except BundleException:
        # Service reference has been invalidated
        return None

    # Return both the reference (to call unget_service()) and the service
    return ref, svc


@contextlib.contextmanager
def use_ipopo(bundle_context: "BundleContext") -> Generator["IPopoService", None, None]:
    """
    Utility context to use the iPOPO service safely in a "with" block.
    It looks after the the iPOPO service and releases its reference when
    exiting the context.

    :param bundle_context: The calling bundle context
    :return: The iPOPO service
    :raise BundleException: Service not found
    """
    # Get the service and its reference
    ref_svc = get_ipopo_svc_ref(bundle_context)
    if ref_svc is None:
        raise BundleException("No iPOPO service available")

    try:
        # Give the service
        yield ref_svc[1]
    finally:
        try:
            # Release it
            bundle_context.unget_service(ref_svc[0])
        except BundleException:
            # Service might have already been unregistered
            pass


@contextlib.contextmanager
def use_waiting_list(bundle_context: "BundleContext") -> Generator["IPopoWaitingList", None, None]:
    """
    Utility context to use the iPOPO waiting list safely in a "with" block.
    It looks after the the iPOPO waiting list service and releases its
    reference when exiting the context.

    :param bundle_context: The calling bundle context
    :return: The iPOPO waiting list service
    :raise BundleException: Service not found
    """
    # Get the service and its reference
    ref = bundle_context.get_service_reference(IPopoWaitingList)
    if ref is None:
        raise BundleException("No iPOPO waiting list service available")

    try:
        # Give the service
        yield bundle_context.get_service(ref)
    finally:
        try:
            # Release it
            bundle_context.unget_service(ref)
        except BundleException:
            # Service might have already been unregistered
            pass
