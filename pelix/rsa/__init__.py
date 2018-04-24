#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote service admin package

:author: Scott Lewis
:copyright: Copyright 2015, Composent, Inc.
:license: Apache License 2.0
:version: 0.1.0

..

    Copyright 2015 Composent, Inc. and others

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

# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

import datetime
from pelix import constants
import threading
import uuid
import time
from argparse import ArgumentError

def create_uuid():
    return str(uuid.uuid4())

def create_uuid_uri():
    return "uuid:"+create_uuid()

def time_since_epoch():
    return int(time.time() - 1000)

#----------------------------------------------------------------------------
# RSA constants (declared in org.osgi.service.remoteserviceadmin.RemoteConstants
ENDPOINT_ID = "endpoint.id"
ENDPOINT_SERVICE_ID = "endpoint.service.id"
ENDPOINT_FRAMEWORK_UUID = "endpoint.framework.uuid"
ENDPOINT_PACKAGE_VERSION_ = "endpoint.package.version."
SERVICE_EXPORTED_INTERFACES = "service.exported.interfaces"
REMOTE_CONFIGS_SUPPORTED = "remote.configs.supported"
REMOTE_INTENTS_SUPPORTED = "remote.intents.supported"
SERVICE_EXPORTED_CONFIGS = "service.exported.configs"
SERVICE_EXPORTED_INTENTS = "service.exported.intents"
SERVICE_EXPORTED_INTENTS_EXTRA = "service.exported.intents.extra"
SERVICE_IMPORTED = "service.imported"
SERVICE_IMPORTED_CONFIGS = "service.imported.configs"
SERVICE_INTENTS = "service.intents"
SERVICE_ID = "service.id"
OBJECT_CLASS = "objectClass"
INSTANCE_NAME = "instance.name"
SERVICE_RANKING = 'service.ranking'
SERVICE_COMPONENT_NAME = 'component.name'
SERVICE_COMPONENT_ID = 'component.id'

rsaprops = [ENDPOINT_ID,ENDPOINT_SERVICE_ID,ENDPOINT_FRAMEWORK_UUID,SERVICE_EXPORTED_INTERFACES,REMOTE_CONFIGS_SUPPORTED,REMOTE_INTENTS_SUPPORTED,SERVICE_EXPORTED_CONFIGS,SERVICE_EXPORTED_INTENTS,SERVICE_EXPORTED_INTENTS_EXTRA,SERVICE_IMPORTED,SERVICE_IMPORTED_CONFIGS,SERVICE_INTENTS,SERVICE_ID,OBJECT_CLASS,INSTANCE_NAME,SERVICE_RANKING,SERVICE_COMPONENT_ID,SERVICE_COMPONENT_NAME]

ECF_ENDPOINT_CONTAINERID_NAMESPACE = "ecf.endpoint.id.ns"
ECF_ENDPOINT_ID = "ecf.endpoint.id"
ECF_RSVC_ID = "ecf.rsvc.id"
ECF_ENDPOINT_TIMESTAMP = "ecf.endpoint.ts"
ECF_ENDPOINT_CONNECTTARGET_ID = "ecf.endpoint.connecttarget.id"
ECF_ENDPOINT_IDFILTER_IDS = "ecf.endpoint.idfilter.ids"

ECF_ENDPOINT_REMOTESERVICE_FILTER = "ecf.endpoint.rsfilter"
ECF_SERVICE_EXPORTED_CONTAINER_FACTORY_ARGS = "ecf.exported.containerfactoryargs"
ECF_SERVICE_EXPORTED_CONTAINER_CONNECT_CONTEXT = "ecf.exported.containerconnectcontext"
ECF_SERVICE_EXPORTED_CONTAINER_ID = "ecf.exported.containerid"
ECF_SERVICE_EXPORTED_ASYNC_INTERFACES = "ecf.exported.async.interfaces"
ECF_SERVICE_EXPORTED_ASYNC_NOPROXY = "ecf.rsvc.async.noproxy"
ECF_SERVICE_ASYNC_RSPROXY_CLASS_ = "ecf.rsvc.async.proxy_"
ECF_ASYNC_INTERFACE_SUFFIX = "Async"
ECF_SERVICE_IMPORTED_VALUETYPE = "ecf.service.imported.valuetype"
ECF_SERVICE_IMPORTED_ENDPOINT_ID = ENDPOINT_ID
ECF_SERVICE_IMPORTED_ENDPOINT_SERVICE_ID = ENDPOINT_SERVICE_ID
ECF_OSGI_ENDPOINT_MODIFIED = "ecf.osgi.endpoint.modified"
ECF_OSGI_CONTAINER_ID_NS = "ecf.osgi.ns"

ecfprops = [ECF_ENDPOINT_CONTAINERID_NAMESPACE,ECF_ENDPOINT_ID,ECF_RSVC_ID,ECF_ENDPOINT_TIMESTAMP,ECF_ENDPOINT_CONNECTTARGET_ID,ECF_ENDPOINT_IDFILTER_IDS,ECF_ENDPOINT_REMOTESERVICE_FILTER,ECF_SERVICE_EXPORTED_ASYNC_INTERFACES]
#----------------------------------------------------------------------------------
REMOTE_SERVICE_ADMIN = "pelix.rsa.remoteserviceadmin"
SERVICE_EXPORT_PROVIDER = "pelix.rsa.exportprovider"
SERVICE_IMPORT_PROVIDER = "pelix.rsa.immportprovider"
RSA_EVENT_LISTENER = "pelix.rsa.remoteserviceadmineventlistener"
ENDPOINT_EVENT_LISTENER = 'pelix.rsa.remoteserviceadminendpointeventlistener'
ERROR_EP_ID = '0'
ERROR_NAMESPACE = 'org.eclipse.ecf.core.identity.StringID'
ERROR_IMPORTED_CONFIGS = ['import.error.config']
ERROR_ECF_EP_ID = 'export.error.id'
DEFAULT_EXPORTED_CONFIGS = ['ecf.xmlrpc.server']

def get_fw_uuid(context):
    return context.get_property(constants.FRAMEWORK_UID)

def get_matching_interfaces(origin, propValue):
    if origin is None or propValue is None:
        return None
    if isinstance(propValue,type("")):
        if propValue == '*':
            return origin
    else:
        if isinstance(propValue,type("")) and len(propValue) == 1 and propValue[0] == '*':
            return origin
        else:
            return propValue

def get_prop_value(name, props, default=None): 
    if not props:
        return default
    try:
        return props[name]
    except KeyError:
        return default

def set_prop_if_null(name, props, ifnull):     
    v = get_prop_value(name,props)
    if v is None:
        props[name] = ifnull

def get_string_plus_property_value(value):
    if value:
        if isinstance(value,type("")):
            return [value]
        elif isinstance(value,type([])):
            return value;
        elif isinstance(value,type(tuple())):
            return list(value)
        else:
            return None

def parse_string_plus_value(value):
    return value.split(',')
              
def get_string_plus_property(name, props, default=None):   
    val = get_string_plus_property_value(get_prop_value(name,props,default))
    return default if val is None else val

def get_current_time_millis():
    return int((datetime.datetime.now() - datetime.datetime.utcfromtimestamp(0)).total_seconds() * 1000)

def get_interfaces2(svc_ref,intfValue):
    if intfValue is None:
        return None
    return get_matching_interfaces(svc_ref.get_property(constants.OBJECTCLASS), intfValue)

def get_interfaces1(svc_ref):
    return get_interfaces2(svc_ref,svc_ref.get_property(SERVICE_EXPORTED_INTERFACES))
                           
def get_exported_interfaces(svc_ref, props):
    intfValue = get_prop_value(SERVICE_EXPORTED_INTERFACES, props)
    return get_interfaces2(svc_ref,intfValue) if not intfValue is None else get_interfaces1(svc_ref)

def get_package_from_classname(classname):
    try:
        return classname[:classname.rindex('.')]
    except KeyError:
        return None

def get_package_versions(intfs, props):
    result = []
    for intf in intfs:
        pkgname = get_package_from_classname(intf)
        if pkgname:
            key = ENDPOINT_PACKAGE_VERSION_+pkgname
            val = props[key]
            if val:
                result.append((key,val))
    return result

_next_rsid = 1
_next_rsid_lock = threading.Lock()

def get_next_rsid():
    with _next_rsid_lock:
        global _next_rsid
        n = _next_rsid
        _next_rsid += 1
        return n

def merge_dicts(*dict_args):
    '''
    Given any number of dicts, shallow copy and merge into a new dict,
    precedence goes to key value pairs in latter dicts.
    '''
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result

def get_rsa_props(object_class, exported_cfgs, intents=None, ep_svc_id=None, fw_id=None, pkg_vers=None):
    results = {}
    if not object_class:
        raise ArgumentError('object_class must be an [] of Strings')
    results['objectClass'] = object_class
    if not exported_cfgs:
        raise ArgumentError('rmt_configs must be an array of Strings')
    results[SERVICE_EXPORTED_CONFIGS] = exported_cfgs
    results[SERVICE_IMPORTED_CONFIGS] = exported_cfgs
    if intents:
        results[SERVICE_INTENTS] = intents
    if not ep_svc_id:
        ep_svc_id = get_next_rsid()
    results[ENDPOINT_SERVICE_ID] = ep_svc_id
    results[SERVICE_ID] = ep_svc_id
    if not fw_id:
        fw_id = create_uuid()
    results[ENDPOINT_FRAMEWORK_UUID] = fw_id
    if pkg_vers:
        if isinstance(pkg_vers,type(tuple())):
            pkg_vers = [pkg_vers]
        for pkg_ver in pkg_vers:
            results[pkg_ver[0]] = pkg_ver[1]
    results[ENDPOINT_ID] = create_uuid()
    results[SERVICE_IMPORTED] = 'true'
    results[SERVICE_EXPORTED_INTERFACES] = '*'
    return results

def get_ecf_props(ep_id, ep_id_ns, rsvc_id=None, ep_ts=None):
    results = {}
    if not ep_id:
        raise ArgumentError('ep_id must be a valid endpoint id')
    results[ECF_ENDPOINT_ID] = ep_id
    if not ep_id_ns:
        raise ArgumentError('ep_id_ns must be a valid namespace')
    results[ECF_ENDPOINT_CONTAINERID_NAMESPACE] = ep_id_ns
    if not rsvc_id:
        rsvc_id = get_next_rsid()
    results[ECF_RSVC_ID] = rsvc_id
    if not ep_ts:
        ep_ts = time_since_epoch()
    results[ECF_ENDPOINT_TIMESTAMP] = ep_ts
    results[ECF_SERVICE_EXPORTED_ASYNC_INTERFACES] = '*'
    return results

def get_extra_props(props):
    result = {}
    for key, value in props.items():
        if not key in ecfprops and not key in rsaprops:
            if not key.startswith(ENDPOINT_PACKAGE_VERSION_):
                result[key] = value
    return result

def get_edef_props(object_class, exported_cfgs, ep_namespace, ep_id, ecf_ep_id, ep_rsvc_id, ep_ts, intents, fw_id=None, pkg_ver=None):
    osgi_props = get_rsa_props(object_class, exported_cfgs, intents, ep_rsvc_id, fw_id, pkg_ver)
    ecf_props = get_ecf_props(ecf_ep_id, ep_namespace, ep_rsvc_id, ep_ts)
    return merge_dicts(osgi_props,ecf_props)

def get_edef_props_error(object_class):
    return get_edef_props(object_class, ERROR_IMPORTED_CONFIGS, ERROR_NAMESPACE, ERROR_EP_ID, ERROR_ECF_EP_ID, 0, 0, None, None)

class SelectExporterError(Exception):
    def __init__(self,*args,**kwargs):
        Exception.__init__(self,*args,**kwargs)

class SelectImporterError(Exception):
    def __init__(self,*args,**kwargs):
        Exception.__init__(self,*args,**kwargs)

class RemoteServiceError(Exception):
    def __init__(self,*args,**kwargs):
        Exception.__init__(self,*args,**kwargs)
        
