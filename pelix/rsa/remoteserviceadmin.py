#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Remote Service Admin API

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Scott Lewis

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

from datetime import datetime
from distutils.util import strtobool
from traceback import print_exception
import logging
import threading
import sys

# Typing
try:
    # pylint: disable=W0611
    from typing import Any, Dict, List, Optional, Tuple
    from pelix.framework import Bundle, BundleContext
    from pelix.internals.registry import ServiceRegistration
    from pelix.rsa.providers.distribution import (
        ExportContainer,
        ImportContainer,
    )
except ImportError:
    pass

from pelix import constants
from pelix.constants import (
    BundleActivator,
    SERVICE_RANKING,
    OBJECTCLASS,
    OSGI_FRAMEWORK_UUID,
)
from pelix.framework import BundleException
from pelix.internals.registry import ServiceReference

from pelix.ipopo.decorators import (
    ComponentFactory,
    Provides,
    Instantiate,
    Validate,
    Invalidate,
    Requires,
    RequiresBest,
)

from pelix.rsa.edef import EDEFWriter
from pelix.rsa.endpointdescription import EndpointDescription

from pelix.rsa import (
    SelectImporterError,
    RemoteServiceError,
    validate_exported_interfaces,
    RemoteServiceAdminEvent,
    SERVICE_REMOTE_SERVICE_ADMIN,
    SERVICE_RSA_EVENT_LISTENER,
    get_exported_interfaces,
    SERVICE_EXPORTED_INTERFACES,
    get_edef_props_error,
    REMOTE_CONFIGS_SUPPORTED,
    SERVICE_EXPORTED_CONFIGS,
    SERVICE_INTENTS,
    SERVICE_EXPORTED_INTENTS,
    SERVICE_EXPORTED_INTENTS_EXTRA,
    ECF_ENDPOINT_TIMESTAMP,
    ENDPOINT_FRAMEWORK_UUID,
    get_current_time_millis,
    get_string_plus_property,
    ExportReference,
    ExportRegistration,
    set_append,
    ImportReference,
    ImportRegistration,
    RemoteServiceAdminListener,
)

from pelix.rsa.providers.distribution import (
    SERVICE_EXPORT_DISTRIBUTION_PROVIDER,
    SERVICE_IMPORT_DISTRIBUTION_PROVIDER,
)

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (0, 8, 1)
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
class Activator(object):
    """
    Bundle activator. By default, register an instance of
    RemoteServiceAdminEventListener service for debugging.
    This can be disabled by setting the DEBUG_PROPERTY aka
    ``pelix.rsa.remoteserviceadmin.debug`` to ``false``.
    """

    def __init__(self):
        self._context = None
        self._debug_reg = None

    def start(self, context):
        """
        Bundle starting
        """
        self._context = context
        debug_str = self._context.get_property(DEBUG_PROPERTY)
        if not debug_str:
            debug_str = DEBUG_PROPERTY_DEFAULT

        if strtobool(debug_str):
            self._debug_reg = self._context.register_service(
                SERVICE_RSA_EVENT_LISTENER,
                DebugRemoteServiceAdminListener(),
                None,
            )

    def stop(self, _):
        """
        Bundle stopping
        """
        if self._debug_reg:
            self._debug_reg.unregister()
            self._debug_reg = None
        self._context = None


# ------------------------------------------------------------------------------


SERVICE_EXPORT_CONTAINER_SELECTOR = "pelix.rsa.exportcontainerselector"


class ExportContainerSelector:
    """
    RSA Impl Export Container Selector service specification and default
    implementation.  The highest priority instance of this service available
    at runtime is used by the RemoteServiceAdmin implementation to select
    export containers to handle a given call to
    RemoteServiceAdmin.export_service
    """

    # pylint: disable=R0903
    def select_export_containers(
        self, service_ref, exported_intfs, export_props
    ):
        # type: (ServiceReference, List[str], Dict[str, Any]) -> List[ExportContainer]
        # pylint: disable=W0613
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
        raise Exception(
            "{0}.select_export_containers is not implemented".format(self)
        )


@ComponentFactory("pelix-rsa-exporterselector-factory")
@Provides(SERVICE_EXPORT_CONTAINER_SELECTOR)
@Requires(
    "_export_distribution_providers",
    SERVICE_EXPORT_DISTRIBUTION_PROVIDER,
    True,
    True,
)
@Instantiate(SERVICE_EXPORT_CONTAINER_SELECTOR, {SERVICE_RANKING: -1000000000})
class ExportContainerSelectorImpl(ExportContainerSelector):
    def __init__(self):
        self._export_distribution_providers = []

    def select_export_containers(
        self, service_ref, exported_intfs, export_props
    ):
        # type: (ServiceReference, List[str], Dict[str, Any]) -> List[ExportContainer]
        # get exported configs
        exported_configs = get_string_plus_property(
            SERVICE_EXPORTED_CONFIGS, export_props, None
        )
        # get service intents, via service.intents, services.exported.intents,
        # and extra
        service_intents_set = set_append(
            set(), export_props.get(SERVICE_INTENTS, None)
        )
        service_intents_set = set_append(
            service_intents_set,
            export_props.get(SERVICE_EXPORTED_INTENTS, None),
        )
        service_intents_set = set_append(
            service_intents_set,
            export_props.get(SERVICE_EXPORTED_INTENTS_EXTRA, None),
        )

        export_containers = []
        for export_provider in self._export_distribution_providers:
            export_container = export_provider.supports_export(
                exported_configs, list(service_intents_set), export_props
            )
            if export_container:
                export_containers.append(export_container)

        return export_containers


# ------------------------------------------------------------------------------
# Import Container Selector service specification and default
# implementation.  The highest priority instance of this service available
# at runtime is used by the RemoteServiceAdmin implementation to select
# a single import container to handle a given call to RemoteServiceAdmin.import_service
SERVICE_IMPORT_CONTAINER_SELECTOR = "pelix.rsa.importcontainerselector"


class ImportContainerSelector:
    # pylint: disable=R0903
    def select_import_container(self, remote_configs, endpoint_description):
        # type: (List[str], EndpointDescription) -> ImportContainer
        # pylint: disable=W0613
        """
        Select import container, given endpoint_description
        (EndpointDescription).
        Returns a single ImportContainer, or None.

        :param endpoint_description: EndpointDescription describing endpoint for
                                     possible import
        :return ImportContainer instance or None
        """
        raise Exception(
            "{0}.select_import_container is not implemented".format(self)
        )


# ------------------------------------------------------------------------------
@ComponentFactory("pelix-rsa-importerselector-factory")
@Provides(SERVICE_IMPORT_CONTAINER_SELECTOR)
@Requires(
    "_import_distribution_providers",
    SERVICE_IMPORT_DISTRIBUTION_PROVIDER,
    True,
    True,
)
@Instantiate("pelix-rsa-importerselector-impl", {SERVICE_RANKING: -1000000000})
class ImportContainerSelectorImpl(ImportContainerSelector):
    # pylint: disable=R0903
    def __init__(self):
        self._import_distribution_providers = []

    def select_import_container(self, remote_configs, endpoint_description):
        # type: (List[str], EndpointDescription) -> ImportContainer
        for import_provider in self._import_distribution_providers:
            import_container = import_provider.supports_import(
                remote_configs,
                endpoint_description.get_intents(),
                endpoint_description.get_properties(),
            )
            if import_container:
                return import_container

        return None


# ------------------------------------------------------------------------------
# Implementation of RemoteServiceAdmin service
# ------------------------------------------------------------------------------
@ComponentFactory("pelix-rsa-remoteserviceadminimpl-factory")
@Provides(SERVICE_REMOTE_SERVICE_ADMIN)
@RequiresBest(
    "_export_container_selector", SERVICE_EXPORT_CONTAINER_SELECTOR, False
)
@RequiresBest(
    "_import_container_selector", SERVICE_IMPORT_CONTAINER_SELECTOR, False
)
@Requires("_rsa_event_listeners", SERVICE_RSA_EVENT_LISTENER, True, True)
@Instantiate("pelix-rsa-remoteserviceadminimpl")
class RemoteServiceAdminImpl(object):
    def __init__(self):
        self._context = None  # type: BundleContext
        self._exported_regs = []  # type: List[ExportRegistrationImpl]
        self._exported_regs_lock = threading.RLock()
        self._imported_regs = []  # type: List[ImportRegistrationImpl]
        self._imported_regs_lock = threading.RLock()
        self._rsa_event_listeners = []
        self._export_container_selector = None  # type: ExportContainerSelector
        self._import_container_selector = None  # type: ImportContainerSelector

    def get_exported_services(self):
        # type: () -> List[ExportReference]
        result = []
        for reg in self._get_export_regs():
            exp_ref = reg.get_export_reference()
            if exp_ref:
                result.append(exp_ref)
        return result

    def get_imported_endpoints(self):
        # type: () -> List[ImportReference]
        result = []
        for reg in self._get_import_regs():
            imp_ref = reg.get_import_reference()
            if imp_ref:
                result.append(imp_ref)
        return result

    def _get_export_regs(self):
        # type: () -> List[ExportRegistration]
        with self._exported_regs_lock:
            return self._exported_regs[:]

    def _get_import_regs(self):
        # type: () -> List[ImportRegistration]
        with self._imported_regs_lock:
            return self._imported_regs[:]

    def export_service(self, service_ref, overriding_props=None):
        # type: (ServiceReference, Dict[str, Any]) -> List[ExportRegistration]
        if not service_ref:
            raise RemoteServiceError("service_ref must not be None")
        assert isinstance(service_ref, ServiceReference)
        # get exported interfaces
        exported_intfs = get_exported_interfaces(service_ref, overriding_props)
        # must be set by service_ref or overriding_props or error
        if not exported_intfs:
            raise RemoteServiceError(
                SERVICE_EXPORTED_INTERFACES
                + " must be set in svc_ref properties or overriding_props"
            )
        # If the given exported_interfaces is not valid, then return empty list
        if not validate_exported_interfaces(
            service_ref.get_property(OBJECTCLASS), exported_intfs
        ):
            return []
        # get export props by overriding service get_reference properties
        # (if overriding_props set)
        export_props = service_ref.get_properties().copy()
        if overriding_props:
            export_props.update(overriding_props)

        # Force the framework UID, as the one from error_props
        # was generated
        export_props[ENDPOINT_FRAMEWORK_UUID] = self._context.get_property(
            OSGI_FRAMEWORK_UUID
        )

        result_regs = []
        result_events = []
        exporters = None
        error_props = get_edef_props_error(
            service_ref.get_property(OBJECTCLASS)
        )
        try:
            # get list of exporters from export_container_selector service
            exporters = self._export_container_selector.select_export_containers(
                service_ref, exported_intfs, export_props
            )
            # if none returned then report as warning at return empty list
            if not exporters:
                _logger.warning(
                    "No exporting containers found to export "
                    "service_ref=%s;export_props=%s",
                    service_ref,
                    export_props,
                )
                return []
        except:
            error_reg = ExportRegistrationImpl.fromexception(
                sys.exc_info(), EndpointDescription(service_ref, error_props)
            )
            export_event = RemoteServiceAdminEvent.fromexportreg(
                self._get_bundle(), error_reg
            )
            result_regs.append(error_reg)
            self._add_exported_service(error_reg)
            result_events.append(export_event)

        # If no errors added to result_regs then we continue
        if not result_regs:
            # get _exported_regs_lock
            with self._exported_regs_lock:
                # cycle through all exporters
                for exporter in exporters:
                    found_regs = []
                    # get exporter id
                    exporterid = exporter.get_id()
                    for reg in self._exported_regs:
                        if reg.match_sr(service_ref, exporterid):
                            found_regs.append(reg)
                    # if so then found_regs will be non-empty
                    if found_regs:
                        for found_reg in found_regs:
                            new_reg = ExportRegistrationImpl.fromreg(found_reg)
                            self._add_exported_service(new_reg)
                            result_regs.append(new_reg)
                    else:
                        # Here is where export is done
                        export_reg = None
                        export_event = None
                        ed_props = error_props

                        try:
                            # use exporter.make_endpoint_props to make endpoint
                            # props, expect dictionary in response
                            ed_props = exporter.prepare_endpoint_props(
                                exported_intfs, service_ref, export_props
                            )
                            # export service and expect and EndpointDescription
                            # instance in response
                            export_ed = exporter.export_service(
                                service_ref, ed_props
                            )
                            # if a valid export_ed was returned
                            if export_ed:
                                export_reg = ExportRegistrationImpl.fromendpoint(
                                    self, exporter, export_ed, service_ref
                                )
                                export_event = RemoteServiceAdminEvent.fromexportreg(
                                    self._get_bundle(), export_reg
                                )
                        except Exception:
                            export_reg = ExportRegistrationImpl.fromexception(
                                sys.exc_info(),
                                EndpointDescription.fromprops(ed_props),
                            )
                            export_event = RemoteServiceAdminEvent.fromexportreg(
                                self._get_bundle(), export_reg
                            )

                        # add exported reg to exported services
                        self._add_exported_service(export_reg)
                        # add to result_regs also
                        result_regs.append(export_reg)
                        # add to result_events
                        result_events.append(export_event)
            # publish events
        for e in result_events:
            self._publish_event(e)
        return result_regs

    def import_service(self, endpoint_description):
        # type: (EndpointDescription) -> ImportRegistration
        if not endpoint_description:
            raise RemoteServiceError(
                "endpoint_description param must not be empty"
            )
        assert isinstance(endpoint_description, EndpointDescription)

        remote_configs = get_string_plus_property(
            REMOTE_CONFIGS_SUPPORTED,
            endpoint_description.get_properties(),
            None,
        )
        if not remote_configs:
            raise RemoteServiceError(
                "endpoint_description must contain {0} property".format(
                    REMOTE_CONFIGS_SUPPORTED
                )
            )

        try:
            importer = self._import_container_selector.select_import_container(
                remote_configs, endpoint_description
            )
            if not importer:
                raise SelectImporterError(
                    "Could not find importer for endpoint={0}".format(
                        endpoint_description
                    )
                )
        except:
            import_reg = ImportRegistrationImpl.fromexception(
                sys.exc_info(), endpoint_description
            )
            import_event = RemoteServiceAdminEvent.fromimportreg(
                self._get_bundle(), import_reg
            )
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
                        new_reg = ImportRegistrationImpl.fromexception(
                            ex, endpoint_description
                        )
                    else:
                        new_reg = ImportRegistrationImpl.fromreg(found_reg)
                        new_reg.get_import_reference().update(
                            endpoint_description
                        )

                    self._add_imported_service(new_reg)
                    return new_reg

                # Here is where new import is done
                try:
                    svc_reg = importer.import_service(endpoint_description)
                    import_reg = ImportRegistrationImpl.fromendpoint(
                        self, importer, endpoint_description, svc_reg
                    )
                    import_event = RemoteServiceAdminEvent.fromimportreg(
                        self._get_bundle(), import_reg
                    )
                except:
                    import_reg = ImportRegistrationImpl.fromexception(
                        sys.exc_info(), endpoint_description
                    )
                    import_event = RemoteServiceAdminEvent.fromimportreg(
                        self._get_bundle(), import_reg
                    )

        self._imported_regs.append(import_reg)
        self._publish_event(import_event)
        return import_reg

    def _publish_event(self, event):
        listeners = self._rsa_event_listeners
        if listeners:
            for l in listeners:
                try:
                    l.remote_admin_event(event)
                except:
                    _logger.exception(
                        "Exception calling rsa event listener=%s", l
                    )

    def _get_bundle(self):
        # type: () -> Optional[Bundle]
        return self._context.get_bundle() if self._context else None

    @Validate
    def _validate(self, context):
        self._context = context

    @Invalidate
    def _invalidate(self, _):
        with self._exported_regs_lock:
            for reg in self._exported_regs:
                reg.close()
            del self._exported_regs[:]
        with self._imported_regs_lock:
            for reg in self._imported_regs:
                reg.close()

            del self._imported_regs[:]
        self._context = None

    def _unexport_service(self, svc_ref):
        # type: (ServiceReference) -> None
        with self._exported_regs_lock:
            for reg in self._exported_regs:
                if reg.match_sr(svc_ref, None):
                    reg.close()

    @staticmethod
    def _valid_exported_interfaces(svc_ref, intfs):
        # type: (ServiceReference, List[str]) -> bool
        if not intfs:
            return False

        object_class = svc_ref.get_property(constants.OBJECTCLASS)
        for item in intfs:
            if not item in object_class:
                return False

        return True

    def _find_existing_export_endpoint(self, svc_ref, cid):
        # type: (ServiceReference, str) -> Optional[ExportRegistration]
        for er in self._exported_regs:
            if er.match_sr(svc_ref, cid):
                return er
        return None

    def _add_exported_service(self, export_reg):
        # type: (ExportRegistration) -> None
        with self._exported_regs_lock:
            self._exported_regs.append(export_reg)

    def _remove_exported_service(self, export_reg):
        # type: (ExportRegistration) -> None
        with self._exported_regs_lock:
            self._exported_regs.remove(export_reg)

    def _add_imported_service(self, import_reg):
        # type: (ImportRegistration) -> None
        with self._imported_regs_lock:
            self._imported_regs.append(import_reg)

    def _remove_imported_service(self, import_reg):
        # type: (ImportRegistration) -> None
        with self._imported_regs_lock:
            self._imported_regs.remove(import_reg)


# ------------------------------------------------------------------------------
# Internal class used to implement ExportRegistration/ExportReference below.
class _ExportEndpoint(object):
    def __init__(self, rsa, export_container, ed, svc_ref):
        # type: (RemoteServiceAdminImpl, ExportContainer, EndpointDescription, ServiceReference) -> None
        assert rsa
        self.__rsa = rsa
        assert export_container
        self.__export_container = export_container
        assert ed
        self.__ed = ed
        assert svc_ref
        self.__svc_ref = svc_ref
        self.__lock = threading.RLock()
        self.__active_registrations = []  # type: List[ExportRegistration]
        self.__orig_props = self.__ed.get_properties()

    def _rsa(self):
        with self.__lock:
            return self.__rsa

    def _originalprops(self):
        # type: () -> Dict[str, Any]
        with self.__lock:
            return self.get_reference().get_properties()

    def _add_export_registration(self, export_reg):
        # type: (ExportRegistration) -> None
        with self.__lock:
            self.__active_registrations.append(export_reg)

    def _remove_export_registration(self, export_reg):
        # type: (ExportRegistration) -> None
        with self.__lock:
            self.__active_registrations.remove(export_reg)

    def get_description(self):
        # type: () -> EndpointDescription
        with self.__lock:
            return self.__ed

    def get_reference(self):
        # type: () -> ServiceReference
        with self.__lock:
            return self.__svc_ref

    def get_export_container_id(self):
        # type: () -> str
        with self.__lock:
            return self.__export_container.get_id()

    def get_remoteservice_id(self):
        # type: () -> Tuple[Tuple[str, str], int]
        with self.__lock:
            return self.__ed.get_remoteservice_id()

    def update(self, props):
        # type: (Dict[str, Any]) -> EndpointDescription
        with self.__lock:
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

    def close(self, export_reg):
        # type: (ExportRegistration) -> bool
        with self.__lock:
            try:
                self.__active_registrations.remove(export_reg)
            except ValueError:
                pass
            if len(self.__active_registrations) is 0:
                try:
                    self.__export_container.unexport_service(self.__ed)
                except:
                    _logger.exception(
                        "get_exception in exporter.unexport_service ed=%s",
                        self.__ed,
                    )

                # pylint: disable=W0212
                self.__rsa._remove_exported_service(export_reg)
                self.__ed = (
                    self.__export_container
                ) = self.__svc_ref = self.__rsa = None
                return True
        return False


# ------------------------------------------------------------------------------


class ExportReferenceImpl(ExportReference):
    """
    Implementation of ExportReference API. See ExportReference class for
    external contract and documentation
    """

    @classmethod
    def fromendpoint(cls, endpoint):
        # type: (_ExportEndpoint) -> ExportReference
        return cls(endpoint=endpoint)

    @classmethod
    def fromexception(cls, e, ed):
        # type: (Optional[Tuple[Any, Any, Any]], EndpointDescription) -> ExportReference
        return cls(endpoint=None, exception=e, errored=ed)

    def __init__(self, endpoint=None, exception=None, errored=None):
        # type: (Optional[_ExportEndpoint], Optional[Tuple[Any, Any, Any]], Optional[EndpointDescription]) -> None
        self.__lock = threading.RLock()
        if endpoint is None:
            if exception is None or errored is None:
                raise RemoteServiceError(
                    "Must supply either endpoint or "
                    "throwable/error EndpointDescription"
                )
            self.__exception = exception
            self.__errored = errored
            self._endpoint = None
        else:
            self._endpoint = endpoint
            self.__exception = self.__errored = None

    def get_export_container_id(self):
        # type: () -> Optional[Tuple[str, str]]
        with self.__lock:
            return (
                None
                if self._endpoint is None
                else self._endpoint.get_export_container_id()
            )

    def get_remoteservice_id(self):
        # type: () -> Optional[Tuple[str, str]]
        with self.__lock:
            return (
                None
                if self._endpoint is None
                else self._endpoint.get_remoteservice_id()
            )

    def get_reference(self):
        # type: () -> Optional[ServiceReference]
        with self.__lock:
            return (
                None
                if self._endpoint is None
                else self._endpoint.get_reference()
            )

    def get_description(self):
        # type: () -> Optional[EndpointDescription]
        with self.__lock:
            return (
                self.__errored
                if self._endpoint is None
                else self._endpoint.get_description()
            )

    def get_exception(self):
        # type: () -> Tuple[Any, Any, Any]
        with self.__lock:
            return self.__exception

    def update(self, properties):
        # type: (Dict[str, Any]) -> EndpointDescription
        with self.__lock:
            return (
                None
                if self._endpoint is None
                else self._endpoint.update(properties)
            )

    def close(self, export_reg):
        # type: (ExportRegistration) -> bool
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
    def fromreg(cls, export_reg):
        # type: (ExportRegistrationImpl) -> ExportRegistrationImpl
        # pylint: disable=W0212
        return cls(export_reg.__rsa, export_reg.__exportref._endpoint)

    @classmethod
    def fromendpoint(cls, rsa, exporter, ed, svc_ref):
        # type: (RemoteServiceAdminImpl, ExportContainer, EndpointDescription, ServiceReference) -> ExportRegistration
        return cls(rsa, _ExportEndpoint(rsa, exporter, ed, svc_ref))

    @classmethod
    def fromexception(cls, e, ed):
        # type: (Tuple[Any, Any, Any], EndpointDescription) -> ExportRegistration
        return cls(rsa=None, endpoint=None, exception=e, errored=ed)

    def __init__(self, rsa=None, endpoint=None, exception=None, errored=None):
        # type: (Optional[RemoteServiceAdminImpl], Optional[_ExportEndpoint], Optional[Tuple[Any, Any, Any]], Optional[EndpointDescription]) -> None
        # pylint: disable=W0212
        if endpoint is None:
            if exception is None or errored is None:
                raise RemoteServiceError(
                    "export endpoint or get_exception/errorED must not be null"
                )
            self.__exportref = ExportReferenceImpl.fromexception(
                exception, errored
            )  # type: ExportReferenceImpl
            self.__rsa = None
        else:
            self.__rsa = endpoint._rsa()
            endpoint._add_export_registration(self)
            self.__exportref = ExportReferenceImpl.fromendpoint(
                endpoint
            )  # type: ExportReferenceImpl

        self.__closed = False
        self.__updateexception = None
        self.__lock = threading.RLock()

    def match_sr(self, svc_ref, cid=None):
        # type: (ServiceReference, Optional[Tuple[str, str]] ) -> bool
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

    def get_export_reference(self):
        # type: () -> ExportReference
        """
        Returns the reference matching this registration

        :return: An export reference
        """
        with self.__lock:
            return None if self.__closed else self.__exportref

    def _exportendpoint(self, svc_ref, cid):
        # type: (ServiceReference, Tuple[str, str]) -> Optional[_ExportEndpoint]
        with self.__lock:
            # pylint: disable=W0212
            return (
                None
                if self.__closed
                else self.__exportref._endpoint
                if self.match_sr(svc_ref, cid)
                else None
            )

    def get_export_container_id(self):
        # type: () -> Optional[Tuple[str, str]]
        """
        Returns the export container ID

        :return: An export container ID
        """
        with self.__lock:
            return (
                None
                if self.__closed
                else self.__exportref.get_export_container_id()
            )

    def get_remoteservice_id(self):
        # type: () -> Optional[Tuple[Tuple[str, str], int]]
        """
        Returns the remote service ID

        :return: The remote service ID
        """
        with self.__lock:
            return (
                None
                if self.__closed
                else self.__exportref.get_remoteservice_id()
            )

    def get_reference(self):
        # type: () -> Optional[ServiceReference]
        """
        Retruns the service reference of the exported service

        :return: A service reference
        """
        with self.__lock:
            return None if self.__closed else self.__exportref.get_reference()

    def get_exception(self):
        # type: () -> Optional[Tuple[Any, Any, Any]]
        """
        Returns the exception associated to the export

        :return: An exception tuple, if any
        """
        with self.__lock:
            return (
                self.__updateexception
                if self.__updateexception or self.__closed
                else self.__exportref.get_exception()
            )

    def get_description(self):
        # type: () -> Optional[EndpointDescription]
        """
        Returns the description of the endpoint

        :return: An endpoint description
        """
        with self.__lock:
            return None if self.__closed else self.__exportref.get_description()

    def update(self, properties):
        # type: (Dict[str, Any]) -> Optional[EndpointDescription]
        with self.__lock:
            if self.__closed:
                self.__updateexception = ValueError(
                    "Update failed since ExportRegistration already closed"
                )
                return None
            # if properties is set then copy
            props = properties.copy() if properties else dict()
            try:
                updated_ed = self.__exportref.update(props)
            except Exception as e:
                self.__updateexception = e
                return None

            if not updated_ed:
                self.__updateexception = ValueError(
                    "Update failed because ExportEndpoint was None"
                )
                return None

            # pylint: disable=W0212
            self.__updateexception = None
            if self.__rsa:
                self.__rsa._publish_event(
                    RemoteServiceAdminEvent.fromexportupdate(
                        self.__rsa._get_bundle(), self
                    )
                )
            return updated_ed

    def close(self):
        """
        Cleans up the export endpoint
        """
        publish = False
        exporterid = rsid = exception = export_ref = ed = None
        with self.__lock:
            if not self.__closed:
                exporterid = self.__exportref.get_export_container_id()
                export_ref = self.__exportref
                rsid = self.__exportref.get_remoteservice_id()
                ed = self.__exportref.get_description()
                exception = self.__exportref.get_exception()
                self.__closed = True
                publish = self.__exportref.close(self)
                self.__exportref = None

        # pylint: disable=W0212
        if publish and export_ref and self.__rsa:
            self.__rsa._publish_event(
                RemoteServiceAdminEvent.fromexportunreg(
                    self.__rsa._get_bundle(),
                    exporterid,
                    rsid,
                    export_ref,
                    exception,
                    ed,
                )
            )
            self.__rsa = None


class _ImportEndpoint(object):
    def __init__(self, rsa, import_container, ed, svc_reg):
        # type: (RemoteServiceAdminImpl, ImportContainer, EndpointDescription, ServiceRegistration) -> None
        assert rsa
        self.__rsa = rsa
        assert import_container
        self.__importer = import_container
        assert ed
        self.__ed = ed
        assert svc_reg
        self.__svc_reg = svc_reg
        self.__lock = threading.RLock()
        self.__active_registrations = []  # type: List[ImportRegistration]

    def _add_import_registration(self, import_reg):
        # type: (ImportRegistration) -> None
        with self.__lock:
            self.__active_registrations.append(import_reg)

    def _rsa(self):
        # type: () -> RemoteServiceAdminImpl
        return self.__rsa

    def match_ed(self, ed):
        # type: (EndpointDescription) -> bool
        with self.__lock:
            if len(self.__active_registrations) is 0:
                return False
            return self.__ed.is_same_service(ed)

    def get_reference(self):
        # type: () -> ServiceReference
        with self.__lock:
            return (
                None
                if self.__importer is None
                else self.__svc_reg.get_reference()
            )

    def get_description(self):
        # type: () -> EndpointDescription
        with self.__lock:
            return self.__ed

    def get_import_container_id(self):
        # type: () -> str
        with self.__lock:
            return None if self.__importer is None else self.__importer.get_id()

    def get_export_container_id(self):
        # type: () -> Tuple[str, str]
        with self.__lock:
            return self.__ed.get_container_id()

    def get_remoteservice_id(self):
        # type: () -> Tuple[Tuple[str, str], int]
        with self.__lock:
            return self.__ed.get_remoteservice_id()

    def update(self, ed):
        # type: (EndpointDescription) -> Optional[EndpointDescription]
        with self.__lock:
            if self.__svc_reg is None:
                return None

            # Prepare properties
            # pylint: disable=W0212
            ed_props = self.__ed.get_properties()
            new_props = self.__importer._prepare_proxy_props(ed)
            ed_props.update(new_props)

            # Make a new endpoint description
            self.__ed = EndpointDescription.fromprops(ed_props)

            # Update the exported service
            self.__svc_reg.set_properties(self.__ed.get_properties())
            return self.__ed

    def close(self, import_reg):
        with self.__lock:
            try:
                self.__active_registrations.remove(import_reg)
            except ValueError:
                pass

            if not self.__active_registrations:
                if self.__svc_reg is not None:
                    try:
                        self.__svc_reg.unregister()
                    except BundleException:
                        # The service might already have unregistered
                        pass
                    except:
                        _logger.exception(
                            "Exception unregistering local proxy=%s",
                            self.__svc_reg.get_reference(),
                        )
                    self.__svc_reg = None
                try:
                    self.__importer.unimport_service(self.__ed)
                except:
                    _logger.exception(
                        "Exception calling importer.unimport_service with ed=%s",
                        self.__ed,
                    )
                    return False

                # pylint: disable=W0212
                self.__rsa._remove_imported_service(import_reg)
                self.__importer = self.__ed = self.__rsa = None
                return True

        return False


# ------------------------------------------------------------------------------
# Implementation of ExportReference API.  See ExportReference class for external
# contract and documentation
class ImportReferenceImpl(ImportReference):
    @classmethod
    def fromendpoint(cls, endpoint):
        # type: (_ImportEndpoint) -> ImportReferenceImpl
        return cls(endpoint=endpoint)

    @classmethod
    def fromexception(cls, e, errored):
        # type: (Tuple[Any, Any, Any], EndpointDescription) -> ImportReferenceImpl
        return cls(endpoint=None, exception=e, errored=errored)

    def __init__(self, endpoint=None, exception=None, errored=None):
        # type: (Optional[_ImportEndpoint], Optional[Tuple[Any, Any, Any]], Optional[EndpointDescription]) -> None
        self.__lock = threading.RLock()
        if endpoint is None:
            if exception is None or errored is None:
                raise RemoteServiceError(
                    "Must supply either endpoint or "
                    "throwable/errorEndpointDescription"
                )
            self.__exception = exception
            self.__errored = errored
            self.__endpoint = None
        else:
            self.__endpoint = endpoint
            self.__exception = self.__errored = None

    def _importendpoint(self):
        # type: () -> _ImportEndpoint
        with self.__lock:
            return self.__endpoint

    def match_ed(self, ed):
        # type: (EndpointDescription) -> bool
        with self.__lock:
            return (
                None
                if self.__endpoint is None
                else self.__endpoint.match_ed(ed)
            )

    def get_import_container_id(self):
        # type: () -> str
        with self.__lock:
            return (
                None
                if self.__endpoint is None
                else self.__endpoint.get_import_container_id()
            )

    def get_export_container_id(self):
        with self.__lock:
            return (
                None
                if self.__endpoint is None
                else self.__endpoint.get_export_container_id()
            )

    def get_remoteservice_id(self):
        # type: () -> Optional[Tuple[Tuple[str, str], int]]
        with self.__lock:
            return (
                None
                if self.__endpoint is None
                else self.__endpoint.get_remoteservice_id()
            )

    def get_reference(self):
        # type: () -> Optional[ServiceReference]
        with self.__lock:
            return (
                None
                if self.__endpoint is None
                else self.__endpoint.get_reference()
            )

    def get_description(self):
        # type: () -> Optional[EndpointDescription]
        with self.__lock:
            return (
                self.__errored
                if self.__endpoint is None
                else self.__endpoint.get_description()
            )

    def get_exception(self):
        # type: () -> Optional[Tuple[Any, Any, Any]]
        with self.__lock:
            return self.__exception

    def update(self, endpoint):
        # type: (EndpointDescription) -> Optional[EndpointDescription]
        with self.__lock:
            return (
                None
                if self.__endpoint is None
                else self.__endpoint.update(endpoint)
            )

    def close(self, import_reg):
        with self.__lock:
            if self.__endpoint is None:
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
    def fromendpoint(cls, rsa, importer, ed, svc_reg):
        # type: (RemoteServiceAdminImpl, ImportContainer, EndpointDescription, ServiceRegistration) -> ImportRegistration
        return cls(endpoint=_ImportEndpoint(rsa, importer, ed, svc_reg))

    @classmethod
    def fromexception(cls, e, ed):
        # type: (Tuple[Any, Any, Any], EndpointDescription) -> ImportRegistration
        return cls(endpoint=None, exception=e, errored=ed)

    @classmethod
    def fromreg(cls, reg):
        # type: (ImportRegistrationImpl) -> ImportRegistrationImpl
        # pylint: disable=W0212
        return cls(endpoint=reg.__importref._importendpoint())

    def __init__(self, endpoint=None, exception=None, errored=None):
        # type: (Optional[_ImportEndpoint], Optional[Tuple[Any, Any, Any]], Optional[EndpointDescription]) -> None
        # pylint: disable=W0212
        if endpoint is None:
            if exception is None or errored is None:
                raise RemoteServiceError(
                    "export endpoint or get_exception/errorED must not be null"
                )
            self.__importref = ImportReferenceImpl.fromexception(
                exception, errored
            )
            self.__rsa = None
        else:
            self.__rsa = endpoint._rsa()
            endpoint._add_import_registration(self)
            self.__importref = ImportReferenceImpl.fromendpoint(endpoint)

        self.__closed = False
        self.__updateexception = None
        self.__lock = threading.RLock()

    def _import_endpoint(self):
        # type: () -> _ImportEndpoint
        # pylint: disable=W0212
        with self.__lock:
            return None if self.__closed else self.__importref._importendpoint()

    def match_ed(self, ed):
        # type: (EndpointDescription) -> bool
        with self.__lock:
            return False if self.__closed else self.__importref.match_ed(ed)

    def get_import_reference(self):
        # type: () -> ImportReference
        with self.__lock:
            return None if self.__closed else self.__importref

    def get_import_container_id(self):
        # type: () -> str
        with self.__lock:
            return (
                None
                if self.__closed
                else self.__importref.get_import_container_id()
            )

    def get_export_container_id(self):
        with self.__lock:
            return (
                None
                if self.__closed
                else self.__importref.get_export_container_id()
            )

    def get_remoteservice_id(self):
        # type: () -> Optional[Tuple[Tuple[str, str], int]]
        with self.__lock:
            return (
                None
                if self.__closed is None
                else self.__importref.get_remoteservice_id()
            )

    def get_reference(self):
        # type: () -> Optional[ServiceReference]
        with self.__lock:
            return None if self.__closed else self.__importref.get_reference()

    def get_exception(self):
        # type: () -> Optional[Tuple[Any, Any, Any]]
        with self.__lock:
            return (
                self.__updateexception
                if self.__updateexception or self.__closed
                else self.__importref.get_exception()
            )

    def get_description(self):
        # type: () -> Optional[EndpointDescription]
        with self.__lock:
            return None if self.__closed else self.__importref.get_description()

    def update(self, endpoint_description):
        # type: (EndpointDescription) -> bool
        with self.__lock:
            if self.__closed:
                self.__updateexception = ValueError(
                    "Update failed since ImportRegistration already closed"
                )
                return False

            try:
                self.__importref.update(endpoint_description)
            except Exception as e:
                self.__updateexception = e
                return False

            if self.__rsa:
                # pylint: disable=W0212
                self.__rsa._publish_event(
                    RemoteServiceAdminEvent.fromimportupdate(
                        self.__rsa._get_bundle(), self
                    )
                )
                return True

            return False

    def close(self):
        publish = False
        importerid = rsid = import_ref = exception = ed = None
        with self.__lock:
            if not self.__closed:
                importerid = self.__importref.get_import_container_id()
                rsid = self.__importref.get_remoteservice_id()
                import_ref = self.__importref
                exception = self.__importref.get_exception()
                ed = self.__importref.get_description()
                self.__closed = True
                publish = self.__importref.close(self)
                self.__importref = None
        if publish and import_ref and self.__rsa:
            # pylint: disable=W0212
            self.__rsa._publish_event(
                RemoteServiceAdminEvent.fromimportunreg(
                    self.__rsa._get_bundle(),
                    importerid,
                    rsid,
                    import_ref,
                    exception,
                    ed,
                )
            )
            self.__rsa = None


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
        file=sys.stdout,
        event_mask=ALL_MASK,
        write_endpoint=True,
        ed_encoding="unicode",
        xml_declaration=True,
    ):
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

    def write_description(self, ed):
        if self._write_endpoint and ed:
            self._output.write("---Endpoint Description---\n")
            self._output.write(self._writer.to_string([ed]))
            self._output.write("\n---End Endpoint Description---\n")
            self._output.flush()

    def write_ref(self, svc_ref, cid, rsid, ed):
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

    def write_exception(self, exception):
        self._output.write("---Exception Stack---\n")
        print_exception(
            exception[0],
            exception[1],
            exception[2],
            limit=None,
            file=self._output,
        )
        self._output.write("---End Exception Stack---\n")

    def write_type(self, event_type):
        (dt, micro) = datetime.now().strftime("%H:%M:%S.%f").split(".")
        dt = "%s.%03d" % (dt, int(micro) / 1000)
        self._output.write(
            dt + ";" + self._eventtypestr.get(event_type, "UNKNOWN") + ";"
        )

    def write_event(self, rsa_event):
        event_type = rsa_event.get_type()
        rs_ref = None
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

    def remote_admin_event(self, rsa_event):
        self.write_event(rsa_event)
