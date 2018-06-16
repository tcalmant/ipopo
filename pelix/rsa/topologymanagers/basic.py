#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

BasicTopologyManager implements TopologyManager API

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
# ------------------------------------------------------------------------------
# Standard logging
import logging
_logger = logging.getLogger(__name__)
# ------------------------------------------------------------------------------
# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)
# Documentation strings format
__docformat__ = "restructuredtext en"
# ------------------------------------------------------------------------------
from pelix.rsa import ECF_ENDPOINT_CONTAINERID_NAMESPACE
from pelix.rsa.providers.discovery import EndpointEvent
from pelix.ipopo.decorators import ComponentFactory, Instantiate
from pelix.rsa.topologymanagers import TopologyManager
# ------------------------------------------------------------------------------
@ComponentFactory('basic-topology-manager-factory')
# Tell iPOPO to instantiate a component instance as soon as the file is loaded
@Instantiate('basic-topology-manager', { TopologyManager.ENDPOINT_LISTENER_SCOPE:'('+ECF_ENDPOINT_CONTAINERID_NAMESPACE+'=*)'})
class BasicTopologyManager(TopologyManager):
    '''BasicTopologyManager extends TopologyManager api
    '''
    # Implementation of EventListenerHook.  Called by local
    # service registry when a service is registered, unregistered o
    # or modified.  Will be called by thread doing registration/unregister
    # service
    def event(self,service_event,listener_dict):
        self._handle_event(service_event)

    # implementation of discovery API EndpointEventListener.  
    # Called by discovery provider when an endpoint change 
    # ADDED,REMOVED,MODIFIED is detected.  May be called 
    # by arbitrary thread.
    def endpoint_changed(self,endpoint_event,matched_filter):
        event_type = endpoint_event.get_type()
        ed = endpoint_event.get_endpoint_description()
        ed_id = ed.get_id()
        if event_type == EndpointEvent.ADDED:
            # if it's an add event, we call handle_endpoint_addede
            imported_reg = self._import_added_endpoint(ed)
            # get exception from ImportRegistration
            exc = imported_reg.get_exception()
            # if there was exception on import, print out messages
            if exc:
                print('BasicTopologyManager import failed for endpoint.id={0}'.format(ed_id))
            else:
                print('BasicTopologyManager: service imported! endpoint.id={0},service_ref={1}'.format(ed_id,imported_reg.get_reference()))
        elif event_type == EndpointEvent.REMOVED:
            self._unimport_removed_endpoint(ed)
            print('BasicTopologyManager: endpoint removed.  endpoint.id={0}'.format(ed_id))

    #Implementation of RemoteServiceAdminEventListener.  Called by RSA service when 
    # a remote service event occurs.  See RemoteServiceAdminEventListener class and
    # RemoteServiceAdminEvent classes.
    def remote_admin_event(self, event):
        super(BasicTopologyManager,self).remote_admin_event(event)
        
