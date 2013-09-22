#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Service providing handler

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.5.4
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
__version_info__ = (0, 5, 4)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix beans
from pelix.constants import BundleException

# iPOPO constants
import pelix.ipopo.constants as constants

# Standard library
import logging

# ------------------------------------------------------------------------------

class ServiceRegistrationHandler(object):
    """
    Handles the registration of a service provided by a component
    """
    def __init__(self, specifications, controller_name, ipopo_instance):
        """
        Sets up the handler
        
        :param specifications: The service specifications
        :param controller_name: Name of the associated service controller
                                (can be None)
        :param ipopo_instance: The iPOPO component StoredInstance
        """
        self.specifications = specifications
        self._ipopo_instance = ipopo_instance

        self.__controller = controller_name
        # Controller is "on" by default
        self.__controller_on = True
        self.__validated = False

        # The ServiceRegistration and ServiceReference objects
        self._registration = None
        self._svc_reference = None


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
        return (constants.HANDLER_SERVICE_PROVIDER,)


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
