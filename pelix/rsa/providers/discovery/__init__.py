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
from threading import RLock
_logger = logging.getLogger(__name__)
# ------------------------------------------------------------------------------
# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)
# Documentation strings format
__docformat__ = "restructuredtext en"
# ------------------------------------------------------------------------------# Standard library
from pelix.rsa.endpointdescription import EndpointDescription

SERVICE_ENDPOINT_ADVERTISER = 'pelix.rsa.discovery.endpointadvertiser'
SERVICE_ENDPOINT_LISTENER = 'pelix.rsa.discovery.endpointeventlistener'

class EndpointAdvertiser(object):
    
    def advertise_endpoint_description(self,endpoint_description):
        pass
    
    def unadvertise_endpoint_description(self,endpoint_description):
        pass

class EndpointEvent(object):
    
    ADDED = 1
    REMOVED = 2
    MODIFIED = 4
    
    def __init__(self,event_type,endpoint_description):
        assert type and isinstance(event_type, int)
        self._type = type
        assert endpoint_description and isinstance(endpoint_description,EndpointDescription)
        self._ed = endpoint_description
        
    def get_type(self):
        return self._type
    
    def get_endpoint(self):
        return self._ed
    
class EndpointEventListener(object):
    
    ENDPOINT_LISTENER_SCOPE = 'endpoint.listener.scope'
    
    def endpoint_changed(self,endpoint_event,matched_filter):
        pass
    
    
class AdvertiserDiscoveryProvider(EndpointAdvertiser):
    
    def __init__(self):
        self._published_endpoints = {}
        self._lock = RLock()
        
    def is_advertised(self,endpointid):
        return self.get_advertised(endpointid) != None
    
    def get_advertised(self,endpointid):
        with self._lock:
            return self._published_endpoints.get(endpointid,None)
        
    def _add_advertised(self,ed,serialized):
        self._published_endpoints[ed.get_id(),(ed,serialized)]
        
    def _remove_advertised(self,endpointid):
        self._published_endpoints.pop(endpointid,None)
        
    def _serialize_endpoint(self,ed):
        return ed.get_properties()
    
    def _advertise(self,serialized):
        raise Exception('not implemented')
    
    def _unadvertise(self,ed,serialized):
        raise Exception('not implemented')
    
    def advertise_endpoint_description(self,endpoint_description):
        endpointid = endpoint_description.get_id()
        with self._lock:
            if self.get_advertised(endpointid) == None:
                return False
            serialized = self._serialize_endpoint(endpoint_description)
            self._advertise(serialized)
            self._add_advertised(endpoint_description, serialized)
    
    def unadvertise_endpoint_description(self,endpoint_description):
        endpointid = endpoint_description.get_id()
        with self._lock:
            with self._lock:
                advertised = self.get_advertised(endpointid)
                if not advertised:
                    return None
                self._unadvertise(*list(advertised))
                self._remove_advertised(endpointid)
    