#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Discovery Provider APIs

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
from pelix.rsa import get_string_plus_property, get_string_plus_property_value,\
    ECF_ENDPOINT_CONTAINERID_NAMESPACE
_logger = logging.getLogger(__name__)
# ------------------------------------------------------------------------------
# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)
# Documentation strings format
__docformat__ = "restructuredtext en"
# ------------------------------------------------------------------------------# Standard library
from pelix.rsa.endpointdescription import EndpointDescription
from threading import RLock
from pelix.ipopo.decorators import Provides, ComponentFactory, Instantiate,\
    BindField, UnbindField, Requires
#------------------------------------------------------------------------------# Standard library

SERVICE_ENDPOINT_ADVERTISER = 'pelix.rsa.discovery.endpointadvertiser'
SERVICE_ENDPOINT_LISTENER = 'pelix.rsa.discovery.endpointeventlistener'

class EndpointEvent(object):
    
    ADDED = 1
    REMOVED = 2
    MODIFIED = 4
    
    def __init__(self,event_type,endpoint_description):
        assert event_type and isinstance(event_type, int)
        self._type = event_type
        assert endpoint_description and isinstance(endpoint_description,EndpointDescription)
        self._ed = endpoint_description
        
    def get_type(self):
        return self._type
    
    def get_endpoint(self):
        return self._ed

    def __str__(self):
        return 'EndpointEvent(type={0},ed={1})'.format(self.get_type(),self.get_endpoint())
    
class EndpointEventListener(object):
    
    ENDPOINT_LISTENER_SCOPE = 'endpoint.listener.scope'
    
    def endpoint_changed(self,endpoint_event,matched_filter):
        pass

@Requires('_event_listeners',SERVICE_ENDPOINT_LISTENER,True,True)
class EndpointSubscriber():
    
    def __init__(self):
        self._other_sessions = set()
        self._other_sessions_lock = RLock()
        self._endpoint_event_listeners = []
        self._endpoint_event_listeners_lock = RLock()
        self._discovered_endpoints = {}
        self._discovered_endpoints_lock = RLock()

    @BindField('_event_listeners')
    def _add_endpoint_event_listener(self,field,listener,service_ref):
        with self._endpoint_event_listeners_lock:
            self._endpoint_event_listeners.append((listener,service_ref))
            
    @UnbindField('_event_listeners')
    def _remove_endpoint_event_listener(self,field,listener,service_ref):
        with self._endpoint_event_listeners_lock:      
            try:          
                return self._endpoint_event_listeners.remove((listener,service_ref))
            except:
                pass
    
    def _get_matching_endpoint_event_listeners(self,ed):
        result = []
        with self._discovered_endpoints_lock:
            ls = self._endpoint_event_listeners.copy()
        for l in ls:
            svc_ref = l[1]
            filters = get_string_plus_property_value(svc_ref.get_property(EndpointEventListener.ENDPOINT_LISTENER_SCOPE))
            matching_filter = None
            if filters:
                for f in filters:
                    if ed.matches(f):
                        matching_filter = f
                        break
            if matching_filter:
                result.append(l[0])
        return result
            
    def _add_discovered_endpoint(self,ed):
        with self._discovered_endpoints_lock:
            _logger.debug('_add_discovered_endpoint ed={0}'.format(ed))
            self._discovered_endpoints[ed.get_id()] = ed
            
    def _remove_discovered_endpoint(self,endpointid):
        with self._discovered_endpoints_lock:
            return self._discovered_endpoints.pop(endpointid,None)

    def _add_other_session(self,sessionid):
        with self._other_sessions_lock:
            self._other_sessions.add(sessionid)

    def _remove_other_session(self,sessionid):
        with self._other_sessions_lock:
            try:
                return self._other_sessions.remove(sessionid)
            except KeyError:
                pass

    def _fire_endpoint_event(self,event_type,ed):
        listeners = self._get_matching_endpoint_event_listeners(ed)
        if not listeners:
            logging.error('TopologyManager._fire_endpoint_event found no matching listeners for event_type={0} and endpoint={0}'.format(event_type,ed))
            return
        event = EndpointEvent(event_type, ed)   
        for listener in listeners:
            try:
                listener.endpoint_changed(event,'matched')
            except:
                _logger.exception('Exception calling endpoint event listener.endpoint_changed for listener={0} and event={1}'.format(listener,event))
    
class EndpointAdvertiser(object):
    
    def __init__(self):
        self._published_endpoints = {}
        self._published_endpoints_lock = RLock()
        
    def is_advertised(self,endpointid):
        return self.get_advertised(endpointid) != None
    
    def get_advertised_endpoint(self,endpointid):
        with self._published_endpoints_lock:
            return self._published_endpoints.get(endpointid,None)
        
    def get_advertised_endpoints(self):
        with self._published_endpoints_lock:
            return self._published_endpoints.copy()
        
    def _add_advertised(self,ed,advertise_result):
        with self._published_endpoints_lock:
            self._published_endpoints[ed.get_id()] = (ed,advertise_result)
        
    def _remove_advertised(self,endpointid):
        with self._published_endpoints_lock:
            return self._published_endpoints.pop(endpointid,None)
        
    def _advertise(self,endpoint_description):
        raise Exception('Endpoint._advertise must be overridden by subclasses')
    
    def _unadvertise(self,advertised):
        raise Exception('Endpoint._unadvertise must be overridden by subclasses')
    
    def advertise_endpoint(self,endpoint_description):
        endpointid = endpoint_description.get_id()
        with self._published_endpoints_lock:
            if self.get_advertised_endpoint(endpointid) != None:
                return False
            advertise_result = self._advertise(endpoint_description)
            if advertise_result:
                self._add_advertised(endpoint_description, advertise_result)
    
    def unadvertise_endpoint(self,endpointid):
        with self._published_endpoints_lock:
            with self._published_endpoints_lock:
                advertised = self.get_advertised_endpoint(endpointid)
                if not advertised:
                    return None
                unadvertise_result = self._unadvertise(advertised)
                if unadvertise_result:
                    self._remove_advertised(endpointid)

        