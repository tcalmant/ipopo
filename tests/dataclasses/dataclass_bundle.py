#!/usr/bin/python3
# -- Content-Encoding: UTF-8 --
"""
Module checking the behaviour of iPOPO with PEP-557 Data Classes

:author: Thomas Calmant
:copyright: Copyright 2020, Thomas Calmant
:license: Apache License 2.0

..

    Copyright 2020 Thomas Calmant

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

try:
    dataclass
except NameError:
    try:
        from dataclasses import dataclass
    except ImportError:
        raise Exception("dataclass decorator not available "
                        "(Python 3.6+ required)")

from pelix.ipopo.decorators import ComponentFactory, Property, Provides, \
    Requires


@ComponentFactory("dataclass.before")
@Provides("dataclass.before")
@Property("property_set", "property.set", "SAMPLE")
@Property("property_default", "property.default")
@Requires("requirement", "dataclass.check")
@dataclass
class DataClassBeforeManipulation:
    some_value: str = "42"
    instance_name: str = None
    requirement: object = None
    property_set: str = "Default"
    property_default: str = "Default"


@dataclass
@ComponentFactory("dataclass.after")
@Provides("dataclass.after")
@Property("property_set", "property.set", "SAMPLE")
@Property("property_default", "property.default")
@Requires("requirement", "dataclass.check")
class DataClassAfterManipulation:
    some_value: str = "42"
    instance_name: str = None
    requirement: object = None
    property_set: str = "Default"
    property_default: str = "Default"
