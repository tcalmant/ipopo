#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

RemoteServiceAdmin constants and utility functions

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0

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
SERVICE_BUNDLE_ID = 'service.bundleid'
INSTANCE_NAME = "instance.name"
SERVICE_RANKING = 'service.ranking'
SERVICE_COMPONENT_NAME = 'component.name'
SERVICE_COMPONENT_ID = 'component.id'
# List of them
RSA_PROP_NAMES = [ENDPOINT_ID,ENDPOINT_SERVICE_ID,ENDPOINT_FRAMEWORK_UUID,SERVICE_EXPORTED_INTERFACES,REMOTE_CONFIGS_SUPPORTED,REMOTE_INTENTS_SUPPORTED,SERVICE_EXPORTED_CONFIGS,SERVICE_EXPORTED_INTENTS,SERVICE_EXPORTED_INTENTS_EXTRA,SERVICE_IMPORTED,SERVICE_IMPORTED_CONFIGS,SERVICE_INTENTS,SERVICE_ID,OBJECT_CLASS,INSTANCE_NAME,SERVICE_RANKING,SERVICE_COMPONENT_ID,SERVICE_COMPONENT_NAME]
# ECF constants
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
# List
ECFPROPNAMES = [ECF_ENDPOINT_CONTAINERID_NAMESPACE,ECF_ENDPOINT_ID,ECF_RSVC_ID,ECF_ENDPOINT_TIMESTAMP,ECF_ENDPOINT_CONNECTTARGET_ID,ECF_ENDPOINT_IDFILTER_IDS,ECF_ENDPOINT_REMOTESERVICE_FILTER,ECF_SERVICE_EXPORTED_ASYNC_INTERFACES,ECF_SERVICE_IMPORTED_VALUETYPE]
#----------------------------------------------------------------------------------
SERVICE_REMOTE_SERVICE_ADMIN = "pelix.rsa.remoteserviceadmin"
SERVICE_EXPORT_DISTRIBUTION_PROVIDER = "pelix.rsa.exportdistributionprovider"
SERVICE_IMPORT_DISTRIBUTION_PROVIDER = "pelix.rsa.importdistributionprovider"
SERVICE_EXPORT_CONTAINER = "pelix.rsa.exportcontainer"
SERVICE_IMPORT_CONTAINER = "pelix.rsa.importcontainer"
SERVICE_RSA_EVENT_LISTENER = "pelix.rsa.remoteserviceadmineventlistener"
SERVICE_ENDPOINT_EVENT_LISTENER = 'pelix.rsa.remoteserviceadminendpointeventlistener'
SERVICE_EXPORT_CONTAINER_SELECTOR = "pelix.rsa.exportcontainerselector"
SERVICE_IMPORT_CONTAINER_SELECTOR = 'pelix.rsa.importcontainerselector'
DISTRIBUTION_PROVIDER_CONTAINER_PROP = "pelix.rsa.distributionprovider"
ERROR_EP_ID = '0'
ERROR_NAMESPACE = 'org.eclipse.ecf.core.identity.StringID'
ERROR_IMPORTED_CONFIGS = ['import.error.config']
ERROR_ECF_EP_ID = 'export.error.id'
DEFAULT_EXPORTED_CONFIGS = ['ecf.xmlrpc.server']

def get_fw_uuid(context):
    return context.get_property(constants.OSGI_FRAMEWORK_UUID)

def get_matching_interfaces(object_class, exported_intfs):
    if object_class is None or exported_intfs is None:
        return None
    if isinstance(exported_intfs,str) and exported_intfs == '*':
        return object_class
    else:
        # after this exported_intfs will be list
        exported_intfs = get_string_plus_property_value(exported_intfs)
        if len(exported_intfs) == 1 and exported_intfs[0] == '*':
            return object_class
        else:
            return exported_intfs

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
        if isinstance(value,str):
            return [value]
        elif isinstance(value,list):
            return value;
        elif isinstance(value,tuple):
            return list(value)
        else:
            return None

def convert_string_plus_value(values):
    if not values:
        return None
    size = len(values)
    if size == 0:
        return None
    elif size == 1:
        return values[1]
    else:
        return values

def parse_string_plus_value(value):
    return value.split(',')
              
def get_string_plus_property(name, props, default=None):   
    val = get_string_plus_property_value(get_prop_value(name,props,default))
    return default if val is None else val

def get_current_time_millis():
    return int((datetime.datetime.now() - datetime.datetime.utcfromtimestamp(0)).total_seconds() * 1000)

def get_exported_interfaces(svc_ref, overriding_props = None):
    # first check overriding_props for service.exported.interfaces
    exported_intfs = get_prop_value(SERVICE_EXPORTED_INTERFACES, overriding_props)
    # then check svc_ref property
    if not exported_intfs:
        exported_intfs = svc_ref.get_property(SERVICE_EXPORTED_INTERFACES)
    if not exported_intfs:
        return None
    return get_matching_interfaces(svc_ref.get_property(constants.OBJECTCLASS), exported_intfs)

def validate_exported_interfaces(object_class, exported_intfs):
    if not exported_intfs or not isinstance(exported_intfs,list) or len(exported_intfs) == 0:
        return False
    else:
        for exintf in exported_intfs:
            if not exintf in object_class:
                return False
    return True

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
            val = props.get(key,None)
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

def copy_ref_props(service_ref):
    keys = service_ref.get_property_keys()
    result = dict()
    for key in keys:
        result[key] = service_ref.get_property(key)
    return result

def merge_dicts(*dict_args):
    '''
    Given any number of dicts, shallow copy and merge into a new dict,
    precedence goes to key value pairs in latter dicts.
    '''
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result

def merge_overriding_props(service_ref,overriding_props):
    ref_props = copy_ref_props(service_ref)
    return merge_dicts(ref_props, overriding_props)

def get_rsa_props(object_class, exported_cfgs, intents=None, ep_svc_id=None, fw_id=None, pkg_vers=None):
    results = {}
    if not object_class:
        raise ArgumentError('object_class must be an [] of Strings')
    results['objectClass'] = object_class
    if not exported_cfgs:
        raise ArgumentError('rmt_configs must be an array of Strings')
    results[REMOTE_CONFIGS_SUPPORTED] = exported_cfgs
    results[SERVICE_IMPORTED_CONFIGS] = exported_cfgs
    if intents:
        results[REMOTE_INTENTS_SUPPORTED] = intents
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
        if not key in ECFPROPNAMES and not key in RSA_PROP_NAMES:
            if not key.startswith(ENDPOINT_PACKAGE_VERSION_):
                result[key] = value
    return result

def get_edef_props(object_class, exported_cfgs, ep_namespace, ep_id, ecf_ep_id, ep_rsvc_id, ep_ts, intents, fw_id=None, pkg_ver=None):
    osgi_props = get_rsa_props(object_class, exported_cfgs, intents, ep_rsvc_id, fw_id, pkg_ver)
    ecf_props = get_ecf_props(ecf_ep_id, ep_namespace, ep_rsvc_id, ep_ts)
    return merge_dicts(osgi_props,ecf_props)

def get_edef_props_error(object_class):
    return get_edef_props(object_class, ERROR_IMPORTED_CONFIGS, ERROR_NAMESPACE, ERROR_EP_ID, ERROR_ECF_EP_ID, 0, 0, None, None)

def get_dot_properties(prefix,props,remove_prefix):    
    result_props = dict()
    if props:
        dotkeys = [ x for x in props.keys() if x.startswith(prefix+'.')]
        for dotkey in dotkeys:
            if remove_prefix:
                newkey = dotkey[len(prefix)+1:]
            else:
                newkey = dotkey
            result_props[newkey] = props.get(dotkey)
    return result_props

def is_reserved_property(key):
    return key in RSA_PROP_NAMES or key in ECFPROPNAMES or key.startswith('.')

def remove_from_props(props,keys):
    for key in props:
        if key in keys:
            props.pop(key)
    return props

def copy_non_reserved(props,target):
    for key, value in list(props.items()):
        if not is_reserved_property(key):
            target[key] = value
    return target

def copy_non_ecf(props,target):
    for key, value in list(props.items()):
        if not key in ECFPROPNAMES:
            target[key] = value
    return target

class SelectExporterError(Exception):
    def __init__(self,*args,**kwargs):
        Exception.__init__(self,*args,**kwargs)

class SelectImporterError(Exception):
    def __init__(self,*args,**kwargs):
        Exception.__init__(self,*args,**kwargs)

class RemoteServiceError(Exception):
    def __init__(self,*args,**kwargs):
        Exception.__init__(self,*args,**kwargs)
        