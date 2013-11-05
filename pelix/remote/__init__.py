#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services package

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

#-------------------------------------------------------------------------------

FACTORY_REGISTRY_SERVLET = "pelix-remote-dispatcher-servlet-factory"
""" Name of the factory of the Servlet component giving access to registries """

FACTORY_DISCOVERY_MULTICAST = "pelix-remote-discovery-multicast-factory"
""" Name of the Multicast discovery component factory """

FACTORY_TRANSPORT_JSONRPC_EXPORTER = "pelix-jsonrpc-exporter-factory"
""" Name of the JSON-RPC exporter component factory """
FACTORY_TRANSPORT_JSONRPC_IMPORTER = "pelix-jsonrpc-importer-factory"
""" Name of the JSON-RPC importer component factory """

FACTORY_TRANSPORT_XMLRPC_EXPORTER = "pelix-xmlrpc-exporter-factory"
""" Name of the XML-RPC exporter component factory """
FACTORY_TRANSPORT_XMLRPC_IMPORTER = "pelix-xmlrpc-importer-factory"
""" Name of the XML-RPC importer component factory """

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
