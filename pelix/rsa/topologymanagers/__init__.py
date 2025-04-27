#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Topology Manager API

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
from typing import Any, Dict, List, Optional, cast

import pelix.rsa.remoteserviceadmin as rsa_impl
from pelix.framework import BundleContext
from pelix.internals.events import ServiceEvent
from pelix.internals.hooks import EventListenerHook
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import Invalidate, Provides, Requires, Validate
from pelix.rsa import (
    SERVICE_EXPORTED_INTERFACES,
    SERVICE_RSA_EVENT_LISTENER,
    ImportRegistration,
    RemoteServiceAdmin,
    RemoteServiceAdminEvent,
    RemoteServiceAdminListener,
    get_exported_interfaces,
)
from pelix.rsa.endpointdescription import EndpointDescription
from pelix.rsa.providers.discovery import (
    SERVICE_ENDPOINT_LISTENER,
    EndpointAdvertiser,
    EndpointEvent,
    EndpointEventListener,
)
from pelix.services import SERVICE_EVENT_LISTENER_HOOK
from pelix.ipopo.constants import use_ipopo

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Standard logging
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


@Provides(
    [
        SERVICE_EVENT_LISTENER_HOOK,
        SERVICE_RSA_EVENT_LISTENER,
        SERVICE_ENDPOINT_LISTENER,
    ]
)
@Requires("_rsa", RemoteServiceAdmin)
@Requires("_advertisers", EndpointAdvertiser, True, True)
class TopologyManager(EventListenerHook, RemoteServiceAdminListener, EndpointEventListener):
    _rsa: RemoteServiceAdmin
    _advertisers: List[EndpointAdvertiser]

    def __init__(self) -> None:
        self._context: Optional[BundleContext] = None

    @Validate
    def _validate(self, context: BundleContext) -> None:
        self._context = context

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        self._context = None

    def _import_added_endpoint(self, endpoint_description: EndpointDescription) -> ImportRegistration:
        return self._rsa.import_service(endpoint_description)

    def _unimport_removed_endpoint(self, endpoint_description: EndpointDescription) -> None:
        # pylint: disable=W0212
        import_regs = cast(rsa_impl.RemoteServiceAdminImpl, self._rsa)._get_import_regs()
        for import_reg in import_regs:
            if import_reg.match_ed(endpoint_description):
                import_reg.close()

    def _update_imported_endpoint(self, endpoint_description: EndpointDescription) -> None:
        # pylint: disable=W0212
        import_regs = cast(rsa_impl.RemoteServiceAdminImpl, self._rsa)._get_import_regs()
        for import_reg in import_regs:
            if import_reg.match_ed(endpoint_description):
                import_reg.update(endpoint_description)

    def _handle_service_registered(self, service_ref: ServiceReference[Any]) -> None:
        exp_intfs = get_exported_interfaces(service_ref)
        # If no exported interfaces, then all done
        if not exp_intfs:
            return
        self._rsa.export_service(service_ref, {SERVICE_EXPORTED_INTERFACES: exp_intfs})

    def _handle_service_unregistering(self, service_ref: ServiceReference[Any]) -> None:
        # pylint: disable=W0212
        export_regs = cast(rsa_impl.RemoteServiceAdminImpl, self._rsa)._get_export_regs()
        if export_regs:
            for export_reg in export_regs:
                if export_reg.match_sr(service_ref):
                    _logger.debug(
                        "handle_service_unregistering. closing "
                        "export_registration for service reference=%s",
                        service_ref,
                    )
                    export_reg.close()

    def _handle_service_modified(self, service_ref: ServiceReference[Any]) -> None:
        # pylint: disable=W0212
        export_regs = cast(rsa_impl.RemoteServiceAdminImpl, self._rsa)._get_export_regs()
        if export_regs:
            for export_reg in export_regs:
                if export_reg.match_sr(service_ref):
                    _logger.debug(
                        "_handle_service_modified. updating " "export_registration for service reference=%s",
                        service_ref,
                    )

                    # actually update the export_reg here
                    if not export_reg.update(None):
                        _logger.warning(
                            "_handle_service_modified. updating" "update for service_ref=%s failed",
                            service_ref,
                        )

    def _handle_event(self, service_event: ServiceEvent[Any]) -> None:
        kind = service_event.get_kind()
        service_ref = service_event.get_service_reference()
        if kind == ServiceEvent.REGISTERED:
            self._handle_service_registered(service_ref)
        elif kind == ServiceEvent.UNREGISTERING:
            self._handle_service_unregistering(service_ref)
        elif kind == ServiceEvent.MODIFIED:
            self._handle_service_modified(service_ref)

    # impl of EventListenerHook
    def event(self, service_event: ServiceEvent[Any], listener_dict: Dict[Any, Any]) -> None:
        self._handle_event(service_event)

    def _advertise_endpoint(self, ed: EndpointDescription) -> None:
        for adv in self._advertisers or []:
            try:
                adv.advertise_endpoint(ed)
            except:
                _logger.error(
                    "Exception in advertise_endpoint for " "advertiser=%s endpoint=%s",
                    adv,
                    ed,
                )

    def _update_endpoint(self, ed: EndpointDescription) -> None:
        for adv in self._advertisers or []:
            try:
                adv.update_endpoint(ed)
            except:
                _logger.error(
                    "Exception in update_endpoint for advertiser=%s " "endpoint=%s",
                    adv,
                    ed,
                )

    def _unadvertise_endpoint(self, ed: EndpointDescription) -> None:
        for adv in self._advertisers or []:
            try:
                adv.unadvertise_endpoint(ed.get_id())
            except:
                _logger.error(
                    "Exception in unadvertise_endpoint for advertiser=%s " "endpoint=%s",
                    adv,
                    ed,
                )

    # impl of RemoteServiceAdminListener
    def remote_admin_event(self, rsa_event: RemoteServiceAdminEvent) -> None:
        ed = rsa_event.get_description()
        if ed is None:
            _logger.warning("Got an event without an endpoint description")
            return

        kind = rsa_event.get_type()
        if kind == RemoteServiceAdminEvent.EXPORT_REGISTRATION:
            self._advertise_endpoint(ed)
        elif kind == RemoteServiceAdminEvent.EXPORT_UNREGISTRATION:
            self._unadvertise_endpoint(ed)
        elif kind == RemoteServiceAdminEvent.EXPORT_UPDATE:
            self._update_endpoint(ed)

    def endpoint_changed(self, endpoint_event: EndpointEvent, matched_filter: Any) -> None:
        _logger.debug("TopologyManager.endpoint_event called. You probably want to override this method")
