#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
An EventAdmin handler which prints to the standard output the events it receives

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2025 Thomas Calmant

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
from pprint import pformat
from typing import Any, Dict, List, Union

import pelix.misc
import pelix.services as services
from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Property, Provides, Validate

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


def _parse_boolean(value: Any) -> bool:
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
@Provides(services.ServiceEventHandler)
@Property("_event_topics", services.PROP_EVENT_TOPICS, "*")
@Property("_print", "evt.print", True)
@Property("_log", "evt.log", False)
class EventAdminPrinter(services.ServiceEventHandler):
    # pylint: disable=R0903
    """
    Utility component which can print and log EventAdmin events
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self._event_topics: Union[None, str, List[str]] = None
        self._print: bool = False
        self._log: bool = False

    @Validate
    def _validate(self, _: BundleContext) -> None:
        """
        Component validated
        """
        # Normalize parameters
        self._print = _parse_boolean(self._print)
        self._log = _parse_boolean(self._log)

    def handle_event(self, topic: str, properties: Dict[str, Any]) -> None:
        """
        An EventAdmin event has been received
        """
        if self._print:
            # Print the event on standard output
            print(f"Event: {topic}\nProperties:\n{pformat(properties)}")

        if self._log:
            # Log the event
            _logger.info("Event: %s ; Properties: %s", topic, properties)
