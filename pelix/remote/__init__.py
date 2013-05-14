#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services package

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.1
:status: Alpha

..

    This file is part of iPOPO.

    iPOPO is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    
    iPOPO is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with iPOPO. If not, see <http://www.gnu.org/licenses/>.
"""

# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(map(str, __version_info__))

# Documentation strings format
__docformat__ = "restructuredtext en"

#-------------------------------------------------------------------------------

# Pelix framework constants
import pelix.framework

#-------------------------------------------------------------------------------

SERVICE_DISPATCHER = "pelix.remote.dispatcher"
""" Remote call dispatcher """

SERVICE_DISPATCHER_SERVLET = "pelix.remote.dispatcher.servlet"
""" Servlet to access the content of the dispatcher """

SERVICE_REGISTRY = "pelix.remote.registry"
""" Registry of imported end points """

SERVICE_ENDPOINT_LISTENER = "pelix.remote.endpoint.listener"
"""
End point creation/deletion listeners, with listen.exported and/or
listen.imported properties.
"""

PROP_FRAMEWORK_UID = "pelix.remote.framework.uid"
"""
The UID of the framework that exports the service.
This service property is set by the discoverer, when it parses an end point
event packet.
"""

PROP_ENDPOINT_NAME = "endpoint.name"
""" Name of the end point of an exported service """

PREFIX_PROP_EXPORTED = "service.exported."
""" Prefix common to all export properties (for filtering) """

PROP_EXPORTED_CONFIGS = "{0}configs".format(PREFIX_PROP_EXPORTED)
""" Export configurations (xmlrpc, ...) (array of strings) """

PROP_EXPORTED_INTERFACES = "{0}interfaces".format(PREFIX_PROP_EXPORTED)
""" Exported specifications: must be an array of strings """

PROP_IMPORTED = "service.imported"
""" Flag indicating that the service has been imported """

PROP_IMPORTED_CONFIGS = "service.imported.configs"
""" Configurations of the imported service (mirror of PROP_EXPORTED_CONFIGS) """

PROP_IMPORTED_INTERFACES = "service.imported.interfaces"
""" Imported specifications (mirror of PROP_EXPORTED_INTERFACES) """

PROP_LISTEN_IMPORTED = "listen.imported"
"""
If set to True, the end point listener will be notified of imported end points
"""

PROP_LISTEN_EXPORTED = "listen.exported"
"""
If set to True, the end point listener will be notified of exported end points
"""

#-------------------------------------------------------------------------------

class RemoteServiceError(Exception):
    """
    Error while accessing a remote service entry
    """
    pass

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


    def __compute_specifications(self):
        """
        Computes the list of exported specifications
        """
        specs = self.__reference.get_property(pelix.framework.OBJECTCLASS)
        exported_specs = self.__reference.get_property(PROP_EXPORTED_INTERFACES)

        if exported_specs and exported_specs != "*":
            # A set of specifications is exported, replace "objectClass"
            if isinstance(exported_specs, (list, tuple, set)):
                self.__exported_specs = [spec for spec in specs
                                         if spec in exported_specs]

        else:
            # Export everything
            self.__exported_specs = specs


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
    def __init__(self, uid, kind, name, url, specifications, properties):
        """
        Sets up the members
        
        :param uid: Unique identified of the end point
        :param kind: Kind of end point (xmlrpc, ...)
        :param name: Name of the end point
        :param url: URL to access to the end point
        :param specifications: Specifications of the exported service
        :param properties: Properties of the service
        """
        self.__uid = uid
        self.__kind = kind
        self.__name = name
        self.__url = url
        self.__specifications = specifications
        self.__properties = properties.copy() if properties else {}

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
