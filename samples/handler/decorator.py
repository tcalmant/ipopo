#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Defines the decorator for the logger iPOPO handler

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

# iPOPO Decorators utility methods
import pelix.ipopo.decorators as decorators

# Standard library
import inspect
import logging

# ------------------------------------------------------------------------------

# The logger for decoration warnings
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class Logger(object):
    """
    The decorator to activate and configure the logger handler
    """
    def __init__(self, field):
        """
        Sets up the logger configuration

        :param field: Field where to inject the logger
        """
        self._field = field

    def __call__(self, clazz):
        """
        Stores the configuration of the handler in the component factory
        context

        Do not forget to return the given class if no exception is raised

        :param clazz: Manipulated class
        :return: The (manipulated) class
        """
        # Ensure that the decorator is applied on a class
        if not inspect.isclass(clazz):
            raise TypeError("@Logger can decorate only classes, not '{0}'"
                            .format(type(clazz).__name__))

        # Retrieve the Factory context
        context = decorators.get_factory_context(clazz)
        if context.completed:
            # Do nothing if the class has already been manipulated
            _logger.warning("@Logger: Already manipulated class: %s",
                            decorators.get_method_description(clazz))
            return clazz

        # Store the handler information
        context.set_handler(constants.HANDLER_LOGGER, self._field)

        # Inject the logger field in the class
        setattr(clazz, self._field, None)

        return clazz
