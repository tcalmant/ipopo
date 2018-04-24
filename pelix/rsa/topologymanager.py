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

from pelix.remote.edef_io import EDEFReader, EDEFWriter

from pelix.rsa.remoteserviceadmin import EndpointEventListener, EndpointEvent
from pelix.framework import ServiceEvent

import pelix.rsa as rsa
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

    
class AbstractTopologyManager(EndpointEventListener):
    
    def __init__(self):
        self._rsa = None
        self._context = None
        self._self_reg = None
        
    def _validate(self, context):
        self._context = context
        # Prepare the export LDAP filter
        ldapfilter = '(|({0}=*)({1}=*))' \
            .format(rsa.SERVICE_IMPORTED_CONFIGS,
                    rsa.SERVICE_EXPORTED_INTERFACES)
        # Register a service listener, to update the exported services state
        self._reg = self._context.add_service_listener(self, ldapfilter)
    
    def _invalidate(self, context):
        if self._reg:
            self._reg.unregister()
            self._reg = None
        self._context = None
    
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
    
    # impl of EndpointEventListener
    def endpoint_changed(self, ep_event, matched_scope):
        if ep_event.get_type() == EndpointEvent.ADDED:
            self._rsa.import_service(ep_event.get_endpoint())

    