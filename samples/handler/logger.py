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
from typing import Any, Iterable, List, Optional

import pelix.ipopo.handlers.constants as ipopo_constants
import samples.handler.constants as constants
from pelix.constants import ActivatorProto, BundleActivator
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceRegistration
from pelix.ipopo.contexts import ComponentContext
from pelix.ipopo.instance import StoredInstance

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


# We need to register the handler factory as a service, using a bundle
# activator
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
            ipopo_constants.HandlerFactory,
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

            # Here, we ignore the error and do not give any handler to iPOPO
            return []

        else:
            # Construct a handler and return it in a list
            return [_LoggerHandler(logger_field, component_context.name)]


class _LoggerHandler(ipopo_constants.Handler):
    """
    The logger handler, associated to a unique component instance
    """

    def __init__(self, field: str, name: str) -> None:
        """
        Sets up the handler. Arguments depends on the HandlerFactory.

        :param field: Field where to inject the logger
        :param name: Name of the logger
        """
        self._field = field
        self._name = name
        self._logger: Optional[logging.Logger] = None

    def manipulate(self, stored_instance: StoredInstance, component_instance: Any) -> None:
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

    def get_kinds(self) -> Iterable[str]:
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
        return ["logger"]

    def start(self) -> None:
        """
        Optional: The handler has been started
        """
        if self._logger is not None:
            self._logger.debug("Component handlers are starting")

    def stop(self) -> None:
        """
        Optional: The handler has been stopped
        """
        if self._logger is not None:
            self._logger.debug("Component handlers are stopping")

    def is_valid(self) -> bool:
        """
        Optional: If this method returns False, the component will then stay or
        become invalid.
        """
        return True

    def clear(self) -> None:
        """
        Cleans up the handler. The handler can't be used after this method has
        been called
        """
        if self._logger is not None:
            self._logger.debug("Component handlers are cleared")

    def pre_validate(self) -> None:
        """
        Optional: called when the component is being validated
        """
        if self._logger is not None:
            self._logger.debug("Component will be validated")

    def post_validate(self) -> None:
        """
        Optional: called when the component has been validated
        """
        if self._logger is not None:
            self._logger.debug("Component has been validated")

    def pre_invalidate(self) -> None:
        """
        Optional: called when the component is being invalidated
        """
        if self._logger is not None:
            self._logger.debug("Component will be invalidated")

    def post_invalidate(self) -> None:
        """
        Optional: called when the component has been invalidated
        """
        if self._logger is not None:
            self._logger.debug("Component has been invalidated")
