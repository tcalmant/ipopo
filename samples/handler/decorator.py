#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Defines the decorator for the logger iPOPO handler

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

import inspect
import logging
from typing import Any, Type

import pelix.ipopo.decorators as decorators
import samples.handler.constants as constants

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# The logger for decoration warnings
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class Logger:
    """
    The decorator to activate and configure the logger handler
    """

    def __init__(self, field: str) -> None:
        """
        Sets up the logger configuration

        :param field: Field where to inject the logger
        """
        self._field = field

    def __call__(self, clazz: Type[Any]) -> Type[Any]:
        """
        Stores the configuration of the handler in the component factory
        context

        Do not forget to return the given class if no exception is raised

        :param clazz: Manipulated class
        :return: The (manipulated) class
        """
        # Ensure that the decorator is applied on a class
        if not inspect.isclass(clazz):
            raise TypeError(f"@Logger can decorate only classes, not '{type(clazz).__name__}'")

        # Retrieve the Factory context
        context = decorators.get_factory_context(clazz)
        if context.completed:
            # Do nothing if the class has already been manipulated
            _logger.warning(
                "@Logger: Already manipulated class: %s",
                decorators.get_method_description(clazz),
            )
            return clazz

        # Store the handler information
        context.set_handler(constants.HANDLER_LOGGER, self._field)

        # Inject the logger field in the class
        setattr(clazz, self._field, None)

        return clazz
