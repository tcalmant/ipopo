#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

EndpointDescription class API

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
from pelix.constants import SERVICE_ID, FRAMEWORK_UID, OBJECTCLASS
from pelix.rsa import get_string_plus_property, set_prop_if_null, get_prop_value, get_matching_interfaces, \
    ENDPOINT_SERVICE_ID, SERVICE_IMPORTED, ENDPOINT_FRAMEWORK_UUID, ENDPOINT_ID, ECF_ENDPOINT_ID,\
    ECF_ENDPOINT_TIMESTAMP, ECF_ENDPOINT_CONNECTTARGET_ID, ECF_ENDPOINT_IDFILTER_IDS, ECF_RSVC_ID, \
    ECF_ENDPOINT_CONTAINERID_NAMESPACE, ECF_ENDPOINT_REMOTESERVICE_FILTER, ECF_SERVICE_EXPORTED_ASYNC_INTERFACES, \
    ECF_SERVICE_EXPORTED_ASYNC_NOPROXY, ECF_ASYNC_INTERFACE_SUFFIX, ECF_SERVICE_ASYNC_RSPROXY_CLASS_, \
    ENDPOINT_PACKAGE_VERSION_, REMOTE_INTENTS_SUPPORTED, SERVICE_IMPORTED_CONFIGS
from pelix.ldapfilter import get_ldap_filter
# ------------------------------------------------------------------------------
# EndpointDescription class
# ------------------------------------------------------------------------------
class EndpointDescription(object):
    
    @classmethod
    def fromsvcref(cls,svc_ref):
        return cls(svc_ref,None)
    
    @classmethod
    def fromprops(cls,props):
        return cls(None,props)
    
    @classmethod
    def fromsvcrefprops(cls,svc_ref,props):
        return cls(svc_ref,props)
    
    @classmethod
    def _condition_props(cls, properties):
        set_prop_if_null(SERVICE_IMPORTED, properties, True)
        for key in properties.keys():
            if key.startswith("services.exported."):
                properties.remove(key)
        return properties;
    
    @classmethod
    def _verify_export_props(cls, svc_ref, all_properties):
        props = {}
        props.update(all_properties)
        
        set_prop_if_null(ENDPOINT_SERVICE_ID, props, svc_ref.get_property(SERVICE_ID))
        set_prop_if_null(ENDPOINT_FRAMEWORK_UUID,props,svc_ref.get_property(FRAMEWORK_UID))
        
        return props
    
    def __init__(self, svc_ref=None, properties=None):
        if svc_ref is None and properties is None:
            raise ValueError("Either service reference or properties argument must be non-null")
        
        all_properties = {}
        
        if svc_ref is not None:
            all_properties.update(svc_ref.get_properties())
            
        if properties is not None:
            all_properties.update(properties)
                
        if svc_ref is not None:
            self._properties = EndpointDescription._verify_export_props(svc_ref, all_properties)
        else:
            self._properties = all_properties
                
        self._interfaces = list(self._properties.get(OBJECTCLASS))
        self._service_id = self._verify_long_prop(ENDPOINT_SERVICE_ID)
        self._framework_uuid = self._verify_str_prop(ENDPOINT_FRAMEWORK_UUID)
        endpoint_id = self._verify_str_prop(ENDPOINT_ID)
        if endpoint_id is None:
            raise ValueError("endpoint.id property must be set")
        self._id = endpoint_id.strip()
        
        if len(self.get_configuration_types()) == 0:
            raise ValueError("service.imported.configs property must be set and non-empty")
        
        self._ecfid = self._verify_str_prop(ECF_ENDPOINT_ID)
        if self._ecfid is None:
            raise ValueError("ecf.endpoint.id must not be null")
        self._timestamp = self._verify_long_prop(ECF_ENDPOINT_TIMESTAMP)
        if self._timestamp is 0:
            self._timestamp = self.get_service_id();
        self._id_namespace = self._verify_str_prop(ECF_ENDPOINT_CONTAINERID_NAMESPACE)
        self._container_id = (self._id_namespace, self._ecfid)
        self._rs_id = self._verify_long_prop(ECF_RSVC_ID)
        if self._rs_id is None:
            self._rs_id = self.get_service_id()
            
        connect_target_name = self._get_prop(ECF_ENDPOINT_CONNECTTARGET_ID)
        if connect_target_name is not None:
            self._connect_target_id = (self._id_namespace, connect_target_name)
        else:
            self._connect_target_id = None
        
        id_filter_names = self._get_string_plus_property(ECF_ENDPOINT_IDFILTER_IDS)
        if len(id_filter_names) > 0:
            self._id_filters = [(self._id_namespace, x) for x in id_filter_names]
        else:
            self._id_filters = None
            
        self._rs_filter = self._get_prop(ECF_ENDPOINT_REMOTESERVICE_FILTER)
        self._async_intfs = self._verify_async_intfs()
        
    def __hash__(self):
        return hash(self._endpoint_id)

    def __eq__(self, other):
        return self._endpoint_id == other._endpoint_id

    def __ne__(self, other):
        return self._endpoint_id != other._endpoint_id

    def __str__(self):
        rsid = self.get_remoteservice_id()
        return "EndpointDescription(id={0}; endpoint.service.id={1}; " \
               "framework.uuid={2}; ecf.endpoint.id={3}:{4})".format(self.get_id(),
                                            self.get_service_id(),
                                            self.get_framework_uuid(),
                                            rsid[0],rsid[1])
               
    def _get_prop(self, key, default = None):
        return get_prop_value(key, self._properties, default)

    def _get_string_plus_property(self, key):
        return get_string_plus_property(key,self._properties,[])
    
    def _verify_long_prop(self,prop):
        value = self._get_prop(prop)
        return int(value) if value else int(0)
    
    def _verify_str_prop(self,prop):
        value = self._get_prop(prop)
        if value is None:
            raise ValueError("prop name="+prop+" must be present in properties")
        return str(value)

    def _convert_intf_to_async(self,intf):
        async_proxy_intf = self._get_prop(ECF_SERVICE_ASYNC_RSPROXY_CLASS_)
        if async_proxy_intf is not None:
            return async_proxy_intf
        if intf.endswith(ECF_ASYNC_INTERFACE_SUFFIX):
            return intf
        else:
            return intf + ECF_ASYNC_INTERFACE_SUFFIX
        
    def _verify_async_intfs(self):
        matching = []
        no_async_prop = self._get_prop(ECF_SERVICE_EXPORTED_ASYNC_NOPROXY)
        if no_async_prop is None:
            async_inf_val = self._get_prop(ECF_SERVICE_EXPORTED_ASYNC_INTERFACES)
            if async_inf_val is not None:
                matching = get_matching_interfaces(self.get_interfaces(), async_inf_val)
        return [self._convert_intf_to_async(x) for x in matching]
        
    def get_container_id(self):
        return self._container_id
    
    def get_connect_target_id(self):
        return self._connect_target_id
    
    def get_timestamp(self):
        return self._timestamp
    
    def get_remoteservice_id(self):
        return (self.get_container_id(), self._rs_id)
    
    def get_id_filters(self):
        return self._id_filters
    
    def get_remoteservice_filter(self):
        return self._rs_filter
    
    def get_async_interfaces(self):
        return self._async_intfs
    
    def get_framework_uuid(self):
        return self._framework_uuid
    
    def get_id(self):
        """
        Returns the endpoint's id.
        
        :return: str
        """
        return self._id

    def get_intents(self):
        """
        Returns the list of intents implemented by this endpoint.

        The intents are based on the service.intents on an imported service,
        except for any intents that are additionally provided by the importing
        distribution provider.
        All qualified intents must have been expanded.
        This value of the intents is stored in the
        rsa.SERVICE_INTENTS service property.

        :return: A list of intents (list of str)
        """
        # Return a copy of the list
        return self._get_string_plus_property(REMOTE_INTENTS_SUPPORTED)

    def get_interfaces(self):
        """
        Provides the list of interfaces implemented by the exported service.

        :return: A list of specifications (list of str)
        """
        return self._interfaces

    def get_configuration_types(self):
        return self._get_string_plus_property(SERVICE_IMPORTED_CONFIGS)     
    
    def get_service_id(self):
        return self._service_id;

    def get_package_version(self, package):
        """
        Provides the version of the given package name.

        :param package: The name of the package
        :return: The version of the specified package as a tuple or (0,0,0)
        """
        name = "{0}{1}".format(ENDPOINT_PACKAGE_VERSION_,
                               package)
        try:
            # Get the version string
            version = self._properties[name]
            # Split dots ('.')
            return tuple(version.split('.'))

        except KeyError:
            # No version
            return 0, 0, 0

    def get_properties(self):
        """
        Returns all endpoint properties.

        :return: A copy of the endpoint properties
        """
        return self._properties.copy()

    def is_same_service(self, endpoint):
        """
        Tests if this endpoint and the given one have the same framework UUID
        and service ID

        :param endpoint: Another endpoint
        :return: True if both endpoints represent the same remote service
        """
        return self.get_framework_uuid() == endpoint.get_framework_uuid() \
            and self.get_service_id() == endpoint.get_service_id()

    def matches(self, ldap_filter):
        """
        Tests the properties of this EndpointDescription against the given
        filter

        :param ldap_filter: A filter
        :return: True if properties matches the filter
        """
        return get_ldap_filter(ldap_filter) \
            .matches(self._properties)
