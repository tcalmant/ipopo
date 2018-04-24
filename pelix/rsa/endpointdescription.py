#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix endpoint description 

:author: Scott Lewis
:copyright: Copyright 2016, Composent, Inc.
:license: Apache License 2.0
:version: 0.1.0

..

    Copyright 2016 Composent, Inc. and others

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
#import threading

# Remote Services constants
import pelix.constants
import pelix.rsa as rsa

# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)
 
# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

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
    def _conditionProperties(cls, properties):
        rsa.set_prop_if_null(rsa.SERVICE_IMPORTED, properties, True)
        for key in properties.keys():
            if key.startswith("services.exported."):
                properties.remove(key)
        return properties;
    
    @classmethod
    def _verifyExportProperties(cls, svc_ref, all_properties):
        props = {}
        props.update(all_properties)
        
        rsa.set_prop_if_null(rsa.ENDPOINT_SERVICE_ID, props, svc_ref.get_property(pelix.constants.SERVICE_ID))
        rsa.set_prop_if_null(rsa.ENDPOINT_FRAMEWORK_UUID,props,svc_ref.get_bundle().get_bundle_context().get_property("framework.uid"))
        
        return props
    
    def __init__(self, svc_ref=None, properties=None):
        if svc_ref is None and properties is None:
            raise ValueError("Both service reference and properties cannot be null")
        
        all_properties = {}
        
        if svc_ref is not None:
            all_properties.update(svc_ref.get_properties())
            
        if properties is not None:
            all_properties.update(properties)
                
        if svc_ref is not None:
            self._properties = EndpointDescription._verifyExportProperties(svc_ref, all_properties)
        else:
            self._properties = all_properties
                
        self._interfaces = list(self._properties.get(pelix.constants.OBJECTCLASS))
        self._serviceId = self._verifyLongProperty(rsa.ENDPOINT_SERVICE_ID)
        self._frameworkUUID = self._verifyStringProperty(rsa.ENDPOINT_FRAMEWORK_UUID)
        endpointId = self._verifyStringProperty(rsa.ENDPOINT_ID)
        if endpointId is None:
            raise ValueError("endpoint.id property must be set")
        self._id = endpointId.strip()
        
        if len(self.get_configuration_types()) == 0:
            raise ValueError("service.imported.configs property must be set and non-empty")
        
        self._ecfid = self._verifyStringProperty(rsa.ECF_ENDPOINT_ID)
        if self._ecfid is None:
            raise ValueError("ecf.endpoint.id must not be null")
        self._timestamp = self._verifyLongProperty(rsa.ECF_ENDPOINT_TIMESTAMP)
        if self._timestamp is 0:
            self._timestamp = self.get_service_id();
        self._idNamespace = self._verifyStringProperty(rsa.ECF_ENDPOINT_CONTAINERID_NAMESPACE)
        self._containerId = (self._idNamespace, self._ecfid)
        self._rsId = self._verifyLongProperty(rsa.ECF_RSVC_ID)
        if self._rsId is None:
            self._rsId = self.get_service_id()
            
        connectTargetName = self._get_prop(rsa.ECF_ENDPOINT_CONNECTTARGET_ID)
        if connectTargetName is not None:
            self._connectTargetId = (self._idNamespace, connectTargetName)
        else:
            self._connectTargetId = None
        
        idFilterNames = self._get_string_plus_property(rsa.ECF_ENDPOINT_IDFILTER_IDS)
        if len(idFilterNames) > 0:
            self._idFilters = [(self._idNamespace, x) for x in idFilterNames]
        else:
            self._idFilters = None
            
        self._rsFilter = self._get_prop(rsa.ECF_ENDPOINT_REMOTESERVICE_FILTER)
    
        self._asyncInterfaces = self._verifyAsyncInterfaces()
        
    def __hash__(self):
        """
        Custom hash, as we override equality tests
        """
        return hash(self._endpointId)

    def __eq__(self, other):
        """
        Equality checked by UID
        """
        return self._endpointId == other._endpointId

    def __ne__(self, other):
        """
        Inequality checked by UID
        """
        return self._endpointId != other._endpointId

    def __str__(self):
        """
        String representation
        """
        return "EndpointDescription(id={0}; endpoint.service.id={1}; " \
               "framework.uuid={2}; ecf.endpoint.id={3})".format(self.get_id(),
                                            self.get_service_id(),
                                            self.get_framework_uuid(),
                                            self.get_container_id())
               
    def _get_prop(self, key, default = None):
        return rsa.get_prop_value(key, self._properties, default)

    def _get_string_plus_property(self, key):
        
        value = self._get_prop(key)
        
        if value is None:
            return []
        elif isinstance(value,type("")):
            return [ value ]
        elif isinstance(value,type([])):
            return value
        elif isinstance(value,type(( 1, 1))):
            return list(value)
        else:
            return []
    
    def _verifyLongProperty(self,propName):
        value = self._get_prop(propName)
        if value is None:
            return int(0)
        return int(value)
    
    
    def _verifyStringProperty(self,propName):
        value = self._get_prop(propName)
        if value is None:
            raise ValueError("prop name="+propName+" must be present in properties")
        return str(value)

    def _convert_intf_to_async(self,intfName):
        asyncProxyName = self._get_prop(rsa.ECF_SERVICE_ASYNC_RSPROXY_CLASS_)
        if asyncProxyName is not None:
            return asyncProxyName
        if intfName.endswith(rsa.ECF_ASYNC_INTERFACE_SUFFIX):
            return intfName
        else:
            return intfName + rsa.ECF_ASYNC_INTERFACE_SUFFIX
        
    def _verifyAsyncInterfaces(self):
        matchingInterfaces = []
        noAsyncProp = self._get_prop(rsa.ECF_SERVICE_EXPORTED_ASYNC_NOPROXY)
        if noAsyncProp is None:
            asyncInterfacesValue = self._get_prop(rsa.ECF_SERVICE_EXPORTED_ASYNC_INTERFACES)
            if asyncInterfacesValue is not None:
                matchingInterfaces = rsa.get_matching_interfaces(self.get_interfaces(), asyncInterfacesValue)
        return [self._convert_intf_to_async(x) for x in matchingInterfaces]
        
    def get_container_id(self):
        return self._containerId
    
    def get_connect_target_id(self):
        return self._connectTargetId
    
    def get_timestamp(self):
        return self._timestamp
    
    def get_remoteservice_id(self):
        return self._rsId
    
    def get_idfilters(self):
        return self._idFilters
    
    def get_remoteservice_filter(self):
        return self._rsFilter
    
    def get_async_interfaces(self):
        return self._asyncInterfaces
    
    def get_framework_uuid(self):
        return self._frameworkUUID
    
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
        return self._get_string_plus_property(rsa.REMOTE_INTENTS_SUPPORTED)

    def get_interfaces(self):
        """
        Provides the list of interfaces implemented by the exported service.

        :return: A list of specifications (list of str)
        """
        return self._interfaces

    def get_configuration_types(self):
        return self._get_string_plus_property(rsa.SERVICE_IMPORTED_CONFIGS)     
    
    def get_service_id(self):
        return self._serviceId;

    def get_package_version(self, package):
        """
        Provides the version of the given package name.

        :param package: The name of the package
        :return: The version of the specified package as a tuple or (0,0,0)
        """
        name = "{0}{1}".format(rsa.ENDPOINT_PACKAGE_VERSION_,
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
        return pelix.ldapfilter.get_ldap_filter(ldap_filter) \
            .matches(self._properties)

    


