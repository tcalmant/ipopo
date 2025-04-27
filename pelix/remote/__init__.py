#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services package

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

from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple, Union

import pelix.http
from pelix.constants import Specification
from pelix.internals.registry import ServiceReference
from pelix.remote.beans import ExportEndpoint, ImportEndpoint

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

FACTORY_REGISTRY_SERVLET = "pelix-remote-dispatcher-servlet-factory"
"""
Name of the factory of the Servlet component giving access to registries
"""


FACTORY_DISCOVERY_MQTT = "pelix-remote-discovery-mqtt-factory"
""" Name of the MQTT discovery component factory """

FACTORY_DISCOVERY_MULTICAST = "pelix-remote-discovery-multicast-factory"
""" Name of the Multicast discovery component factory """

FACTORY_DISCOVERY_ZEROCONF = "pelix-remote-discovery-zeroconf-factory"
""" Name of the Zeroconf/mDNS discovery component factory """

FACTORY_DISCOVERY_REDIS = "pelix-remote-discovery-redis-factory"
""" Name of the Redis-based discovery component factory """

FACTORY_DISCOVERY_ZOOKEEPER = "pelix-remote-discovery-zookeeper-factory"
""" Name of the ZooKeeper-based discovery component factory """


FACTORY_TRANSPORT_JSONRPC_EXPORTER = "pelix-jsonrpc-exporter-factory"
""" Name of the JSON-RPC exporter component factory """
FACTORY_TRANSPORT_JSONRPC_IMPORTER = "pelix-jsonrpc-importer-factory"
""" Name of the JSON-RPC importer component factory """

FACTORY_TRANSPORT_XMLRPC_EXPORTER = "pelix-xmlrpc-exporter-factory"
""" Name of the XML-RPC exporter component factory """
FACTORY_TRANSPORT_XMLRPC_IMPORTER = "pelix-xmlrpc-importer-factory"
""" Name of the XML-RPC importer component factory """

FACTORY_TRANSPORT_JABSORBRPC_EXPORTER = "pelix-jabsorbrpc-exporter-factory"
""" Name of the JABSORB-RPC exporter component factory """
FACTORY_TRANSPORT_JABSORBRPC_IMPORTER = "pelix-jabsorbrpc-importer-factory"
""" Name of the JABSORB-RPC importer component factory """

FACTORY_TRANSPORT_MQTTRPC_EXPORTER = "pelix-mqttrpc-exporter-factory"
""" Name of the MQTT-RPC exporter component factory """
FACTORY_TRANSPORT_MQTTRPC_IMPORTER = "pelix-mqttrpc-importer-factory"
""" Name of the MQTT-RPC importer component factory """

# ------------------------------------------------------------------------------

SERVICE_DISPATCHER = "pelix.remote.dispatcher"
""" Remote call dispatcher """

SERVICE_DISPATCHER_SERVLET = "pelix.remote.dispatcher.servlet"
""" Servlet to access the content of the dispatcher """

SERVICE_REGISTRY = "pelix.remote.registry"
""" Registry of imported end points """

SERVICE_IMPORT_PROVIDER = "pelix.remote.provider.import"
""" Remote Services: importer """

SERVICE_EXPORT_PROVIDER = "pelix.remote.provider.export"
""" Remote Services: exporter """

SERVICE_EXPORT_ENDPOINT_LISTENER = "pelix.remote.endpoint.export.listener"
""" Exported endpoints listener specification """

SERVICE_IMPORT_ENDPOINT_LISTENER = "pelix.remote.endpoint.import.listener"
""" Imported endpoints listener specification """

# ------------------------------------------------------------------------------
# Properties used by Pelix

PROP_ENDPOINT_NAME = "endpoint.name"
""" Name of the end point of an exported service """

PREFIX_PROP_EXPORTED = "service.exported."
""" Prefix common to all export properties (for filtering) """

PROP_IMPORTED_INTERFACES = "service.imported.interfaces"
""" Imported specifications (mirror of PROP_EXPORTED_INTERFACES) """

PROP_SYNONYMS = "pelix.remote.synonyms"
"""
Synonyms of the exported specifications. Used of multi-language applications.
"""

PROP_EXPORT_NONE = "pelix.remote.export.none"
"""
A service with this property set to a non-false value (any value other than an
empty string, False, ...) will never be exported.
This can be used to avoid the export of a service due to properties of the
component providing it.
If this property is set, the other "pelix.remote.export" properties are
ignored.
"""

PROP_EXPORT_ONLY = "pelix.remote.export.only"
"""
Only the specifications given in this property can be exported, if the service
provides them.
This property is used only if it has a non-false value.
If given, the "pelix.remote.export.reject" is ignored.
"""

PROP_EXPORT_REJECT = "pelix.remote.export.reject"
"""
List of specifications that must never exported. Acts as a filter when
exporting all other specifications with the "service.exported.interfaces"
property set to "*".
"""

# ------------------------------------------------------------------------------
# Properties declared in RSA specifications

PROP_EXPORTED_CONFIGS = "service.exported.configs"
""" Export configurations (xmlrpc, ...) (str or array of str) """

PROP_EXPORTED_INTERFACES = "service.exported.interfaces"
""" Exported specifications (str or array of str) """

PROP_IMPORTED = "service.imported"
""" Flag indicating that the service has been imported """

PROP_IMPORTED_CONFIGS = "service.imported.configs"
""" Configurations of the imported service (array of str) """

PROP_EXPORTED_INTENTS = "service.exported.intents"
"""
Service property identifying the intents that the distribution provider must
implement to distribute the service. Intents listed in this property are
reserved for intents that are critical for the code to function correctly,
for example, ordering of messages.
These intents should not be configurable. (str or array of str)
"""

PROP_EXPORTED_INTENTS_EXTRA = "service.exported.intents.extra"
"""
Service property identifying the extra intents that the distribution provider
must implement to distribute the service.
This property is merged with the ``service.exported.intents`` property before
the distribution provider interprets the listed intents; it has therefore the
same semantics but the property should be configurable so the administrator can
choose the intents based on the topology.
Bundles should therefore make this property configurable, for example through
the Configuration Admin service. (str or array of str)
"""

PROP_INTENTS = "service.intents"
"""
Service property identifying the intents that this service implement
(array of str)
"""

PROP_ENDPOINT_FRAMEWORK_UUID = "endpoint.framework.uuid"
""" UUID of the framework exporting the service (str) """

PROP_ENDPOINT_ID = "endpoint.id"
""" ID of the endpoint (str) """

PROP_ENDPOINT_PACKAGE_VERSION_ = "endpoint.package.version."
"""
Prefix for an endpoint property identifying the package version for a
specification.
For example, the property ``endpoint.package.version.com.acme=1.3`` describes
the version of the package for the ``com.acme.Foo`` specification.
This endpoint property for an interface package does not have to be set.
If not set, the value must be assumed to be 0. (str)
"""

PROP_ENDPOINT_SERVICE_ID = "endpoint.service.id"
"""
The service id of the exported service. Can be absent or 0 if the corresponding
endpoint is not for an OSGi service. (int)
"""

PROP_REMOTE_CONFIGS_SUPPORTED = "remote.configs.supported"
"""
Service property identifying the configuration types supported by a
distribution provider.
Registered by the distribution provider on one of its services to indicate the
supported configuration types. (str or array of str)
"""

PROP_REMOTE_INTENTS_SUPPORTED = "remote.intents.supported"
"""
Service property identifying the intents supported by a distribution provider.
Registered by the distribution provider on one of its services to indicate the
vocabulary of implemented intents. (str or array of str)
"""

# ------------------------------------------------------------------------------
# Zeroconf discovery properties

PROP_ZEROCONF_TYPE = "zeroconf.service.type"
""" Name of the Zeroconf/mDNS discovery component factory """

VALUE_ZEROCONF_TYPE_ECF = "_ecfosgirsvc._default.default."
"""
Service type recognized by Eclipse ECF as a description of a remote service.
WARNING: Doesn't work as is with pyzeroconf: the library must be patched.
=> checking in zeroconf.mdns.DNSQuestion must be removed (around line 220)
"""

# ------------------------------------------------------------------------------


class RemoteServiceError(Exception):
    """
    Error while accessing a remote service entry
    """

    pass


@Specification(SERVICE_REGISTRY)
class RemoteServiceRegistry(Protocol):
    """
    Specification of the remote service registry
    """

    def add(self, endpoint: ImportEndpoint) -> bool:
        """
        Registers an end point and notifies listeners. Does nothing if the
        endpoint UID was already known.

        :param endpoint: An :class:`~pelix.remote.beans.ImportEndpoint` object
        :return: True if the end point has been added
        """
        ...

    def update(self, uid: str, new_properties: Dict[str, Any]) -> bool:
        """
        Updates an end point and notifies listeners

        :param uid: The UID of the end point
        :param new_properties: The new properties of the end point
        :return: True if the endpoint is known, else False
        """
        ...

    def contains(self, endpoint: Union[str, ImportEndpoint]) -> bool:
        """
        Checks if an endpoint is in the registry

        :param endpoint: An endpoint UID or an :class:`~pelix.remote.beans.ImportEndpoint` object
        :return: True if the endpoint is known, else False
        """
        ...

    def remove(self, uid: str) -> bool:
        """
        Unregisters an end point and notifies listeners

        :param uid: The UID of the end point to unregister
        :return: True if the endpoint was known
        """
        ...

    def lost_framework(self, uid: Optional[str]) -> None:
        """
        Unregisters all the end points associated to the given framework UID

        :param uid: The UID of a framework
        """
        ...


@Specification(SERVICE_DISPATCHER)
class RemoteServiceDispatcher(Protocol):
    """
    Remote service dispatcher
    """

    def get_endpoints(self, kind: Optional[str] = None, name: Optional[str] = None) -> List[ExportEndpoint]:
        """
        Retrieves all end points matching the given kind and/or name

        :param kind: A kind of end point
        :param name: The name of the end point
        :return: A list of :class:`~pelix.remote.beans.ExportEndpoint` matching the parameters
        """
        ...

    def get_endpoint(self, uid: str) -> Optional[ExportEndpoint]:
        """
        Return an exported endpoint
        """
        ...


@Specification(SERVICE_DISPATCHER_SERVLET)
class RemoteServiceDispatcherServlet(pelix.http.Servlet, Protocol):
    """
    Remote service dispatcher servlet
    """

    def get_access(self) -> Optional[Tuple[int, str]]:
        """
        Returns the port and path to access this servlet with the first
        bound HTTP service.
        Returns None if this servlet is still not bound to a server

        :return: A tuple: (port, path) or None
        """
        ...

    def send_discovered(self, host: str, port: int, path: str) -> bool:
        """
        Sends a "discovered" HTTP POST request to the dispatcher servlet of the
        framework that has been discovered

        :param host: The address of the sender
        :param port: Port of the HTTP server of the sender
        :param path: Path of the dispatcher servlet
        :return: True if the request has been handled by the peer
        """
        ...

    def grab_endpoint(self, host: str, port: int, path: str, uid: str) -> Optional[ImportEndpoint]:
        """
        Retrieves the description of the end point with the given UID from the
        given dispatcher servlet.
        Returns an ImportEndpoint bean, or None in case of error.
        Does not register the end point.

        :param host: Dispatcher host address
        :param port: Dispatcher HTTP service port
        :param path: Path to the dispatcher servlet
        :param uid: The UID of an end point
        :return: An ImportEndpoint bean or None
        """
        ...


@Specification(SERVICE_EXPORT_PROVIDER)
class RemoteServiceExportProvider(Protocol):
    """
    Remote service exporter
    """

    def handles(self, configs: Iterable[str]) -> bool:
        """
        Checks if this provider handles the given configuration types

        :param configurations: Configuration types
        """
        ...

    def export_service(
        self, svc_ref: ServiceReference[Any], name: str, fw_uid: Optional[str]
    ) -> Optional[ExportEndpoint]:
        """
        Prepares an export endpoint

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: An ExportEndpoint bean
        :raise NameError: Already known name
        :raise BundleException: Error getting the service
        """
        ...

    def update_export(
        self, endpoint: ExportEndpoint, new_name: str, old_properties: Optional[Dict[str, Any]]
    ) -> None:
        """
        Updates an export endpoint

        :param endpoint: An ExportEndpoint bean
        :param new_name: Future endpoint name
        :param old_properties: Previous properties
        :raise NameError: Rename refused
        """
        ...

    def unexport_service(self, endpoint: ExportEndpoint) -> None:
        """
        Deletes an export endpoint

        :param endpoint: An ExportEndpoint bean
        """
        ...


@Specification(SERVICE_EXPORT_ENDPOINT_LISTENER)
class RemoteServiceExportEndpointListener(Protocol):
    """
    Remote service export endpoint listener
    """

    def endpoints_added(self, endpoints: List[ExportEndpoint]) -> None:
        """
        Notification of new remote service export endpoints
        """
        ...

    def endpoint_updated(self, endpoint: ExportEndpoint, old_properties: Optional[Dict[str, Any]]) -> None:
        """
        Notification of the update of an endpoint of an an exported service
        """
        ...

    def endpoint_removed(self, endpoint: ExportEndpoint) -> None:
        """
        Notification of the removal of an endpoint of an an exported service
        """
        ...


@Specification(SERVICE_IMPORT_ENDPOINT_LISTENER)
class RemoteServiceImportEndpointListener(Protocol):
    """
    Remote service import endpoint listener
    """

    def endpoint_added(self, endpoint: ImportEndpoint) -> None:
        """
        Notification of new imported remote service endpoint
        """
        ...

    def endpoint_updated(self, endpoint: ImportEndpoint, old_properties: Optional[Dict[str, Any]]) -> None:
        """
        Notification of the removal of a remote service
        """
        ...

    def endpoint_removed(self, endpoint: ImportEndpoint) -> None:
        """
        Notification of the removal of a remote service endpoint
        """
        ...
