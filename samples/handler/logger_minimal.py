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


# We need to register the handler factory as a service,
# using a bundle activator
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

        else:
            # Create the logger for this component instance
            logger = logging.getLogger(component_context.name)

            # Inject it
            setattr(instance, logger_field, logger)
            logger.debug("Logger has been injected")

        # No need to have an instance handler
        return []
