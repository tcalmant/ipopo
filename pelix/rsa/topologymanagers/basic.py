#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

BasicTopologyManager implements TopologyManager API

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
from typing import Any, Dict, Optional
from pelix.internals.events import ServiceEvent

from pelix.ipopo.decorators import ComponentFactory, Instantiate

from pelix.rsa import ECF_ENDPOINT_CONTAINERID_NAMESPACE
from pelix.rsa.providers.discovery import EndpointEvent
from pelix.rsa.topologymanagers import TopologyManager
from pelix.framework import BundleContext

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Standard logging
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

BASIC_TOPOLOGY_MANAGER_FACTORY = "basic-topology-manager-factory"
BASIC_TOPOLOGY_MANAGER_NAME = "basic-topology-manager"
BASIC_TOPOLOGY_MANAGER_DEFAULT_PROPS = {TopologyManager.ENDPOINT_LISTENER_SCOPE: f"({ECF_ENDPOINT_CONTAINERID_NAMESPACE}=*)"}


@ComponentFactory(BASIC_TOPOLOGY_MANAGER_FACTORY)
class BasicTopologyManager(TopologyManager):
    """
    BasicTopologyManager extends TopologyManager api
    """

    def event(self, service_event: ServiceEvent[Any], listener_dict: Dict[Any, Any]) -> None:
        """
        Implementation of EventListenerHook.  Called by local
        service registry when a service is registered, unregistered
        or modified.  Will be called by thread doing registration/unregister
        service
        """
        self._handle_event(service_event)

    def endpoint_changed(self, endpoint_event: EndpointEvent, matched_filter: Any) -> None:
        """
        Implementation of discovery API EndpointEventListener.
        Called by discovery provider when an endpoint change
        ADDED,REMOVED,MODIFIED is detected.  May be called
        by arbitrary thread.
        """
        event_type = endpoint_event.get_type()
        ed = endpoint_event.get_endpoint_description()
        ed_id = ed.get_id()

        if event_type == EndpointEvent.ADDED:
            # if it's an add event, we call handle_endpoint_added
            imported_reg = self._import_added_endpoint(ed)
            # get exception from ImportRegistration
            exc = imported_reg.get_exception()
            # if there was exception on import, print out messages
            if exc:
                _logger.error(
                    "BasicTopologyManager import failed for endpoint.id=%s", ed_id)
            else:
                _logger.debug(
                    "BasicTopologyManager: service imported! " "endpoint.id=%s, service_ref=%s",
                    ed_id,
                    imported_reg.get_reference(),
                )
        elif event_type == EndpointEvent.REMOVED:
            self._unimport_removed_endpoint(ed)
            _logger.debug("BasicTopologyManager: endpoint removed. endpoint.id=%s", ed_id)
        elif event_type == EndpointEvent.MODIFIED:
            self._update_imported_endpoint(ed)
            _logger.debug("BasicTopologyManager: endpoint updated. endpoint.id=%s", ed_id)


def instantiate_basic_topology_manager(context: BundleContext, properties: Optional[Dict[str, Any]]=None):
    if not properties:
        properties = BASIC_TOPOLOGY_MANAGER_DEFAULT_PROPS
    from pelix.rsa import instantiate_rsa_component
    return instantiate_rsa_component(context, BASIC_TOPOLOGY_MANAGER_FACTORY, BASIC_TOPOLOGY_MANAGER_NAME, properties)
