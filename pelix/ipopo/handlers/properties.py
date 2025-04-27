#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Properties handler

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

from typing import Any, Callable, Iterable, Optional, Tuple, TypeVar

import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants
from pelix.constants import ActivatorProto, BundleActivator
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceRegistration
from pelix.ipopo.contexts import ComponentContext
from pelix.ipopo.instance import StoredInstance

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

T = TypeVar("T")

# ------------------------------------------------------------------------------


class _HandlerFactory(constants.HandlerFactory):
    """
    Factory service for service registration handlers
    """

    def get_handlers(self, component_context: ComponentContext, instance: Any) -> Iterable[constants.Handler]:
        """
        Sets up service providers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list/tuple of handlers associated to the given component
        """
        # 1 handler per provided service
        return (PropertiesHandler(),)


@BundleActivator
class Activator(ActivatorProto):
    """
    The bundle activator
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self._registration: Optional[ServiceRegistration[constants.HandlerFactory]] = None

    def start(self, context: BundleContext) -> None:
        """
        Bundle started
        """
        # Set up properties
        properties = {constants.PROP_HANDLER_ID: ipopo_constants.HANDLER_PROPERTY}

        # Register the handler factory service
        self._registration = context.register_service(
            constants.HandlerFactory,
            _HandlerFactory(),
            properties,
        )

    def stop(self, _: BundleContext) -> None:
        """
        Bundle stopped
        """
        if self._registration is not None:
            # Unregister the service
            self._registration.unregister()
            self._registration = None


# ------------------------------------------------------------------------------


class PropertiesHandler(constants.Handler):
    """
    Handles the properties
    """

    def __init__(self) -> None:
        super().__init__()
        self._ipopo_instance: Optional[StoredInstance] = None

    def _field_property_generator(
        self, public_properties: bool
    ) -> Tuple[Callable[[T, str], Any], Callable[[T, str, Any], Any]]:
        """
        Generates the methods called by the injected class properties

        :param public_properties: If True, create a public property accessor,
        else an hidden property accessor
        :return: getter and setter methods
        """
        # Local variable, to avoid messing with "self"
        stored_instance = self._ipopo_instance

        if stored_instance is None or stored_instance.context is None:
            raise ValueError("Stored instance not configured")

        # Choose public or hidden properties
        # and select the method to call to notify about the property update
        if public_properties:
            properties = stored_instance.context.properties
            update_notifier = stored_instance.update_property
        else:
            # Copy Hidden properties and remove them from the context
            properties = stored_instance.context.grab_hidden_properties()
            update_notifier = stored_instance.update_hidden_property

        def get_value(_: T, name: str) -> Any:
            """
            Retrieves the property value, from the iPOPO dictionaries

            :param name: The property name
            :return: The property value
            """
            return properties.get(name)

        def set_value(_: T, name: str, new_value: Any) -> Any:
            """
            Sets the property value and trigger an update event

            :param name: The property name
            :param new_value: The new property value
            """
            assert stored_instance is not None and stored_instance.context is not None

            # Get the previous value
            old_value = properties.get(name)
            if new_value != old_value:
                # Change the property
                properties[name] = new_value

                # New value is different of the old one, trigger an event
                update_notifier(name, old_value, new_value)

            return new_value

        return get_value, set_value

    @staticmethod
    def get_methods_names(public_properties: bool) -> Tuple[str, str]:
        """
        Generates the names of the fields where to inject the getter and setter
        methods

        :param public_properties: If True, returns the names of public property
        accessors, else of hidden property ones
        :return: getter and a setter field names
        """
        if public_properties:
            prefix = ipopo_constants.IPOPO_PROPERTY_PREFIX
        else:
            prefix = ipopo_constants.IPOPO_HIDDEN_PROPERTY_PREFIX

        return (
            f"{prefix}{ipopo_constants.IPOPO_GETTER_SUFFIX}",
            f"{prefix}{ipopo_constants.IPOPO_SETTER_SUFFIX}",
        )

    def get_kinds(self) -> Tuple[str]:
        return (constants.KIND_PROPERTIES,)

    def manipulate(self, stored_instance: StoredInstance, component_instance: Any) -> None:
        """
        Manipulates the component instance

        :param stored_instance: The iPOPO component StoredInstance
        :param component_instance: The component instance
        """
        # Store the stored instance
        self._ipopo_instance = stored_instance

        if stored_instance.context is None:
            raise ValueError("Stored instance not configured")

        # Public flags to generate (True for public accessors)
        flags_to_generate = set()
        if stored_instance.context.properties:
            flags_to_generate.add(True)

        # (False for hidden ones)
        if stored_instance.context.has_hidden_properties():
            flags_to_generate.add(False)

        # Inject properties getters and setters
        for public_flag in flags_to_generate:
            # Prepare methods
            getter, setter = self._field_property_generator(public_flag)

            # Inject the getter and setter at the instance level
            getter_name, setter_name = self.get_methods_names(public_flag)
            setattr(component_instance, getter_name, getter)
            setattr(component_instance, setter_name, setter)
