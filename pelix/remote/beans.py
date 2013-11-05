#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Specifications handling utility methods

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.1.1
:status: Beta

..

    Copyright 2013 isandlaTech

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
__version_info__ = (0, 1, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix
import pelix.remote

# Standard library
try:
    # Python 3
    from urllib.parse import urlparse

except ImportError:
    # Python 2
    from urlparse import urlparse


# ------------------------------------------------------------------------------

PYTHON_LANGUAGE = "python"
""" Prefix to use for the Python specifications """

#-------------------------------------------------------------------------------

class ExportEndpoint(object):
    """
    Represents an end point to access an exported service
    """
    def __init__(self, uid, kind, name, svc_ref, service, url):
        """
        Sets up the members

        :param uid: Unique identified of the end point
        :param kind: Kind of end point (xmlrpc, ...)
        :param name: Name of the end point
        :param svc_ref: ServiceReference of the exported service
        :param service: Instance of the exported service
        :param url: URL to access to the end point
        :raise ValueError: Invalid UID or the end point exports nothing
                           (all specifications have been filtered)
        """
        if not uid:
            raise ValueError("Invalid GUID")

        # Given information
        self.__uid = uid
        self.__instance = service
        self.__reference = svc_ref
        self.__kind = kind
        self.__name = name
        self.__url = url

        # Exported specifications
        self.__exported_specs = []
        self.__compute_specifications()
        if not self.__exported_specs:
            raise ValueError("End point %s, %s, exports nothing",
                             self.__uid, self.__name)


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
        return "ExportEndpoint(uid={0}, kind={1}, specs={2})" \
            .format(self.__uid, self.__kind, self.__compute_specifications())


    def __compute_specifications(self):
        """
        Computes the list of exported specifications
        """
        specs = self.__reference.get_property(pelix.framework.OBJECTCLASS)
        exported_specs = self.__reference.get_property(\
                                        pelix.remote.PROP_EXPORTED_INTERFACES)

        if exported_specs and exported_specs != "*":
            # A set of specifications is exported, replace "objectClass"
            if isinstance(exported_specs, (list, tuple, set)):
                filtered_specs = [spec for spec in specs
                                         if spec in exported_specs]

        else:
            # Export everything
            filtered_specs = specs

        # Transform the specifications for export (add the language prefix)
        self.__exported_specs = format_specifications(filtered_specs)


    # Access to the service
    @property
    def instance(self):
        """
        Service instance
        """
        return self.__instance


    @property
    def reference(self):
        """
        Service reference
        """
        return self.__reference


    # End point properties
    @property
    def uid(self):
        """
        End point unique identifier
        """
        return self.__uid


    @property
    def kind(self):
        """
        Kind of end point
        """
        return self.__kind

    @property
    def name(self):
        """
        Name of the end point
        """
        return self.__name

    @property
    def specifications(self):
        """
        Returns the exported specifications
        """
        return self.__exported_specs

    @property
    def url(self):
        """
        URL to access the end point
        """
        return self.__url

#-------------------------------------------------------------------------------

class ImportEndpoint(object):
    """
    Represents an end point to access an imported service
    """
    def __init__(self, uid, framework, kind, name, url, specifications,
                 properties):
        """
        Sets up the members

        :param uid: Unique identified of the end point
        :param framework: UID of the framework exporting the end point
                          (can be None)
        :param kind: Kind of end point (xmlrpc, ...)
        :param name: Name of the end point
        :param url: URL to access to the end point
        :param specifications: Specifications of the exported service
        :param properties: Properties of the service
        """
        self.__uid = uid
        self.__fw_uid = framework or None
        self.__kind = kind
        self.__name = name
        self.__url = url
        self.__properties = properties.copy() if properties else {}

        # Extract the language prefix in specifications
        self.__specifications = extract_specifications(specifications)


    def __str__(self):
        """
        String representation of the end point
        """
        return "ImportEndpoint(uid={0}, framework={1}, kind={2}, specs={3})" \
            .format(self.__uid, self.__fw_uid, self.__kind,
                    self.__specifications)


    # Access to the service informations
    @property
    def specifications(self):
        """
        Specifications of the service
        """
        return self.__specifications


    @property
    def properties(self):
        """
        Specifications of the service
        """
        return self.__properties


    @properties.setter
    def properties(self, properties):
        """
        Specifications of the service
        """
        self.__properties = properties


    # End point properties
    @property
    def uid(self):
        """
        End point unique identifier
        """
        return self.__uid

    @property
    def framework(self):
        """
        UID of the framework exporting this end point
        """
        return self.__fw_uid

    @property
    def kind(self):
        """
        Kind of end point
        """
        return self.__kind

    @property
    def name(self):
        """
        Name of the end point
        """
        return self.__name

    @property
    def url(self):
        """
        URL to access the end point
        """
        return self.__url


# ------------------------------------------------------------------------------

def extract_specifications(specifications):
    """
    Converts "python:/name" specifications to "name". Keeps the other
    specifications as is.

    :param specifications: The specifications found in a remote registration
    :return: The filtered specifications (as a set)
    """
    filtered_specs = set()

    for original in specifications:
        try:
            # Extract informations
            lang, spec = _extract_specifications_parts(original)
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
    """
    Transforms the interfaces names into a URI string, with the interface
    implementation language as a scheme.

    :param specifications: Specifications to transform
    :return: The transformed names
    """
    transformed = set()

    for original in specifications:
        try:
            lang, spec = _extract_specifications_parts(original)
            transformed.add(_format_specification(lang, spec))

        except ValueError:
            # Ignore invalid specifications
            pass

    return list(transformed)


def _extract_specifications_parts(specification):
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

    return (language, interface)


def _format_specification(language, specification):
    """
    Formats a "language://interface" string

    :param language: Specification language
    :param specification: Specification name
    :return: A formatted string
    """
    return "{0}:/{1}".format(language, _escape_specification(specification))


def _escape_specification(specification):
    """
    Escapes the interface string: replaces slashes '/' by '%2F'

    :param specification: Specification name
    :return: The escaped name
    """
    return specification.replace('/', '%2F')


def _unescape_specification(specification):
    """
    Unescapes the interface string: replaces '%2F' by slashes '/'

    :param specification: Specification name
    :return: The escaped name
    """
    return specification.replace('%2F', '/')
