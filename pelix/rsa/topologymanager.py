#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote service admin package

:author: Scott Lewis
:copyright: Copyright 2016, Composent, Inc.
:license: Apache License 2.0
:version: 0.1.0

..

    Copyright 2016 Composent, Inc., Thomas Calmont and others.

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

# Standard library
import logging

from pelix.ipopo.decorators import Validate, Invalidate

from pelix.remote.edef_io import EDEFReader, EDEFWriter

from pelix.rsa.remoteserviceadmin import RemoteServiceAdminListener, EndpointEvent, EndpointEventListener
from pelix.framework import ServiceEvent

from pelix.internals.hooks import EventListenerHook

from threading import RLock
from pelix.rsa import SERVICE_EXPORTED_INTERFACES, SERVICE_EXPORTED_CONFIGS
from pelix.constants import OBJECTCLASS

# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------
_logger = logging.getLogger(__name__)
# ------------------------------------------------------------------------------

class RSACommandHandler(object):
    
    def __init__(self):
        self._eel = None
        self.__edefreader = EDEFReader()
        
    @staticmethod
    def get_namespace():
        """
        Retrieves the name space of this command handler
        """
        return "rsa"

    def get_methods(self):
        """
        Retrieves the list of tuples (command, method) for this command handler
        """
        return [("importedef", self.import_edef)]

    def import_edef(self, io_handler, edeffile):
        eds = self.__edefreader.parse(open(edeffile, 'r').read())
        for ed in eds:
            self._eel.endpoint_changed(EndpointEvent(EndpointEvent.ADDED,ed),None)

class EndpointEventListenerImpl(EndpointEventListener):
    
    def __init__(self,tm_impl):
        self._tmimpl = tm_impl
        
    def endpoint_changed(self, ep_event, matched_scope):
        # XXX todo
        EndpointEventListener.endpoint_changed(self, ep_event, matched_scope)

class TopologyManager(EventListenerHook, RemoteServiceAdminListener, object):
    
    def __init__(self):
        self._matching_filters = list()
        self._context = None
        self._ep_l_reg = None
        self._rsa = None

    @Validate
    def _validate(self, context):
        self._context = context
        fw_uuid = context.get_property('framework.uid')
        
    @Invalidate
    def _invalidate(self, context):
        if self._ep_l_reg:
            self._ep_l_reg.unregister()
            self._ep_l_reg = None
        self._context = None
        self._matching_filters.clear()
    
    def get_endpoint_filters(self):
        return list(self._matching_filters)
    
    def set_endpoint_filters(self,new_filters):
        # xxx todo
        pass

    def _list_from_prop_value(self,value):
        if not value:
            return None
        elif isinstance(value,str):
            return [ value ]
        elif isinstance(value,list):
            return value
        
    def _handle_service_registered(self,service_ref):
        exp_intfs = self._get_exported_interfaces(service_ref)
        # If no exported interfaces, then all done
        if not exp_intfs:
            return
        self._rsa.export_service(service_ref, { SERVICE_EXPORTED_INTERFACES:exp_intfs })
    
    def _handle_service_unregistering(self,service_ref):
        return 
    
    def _handle_service_modified(self,service_ref):
        return
    
    def _get_exported_interfaces(self,service_ref):
        pv = service_ref.get_property(SERVICE_EXPORTED_INTERFACES)
        if not pv:
            return None
        objectClass = service_ref.get_property(OBJECTCLASS)
        # objectClass must be list
        if not objectClass:
            return None
        if '*' == pv:
            return objectClass
        elif isinstance(pv,str):
            return [ pv ]
        elif isinstance(pv,list):
            return pv
        return None
    
    # impl of EventListenerHoook
    def event(self,service_event,listener_dict):
        rsa = self._rsa
        if not rsa:
            return None
        kind = service_event.get_kind()
        service_ref = service_event.get_service_reference()
        if kind == ServiceEvent.REGISTERED:
            self._handle_service_registered(service_ref)
        elif kind == ServiceEvent.UNREGISTERING:
            self._handle_service_unregistering(service_ref)
        elif kind == ServiceEvent.MODIFIED:
            self._handle_service_modified(service_ref)
            
    # impl of RemoteServiceAdminListener
    def remote_admin_event(self, event):
        # XXX todo
        return 
    
    #impl of service listener
    def service_changed(self, event):
        if not self._rsa:
            return None
        """
        Called when a service event is triggered
        """
        kind = event.get_kind()
        svc_ref = event.get_service_reference()

        if kind == ServiceEvent.REGISTERED:
            # Simply export the service
            regs = self._rsa.export_service(svc_ref)
            # test
            reg = regs[0]
            e = reg.exception()
            if e:
                _logger.error(e)
            else:
                ed = reg.description()
                print(str(ed.get_properties()))
                print(EDEFWriter().to_string([ed]))

        elif (kind == ServiceEvent.UNREGISTERING or
                 kind == ServiceEvent.MODIFIED_ENDMATCH):
            # Service is updated or unregistering
            self._rsa._unexport_service(svc_ref)
    

    