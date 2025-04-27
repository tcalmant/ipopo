#!/usr/bin/python3
# -- Content-Encoding: UTF-8 --
"""
Module checking the behaviour of iPOPO with PEP-557 Data Classes

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0

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

from dataclasses import dataclass
from typing import Optional

from pelix.ipopo.constants import IPOPO_INSTANCE_NAME
from pelix.ipopo.decorators import ComponentFactory, Property, Provides, Requires


@ComponentFactory("dataclass.before")
@Provides("dataclass.before")
@Property("instance_name", IPOPO_INSTANCE_NAME)
@Property("property_set", "property.set", "SAMPLE-before")
@Property("property_default", "property.default")
@Requires("requirement", "dataclass.check")
@dataclass
class DataClassBeforeManipulation:
    some_value: str = "42"
    instance_name: Optional[str] = None
    requirement: Optional[object] = None
    property_set: str = "Default-before"
    property_default: str = "Default-before"


@dataclass
@ComponentFactory("dataclass.after")
@Provides("dataclass.after")
@Property("instance_name", IPOPO_INSTANCE_NAME)
@Property("property_set", "property.set", "SAMPLE-after")
@Property("property_default", "property.default")
@Requires("requirement", "dataclass.check")
class DataClassAfterManipulation:
    some_value: str = "42"
    instance_name: Optional[str] = None
    requirement: Optional[object] = None
    property_set: str = "Default-after"
    property_default: str = "Default-after"
