#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Remote Service Admin API

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

import logging
import sys
import threading
from datetime import datetime
from traceback import print_exception
from typing import IO, Any, Dict, List, Optional, Protocol, Set, Tuple, Union, cast

from pelix import constants
from pelix.constants import (
    OBJECTCLASS,
    OSGI_FRAMEWORK_UUID,
    SERVICE_RANKING,
    ActivatorProto,
    BundleActivator,
    BundleException,
    Specification,
)
from pelix.framework import Bundle, BundleContext
from pelix.internals.registry import ServiceReference, ServiceRegistration
from pelix.ipopo.decorators import (
    ComponentFactory,
    Instantiate,
    Invalidate,
    Provides,
    Requires,
    RequiresBest,
    Validate,
)
from pelix.rsa import (
    ECF_ENDPOINT_TIMESTAMP,
    ENDPOINT_FRAMEWORK_UUID,
    REMOTE_CONFIGS_SUPPORTED,
    SERVICE_EXPORTED_CONFIGS,
    SERVICE_EXPORTED_INTENTS,
    SERVICE_EXPORTED_INTENTS_EXTRA,
    SERVICE_EXPORTED_INTERFACES,
    SERVICE_INTENTS,
    ExportReference,
    ExportRegistration,
    ImportReference,
    ImportRegistration,
    RemoteServiceAdmin,
    RemoteServiceAdminEvent,
    RemoteServiceAdminListener,
    RemoteServiceError,
    SelectImporterError,
    get_current_time_millis,
    get_edef_props_error,
    get_exported_interfaces,
    get_string_plus_property,
    set_append,
    validate_exported_interfaces,
)
from pelix.rsa.edef import EDEFWriter
from pelix.rsa.endpointdescription import EndpointDescription
from pelix.rsa.providers.distribution import (
    ExportContainer,
    ExportDistributionProvider,
    ImportContainer,
    ImportDistributionProvider,
)
from pelix.utilities import str2bool

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Standard logging
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

# Framework property that allows RSA debug to be disabled. To disable automatic
# output of RSA events, set the property 'pelix.rsa.remoteserviceadmin.debug
# to some string other than 'true' (the default)
DEBUG_PROPERTY = "pelix.rsa.remoteserviceadmin.debug"
DEBUG_PROPERTY_DEFAULT = "false"

# ------------------------------------------------------------------------------


@BundleActivator
class Activator(ActivatorProto):
    """
    Bundle activator. By default, register an instance of
    RemoteServiceAdminEventListener service for debugging.
    This can be disabled by setting the DEBUG_PROPERTY aka
    ``pelix.rsa.remoteserviceadmin.debug`` to ``false``.
    """

    def __init__(self) -> None:
        self._context: Optional[BundleContext] = None
        self._debug_reg: Optional[ServiceRegistration[RemoteServiceAdminListener]] = None

    def start(self, context: BundleContext) -> None:
        """
        Bundle starting
        """
        self._context = context
        debug_str = self._context.get_property(DEBUG_PROPERTY)
        if not debug_str:
            debug_str = DEBUG_PROPERTY_DEFAULT

        if str2bool(debug_str):
            self._debug_reg = self._context.register_service(
                RemoteServiceAdminListener,
                DebugRemoteServiceAdminListener(),
                None,
            )

    def stop(self, _: BundleContext) -> None:
        """
        Bundle stopping
        """
        if self._debug_reg is not None:
            self._debug_reg.unregister()
            self._debug_reg = None
        self._context = None


# ------------------------------------------------------------------------------


SERVICE_EXPORT_CONTAINER_SELECTOR = "pelix.rsa.exportcontainerselector"


@Specification(SERVICE_EXPORT_CONTAINER_SELECTOR)
class ExportContainerSelector(Protocol):
    """
    RSA Impl Export Container Selector service specification and default
    implementation.  The highest priority instance of this service available
    at runtime is used by the RemoteServiceAdmin implementation to select
    export containers to handle a given call to
    RemoteServiceAdmin.export_service
    """

    def select_export_containers(
        self, service_ref: ServiceReference[Any], exported_intfs: List[str], export_props: Dict[str, Any]
    ) -> List[ExportContainer]:
        """
        Select export containers, given service_ref (ServiceReference),
        exported_refs list(string), and export_props dict(string:?).  Each of
        these parameters must not be None.

        :param service_ref ServiceReference for possible export
        :param exported_intf list of strings defining the service specifications
        to be exported for the service
        :param export_prop the service properties to be used for export after
        combining the service_ref properties with any overriding properties.
        :return list of ExportContainer instances that will be responsible for
        exporting the given service.  Will not return None, but may return
        empty list
        """
        ...


@ComponentFactory("pelix-rsa-exporterselector-factory")
@Provides(ExportContainerSelector)
@Requires(
    "_export_distribution_providers",
    ExportDistributionProvider,
    True,
    True,
)
@Instantiate(SERVICE_EXPORT_CONTAINER_SELECTOR, {SERVICE_RANKING: -1000000000})
class ExportContainerSelectorImpl(ExportContainerSelector):
    _export_distribution_providers: List[ExportDistributionProvider]

    def select_export_containers(
        self, service_ref: ServiceReference[Any], exported_intfs: List[str], export_props: Dict[str, Any]
    ) -> List[ExportContainer]:
        # get exported configs
        exported_configs = get_string_plus_property(SERVICE_EXPORTED_CONFIGS, export_props, None)
        # get service intents, via service.intents, services.exported.intents,
        # and extra
        service_intents_set: Set[str] = set_append(set(), export_props.get(SERVICE_INTENTS, None))
        service_intents_set = set_append(
            service_intents_set,
            export_props.get(SERVICE_EXPORTED_INTENTS, None),
        )
        service_intents_set = set_append(
            service_intents_set,
            export_props.get(SERVICE_EXPORTED_INTENTS_EXTRA, None),
        )

        export_containers: List[ExportContainer] = []
        for export_provider in self._export_distribution_providers:
            export_container = export_provider.supports_export(
                exported_configs, list(service_intents_set), export_props
            )
            if export_container is not None:
                export_containers.append(export_container)

        return export_containers


# ------------------------------------------------------------------------------
# Import Container Selector service specification and default
# implementation.  The highest priority instance of this service available
# at runtime is used by the RemoteServiceAdmin implementation to select
# a single import container to handle a given call to RemoteServiceAdmin.import_service
SERVICE_IMPORT_CONTAINER_SELECTOR = "pelix.rsa.importcontainerselector"


@Specification(SERVICE_IMPORT_CONTAINER_SELECTOR)
class ImportContainerSelector(Protocol):
    def select_import_container(
        self, remote_configs: List[str], endpoint_description: EndpointDescription
    ) -> Optional[ImportContainer]:
        """
        Select import container, given endpoint_description
        (EndpointDescription).
        Returns a single ImportContainer, or None.

        :param endpoint_description: EndpointDescription describing endpoint for possible import
        :return ImportContainer instance or None
        """
        ...


# ------------------------------------------------------------------------------
@ComponentFactory("pelix-rsa-importerselector-factory")
@Provides(ImportContainerSelector)
@Requires(
    "_import_distribution_providers",
    ImportDistributionProvider,
    True,
    True,
)
@Instantiate("pelix-rsa-importerselector-impl", {SERVICE_RANKING: -1000000000})
class ImportContainerSelectorImpl(ImportContainerSelector):
    _import_distribution_providers: List[ImportDistributionProvider]

    def select_import_container(
        self, remote_configs: List[str], endpoint_description: EndpointDescription
    ) -> Optional[ImportContainer]:
        for import_provider in self._import_distribution_providers:
            import_container = import_provider.supports_import(
                remote_configs,
                endpoint_description.get_intents(),
                endpoint_description.get_properties(),
            )
            if import_container is not None:
                return import_container

        return None


# ------------------------------------------------------------------------------
# Implementation of RemoteServiceAdmin service
# ------------------------------------------------------------------------------
@ComponentFactory("pelix-rsa-remoteserviceadminimpl-factory")
@Provides(RemoteServiceAdmin)
@RequiresBest("_export_container_selector", ExportContainerSelector, False)
@RequiresBest("_import_container_selector", ImportContainerSelector, False)
@Requires("_rsa_event_listeners", RemoteServiceAdminListener, True, True)
@Instantiate("pelix-rsa-remoteserviceadminimpl")
class RemoteServiceAdminImpl(RemoteServiceAdmin):
    _export_container_selector: ExportContainerSelector
    _import_container_selector: ImportContainerSelector
    _rsa_event_listeners: List[RemoteServiceAdminListener]
    _context: BundleContext

    def __init__(self) -> None:
        self._exported_regs: List[ExportRegistrationImpl] = []
        self._exported_regs_lock = threading.RLock()
        self._imported_regs: List[ImportRegistrationImpl] = []
        self._imported_regs_lock = threading.RLock()

    def get_exported_services(self) -> List[ExportReference]:
        result: List[ExportReference] = []
        for reg in self._get_export_regs():
            exp_ref = reg.get_export_reference()
            if exp_ref:
                result.append(exp_ref)
        return result

    def get_imported_endpoints(self) -> List[ImportReference]:
        result: List[ImportReference] = []
        for reg in self._get_import_regs():
            imp_ref = reg.get_import_reference()
            if imp_ref:
                result.append(imp_ref)
        return result

    def _get_export_regs(self) -> List[ExportRegistration]:
        with self._exported_regs_lock:
            return list(self._exported_regs)

    def _get_import_regs(self) -> List[ImportRegistration]:
        with self._imported_regs_lock:
            return list(self._imported_regs)

    def export_service(
        self, service_ref: ServiceReference[Any], overriding_props: Optional[Dict[str, Any]] = None
    ) -> List[ExportRegistration]:
        bundle = self._get_bundle()

        if service_ref is None:
            raise RemoteServiceError("service_ref must not be None")

        # get exported interfaces
        exported_intfs = get_exported_interfaces(service_ref, overriding_props)
        # must be set by service_ref or overriding_props or error
        if not exported_intfs:
            raise RemoteServiceError(
                f"{SERVICE_EXPORTED_INTERFACES} must be set in svc_ref properties or overriding_props"
            )

        # If the given exported_interfaces is not valid, then return empty list
        if not validate_exported_interfaces(service_ref.get_property(OBJECTCLASS), exported_intfs):
            return []

        # get export props by overriding service get_reference properties
        # (if overriding_props set)
        export_props = service_ref.get_properties().copy()
        if overriding_props:
            export_props.update(overriding_props)

        # Force the framework UID, as the one from error_props
        # was generated
        export_props[ENDPOINT_FRAMEWORK_UUID] = self._context.get_property(OSGI_FRAMEWORK_UUID)

        result_regs: List[ExportRegistrationImpl] = []
        result_events: List[RemoteServiceAdminEvent] = []
        exporters: List[ExportContainer] = []

        # Default properties for erroneous cases
        error_props = get_edef_props_error(service_ref.get_property(OBJECTCLASS))

        try:
            # get list of exporters from export_container_selector service
            exporters = self._export_container_selector.select_export_containers(
                service_ref, exported_intfs, export_props
            )
            # if none returned then report as warning at return empty list
            if not exporters:
                _logger.warning(
                    "No exporting containers found to export " "service_ref=%s;export_props=%s",
                    service_ref,
                    export_props,
                )
                return []
        except:
            error_reg = ExportRegistrationImpl.fromexception(
                sys.exc_info(), EndpointDescription(service_ref, error_props)
            )
            export_event = RemoteServiceAdminEvent.fromexportreg(bundle, error_reg)
            result_regs.append(error_reg)
            self._add_exported_service(error_reg)
            result_events.append(export_event)

        # If no errors added to result_regs then we continue
        if not result_regs and exporters:
            # get _exported_regs_lock
            with self._exported_regs_lock:
                # cycle through all exporters
                for exporter in exporters:
                    found_regs = []
                    # get exporter id
                    exporter_id = exporter.get_id()
                    exporter_id_ns = exporter.get_namespace()
                    for reg in self._exported_regs:
                        if reg.match_sr(service_ref, (exporter_id_ns, exporter_id)):
                            found_regs.append(reg)
                    # if so then found_regs will be non-empty
                    if found_regs:
                        for found_reg in found_regs:
                            new_reg = ExportRegistrationImpl.fromreg(found_reg)
                            self._add_exported_service(new_reg)
                            result_regs.append(new_reg)
                    else:
                        # Here is where export is done
                        ed_props = error_props

                        try:
                            # use exporter.make_endpoint_props to make endpoint
                            # props, expect dictionary in response
                            ed_props = exporter.prepare_endpoint_props(
                                exported_intfs, service_ref, export_props
                            )
                            # export service and expect and EndpointDescription
                            # instance in response
                            export_ed = exporter.export_service(service_ref, ed_props)
                            # if a valid export_ed was returned
                            if export_ed:
                                export_reg = ExportRegistrationImpl.fromendpoint(
                                    self, exporter, export_ed, service_ref
                                )
                                export_event = RemoteServiceAdminEvent.fromexportreg(bundle, export_reg)
                            else:
                                raise RemoteServiceError("Service couldn't be exported")
                        except Exception:
                            export_reg = ExportRegistrationImpl.fromexception(
                                sys.exc_info(),
                                EndpointDescription.fromprops(ed_props),
                            )
                            export_event = RemoteServiceAdminEvent.fromexportreg(bundle, export_reg)

                        # add exported reg to exported services
                        self._add_exported_service(export_reg)
                        # add to result_regs also
                        result_regs.append(export_reg)
                        # add to result_events
                        result_events.append(export_event)

        # publish events
        for e in result_events:
            self._publish_event(e)

        # Explicit cast as caller doesn't have to know about the implementation
        return cast(List[ExportRegistration], result_regs)

    def import_service(self, endpoint_description: EndpointDescription) -> ImportRegistration:
        if not endpoint_description:
            raise RemoteServiceError("endpoint_description param must not be empty")
        assert isinstance(endpoint_description, EndpointDescription)

        remote_configs = get_string_plus_property(
            REMOTE_CONFIGS_SUPPORTED,
            endpoint_description.get_properties(),
            None,
        )
        if not remote_configs:
            raise RemoteServiceError(f"endpoint_description must contain {REMOTE_CONFIGS_SUPPORTED} property")

        try:
            importer = self._import_container_selector.select_import_container(
                remote_configs, endpoint_description
            )
            if not importer:
                raise SelectImporterError(f"Could not find importer for endpoint={endpoint_description}")
        except:
            import_reg = ImportRegistrationImpl.fromexception(sys.exc_info(), endpoint_description)
            import_event = RemoteServiceAdminEvent.fromimportreg(self._get_bundle(), import_reg)
        else:
            with self._imported_regs_lock:
                found_reg = None
                for reg in self._imported_regs:
                    if reg.match_ed(endpoint_description):
                        found_reg = reg
                        break

                if found_reg is not None:
                    # if so then found_regs will be non-empty
                    ex = found_reg.get_exception()
                    if ex:
                        new_reg = ImportRegistrationImpl.fromexception(ex, endpoint_description)
                    else:
                        new_reg = ImportRegistrationImpl.fromreg(found_reg)
                        new_reg.get_import_reference().update(endpoint_description)

                    self._add_imported_service(new_reg)
                    return new_reg

                # Here is where new import is done
                try:
                    svc_reg = importer.import_service(endpoint_description)
                    if svc_reg is None:
                        raise RemoteServiceError("Service couldn't be imported")

                    import_reg = ImportRegistrationImpl.fromendpoint(
                        self, importer, endpoint_description, svc_reg
                    )
                    import_event = RemoteServiceAdminEvent.fromimportreg(self._get_bundle(), import_reg)
                except:
                    import_reg = ImportRegistrationImpl.fromexception(sys.exc_info(), endpoint_description)
                    import_event = RemoteServiceAdminEvent.fromimportreg(self._get_bundle(), import_reg)

        self._imported_regs.append(import_reg)
        self._publish_event(import_event)
        return import_reg

    def _publish_event(self, event: RemoteServiceAdminEvent) -> None:
        listeners = self._rsa_event_listeners[:] if self._rsa_event_listeners else None
        if listeners:
            for l in listeners:
                try:
                    l.remote_admin_event(event)
                except:
                    _logger.error("Exception calling rsa event listener=%s", l)

    def _get_bundle(self) -> Bundle:
        return self._context.get_bundle()

    @Validate
    def _validate(self, context: BundleContext) -> None:
        self._context = context

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        with self._exported_regs_lock:
            for export_reg in self._exported_regs:
                export_reg.close()
            del self._exported_regs[:]

        with self._imported_regs_lock:
            for import_reg in self._imported_regs:
                import_reg.close()

            del self._imported_regs[:]

    def _unexport_service(self, svc_ref: ServiceReference[Any]) -> None:
        with self._exported_regs_lock:
            for reg in self._exported_regs:
                if reg.match_sr(svc_ref, None):
                    reg.close()

    @staticmethod
    def _valid_exported_interfaces(svc_ref: ServiceReference[Any], intfs: List[str]) -> bool:
        if not intfs:
            return False

        object_class = svc_ref.get_property(constants.OBJECTCLASS)
        for item in intfs:
            if not item in object_class:
                return False

        return True

    def _find_existing_export_endpoint(
        self, svc_ref: ServiceReference[Any], cid: Tuple[str, str]
    ) -> Optional["ExportRegistrationImpl"]:
        for er in self._exported_regs:
            if er.match_sr(svc_ref, cid):
                return er
        return None

    def _add_exported_service(self, export_reg: "ExportRegistrationImpl") -> None:
        with self._exported_regs_lock:
            self._exported_regs.append(export_reg)

    def _remove_exported_service(self, export_reg: "ExportRegistrationImpl") -> None:
        with self._exported_regs_lock:
            self._exported_regs.remove(export_reg)

    def _add_imported_service(self, import_reg: "ImportRegistrationImpl") -> None:
        with self._imported_regs_lock:
            self._imported_regs.append(import_reg)

    def _remove_imported_service(self, import_reg: "ImportRegistrationImpl") -> None:
        with self._imported_regs_lock:
            self._imported_regs.remove(import_reg)


# ------------------------------------------------------------------------------
# Internal class used to implement ExportRegistration/ExportReference below.
class _ExportEndpoint:
    def __init__(
        self,
        rsa: RemoteServiceAdminImpl,
        export_container: ExportContainer,
        ed: EndpointDescription,
        svc_ref: ServiceReference[Any],
    ) -> None:
        self.__rsa = rsa
        self.__export_container = export_container
        self.__ed = ed
        self.__svc_ref = svc_ref
        self.__lock = threading.RLock()
        self.__active_registrations: List[ExportRegistration] = []
        self.__orig_props = self.__ed.get_properties()

    def _rsa(self) -> RemoteServiceAdmin:
        with self.__lock:
            if self.__rsa is None:
                raise Exception("Export endpoint is already closed")

            return self.__rsa

    def _originalprops(self) -> Dict[str, Any]:
        with self.__lock:
            return self.get_reference().get_properties()

    def _add_export_registration(self, export_reg: ExportRegistration) -> None:
        with self.__lock:
            self.__active_registrations.append(export_reg)

    def _remove_export_registration(self, export_reg: ExportRegistration) -> None:
        with self.__lock:
            self.__active_registrations.remove(export_reg)

    def get_description(self) -> EndpointDescription:
        with self.__lock:
            if self.__ed is None:
                raise Exception("Export endpoint is already closed")

            return self.__ed

    def get_reference(self) -> ServiceReference[Any]:
        with self.__lock:
            if self.__svc_ref is None:
                raise Exception("Export endpoint is already closed")

            return self.__svc_ref

    def get_export_container_id(self) -> str:
        with self.__lock:
            if self.__export_container is None:
                raise Exception("Export endpoint is already closed")

            return self.__export_container.get_id()

    def get_export_container_ns(self) -> str:
        with self.__lock:
            if self.__export_container is None:
                raise Exception("Export endpoint is already closed")

            return self.__export_container.get_namespace()

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        with self.__lock:
            if self.__ed is None:
                raise Exception("Export endpoint is already closed")

            return self.__ed.get_remoteservice_id()

    def update(self, props: Dict[str, Any]) -> EndpointDescription:
        with self.__lock:
            if self.__svc_ref is None:
                raise Exception("Export endpoint is already closed")

            rsprops = self.__orig_props.copy()
            if not props:
                updatedprops = rsprops
            else:
                updatedprops = props.copy()
                updatedprops.update(rsprops)

            updatedprops.update(self.__svc_ref.get_properties())
            updatedprops[ECF_ENDPOINT_TIMESTAMP] = get_current_time_millis()
            self.__ed = EndpointDescription(self.__svc_ref, updatedprops)
            return self.__ed

    def close(self, export_reg: ExportRegistration) -> bool:
        if not isinstance(export_reg, ExportRegistrationImpl):
            # Doesn't come from us if it's not an ExportRegistrationImpl
            return False

        with self.__lock:
            if self.__rsa is None or self.__export_container is None or self.__ed is None:
                # Already closed
                return False

            try:
                self.__active_registrations.remove(export_reg)
            except ValueError:
                pass

            if len(self.__active_registrations) == 0:
                try:
                    self.__export_container.unexport_service(self.__ed)
                except:
                    _logger.error(
                        "get_exception in exporter.unexport_service ed=%s",
                        self.__ed,
                    )

                self.__rsa._remove_exported_service(export_reg)

                # Clean up
                self.__ed = None  # type: ignore
                self.__export_container = None  # type: ignore
                self.__svc_ref = None  # type: ignore
                self.__rsa = None  # type: ignore
                return True

        return False


# ------------------------------------------------------------------------------


class ExportReferenceImpl(ExportReference):
    """
    Implementation of ExportReference API. See ExportReference class for
    external contract and documentation
    """

    @classmethod
    def fromendpoint(cls, endpoint: _ExportEndpoint) -> "ExportReferenceImpl":
        return cls(endpoint=endpoint)

    @classmethod
    def fromexception(
        cls, e: Optional[Tuple[Any, Any, Any]], ed: EndpointDescription
    ) -> "ExportReferenceImpl":
        return cls(endpoint=None, exception=e, errored=ed)

    def __init__(
        self,
        endpoint: Optional[_ExportEndpoint] = None,
        exception: Optional[Tuple[Any, Any, Any]] = None,
        errored: Optional[EndpointDescription] = None,
    ) -> None:
        self.__lock = threading.RLock()
        if endpoint is None:
            if exception is None or errored is None:
                raise RemoteServiceError(
                    "Must supply either endpoint or " "throwable/error EndpointDescription"
                )
            self.__exception: Optional[Tuple[Any, Any, Any]] = exception
            self.__errored: Optional[EndpointDescription] = errored
            self._endpoint: Optional[_ExportEndpoint] = None
        else:
            self._endpoint = endpoint
            self.__exception = None
            self.__errored = None

    def get_export_container_id(self) -> Tuple[str, str]:
        with self.__lock:
            if self._endpoint is not None:
                export_ns = self._endpoint.get_export_container_ns()
                export_id = self._endpoint.get_export_container_id()
                if export_ns is None or export_id is None:
                    raise RemoteServiceError("Export container ID must not be None")

                return export_ns, export_id
            elif self.__errored is not None:
                return self.__errored.get_container_id()
            else:
                raise RemoteServiceError("Export container ID not set")

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        with self.__lock:
            if self._endpoint is not None:
                return self._endpoint.get_remoteservice_id()
            elif self.__errored is not None:
                return self.__errored.get_remoteservice_id()
            else:
                raise RemoteServiceError("Remote service ID not found")

    def get_reference(self) -> Optional[ServiceReference[Any]]:
        with self.__lock:
            if self._endpoint is not None:
                return self._endpoint.get_reference()

            return None

    def get_description(self) -> EndpointDescription:
        with self.__lock:
            if self._endpoint is not None:
                return self._endpoint.get_description()
            elif self.__errored is not None:
                return self.__errored
            else:
                raise RemoteServiceError("Endpoint description not set")

    def get_exception(self) -> Optional[Tuple[Any, Any, Any]]:
        with self.__lock:
            return self.__exception

    def update(self, properties: Dict[str, Any]) -> Optional[EndpointDescription]:
        with self.__lock:
            if self._endpoint is not None:
                return self._endpoint.update(properties)

            return None

    def close(self, export_reg: ExportRegistration) -> bool:
        with self.__lock:
            if self._endpoint is None:
                return False

            result = self._endpoint.close(export_reg)
            self._endpoint = None
            return bool(result)


# ------------------------------------------------------------------------------


class ExportRegistrationImpl(ExportRegistration):
    """
    Implementation of ExportRegistration API.
    See ExportRegistration class for external contract and documentation
    """

    @classmethod
    def fromreg(cls, export_reg: "ExportRegistrationImpl") -> "ExportRegistrationImpl":
        return cls(export_reg.__rsa, export_reg.__exportref._endpoint)

    @classmethod
    def fromendpoint(
        cls,
        rsa: RemoteServiceAdminImpl,
        exporter: ExportContainer,
        ed: EndpointDescription,
        svc_ref: ServiceReference[Any],
    ) -> "ExportRegistrationImpl":
        return cls(rsa, _ExportEndpoint(rsa, exporter, ed, svc_ref))

    @classmethod
    def fromexception(cls, e: Tuple[Any, Any, Any], ed: EndpointDescription) -> "ExportRegistrationImpl":
        return cls(rsa=None, endpoint=None, exception=e, errored=ed)

    def __init__(
        self,
        rsa: Optional[RemoteServiceAdminImpl] = None,
        endpoint: Optional[_ExportEndpoint] = None,
        exception: Optional[Tuple[Any, Any, Any]] = None,
        errored: Optional[EndpointDescription] = None,
    ) -> None:
        if endpoint is None:
            if exception is None or errored is None:
                raise RemoteServiceError("export endpoint or get_exception/errorED must not be null")

            self.__exportref: ExportReferenceImpl = ExportReferenceImpl.fromexception(exception, errored)
            self.__rsa = None
        else:
            self.__rsa = cast(RemoteServiceAdminImpl, endpoint._rsa())
            endpoint._add_export_registration(self)
            self.__exportref = ExportReferenceImpl.fromendpoint(endpoint)

        self.__closed = False
        self.__update_exception: Optional[Tuple[Any, Any, Any]] = None
        self.__lock = threading.RLock()

    def match_sr(self, svc_ref: ServiceReference[Any], cid: Optional[Tuple[str, str]] = None) -> bool:
        """
        Checks if this export registration matches the given service reference

        :param svc_ref: A service reference
        :param cid: A container ID
        :return: True if the service matches this export registration
        """
        with self.__lock:
            our_sr = self.get_reference()
            if our_sr is None:
                return False

            sr_compare = our_sr == svc_ref
            if cid is None:
                return sr_compare

            our_cid = self.get_export_container_id()
            if our_cid is None:
                return False

            return sr_compare and our_cid == cid

    def get_export_reference(self) -> Optional[ExportReference]:
        """
        Returns the reference matching this registration

        :return: An export reference
        """
        with self.__lock:
            if self.__closed:
                return None

            return self.__exportref

    def _exportendpoint(
        self, svc_ref: ServiceReference[Any], cid: Tuple[str, str]
    ) -> Optional[_ExportEndpoint]:
        with self.__lock:
            if self.__closed:
                return None

            if self.match_sr(svc_ref, cid):
                return self.__exportref._endpoint
            else:
                return None

    def get_export_container_id(self) -> Tuple[str, str]:
        """
        Returns the export container namespace and ID

        :return: An export container namespace and ID
        """
        with self.__lock:
            if self.__closed:
                raise RemoteServiceError("ExportRegistration already closed")

            return self.__exportref.get_export_container_id()

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        """
        Returns the remote service ID

        :return: The remote service ID
        """
        with self.__lock:
            if self.__closed:
                raise RemoteServiceError("ExportRegistration already closed")

            return self.__exportref.get_remoteservice_id()

    def get_reference(self) -> Optional[ServiceReference[Any]]:
        """
        Retruns the service reference of the exported service

        :return: A service reference
        """
        with self.__lock:
            if self.__closed:
                return None

            return self.__exportref.get_reference()

    def get_exception(self) -> Optional[Tuple[Any, Any, Any]]:
        """
        Returns the exception associated to the export

        :return: An exception tuple, if any
        """
        with self.__lock:
            if self.__closed or self.__update_exception is not None:
                return self.__update_exception

            return self.__exportref.get_exception()

    def get_description(self) -> EndpointDescription:
        """
        Returns the description of the endpoint

        :return: An endpoint description
        """
        with self.__lock:
            if self.__closed:
                raise RemoteServiceError("ExportRegistration already closed")

            return self.__exportref.get_description()

    def update(self, properties: Optional[Dict[str, Any]]) -> Optional[EndpointDescription]:
        with self.__lock:
            if self.__closed:
                try:
                    raise RemoteServiceError("Update failed since ExportRegistration already closed")
                except RemoteServiceError:
                    self.__update_exception = sys.exc_info()
                return None

            # if properties is set then copy
            props = properties.copy() if properties else dict()
            try:
                updated_ed = self.__exportref.update(props)
            except Exception:
                self.__update_exception = sys.exc_info()
                return None

            if updated_ed is None:
                try:
                    raise RemoteServiceError("Update failed because ExportEndpoint was None")
                except RemoteServiceError:
                    self.__update_exception = sys.exc_info()
                return None

            self.__update_exception = None
            if self.__rsa is not None:
                self.__rsa._publish_event(
                    RemoteServiceAdminEvent.fromexportupdate(self.__rsa._get_bundle(), self)
                )
            return updated_ed

    def close(self) -> None:
        """
        Cleans up the export endpoint
        """
        with self.__lock:
            if self.__closed:
                return

            exporter_id = self.__exportref.get_export_container_id()
            export_ref = self.__exportref
            rsid = self.__exportref.get_remoteservice_id()
            ed = self.__exportref.get_description()
            exception = self.__exportref.get_exception()

            # Update status
            self.__closed = True

            # Close underlying reference
            publish = self.__exportref.close(self)
            self.__exportref = None  # type: ignore

            # Keep a reference to the RSA to publish the event
            rsa = self.__rsa
            self.__rsa = None

        if (
            publish is not None
            and rsa is not None
            and export_ref is not None
            and exporter_id is not None
            and rsid is not None
            and ed is not None
        ):
            rsa._publish_event(
                RemoteServiceAdminEvent.fromexportunreg(
                    rsa._get_bundle(),
                    exporter_id,
                    rsid,
                    export_ref,
                    exception,
                    ed,
                )
            )


class _ImportEndpoint:
    def __init__(
        self,
        rsa: RemoteServiceAdminImpl,
        import_container: ImportContainer,
        ed: EndpointDescription,
        svc_reg: ServiceRegistration[Any],
    ) -> None:
        self.__rsa: RemoteServiceAdminImpl = rsa
        self.__importer: ImportContainer = import_container
        self.__ed: EndpointDescription = ed
        self.__svc_reg: ServiceRegistration[Any] = svc_reg
        self.__lock = threading.RLock()
        self.__active_registrations: List[ImportRegistration] = []

    def _add_import_registration(self, import_reg: ImportRegistration) -> None:
        with self.__lock:
            self.__active_registrations.append(import_reg)

    def _rsa(self) -> RemoteServiceAdminImpl:
        return self.__rsa

    def match_ed(self, ed: EndpointDescription) -> bool:
        with self.__lock:
            if len(self.__active_registrations) == 0:
                return False
            return self.__ed.is_same_service(ed)

    def get_reference(self) -> Optional[ServiceReference[Any]]:
        with self.__lock:
            if self.__importer and self.__svc_reg:
                return self.__svc_reg.get_reference()

    def get_description(self) -> EndpointDescription:
        with self.__lock:
            return self.__ed

    def get_import_container_id(self) -> str:
        with self.__lock:
            if self.__importer:
                return self.__importer.get_id()

    def get_import_container_ns(self) -> str:
        with self.__lock:
            if self.__importer:
                return self.__importer.get_namespace()

    def get_export_container_id(self) -> Tuple[str, str]:
        with self.__lock:
            return self.__ed.get_container_id()

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        with self.__lock:
            return self.__ed.get_remoteservice_id()

    def update(self, ed: EndpointDescription) -> Optional[EndpointDescription]:
        with self.__lock:
            if self.__svc_reg is None or self.__importer is None:
                return None

            # Prepare properties
            ed_props = self.__ed.get_properties()
            new_props = self.__importer._prepare_proxy_props(ed)
            ed_props.update(new_props)

            # Make a new endpoint description
            self.__ed = EndpointDescription.fromprops(ed_props)

            # Update the exported service
            self.__svc_reg.set_properties(self.__ed.get_properties())
            return self.__ed

    def close(self, import_reg: ImportRegistration) -> bool:
        if not isinstance(import_reg, ImportRegistrationImpl):
            # Doesn't come from us if it's not an ImportRegistrationImpl
            return False

        with self.__lock:
            try:
                self.__active_registrations.remove(import_reg)
            except ValueError:
                pass

            if not self.__active_registrations:
                if self.__svc_reg:
                    try:
                        self.__svc_reg.unregister()
                    except BundleException:
                        # The service might already have unregistered
                        pass
                    except:
                        _logger.error(
                            "Exception unregistering local proxy=%s",
                            self.__svc_reg.get_reference(),
                        )
                    self.__svc_reg = None  # type: ignore
                try:
                    self.__importer.unimport_service(self.__ed)
                except:
                    _logger.error(
                        "Exception calling importer.unimport_service with ed=%s",
                        self.__ed,
                    )
                    return False

                self.__rsa._remove_imported_service(import_reg)

                self.__importer = None  # type: ignore
                self.__ed = None  # type: ignore
                self.__rsa = None  # type: ignore
                return True

        return False


# ------------------------------------------------------------------------------
# Implementation of ExportReference API.  See ExportReference class for external
# contract and documentation
class ImportReferenceImpl(ImportReference):
    @classmethod
    def fromendpoint(cls, endpoint: _ImportEndpoint) -> "ImportReferenceImpl":
        return cls(endpoint=endpoint)

    @classmethod
    def fromexception(cls, e: Tuple[Any, Any, Any], errored: EndpointDescription) -> "ImportReferenceImpl":
        return cls(endpoint=None, exception=e, errored=errored)

    def __init__(
        self,
        endpoint: Optional[_ImportEndpoint] = None,
        exception: Optional[Tuple[Any, Any, Any]] = None,
        errored: Optional[EndpointDescription] = None,
    ) -> None:
        self.__lock = threading.RLock()
        if endpoint is None:
            self.__exception: Optional[Tuple[Any, Any, Any]] = exception
            self.__errored: Optional[EndpointDescription] = errored
            self.__endpoint: Optional[_ImportEndpoint] = None
        else:
            self.__endpoint = endpoint
            self.__exception = None
            self.__errored = None

    def _importendpoint(self) -> Optional[_ImportEndpoint]:
        with self.__lock:
            return self.__endpoint

    def match_ed(self, ed: EndpointDescription) -> bool:
        with self.__lock:
            if self.__endpoint:
                return self.__endpoint.match_ed(ed)
            return False

    def get_import_container_id(self) -> Tuple[str, str]:
        with self.__lock:
            if self.__endpoint:
                importer_ns = self.__endpoint.get_import_container_ns()
                importer_id = self.__endpoint.get_import_container_id()
            elif self.__errored:
                importer_ns, importer_id = self.__errored.get_container_id()

            return importer_ns, importer_id

    def get_import_container_ns(self) -> str:
        with self.__lock:
            if self.__endpoint:
                return self.__endpoint.get_import_container_ns()
            elif self.__errored:
                return self.__errored.get_container_id()[0]

    def get_export_container_id(self) -> str:
        with self.__lock:
            if self.__endpoint:
                return self.__endpoint.get_export_container_id()
            elif self.__errored:
                return self.__errored.get_container_id()

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        with self.__lock:
            if self.__endpoint:
                return self.__endpoint.get_remoteservice_id()

    def get_reference(self) -> Optional[ServiceReference[Any]]:
        with self.__lock:
            if self.__endpoint:
                return self.__endpoint.get_reference()

    def get_description(self) -> Optional[EndpointDescription]:
        with self.__lock:
            if self.__endpoint:
                return self.__endpoint.get_description()
            return self.__errored

    def get_exception(self) -> Optional[Tuple[Any, Any, Any]]:
        with self.__lock:
            return self.__exception

    def update(self, endpoint: EndpointDescription) -> Optional[EndpointDescription]:
        with self.__lock:
            if self.__endpoint:
                return self.__endpoint.update(endpoint)

    def close(self, import_reg: ImportRegistration) -> bool:
        with self.__lock:
            if not self.__endpoint:
                return False
            result = self.__endpoint.close(import_reg)
            self.__endpoint = None
            return result


# ------------------------------------------------------------------------------


class ImportRegistrationImpl(ImportRegistration):
    """
    Implementation of ExportRegistration API.

    See ExportRegistration class for external contract and documentation
    """

    @classmethod
    def fromendpoint(
        cls,
        rsa: RemoteServiceAdminImpl,
        importer: ImportContainer,
        ed: EndpointDescription,
        svc_reg: ServiceRegistration[Any],
    ) -> "ImportRegistrationImpl":
        return cls(endpoint=_ImportEndpoint(rsa, importer, ed, svc_reg))

    @classmethod
    def fromexception(cls, e: Tuple[Any, Any, Any], ed: EndpointDescription) -> "ImportRegistrationImpl":
        return cls(endpoint=None, exception=e, errored=ed)

    @classmethod
    def fromreg(cls, reg: "ImportRegistrationImpl") -> "ImportRegistrationImpl":
        return cls(endpoint=reg.__importref._importendpoint())

    def __init__(
        self,
        endpoint: Optional[_ImportEndpoint] = None,
        exception: Optional[Tuple[Any, Any, Any]] = None,
        errored: Optional[EndpointDescription] = None,
    ) -> None:
        self._rsa: Optional[RemoteServiceAdminImpl]

        if endpoint is None:
            if exception is None or errored is None:
                raise RemoteServiceError("export endpoint or get_exception/errorED must not be null")
            self.__importref: "ImportReferenceImpl" = ImportReferenceImpl.fromexception(exception, errored)
            self.__rsa = None
        else:
            self.__rsa = endpoint._rsa()
            endpoint._add_import_registration(self)
            self.__importref = ImportReferenceImpl.fromendpoint(endpoint)

        self.__closed = False
        self.__update_exception: Optional[Tuple[Any, Any, Any]] = None
        self.__lock = threading.RLock()

    def _import_endpoint(self) -> Optional[_ImportEndpoint]:
        with self.__lock:
            if self.__closed or self.__importref is None:
                return None

            return self.__importref._importendpoint()

    def match_ed(self, ed: EndpointDescription) -> bool:
        with self.__lock:
            if self.__closed:
                return False

            return self.__importref.match_ed(ed)

    def get_import_reference(self) -> ImportReference:
        with self.__lock:
            if self.__closed:
                raise RemoteServiceError("ImportRegistration already closed")

            return self.__importref

    def get_import_container_id(self) -> Tuple[str, str]:
        with self.__lock:
            if self.__closed:
                raise RemoteServiceError("ImportRegistration already closed")

            return self.__importref.get_import_container_id()

    def get_export_container_id(self) -> Tuple[str, str]:
        with self.__lock:
            if self.__closed:
                raise RemoteServiceError("ImportRegistration already closed")

            return self.__importref.get_export_container_id()

    def get_remoteservice_id(self) -> Tuple[Tuple[str, str], int]:
        with self.__lock:
            if self.__closed:
                raise RemoteServiceError("ImportRegistration already closed")

            return self.__importref.get_remoteservice_id()

    def get_reference(self) -> Optional[ServiceReference[Any]]:
        with self.__lock:
            if self.__closed:
                return None

            return self.__importref.get_reference()

    def get_exception(self) -> Optional[Tuple[Any, Any, Any]]:
        with self.__lock:
            if self.__closed or self.__update_exception is not None:
                return self.__update_exception

            return self.__importref.get_exception()

    def get_description(self) -> Optional[EndpointDescription]:
        with self.__lock:
            if self.__closed:
                return None

            return self.__importref.get_description()

    def update(self, endpoint_description: EndpointDescription) -> bool:
        with self.__lock:
            if self.__closed:
                try:
                    raise RemoteServiceError("Update failed since ImportRegistration already closed")
                except RemoteServiceError:
                    self.__update_exception = sys.exc_info()
                return False

            try:
                self.__importref.update(endpoint_description)
            except Exception:
                self.__update_exception = sys.exc_info()
                return False

            if self.__rsa:
                # pylint: disable=W0212
                self.__rsa._publish_event(
                    RemoteServiceAdminEvent.fromimportupdate(self.__rsa._get_bundle(), self)
                )
                return True

            return False

    def close(self) -> None:
        """
        Cleans up the import endpoint
        """
        with self.__lock:
            if self.__closed:
                return

            importer_id = self.__importref.get_import_container_id()
            rsid = self.__importref.get_remoteservice_id()
            import_ref = self.__importref
            exception = self.__importref.get_exception()
            ed = self.__importref.get_description()
            self.__closed = True
            publish = self.__importref.close(self)
            self.__importref = None  # type: ignore

            # Keep a reference to the RSA to publish the event
            rsa = self.__rsa
            self.__rsa = None

        if (
            publish is not None
            and rsa is not None
            and import_ref is not None
            and importer_id is not None
            and rsid is not None
            and ed is not None
        ):
            rsa._publish_event(
                RemoteServiceAdminEvent.fromimportunreg(
                    rsa._get_bundle(),
                    importer_id,
                    rsid,
                    import_ref,
                    exception,
                    ed,
                )
            )


# ------------------------------------------------------------------------------


class DebugRemoteServiceAdminListener(RemoteServiceAdminListener):
    """
    Implementation of RemoteServiceAdminListener that supports debugging by
    printing out information about the RemoteServiceAdminEvents.
    """

    EXPORT_MASK = (
        RemoteServiceAdminEvent.EXPORT_ERROR
        | RemoteServiceAdminEvent.EXPORT_REGISTRATION
        | RemoteServiceAdminEvent.EXPORT_UNREGISTRATION
        | RemoteServiceAdminEvent.EXPORT_WARNING
    )

    IMPORT_MASK = (
        RemoteServiceAdminEvent.IMPORT_ERROR
        | RemoteServiceAdminEvent.IMPORT_REGISTRATION
        | RemoteServiceAdminEvent.IMPORT_UNREGISTRATION
        | RemoteServiceAdminEvent.IMPORT_WARNING
    )

    ALL_MASK = EXPORT_MASK | IMPORT_MASK

    def __init__(
        self,
        file: IO[str] = sys.stdout,
        event_mask: int = ALL_MASK,
        write_endpoint: bool = True,
        ed_encoding: str = "unicode",
        xml_declaration: bool = True,
    ) -> None:
        self._output = file
        self._writer = EDEFWriter(ed_encoding, xml_declaration)
        self._event_mask = event_mask
        self._write_endpoint = write_endpoint
        self._eventtypestr = {
            RemoteServiceAdminEvent.EXPORT_ERROR: "EXPORT_ERROR",
            RemoteServiceAdminEvent.EXPORT_REGISTRATION: "EXPORT_REGISTRATION",
            RemoteServiceAdminEvent.EXPORT_UNREGISTRATION: "EXPORT_UNREGISTRATION",
            RemoteServiceAdminEvent.EXPORT_UPDATE: "EXPORT_UPDATE",
            RemoteServiceAdminEvent.EXPORT_WARNING: "EXPORT_WARNING",
            RemoteServiceAdminEvent.IMPORT_ERROR: "IMPORT_ERROR",
            RemoteServiceAdminEvent.IMPORT_REGISTRATION: "IMPORT_REGISTRATION",
            RemoteServiceAdminEvent.IMPORT_UNREGISTRATION: "IMPORT_UNREGISTRATION",
            RemoteServiceAdminEvent.IMPORT_UPDATE: "IMPORT_UPDATE",
            RemoteServiceAdminEvent.IMPORT_WARNING: "IMPORT_WARNING",
        }
        self._exporttypes = [
            RemoteServiceAdminEvent.EXPORT_REGISTRATION,
            RemoteServiceAdminEvent.EXPORT_UNREGISTRATION,
            RemoteServiceAdminEvent.EXPORT_UPDATE,
            RemoteServiceAdminEvent.EXPORT_WARNING,
        ]
        self._importtypes = [
            RemoteServiceAdminEvent.IMPORT_REGISTRATION,
            RemoteServiceAdminEvent.IMPORT_UNREGISTRATION,
            RemoteServiceAdminEvent.IMPORT_UPDATE,
            RemoteServiceAdminEvent.IMPORT_WARNING,
        ]
        self._errortypes = [
            RemoteServiceAdminEvent.EXPORT_ERROR,
            RemoteServiceAdminEvent.IMPORT_ERROR,
        ]

    def write_description(self, ed: Optional[EndpointDescription]) -> None:
        if self._write_endpoint and ed:
            self._output.write("---Endpoint Description---\n")
            self._output.write(self._writer.to_string([ed]))
            self._output.write("\n---End Endpoint Description---\n")
            self._output.flush()

    def write_ref(
        self,
        svc_ref: Optional[ServiceReference[Any]],
        cid: Tuple[str, str],
        rsid: Tuple[Tuple[str, str], int],
        ed: Optional[EndpointDescription],
    ) -> None:
        if svc_ref:
            self._output.write(str(svc_ref) + ";")

        self._output.write("local=" + str(cid))
        # get_remoteservice_id should be of form:  ((ns,cid,get_remoteservice_id)
        self._output.write(";remote=")
        if isinstance(rsid, tuple) and len(list(rsid)) == 2:
            nscid = rsid[0]
            if isinstance(nscid, tuple) and len(list(nscid)) == 2:
                self._output.write(str(nscid[1]) + ":" + str(rsid[1]))
        else:
            self._output.write(str(rsid))
        self._output.write("\n")
        self._output.flush()
        self.write_description(ed)

    def write_exception(self, exception: Tuple[Any, Any, Any]) -> None:
        self._output.write("---Exception Stack---\n")
        print_exception(
            exception[0],
            exception[1],
            exception[2],
            limit=None,
            file=self._output,
        )
        self._output.write("---End Exception Stack---\n")

    def write_type(self, event_type: int) -> None:
        (dt, micro) = datetime.now().strftime("%H:%M:%S.%f").split(".")
        dt = "%s.%03d" % (dt, int(micro) / 1000)
        self._output.write(dt + ";" + self._eventtypestr.get(event_type, "UNKNOWN") + ";")

    def write_event(self, rsa_event: RemoteServiceAdminEvent) -> None:
        event_type = rsa_event.get_type()
        rs_ref: Union[None, ImportReference, ExportReference] = None
        svc_ref = None
        exception = None
        self.write_type(event_type)
        if event_type in self._exporttypes:
            rs_ref = rsa_event.get_export_ref()
        elif event_type in self._importtypes:
            rs_ref = rsa_event.get_import_ref()
        elif event_type in self._errortypes:
            exception = rsa_event.get_exception()
        if rs_ref:
            svc_ref = rs_ref.get_reference()
        self.write_ref(
            svc_ref,
            rsa_event.get_container_id(),
            rsa_event.get_remoteservice_id(),
            rsa_event.get_description(),
        )
        if exception:
            self.write_exception(exception)

    def remote_admin_event(self, rsa_event: RemoteServiceAdminEvent) -> None:
        self.write_event(rsa_event)
