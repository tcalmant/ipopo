#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Abstract RPC implementation

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

**TODO:**
* "system" methods (list, help, ...)
"""

# Standard library
import logging
import threading
import uuid

# iPOPO decorators
from pelix.ipopo.decorators import Validate, Invalidate, Property, Provides

# Pelix constants
import pelix.constants as constants
import pelix.remote.beans
from pelix.remote import RemoteServiceError

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


@Provides(pelix.remote.SERVICE_EXPORT_PROVIDER)
@Property("_kinds", pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED)
class AbstractRpcServiceExporter(object):
    """
    Abstract Remote Services exporter
    """

    def __init__(self):
        """
        Sets up the exporter
        """
        # Bundle context
        self._context = None

        # Framework UID
        self._framework_uid = None

        # Handled configurations
        self._kinds = []

        # Exported services: Name -> ExportEndpoint
        self.__endpoints = {}

        # Thread safety
        self.__lock = threading.Lock()

    def dispatch(self, method, params):
        """
        Called by the servlet: calls the method of an exported service
        """
        # Get the best matching name
        matching = None
        len_found = 0
        for name in self.__endpoints:
            if len(name) > len_found and method.startswith(name + "."):
                # Better matching end point name (longer that previous one)
                matching = name
                len_found = len(matching)

        if matching is None:
            # No end point name match
            raise RemoteServiceError(
                "No end point found for: {0}".format(method)
            )

        # Extract the method name. (+1 for the trailing dot)
        method_name = method[len_found + 1 :]

        # Get the service
        try:
            service = self.__endpoints[matching].instance
        except KeyError:
            raise RemoteServiceError("Unknown endpoint: {0}".format(matching))

        # Get the method
        method_ref = getattr(service, method_name, None)
        if method_ref is None:
            raise RemoteServiceError("Unknown method {0}".format(method))

        # Call it (let the errors be propagated)
        if isinstance(params, (list, tuple)):
            return method_ref(*params)

        return method_ref(**params)

    def handles(self, configurations):
        """
        Checks if this provider handles the given configuration types

        :param configurations: Configuration types
        """
        if configurations is None or configurations == "*":
            # 'Matches all'
            return True

        return bool(set(configurations).intersection(self._kinds))

    def export_service(self, svc_ref, name, fw_uid):
        """
        Prepares an export endpoint

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: An ExportEndpoint bean
        :raise NameError: Already known name
        :raise BundleException: Error getting the service
        """
        with self.__lock:
            # Prepare extra properties
            extra_props = self.make_endpoint_properties(svc_ref, name, fw_uid)

            try:
                # Check if the name has been changed by the exporter
                name = extra_props[pelix.remote.PROP_ENDPOINT_NAME]
            except KeyError:
                # Name not updated
                pass

            if name in self.__endpoints:
                # Already known end point
                raise NameError(
                    "Already known end point {0} for kinds {1}".format(
                        name, ",".join(self._kinds)
                    )
                )

            # Get the service (let it raise a BundleException if any
            service = self._context.get_service(svc_ref)

            # Prepare the export endpoint
            try:
                endpoint = pelix.remote.beans.ExportEndpoint(
                    str(uuid.uuid4()),
                    fw_uid,
                    self._kinds,
                    name,
                    svc_ref,
                    service,
                    extra_props,
                )
            except ValueError:
                # No specification to export (specifications filtered, ...)
                return None

            # Store information
            self.__endpoints[name] = endpoint

            # Return the endpoint bean
            return endpoint

    def update_export(self, endpoint, new_name, old_properties):
        # pylint: disable=W0613
        """
        Updates an export endpoint

        :param endpoint: An ExportEndpoint bean
        :param new_name: Future endpoint name
        :param old_properties: Previous properties
        :raise NameError: Rename refused
        """
        with self.__lock:
            try:
                if self.__endpoints[new_name] is not endpoint:
                    # Reject the new name, as an endpoint uses it
                    raise NameError(
                        "New name of {0} already used: {1}".format(
                            endpoint.name, new_name
                        )
                    )
                else:
                    # Name hasn't changed
                    pass
            except KeyError:
                # Update the name of the endpoint
                old_name = endpoint.name
                endpoint.rename(new_name)

                # No endpoint matches the new name: update the storage
                self.__endpoints[new_name] = self.__endpoints.pop(old_name)

    def unexport_service(self, endpoint):
        """
        Deletes an export endpoint

        :param endpoint: An ExportEndpoint bean
        """
        with self.__lock:
            # Clean up storage
            del self.__endpoints[endpoint.name]

            # Release the service
            svc_ref = endpoint.reference
            self._context.unget_service(svc_ref)

    def make_endpoint_properties(self, svc_ref, name, fw_uid):
        """
        Prepare properties for the ExportEndpoint to be created

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: A dictionary of extra endpoint properties
        """
        raise NotImplementedError(
            "make_endpoint_properties() not "
            "implemented by class {0}".format(type(self).__name__)
        )

    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Store the context
        self._context = context

        # Store the framework UID
        self._framework_uid = context.get_property(constants.FRAMEWORK_UID)

    @Invalidate
    def invalidate(self, _):
        """
        Component invalidated
        """
        # Clean up the storage
        self.__endpoints.clear()

        # Clean up members
        self._context = None
        self._framework_uid = None


# ------------------------------------------------------------------------------


@Provides(pelix.remote.SERVICE_IMPORT_ENDPOINT_LISTENER)
@Property("_kinds", pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED)
class AbstractRpcServiceImporter(object):
    """
    Abstract Remote Services importer
    """

    def __init__(self):
        """
        Sets up the exporter
        """
        # Bundle context
        self._context = None

        # Framework UID
        self._framework_uid = None

        # Component properties
        self._kinds = None

        # Registered services (endpoint UID -> ServiceReference)
        self.__registrations = {}
        self.__lock = threading.Lock()

    def endpoint_added(self, endpoint):
        """
        An end point has been imported
        """
        configs = set(endpoint.configurations)
        if "*" not in configs and not configs.intersection(self._kinds):
            # Not for us
            return

        with self.__lock:
            if endpoint.uid in self.__registrations:
                # Already known endpoint
                return

            # Prepare a proxy
            svc = self.make_service_proxy(endpoint)
            if svc is None:
                return

            # Register it as a service
            svc_reg = self._context.register_service(
                endpoint.specifications, svc, endpoint.properties
            )

            # Store references
            self.__registrations[endpoint.uid] = svc_reg

    def endpoint_updated(self, endpoint, old_properties):
        # pylint: disable=W0613
        """
        An end point has been updated
        """
        with self.__lock:
            try:
                # Update service registration properties
                self.__registrations[endpoint.uid].set_properties(
                    endpoint.properties
                )

            except KeyError:
                # Unknown end point
                return

    def endpoint_removed(self, endpoint):
        """
        An end point has been removed
        """
        with self.__lock:
            try:
                # Pop reference and unregister the service
                self.__registrations.pop(endpoint.uid).unregister()

            except KeyError:
                # Unknown end point
                return

            else:
                # Clear the proxy
                self.clear_service_proxy(endpoint)

    def make_service_proxy(self, endpoint):
        """
        Creates the proxy for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        :return: A service proxy
        """
        raise NotImplementedError(
            "make_service_proxy() not implemented by "
            "class {0}".format(type(self).__name__)
        )

    def clear_service_proxy(self, endpoint):
        """
        Destroys the proxy made for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        """
        raise NotImplementedError(
            "clear_service_proxy() not implemented by "
            "class {0}".format(type(self).__name__)
        )

    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Store the bundle context and the framework UID
        self._context = context
        self._framework_uid = context.get_property(constants.FRAMEWORK_UID)

    @Invalidate
    def invalidate(self, _):
        """
        Component invalidated
        """
        # Unregister all of our services
        for svc_reg in self.__registrations.values():
            svc_reg.unregister()

        # Clean up members
        self.__registrations.clear()
        self._context = None
        self._framework_uid = None
