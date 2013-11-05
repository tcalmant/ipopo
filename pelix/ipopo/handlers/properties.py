#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Properties handler

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.5.5
:status: Beta

..

    Copyright 2013 isandlaTech

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

# Module version
__version_info__ = (0, 5, 5)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# iPOPO constants
import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants

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
        return [PropertiesHandler()]


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
                      ipopo_constants.HANDLER_PROPERTY}

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

class PropertiesHandler(constants.Handler):
    """
    Handles the properties
    """
    def __init__(self):
        """
        Sets up the handler
        """
        pass


    def _field_property_generator(self):
        """
        Generates the methods called by the injected class properties
        """
        # Local variable, to avoid messing with "self"
        stored_instance = self._ipopo_instance
        properties = stored_instance.context.properties

        def get_value(self, name):
            """
            Retrieves the property value, from the iPOPO dictionaries

            :param name: The property name
            :return: The property value
            """
            return properties.get(name, None)


        def set_value(self, name, new_value):
            """
            Sets the property value and trigger an update event

            :param name: The property name
            :param new_value: The new property value
            """
            assert stored_instance.context is not None

            # Get the previous value
            old_value = properties.get(name, None)
            if new_value != old_value:
                # Change the property
                properties[name] = new_value

                # New value is different of the old one, trigger an event
                stored_instance.update_property(name, old_value, new_value)

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

        # Inject properties
        getter, setter = self._field_property_generator()

        # Prepare the methods names
        getter_name = "{0}{1}".format(ipopo_constants.IPOPO_PROPERTY_PREFIX,
                                      ipopo_constants.IPOPO_GETTER_SUFFIX)
        setter_name = "{0}{1}".format(ipopo_constants.IPOPO_PROPERTY_PREFIX,
                                      ipopo_constants.IPOPO_SETTER_SUFFIX)

        # Inject the getter and setter at the instance level
        setattr(component_instance, getter_name, getter)
        setattr(component_instance, setter_name, setter)
