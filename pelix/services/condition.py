#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
The Condition service of Pelix, after the OSGi Condition Service specification:
marker services which tell that a state of the system is reached

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.3.0

..

    Copyright 2026 Thomas Calmant

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

from typing import Final, Protocol

from pelix.constants import Specification

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "CONDITION_ID",
    "CONDITION_ID_TRUE",
    "INSTANCE",
    "SERVICE_CONDITION",
    "Condition",
    "ConditionInstance",
]

# ------------------------------------------------------------------------------

SERVICE_CONDITION: Final = "org.osgi.service.condition.Condition"
""" Specification of a Condition service (same name as in OSGi) """

CONDITION_ID: Final = "osgi.condition.id"
""" Service property which identifies the condition(s) a service stands for """

CONDITION_ID_TRUE: Final = "true"
""" ID of the condition always registered by the framework """


@Specification(SERVICE_CONDITION)
class Condition(Protocol):
    """
    A Condition is a marker: it carries no method, its presence in the service
    registry (with the ``osgi.condition.id`` property) tells that the
    condition is met.
    """


class ConditionInstance:
    """Default implementation of the marker, to register a condition without writing a class"""


INSTANCE: Final[Condition] = ConditionInstance()
""" Shared marker to register a condition service """
