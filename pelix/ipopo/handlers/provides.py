#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Service providing handler

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.5.5
:status: Alpha

..

    This file is part of iPOPO.

    iPOPO is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    iPOPO is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with iPOPO. If not, see <http://www.gnu.org/licenses/>.
"""

# Module version
__version_info__ = (0, 5, 5)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix beans
from pelix.constants import BundleException

# iPOPO constants
import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants

# Standard library
import logging

# ------------------------------------------------------------------------------

class _HandlerFactory(constants.HandlerFactory):
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
        # 1 handler per provided service
        return [ServiceRegistrationHandler(specs, controller)
                for specs, controller in component_context.get_provides()]


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
        properties = {constants.PROP_HANDLER_ID:
                      ipopo_constants.HANDLER_PROVIDES}

        # Register the handler factory service
        self._registration = context.register_service(
                                      constants.SERVICE_IPOPO_HANDLER_FACTORY,
                                      _HandlerFactory(),
                                      properties)


    def stop(self, context):
        """
        Bundle stopped
        """
        # Unregister the service
        self._registration.unregister()
        self._registration = None

# Declare the activator
activator = _Activator()

# ------------------------------------------------------------------------------

class ServiceRegistrationHandler(constants.ServiceProviderHandler):
    """
    Handles the registration of a service provided by a component
    """
    def __init__(self, specifications, controller_name):
        """
        Sets up the handler

        :param specifications: The service specifications
        :param controller_name: Name of the associated service controller
                                (can be None)
        """
        self.specifications = specifications
        self.__controller = controller_name
        self._ipopo_instance = None

        # Controller is "on" by default
        self.__controller_on = True
        self.__validated = False

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
            """
            Retrieves the controller value, from the iPOPO dictionaries

            :param name: The property name
            :return: The property value
            """
            return stored_instance.get_controller_state(name)


        def set_value(self, name, new_value):
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

        return (get_value, set_value)


    def manipulate(self, stored_instance, component_instance):
        """
        Manipulates the component instance

        :param stored_instance: The iPOPO component StoredInstance
        :param component_instance: The component instance
        """
        # Store the stored instance
        self._ipopo_instance = stored_instance

        # Inject controllers

        # Avoid injection of unused instance fields...
        provides_tuples = stored_instance.context.factory_context.provides
        controllers = set([value[1] for value in provides_tuples if value[1]])
        if controllers:
            # Controllers are valid by default
            for name in controllers:
                # Get the current value of the member (True by default)
                controller_value = getattr(component_instance, name, True)
                # Store the controller value
                stored_instance.set_controller_state(name, controller_value)

            # Prepare the methods names
            getter_name = "{0}{1}" \
                          .format(ipopo_constants.IPOPO_CONTROLLER_PREFIX,
                                  ipopo_constants.IPOPO_GETTER_SUFFIX)
            setter_name = "{0}{1}" \
                          .format(ipopo_constants.IPOPO_CONTROLLER_PREFIX,
                                  ipopo_constants.IPOPO_SETTER_SUFFIX)

            # Inject the getter and setter at the instance level
            getter, setter = self._field_controller_generator()
            setattr(component_instance, getter_name, getter)
            setattr(component_instance, setter_name, setter)


    def check_event(self, svc_event):
        """
        Tests if the given service event corresponds to the registered service

        :param svc_event: A service event
        :return: True if the given event references the provided service
        """
        return self._svc_reference is not svc_event.get_service_reference()


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
        Called by the instance manager when a controller value has been modified

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
        if self._registration is None and self.specifications \
        and self.__validated and self.__controller_on:
            # Use a copy of component properties
            properties = self._ipopo_instance.context.properties.copy()
            bundle_context = self._ipopo_instance.bundle_context

            # Register the service
            self._registration = bundle_context.register_service(
                                            self.specifications,
                                            self._ipopo_instance.instance,
                                            properties)
            self._svc_reference = self._registration.get_reference()


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
                logger = logging.getLogger('-'.join((self._ipopo_instance.name,
                                                     'ServiceRegistration')))
                logger.error("Error unregistering a service: %s", ex)

            self._registration = None
            self._svc_reference = None
