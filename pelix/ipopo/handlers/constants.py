#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO handlers constants and base classes

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

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Iterable, List, Optional, Protocol, Tuple
from pelix.constants import Specification

from pelix.internals.events import ServiceEvent
from pelix.internals.registry import ServiceReference

if TYPE_CHECKING:
    from pelix.ipopo.contexts import ComponentContext, Requirement
    from pelix.ipopo.instance import StoredInstance

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

SERVICE_IPOPO_HANDLER_FACTORY = "ipopo.handler.factory"
"""
iPOPO handler factory service specification. Those services should implement
the methods of HandlerFactory.
"""

PROP_HANDLER_ID = "ipopo.handler.id"
""" Service property: the ID of the iPOPO handler factory """

# ------------------------------------------------------------------------------

KIND_PROPERTIES = "properties"
"""
Represents the 'properties' kind of handler, which manipulates the component
to notify property changes.
"""

KIND_DEPENDENCY = "dependency"
"""
Represents the 'dependency' kind of handler.
Those handlers must implement the following methods:

* get_bindings(): Retrieves the list of bound service references
* is_valid(): Returns True if the dependency is in a valid state
"""

KIND_SERVICE_PROVIDER = "service_provider"
"""
Represents the 'service_provider' kind of handler.
Those handlers must implement the following method:

* get_service_reference(): Retrieves the reference of the provided service (a ServiceReference object).

It should also implement the following ones:

* on_controller_changer(): Called when a component controller has been
  modified. The publication of a service might be stopped if its controller is
  set to False.
* on_property_change(): Called when a component property has been modified.
  The provided service properties should be modified accordingly.
"""

# ------------------------------------------------------------------------------


class Handler(ABC):
    """
    Basic handler abstract class
    """

    @abstractmethod
    def get_kinds(self) -> Iterable[str]:
        """
        Returns the kinds of this handler

        :return: A tuple of the kinds of this handler
        """
        ...

    @abstractmethod
    def manipulate(self, stored_instance: "StoredInstance", component_instance: Any) -> None:
        """
        Manipulates the associated component instance
        """
        ...

    def check_event(self, event: ServiceEvent[Any]) -> Optional[bool]:
        """
        Tests if the given service event must be handled or ignored, based
        on the state of the iPOPO service and on the content of the event.

        :param event: A service event
        :return: None to ignore result, True if the event can be handled, False if it must be ignored
        """
        return None

    def is_valid(self) -> bool:
        """
        Checks this handler is valid. All handlers must be valid for a
        component to be validated

        :return: True if the handler is in a valid state
        """
        return True

    def on_controller_change(self, name: str, value: bool) -> None:
        """
        Notifies the change of state of the controller with the given name

        :param name: The name of the controller
        :param value: The new value of the controller
        """
        return None

    def on_property_change(self, name: str, old_value: Any, new_value: Any) -> None:
        """
        Handles a property changed event

        :param name: The changed property name
        :param old_value: The previous property value
        :param new_value: The new property value
        """
        return None

    def on_hidden_property_change(self, name: str, old_value: Any, new_value: Any) -> None:
        """
        Handles a the property changed event of a hidden property

        :param name: The changed property name
        :param old_value: The previous property value
        :param new_value: The new property value
        """
        return None

    def start(self) -> None:
        """
        Starts the handler (listeners, ...). Called once, after the component
        has been manipulated by all handlers.
        """
        return None

    def stop(self) -> Optional[Iterable[Tuple[Any, ServiceReference[Any]]]]:
        """
        Stops the handler. Called once, just after the component has been
        killed

        :return: The removed bindings (list) or None
        """
        return None

    def clear(self) -> None:
        """
        Called just after a component has been killed and all handlers have
        been stopped. The handler should release all its resources here.
        """
        return None

    def pre_validate(self) -> None:
        """
        Called just before a component is validated
        """
        return None

    def post_validate(self) -> None:
        """
        Called just after a component has been validated
        """
        return None

    def pre_invalidate(self) -> None:
        """
        Called just before a component is invalidated
        """
        return None

    def post_invalidate(self) -> None:
        """
        Called just after a component has been invalidated
        """
        return None


class HandlerException(Exception):
    """
    Kind of exception used by handlers
    """

    ...


# ------------------------------------------------------------------------------


class ServiceProviderHandler(Handler, ABC):
    """
    Service provider handler abstract class
    """

    @abstractmethod
    def get_service_reference(self) -> Optional[ServiceReference[Any]]:
        """
        Returns the reference to the service provided by this handler
        """
        ...


# ------------------------------------------------------------------------------


class DependencyHandler(Handler, ABC):
    """
    Dependency handler abstract class
    """

    requirement: "Requirement"

    def get_field(self) -> Optional[str]:
        """
        Returns the name of the field where to inject the dependency
        """
        return None

    def try_binding(self) -> None:
        """
        Forces the handler to try to bind to existing services
        """
        return None

    def get_bindings(self) -> List[ServiceReference[Any]]:
        """
        Retrieves the list of the references to the bound services

        :return: A list of ServiceReferences objects
        """
        return []

    def get_value(self) -> Any:
        """
        Returns the value to inject
        """
        return None


# ------------------------------------------------------------------------------


@Specification(SERVICE_IPOPO_HANDLER_FACTORY)
class HandlerFactory(Protocol):
    """
    Handler factory abstract class
    """

    def get_handlers(self, component_context: "ComponentContext", instance: Any) -> Iterable[Handler]:
        """
        Prepares handlers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
        """
        ...
