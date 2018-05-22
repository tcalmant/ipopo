"""
Pelix remote service admin package

:author: Scott Lewis
:copyright: Copyright 2016, Composent, Inc.
:license: Apache License 2.0
:version: 0.1.0

..

    Copyright 2016 Composent, Inc., Scott Lewis and others.

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
from uuid import uuid4
from pelix.ipopo.constants import SERVICE_IPOPO, IPOPO_INSTANCE_NAME, ARG_BUNDLE_CONTEXT,\
    ARG_PROPERTIES
from pelix.ipopo.decorators import Requires, ValidateComponent, Invalidate
from pelix.rsa import DISTRIBUTION_PROVIDER_CONTAINER_PROP, get_dot_properties, SERVICE_INTENTS,\
    merge_dicts, ECF_RSVC_ID, RemoteServiceError,copy_non_reserved,\
    ECF_SERVICE_EXPORTED_ASYNC_INTERFACES,ENDPOINT_ID,SERVICE_ID,\
    SERVICE_IMPORTED, SERVICE_IMPORTED_CONFIGS,REMOTE_CONFIGS_SUPPORTED,\
    SERVICE_BUNDLE_ID,convert_string_plus_value
    
from pelix.constants import OBJECTCLASS, SERVICE_SCOPE, FRAMEWORK_UID
    
import pelix.rsa as rsa    
from threading import RLock
from pelix.rsa.endpointdescription import EndpointDescription
# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------
_logger = logging.getLogger(__name__)
# ------------------------------------------------------------------------------

@Requires('_ipopo', SERVICE_IPOPO)
class DistributionProvider():
    
    def __init__(self):
        self._config_name = None
        self._namespace = None
        self._allow_reuse = True
        self._auto_create = True
        self._supported_configs = None
        self._supported_intents = None
        self._ipopo = None

    def _prepare_container_id(self,container_props):
        raise Exception('DistributionProvider._prepare_container_id must be implemented by distribution provider')

    def _find_container(self,container_id,container_props):
        try:
            instance = self._ipopo.get_instance(container_id)
            if instance and instance._match_container_props(container_props):
                return instance
        except KeyError:
            return None

    def _match_required_configs(self,configs):
        if not configs or not self._supported_configs:
            return False
        return len([x for x in configs if x in self._supported_configs]) == len(configs) 
        
    def _match_container_props(self,container_props):
        return True
        
    def _match_service_intents(self,intents,all_props):
        if not intents or not self._supported_intents:
            return False
        return len([x for x in intents if x in self._supported_intents]) == len(intents) 
    
    def _prepare_container_props(self,service_intents,export_props):
        container_props = {DISTRIBUTION_PROVIDER_CONTAINER_PROP:self}
        # first get . properties for this config
        container_props.update(get_dot_properties(self._config_name,export_props,True))
        # then add any service intents
        if service_intents:
            container_props[SERVICE_INTENTS] = service_intents
            for intent in service_intents:
                container_props = merge_dicts(container_props,get_dot_properties(intent,export_props,False))
        return container_props
    
    def _get_or_create_container(self, required_configs, service_intents, all_props):
        container = None
        if self._match_required_configs(required_configs) and self._match_service_intents(service_intents, all_props):
            container_props = self._prepare_container_props(service_intents,all_props)
            if container_props:
                container_id = self._prepare_container_id(container_props)
                container = self._find_container(container_id,container_props)
                if not container:
                    container = self._ipopo.instantiate(self._config_name, container_id, container_props)
        return container
            
class ExportDistributionProvider(DistributionProvider):      

    def __init__(self):
        super(ExportDistributionProvider, self).__init__()

    def supports_export(self, exported_configs, service_intents, export_props):
        return self._get_or_create_container(exported_configs, service_intents, export_props)
        
class ImportDistributionProvider(DistributionProvider):
    
    def __init__(self):
        super(ImportDistributionProvider, self).__init__()
        self._supported_configs = None
        
    def _prepare_container_id(self, container_props):
        return str(uuid4())
    
    def _get_imported_configs(self,exported_configs):
        return [self._config_name]
    
    def supports_import(self, exported_configs, service_intents, endpoint_props):
        return self._get_or_create_container(exported_configs, service_intents, endpoint_props)

class Container():
    
    def __init__(self):
        self._id = None
        self._container_props = None
        self._bundle_context = None
        self._rs_instances = {}
        self._rs_instances_lock = RLock()

    @ValidateComponent(ARG_BUNDLE_CONTEXT, ARG_PROPERTIES)
    def _validate_component(self, bundle_context, container_props):
        self._initialize(bundle_context, container_props)
    
    def _initialize(self, bundle_context, container_props):
        self._bundle_context = bundle_context
        self._id = container_props.get(IPOPO_INSTANCE_NAME)
        if not self._id:
            raise Exception('Exception validating component...self._id set to None')
        self._container_props = container_props
        
    def _get_bundle_context(self):
        return self._bundle_context
    
    def get_id(self):
        return self._id
    
    def _add_export(self, rsid, inst):
        with self._rs_instances_lock:
            self._rs_instances[rsid] = inst
            
    def _remove_export(self, rsid):    
        with self._rs_instances_lock:
            return self._rs_instances.pop(rsid)
             
    def _get_export(self, rsid):
        with self._rs_instances_lock:
            return self._rs_instances.get(rsid,None)
            
    def _get_distribution_provider(self):
        return self._container_props[DISTRIBUTION_PROVIDER_CONTAINER_PROP]
    
    def _get_config_name(self):
        return self._get_distribution_provider()._config_name
    
    def _get_namespace(self):
        return self._get_distribution_provider()._namespace
    
    def _match_container_props(self,container_props):
        return True

    @Invalidate
    def _invalidate(self, bundle_context):
        with self._rs_instances_lock:
            self._rs_instances.clear()
        self._bundle_context = None
        self._container_props = None
        
class ExportContainer(Container):
    
    def __init__(self):
        super(ExportContainer, self).__init__()
    
    def _get_service_intents(self):
        return self._container_props.get(SERVICE_INTENTS)
     
    def _export_service(self,svc,ed_props):
        self._add_export(ed_props.get(ECF_RSVC_ID), svc)

    def _update_service(self, ed):
        # do nothing by default, subclasses may override
        pass
    
    def _unexport_service(self, ed):
        self._remove_export(ed.get_remoteservice_id())
    
    def _make_endpoint_extra_props(self, export_props):
        return {}
    
    def prepare_endpoint_props(self, intfs, svc_ref, export_props):
        pkg_vers = rsa.get_package_versions(intfs, export_props)
        rsa_props = rsa.get_rsa_props(intfs, [self._get_config_name()], self._get_service_intents(), svc_ref.get_property(SERVICE_ID), svc_ref.get_property(FRAMEWORK_UID), pkg_vers)
        ecf_props = rsa.get_ecf_props(self.get_id(), self._get_namespace(), rsa.get_next_rsid(), rsa.get_current_time_millis())
        extra_props = rsa.get_extra_props(export_props)
        exporter_props = self._make_endpoint_extra_props(export_props)
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
        assert isinstance(ed, EndpointDescription)
        return self._update_service(ed)

    def unexport_service(self, ed):
        assert isinstance(ed, EndpointDescription)
        return self._unexport_service(ed)
    
    def _dispatch_exported(self,rsid,method_name,params):
        # first lookup service instance
        service = self._get_export(rsid)
        if not service:
            raise RemoteServiceError('Unknown instance with rsid={0} for method call={1}'.format(str(rsid),method_name))
        # Get the method
        method_ref = getattr(service, method_name, None)
        if method_ref is None:
            raise RemoteServiceError("Unknown method {0}".format(method_name))
        # Call it (let the errors be propagated)
        if isinstance(params, (list, tuple)):
            return method_ref(*params)
        else:
            return method_ref(**params)

class ImportContainer(Container):
    
    def __init__(self):
        super(ImportContainer, self).__init__()
    
    def _get_imported_configs(self,exported_configs):
        dp = self._get_distribution_provider();
        return dp._get_imported_configs(exported_configs)
    
    def _prepare_proxy_props(self, ed):
        ed_props = ed.get_properties()
        result_props = copy_non_reserved(ed.get_properties(),dict())
        result_props.pop(OBJECTCLASS,None)
        result_props.pop(SERVICE_ID,None)
        result_props.pop(SERVICE_BUNDLE_ID,None)
        result_props.pop(SERVICE_SCOPE,None)
        intents = convert_string_plus_value(ed.get_intents())
        if intents:
            result_props[SERVICE_INTENTS] = intents
        result_props[SERVICE_IMPORTED] = True
        remote_configs_supported = ed_props.get(REMOTE_CONFIGS_SUPPORTED)
        imported_configs = self._get_imported_configs(remote_configs_supported)
        result_props[SERVICE_IMPORTED_CONFIGS] = imported_configs      
        result_props[ENDPOINT_ID] = ed.get_id()     
        asyn = ed_props.get(ECF_SERVICE_EXPORTED_ASYNC_INTERFACES)
        if asyn:
            result_props[ECF_SERVICE_EXPORTED_ASYNC_INTERFACES] = asyn                            
        return result_props
        
    def _prepare_proxy(self,ed):
        raise Exception('_prepare_proxy must be implemented by ImportContainer subclass')
    
    def unget_service_proxy(self, ed):
        raise NotImplementedError("unget_service_proxy must be implemented by ImportContainer subclass")

    def import_service(self, endpoint_description):
        proxy_props = self._prepare_proxy_props(endpoint_description)
        proxy = self._prepare_proxy(endpoint_description)
        return self._get_bundle_context().register_service(endpoint_description.get_interfaces(),proxy,proxy_props)
