#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Distribution Provider and Discovery Provider APIs

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
# ------------------------------------------------------------------------------# Standard library
from pelix.ipopo.constants import SERVICE_IPOPO, IPOPO_INSTANCE_NAME, ARG_BUNDLE_CONTEXT,\
    ARG_PROPERTIES
from pelix.ipopo.decorators import Requires, ValidateComponent, Invalidate
from pelix.rsa import DISTRIBUTION_PROVIDER_CONTAINER_PROP, get_dot_properties, SERVICE_INTENTS,\
    merge_dicts, ECF_RSVC_ID, RemoteServiceError,copy_non_reserved,\
    ECF_SERVICE_EXPORTED_ASYNC_INTERFACES,ENDPOINT_ID,SERVICE_ID,\
    SERVICE_IMPORTED, SERVICE_IMPORTED_CONFIGS,REMOTE_CONFIGS_SUPPORTED,\
    SERVICE_BUNDLE_ID,convert_string_plus_value, create_uuid,SERVICE_REMOTE_SERVICE_ADMIN
    
from pelix.constants import OBJECTCLASS, SERVICE_SCOPE, FRAMEWORK_UID
    
import pelix.rsa as rsa    
from threading import RLock
from pelix.rsa.endpointdescription import EndpointDescription
# ------------------------------------------------------------------------------# Standard library
@Requires('_rsa',SERVICE_REMOTE_SERVICE_ADMIN)
@Requires('_ipopo', SERVICE_IPOPO)
class DistributionProvider():
    '''
    Abstract super class for all distribution providers.
    Does not expose and 'public' methods (all methods _)
    that are intended to allow subclasses (e.g. ImportDistributionProvider
    and ExportDistributionProvider to get behavior necessary
    to implement supports_import and supports_export in a manner
    consistent with OSGi RSA requirements.
    
    Note that subclasses should set the following fields to non-None
    values via Property annotations or in __init__:
    
    self._config_name  (string)
    self._namespace  (string)
    self._supported_configs  (list(string))
    self._supported_intents  (list(string))
    
    These two members will be set via Requires class annotations:
    
    self._rsa  (SERVICE_REMOTE_SERVICE_ADMIN instance)
    self._ipopo (SERVICE_IPOPO instance)
    '''
    def __init__(self):
        self._config_name = None
        self._namespace = None
        self._allow_reuse = True
        self._auto_create = True
        self._supported_configs = None
        self._supported_intents = None
        self._rsa = None
        self._ipopo = None

    def get_config_name(self):
        return self._config_name
    
    def get_supported_configs(self):
        return self._supported_configs
    
    def get_supported_intents(self):
        return self._supported_intents
    
    def _get_imported_configs(self,exported_configs):
        ''' 
        Get any imported configs (list) given a set of exported_configs.
        Default implementation simply returns [self._config_name]
        '''
        return [self._config_name]

    def _match_intents_supported(self,intents,supported_intents):
        '''
        Match the list of given intents with given supported_intents.
        This method is used by the other _match methods.
        '''
        if intents == None or not supported_intents:
            return False
        return len([x for x in intents if x in supported_intents]) == len(intents) 
            
    def _match_required_configs(self,required_configs):
        '''
        Match required configs list(string).  
        Default implementation compares required configs with self._supported_configs
        to make sure that all required configs are present for this distribution
        provider.
        '''
        if required_configs == None or not self._supported_configs:
            return False
        return len([x for x in required_configs if x in self._supported_configs]) == len(required_configs) 
        
    def _match_intents(self,intents):
        '''
        Match list(string) of intents against self._supported_intents.
        Default implementation compares intents against self._supported_intents
        '''
        return self._match_intents_supported(intents,self._supported_intents)
    
    def _find_container(self,container_id,container_props):
        '''
        Uses given container_id to get an ipopo instance with name=container_id.
        If instance is returned from ipopo.get_instance(container_id), then
        instance._match_container_props(container_props) is true, then
        the instance is returned, else None
        '''
        try:
            instance = self._ipopo.get_instance(container_id)
            if instance and instance._match_container_props(container_props):
                return instance
        except KeyError:
            return None
    
    def _prepare_container_id(self,container_props):
        '''
        Prepare and return a (string) container id.  This method is called by
        self._get_or_create_container to create an id prior to instantiating
        and instance of the appropriate Container with the instance.name set
        to the container_id returned from this method.
        This method must be overridden by subclasses as the default implementation
        raises an Exception.   If it returns None, then no container will be created.
        '''
        raise Exception('DistributionProvider._prepare_container_id must be implemented by distribution provider')

    def _prepare_container_props(self,service_intents,export_props):
        '''
        Prepare container props (dict).
        Creates dict of props subsequently passed to ipopo.instantiate(factory,container_name,container_props).
        default implementation copies . properties (as per OSGi spec)
        along with service.intents and <intent>. properties.
        Also sets DISTRIBUTION_PROVIDER_CONTAINER_PROP to self.  This 
        is required by Container._get_distribution_provider()
        '''
        container_props = {DISTRIBUTION_PROVIDER_CONTAINER_PROP:self}
        # first get . properties for this config
        container_props.update(get_dot_properties(self._config_name,export_props,True))
        # then add any service intents
        if service_intents != None:
            container_props[SERVICE_INTENTS] = service_intents
            for intent in service_intents:
                container_props = merge_dicts(container_props,get_dot_properties(intent,export_props,False))
        return container_props
    
    def _get_or_create_container(self, required_configs, service_intents, all_props):
        container = None
        if self._match_required_configs(required_configs) and self._match_intents(service_intents):
            container_props = self._prepare_container_props(service_intents,all_props)
            if container_props:
                container_id = self._prepare_container_id(container_props)
                container = self._find_container(container_id,container_props)
                if not container:
                    container = self._ipopo.instantiate(self._config_name, container_id, container_props)
                    assert container.is_valid()
        return container
    
    def _find_import_registration(self,ed):
        if not ed:
            return None
        import_regs = self._rsa._get_import_regs()
        if import_regs:
            for import_reg in import_regs:
                if import_reg.match_ed(ed):
                    return import_reg

    def _handle_import(self,ed):
        return self._rsa.import_service(ed)
   
    def _handle_import_update(self,ed):
        import_reg = self._find_import_registration(ed)
        if import_reg:
            import_ref = import_reg.get_import_reference()
            if import_ref:
                import_ref.update(ed)

    def _handle_import_close(self,ed):
        import_reg = self._find_import_registration(ed)
        if import_reg:
            import_reg.close()

class ExportDistributionProvider(DistributionProvider):      
    '''
    Export distribution provider.  
    
    Implements supports_export, which is called by RSA during export_service
    to give self the ability to provide a container for exporting
    the remote service described by exported_configs, service_intents, and
    export_props.
    
    Note:  Subclasses MUST implement/override _prepare_container_id method
    and return a string to identify the created container instance.
    '''
    def supports_export(self, exported_configs, service_intents, export_props):
        '''
        Method called by rsa.export_service to ask if this ExportDistributionProvider
        supports export for given exported_configs (list), service_intents (list), and
        export_props (dict).
        
        If a ExportContainer instance is returned then it is used to export
        the service.  If None is returned, then this distribution provider will
        not be used to export the service.
        
        The default implementation returns self._get_or_create_container.
        '''
        return self._get_or_create_container(exported_configs, service_intents, export_props)
        
class ImportDistributionProvider(DistributionProvider):
    
    def _prepare_container_id(self,container_props):
        '''
        Default for import containers creates a UUID for the created container.
        '''
        return create_uuid()

    def supports_import(self, exported_configs, service_intents, endpoint_props):
        '''
        Method called by rsa.export_service to ask if this ImportDistributionProvider
        supports import for given exported_configs (list), service_intents (list), and
        export_props (dict).
        
        If a ImportContainer instance is returned then it is used to import
        the service.  If None is returned, then this distribution provider will
        not be used to import the service.
        
        The default implementation returns self._get_or_create_container.
        '''
        return self._get_or_create_container(exported_configs, service_intents, endpoint_props)

class Container():
    
    def __init__(self):
        self._bundle_context = None
        self._container_props = None
        self._rs_instances = {}
        self._rs_instances_lock = RLock()

    def get_id(self):
        return self._container_props.get(IPOPO_INSTANCE_NAME,None)
           
    def is_valid(self):
        assert self._bundle_context
        assert self._container_props != None
        assert self._get_distribution_provider()  
        assert self.get_config_name()
        assert self.get_namespace()
        return True
              
    @ValidateComponent(ARG_BUNDLE_CONTEXT, ARG_PROPERTIES)
    def _validate_component(self, bundle_context, container_props):
        self._bundle_context = bundle_context
        self._container_props = container_props
        self.is_valid()
    
    @Invalidate
    def _invalidate_component(self, bundle_context):
        with self._rs_instances_lock:
            self._rs_instances.clear()

    def _get_bundle_context(self):
        return self._bundle_context
    
    def _add_export(self, get_remoteservice_id, inst):
        with self._rs_instances_lock:
            self._rs_instances[get_remoteservice_id] = inst
            
    def _remove_export(self, get_remoteservice_id):    
        with self._rs_instances_lock:
            return self._rs_instances.pop(get_remoteservice_id,None)
             
    def _get_export(self, get_remoteservice_id):
        with self._rs_instances_lock:
            return self._rs_instances.get(get_remoteservice_id,None)
            
    def _get_distribution_provider(self):
        return self._container_props[DISTRIBUTION_PROVIDER_CONTAINER_PROP]
    
    def get_config_name(self):
        return self._get_distribution_provider()._config_name
    
    def get_namespace(self):
        return self._get_distribution_provider()._namespace
    
    def _match_container_props(self,container_props):
        return True
    
    def get_connected_id(self):
        return None
        
class ExportContainer(Container):
    
    def _get_service_intents(self):
        return self._container_props.get(SERVICE_INTENTS)
     
    def _export_service(self,svc,ed_props):
        self._add_export(ed_props.get(ECF_RSVC_ID), svc)

    def _update_service(self, ed):
        # do nothing by default, subclasses may override
        pass
    
    def _unexport_service(self, ed):
        return self._remove_export(ed.get_properties().get(ECF_RSVC_ID))
    
    def _prepare_endpoint_extra_props(self, export_props):
        return {}
    
    def prepare_endpoint_props(self, intfs, svc_ref, export_props):
        pkg_vers = rsa.get_package_versions(intfs, export_props)
        rsa_props = rsa.get_rsa_props(intfs, [self.get_config_name()], 
                                      self._get_service_intents(), 
                                      svc_ref.get_property(SERVICE_ID), 
                                      svc_ref.get_property(FRAMEWORK_UID), pkg_vers)
        ecf_props = rsa.get_ecf_props(self.get_id(), self.get_namespace(), 
                                      rsa.get_next_rsid(), 
                                      rsa.get_current_time_millis())
        extra_props = rsa.get_extra_props(export_props)
        exporter_props = self._prepare_endpoint_extra_props(export_props)
        merged = rsa.merge_dicts(rsa_props, ecf_props, extra_props, exporter_props)
        # remove service.bundleid
        merged.pop(SERVICE_BUNDLE_ID,None)
        # remove service.scope
        merged.pop(SERVICE_SCOPE,None)
        return merged
    
    def export_service(self, svc_ref, export_props):
        self._export_service(self._get_bundle_context().get_service(svc_ref), export_props.copy())
        return EndpointDescription.fromprops(export_props)

    def update_service(self, ed):
        return self._update_service(ed)

    def unexport_service(self, ed):
        return self._unexport_service(ed)
    
    def _dispatch_exported(self,get_remoteservice_id,method_name,params):
        # first lookup service instance
        service = self._get_export(get_remoteservice_id)
        if not service:
            raise RemoteServiceError('Unknown instance with get_remoteservice_id={0} for method call={1}'.format(str(get_remoteservice_id),method_name))
        # Get the method
        method_ref = getattr(service, method_name, None)
        if method_ref is None:
            raise RemoteServiceError("Unknown method {0}".format(method_name))
        # Call it (let the errors be propagated)
        if isinstance(params, (list, tuple)):
            return method_ref(*params)
        else:
            return method_ref(**params)
        
    def get_connected_id(self):
        return self.get_id()
    
class ImportContainer(Container):
    
    def _get_imported_configs(self,exported_configs):
        dp = self._get_distribution_provider();
        return dp._get_imported_configs(exported_configs)
    
    def _prepare_proxy_props(self, ed):
        result_props = copy_non_reserved(ed.get_properties(),dict())
        # remove these props
        result_props.pop(OBJECTCLASS,None)
        result_props.pop(SERVICE_ID,None)
        result_props.pop(SERVICE_BUNDLE_ID,None)
        result_props.pop(SERVICE_SCOPE,None)
        result_props.pop(IPOPO_INSTANCE_NAME,None)
        intents = convert_string_plus_value(ed.get_intents())
        if intents:
            result_props[SERVICE_INTENTS] = intents
        result_props[SERVICE_IMPORTED] = True
        result_props[SERVICE_IMPORTED_CONFIGS] = self._get_imported_configs(ed.get_remote_configs_supported())      
        result_props[ENDPOINT_ID] = ed.get_id()     
        asyn = ed.get_async_interfaces()
        if asyn and len(asyn) > 0:
            result_props[ECF_SERVICE_EXPORTED_ASYNC_INTERFACES] = asyn                            
        return result_props
        
    def _prepare_proxy(self,ed):
        raise Exception('ImportContainer._prepare_proxy must be implemented by subclass')
    
    def import_service(self, ed):
        proxy = self._prepare_proxy(ed)
        if proxy:
            return self._get_bundle_context().register_service(ed.get_interfaces(),proxy,self._prepare_proxy_props(ed))
    
    def unimport_service(self,ed):
        pass
