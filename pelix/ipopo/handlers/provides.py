#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Service providing handler

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Thomas Calmant

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

# Standard library
import logging

# Pelix beans
from pelix.constants import BundleActivator, BundleException

# iPOPO constants
import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class _HandlerFactory(constants.HandlerFactory):
    # pylint: disable=R0903
    """
    Factory service for service registration handlers
    """

    def get_handlers(self, component_context, instance):
        """
        Sets up service providers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
        """
        # Retrieve the handler configuration
        provides = component_context.get_handler(
            ipopo_constants.HANDLER_PROVIDES
        )
        if not provides:
            # Nothing to do
            return ()

        # 1 handler per provided service
        return [
            ServiceRegistrationHandler(
                specs, controller, is_factory, is_prototype
            )
            for specs, controller, is_factory, is_prototype in provides
        ]


@BundleActivator
class _Activator(object):
    """
    The bundle activator
    """

    def __init__(self):
        """
        Sets up members
        """
        self._registration = None

    def start(self, context):
        """
        Bundle started
        """
        # Set up properties
        properties = {
            constants.PROP_HANDLER_ID: ipopo_constants.HANDLER_PROVIDES
        }

        # Register the handler factory service
        self._registration = context.register_service(
            constants.SERVICE_IPOPO_HANDLER_FACTORY,
            _HandlerFactory(),
            properties,
        )

    def stop(self, _):
        """
        Bundle stopped
        """
        # Unregister the service
        self._registration.unregister()
        self._registration = None


# ------------------------------------------------------------------------------


class ServiceRegistrationHandler(constants.ServiceProviderHandler):
    """
    Handles the registration of a service provided by a component
    """

    def __init__(
        self, specifications, controller_name, is_factory, is_prototype
    ):
        """
        Sets up the handler

        :param specifications: The service specifications
        :param controller_name: Name of the associated service controller
                                (can be None)
        :param is_factory: If True, this is a service factory
        :param is_prototype: If True, this is a prototype service factory
        """
        self.specifications = specifications
        self.__controller = controller_name
        self._ipopo_instance = None

        # Controller is "on" by default
        self.__controller_on = True
        self.__validated = False

        # Service factory flag
        self.__is_factory = is_factory
        self.__is_prototype = is_prototype

        # The ServiceRegistration and ServiceReference objects
        self._registration = None
        self._svc_reference = None

    def _field_controller_generator(self):
        """
        Generates the methods called by the injected controller
        """
        # Local variable, to avoid messing with "self"
        stored_instance = self._ipopo_instance

        def get_value(self, name):
            # pylint: disable=W0613
            """
            Retrieves the controller value, from the iPOPO dictionaries

            :param name: The property name
            :return: The property value
            """
            return stored_instance.get_controller_state(name)

        def set_value(self, name, new_value):
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

    def manipulate(self, stored_instance, component_instance):
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
        stored_instance.set_controller_state(
            self.__controller, controller_value
        )

        # Prepare the methods names
        getter_name = "{0}{1}".format(
            ipopo_constants.IPOPO_CONTROLLER_PREFIX,
            ipopo_constants.IPOPO_GETTER_SUFFIX,
        )
        setter_name = "{0}{1}".format(
            ipopo_constants.IPOPO_CONTROLLER_PREFIX,
            ipopo_constants.IPOPO_SETTER_SUFFIX,
        )

        # Inject the getter and setter at the instance level
        getter, setter = self._field_controller_generator()
        setattr(component_instance, getter_name, getter)
        setattr(component_instance, setter_name, setter)

    def check_event(self, event):
        """
        Tests if the given service event corresponds to the registered service

        :param event: A service event
        :return: True if the given event references the provided service
        """
        return self._svc_reference is not event.get_service_reference()

    def get_kinds(self):
        """
        Retrieves the kinds of this handler: 'service_provider'

        :return: the kinds of this handler
        """
        return (constants.KIND_SERVICE_PROVIDER,)

    def get_service_reference(self):
        """
        Retrieves the reference of the provided service

        :return: A ServiceReference object
        """
        return self._svc_reference

    def on_controller_change(self, name, value):
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

    def on_property_change(self, name, old_value, new_value):
        """
        Called by the instance manager when a component property is modified

        :param name: The changed property name
        :param old_value: The previous property value
        :param new_value: The new property value
        """
        if self._registration is not None:
            # use the registration to trigger the service event
            self._registration.set_properties({name: new_value})

    def post_validate(self):
        """
        Called by the instance manager once the component has been validated
        """
        # Update the validation flag
        self.__validated = True
        self._register_service()

    def pre_invalidate(self):
        """
        Called by the instance manager before the component is invalidated
        """
        # Update the validation flag
        self.__validated = False

        # Force service unregistration
        self._unregister_service()

    def _register_service(self):
        """
        Registers the provided service, if possible
        """
        if (
            self._registration is None
            and self.specifications
            and self.__validated
            and self.__controller_on
        ):
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

    def _unregister_service(self):
        """
        Unregisters the provided service, if needed
        """
        if self._registration is not None:
            # Ignore error
            try:
                self._registration.unregister()
            except BundleException as ex:
                # Only log the error at this level
                logger = logging.getLogger(
                    "-".join((self._ipopo_instance.name, "ServiceRegistration"))
                )
                logger.error("Error unregistering a service: %s", ex)

            # Notify the component (even in case of error)
            self._ipopo_instance.safe_callback(
                ipopo_constants.IPOPO_CALLBACK_POST_UNREGISTRATION,
                self._svc_reference,
            )

            self._registration = None
            self._svc_reference = None
