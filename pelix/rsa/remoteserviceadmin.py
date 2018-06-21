#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Remote Service Admin API

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
import threading
import sys
from distutils.util import strtobool
from argparse import ArgumentError
from datetime import datetime
from traceback import print_exception

from pelix import constants
from pelix.constants import BundleActivator, SERVICE_RANKING, \
    OBJECTCLASS
from pelix.internals.registry import ServiceReference

from pelix.ipopo.decorators import ComponentFactory, Provides, \
    Instantiate, Validate, Invalidate, Requires, RequiresBest
    
from pelix.rsa import SelectImporterError,\
    validate_exported_interfaces, RemoteServiceAdminEvent,\
    SERVICE_REMOTE_SERVICE_ADMIN, SERVICE_RSA_EVENT_LISTENER,\
    get_exported_interfaces, SERVICE_EXPORTED_INTERFACES, get_edef_props_error,\
    REMOTE_CONFIGS_SUPPORTED, SERVICE_EXPORTED_CONFIGS,\
    SERVICE_INTENTS, SERVICE_EXPORTED_INTENTS, SERVICE_EXPORTED_INTENTS_EXTRA,\
    ECF_ENDPOINT_TIMESTAMP, get_current_time_millis, get_string_plus_property,\
    ExportReference, ExportRegistration, set_append, ImportReference,\
    ImportRegistration, RemoteServiceAdminListener
        
from pelix.rsa.providers.distribution import SERVICE_EXPORT_DISTRIBUTION_PROVIDER,\
    SERVICE_IMPORT_DISTRIBUTION_PROVIDER

from pelix.rsa.endpointdescription import EndpointDescription

from pelix.rsa.edef import EDEFWriter
# Framework property that allows RSA debug to be disabled.  To disable automatic
# output of RSA events, set the property 'pelix.rsa.remoteserviceadmin.debug 
# to some string other than 'true' (the default)
DEBUG_PROPERTY = 'pelix.rsa.remoteserviceadmin.debug'
DEBUG_PROPERTY_DEFAULT = 'true'

# ------------------------------------------------------------------------------
# Bundle activator.  By default, register an instance of RemoteServiceAdminEventListener
# service for debugging.  This can be disabled by setting the DEBUG_PROPERTY
# aka 'pelix.rsa.remoteserviceadmin.debug' to 'false'.
@BundleActivator
class Activator(object):
    def __init__(self):
        self._context = None
        self._debug_reg = None

    def start(self, context):
        self._context = context
        debugstr = self._context.get_property(DEBUG_PROPERTY)
        if not debugstr:
            debugstr = DEBUG_PROPERTY_DEFAULT
        if strtobool(debugstr):
            self._debug_reg = self._context.register_service(SERVICE_RSA_EVENT_LISTENER,DebugRemoteServiceAdminListener(),None)
        
    def stop(self, _):
        if self._debug_reg:
            self._debug_reg.unregister()
            self._debug_reg = None
        self._context = None

# ------------------------------------------------------------------------------
# RSA Impl Export Container Selector service specification and default
# implementation.  The highest priority instance of this service available
# at runtime is used by the RemoteServiceAdmin implementation to select
# export containers to handle a given call to RemoteServiceAdmin.export_service
SERVICE_EXPORT_CONTAINER_SELECTOR = "pelix.rsa.exportcontainerselector"
class ExportContainerSelector():
    '''
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
    '''
    def select_export_containers(self, service_ref, exported_intfs, export_props):
        raise Exception('{0}.select_export_containers is not implemented'.format(self))
    
@ComponentFactory('pelix-rsa-exporterselector-factory')
@Provides(SERVICE_EXPORT_CONTAINER_SELECTOR)
@Requires('_export_distribution_providers', SERVICE_EXPORT_DISTRIBUTION_PROVIDER, True, True)
@Instantiate(SERVICE_EXPORT_CONTAINER_SELECTOR, { SERVICE_RANKING: -1000000000 })
class ExportContainerSelectorImpl(ExportContainerSelector):
    
    def __init__(self):
        self._export_distribution_providers = []
        
    def select_export_containers(self, service_ref, exported_intfs, export_props):
        # get exported configs
        exported_configs = get_string_plus_property(SERVICE_EXPORTED_CONFIGS,export_props,None)
        # get service intents, via service.intents, services.exported.intents, and extra
        service_intents_set = set_append(set(), export_props.get(SERVICE_INTENTS,None))
        service_intents_set = set_append(service_intents_set, export_props.get(SERVICE_EXPORTED_INTENTS,None))
        service_intents_set = set_append(service_intents_set, export_props.get(SERVICE_EXPORTED_INTENTS_EXTRA,None))
        
        export_containers = []
        for export_provider in self._export_distribution_providers:
            export_container = export_provider.supports_export(exported_configs,list(service_intents_set),export_props)
            if export_container:
                export_containers.append(export_container)
                
        return export_containers
    
# ------------------------------------------------------------------------------
# Import Container Selector service specification and default
# implementation.  The highest priority instance of this service available
# at runtime is used by the RemoteServiceAdmin implementation to select
# a single import container to handle a given call to RemoteServiceAdmin.import_service
SERVICE_IMPORT_CONTAINER_SELECTOR = 'pelix.rsa.importcontainerselector'
class ImportContainerSelector():
    '''
    Select import container, given endpoint_description (EndpointDescription).
    Returns a single ImportContainer, or None.
    
    :param EndpointDescription endpoint_description describing endpoint for possible
    import
    :return ImportContainer instance or None
    '''
    def select_import_container(self, remote_configs, endpoint_description):
        raise Exception('{0}.select_import_container is not implemented'.format(self))
# ------------------------------------------------------------------------------    
@ComponentFactory('pelix-rsa-importerselector-factory')
@Provides(SERVICE_IMPORT_CONTAINER_SELECTOR)
@Requires('_import_distribution_providers', SERVICE_IMPORT_DISTRIBUTION_PROVIDER, True, True)
@Instantiate('pelix-rsa-importerselector-impl', { SERVICE_RANKING: -1000000000 })    
class ImportContainerSelectorImpl(ImportContainerSelector):
    
    def __init__(self):
        self._import_distribution_providers = []
        
    def select_import_container(self, remote_configs, endpoint_description):
        for import_provider in self._import_distribution_providers:
            import_container = import_provider.supports_import(remote_configs, endpoint_description.get_intents(), endpoint_description.get_properties())
            if import_container:
                return import_container    
                                  
# ------------------------------------------------------------------------------
# Implementation of RemoteServiceAdmin service
# ------------------------------------------------------------------------------
@ComponentFactory('pelix-rsa-remoteserviceadminimpl-factory')
@Provides(SERVICE_REMOTE_SERVICE_ADMIN)
@RequiresBest('_export_container_selector', SERVICE_EXPORT_CONTAINER_SELECTOR, False)
@RequiresBest('_import_container_selector', SERVICE_IMPORT_CONTAINER_SELECTOR, False)
@Requires('_rsa_event_listeners', SERVICE_RSA_EVENT_LISTENER, True, True)
@Instantiate('pelix-rsa-remoteserviceadminimpl')
class RemoteServiceAdminImpl(object):

    def get_exported_services(self):
        result = []
        for reg in self._get_export_regs():
            exp_ref = reg.get_export_ref()
            if exp_ref:
                result.append(exp_ref)
        return result
    
    def get_imported_endpoints(self):
        result = []
        for reg in self._get_import_regs():
            imp_ref = reg.get_import_ref()
            if imp_ref:
                result.append(imp_ref)
        return result

    def _get_export_regs(self):
        with self._exported_regs_lock:
            return self._exported_regs.copy()
    
    def _get_import_regs(self):
        with self._imported_regs_lock:
            return self._imported_regs.copy()
    
    def export_service(self, service_ref, overriding_props = None):
            if not service_ref:
                raise ArgumentError('service_ref must not be None')
            assert isinstance(service_ref,ServiceReference)
            # get exported interfaces
            exported_intfs = get_exported_interfaces(service_ref, overriding_props)
            # must be set by service_ref or overriding_props or error
            if not exported_intfs:
                raise ArgumentError(SERVICE_EXPORTED_INTERFACES+' must be set in svc_ref properties or overriding_props')
            # If the given exported_interfaces is not valid, then return empty list
            if not validate_exported_interfaces(service_ref.get_property(OBJECTCLASS), exported_intfs):
                return []
            # get export props by overriding service get_reference properties (if overriding_props set)
            export_props = service_ref.get_properties().copy()
            if overriding_props:
                export_props.update(overriding_props)
            
            result_regs = []
            result_events = []
            exporters = None
            error_props = get_edef_props_error(service_ref.get_property(OBJECTCLASS))
            try:
                # get list of exporters from export_container_selector service
                exporters = self._export_container_selector.select_export_containers(service_ref, exported_intfs, export_props)
                # if none returned then report as warning at return empty list
                if not exporters or len(exporters) == 0:
                    _logger.warning('No exporting containers found to export service_ref={0};export_props='.format(service_ref,export_props))
                    return []
            except:
                error_reg = ExportRegistrationImpl.fromexception(sys.exc_info(), EndpointDescription(service_ref, error_props))
                export_event = RemoteServiceAdminEvent.fromexportreg(self._get_bundle(), error_reg)
                result_regs.append(error_reg)
                self._add_exported_service(error_reg)
                result_events.append(export_event)
            # If no errors added to result_regs then we continue
            if len(result_regs) == 0:    
                # get _exported_regs_lock
                with self._exported_regs_lock:
                    # cycle through all exporters
                    for exporter in exporters:
                        found_regs = []
                        # get exporter id
                        exporterid = exporter.get_id()
                        for reg in self._exported_regs:
                            if reg.match_sr(service_ref,exporterid):
                                found_regs.append(reg)
                        #if so then found_regs will be non-empty
                        if len(found_regs) > 0:
                            for found_reg in found_regs:
                                new_reg = ExportRegistrationImpl.fromreg(self, found_reg)
                                self._add_exported_service(new_reg)
                                result_regs.append(new_reg)
                        else:
                            # Here is where export is done
                            export_reg = None
                            export_event = None
                            ed_props = error_props
                            try:
                                # use exporter.make_endpoint_props to make endpoint props, expect dictionary in response
                                ed_props = exporter.prepare_endpoint_props(exported_intfs, service_ref, export_props)
                                # export service and expect and EndpointDescription instance in response
                                export_ed = exporter.export_service(service_ref, ed_props)
                                # if a valid export_ed was returned
                                if export_ed:
                                    export_reg = ExportRegistrationImpl.fromendpoint(self, exporter, export_ed, service_ref)
                                    export_event = RemoteServiceAdminEvent.fromexportreg(self._get_bundle(), export_reg)
                            except Exception as e:
                                export_reg = ExportRegistrationImpl.fromexception(sys.exc_info(), EndpointDescription.fromprops(ed_props))
                                export_event = RemoteServiceAdminEvent.fromexportreg(self._get_bundle(), export_reg)
                        # add exported reg to exported services
                        self._add_exported_service(export_reg)
                        # add to result_regs also
                        result_regs.append(export_reg)
                        # add to result_events
                        result_events.append(export_event)
                #publish events
            for e in result_events:
                self._publish_event(e)    
            return result_regs
            
    def import_service(self, endpoint_description):
        if not endpoint_description:
                raise ArgumentError(None,'endpoint_description param must not be empty')
        assert isinstance(endpoint_description,EndpointDescription)

        remote_configs = get_string_plus_property(REMOTE_CONFIGS_SUPPORTED, endpoint_description.get_properties(), None)
        if not remote_configs:
            raise ArgumentError(None,'endpoint_description must contain {0} property'.format(REMOTE_CONFIGS_SUPPORTED))
        
        import_reg = None
        import_event = None

        try:
            importer = self._import_container_selector.select_import_container(remote_configs, endpoint_description)
            if not importer:
                raise SelectImporterError('Could not find importer for endpoint={0}'.format(endpoint_description))
        except:
            import_reg = ImportRegistrationImpl.fromexception(sys.exc_info(), endpoint_description)
            import_event = RemoteServiceAdminEvent.fromimportreg(self._get_bundle(), import_reg)

        if not import_reg:
            with self._imported_regs_lock:
                found_reg = None
                for reg in self._imported_regs:
                    if reg.match_ed(endpoint_description):
                        found_reg.append(reg)
                if found_reg:
                    new_reg = None
                    #if so then found_regs will be non-empty
                    ex = found_reg.get_exception()
                    if ex:
                        new_reg = ImportRegistrationImpl.fromexception(ex, endpoint_description)
                    else:
                        new_reg = ImportRegistrationImpl.fromreg(self, found_reg)
                    self._add_imported_service(new_reg)
                    return new_reg
                # Here is where new import is done
                try:
                    svc_reg = importer.import_service(endpoint_description)
                    import_reg = ImportRegistrationImpl.fromendpoint(self, importer, endpoint_description, svc_reg)
                    import_event = RemoteServiceAdminEvent.fromimportreg(self._get_bundle(), import_reg)
                except Exception:
                    import_reg = ImportRegistrationImpl.fromexception(sys.exc_info(), endpoint_description)
                    import_event = RemoteServiceAdminEvent.fromimportreg(self._get_bundle(), import_reg)
        self._imported_regs.append(import_reg)
        self._publish_event(import_event)
        return import_reg

    def __init__(self):
        self._context = None
        self._exported_regs = []
        self._exported_regs_lock = threading.RLock()
        self._imported_regs = []
        self._imported_regs_lock = threading.RLock()
        self._rsa_event_listeners = []
        self._export_container_selector = None
        self._import_container_selector = None
             
    def _publish_event(self,event):
        listeners = self._rsa_event_listeners
        if listeners:
            for l in listeners:
                try:
                    l.remote_admin_event(event)
                except:
                    _logger.exception('Exception calling rsa event listener={0}'.format(l))
    
    def _get_bundle(self):
        if self._context:
            return self._context.get_bundle()
        return None

    @Validate
    def _validate(self, context):
        self._context = context
   
    @Invalidate
    def _invalidate(self, context):
        with self._exported_regs_lock:
            for reg in self._exported_regs:
                reg.close()
            self._exported_regs.clear()
        with self._imported_regs_lock:
            for reg in self._imported_regs:
                reg.close()
                self._imported_regs.clear()  
        self._context = None
        
    def _unexport_service(self,svc_ref):
        with self._exported_regs_lock:
            for reg in self._exported_regs:
                if reg.match_sr(svc_ref,None):
                    reg.close()
    
    def _valid_exported_interfaces(self,svc_ref,intfs):    
        if intfs is None or len(intfs) == 0:
            return False
        object_class = svc_ref.get_property(constants.OBJECTCLASS)
        for item in intfs:
            if not item in object_class:
                return False
        return True
    
    def _find_existing_export_endpoint(self, svc_ref, cid):
        for er in self.__exported_registrations:
            if er.match_sr(svc_ref,cid):
                return er
        return None
    
    def _add_exported_service(self,export_reg):
        with self._exported_regs_lock:
            self._exported_regs.append(export_reg)
    
    def _remove_exported_service(self,export_reg):
        with self._exported_regs_lock:
            self._exported_regs.remove(export_reg)

    def _add_imported_service(self,import_reg):
        with self._imported_regs_lock:
            self._imported_regs.append(import_reg)
    
    def _remove_imported_service(self,import_reg):
        with self._imported_regs_lock:
            self._imported_regs.remove(import_reg)

# ------------------------------------------------------------------------------
# Internal class used to implement ExportRegistration/ExportReference below.
class _ExportEndpoint(object):

    def __init__(self, rsa, export_container, ed, svc_ref):
        assert rsa
        self.__rsa = rsa
        assert export_container
        self.__export_container = export_container
        assert ed
        self.__ed = ed
        assert svc_ref
        self.__svc_ref = svc_ref
        self.__lock = threading.RLock()
        self.__active_registrations = []
        self.__orig_props = self.__ed.get_properties()
        
    def _rsa(self):
        with self.__lock:
            return self.__rsa
    
    def _originalprops(self):
        with self.__lock:
            return self.get_reference().get_properties()
        
    def _add_export_registration(self, export_reg):
        with self.__lock:
            self.__active_registrations.append(export_reg)
    
    def _remove_export_registration(self, export_reg):
        with self.__lock:
            self.__active_registrations.remove(export_reg) 
                   
    def get_description(self):
        with self.__lock:
            return self.__ed
        
    def get_reference(self):
        with self.__lock:
            return self.__svc_ref
    
    def get_export_container_id(self):
        with self.__lock:
            return self.__export_container.get_id()
    
    def get_remoteservice_id(self):
        with self.__lock:
            return self.__ed.get_remoteservice_id()
    
    def update(self, props):
        with self.__lock:
            srprops = self.get_reference.get_properties().copy()
            rsprops = self.__orig_props.copy()
            updateprops = rsprops if props is None else props.update(rsprops).copy()
            updatedprops = updateprops.update(srprops).copy()
            updatedprops[ECF_ENDPOINT_TIMESTAMP] = get_current_time_millis()
            self.__ed = EndpointDescription(updatedprops)
            return self.__ed

    def close(self, export_reg):
        with self.__lock:
            try:
                self.__active_registrations.remove(export_reg)
            except ValueError:
                pass
            if len(self.__active_registrations) is 0:
                try:
                    self.__export_container.unexport_service(self.__ed)
                except:
                    _logger.exception('get_exception in exporter.unexport_service ed={0}'.format(self.__ed))
                self.__rsa._remove_exported_service(export_reg)
                self.__ed = self.__export_container = self.__svc_ref = self.__rsa = None
                return True
        return False

# ------------------------------------------------------------------------------
# Implementation of ExportReference API.  See ExportReference class for external
# contract and documentation
class ExportReferenceImpl(ExportReference):
    
    @classmethod
    def fromendpoint(cls,endpoint):
        return cls(endpoint=endpoint)
    
    @classmethod
    def fromexception(cls,e,ed):
        return cls(endpoint=None,exception=e,errored=ed)
    
    def __init__(self,endpoint=None,exception=None,errored=None):
        self.__lock = threading.RLock()
        if endpoint is None:
            if exception is None or errored is None:
                raise ArgumentError('Must supply either endpoint or throwable/errorEndpointDescription')
            self.__exception = exception
            self.__errored = errored
            self.__endpoint = None
        else:
            self.__endpoint = endpoint
            self.__exception = self.__errored = None
    
    def get_export_container_id(self):
        with self.__lock:
            return None if self.__endpoint is None else self.__endpoint.get_export_container_id()
    
    def get_remoteservice_id(self):
        with self.__lock:
            return None if self.__endpoint is None else self.__endpoint.get_remoteservice_id()
        
    def get_reference(self):
        with self.__lock:
            return None if self.__endpoint is None else self.__endpoint.get_reference()
    
    def get_description(self):
        with self.__lock:
            return self.__errored if self.__endpoint is None else self.__endpoint.get_description()
    
    def get_exception(self):
        with self.__lock:
            return self.__exception

    def update(self,properties):
        with self.__lock:
            return None if self.__endpoint is None else self.__endpoint.update(properties)
        
    def close(self,export_reg):
        with self.__lock:
            if self.__endpoint is None:
                return False
            else:
                result = self.__endpoint.close(export_reg)
                self.__endpoint = None
                return result != None
            
# ------------------------------------------------------------------------------
# Implementation of ExportRegistration API.  See ExportRegistration class for external
# contract and documentation
class ExportRegistrationImpl(ExportRegistration):

    @classmethod
    def fromreg(cls, export_reg):
        return cls(export_reg.__rsa,export_reg.__export_ref.__endpoint)
    
    @classmethod
    def fromendpoint(cls, rsa, exporter, ed, svc_ref):
        return cls(rsa,_ExportEndpoint(rsa, exporter, ed, svc_ref))
    
    @classmethod
    def fromexception(cls,e,ed):
        return cls(rsa=None,endpoint=None,exception=e,errored=ed)
    
    def __init__(self,rsa=None,endpoint=None,exception=None,errored=None):
        if endpoint is None:
            if exception is None or errored is None:
                raise ArgumentError('export endpoint or get_exception/errorED must not be null')
            self.__exportref = ExportReferenceImpl.fromexception(exception, errored)
            self.__rsa = None
        else:
            self.__rsa = endpoint._rsa()
            endpoint._add_export_registration(self)   
            self.__exportref = ExportReferenceImpl.fromendpoint(endpoint)
        self.__closed = False
        self.__updateexception = None
        self.__lock = threading.RLock()
        
    def match_sr(self,sr,cid=None):
        with self.__lock:
            oursr = self.get_reference()
            if oursr is None:
                return False
            srcompare = oursr == sr
            if cid is None:
                return srcompare
            ourcid = self.get_export_container_id()
            if ourcid is None:
                return False
            return srcompare and ourcid == cid
    
    def get_export_reference(self):
        with self.__lock:
            return None if self.__closed else self.__exportref

    def _exportendpoint(self,sr,cid):
        with self.__lock:
            return None if self.__closed else self.__exportref.__endpoint if self.match_sr(sr,cid) else None

    def get_export_container_id(self):
        with self.__lock:
            return None if self.__closed else self.__exportref.get_export_container_id()

    def get_remoteservice_id(self):
        with self.__lock:
            return None if self.__closed else self.__exportref.get_remoteservice_id()
        
    def get_reference(self):
        with self.__lock:
            return None if self.__closed else self.__exportref.get_reference()
    
    def get_exception(self):
        with self.__lock:
            return self.__updateexception if self.__closed else self.__exportref.get_exception()
    
    def get_description(self):
        with self.__lock:
            return None if self.__closed else self.__exportref.get_description()
    
    def close(self):
        publish = False
        exporterid = rsid = exception = export_ref = ed = None
        with self.__lock:
            if not self.__closed:
                exporterid = self.__exportref.get_export_container_id()
                export_ref = self.__exportref
                rsid = self.__exportref.get_remoteservice_id()
                ed = self.__exportref.get_description()
                exception = self.__exportref.get_exception()
                publish = self.__exportref.close(self)
                self.__exportref = None
                self.__closed = True
        if publish and export_ref and self.__rsa:
            self.__rsa._publish_event(RemoteServiceAdminEvent.fromexportunreg(self.__rsa._get_bundle(), exporterid, 
                                                                              rsid, export_ref, exception, ed))
            self.__rsa = None

class _ImportEndpoint(object):
    
    def __init__(self, rsa, import_container, ed, svc_reg):
        assert rsa
        self.__rsa = rsa
        assert import_container
        self.__importer = import_container
        assert ed
        self.__ed = ed
        assert svc_reg
        self.__svc_reg = svc_reg
        self.__lock = threading.RLock()
        self.__active_registrations = []
    
    def _add_import_registration(self, import_reg):
        with self.__lock:
            self.__active_registrations.append(import_reg)

    def _rsa(self):
        return self.__rsa
        
    def match_ed(self,ed):
        with self.__lock:
            if len(self.__active_registrations) is 0:
                return False
            return self.__ed.is_same_service(ed)
        
    def get_reference(self):
        with self.__lock:
            return None if self.__importer is None else self.__svc_reg.get_reference()
        
    def get_description(self):
        with self.__lock:
            return self.__ed
        
    def get_import_container_id(self):
        with self.__lock:
            return None if self.__importer is None else self.__importer.get_id()

    def get_export_container_id(self):
        with self.__lock:
            return self.__ed.get_container_id()
        
    def get_remoteservice_id(self):
        with self.__lock:
            return self.__ed.get_remoteservice_id()

    def update(self, ed):
        with self.__lock:
            if self.__svc_reg is None:
                return None
            new_props = self.__importer._prepare_proxy_props(ed)
            ed.update(new_props.get_properties())
            self.__ed = ed
            self.__svc_reg.set_properties(self.__ed.get_properties())

    def close(self, import_reg):
        with self.__lock:
            try:
                self.__active_registrations.remove(import_reg)
            except ValueError:
                pass
            if len(self.__active_registrations) is 0:
                if self.__svc_reg:
                    try:
                        self.__svc_reg.unregister()
                    except:
                        _logger.exception('Exception unregistering local proxy={0}'.format(self.__svc_reg.get_reference()))
                    self.__svc_reg = None
                try:
                    self.__importer.unimport_service(self.__ed)
                except:
                    _logger.exception('Exception calling importer.unimport_service with ed={0}'.format(self.__ed))
                    return False
                self.__rsa._remove_imported_service(import_reg)
                self.__importer = self.__ed = self.__rsa = None
                return True
        return False        

# ------------------------------------------------------------------------------
# Implementation of ExportReference API.  See ExportReference class for external
# contract and documentation
class ImportReferenceImpl(ImportReference):
    
    @classmethod
    def fromendpoint(cls,endpoint):
        return cls(endpoint=endpoint)
    
    @classmethod
    def fromexception(cls,e,errored):
        return cls(endpoint=None,exception=e,errored=errored)

    def __init__(self,endpoint=None,exception=None,errored=None):
        self.__lock = threading.RLock()
        if endpoint is None:
            if exception is None or errored is None:
                raise ArgumentError('Must supply either endpoint or throwable/errorEndpointDescription')
            self.__exception = exception
            self.__errored = errored
            self.__endpoint = None
        else:
            self.__endpoint = endpoint
            self.__exception = self.__errored = None
        
    def _importendpoint(self):
        with self.__lock:
            return self.__endpoint
        
    def match_ed(self,ed):
        with self.__lock:
            return None if self.__endpoint is None else self.__endpoint.match_ed(ed)

    def get_import_container_id(self):
        with self.__lock:
            return None if self.__endpoint is None else self.__endpoint.get_import_container_id()

    def get_export_container_id(self):
        with self.__lock:
            return None if self.__endpoint is None else self.__endpoint.get_export_container_id()
        
    def get_remoteservice_id(self):
        with self.__lock:
            return None if self.__endpoint is None else self.__endpoint.get_remoteservice_id()
    
    def get_reference(self):
        with self.__lock:
            return None if self.__endpoint is None else self.__endpoint.get_reference()
    
    def get_description(self):
        with self.__lock:
            return self.__errored if self.__endpoint is None else self.__endpoint.get_description()
    
    def get_exception(self):
        with self.__lock:
            return self.__exception
    
    def update(self,ed):
        with self.__lock:
            return None if self.__endpoint is None else self.__endpoint.update(ed)
        
    def close(self,import_reg):
        with self.__lock:
            if self.__endpoint is None:
                return False
            else:
                result = self.__endpoint.close(import_reg)
                self.__endpoint = None
                return result
        
# ------------------------------------------------------------------------------
# Implementation of ExportRegistration API.  See ExportRegistration class for external
# contract and documentation
class ImportRegistrationImpl(ImportRegistration):

    @classmethod
    def fromendpoint(cls,rsa,importer,ed,svc_reg):
        return cls(endpoint=_ImportEndpoint(rsa,importer,ed,svc_reg))
    
    @classmethod
    def fromexception(cls,e,ed):
        return cls(endpoint=None,exception=e,errored=ed)
    
    @classmethod
    def fromreg(cls,reg):
        return cls(endpoint=reg._importendpoint())
    
    def __init__(self,endpoint=None,exception=None,errored=None):
        if endpoint is None:
            if exception is None or errored is None:
                raise ArgumentError('export endpoint or get_exception/errorED must not be null')
            self.__importref = ImportReferenceImpl.fromexception(exception, errored)
            self.__rsa = None
        else:
            self.__rsa = endpoint._rsa()
            endpoint._add_import_registration(self)   
            self.__importref = ImportReferenceImpl.fromendpoint(endpoint)
        self.__closed = False
        self.__lock = threading.RLock()
    
    def _import_endpoint(self):
        with self.__lock:
            return None if self.__closed else self.__importref._importendpoint()
         
    def match_ed(self,ed):
        with self.__lock:
            return False if self.__closed else self.__importref.match_ed(ed)

    def get_import_reference(self):
        with self.__lock:
            return None if self.__closed else self.__importref

    def get_import_container_id(self):
        with self.__lock:
            return None if self.__closed else self.__importref.get_import_container_id()

    def get_export_container_id(self):
        with self.__lock:
            return None if self.__closed else self.__importref.get_export_container_id()

    def get_remoteservice_id(self):
        with self.__lock:
            return None if self.__closed is None else self.__importref.get_remoteservice_id()
        
    def get_reference(self):
        with self.__lock:
            return None if self.__closed else self.__importref.get_reference()
    
    def get_exception(self):
        with self.__lock:
            return None if self.__closed else self.__importref.get_exception()
    
    def get_description(self):
        with self.__lock:
            return None if self.__closed else self.__importref.get_description()
    
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
                publish = self.__importref.close(self)
                self.__importref = None
                self.__closed = True
        if publish and import_ref and self.__rsa:
            self.__rsa._publish_event(RemoteServiceAdminEvent.fromimportunreg(self.__rsa._get_bundle(), 
                                     importerid, rsid, import_ref, exception, ed))
            self.__rsa = None             
# ------------------------------------------------------------------------------
#----------------------------------------------------------------------------------    
# Implementation of RemoteServiceAdminListener that supports debugging by printing
# out information about the RemoteServiceAdminEvents.
class DebugRemoteServiceAdminListener(RemoteServiceAdminListener):

    EXPORT_MASK = RemoteServiceAdminEvent.EXPORT_ERROR\
        | RemoteServiceAdminEvent.EXPORT_REGISTRATION\
        | RemoteServiceAdminEvent.EXPORT_UNREGISTRATION\
        | RemoteServiceAdminEvent.EXPORT_WARNING
            
    IMPORT_MASK = RemoteServiceAdminEvent.IMPORT_ERROR\
        | RemoteServiceAdminEvent.IMPORT_REGISTRATION\
        | RemoteServiceAdminEvent.IMPORT_UNREGISTRATION\
        | RemoteServiceAdminEvent.IMPORT_WARNING
            
    ALL_MASK = EXPORT_MASK | IMPORT_MASK

    def __init__(self,file=sys.stdout,event_mask=ALL_MASK,write_endpoint=True,ed_encoding='unicode',xml_declaration=True):
        self._output = file
        self._writer = EDEFWriter(ed_encoding, xml_declaration)
        self._event_mask = event_mask
        self._write_endpoint = write_endpoint
        self._eventtypestr = { RemoteServiceAdminEvent.EXPORT_ERROR:'EXPORT_ERROR',RemoteServiceAdminEvent.EXPORT_REGISTRATION:'EXPORT_REGISTRATION',\
                          RemoteServiceAdminEvent.EXPORT_UNREGISTRATION:'EXPORT_UNREGISTRATION',RemoteServiceAdminEvent.EXPORT_UPDATE:'EXPORT_UPDATE',\
                          RemoteServiceAdminEvent.EXPORT_WARNING:'EXPORT_WARNING',RemoteServiceAdminEvent.IMPORT_ERROR:'IMPORT_ERROR',\
                          RemoteServiceAdminEvent.IMPORT_REGISTRATION:'IMPORT_REGISTRATION',RemoteServiceAdminEvent.IMPORT_UNREGISTRATION:'IMPORT_UNREGISTRATION',\
                          RemoteServiceAdminEvent.IMPORT_UPDATE:'IMPORT_UPDATE',RemoteServiceAdminEvent.IMPORT_WARNING:'IMPORT_WARNING' }
        self._exporttypes = [RemoteServiceAdminEvent.EXPORT_REGISTRATION,RemoteServiceAdminEvent.EXPORT_UNREGISTRATION,\
                             RemoteServiceAdminEvent.EXPORT_UPDATE,RemoteServiceAdminEvent.EXPORT_WARNING]
        self._importtypes = [RemoteServiceAdminEvent.IMPORT_REGISTRATION,RemoteServiceAdminEvent.IMPORT_UNREGISTRATION,\
                             RemoteServiceAdminEvent.IMPORT_UPDATE,RemoteServiceAdminEvent.IMPORT_WARNING]
        self._errortypes = [RemoteServiceAdminEvent.EXPORT_ERROR,RemoteServiceAdminEvent.IMPORT_ERROR]
    
    def write_description(self,ed):
        if self._write_endpoint and ed:
            self._output.write('---Endpoint Description---\n')
            self._output.write(self._writer.to_string([ed]))
            self._output.write('\n---End Endpoint Description---\n')
            self._output.flush()

    def write_ref(self,svc_ref,cid,rsid,ed):
        if svc_ref:
            self._output.write(str(svc_ref)+';')
        self._output.write('local='+str(cid))
        # get_remoteservice_id should be of form:  ((ns,cid,get_remoteservice_id)
        self._output.write(';remote=')
        if isinstance(rsid,tuple) and len(list(rsid)) == 2:
            nscid = rsid[0]
            if isinstance(nscid,tuple) and len(list(nscid)) == 2:
                self._output.write(str(nscid[1])+':'+str(rsid[1]))
        else:
            self._output.write(str(rsid))
        self._output.write('\n')
        self._output.flush()
        self.write_description(ed)
    
    def write_exception(self,exception):
        self._output.write('---Exception Stack---\n')
        print_exception(exception[0],exception[1],exception[2],limit=None, file=self._output)   
        self._output.write('---End Exception Stack---\n')

    def write_type(self,event_type):
        (dt, micro) = datetime.now().strftime('%H:%M:%S.%f').split('.')
        dt = "%s.%03d" % (dt, int(micro) / 1000)
        self._output.write(dt+';'+self._eventtypestr.get(event_type,'UNKNOWN')+';')

    def write_event(self,rsa_event):
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
        self.write_ref(svc_ref,rsa_event.get_container_id(),rsa_event.get_remoteservice_id(),rsa_event.get_description())
        if exception:
            self.write_exception(exception)
                
    def remote_admin_event(self, event):
        self.write_event(event)

