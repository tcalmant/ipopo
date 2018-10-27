#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Specifications handling utility methods

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
try:
    # Python 3
    # pylint: disable=F0401,E0611
    from urllib.parse import urlparse
except ImportError:
    # Python 2
    # pylint: disable=F0401
    from urlparse import urlparse

# Standard typing module should be optional
try:
    # pylint: disable=W0611
    from typing import Any, Dict, Iterable, List, Optional, Tuple
except ImportError:
    pass

# Pelix
from pelix.utilities import is_string
import pelix.constants
import pelix.framework
import pelix.ldapfilter
import pelix.remote
import pelix.utilities

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

PYTHON_LANGUAGE = "python"
""" Prefix to use for the Python specifications """

# ------------------------------------------------------------------------------


class ExportEndpoint(object):
    """
    Represents an export end point (one per group of configuration types)
    """

    def __init__(
        self, uid, fw_uid, configurations, name, svc_ref, service, properties
    ):
        # type: (str, str, Any[str, List[str]], str, pelix.framework.ServiceReference, object, dict) -> None
        """
        :param uid: Unique identified of the end point
        :param fw_uid: The framework UID
        :param configurations: Kinds of end point (xmlrpc, ...)
        :param name: Name of the end point
        :param svc_ref: ServiceReference of the exported service
        :param service: Instance of the exported service
        :param properties: Extra properties
        :raise ValueError: Invalid UID or the end point exports nothing
                           (all specifications have been filtered)
        """
        if not uid:
            raise ValueError("Invalid UID")

        # Given information
        self.__uid = uid
        self.__fw_uid = fw_uid
        self.__instance = service
        self.__reference = svc_ref
        self.__configurations = configurations
        self.__name = name

        # Normalize extra properties
        if isinstance(properties, dict):
            self.__properties = properties
        else:
            self.__properties = {}

        # Normalize the list of configurations
        if is_string(configurations):
            self.__configurations = (configurations,)
        else:
            self.__configurations = tuple(configurations)

        # Exported specifications
        self.__exported_specs = []  # type: List[str]
        exported_specs = compute_exported_specifications(svc_ref)
        if exported_specs:
            # Transform the specifications for export (add the language prefix)
            self.__exported_specs = format_specifications(exported_specs)
        else:
            raise ValueError(
                "Endpoint {0}, {1}, exports nothing".format(
                    self.__uid, self.__name
                )
            )

    def __hash__(self):
        """
        Custom hash, as we override equality tests
        """
        return hash(self.__uid)

    def __eq__(self, other):
        """
        Equality checked by UID
        """
        return self.__uid == other.uid

    def __ne__(self, other):
        """
        Inequality checked by UID
        """
        return self.__uid != other.uid

    def __str__(self):
        """
        String representation
        """
        return "ExportEndpoint(uid={0}, types={1}, specs={2})".format(
            self.__uid, self.__configurations, self.__exported_specs
        )

    def get_properties(self):
        # type: () -> dict
        """
        Returns merged properties

        :return: Endpoint merged properties
        """
        # Get service properties
        properties = self.__reference.get_properties()

        # Merge with local properties
        properties.update(self.__properties)

        # Some properties can't be merged
        for key in pelix.constants.OBJECTCLASS, pelix.constants.SERVICE_ID:
            properties[key] = self.__reference.get_property(key)

        # Force the exported configurations
        properties[pelix.remote.PROP_EXPORTED_CONFIGS] = self.configurations

        return properties

    def make_import_properties(self):
        # type: () -> dict
        """
        Returns the properties of this endpoint where export properties have
        been replaced by import ones

        :return: A dictionary with import properties
        """
        # Convert merged properties
        props = to_import_properties(self.get_properties())

        # Add the framework UID
        props[pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID] = self.__fw_uid
        return props

    def rename(self, new_name):
        # type: (str) -> None
        """
        Updates the endpoint name

        :param new_name: The new name of the endpoint
        """
        if new_name:
            # Update the name only if the new one is valid
            self.__name = new_name

    # Access to the service
    @property
    def instance(self):
        # type: () -> object
        """
        Service instance
        """
        return self.__instance

    @property
    def reference(self):
        # type: () -> pelix.framework.ServiceReference
        """
        Service reference
        """
        return self.__reference

    # End point properties
    @property
    def uid(self):
        # type: () -> str
        """
        End point unique identifier
        """
        return self.__uid

    @property
    def framework(self):
        # type: () -> str
        """
        Framework UID
        """
        return self.__fw_uid

    @property
    def configurations(self):
        # type: () ->  Tuple[str, ...]
        """
        Configurations of this end point
        """
        return self.__configurations

    @property
    def name(self):
        # type: () -> str
        """
        Name of the end point
        """
        return self.__name

    @property
    def specifications(self):
        # type: () -> List[str]
        """
        Returns the exported specifications
        """
        return self.__exported_specs


# ------------------------------------------------------------------------------


class ImportEndpoint(object):
    """
    Represents an end point to access an imported service
    """

    def __init__(
        self, uid, framework, configurations, name, specifications, properties
    ):
        # type: (str, str, Any[str, List[str]], Optional[str], List[str], dict) -> None
        """
        :param uid: Unique identified of the end point
        :param framework: UID of the framework exporting the end point
                          (can be None)
        :param configurations: Kinds of end point (xmlrpc, ...)
        :param name: Name of the end point
        :param specifications: Specifications of the exported service
        :param properties: Properties of the service
        """
        self.__uid = uid
        self.__fw_uid = framework or None
        self.__name = name
        self.__properties = properties.copy() if properties else {}

        # Normalize list of configurations
        if is_string(configurations):
            tuple_conf = (configurations,)  # type: Tuple[str, ...]
        else:
            tuple_conf = tuple(configurations)

        self.__configurations = tuple_conf

        # Extract the language prefix in specifications
        self.__specifications = extract_specifications(
            specifications, self.__properties
        )

        # Public variable: the source server,
        # set up by a Pelix discovery service
        self.server = None  # type: str

    def __str__(self):
        """
        String representation of the end point
        """
        return (
            "ImportEndpoint(uid={0}, framework={1}, configurations={2}, "
            "specs={3})".format(
                self.__uid,
                self.__fw_uid,
                self.__configurations,
                self.__specifications,
            )
        )

    # Access to the service details
    @property
    def specifications(self):
        # type: () -> List[str]
        """
        Specifications of the service
        """
        return self.__specifications

    @property
    def properties(self):
        # type: () -> dict
        """
        Properties of the imported service
        """
        return self.__properties

    @properties.setter
    def properties(self, properties):
        # type: (dict) -> None
        """
        Sets the properties of the imported service
        """
        # Keep a copy of the new properties
        self.__properties = properties.copy() if properties else {}

    # End point properties
    @property
    def uid(self):
        # type: () -> str
        """
        End point unique identifier
        """
        return self.__uid

    @property
    def framework(self):
        # type: () -> str
        """
        UID of the framework exporting this end point
        """
        return self.__fw_uid

    @property
    def configurations(self):
        # type: () -> Tuple[str, ...]
        """
        Kind of end point
        """
        return self.__configurations

    @property
    def name(self):
        # type: () -> str
        """
        Name of the end point
        """
        return self.__name


# ------------------------------------------------------------------------------


class EndpointDescription(object):
    """
    Endpoint description bean, according to OSGi specifications:

    http://www.osgi.org/javadoc/r4v42/org/osgi/service/remoteserviceadmin/
    EndpointDescription.html

    This is an importer-side description
    """

    def __init__(self, svc_ref, properties):
        # type: (Optional[pelix.framework.ServiceReference], dict) -> None
        """
        Sets up the description with the given properties

        :raise ValueError: Invalid properties
        """
        # Set up properties
        all_properties = {}  # type: Dict[str, Any]
        if svc_ref is not None:
            all_properties.update(svc_ref.get_properties())

        if properties:
            all_properties.update(properties)

        # Add  some properties if the service reference is given
        if svc_ref is not None:
            # Service ID
            all_properties[
                pelix.remote.PROP_ENDPOINT_SERVICE_ID
            ] = svc_ref.get_property(pelix.constants.SERVICE_ID)

        # Convert properties
        self.__properties = to_import_properties(all_properties)

        # Check their validity
        self.__check_properties(self.__properties)

        # Keep a copy of the endpoint ID
        self.__endpoint_id = self.get_id()

    def __hash__(self):
        """
        Custom hash, as we override equality tests
        """
        return hash(self.__endpoint_id)

    def __eq__(self, other):
        """
        Equality checked by UID
        """
        # pylint: disable=W0212
        return self.__endpoint_id == other.__endpoint_id

    def __ne__(self, other):
        """
        Inequality checked by UID
        """
        # pylint: disable=W0212
        return self.__endpoint_id != other.__endpoint_id

    def __str__(self):
        """
        String representation
        """
        return (
            "EndpointDescription(id={0}; endpoint.service.id={1}; "
            "framework.uuid={2})".format(
                self.get_id(), self.get_service_id(), self.get_framework_uuid()
            )
        )

    @staticmethod
    def __check_properties(props):
        # type: (dict) -> None
        """
        Checks that the given dictionary doesn't have export keys and has
        import keys

        :param props: Properties to validate
        :raise ValueError: Invalid properties
        """
        # Mandatory properties
        mandatory = (
            pelix.remote.PROP_ENDPOINT_ID,
            pelix.remote.PROP_IMPORTED_CONFIGS,
            pelix.constants.OBJECTCLASS,
        )
        for key in mandatory:
            if key not in props:
                raise ValueError("Missing property: {0}".format(key))

        # Export/Import properties
        props_export = (
            pelix.remote.PROP_EXPORTED_CONFIGS,
            pelix.remote.PROP_EXPORTED_INTERFACES,
        )

        for key in props_export:
            if key in props:
                raise ValueError("Export property found: {0}".format(key))

    def get_configuration_types(self):
        # type: () -> List[str]
        """
        Returns the configuration types.

        A distribution provider exports a service with an endpoint.
        This endpoint uses some kind of communications protocol with a set of
        configuration parameters.
        There are many different types but each endpoint is configured by only
        one configuration type.
        However, a distribution provider can be aware of different
        configuration types and provide synonyms to increase the change a
        receiving distribution provider can create a connection to this
        endpoint.
        This value of the configuration types is stored in the
        pelix.remote.PROP_IMPORTED_CONFIGS service property.

        :return: The configuration types (list of str)
        """
        # Return a copy of the list
        return self.__properties[pelix.remote.PROP_IMPORTED_CONFIGS][:]

    def get_framework_uuid(self):
        # type: () -> str
        """
        Returns the UUID of the framework exporting this endpoint, or None

        :return: A framework UUID (str) or None
        """
        return self.__properties.get(pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID)

    def get_id(self):
        # type: () -> str
        """
        Returns the endpoint's id.
        """
        return self.__properties[pelix.remote.PROP_ENDPOINT_ID]

    def get_intents(self):
        # type: () -> List[str]
        """
        Returns the list of intents implemented by this endpoint.

        The intents are based on the service.intents on an imported service,
        except for any intents that are additionally provided by the importing
        distribution provider.
        All qualified intents must have been expanded.
        This value of the intents is stored in the
        pelix.remote.PROP_INTENTS service property.

        :return: A list of intents (list of str)
        """
        # Return a copy of the list
        try:
            return self.__properties[pelix.remote.PROP_INTENTS][:]
        except KeyError:
            return []

    def get_interfaces(self):
        # type: () -> List[str]
        """
        Provides the list of interfaces implemented by the exported service.

        :return: A list of specifications (list of str)
        """
        return self.__properties[pelix.constants.OBJECTCLASS][:]

    def get_package_version(self, package):
        # type: (str) -> Tuple[int, ...]
        """
        Provides the version of the given package name.

        :param package: The name of the package
        :return: The version of the specified package as a tuple or (0,0,0)
        """
        name = "{0}{1}".format(
            pelix.remote.PROP_ENDPOINT_PACKAGE_VERSION_, package
        )
        try:
            # Get the version string
            version = self.__properties[name]

            # Split dots ('.')
            return tuple(version.split("."))
        except KeyError:
            # No version
            return 0, 0, 0

    def get_properties(self):
        # type: () -> dict
        """
        Returns all endpoint properties.

        :return: A copy of the endpoint properties
        """
        return self.__properties.copy()

    def get_service_id(self):
        # type: () -> int
        """
        Returns the service id for the service exported through this endpoint.

        :return: The ID of service on the exporter side, or 0
        """
        try:
            return self.__properties[pelix.remote.PROP_ENDPOINT_SERVICE_ID]
        except KeyError:
            # Not found
            return 0

    def is_same_service(self, endpoint):
        # type: (EndpointDescription) -> bool
        """
        Tests if this endpoint and the given one have the same framework UUID
        and service ID

        :param endpoint: Another endpoint
        :return: True if both endpoints represent the same remote service
        """
        return (
            self.get_framework_uuid() == endpoint.get_framework_uuid()
            and self.get_service_id() == endpoint.get_service_id()
        )

    def matches(self, ldap_filter):
        # type: (Any[str, pelix.ldapfilter.LDAPFilter]) -> bool
        """
        Tests the properties of this EndpointDescription against the given
        filter

        :param ldap_filter: A filter
        :return: True if properties matches the filter
        """
        return pelix.ldapfilter.get_ldap_filter(ldap_filter).matches(
            self.__properties
        )

    def to_import(self):
        # type: () -> ImportEndpoint
        """
        Converts an EndpointDescription bean to an ImportEndpoint

        :return: An ImportEndpoint bean
        """
        # Properties
        properties = self.get_properties()

        # Framework UUID
        fw_uid = self.get_framework_uuid()

        # Endpoint name
        try:
            # From Pelix UID
            name = properties[pelix.remote.PROP_ENDPOINT_NAME]
        except KeyError:
            # Generated
            name = "{0}.{1}".format(fw_uid, self.get_service_id())

        # Configuration / kind
        configurations = self.get_configuration_types()

        # Interfaces
        specifications = self.get_interfaces()

        return ImportEndpoint(
            self.get_id(),
            fw_uid,
            configurations,
            name,
            specifications,
            properties,
        )

    @classmethod
    def from_export(cls, endpoint):
        # type: (ExportEndpoint) -> EndpointDescription
        """
        Converts an ExportEndpoint bean to an EndpointDescription

        :param endpoint: An ExportEndpoint bean
        :return: An EndpointDescription bean
        """
        assert isinstance(endpoint, ExportEndpoint)

        # Service properties
        properties = endpoint.get_properties()

        # Set import keys
        properties[pelix.remote.PROP_ENDPOINT_ID] = endpoint.uid
        properties[pelix.remote.PROP_IMPORTED_CONFIGS] = endpoint.configurations
        properties[
            pelix.remote.PROP_EXPORTED_INTERFACES
        ] = endpoint.specifications

        # Remove export keys
        for key in (
            pelix.remote.PROP_EXPORTED_CONFIGS,
            pelix.remote.PROP_EXPORTED_INTERFACES,
            pelix.remote.PROP_EXPORTED_INTENTS,
            pelix.remote.PROP_EXPORTED_INTENTS_EXTRA,
        ):
            try:
                del properties[key]
            except KeyError:
                pass

        # Other information
        properties[pelix.remote.PROP_ENDPOINT_NAME] = endpoint.name
        properties[
            pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID
        ] = endpoint.framework

        return EndpointDescription(None, properties)


# ------------------------------------------------------------------------------


def to_import_properties(properties):
    # type: (dict) -> dict
    """
    Returns a dictionary where export properties have been replaced by import
    ones

    :param properties: A dictionary of service properties (with export keys)
    :return: A dictionary with import properties
    """
    # Copy the given dictionary
    props = properties.copy()

    # Add the "imported" property
    props[pelix.remote.PROP_IMPORTED] = True

    # Remote service ID
    try:
        props[pelix.remote.PROP_ENDPOINT_SERVICE_ID] = props.pop(
            pelix.constants.SERVICE_ID
        )
    except KeyError:
        # No service ID
        pass

    # Replace the "export configs"
    configs = props.pop(pelix.remote.PROP_EXPORTED_CONFIGS, None)
    if configs:
        props[pelix.remote.PROP_IMPORTED_CONFIGS] = configs

    # Clear other export properties
    for key in (
        pelix.remote.PROP_EXPORTED_INTENTS,
        pelix.remote.PROP_EXPORTED_INTENTS_EXTRA,
        pelix.remote.PROP_EXPORTED_INTERFACES,
    ):
        try:
            del props[key]
        except KeyError:
            # Key wasn't there
            pass

    return props


# ------------------------------------------------------------------------------


def compute_exported_specifications(svc_ref):
    # type: (pelix.framework.ServiceReference) -> List[str]
    """
    Computes the list of specifications exported by the given service

    :param svc_ref: A ServiceReference
    :return: The list of exported specifications (or an empty list)
    """
    if svc_ref.get_property(pelix.remote.PROP_EXPORT_NONE):
        # The export of this service is explicitly forbidden, stop here
        return []

    # Service specifications
    specs = svc_ref.get_property(pelix.constants.OBJECTCLASS)

    # Exported specifications
    exported_specs = svc_ref.get_property(pelix.remote.PROP_EXPORTED_INTERFACES)

    if exported_specs and exported_specs != "*":
        # A set of specifications is exported, replace "objectClass"
        iterable_exports = pelix.utilities.to_iterable(exported_specs, False)
        all_exported_specs = [
            spec for spec in specs if spec in iterable_exports
        ]
    else:
        # Export everything
        all_exported_specs = pelix.utilities.to_iterable(specs)

    # Authorized and rejected specifications
    export_only_specs = pelix.utilities.to_iterable(
        svc_ref.get_property(pelix.remote.PROP_EXPORT_ONLY), False
    )

    if export_only_specs:
        # Filter specifications (keep authorized specifications)
        return [
            spec for spec in all_exported_specs if spec in export_only_specs
        ]

    # Filter specifications (reject)
    rejected_specs = pelix.utilities.to_iterable(
        svc_ref.get_property(pelix.remote.PROP_EXPORT_REJECT), False
    )
    return [spec for spec in all_exported_specs if spec not in rejected_specs]


def extract_specifications(specifications, properties):
    # type: (Any[str, List[str]], dict) -> List[str]
    """
    Converts "python:/name" specifications to "name". Keeps the other
    specifications as is.

    :param specifications: The specifications found in a remote registration
    :param properties: Service properties
    :return: The filtered specifications (as a list)
    """
    all_specs = set(pelix.utilities.to_iterable(specifications))
    try:
        synonyms = pelix.utilities.to_iterable(
            properties[pelix.remote.PROP_SYNONYMS], False
        )
        all_specs.update(synonyms)
    except KeyError:
        # No synonyms property
        pass

    filtered_specs = set()
    for original in all_specs:
        try:
            # Extract information
            lang, spec = _extract_specification_parts(original)
            if lang == PYTHON_LANGUAGE:
                # Language match: keep the name only
                filtered_specs.add(spec)
            else:
                # Keep the name as is
                filtered_specs.add(original)
        except ValueError:
            # Ignore invalid specifications
            pass

    return list(filtered_specs)


def format_specifications(specifications):
    # type: (Iterable[str]) -> List[str]
    """
    Transforms the interfaces names into URI strings, with the interface
    implementation language as a scheme.

    :param specifications: Specifications to transform
    :return: The transformed names
    """
    transformed = set()
    for original in specifications:
        try:
            lang, spec = _extract_specification_parts(original)
            transformed.add(_format_specification(lang, spec))
        except ValueError:
            # Ignore invalid specifications
            pass

    return list(transformed)


def _extract_specification_parts(specification):
    # type: (str) -> Tuple[str, str]
    """
    Extract the language and the interface from a "language:/interface"
    interface name

    :param specification: The formatted interface name
    :return: A (language, interface name) tuple
    :raise ValueError: Invalid specification content
    """
    try:
        # Parse the URI-like string
        parsed = urlparse(specification)
    except:
        # Invalid URL
        raise ValueError("Invalid specification URL: {0}".format(specification))

    # Extract the interface name
    interface = parsed.path

    # Extract the language, if given
    language = parsed.scheme
    if not language:
        # Simple name, without scheme
        language = PYTHON_LANGUAGE
    else:
        # Formatted name: un-escape it, without the starting '/'
        interface = _unescape_specification(interface[1:])

    return language, interface


def _format_specification(language, specification):
    # type: (str, str) -> str
    """
    Formats a "language://interface" string

    :param language: Specification language
    :param specification: Specification name
    :return: A formatted string
    """
    return "{0}:/{1}".format(language, _escape_specification(specification))


def _escape_specification(specification):
    # type: (str) -> str
    """
    Escapes the interface string: replaces slashes '/' by '%2F'

    :param specification: Specification name
    :return: The escaped name
    """
    return specification.replace("/", "%2F")


def _unescape_specification(specification):
    # type: (str) -> str
    """
    Unescapes the interface string: replaces '%2F' by slashes '/'

    :param specification: Specification name
    :return: The unescaped name
    """
    return specification.replace("%2F", "/")
