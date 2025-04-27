#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Zeroconf (mDNS) discovery and event notification

This module depends on the zeroconf package

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

import json
import logging
import socket
from typing import Any, Dict, List, Optional, Protocol, Union, cast

import zeroconf

import pelix.constants
import pelix.remote
import pelix.remote.beans as beans
from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Requires, Validate
from pelix.utilities import is_bytes, is_string, to_str

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

DEFAULT_ZEROCONF_TYPE = "_pelix-rs._tcp.local."


class _ZeroConfServiceListener(Protocol):
    """
    Protocol of a Zeroconf service listener, as it is not defined in the zeroconf
    package package anymore
    """

    def add_service(self, zc: zeroconf.Zeroconf, type_: str, name: str) -> None:
        """
        Called by Zeroconf when a record is updated

        :param zc: The Zeroconf instance than notifies of the modification
        :param type_: Service type
        :param name: Service name
        """
        ...

    def remove_service(self, zc: zeroconf.Zeroconf, type_: str, name: str) -> None:
        """
        Called by Zeroconf when a record is removed

        :param zc: The Zeroconf instance than notifies of the modification
        :param type_: Service type
        :param name: Service name
        """
        ...


@ComponentFactory(pelix.remote.FACTORY_DISCOVERY_ZEROCONF)
@Provides(pelix.remote.RemoteServiceExportEndpointListener)
@Property("_rs_type", pelix.remote.PROP_ZEROCONF_TYPE, DEFAULT_ZEROCONF_TYPE)
@Property("_ttl", "zeroconf.ttl", 60)
@Requires("_access", pelix.remote.SERVICE_DISPATCHER_SERVLET)
@Requires("_registry", pelix.remote.RemoteServiceRegistry)
class ZeroconfDiscovery(pelix.remote.RemoteServiceExportEndpointListener, _ZeroConfServiceListener):
    """
    Remote services discovery and notification using the module zeroconf
    """

    # Imported endpoints registry
    _registry: pelix.remote.RemoteServiceRegistry

    # Dispatcher access
    _access: pelix.remote.RemoteServiceDispatcherServlet

    # Service type for the Pelix dispatcher servlet
    DNS_DISPATCHER_TYPE = "_rs-dispatcher._tcp.local."

    def __init__(self) -> None:
        """
        Sets up the component
        """
        # Remote Service type
        self._rs_type: str = DEFAULT_ZEROCONF_TYPE

        # Zeroconf TTL
        self._ttl = 60

        # Framework UID
        self._fw_uid: Optional[str] = None

        # Address of this framework
        self._address: Optional[bytes] = None

        # Zeroconf
        self._zeroconf: Optional[zeroconf.Zeroconf] = None
        self._browsers: List[zeroconf.ServiceBrowser] = []

        # Endpoint UID -> ServiceInfo
        self._export_infos: Dict[str, zeroconf.ServiceInfo] = {}

        # mDNS name -> Endpoint UID
        self._imported_endpoints: Dict[str, str] = {}

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Get the host address
        self._address = socket.inet_aton(socket.gethostbyname(socket.gethostname()))

        # Prepare Zeroconf
        self._zeroconf = zeroconf.Zeroconf()

        # Register the dispatcher servlet as a service
        self.__register_servlet()

        # Listen to our types
        self._browsers.append(
            zeroconf.ServiceBrowser(self._zeroconf, ZeroconfDiscovery.DNS_DISPATCHER_TYPE, self)
        )
        self._rs_type = self._rs_type or DEFAULT_ZEROCONF_TYPE
        self._browsers.append(zeroconf.ServiceBrowser(self._zeroconf, self._rs_type, self))

        _logger.debug("Zeroconf discovery validated")

    @Invalidate
    def invalidate(self, _: BundleContext) -> None:
        """
        Component invalidated
        """
        # Stop listeners
        for browser in self._browsers:
            browser.cancel()

        # Close Zeroconf
        if self._zeroconf is not None:
            self._zeroconf.unregister_all_services()
            self._zeroconf.close()

        # Clean up
        self._export_infos.clear()
        self._zeroconf = None
        self._fw_uid = None

        _logger.debug("Zeroconf discovery invalidated")

    @staticmethod
    def _serialize_properties(props: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts properties values into strings
        """
        new_props: Dict[str, Any] = {}

        for key, value in props.items():
            if is_string(value):
                new_props[key] = value
            else:
                try:
                    new_props[key] = json.dumps(value)
                except ValueError:
                    new_props[key] = f"pelix-type:{type(value).__name__}:{repr(value)}"

        # FIXME: to simplify the usage with ECF, send single strings instead of
        # arrays
        for key in (
            pelix.constants.OBJECTCLASS,
            pelix.remote.PROP_IMPORTED_CONFIGS,
        ):
            try:
                new_props[key] = props[key][0]
            except KeyError:
                pass

        return new_props

    @staticmethod
    def _deserialize_properties(
        props: Dict[Union[str, bytes], Optional[Union[str, bytes]]]
    ) -> Dict[str, Any]:
        """
        Converts properties values into their type
        """
        new_props: Dict[str, Any] = {}
        for key, raw_value in props.items():
            key = to_str(key)
            if raw_value is None:
                new_props[key] = None
                continue

            value: str = to_str(raw_value) if is_bytes(raw_value) else cast(str, raw_value)

            try:
                try:
                    new_props[key] = json.loads(value)
                except (TypeError, ValueError):
                    if is_string(value) and value.startswith("pelix-type:"):
                        # Pseudo-serialized
                        value_type, value = value.split(":", 3)[2:]
                        if "." in value_type and value_type not in value:
                            # Not a builtin type...
                            _logger.warning("Won't work: %s (%s)", value, value_type)

                        new_props[key] = eval(value)
                    else:
                        # String
                        new_props[key] = value
            except Exception as ex:
                _logger.error("Can't deserialize %s: %s", value, ex)

        return new_props

    def __register_servlet(self) -> None:
        """
        Registers the Pelix Remote Services dispatcher servlet as a service via mDNS
        """
        assert self._zeroconf is not None

        # Get the dispatcher servlet access
        access = self._access.get_access()
        if access is None:
            raise ValueError("No dispatcher servlet access to broadcast")

        # Convert properties to be stored as strings
        properties = {
            "pelix.version": pelix.__version__,
            pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID: self._fw_uid,
            "pelix.access.port": access[0],
            "pelix.access.path": access[1],
        }
        properties = self._serialize_properties(properties)

        # Prepare the service type
        svc_name = f"{self._fw_uid}.{ZeroconfDiscovery.DNS_DISPATCHER_TYPE}"

        # Prepare the mDNS entry
        info = zeroconf.ServiceInfo(
            ZeroconfDiscovery.DNS_DISPATCHER_TYPE,  # Type
            svc_name,  # Name
            address=self._address,  # Access address
            port=access[0],  # Access port
            properties=properties,
        )

        # Register the service
        self._zeroconf.register_service(info, self._ttl)

    def endpoints_added(self, endpoints: List[beans.ExportEndpoint]) -> None:
        """
        Multiple endpoints have been added

        :param endpoints: A list of ExportEndpoint beans
        """
        if self._zeroconf is None:
            _logger.error("Zeroconf is not ready")
            return

        # Get the dispatcher servlet port
        access = self._access.get_access()
        if access is None:
            _logger.error("Dispatcher servlet is not ready")
            return

        access_port = access[0]

        # Handle each one separately
        for endpoint in endpoints:
            self._endpoint_added(endpoint, access_port)

    def _endpoint_added(self, exp_endpoint: beans.ExportEndpoint, access_port: int) -> None:
        """
        A new service is exported

        :param exp_endpoint: An ExportEndpoint bean
        :param access_port: The dispatcher access port
        """
        if self._zeroconf is None:
            _logger.error("Zeroconf is not ready")
            return

        # Convert the export endpoint into an EndpointDescription bean
        endpoint = beans.EndpointDescription.from_export(exp_endpoint)

        # Get its properties
        properties = endpoint.get_properties()

        # Convert properties to be stored as strings
        properties = self._serialize_properties(properties)

        # Prepare the service name
        svc_name = f"{endpoint.get_id().replace('-', '')}.{self._rs_type}"

        # Prepare the mDNS entry
        info = zeroconf.ServiceInfo(
            self._rs_type,  # Type
            svc_name,  # Name
            address=self._address,  # Access address
            port=access_port,  # Access port
            properties=properties,
        )

        self._export_infos[exp_endpoint.uid] = info

        # Register the service
        self._zeroconf.register_service(info, self._ttl)

    def endpoint_updated(
        self, endpoint: beans.ExportEndpoint, old_properties: Optional[Dict[str, Any]]
    ) -> None:
        # pylint: disable=W0613
        """
        An end point is updated

        :param endpoint: The updated endpoint
        :param old_properties: Previous properties of the endpoint
        """
        # Not available...
        # TODO: register a temporary service while the update is performed ?
        return

    def endpoint_removed(self, endpoint: beans.ExportEndpoint) -> None:
        """
        An end point is removed

        :param endpoint: Endpoint being removed
        """
        if self._zeroconf is None:
            _logger.error("Zeroconf is not ready")
            return

        try:
            # Get the associated service info
            info = self._export_infos.pop(endpoint.uid)
        except KeyError:
            # Unknown service
            _logger.debug("Unknown removed endpoint: %s", endpoint)
        else:
            # Unregister the service
            self._zeroconf.unregister_service(info)

    def _get_service_info(
        self, svc_type: str, name: str, max_retries: int = 10
    ) -> Optional[zeroconf.ServiceInfo]:
        """
        Tries to get information about the given mDNS service

        :param svc_type: Service type
        :param name: Service name
        :param max_retries: Number of retries before timeout
        :return: A ServiceInfo bean
        """
        info = None
        retries = 0
        while self._zeroconf is not None and info is None and retries < max_retries:
            # Try to get information about the service...
            info = self._zeroconf.get_service_info(svc_type, name)
            retries += 1

        return info

    def add_service(self, zc: zeroconf.Zeroconf, type_: str, name: str) -> None:
        """
        Called by Zeroconf when a record is updated

        :param zc: The Zeroconf instance than notifies of the modification
        :param type_: Service type
        :param name: Service name
        """
        # Get information about the service
        info = self._get_service_info(type_, name)
        if info is None:
            _logger.warning("Timeout reading service information: %s - %s", type_, name)
            return

        # Read properties
        properties = self._deserialize_properties(info.properties)

        try:
            sender_uid = properties[pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID]
            if sender_uid == self._fw_uid:
                # We sent this message
                return
        except KeyError:
            # Not a Pelix message
            _logger.warning("Not a Pelix record: %s", properties)
            return

        if type_ == ZeroconfDiscovery.DNS_DISPATCHER_TYPE:
            # Dispatcher servlet found, get source info
            if info.port is None:
                _logger.warning("Ignore discovered service with no port information: %s", info)
                return

            address: Optional[str] = None
            if info.address:
                address = socket.inet_ntoa(info.address)
            elif info.server:
                address = info.server

            if not address:
                _logger.warning("Ignore discovered service with no server information: %s", info)
                return

            self._access.send_discovered(address, info.port, properties["pelix.access.path"])
        elif type_ == self._rs_type:
            # Remote service
            # Get the first available configuration
            configuration = properties[pelix.remote.PROP_IMPORTED_CONFIGS]
            if not isinstance(configuration, str):
                configuration = configuration[0]

            # Ensure we have a list of specifications
            specs = properties[pelix.constants.OBJECTCLASS]
            if isinstance(specs, str):
                specs = [specs]

            try:
                # Make an import bean
                endpoint = beans.ImportEndpoint(
                    properties[pelix.remote.PROP_ENDPOINT_ID],
                    properties[pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID],
                    [configuration],
                    None,
                    specs,
                    properties,
                )
            except KeyError as ex:
                # Log a warning on incomplete endpoints
                _logger.warning(
                    "Incomplete endpoint description, missing %s: %s",
                    ex,
                    properties,
                )
                return
            else:
                # Register the endpoint
                if self._registry.add(endpoint):
                    # Associate the mDNS name to the endpoint on success
                    self._imported_endpoints[name] = endpoint.uid

    def remove_service(self, zc: zeroconf.Zeroconf, type_: str, name: str) -> None:
        """
        Called by Zeroconf when a record is removed

        :param zc: The Zeroconf instance than notifies of the modification
        :param type_: Service type
        :param name: Service name
        """
        if type_ == self._rs_type:
            # Get information about the service
            try:
                # Get the stored endpoint UID
                uid = self._imported_endpoints.pop(name)
            except KeyError:
                # Unknown service
                return
            else:
                # Remove it
                self._registry.remove(uid)
        elif type_ == ZeroconfDiscovery.DNS_DISPATCHER_TYPE:
            # A dispatcher servlet is gone
            fw_uid = name.split(".", 1)[0]
            if fw_uid == self._fw_uid:
                # Local message: ignore
                return

            # Remote framework is lost
            self._registry.lost_framework(fw_uid)

    def update_service(self, zc: zeroconf.Zeroconf, type_: str, name: str) -> None:
        """
        Called by Zeroconf when a record is removed

        :param zc: The Zeroconf instance than notifies of the modification
        :param type_: Service type
        :param name: Service name
        """
        if type_ == ZeroconfDiscovery.DNS_DISPATCHER_TYPE:
            fw_uid = name.split(".", 1)[0]
            if fw_uid == self._fw_uid:
                # Local message: ignore
                return

            # Framework updates should not happen: consider a removal/addition
            self.remove_service(zc, type_, name)
            self.add_service(zc, type_, name)
        elif type_ == self._rs_type:
            # Remote service update
            try:
                # Get the stored endpoint UID
                uid = self._imported_endpoints.pop(name)
            except KeyError:
                # Unknown service: try to add it
                self.add_service(zc, type_, name)
            else:
                # Get information about the known service
                info = self._get_service_info(type_, name)
                if info is None:
                    _logger.warning("Timeout reading service information: %s - %s", type_, name)
                    return

                # Update local endpoint
                properties = self._deserialize_properties(info.properties)
                self._registry.update(uid, properties)
