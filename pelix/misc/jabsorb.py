#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Python JSON ↔ Java Jabsorb format converter

Jabsorb is a serialization library for Java, converting Java beans to JSON
and vice versa.

This module is compatible with the fork of Jabsorb available at
https://github.com/Thomas Calmant/cohorte-org.jabsorb.ng

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
import inspect
import re

try:
    # Python 2
    # pylint: disable=F0401
    import __builtin__ as builtins
except ImportError:
    # Python 3
    # pylint: disable=F0401
    import builtins

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

JSON_CLASS = "__jsonclass__"
"""
Tuple used by jsonrpclib to indicate wich Python class corresponds to its
content
"""

JAVA_CLASS = "javaClass"
"""
Dictionary key used by Jabsorb to indicate which Java class corresponds to its
content
"""

JAVA_MAPS_PATTERN = re.compile(r"java\.util\.(.*Map|Properties)")
""" Pattern to detect standard Java classes for maps """

JAVA_LISTS_PATTERN = re.compile(r"java\.util\..*List")
""" Pattern to detect standard Java classes for lists """

JAVA_SETS_PATTERN = re.compile(r"java\.util\..*Set")
""" Pattern to detect standard Java classes for sets """

# ------------------------------------------------------------------------------


class HashableDict(dict):
    """
    Small workaround because dictionaries are not hashable in Python
    """

    def __hash__(self):
        """
        Computes the hash of the dictionary
        """
        return hash("HashableDict({0})".format(sorted(self.items())))


class HashableSet(set):
    """
    Small workaround because sets are not hashable in Python
    """

    def __hash__(self):
        """
        Computes the hash of the set
        """
        return hash("HashableSet({0})".format(sorted(self)))


class HashableList(list):
    """
    Small workaround because lists are not hashable in Python
    """

    def __hash__(self):
        """
        Computes the hash of the list
        """
        return hash("HashableList({0})".format(sorted(self)))


class AttributeMap(dict):
    """
    Wraps a map to have the same behaviour between getattr and getitem
    """

    def __init__(self, *args, **kwargs):
        """
        Adds a __dict__ member to this dictionary
        """
        super(AttributeMap, self).__init__(*args, **kwargs)
        self.__dict__ = self

    def __hash__(self):
        """
        Computes the hash of the dictionary
        """
        return hash("AttributeMap({0})".format(sorted(self.items())))


# ------------------------------------------------------------------------------


def _compute_jsonclass(obj):
    """
    Compute the content of the __jsonclass__ field for the given object

    :param obj: An object
    :return: The content of the __jsonclass__ field
    """
    # It's not a standard type, so it needs __jsonclass__
    module_name = inspect.getmodule(obj).__name__
    json_class = obj.__class__.__name__
    if module_name not in ("", "__main__"):
        json_class = "{0}.{1}".format(module_name, json_class)

    return [json_class, []]


def _is_builtin(obj):
    """
    Checks if the type of the given object is a built-in one or not

    :param obj: An object
    :return: True if the object is of a built-in type
    """
    module_ = inspect.getmodule(obj)
    if module_ in (None, builtins):
        return True

    return module_.__name__ in ("", "__main__")


def _is_converted_class(java_class):
    """
    Checks if the given Java class is one we *might* have set up
    """
    if not java_class:
        return False

    return (
        JAVA_MAPS_PATTERN.match(java_class) is not None
        or JAVA_LISTS_PATTERN.match(java_class) is not None
        or JAVA_SETS_PATTERN.match(java_class) is not None
    )


# ------------------------------------------------------------------------------


def to_jabsorb(value):
    """
    Adds information for Jabsorb, if needed.

    Converts maps and lists to a jabsorb form.
    Keeps tuples as is, to let them be considered as arrays.

    :param value: A Python result to send to Jabsorb
    :return: The result in a Jabsorb map format (not a JSON object)
    """
    # None ?
    if value is None:
        return None

    # Map ?
    elif isinstance(value, dict):
        if JAVA_CLASS in value or JSON_CLASS in value:
            if not _is_converted_class(value.get(JAVA_CLASS)):
                # Bean representation
                converted_result = {}

                for key, content in value.items():
                    converted_result[key] = to_jabsorb(content)

                try:
                    # Keep the raw jsonrpclib information
                    converted_result[JSON_CLASS] = value[JSON_CLASS]
                except KeyError:
                    pass

            else:
                # We already worked on this value
                converted_result = value

        else:
            # Needs the whole transformation
            converted_result = {JAVA_CLASS: "java.util.HashMap"}
            converted_result["map"] = map_pairs = {}
            for key, content in value.items():
                map_pairs[key] = to_jabsorb(content)

            try:
                # Keep the raw jsonrpclib information
                map_pairs[JSON_CLASS] = value[JSON_CLASS]
            except KeyError:
                pass

    # List ? (consider tuples as an array)
    elif isinstance(value, list):
        converted_result = {
            JAVA_CLASS: "java.util.ArrayList",
            "list": [to_jabsorb(entry) for entry in value],
        }

    # Set ?
    elif isinstance(value, (set, frozenset)):
        converted_result = {
            JAVA_CLASS: "java.util.HashSet",
            "set": [to_jabsorb(entry) for entry in value],
        }

    # Tuple ? (used as array, except if it is empty)
    elif isinstance(value, tuple):
        converted_result = [to_jabsorb(entry) for entry in value]

    elif hasattr(value, JAVA_CLASS):
        # Class with a Java class hint: convert into a dictionary
        class_members = {
            name: getattr(value, name)
            for name in dir(value)
            if not name.startswith("_")
        }

        converted_result = HashableDict(
            (name, to_jabsorb(content))
            for name, content in class_members.items()
            if not inspect.ismethod(content)
        )

        # Do not forget the Java class
        converted_result[JAVA_CLASS] = getattr(value, JAVA_CLASS)

        # Also add a __jsonclass__ entry
        converted_result[JSON_CLASS] = _compute_jsonclass(value)

    # Other ?
    else:
        converted_result = value

    return converted_result


def from_jabsorb(request, seems_raw=False):
    """
    Transforms a jabsorb request into a more Python data model (converts maps
    and lists)

    :param request: Data coming from Jabsorb
    :param seems_raw: Set it to True if the given data seems to already have
                      been parsed (no Java class hint). If True, the lists will
                      be kept as lists instead of being converted to tuples.
    :return: A Python representation of the given data
    """
    if isinstance(request, (tuple, set, frozenset)):
        # Special case : JSON arrays (Python lists)
        return type(request)(from_jabsorb(element) for element in request)

    elif isinstance(request, list):
        # Check if we were a list or a tuple
        if seems_raw:
            return list(from_jabsorb(element) for element in request)

        return tuple(from_jabsorb(element) for element in request)

    elif isinstance(request, dict):
        # Dictionary
        java_class = request.get(JAVA_CLASS)
        json_class = request.get(JSON_CLASS)
        seems_raw = not java_class and not json_class

        if java_class:
            # Java Map ?
            if JAVA_MAPS_PATTERN.match(java_class) is not None:
                return HashableDict(
                    (from_jabsorb(key), from_jabsorb(value))
                    for key, value in request["map"].items()
                )

            # Java List ?
            elif JAVA_LISTS_PATTERN.match(java_class) is not None:
                return HashableList(
                    from_jabsorb(element) for element in request["list"]
                )

            # Java Set ?
            elif JAVA_SETS_PATTERN.match(java_class) is not None:
                return HashableSet(
                    from_jabsorb(element) for element in request["set"]
                )

        # Any other case
        result = AttributeMap(
            (from_jabsorb(key), from_jabsorb(value, seems_raw))
            for key, value in request.items()
        )

        # Keep JSON class information as is
        if json_class:
            result[JSON_CLASS] = json_class

        return result

    elif not _is_builtin(request):
        # Bean
        for attr in dir(request):
            # Only convert public fields
            if not attr[0] == "_":
                # Field conversion
                setattr(request, attr, from_jabsorb(getattr(request, attr)))

        return request

    else:
        # Any other case
        return request
