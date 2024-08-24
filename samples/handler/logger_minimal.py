#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
The logger handler implementation

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2023 Thomas Calmant

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
from typing import Any, List, Optional
from pelix.internals.registry import ServiceRegistration

import pelix.ipopo.handlers.constants as ipopo_constants
import samples.handler.constants as constants
from pelix.constants import ActivatorProto, BundleActivator
from pelix.framework import BundleContext
from pelix.ipopo.contexts import ComponentContext

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# The logger for manipulation warnings
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


# We need to register the handler factory as a service,
# using a bundle activator
@BundleActivator
class Activator(ActivatorProto):
    """
    The bundle activator
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self._registration: Optional[ServiceRegistration[ipopo_constants.HandlerFactory]] = None

    def start(self, context: BundleContext) -> None:
        """
        Bundle started
        """
        # Set up properties: declare the handler ID
        properties = {ipopo_constants.PROP_HANDLER_ID: constants.HANDLER_LOGGER}

        # Register an handler factory instance as a service
        self._registration = context.register_service(
            ipopo_constants.SERVICE_IPOPO_HANDLER_FACTORY,
            _LoggerHandlerFactory(),
            properties,
        )

    def stop(self, context: BundleContext) -> None:
        """
        Bundle stopped
        """
        if self._registration is not None:
            # Unregister the service
            self._registration.unregister()
            self._registration = None


# ------------------------------------------------------------------------------


class _LoggerHandlerFactory(ipopo_constants.HandlerFactory):
    """
    The handler factory: used by iPOPO to create a handler per component
    instance
    """

    def get_handlers(
        self, component_context: ComponentContext, instance: Any
    ) -> List[ipopo_constants.Handler]:
        """
        Sets up service providers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component (never None)
        """
        # Extract information from the context
        logger_field = component_context.get_handler(constants.HANDLER_LOGGER)
        if not logger_field:
            # Error: log it and either raise an exception
            # or ignore this handler
            _logger.warning("Logger iPOPO handler can't find its configuration")

        else:
            # Create the logger for this component instance
            logger = logging.getLogger(component_context.name)

            # Inject it
            setattr(instance, logger_field, logger)
            logger.debug("Logger has been injected")

        # No need to have an instance handler
        return []
