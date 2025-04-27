#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Service providing handler

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

import logging
from typing import Any, Callable, Iterable, List, Optional, Tuple, TypeVar

import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants
from pelix.constants import ActivatorProto, BundleActivator, BundleException
from pelix.framework import BundleContext
from pelix.internals.events import ServiceEvent
from pelix.internals.registry import ServiceReference, ServiceRegistration
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
        :return: The list of handlers associated to the given component
        """
        # Retrieve the handler configuration
        provides = component_context.get_handler(ipopo_constants.HANDLER_PROVIDES)
        if not provides:
            # Nothing to do
            return []

        # 1 handler per provided service
        return [
            ServiceRegistrationHandler(specs, controller, is_factory, is_prototype)
            for specs, controller, is_factory, is_prototype in provides
        ]


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
        properties = {constants.PROP_HANDLER_ID: ipopo_constants.HANDLER_PROVIDES}

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


class ServiceRegistrationHandler(constants.ServiceProviderHandler):
    """
    Handles the registration of a service provided by a component
    """

    def __init__(
        self, specifications: List[str], controller_name: str, is_factory: bool, is_prototype: bool
    ) -> None:
        """
        Sets up the handler

        :param specifications: The service specifications
        :param controller_name: Name of the associated service controller (can be None)
        :param is_factory: If True, this is a service factory
        :param is_prototype: If True, this is a prototype service factory
        """
        self.specifications = specifications
        self.__controller = controller_name
        self._ipopo_instance: Optional[StoredInstance] = None

        # Controller is "on" by default
        self.__controller_on = True
        self.__validated = False

        # Service factory flag
        self.__is_factory = is_factory
        self.__is_prototype = is_prototype

        # The ServiceRegistration and ServiceReference objects
        self._registration: Optional[ServiceRegistration[Any]] = None
        self._svc_reference: Optional[ServiceReference[Any]] = None

    def _field_controller_generator(self) -> Tuple[Callable[[T, str], Any], Callable[[T, str, Any], Any]]:
        """
        Generates the methods called by the injected controller
        """
        # Local variable, to avoid messing with "self"
        stored_instance = self._ipopo_instance
        if stored_instance is None:
            raise ValueError("Stored instance not available")

        def get_value(_: T, name: str) -> Any:
            # pylint: disable=W0613
            """
            Retrieves the controller value, from the iPOPO dictionaries

            :param name: The property name
            :return: The property value
            """
            return stored_instance.get_controller_state(name)

        def set_value(_: T, name: str, new_value: Any) -> Any:
            # pylint: disable=W0613
            """
            Sets the property value and trigger an update event

            :param name: The property name
            :param new_value: The new property value
            """
            # Get the previous value
            old_value = stored_instance.get_controller_state(name)
            if new_value != old_value:
                # Update the controller state
                stored_instance.set_controller_state(name, new_value)

            return new_value

        return get_value, set_value

    def manipulate(self, stored_instance: StoredInstance, component_instance: Any) -> None:
        """
        Manipulates the component instance

        :param stored_instance: The iPOPO component StoredInstance
        :param component_instance: The component instance
        """
        # Store the stored instance
        self._ipopo_instance = stored_instance

        if self.__controller is None:
            # No controller: do nothing
            return

        # Get the current value of the member (True by default)
        controller_value = getattr(component_instance, self.__controller, True)

        # Store the controller value
        stored_instance.set_controller_state(self.__controller, controller_value)

        # Prepare the methods names
        getter_name = f"{ipopo_constants.IPOPO_CONTROLLER_PREFIX}{ipopo_constants.IPOPO_GETTER_SUFFIX}"
        setter_name = f"{ipopo_constants.IPOPO_CONTROLLER_PREFIX}{ipopo_constants.IPOPO_SETTER_SUFFIX}"

        # Inject the getter and setter at the instance level
        getter, setter = self._field_controller_generator()
        setattr(component_instance, getter_name, getter)
        setattr(component_instance, setter_name, setter)

    def check_event(self, event: ServiceEvent[Any]) -> bool:
        """
        Tests if the given service event corresponds to the registered service

        :param event: A service event
        :return: True if the given event references the provided service
        """
        return self._svc_reference is not event.get_service_reference()

    def get_kinds(self) -> Tuple[str]:
        """
        Retrieves the kinds of this handler: 'service_provider'

        :return: the kinds of this handler
        """
        return (constants.KIND_SERVICE_PROVIDER,)

    def get_service_reference(self) -> Optional[ServiceReference[Any]]:
        """
        Retrieves the reference of the provided service

        :return: A ServiceReference object
        """
        return self._svc_reference

    def on_controller_change(self, name: str, value: bool) -> None:
        """
        Called by the instance manager when a controller value has been
        modified

        :param name: The name of the controller
        :param value: The new value of the controller
        """
        if self.__controller != name:
            # Nothing to do
            return

        # Update the controller value
        self.__controller_on = value
        if value:
            # Controller switched to "ON"
            self._register_service()
        else:
            # Controller switched to "OFF"
            self._unregister_service()

    def on_property_change(self, name: str, old_value: Any, new_value: Any) -> None:
        """
        Called by the instance manager when a component property is modified

        :param name: The changed property name
        :param old_value: The previous property value
        :param new_value: The new property value
        """
        if self._registration is not None:
            # use the registration to trigger the service event
            self._registration.set_properties({name: new_value})

    def post_validate(self) -> None:
        """
        Called by the instance manager once the component has been validated
        """
        # Update the validation flag
        self.__validated = True
        self._register_service()

    def pre_invalidate(self) -> None:
        """
        Called by the instance manager before the component is invalidated
        """
        # Update the validation flag
        self.__validated = False

        # Force service unregistration
        self._unregister_service()

    def _register_service(self) -> None:
        """
        Registers the provided service, if possible
        """
        if self._ipopo_instance is None or self._ipopo_instance.context is None:
            raise ValueError("iPOPO instance not configured")

        if self._registration is None and self.specifications and self.__validated and self.__controller_on:
            # Use a copy of component properties
            properties = self._ipopo_instance.context.properties.copy()
            bundle_context = self._ipopo_instance.bundle_context

            # Register the service
            self._registration = bundle_context.register_service(
                self.specifications,
                self._ipopo_instance.instance,
                properties,
                factory=self.__is_factory,
                prototype=self.__is_prototype,
            )
            self._svc_reference = self._registration.get_reference()

            # Notify the component
            self._ipopo_instance.safe_callback(
                ipopo_constants.IPOPO_CALLBACK_POST_REGISTRATION,
                self._svc_reference,
            )

    def _unregister_service(self) -> None:
        """
        Unregisters the provided service, if needed
        """
        if self._ipopo_instance is None:
            raise ValueError("iPOPO instance not available")

        if self._registration is not None:
            # Ignore error
            try:
                self._registration.unregister()
            except BundleException as ex:
                # Only log the error at this level
                logger = logging.getLogger("-".join((self._ipopo_instance.name, "ServiceRegistration")))
                logger.error("Error unregistering a service: %s", ex)

            # Notify the component (even in case of error)
            self._ipopo_instance.safe_callback(
                ipopo_constants.IPOPO_CALLBACK_POST_UNREGISTRATION,
                self._svc_reference,
            )

            self._registration = None
            self._svc_reference = None
