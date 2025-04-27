#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Distribution Provider API

:author: Scott Lewis
:copyright: Copyright 2020, Scott Lewis
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2020 Scott Lewis

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

import abc
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union, cast

import pelix.rsa as rsa
import pelix.rsa.remoteserviceadmin as rsa_impl
from pelix.constants import OBJECTCLASS, SERVICE_SCOPE, Specification
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference, ServiceRegistration
from pelix.ipopo.constants import ARG_BUNDLE_CONTEXT, ARG_PROPERTIES, IPOPO_INSTANCE_NAME, IPopoService
from pelix.ipopo.decorators import Invalidate, Requires, ValidateComponent
from pelix.rsa import (
    ECF_SERVICE_EXPORTED_ASYNC_INTERFACES,
    ENDPOINT_FRAMEWORK_UUID,
    ENDPOINT_ID,
    SERVICE_BUNDLE_ID,
    SERVICE_EXPORTED_CONFIGS,
    SERVICE_EXPORTED_INTENTS,
    SERVICE_EXPORTED_INTENTS_EXTRA,
    SERVICE_ID,
    SERVICE_IMPORTED,
    SERVICE_IMPORTED_CONFIGS,
    SERVICE_INTENTS,
    ImportRegistration,
    RemoteServiceAdmin,
    RemoteServiceError,
    copy_non_reserved,
    create_uuid,
    get_dot_properties,
    get_string_plus_property_value,
    merge_dicts,
)
from pelix.rsa.endpointdescription import EndpointDescription

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Standard service property that is added to the set of properties provided
# to the call to ipopo.instantiate(container_factory,container_id,properties
# The property value is guaranteed to refer to the self instance of the
# distribution provider that is creating/instantiating the container
DISTRIBUTION_PROVIDER_CONTAINER_PROP = "pelix.rsa.distributionprovider"

# ------------------------------------------------------------------------------
# Abstract DistributionProvider superclass


@Requires("_rsa", RemoteServiceAdmin)
@Requires("_ipopo", IPopoService)
class DistributionProvider(abc.ABC):
    """
    Abstract super class for all distribution providers.
    Does not expose and 'public' methods (all methods _)
    that are intended to allow subclasses (e.g. ImportDistributionProvider
    and ExportDistributionProvider to get behavior necessary
    to implement supports_import and supports_export in a manner
    consistent with OSGi RSA requirements.

    Note that subclasses should set the following fields to non-None
    values via Property annotations or in __init__:

    self._config_name  (string)
    self._namespace  (string)
    self._supported_configs  (list(string))
    self._supported_intents  (list(string))

    These two members will be set via Requires class annotations:

    self._rsa  (SERVICE_REMOTE_SERVICE_ADMIN instance)
    self._ipopo (SERVICE_IPOPO instance)
    """

    _rsa: RemoteServiceAdmin
    _ipopo: IPopoService

    def __init__(self) -> None:
        self._config_name: str = ""
        self._namespace: str = ""
        self._allow_reuse: bool = True
        self._auto_create: bool = True
        self._supported_configs: List[str] = []
        self._supported_intents: Optional[List[str]] = None

    def get_config_name(self) -> str:
        return self._config_name

    def get_supported_configs(self) -> List[str]:
        return self._supported_configs

    def get_supported_intents(self) -> Optional[List[str]]:
        return self._supported_intents

    def _get_imported_configs(self, exported_configs: List[str]) -> List[str]:
        """
        Get any imported configs (list) given a set of exported_configs.
        Default implementation simply returns [self._config_name]
        """
        return [self._config_name]

    @staticmethod
    def _match_intents_supported(
        intents: Optional[List[str]], supported_intents: Optional[List[str]]
    ) -> bool:
        """
        Match the list of given intents with given supported_intents.
        This method is used by the other _match methods.
        """
        if intents is None or not supported_intents:
            return False

        return len([x for x in intents if x in supported_intents]) == len(intents)

    def _match_required_configs(self, required_configs: Optional[List[str]]) -> bool:
        """
        Match required configs list(string).
        Default implementation compares required configs with
        self._supported_configs to make sure that all required configs are
        present for this distribution provider.
        """
        if not required_configs:
            return True
        if not self._supported_configs:
            return False
        return len([x for x in required_configs if x in self._supported_configs]) == len(required_configs)

    def _match_intents(self, intents: Optional[List[str]]) -> bool:
        """
        Match list(string) of intents against self._supported_intents.
        Default implementation compares intents against self._supported_intents
        """
        return self._match_intents_supported(intents, self._supported_intents)

    def _find_container(self, container_id: str, container_props: Dict[str, Any]) -> Any:
        """
        Uses given container_id to get an ipopo instance with name=container_id.
        If instance is returned from ipopo.get_instance(container_id), then
        instance._match_container_props(container_props) is true, then
        the instance is returned, else None
        """
        try:
            instance = self._ipopo.get_instance(container_id)
            if instance and instance._match_container_props(container_props):
                return instance
        except KeyError:
            pass

        return None

    @abc.abstractmethod
    def _prepare_container_id(self, container_props: Dict[str, Any]) -> Optional[str]:
        """
        Prepare and return a (string) container id.  This method is called by
        self._get_or_create_container to create an id prior to instantiating
        and instance of the appropriate Container with the instance.name set
        to the container_id returned from this method.
        This method must be overridden by subclasses as the default
        implementation raises an Exception.
        If it returns None, then no container will be created.
        """
        ...

    def _prepare_container_props(
        self, service_intents: Optional[List[str]], export_props: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Prepare container props (dict).
        Creates dict of props subsequently passed to
        ipopo.instantiate(factory,container_name,container_props).
        default implementation copies . properties (as per OSGi spec)
        along with service.intents and <intent>. properties.
        Also sets DISTRIBUTION_PROVIDER_CONTAINER_PROP to self.  This
        is required by Container._get_distribution_provider()
        """
        container_props: Dict[str, Any] = {DISTRIBUTION_PROVIDER_CONTAINER_PROP: self}
        # first get . properties for this config
        container_props.update(get_dot_properties(self._config_name, export_props, True))
        # then add any service intents
        if service_intents is not None:
            container_props[SERVICE_INTENTS] = service_intents
            for intent in service_intents:
                container_props = merge_dicts(
                    container_props,
                    get_dot_properties(intent, export_props, False),
                )
        return container_props

    def _get_or_create_container(
        self,
        required_configs: Optional[List[str]],
        service_intents: Optional[List[str]],
        all_props: Dict[str, Any],
    ) -> Optional["Container"]:
        if self._match_required_configs(required_configs) and self._match_intents(service_intents):
            container_props = self._prepare_container_props(service_intents, all_props)
            if container_props:
                container_id = self._prepare_container_id(container_props)
                if not container_id:
                    # Container not created
                    raise Exception(f"No container ID found for properties {container_props}")
                container = self._find_container(container_id, container_props)
                if container is None:
                    container = self._ipopo.instantiate(self._config_name, container_id, container_props)

                if not isinstance(container, Container) or not container.is_valid():
                    raise Exception("New RSA container is invalid")

                return container

        return None

    def _find_import_registration(self, ed: EndpointDescription) -> Optional[ImportRegistration]:
        """
        Looks for the Import Registration matching the given endpoint
        description

        :param ed: An endpoint description
        :return: The matching ImportRegistration or None
        """
        if not ed:
            return None

        import_regs = cast(rsa_impl.RemoteServiceAdminImpl, self._rsa)._get_import_regs()
        if import_regs:
            for import_reg in import_regs:
                if import_reg.match_ed(ed):
                    return import_reg

        return None

    def _handle_import(self, ed: EndpointDescription) -> ImportRegistration:
        """
        Handle the import of an endpoint

        :param ed: An endpoint description
        :return: An import registration
        """
        return self._rsa.import_service(ed)

    def _handle_import_update(self, ed: EndpointDescription) -> None:
        """
        Handle the update of an endpoint

        :param ed: An endpoint description
        """
        import_reg = self._find_import_registration(ed)
        if import_reg:
            import_ref = import_reg.get_import_reference()
            if import_ref:
                import_ref.update(ed)

    def _handle_import_close(self, ed: EndpointDescription) -> None:
        """
        Cleans up import registration

        :param ed: An endpoint description
        """
        import_reg = self._find_import_registration(ed)
        if import_reg:
            import_reg.close()


# ------------------------------------------------------------------------------
# Specification for SERVICE_EXPORT_DISTRIBUTION_PROVIDER
SERVICE_EXPORT_DISTRIBUTION_PROVIDER = "pelix.rsa.exportdistributionprovider"
# Abstract implementation of SERVICE_EXPORT_DISTRIBUTION_PROVIDER extends
# DistributionProvider superclass


@Specification(SERVICE_EXPORT_DISTRIBUTION_PROVIDER)
class ExportDistributionProvider(DistributionProvider):
    """
    Export distribution provider.

    Implements supports_export, which is called by RSA during export_service
    to give self the ability to provide a container for exporting
    the remote service described by exported_configs, service_intents, and
    export_props.

    Note:  Subclasses MUST implement/override _prepare_container_id method
    and return a string to identify the created container instance.
    """

    def supports_export(
        self,
        exported_configs: Optional[List[str]],
        service_intents: Optional[List[str]],
        export_props: Dict[str, Any],
    ) -> Optional["ExportContainer"]:
        """
        Method called by rsa.export_service to ask if this
        ExportDistributionProvider supports export for given
        exported_configs (list), service_intents (list), and
        export_props (dict).

        If a ExportContainer instance is returned then it is used to export
        the service.  If None is returned, then this distribution provider will
        not be used to export the service.

        The default implementation returns self._get_or_create_container.
        """
        return cast(
            ExportContainer, self._get_or_create_container(exported_configs, service_intents, export_props)
        )


# ------------------------------------------------------------------------------
# Specification for SERVICE_IMPORT_DISTRIBUTION_PROVIDER
SERVICE_IMPORT_DISTRIBUTION_PROVIDER = "pelix.rsa.importdistributionprovider"


@Specification(SERVICE_IMPORT_DISTRIBUTION_PROVIDER)
class ImportDistributionProvider(DistributionProvider):
    """
    Abstract implementation of SERVICE_EXPORT_DISTRIBUTION_PROVIDER
    extends DistributionProvider superclass
    """

    def _prepare_container_id(self, container_props: Dict[str, Any]) -> str:
        """
        Default for import containers creates a UUID for the created container.
        """
        return create_uuid()

    def supports_import(
        self,
        exported_configs: Optional[List[str]],
        service_intents: Optional[List[str]],
        endpoint_props: Dict[str, Any],
    ) -> Optional["ImportContainer"]:
        """
        Method called by rsa.export_service to ask if this
        ImportDistributionProvider supports import for given
        exported_configs (list), service_intents (list), and
        endpoint_props (dict).

        If a ImportContainer instance is returned then it is used to import
        the service.  If None is returned, then this distribution provider will
        not be used to import the service.

        The default implementation returns self._get_or_create_container.
        """
        return cast(
            ImportContainer, self._get_or_create_container(exported_configs, service_intents, endpoint_props)
        )


# ------------------------------------------------------------------------------


class Container(abc.ABC):
    """
    Abstract Container type supporting both ImportContainer and ExportContainer
    """

    def __init__(self) -> None:
        self._bundle_context: Optional[BundleContext] = None
        self._container_props: Dict[str, Any] = {}
        self._exported_services: Dict[str, Tuple[Any, EndpointDescription]] = {}
        self._exported_instances_lock = RLock()

    def get_id(self) -> str:
        """
        Returns the ID of this container (its component name)

        :return: The ID of this containers
        """
        name = cast(Optional[str], self._container_props.get(IPOPO_INSTANCE_NAME, None))
        if not name:
            raise ValueError(f"Invalid empty ID for container {self}")
        return name

    def is_valid(self) -> bool:
        """
        Checks if the component is valid

        :return: Always True if it doesn't raise an exception
        :raises AssertionError: Invalid properties
        """
        if not (
            self._bundle_context
            or self._container_props is not None
            or self._get_distribution_provider()
            or self.get_config_name()
            or self.get_namespace()
        ):
            raise Exception("Invalid container")
        return True

    @ValidateComponent(ARG_BUNDLE_CONTEXT, ARG_PROPERTIES)
    def _validate_component(self, bundle_context: BundleContext, container_props: Dict[str, Any]) -> None:
        """
        Component validated

        :param bundle_context: Bundle context
        :param container_props: Instance properties
        :raises AssertionError: Invalid properties
        """
        self._bundle_context = bundle_context
        self._container_props = container_props
        self.is_valid()

    @Invalidate
    def _invalidate_component(self, _: BundleContext) -> None:
        """
        Component invalidated

        :param bundle_context: The bundle context
        """
        with self._exported_instances_lock:
            self._exported_services.clear()

    def _get_bundle_context(self) -> BundleContext:
        """
        Returns the bundle context of this container

        :return: A bundle context
        """
        if self._bundle_context is None:
            raise Exception("Bundle context should be set")
        return self._bundle_context

    def _add_export(self, ed_id: str, inst: Tuple[Any, EndpointDescription]) -> None:
        """
        Keeps track of an exported service

        :param ed_id: ID of the endpoint description
        :param inst: A tuple: (service instance, endpoint description)
        """
        with self._exported_instances_lock:
            self._exported_services[ed_id] = inst

    def _remove_export(self, ed_id: str) -> Optional[Tuple[Any, EndpointDescription]]:
        """
        Cleans up an exported service

        :param ed_id: ID of the endpoint description
        :return: The stored tuple (service instance, endpoint description) or None
        """
        with self._exported_instances_lock:
            return self._exported_services.pop(ed_id, None)

    def _get_export(self, ed_id: str) -> Optional[Tuple[Any, EndpointDescription]]:
        """
        Get the details of an exported service

        :param ed_id: ID of an endpoint description
        :return: The stored tuple (service instance, endpoint description) or None
        """
        with self._exported_instances_lock:
            return self._exported_services.get(ed_id, None)

    def _find_export(
        self, func: Callable[[Tuple[Any, EndpointDescription]], bool]
    ) -> Optional[Tuple[Any, EndpointDescription]]:
        """
        Look for an export using the given lookup method

        The lookup method must accept a single parameter, which is a tuple
        containing a service instance and endpoint description.

        :param func: A function to look for the excepted export
        :return: The found tuple or None
        """
        with self._exported_instances_lock:
            for val in self._exported_services.values():
                if func(val):
                    return val

            return None

    def _get_distribution_provider(self) -> DistributionProvider:
        """
        Returns the distribution provider associated to this container

        :return: A distribution provider
        """
        return cast(DistributionProvider, self._container_props[DISTRIBUTION_PROVIDER_CONTAINER_PROP])

    def get_config_name(self) -> str:
        """
        Returns the configuration name handled by this container

        :return: A configuration name
        """
        return self._get_distribution_provider()._config_name

    def get_namespace(self) -> str:
        """
        Returns the namespace of this container

        :return: A namespace ID
        """
        return self._get_distribution_provider()._namespace

    def _match_container_props(self, container_props: Dict[str, Any]) -> bool:
        return True

    def get_connected_id(self) -> Optional[str]:
        return None


# ------------------------------------------------------------------------------#
# Service specification for SERVICE_EXPORT_CONTAINER
SERVICE_EXPORT_CONTAINER = "pelix.rsa.exportcontainer"


@Specification(SERVICE_EXPORT_CONTAINER)
class ExportContainer(Container):
    """
    Abstract implementation of SERVICE_EXPORT_CONTAINER service specification
    extends Container class. New export distribution containers should use this
    class as a superclass to inherit required behavior.
    """

    def _get_supported_intents(self) -> Optional[List[str]]:
        return self._get_distribution_provider().get_supported_intents()

    def _export_service(self, svc: Any, ed: EndpointDescription) -> None:
        """
        Registers a service export

        :param svc: Service instance
        :param ed: Endpoint description
        """
        self._add_export(ed.get_id(), (svc, ed))

    def _update_service(self, ed: EndpointDescription) -> Any:
        # do nothing by default, subclasses may override
        pass

    def _unexport_service(self, ed: EndpointDescription) -> Optional[Tuple[Any, EndpointDescription]]:
        """
        Clears a service export

        :param ed: The endpoint description
        :return: The service instance and endpoint description or None
        """
        return self._remove_export(ed.get_id())

    def prepare_endpoint_props(
        self, intfs: List[str], svc_ref: ServiceReference[Any], export_props: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Sets up the properties of an endpoint

        :param intfs: Specifications to export
        :param svc_ref: Reference of the exported service
        :param export_props: Export properties
        :return: The properties of the endpoint
        """
        pkg_vers = rsa.get_package_versions(intfs, export_props)
        exported_configs = get_string_plus_property_value(svc_ref.get_property(SERVICE_EXPORTED_CONFIGS))
        if not exported_configs:
            exported_configs = [self.get_config_name()]
        service_intents = set()
        svc_intents = export_props.get(SERVICE_INTENTS, None)
        if svc_intents:
            service_intents.update(svc_intents)
        svc_exp_intents = export_props.get(SERVICE_EXPORTED_INTENTS, None)
        if svc_exp_intents:
            service_intents.update(svc_exp_intents)
        svc_exp_intents_extra = export_props.get(SERVICE_EXPORTED_INTENTS_EXTRA, None)
        if svc_exp_intents_extra:
            service_intents.update(svc_exp_intents_extra)

        rsa_props = rsa.get_rsa_props(
            intfs,
            exported_configs,
            self._get_supported_intents(),
            svc_ref.get_property(SERVICE_ID),
            export_props.get(ENDPOINT_FRAMEWORK_UUID),
            pkg_vers,
            list(service_intents),
        )
        ecf_props = rsa.get_ecf_props(
            self.get_id(),
            self.get_namespace(),
            rsa.get_next_rsid(),
            rsa.get_current_time_millis(),
        )
        extra_props = rsa.get_extra_props(export_props)
        merged = rsa.merge_dicts(rsa_props, ecf_props, extra_props)
        # remove service.bundleid
        merged.pop(SERVICE_BUNDLE_ID, None)
        # remove service.scope
        merged.pop(SERVICE_SCOPE, None)
        return merged

    def export_service(
        self, svc_ref: ServiceReference[Any], export_props: Dict[str, Any]
    ) -> EndpointDescription:
        """
        Exports the given service

        :param svc_ref: Reference to the service to export
        :param export_props: Export properties
        :return: The endpoint description
        """
        ed = EndpointDescription.fromprops(export_props)
        self._export_service(self._get_bundle_context().get_service(svc_ref), ed)
        return ed

    def update_service(self, ed: EndpointDescription) -> Any:
        """
        Updates a service with a new endpoint description

        :param ed: The new state of the endpoint description
        :return:
        """
        return self._update_service(ed)

    def unexport_service(self, ed: EndpointDescription) -> Optional[Tuple[Any, EndpointDescription]]:
        """
        Clears a service export

        :param ed: The endpoint description
        :return: The service instance and endpoint description or None
        """
        return self._unexport_service(ed)

    def _dispatch_exported(
        self, rs_id: int, method_name: str, params: Union[Iterable[Any], Dict[str, Any]]
    ) -> Any:
        # first lookup service instance by comparing the rs_id against the
        # service's remote service id
        service = self._find_export(lambda val: val[1].get_remoteservice_id()[1] == int(rs_id))
        if not service:
            raise RemoteServiceError(
                "Unknown service with rs_id={0} for method call={1}".format(rs_id, method_name)
            )
        # Get the method
        method_ref = getattr(service[0], method_name, None)
        if method_ref is None:
            raise RemoteServiceError(f"Unknown method {method_name}")
        # Call it (let the errors be propagated)
        if isinstance(params, (list, tuple)):
            return method_ref(*params)

        return method_ref(**params)

    def get_connected_id(self) -> Optional[str]:
        """
        Returns the ID of this container

        :return: The ID of the container
        """
        return self.get_id()


# ------------------------------------------------------------------------------#
# Service specification for SERVICE_IMPORT_CONTAINER
SERVICE_IMPORT_CONTAINER = "pelix.rsa.importcontainer"


@Specification(SERVICE_IMPORT_CONTAINER)
class ImportContainer(Container, abc.ABC):
    """
    Abstract implementation of SERVICE_IMPORT_CONTAINER service specification
    extends Container class.  New import container classes should
    subclass this ImportContainer class to inherit necessary functionality.
    """

    def _get_imported_configs(self, exported_configs: List[str]) -> List[str]:
        return self._get_distribution_provider()._get_imported_configs(exported_configs)

    def _prepare_proxy_props(self, endpoint_description: EndpointDescription) -> Dict[str, Any]:
        """
        Utility method to construct the properties of the proxy of the given endpoint description
        """
        result_props = copy_non_reserved(endpoint_description.get_properties(), dict())
        # remove these props
        result_props.pop(OBJECTCLASS, None)
        result_props.pop(SERVICE_ID, None)
        result_props.pop(SERVICE_BUNDLE_ID, None)
        result_props.pop(SERVICE_SCOPE, None)
        result_props.pop(IPOPO_INSTANCE_NAME, None)
        intents = endpoint_description.get_intents()
        if intents:
            result_props[SERVICE_INTENTS] = intents
        result_props[SERVICE_IMPORTED] = True
        result_props[SERVICE_IMPORTED_CONFIGS] = endpoint_description.get_imported_configs()
        result_props[ENDPOINT_ID] = endpoint_description.get_id()
        result_props[ENDPOINT_FRAMEWORK_UUID] = endpoint_description.get_framework_uuid()
        async_ = endpoint_description.get_async_interfaces()
        if async_:
            result_props[ECF_SERVICE_EXPORTED_ASYNC_INTERFACES] = async_
        return result_props

    @abc.abstractmethod
    def _prepare_proxy(self, endpoint_description: EndpointDescription) -> Any:
        """
        Sets up a proxy for the given endpoint description
        """
        ...

    def import_service(self, endpoint_description: EndpointDescription) -> Optional[ServiceRegistration[Any]]:
        """
        Import a service from an Endpoint. The Remote Service Admin must use the
        given Endpoint to create a proxy. This method can return None if
        the service could not be imported.
        """
        endpoint_description.update_imported_configs(
            self._get_imported_configs(endpoint_description.get_remote_configs_supported())
        )
        proxy = self._prepare_proxy(endpoint_description)
        if proxy:
            return self._get_bundle_context().register_service(
                endpoint_description.get_interfaces(),
                proxy,
                self._prepare_proxy_props(endpoint_description),
            )

        return None

    def unimport_service(self, endpoint_description: EndpointDescription) -> None:
        """
        Free the resources used by the given imported service
        """
        ...
