#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
An EventAdmin handler which prints to the standard output the events it receives

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
from pprint import pformat
import logging

# Pelix
from pelix.ipopo.decorators import (
    ComponentFactory,
    Provides,
    Property,
    Validate,
)
import pelix.misc
import pelix.services as services

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


def _parse_boolean(value):
    """
    Returns a boolean value corresponding to the given value.

    :param value: Any value
    :return: Its boolean value
    """
    if not value:
        return False

    try:
        # Lower string to check known "false" value
        value = value.lower()
        return value not in ("none", "0", "false", "no")
    except AttributeError:
        # Not a string, but has a value
        return True


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.misc.FACTORY_EVENT_ADMIN_PRINTER)
@Provides(services.SERVICE_EVENT_HANDLER)
@Property("_event_topics", services.PROP_EVENT_TOPICS, "*")
@Property("_print", "evt.print", True)
@Property("_log", "evt.log", False)
class EventAdminPrinter(object):
    # pylint: disable=R0903
    """
    Utility component which can print and log EventAdmin events
    """

    def __init__(self):
        """
        Sets up members
        """
        self._event_topics = None
        self._print = False
        self._log = False

    @Validate
    def _validate(self, _):
        """
        Component validated
        """
        # Normalize parameters
        self._print = _parse_boolean(self._print)
        self._log = _parse_boolean(self._log)

    def handle_event(self, topic, properties):
        """
        An EventAdmin event has been received
        """
        if self._print:
            # Print the event on standard output
            print(
                "Event: {0}\nProperties:\n{1}".format(
                    topic, pformat(properties)
                )
            )

        if self._log:
            # Log the event
            _logger.info("Event: %s ; Properties: %s", topic, properties)
