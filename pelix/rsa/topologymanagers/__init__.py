#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Topology Manager API

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0
:version: 0.1.0

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

import logging

from pelix.framework import ServiceEvent
from pelix.internals.hooks import EventListenerHook
from pelix.ipopo.decorators import (
    Validate,
    Invalidate,
    Property,
    Provides,
    Requires,
)
from pelix.services import SERVICE_EVENT_LISTENER_HOOK

from pelix.rsa.providers.discovery import (
    SERVICE_ENDPOINT_ADVERTISER,
    SERVICE_ENDPOINT_LISTENER,
    EndpointEventListener,
)

from pelix.rsa import (
    SERVICE_EXPORTED_INTERFACES,
    get_exported_interfaces,
    SERVICE_RSA_EVENT_LISTENER,
    SERVICE_REMOTE_SERVICE_ADMIN,
    ECF_ENDPOINT_CONTAINERID_NAMESPACE,
    RemoteServiceAdminListener,
    RemoteServiceAdminEvent,
)

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (0, 1, 0)
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
@Requires("_rsa", SERVICE_REMOTE_SERVICE_ADMIN)
@Requires("_advertisers", SERVICE_ENDPOINT_ADVERTISER, True, True)
class TopologyManager(
    EventListenerHook, RemoteServiceAdminListener, EndpointEventListener, object
):
    def __init__(self):
        self._advertisers = []
        self._context = self._rsa = None

    @Validate
    def _validate(self, context):
        self._context = context

    @Invalidate
    def _invalidate(self, _):
        self._context = None

    def _import_added_endpoint(self, endpoint_description):
        return self._rsa.import_service(endpoint_description)

    def _unimport_removed_endpoint(self, endpoint_description):
        import_regs = self._rsa._get_import_regs()
        for import_reg in import_regs:
            if import_reg.match_ed(endpoint_description):
                import_reg.close()

    def _handle_service_registered(self, service_ref):
        exp_intfs = get_exported_interfaces(service_ref)
        # If no exported interfaces, then all done
        if not exp_intfs:
            return
        self._rsa.export_service(
            service_ref, {SERVICE_EXPORTED_INTERFACES: exp_intfs}
        )

    def _handle_service_unregistering(self, service_ref):
        export_regs = self._rsa._get_export_regs()
        if export_regs:
            for export_reg in export_regs:
                if export_reg.match_sr(service_ref):
                    _logger.debug(
                        "handle_service_unregistering. closing export_registration for service reference="
                        + str(service_ref)
                    )
                    export_reg.close()

    def _handle_service_modified(self, service_ref):
        # XXX TODO
        return

    def _handle_event(self, service_event):
        kind = service_event.get_kind()
        service_ref = service_event.get_service_reference()
        if kind == ServiceEvent.REGISTERED:
            self._handle_service_registered(service_ref)
        elif kind == ServiceEvent.UNREGISTERING:
            self._handle_service_unregistering(service_ref)
        elif kind == ServiceEvent.MODIFIED:
            self._handle_service_modified(service_ref)

    # impl of EventListenerHoook
    def event(self, service_event, listener_dict):
        self._handle_event(service_event)

    def _advertise_endpoint(self, ed):
        for adv in self._advertisers:
            try:
                adv.advertise_endpoint(ed)
            except:
                _logger.exception(
                    "Exception in advertise_endpoint for advertiser={0} endpoint={1}".format(
                        adv, ed
                    )
                )

    def _unadvertise_endpoint(self, ed):
        for adv in self._advertisers:
            try:
                adv.unadvertise_endpoint(ed.get_id())
            except:
                _logger.exception(
                    "Exception in unadvertise_endpoint for advertiser={0} endpoint={1}".format(
                        adv, ed
                    )
                )

    # impl of RemoteServiceAdminListener
    def remote_admin_event(self, event):
        kind = event.get_type()
        if kind == RemoteServiceAdminEvent.EXPORT_REGISTRATION:
            self._advertise_endpoint(event.get_description())
        elif kind == RemoteServiceAdminEvent.EXPORT_UNREGISTRATION:
            self._unadvertise_endpoint(event.get_description())

    def endpoint_changed(self, endpoint_event, matched_filter):
        print(
            "TopologyManager.endpoint_event called.  You probably want to override this method"
        )


# ------------------------------------------------------------------------------
