#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO service interfaces definitions

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2023 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

from typing import Any, Dict, List, Optional, Protocol, Set, Tuple, Type

from pelix.framework import Bundle, BundleContext
from pelix.ipopo import constants
from pelix.ipopo.constants import IPopoEvent


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


class IPopoService(Protocol):
    """
    Interface of the iPOPO core service
    """

    __SPECIFICATION__ = constants.IPOPO_SERVICE_SPECIFICATION

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

    def register_factory(self, bundle_context: BundleContext, factory: Type) -> bool:
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

    def get_factory_bundle(self, name: str) -> Bundle:
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
