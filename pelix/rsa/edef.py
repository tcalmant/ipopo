"""
Pelix remote services: EDEF file handler

Endpoint Description Extender Format (EDEF) is specified in OSGi Compendium
specifications, section 122.8.

:author: Thomas Calmant and Scott Lewis
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
import logging
import sys
import xml.etree.ElementTree as ElementTree

try:
    # Python 2
    from StringIO import StringIO
except ImportError:
    # Python 3
    from io import StringIO

# Typing
try:
    # pylint: disable=W0611
    from typing import Iterable, List, Tuple, Any, Union
except ImportError:
    pass

# Pelix
from pelix.rsa.endpointdescription import EndpointDescription
from pelix import rsa
import pelix.constants

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Standard logging
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

# EDEF XML name space
EDEF_NAMESPACE = "http://www.osgi.org/xmlns/rsa/v1.0.0"

# EDEF tags
TAG_ENDPOINT_DESCRIPTIONS = "{{{0}}}endpoint-descriptions".format(
    EDEF_NAMESPACE
)
TAG_ENDPOINT_DESCRIPTION = "{{{0}}}endpoint-description".format(EDEF_NAMESPACE)
TAG_PROPERTY = "{{{0}}}property".format(EDEF_NAMESPACE)
TAG_ARRAY = "{{{0}}}array".format(EDEF_NAMESPACE)
TAG_LIST = "{{{0}}}list".format(EDEF_NAMESPACE)
TAG_SET = "{{{0}}}set".format(EDEF_NAMESPACE)
TAG_XML = "{{{0}}}xml".format(EDEF_NAMESPACE)
TAG_VALUE = "{{{0}}}value".format(EDEF_NAMESPACE)

# Property attributes
ATTR_NAME = "name"
ATTR_VALUE_TYPE = "value-type"
ATTR_VALUE = "value"

# Value types
TYPE_BOOLEAN = "Boolean"
TYPE_DOUBLE = "Double"
TYPE_LONG = "Long"
TYPE_STRING = "String"

TYPES_BOOLEAN = ("boolean", "Boolean")
TYPES_CHAR = ("char", "Character")
TYPES_FLOAT = ("float", "Float", "double", "Double")
TYPES_INT = (
    "int",
    "Integer",
    "long",
    "Long",
    "short",
    "Short",
    "bytes",
    "Bytes",
)

# Type of properties
TYPED_BOOL = tuple()
TYPED_LONG = (
    rsa.ENDPOINT_SERVICE_ID,
    rsa.ECF_ENDPOINT_TIMESTAMP,
    rsa.ECF_RSVC_ID,
)
TYPED_STRING = (
    pelix.constants.OBJECTCLASS,
    rsa.ENDPOINT_FRAMEWORK_UUID,
    rsa.ENDPOINT_ID,
    rsa.ENDPOINT_PACKAGE_VERSION_,
    rsa.SERVICE_IMPORTED_CONFIGS,
    rsa.SERVICE_INTENTS,
    rsa.SERVICE_IMPORTED,
)

# Special case: XML value given
XML_VALUE = object()

# ------------------------------------------------------------------------------


class EDEFReader(object):
    """
    Reads an EDEF XML data. Inspired from EndpointDescriptionParser from ECF
    """

    @staticmethod
    def _convert_value(vtype, value):
        # type: (str, str) -> Any
        """
        Converts the given value string according to the given type

        :param vtype: Type of the value
        :param value: String form of the value
        :return: The converted value
        :raise ValueError: Conversion failed
        """
        # Normalize value
        value = value.strip()

        if vtype == TYPE_STRING:
            # Nothing to do
            return value
        elif vtype in TYPES_INT:
            return int(value)
        elif vtype in TYPES_FLOAT:
            return float(value)
        elif vtype in TYPES_BOOLEAN:
            # Compare lower-case value
            return value.lower() not in ("false", "0")
        elif vtype in TYPES_CHAR:
            return value[0]

        # No luck
        raise ValueError("Unknown value type: {0}".format(vtype))

    def _parse_description(self, node):
        # type: (ElementTree.Element) -> EndpointDescription
        """
        Parse an endpoint description node

        :param node: The endpoint description node
        :return: The parsed EndpointDescription bean
        :raise KeyError: Attribute missing
        :raise ValueError: Invalid description
        """
        endpoint = {}
        for prop_node in node.findall(TAG_PROPERTY):
            name, value = self._parse_property(prop_node)
            endpoint[name] = value

        return EndpointDescription(None, endpoint)

    def _parse_property(self, node):
        # type: (ElementTree.Element) -> Tuple[str, Any]
        """
        Parses a property node

        :param node: The property node
        :return: A (name, value) tuple
        :raise KeyError: Attribute missing
        """
        # Get information
        name = node.attrib[ATTR_NAME]
        vtype = node.attrib.get(ATTR_VALUE_TYPE, TYPE_STRING)

        # Look for a value as a single child node
        try:
            value_node = next(iter(node))
            value = self._parse_value_node(vtype, value_node)
        except StopIteration:
            # Value is an attribute
            value = self._convert_value(vtype, node.attrib[ATTR_VALUE])

        return name, value

    def _parse_value_node(self, vtype, node):
        # type: (str, ElementTree.Element) -> Any
        """
        Parses a value node

        :param vtype: The value type
        :param node: The value node
        :return: The parsed value
        """
        kind = node.tag
        if kind == TAG_XML:
            # Raw XML value
            return next(iter(node))

        elif kind == TAG_LIST or kind == TAG_ARRAY:
            # List
            return [
                self._convert_value(vtype, value_node.text)
                for value_node in node.findall(TAG_VALUE)
            ]

        elif kind == TAG_SET:
            # Set
            return set(
                self._convert_value(vtype, value_node.text)
                for value_node in node.findall(TAG_VALUE)
            )

        else:
            # Unknown
            raise ValueError("Unknown value tag: {0}".format(kind))

    def parse(self, xml_str):
        # type: (str) -> List[EndpointDescription]
        """
        Parses an EDEF XML string

        :param xml_str: An XML string
        :return: The list of parsed EndpointDescription
        """
        # Parse the document
        root = ElementTree.fromstring(xml_str)
        if root.tag != TAG_ENDPOINT_DESCRIPTIONS:
            raise ValueError("Not an EDEF XML: {0}".format(root.tag))

        # Parse content
        return [
            self._parse_description(node)
            for node in root.findall(TAG_ENDPOINT_DESCRIPTION)
        ]


# ------------------------------------------------------------------------------


class EDEFWriter(object):
    """
    EDEF XML file writer
    """

    def __init__(self, encoding="unicode", xml_declaration=True):
        # type: (str, bool) -> None
        """
        :param encoding: XML encoding
        :param xml_declaration: Add XML declaration
        """
        if sys.version_info[0] < 3 and encoding == "unicode":
            # Small trick for Python 2.7
            encoding = "UTF-8"

        self._encoding = encoding
        self._xml_declaration = xml_declaration

    def _indent(self, element, level=0, prefix="\t"):
        # type: (ElementTree.Element, int, str) -> None
        """
        In-place Element text auto-indent, for pretty printing.

        Code from: http://effbot.org/zone/element-lib.htm#prettyprint

        :param element: An Element object
        :param level: Level of indentation
        :param prefix: String to use for each indentation
        """
        element_prefix = "\n{0}".format(level * prefix)

        if element is not None:
            if not element.text or not element.text.strip():
                element.text = element_prefix + prefix

            if not element.tail or not element.tail.strip():
                element.tail = element_prefix

            # Yep, let the "element" variable be overwritten
            # pylint: disable=R1704
            for element in element:
                self._indent(element, level + 1, prefix)

            # Tail of the last child
            if not element.tail or not element.tail.strip():
                element.tail = element_prefix

        else:
            if level and (not element.tail or not element.tail.strip()):
                element.tail = element_prefix

    @staticmethod
    def _add_container(props_node, tag, container):
        # type: (ElementTree.Element, str, Iterable) -> None
        """
        Walks through the given container and fills the node

        :param props_node: A property node
        :param tag: Name of the container tag
        :param container: The container
        """
        values_node = ElementTree.SubElement(props_node, tag)
        for value in container:
            value_node = ElementTree.SubElement(values_node, TAG_VALUE)
            value_node.text = str(value)

    @staticmethod
    def _get_type(name, value):
        # type: (str, Any) -> Union[str, object]
        """
        Returns the type associated to the given name or value

        :param name: Property name
        :param value: Property value
        :return: A value type name
        """
        # Types forced for known keys
        if name in TYPED_BOOL:
            return TYPE_BOOLEAN

        elif name in TYPED_LONG:
            return TYPE_LONG

        elif name in TYPED_STRING:
            return TYPE_STRING

        # We need to analyze the content of value
        if isinstance(value, (tuple, list, set)):
            # Get the type from container content
            try:
                # Extract value
                value = next(iter(value))

            except StopIteration:
                # Empty list, can't check
                return TYPE_STRING

        # Single value
        if isinstance(value, int):
            # Integer
            return TYPE_LONG

        elif isinstance(value, float):
            # Float
            return TYPE_DOUBLE

        elif isinstance(value, type(ElementTree.Element(None))):
            # XML
            return XML_VALUE

        # Default: String
        return TYPE_STRING

    def _make_endpoint(self, root_node, endpoint):
        # type: (ElementTree.Element, EndpointDescription) -> None
        """
        Converts the given endpoint bean to an XML Element

        :param root_node: The XML root Element
        :param endpoint: An EndpointDescription bean
        """
        endpoint_node = ElementTree.SubElement(
            root_node, TAG_ENDPOINT_DESCRIPTION
        )

        for name, value in endpoint.get_properties().items():
            # Compute value type
            vtype = self._get_type(name, value)

            # Prepare the property node
            prop_node = ElementTree.SubElement(
                endpoint_node, TAG_PROPERTY, {ATTR_NAME: name}
            )

            if vtype == XML_VALUE:
                # Special case, we have to store the value as a child
                # without a value-type attribute
                prop_node.append(value)
                continue

            # Set the value type
            prop_node.set(ATTR_VALUE_TYPE, vtype)

            # Compute value node or attribute
            if isinstance(value, tuple):
                # Array
                self._add_container(prop_node, TAG_ARRAY, value)

            elif isinstance(value, list):
                # List
                self._add_container(prop_node, TAG_ARRAY, value)

            elif isinstance(value, set):
                # Set
                self._add_container(prop_node, TAG_SET, value)

            elif isinstance(value, type(root_node)):
                # XML (direct addition)
                prop_node.append(value)

            else:
                # Simple value -> Attribute
                prop_node.set(ATTR_VALUE, str(value))

    def _make_xml(self, endpoints):
        # type: (List[EndpointDescription]) -> ElementTree.Element
        """
        Converts the given endpoint description beans into an XML Element

        :param endpoints: A list of EndpointDescription beans
        :return: A string containing an XML document
        """
        root = ElementTree.Element(TAG_ENDPOINT_DESCRIPTIONS)
        for endpoint in endpoints:
            self._make_endpoint(root, endpoint)

        # Prepare pretty-printing
        self._indent(root)
        return root

    def to_string(self, endpoints):
        # type: (List[EndpointDescription]) -> str
        """
        Converts the given endpoint description beans into a string

        :param endpoints: A list of EndpointDescription beans
        :return: A string containing an XML document
        """
        # Make the ElementTree
        root = self._make_xml(endpoints)
        tree = ElementTree.ElementTree(root)

        # Force the default name space
        ElementTree.register_namespace("", EDEF_NAMESPACE)

        # Make the XML
        # Prepare a StringIO output
        output = StringIO()

        # Try to write with a correct encoding
        tree.write(
            output,
            encoding=self._encoding,
            xml_declaration=self._xml_declaration,
        )

        return output.getvalue().strip()

    def write(self, endpoints, filename):
        # type: (List[EndpointDescription], str) -> None
        """
        Writes the given endpoint descriptions to the given file

        :param endpoints: A list of EndpointDescription beans
        :param filename: Name of the file where to write the XML
        :raise IOError: Error writing the file
        """
        with open(filename, "w") as filep:
            filep.write(self.to_string(endpoints))
