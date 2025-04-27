#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Common dispatcher

Calls services according to the given method name and parameters

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

import http.client as httplib
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin

import pelix.constants
import pelix.framework
import pelix.http
import pelix.remote
import pelix.remote.beans as beans
from pelix.internals.events import ServiceEvent
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    Requires,
    UnbindField,
    Validate,
)
from pelix.utilities import to_str

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


@ComponentFactory("pelix-remote-dispatcher-factory")
@Provides(pelix.remote.RemoteServiceDispatcher)
@Requires("_exporters", pelix.remote.RemoteServiceExportProvider, True, True)
@Requires(
    "_listeners",
    pelix.remote.RemoteServiceExportEndpointListener,
    aggregate=True,
    optional=True,
)
@Instantiate("pelix-remote-dispatcher")
class Dispatcher(pelix.remote.RemoteServiceDispatcher):
    """
    Common dispatcher for all exporters
    """

    # Remote Service providers
    _exporters: List[pelix.remote.RemoteServiceExportProvider]

    # Injected listeners
    _listeners: List[pelix.remote.RemoteServiceExportEndpointListener]

    def __init__(self) -> None:
        # Bundle context
        self._context: Optional[pelix.framework.BundleContext] = None

        # Framework UID
        self._fw_uid: Optional[str] = None

        # UID -> Endpoint
        self.__endpoints: Dict[str, beans.ExportEndpoint] = {}
        self.__endpoints_lock = threading.Lock()

        # UID -> Exporter
        self.__uid_exporter: Dict[str, pelix.remote.RemoteServiceExportProvider] = {}

        # Service Reference -> set(UID)
        self.__service_uids: Dict[ServiceReference[Any], Set[str]] = {}
        self.__exporters_lock = threading.Lock()

    @Validate
    def _validate(self, context: pelix.framework.BundleContext) -> None:
        """
        Component validated
        """
        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)
        self._context = context

        # Prepare the export LDAP filter
        ldap = f"(|({pelix.remote.PROP_EXPORTED_CONFIGS}=*)({pelix.remote.PROP_EXPORTED_INTERFACES}=*))"

        # Export existing services
        existing_ref: Optional[List[ServiceReference[Any]]] = context.get_all_service_references(None, ldap)
        if existing_ref is not None:
            for reference in existing_ref:
                self.__export_service(reference)

        # Register a service listener, to update the exported services state
        context.add_service_listener(self, ldap)

    @Invalidate
    def _invalidate(self, context: pelix.framework.BundleContext) -> None:
        """
        Component invalidated: clean up storage
        """
        # Unregister the service listener
        context.remove_service_listener(self)
        self._context = None
        self._fw_uid = None

    @staticmethod
    def _compute_endpoint_name(properties: Dict[str, Any]) -> str:
        """
        Computes the end point name according to service properties

        :param properties: Service properties
        :return: The computed end point name
        """
        name = properties.get(pelix.remote.PROP_ENDPOINT_NAME)
        if not name:
            name = f"service_{properties[pelix.constants.SERVICE_ID]}"

        return name

    def _check_name_reuse(self, name: str) -> None:
        """
        Checks if a service was waiting to reuse an endpoint name

        :param name: The endpoint name to reuse
        """
        assert self._context is not None

        ldap_filter = f"(&({pelix.remote.PROP_ENDPOINT_NAME}={name})(!({pelix.remote.PROP_IMPORTED}=*)))"
        svc_ref: Optional[ServiceReference[Any]] = self._context.get_service_reference(None, ldap_filter)
        if svc_ref is not None:
            # A service wants to be exported with the given endpoint name
            _logger.debug("Reuse endpoint name %s with %s", name, svc_ref)
            self.__export_service(svc_ref)

    def service_changed(self, event: ServiceEvent[Any]) -> None:
        """
        Called when a service event is triggered
        """
        kind = event.get_kind()
        svc_ref = event.get_service_reference()

        with self.__exporters_lock:
            if kind == ServiceEvent.REGISTERED:
                # Simply export the service
                self.__export_service(svc_ref)

            elif kind == ServiceEvent.MODIFIED:
                # Matching registering or updated service
                if svc_ref not in self.__service_uids:
                    # New match
                    self.__export_service(svc_ref)

                else:
                    # Properties modification:
                    # Re-export if endpoint.name has changed
                    self.__update_service(svc_ref, event.get_previous_properties())

            elif svc_ref in self.__service_uids and (
                kind == ServiceEvent.UNREGISTERING or kind == ServiceEvent.MODIFIED_ENDMATCH
            ):
                # Service is updated or unregistering
                self.__unexport_service(svc_ref)

    def __export_service(self, svc_ref: ServiceReference[Any]) -> None:
        """
        Exports the given service using all available matching providers

        :param svc_ref: A service reference
        """
        if not beans.compute_exported_specifications(svc_ref):
            # No exported specification matches the service
            # (case of iPOPO components services sharing export properties)
            return

        # Service can be exported
        service_uids = self.__service_uids.setdefault(svc_ref, set())

        if not self._exporters:
            _logger.warning("No exporters yet.")
            return

        # Select providers according to the supported configurations
        configs = svc_ref.get_property(pelix.remote.PROP_EXPORTED_CONFIGS)
        if not configs or configs == "*":
            # Export with all providers
            exporters = self._exporters[:]
        else:
            # Filter exporters
            exporters = [exporter for exporter in self._exporters[:] if exporter.handles(configs)]

        if not exporters:
            _logger.warning("No exporter for %s", configs)
            return

        # Prepare an endpoint name
        name = self._compute_endpoint_name(svc_ref.get_properties())

        # Create endpoints
        endpoints = []
        for exporter in exporters:
            try:
                # Create the endpoint
                endpoint = exporter.export_service(svc_ref, name, self._fw_uid)
                if endpoint is None:
                    # Export refused
                    continue

                endpoints.append(endpoint)

                # Store it
                uid = endpoint.uid
                self.__endpoints[uid] = endpoint
                self.__uid_exporter[uid] = exporter
                service_uids.add(uid)
            except (NameError, pelix.constants.BundleException) as ex:
                _logger.error("Error exporting service: %s", ex)

        if not endpoints:
            _logger.warning("No endpoint created for %s", svc_ref)
            return

        # Call listeners (out of the lock)
        if self._listeners:
            for listener in self._listeners[:]:
                listener.endpoints_added(endpoints)

    def __update_service(
        self, svc_ref: ServiceReference[Any], old_properties: Optional[Dict[str, Any]]
    ) -> None:
        """
        Service updated, notify exporters
        """
        try:
            # Get the UIDs of its endpoints
            uids = self.__service_uids[svc_ref].copy()
        except KeyError:
            # No known UID
            return

        names: Set[str] = set()
        for uid in uids:
            try:
                # Get its exporter and bean
                exporter = self.__uid_exporter[uid]
                endpoint = self.__endpoints[uid]
            except KeyError:
                # No exporter
                _logger.warning("No exporter for endpoint %s", uid)

                # Remove the UID from the storage
                self.__service_uids[svc_ref].discard(uid)
            else:
                # TODO: check configuration change (can be an unexport)
                # Compute the previous name
                new_name = self._compute_endpoint_name(svc_ref.get_properties())

                try:
                    exporter.update_export(endpoint, new_name, old_properties)
                except NameError as ex:
                    _logger.error("Error updating service properties: %s", ex)

                    # Unexport the service from this exporter
                    del self.__uid_exporter[endpoint.uid]
                    del self.__endpoints[endpoint.uid]
                    exporter.unexport_service(endpoint)
                    names.add(endpoint.name)

                    # Call listeners (out of the lock)
                    if self._listeners:
                        for listener in self._listeners:
                            listener.endpoint_removed(endpoint)
                else:
                    # Call listeners (out of the lock)
                    if self._listeners:
                        for listener in self._listeners:
                            listener.endpoint_updated(endpoint, old_properties)

        # Check if a service wanted to export an endpoint with the given name
        for name in names:
            self._check_name_reuse(name)

    def __unexport_service(self, svc_ref: ServiceReference[Any]) -> None:
        """
        Deletes all endpoints for the given service

        :param svc_ref: A service reference
        """
        try:
            # Get the UIDs of its endpoints
            uids = self.__service_uids.pop(svc_ref)
        except KeyError:
            # No known UID
            return

        names: Set[str] = set()
        for uid in uids:
            try:
                # Remove from storage
                endpoint = self.__endpoints.pop(uid)
                exporter = self.__uid_exporter.pop(uid)
            except KeyError:
                # Oops
                _logger.warning("Trying to remove a lost endpoint (%s)", uid)
            else:
                # Delete endpoint
                exporter.unexport_service(endpoint)
                names.add(endpoint.name)

                # Call listeners
                if self._listeners:
                    for listener in self._listeners[:]:
                        try:
                            listener.endpoint_removed(endpoint)
                        except Exception as ex:
                            _logger.error("Error notifying listener: %s", ex)

        # Check if a service wanted to export an endpoint with the given name
        for name in names:
            self._check_name_reuse(name)

    @BindField("_listeners")
    def _bind_listener(
        self,
        field: str,
        listener: pelix.remote.RemoteServiceExportEndpointListener,
        svc_ref: ServiceReference[pelix.remote.RemoteServiceExportEndpointListener],
    ) -> None:
        # pylint: disable=W0613
        """
        Listener bound to the component
        """
        # Exported services listener
        if self.__endpoints:
            try:
                listener.endpoints_added(list(self.__endpoints.values()))
            except Exception as ex:
                _logger.exception("Error notifying newly bound listener: %s", ex)

    @BindField("_exporters", if_valid=True)
    def _bind_exporter(
        self,
        field: str,
        exporter: pelix.remote.RemoteServiceExportProvider,
        exporter_ref: ServiceReference[pelix.remote.RemoteServiceExportProvider],
    ) -> None:
        # pylint: disable=W0613
        """
        Exporter bound
        """
        with self.__exporters_lock:
            # Tell the exporter to export already known services
            for svc_ref in self.__service_uids:
                # Compute the endpoint name
                name = self._compute_endpoint_name(svc_ref.get_properties())

                try:
                    # Create the endpoint
                    endpoint = exporter.export_service(svc_ref, name, self._fw_uid)
                    if endpoint is None:
                        _logger.error("No ExportEndpoint created for %s", name)
                        return

                    # Store it
                    uid = endpoint.uid
                    self.__endpoints[uid] = endpoint
                    self.__uid_exporter[uid] = exporter
                    self.__service_uids.setdefault(svc_ref, set()).add(uid)
                except (NameError, pelix.constants.BundleException) as ex:
                    _logger.error("Error exporting service: %s", ex)
                else:
                    # Call listeners (out of the lock)
                    if self._listeners:
                        for listener in self._listeners[:]:
                            listener.endpoints_added([endpoint])

    @UnbindField("_exporters")
    def _unbind_exporter(
        self,
        field: str,
        exporter: pelix.remote.RemoteServiceExportProvider,
        svc_ref: ServiceReference[pelix.remote.RemoteServiceExportProvider],
    ) -> None:
        # pylint: disable=W0613
        """
        Exporter gone
        """
        removed_endpoints = []

        with self.__exporters_lock:
            # Get the UIDs of all endpoints managed by this exporter
            uids = [uid for uid, uid_exporter in self.__uid_exporter.items() if uid_exporter is exporter]

            # Delete each endpoint
            for uid in uids:
                # Remove references
                del self.__uid_exporter[uid]
                endpoint = self.__endpoints.pop(uid)
                self.__service_uids.get(endpoint.reference, set()).remove(uid)

                # Store the endpoint for listeners
                removed_endpoints.append(endpoint)

                # Unexport the service
                try:
                    exporter.unexport_service(endpoint)
                except Exception as ex:
                    _logger.exception("Error unexporting service: %s", ex)

        # Notify listeners (out of the lock)
        if self._listeners:
            for listener in self._listeners[:]:
                for endpoint in removed_endpoints:
                    try:
                        listener.endpoint_removed(endpoint)
                    except Exception as ex:
                        _logger.error("Error notifying listener: %s", ex)

    def get_endpoint(self, uid: str) -> Optional[beans.ExportEndpoint]:
        """
        Retrieves an end point description, selected by its UID.
        Returns None if the UID is unknown.

        :param uid: UID of an end point
        :return: An :class:`~pelix.remote.beans.ExportEndpoint` or None.
        """
        return self.__endpoints.get(uid)

    def get_endpoints(
        self, kind: Optional[str] = None, name: Optional[str] = None
    ) -> List[beans.ExportEndpoint]:
        """
        Retrieves all end points matching the given kind and/or name

        :param kind: A kind of end point
        :param name: The name of the end point
        :return: A list of :class:`~pelix.remote.beans.ExportEndpoint` matching the parameters
        """
        with self.__endpoints_lock:
            # Get all endpoints
            endpoints = list(self.__endpoints.values())

        # Filter by name
        if name:
            endpoints = [endpoint for endpoint in endpoints if endpoint.name == name]

        # Filter by kind
        if kind:
            endpoints = [endpoint for endpoint in endpoints if kind in endpoint.configurations]

        return endpoints


# -----------------------------------------------------------------------------


@ComponentFactory(pelix.remote.FACTORY_REGISTRY_SERVLET)
@Provides(pelix.http.Servlet)
@Provides(pelix.remote.RemoteServiceDispatcherServlet, "_controller")
@Requires("_dispatcher", pelix.remote.RemoteServiceDispatcher)
@Requires("_registry", pelix.remote.RemoteServiceRegistry)
@Property("_path", pelix.http.HTTP_SERVLET_PATH, "/pelix-dispatcher")
class RegistryServlet(pelix.remote.RemoteServiceDispatcherServlet):
    """
    Servlet to access the content of the registry
    """

    # The dispatcher
    _dispatcher: pelix.remote.RemoteServiceDispatcher

    # The imported services registry
    _registry: pelix.remote.RemoteServiceRegistry

    def __init__(self) -> None:
        """
        Sets up members
        """
        # The framework UID
        self._fw_uid: Optional[str] = None

        # Controller for the provided service:
        # => activate only if bound to a server
        self._controller: bool = False

        # Servlet path property
        self._path: str = ""

        # Ports of exposing servers
        self._ports: List[int] = []

    @Validate
    def _validate(self, context: pelix.framework.BundleContext) -> None:
        """
        Component validated
        """
        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Normalize the path
        self._path = f"/{'/'.join(part for part in (self._path or '').split('/') if part)}/"

        _logger.debug("Dispatcher servlet for %s on %s", self._fw_uid, self._path)

    @Invalidate
    def _invalidate(self, _: pelix.framework.BundleContext) -> None:
        """
        Component invalidated
        """
        # Clean up
        self._fw_uid = None

    @staticmethod
    def __grab_data(host: str, port: int, path: str) -> Optional[Any]:
        """
        Sends a HTTP request to the server at (host, port), on the given path.
        Returns the parsed response.
        Returns None if the HTTP result is not 200 or in case of error.

        :param host: Dispatcher host address
        :param port: Dispatcher HTTP service port
        :param path: Request path
        :return: The parsed response content, or None
        """
        # Request the end points
        try:
            conn = httplib.HTTPConnection(host, port)
            conn.request("GET", path)
            result = conn.getresponse()
            data = result.read()
            conn.close()
        except Exception as ex:
            _logger.error("Error accessing the dispatcher servlet: %s", ex)
            return None

        if result.status != 200:
            # Not a valid result
            return None

        try:
            # Parse the JSON result
            return json.loads(data)
        except ValueError as ex:
            # Error parsing data
            _logger.error("Error reading the response of the dispatcher: %s", ex)
            return None

    def _make_endpoint_dict(self, endpoint: beans.ExportEndpoint) -> Dict[str, Any]:
        """
        Converts the end point into a dictionary

        :param endpoint: The end point to convert
        :return: A dictionary
        """
        # Send import-side properties
        return {
            "sender": self._fw_uid,
            "uid": endpoint.uid,
            "configurations": endpoint.configurations,
            "name": endpoint.name,
            "specifications": endpoint.specifications,
            "properties": endpoint.make_import_properties(),
        }

    @staticmethod
    def _make_endpoint_bean(
        endpoint_dict: Dict[str, Any], host: Optional[str] = None
    ) -> beans.ImportEndpoint:
        """
        Converts an endpoint dictionary into an ImportEndpoint bean

        :param endpoint_dict: Dictionary form of the endpoint
        :param host: The host of the endpoint (optional)
        :return: An ImportEndpoint bean
        """
        # Create the end point bean
        endpoint = beans.ImportEndpoint(
            endpoint_dict["uid"],
            endpoint_dict["sender"],
            endpoint_dict["configurations"],
            endpoint_dict["name"],
            endpoint_dict["specifications"],
            endpoint_dict["properties"],
        )

        # Set the host address
        endpoint.server = host
        return endpoint

    def bound_to(self, path: str, parameters: Dict[str, Any]) -> None:
        # pylint: disable=W0613
        """
        This servlet has been bound to a server

        :param path: The servlet path in the server
        :param parameters: The servlet/server parameters
        """
        port = parameters["http.port"]
        if port not in self._ports:
            # Get its access port
            self._ports.append(port)

            # Activate the service, we're bound to a server
            self._controller = True

    def unbound_from(self, path: str, parameters: Dict[str, Any]) -> None:
        # pylint: disable=W0613
        """
        This servlet has been unbound from a server

        :param path: The servlet path in the server
        :param parameters: The servlet/server parameters
        """
        port = parameters["http.port"]
        if port in self._ports:
            # Remove its access port
            self._ports.remove(port)

            # Deactivate the service if no more server available
            if not self._ports:
                self._controller = False

    def do_GET(
        self, request: pelix.http.AbstractHTTPServletRequest, response: pelix.http.AbstractHTTPServletResponse
    ) -> None:
        """
        Handles a GET request

        :param request: Request handler
        :param response: Response handler
        """
        # Normalize the path
        path_parts = [part for part in request.get_path().split("/") if part]

        # Remove the servlet part
        servlet_parts = [part for part in self._path.split("/") if part]
        path_parts = path_parts[len(servlet_parts) :]
        action = path_parts[0]

        data: Any
        if action == "framework":
            # /framework: return the framework UID, let it be converted as a
            # JSON string
            data = self._fw_uid
        elif action == "endpoints":
            # /endpoints: all end points
            endpoints = self._dispatcher.get_endpoints()
            if not endpoints:
                data = []
            else:
                data = [self._make_endpoint_dict(endpoint) for endpoint in endpoints]
        elif action == "endpoint":
            # /endpoint/<uid>: specific end point
            try:
                uid = path_parts[1]
                endpoint = self._dispatcher.get_endpoint(uid)
            except IndexError:
                # UID not given
                uid = "<unknown>"
                endpoint = None

            if endpoint is None:
                response.send_content(404, f"Unknown UID: {uid}", "text/plain")
                return
            else:
                data = self._make_endpoint_dict(endpoint)
        else:
            # Unknown
            response.send_content(
                404,
                f"Unhandled path {request.get_path()}",
                "text/plain",
            )
            return

        # Convert the result to JSON
        data = json.dumps(data)

        # Send the result
        response.send_content(200, data, "application/json")

    def do_POST(
        self, request: pelix.http.AbstractHTTPServletRequest, response: pelix.http.AbstractHTTPServletResponse
    ) -> None:
        """
        Handles a POST request

        :param request: Request handler
        :param response: Response handler
        """
        # Split the path
        path_parts = request.get_path().split("/")
        if path_parts[-1] != "endpoints":
            # Bad path
            response.send_content(404, "Unhandled path", "text/plain")
            return

        # Read the content
        endpoints = json.loads(to_str(request.read_data()))
        if endpoints:
            # Got something
            sender = request.get_client_address()[0]
            for endpoint in endpoints:
                self._registry.add(self._make_endpoint_bean(endpoint, sender))

        # We got the end points
        response.send_content(200, "OK", "text/plain")

    def get_access(self) -> Optional[Tuple[int, str]]:
        """
        Returns the port and path to access this servlet with the first
        bound HTTP service.
        Returns None if this servlet is still not bound to a server

        :return: A tuple: (port, path) or None
        """
        if self._ports:
            return self._ports[0], self._path

        return None

    def grab_endpoint(self, host: str, port: int, path: str, uid: str) -> Optional[beans.ImportEndpoint]:
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
        # Setup the request URI
        if path[-1] == "/":
            path = path[:-1]

        request_path = f"{path}/endpoint/{uid}"

        # Get the endpoint description
        endpoint_dict = self.__grab_data(host, port, request_path)
        if not endpoint_dict:
            # No description found
            return None

        # Create the end point bean
        return self._make_endpoint_bean(endpoint_dict, host)

    def send_discovered(self, host: str, port: int, path: str) -> bool:
        """
        Sends a "discovered" HTTP POST request to the dispatcher servlet of the
        framework that has been discovered

        :param host: The address of the sender
        :param port: Port of the HTTP server of the sender
        :param path: Path of the dispatcher servlet
        :return: True if the request has been handled by the peer
        """
        # Get the end points from the dispatcher
        endpoints = [self._make_endpoint_dict(endpoint) for endpoint in self._dispatcher.get_endpoints()]

        # Make the path to /endpoints
        if path[-1] != "/":
            path += "/"
        path = urljoin(path, "endpoints")

        # Request the end points
        try:
            conn = httplib.HTTPConnection(host, port)
            conn.request(
                "POST",
                path,
                json.dumps(endpoints),
                {"Content-Type": "application/json"},
            )
            result = conn.getresponse()
            data = result.read()
            conn.close()
        except Exception as ex:
            _logger.error(
                "Error sending endpoints to the framework at %s:%s: %s",
                host,
                port,
                ex,
            )
            return False
        else:
            if result.status != 200:
                # Not a valid result
                _logger.warning(
                    "Got an HTTP code %d when contacting a " "discovered framework: %s",
                    result.status,
                    data,
                )
            return result.status == 200
