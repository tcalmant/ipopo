#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Zeroconf (mDNS) discovery and event notification

This module depends on the zeroconf package

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
import json
import logging
import socket

# Zeroconf
import zeroconf

# iPOPO decorators
from pelix.ipopo.decorators import (
    ComponentFactory,
    Requires,
    Provides,
    Invalidate,
    Validate,
    Property,
)
import pelix.constants

# Remote services
import pelix.remote
import pelix.remote.beans as beans
from pelix.utilities import is_bytes, is_string, to_str

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


@ComponentFactory(pelix.remote.FACTORY_DISCOVERY_ZEROCONF)
@Provides(pelix.remote.SERVICE_EXPORT_ENDPOINT_LISTENER)
@Property("_rs_type", pelix.remote.PROP_ZEROCONF_TYPE, "_pelix-rs._tcp.local.")
@Property("_ttl", "zeroconf.ttl", 60)
@Requires("_access", pelix.remote.SERVICE_DISPATCHER_SERVLET)
@Requires("_registry", pelix.remote.SERVICE_REGISTRY)
class ZeroconfDiscovery(object):
    """
    Remote services discovery and notification using the module zeroconf
    """

    # Service type for the Pelix dispatcher servlet
    DNS_DISPATCHER_TYPE = "_rs-dispatcher._tcp.local."

    def __init__(self):
        """
        Sets up the component
        """
        # Imported endpoints registry
        self._registry = None

        # Dispatcher access
        self._access = None

        # Remote Service type
        self._rs_type = None

        # Zeroconf TTL
        self._ttl = 60

        # Framework UID
        self._fw_uid = None

        # Address of this framework
        self._address = None

        # Zeroconf
        self._zeroconf = None  # type: zeroconf.Zeroconf
        self._browsers = []

        # Endpoint UID -> ServiceInfo
        self._export_infos = {}

        # mDNS name -> Endpoint UID
        self._imported_endpoints = {}

    @Invalidate
    def invalidate(self, _):
        """
        Component invalidated
        """
        # Stop listeners
        for browser in self._browsers:
            browser.cancel()

        # Close Zeroconf
        self._zeroconf.unregister_all_services()
        self._zeroconf.close()

        # Clean up
        self._export_infos.clear()
        self._zeroconf = None
        self._fw_uid = None

        _logger.debug("Zeroconf discovery invalidated")

    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Get the host address
        self._address = socket.inet_aton(
            socket.gethostbyname(socket.gethostname())
        )

        # Prepare Zeroconf
        self._zeroconf = zeroconf.Zeroconf()

        # Register the dispatcher servlet as a service
        self.__register_servlet()

        # Listen to our types
        self._browsers.append(
            zeroconf.ServiceBrowser(
                self._zeroconf, ZeroconfDiscovery.DNS_DISPATCHER_TYPE, self
            )
        )
        self._browsers.append(
            zeroconf.ServiceBrowser(self._zeroconf, self._rs_type, self)
        )

        _logger.debug("Zeroconf discovery validated")

    @staticmethod
    def _serialize_properties(props):
        """
        Converts properties values into strings
        """
        new_props = {}

        for key, value in props.items():
            if is_string(value):
                new_props[key] = value
            else:
                try:
                    new_props[key] = json.dumps(value)
                except ValueError:
                    new_props[key] = "pelix-type:{0}:{1}".format(
                        type(value).__name__, repr(value)
                    )

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
    def _deserialize_properties(props):
        """
        Converts properties values into their type
        """
        new_props = {}
        for key, value in props.items():
            key = to_str(key)

            if is_bytes(value):
                # Convert value to string if necessary
                value = to_str(value)

            try:
                try:
                    new_props[key] = json.loads(value)
                except (TypeError, ValueError):
                    if is_string(value) and value.startswith("pelix-type:"):
                        # Pseudo-serialized
                        value_type, value = value.split(":", 3)[2:]
                        if "." in value_type and value_type not in value:
                            # Not a builtin type...
                            _logger.warning(
                                "Won't work: %s (%s)", value, value_type
                            )

                        new_props[key] = eval(value)
                    else:
                        # String
                        new_props[key] = value
            except Exception as ex:
                _logger.error("Can't deserialize %s: %s", value, ex)

        return new_props

    def __register_servlet(self):
        """
        Registers the Pelix Remote Services dispatcher servlet as a service via
        mDNS
        """
        # Get the dispatcher servlet access
        access = self._access.get_access()

        # Convert properties to be stored as strings
        properties = {
            "pelix.version": pelix.__version__,
            pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID: self._fw_uid,
            "pelix.access.port": access[0],
            "pelix.access.path": access[1],
        }
        properties = self._serialize_properties(properties)

        # Prepare the service type
        svc_name = "{0}.{1}".format(
            self._fw_uid, ZeroconfDiscovery.DNS_DISPATCHER_TYPE
        )

        # Prepare the mDNS entry
        info = zeroconf.ServiceInfo(
            ZeroconfDiscovery.DNS_DISPATCHER_TYPE,  # Type
            svc_name,  # Name
            self._address,  # Access address
            access[0],  # Access port
            properties=properties,
        )

        # Register the service
        self._zeroconf.register_service(info, self._ttl)

    def endpoints_added(self, endpoints):
        """
        Multiple endpoints have been added

        :param endpoints: A list of ExportEndpoint beans
        """
        # Get the dispatcher servlet port
        access_port = self._access.get_access()[0]

        # Handle each one separately
        for endpoint in endpoints:
            self._endpoint_added(endpoint, access_port)

    def _endpoint_added(self, exp_endpoint, access_port):
        """
        A new service is exported

        :param exp_endpoint: An ExportEndpoint bean
        :param access_port: The dispatcher access port
        """
        # Convert the export endpoint into an EndpointDescription bean
        endpoint = beans.EndpointDescription.from_export(exp_endpoint)

        # Get its properties
        properties = endpoint.get_properties()

        # Convert properties to be stored as strings
        properties = self._serialize_properties(properties)

        # Prepare the service name
        svc_name = "{0}.{1}".format(
            endpoint.get_id().replace("-", ""), self._rs_type
        )

        # Prepare the mDNS entry
        info = zeroconf.ServiceInfo(
            self._rs_type,  # Type
            svc_name,  # Name
            self._address,  # Access address
            access_port,  # Access port
            properties=properties,
        )

        self._export_infos[exp_endpoint.uid] = info

        # Register the service
        self._zeroconf.register_service(info, self._ttl)

    @staticmethod
    def endpoint_updated(endpoint, old_properties):
        # pylint: disable=W0613
        """
        An end point is updated

        :param endpoint: The updated endpoint
        :param old_properties: Previous properties of the endpoint
        """
        # Not available...
        # TODO: register a temporary service while the update is performed ?
        return

    def endpoint_removed(self, endpoint):
        """
        An end point is removed

        :param endpoint: Endpoint being removed
        """
        try:
            # Get the associated service info
            info = self._export_infos.pop(endpoint.uid)
        except KeyError:
            # Unknown service
            _logger.debug("Unknown removed endpoint: %s", endpoint)
        else:
            # Unregister the service
            self._zeroconf.unregister_service(info)

    def _get_service_info(self, svc_type, name, max_retries=10):
        # type: (str, str, int) -> zeroconf.ServiceInfo
        """
        Tries to get information about the given mDNS service

        :param svc_type: Service type
        :param name: Service name
        :param max_retries: Number of retries before timeout
        :return: A ServiceInfo bean
        """
        info = None
        retries = 0
        while (
            self._zeroconf is not None
            and info is None
            and retries < max_retries
        ):
            # Try to get information about the service...
            info = self._zeroconf.get_service_info(svc_type, name)
            retries += 1

        return info

    def add_service(self, zeroconf_, svc_type, name):
        """
        Called by Zeroconf when a record is updated

        :param zeroconf_: The Zeroconf instance than notifies of the
                          modification
        :param svc_type: Service type
        :param name: Service name
        """
        # Get information about the service
        info = self._get_service_info(svc_type, name)
        if info is None:
            _logger.warning(
                "Timeout reading service information: %s - %s", svc_type, name
            )
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

        if svc_type == ZeroconfDiscovery.DNS_DISPATCHER_TYPE:
            # Dispatcher servlet found, get source info
            address = to_str(socket.inet_ntoa(info.address))
            port = info.port
            self._access.send_discovered(
                address, port, properties["pelix.access.path"]
            )
        elif svc_type == self._rs_type:
            # Remote service
            # Get the first available configuration
            configuration = properties[pelix.remote.PROP_IMPORTED_CONFIGS]
            if not is_string(configuration):
                configuration = configuration[0]

            # Ensure we have a list of specifications
            specs = properties[pelix.constants.OBJECTCLASS]
            if is_string(specs):
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

    def remove_service(self, zeroconf_, svc_type, name):
        """
        Called by Zeroconf when a record is removed

        :param zeroconf_: The Zeroconf instance than notifies of the
                          modification
        :param svc_type: Service type
        :param name: Service name
        """
        if svc_type == self._rs_type:
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
        elif svc_type == ZeroconfDiscovery.DNS_DISPATCHER_TYPE:
            # A dispatcher servlet is gone
            fw_uid = name.split(".", 1)[0]
            if fw_uid == self._fw_uid:
                # Local message: ignore
                return

            # Remote framework is lost
            self._registry.lost_framework(fw_uid)
