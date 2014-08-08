#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
The logger handler implementation

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 0.5.7
:status: Beta

..

    Copyright 2014 isandlaTech

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
__version_info__ = (0, 5, 7)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Logger handler constants
import samples.handler.constants as constants

# Pelix & iPOPO constants
from pelix.constants import BundleActivator
import pelix.ipopo.handlers.constants as ipopo_constants

# Standard library
import logging

# ------------------------------------------------------------------------------

# The logger for manipulation warnings
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


# We need to register the handler factory as a service, using a bundle
# activator
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
        # Set up properties: declare the handler ID
        properties = {ipopo_constants.PROP_HANDLER_ID:
                      constants.HANDLER_LOGGER}

        # Register an handler factory instance as a service
        self._registration = context.register_service(
            ipopo_constants.SERVICE_IPOPO_HANDLER_FACTORY,
            _LoggerHandlerFactory(), properties)

    def stop(self, context):
        """
        Bundle stopped
        """
        # Unregister the service
        self._registration.unregister()
        self._registration = None

# ------------------------------------------------------------------------------


class _LoggerHandlerFactory(ipopo_constants.HandlerFactory):
    """
    The handler factory: used by iPOPO to create a handler per component
    instance
    """
    def get_handlers(self, component_context, instance):
        """
        Sets up service providers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
                 (never None)
        """
        # Extract information from the context
        logger_field = component_context.get_handler(constants.HANDLER_LOGGER)
        if not logger_field:
            # Error: log it and either raise an exception
            # or ignore this handler
            _logger.warning("Logger iPOPO handler can't find "
                            "its configuration")

            # Here, we ignore the error and do not give any handler to iPOPO
            return []

        else:
            # Construct a handler and return it in a list
            return [_LoggerHandler(logger_field, component_context.name)]


class _LoggerHandler(object):
    """
    The logger handler, associated to a unique component instance
    """
    def __init__(self, field, name):
        """
        Sets up the handler. Arguments depends on the HandlerFactory.

        :param field: Field where to inject the logger
        :param name: Name of the logger
        """
        self._field = field
        self._name = name
        self._logger = None

    def manipulate(self, stored_instance, component_instance):
        """
        Called by iPOPO right after the instantiation of the component.
        This is the last chance to manipulate the component before the other
        handlers start.

        :param stored_instance: The iPOPO component StoredInstance
        :param component_instance: The component instance
        """
        # Create the logger for this component instance
        self._logger = logging.getLogger(self._name)

        # Inject it
        setattr(component_instance, self._field, self._logger)

    def get_kinds(self):
        """
        Retrieves the kinds of this handler: the one used by iPOPO
        StoredInstance to handle the component are defined in
        ``pelix.ipopo.handlers.constants``: properties, dependency and
        service_provider.

        As we are not handling the component standard behavior, we can
        return a custom kind. If None or an empty string is returned, this
        handler will never be called by iPOPO

        :return: the kinds of this handler
        """
        return "logger"

    def start(self):
        """
        Optional: The handler has been started
        """
        self._logger.debug("Component handlers are starting")

    def stop(self):
        """
        Optional: The handler has been stopped
        """
        self._logger.debug("Component handlers are stopping")

    def is_valid(self):
        """
        Optional: If this method returns False, the component will then stay or
        become invalid.
        """
        return True

    def clear(self):
        """
        Cleans up the handler. The handler can't be used after this method has
        been called
        """
        self._logger.debug("Component handlers are cleared")

        # Clean up everything to avoid stale references, ...
        self._field = None
        self._name = None
        self._logger = None

    def pre_validate(self):
        """
        Optional: called when the component is being validated
        """
        self._logger.debug("Component will be validated")

    def post_validate(self):
        """
        Optional: called when the component has been validated
        """
        self._logger.debug("Component has been validated")

    def pre_invalidate(self):
        """
        Optional: called when the component is being invalidated
        """
        self._logger.debug("Component will be invalidated")

    def post_invalidate(self):
        """
        Optional: called when the component has been invalidated
        """
        self._logger.debug("Component has been invalidated")
