#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Py4j-based Distribution and Discovery Provider

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
from osgiservicebridge.bridge import JavaServiceProxy,\
    Py4jServiceBridgeEventListener, Py4jServiceBridge
from osgiservicebridge.protobuf import ProtobufServiceProxy
from pelix.rsa import prop_dot_suffix
from py4j.java_gateway import GatewayParameters, CallbackServerParameters
from pelix.constants import OBJECTCLASS
import osgiservicebridge
#logging.basicConfig(level=logging.DEBUG)
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)
# Documentation strings format
__docformat__ = "restructuredtext en"
# ------------------------------------------------------------------------------
# Providers API    
from pelix.rsa.providers.distribution import ExportContainer,ImportContainer,DistributionProvider,\
    SERVICE_EXPORT_CONTAINER, SERVICE_IMPORT_CONTAINER,\
    SERVICE_EXPORT_DISTRIBUTION_PROVIDER, SERVICE_IMPORT_DISTRIBUTION_PROVIDER
# needed ipopo decorators
from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate, Property,\
    Validate, Invalidate, PostRegistration
from pelix.rsa.endpointdescription import EndpointDescription
from queue import Queue
from threading import Thread
from py4j.java_gateway import DEFAULT_PORT, DEFAULT_PYTHON_PROXY_PORT
# ------------------------------------------------------------------------------
# Note:  These must match the Java-side constants recored in Java interface class:
# org.eclipse.ecf.provider.py4j.Py4jConstants
ECF_PY4J_CONTAINER_CONFIG_TYPE = 'ecf.py4j'
ECF_PY4J_PYTHON_HOST_CONFIG_TYPE = 'ecf.py4j.host.python'
ECF_PY4JPB_PYTHON_HOST_CONFIG_TYPE = 'ecf.py4j.host.python.pb'
ECF_PY4J_PYTHON_CONSUMER_CONFIG_TYPE = 'ecf.py4j.consumer.python'
ECF_PY4JPB_PYTHON_CONSUMER_CONFIG_TYPE = 'ecf.py4j.consumer.python.pb'
ECF_PY4J_JAVA_HOST_CONFIG_TYPE = 'ecf.py4j.host'
ECF_PY4JPB_JAVA_HOST_CONFIG_TYPE = 'ecf.py4j.host.pb'
ECF_PY4J_NAMESPACE = 'ecf.namespace.py4j'
ECF_PY4J_SUPPORTED_INTENTS = ['exactlyOnce','passByReference','ordered','py4j']
ECF_PY4JPB_SUPPORTED_INTENTS = ['exactlyOnce','passByValue','ordered','py4j', 'protobuf']

ECF_PY4J_JAVA_PORT_PROP = 'javaport'
ECF_PY4J_PYTHON_PORT_PROP = 'pythonport'
# ------------------------------------------------------------------------------
@ComponentFactory(ECF_PY4J_CONTAINER_CONFIG_TYPE)
@Provides([SERVICE_EXPORT_CONTAINER,SERVICE_IMPORT_CONTAINER])
class Py4jContainer(ExportContainer,ImportContainer):

    def get_connected_id(self):
        return ExportContainer.get_connected_id(self)
    
    def _export_service(self, svc, ed_props):
        # modify svc class to have appropriate metadata for py4j
        osgiservicebridge._modify_remoteservice_class(type(svc),{ OBJECTCLASS: ed_props[OBJECTCLASS] })
        self._get_distribution_provider()._get_bridge().export(svc, ed_props)
        ExportContainer._export_service(self, svc, ed_props)
        return True

    def _unexport_service(self, ed):
        self._get_distribution_provider()._get_bridge().unexport(ed.get_id())
        ExportContainer._unexport_service(self, ed)
        return True
    
    def _prepare_proxy(self,ed):
        # lookup the bridge proxy associated with the ed.get_id()
        bridge = self._get_distribution_provider()._get_bridge()
        proxy = bridge.get_import_endpoint(ed.get_id())[0]
        args = [ bridge.get_jvm(), ed.get_interfaces(), proxy, ed.get_remoteservice_idstr()]
        clazz = JavaServiceProxy
        if ECF_PY4JPB_JAVA_HOST_CONFIG_TYPE in ed.get_remote_configs_supported():
            clazz = ProtobufServiceProxy
        return clazz(*args)
    
    def unimport_service(self,ed):
        self._get_distribution_provider()._get_bridge().remove_import_endpoint(ed.get_id())
        ImportContainer.unimport_service(self, ed)

    
@ComponentFactory("py4j-distribution-provider-factory")
@Provides([SERVICE_EXPORT_DISTRIBUTION_PROVIDER,SERVICE_IMPORT_DISTRIBUTION_PROVIDER])
@Property('_config_name', 'config_name', ECF_PY4J_CONTAINER_CONFIG_TYPE)
@Property('_namespace', 'namespace', ECF_PY4J_NAMESPACE)
@Property('_supported_configs','supported_configs', [ECF_PY4J_PYTHON_HOST_CONFIG_TYPE,ECF_PY4J_PYTHON_CONSUMER_CONFIG_TYPE])
@Property('_supported_intents', 'supported_intents', ECF_PY4J_SUPPORTED_INTENTS)
@Property('_supported_pb_intents','supported_pb_intents', ECF_PY4JPB_SUPPORTED_INTENTS)
@Property('_javaport', prop_dot_suffix(ECF_PY4J_CONTAINER_CONFIG_TYPE,ECF_PY4J_JAVA_PORT_PROP),DEFAULT_PORT)
@Property('_pythonport', prop_dot_suffix(ECF_PY4J_CONTAINER_CONFIG_TYPE,ECF_PY4J_PYTHON_PORT_PROP),DEFAULT_PYTHON_PROXY_PORT)
@Instantiate("py4j-distribution-provider")
class Py4jDistributionProvider(DistributionProvider,Py4jServiceBridgeEventListener):
    def __init__(self):
        super(Py4jDistributionProvider, self).__init__()
        self._bridge = None
        self._queue = Queue()
        self._thread = Thread(target = self._worker)
        self._thread.daemon = True
        self._py4jcontainer = self._supported_pb_intents = None
        self._javaport = self._pythonport = None

    def _get_bridge(self):
        return self._bridge
    
    # Override of DistributionProvider._get_imported_configs. Returns
    # the Py4j bridge.get_id() in list
    def _get_imported_configs(self,exported_configs):
        return [self._bridge.get_id()]
    
    # Implementation of ImportDistributionProvider
    def supports_import(self, exported_configs, service_intents, import_props):
        if ECF_PY4JPB_JAVA_HOST_CONFIG_TYPE in exported_configs:
            if self._match_intents_supported(service_intents, self._supported_pb_intents):
                return self._container
        elif ECF_PY4J_JAVA_HOST_CONFIG_TYPE in exported_configs:
            if self._match_intents(service_intents):
                return self._container

    # Implementation of ExportDistributionProvider
    def supports_export(self, exported_configs, service_intents, export_props):
        if self._match_intents(service_intents):
            if ECF_PY4J_PYTHON_HOST_CONFIG_TYPE in exported_configs or ECF_PY4JPB_PYTHON_HOST_CONFIG_TYPE in exported_configs:
                return self._container

    @Validate
    def _validate(self,context):
        ### XXX here is where we can get java and python ports
        ## and change the defaults for connecting
        try:
            self._bridge = Py4jServiceBridge(service_listener=self,gateway_parameters=GatewayParameters(port=self._javaport),
                                             callback_server_parameters=CallbackServerParameters(port=self._pythonport))
            self._bridge.connect()
        except Exception as e:
            self._bridge = None
            raise e
        # Once bridge is connected, instantiate container using bridge id
        container_props = self._prepare_container_props(self._supported_intents, None)
        self._container = self._ipopo.instantiate(self._config_name,self._bridge.get_id(),container_props)
        
    @Invalidate
    def _invalidate(self,context):   
        if self._bridge:
            try:
                self._ipopo.invalidate(self._bridge.get_id())
            except ValueError:
                pass
            try:
                self._bridge.disconnect()
            except:
                pass
            self._bridge = None
            self._container = None
        
    # Implementation of Py4jServiceBridgeEventListener
    def service_imported(self, servicebridge, endpointid, proxy, endpoint_props):
        ## put on task queue so no blocking, but fifo delivery to rsa
        #  _logger.info('service_imported endpointid='+endpointid)
        self._queue.put((endpointid,endpoint_props,self._handle_import))

    def service_modified(self, servicebridge, endpointid, proxy, endpoint_props):
        #_logger.info('_service_modified endpointid='+endpointid+";proxy="+str(proxy)+";endpoint_props="+str(endpoint_props))
        self._queue.put((endpointid,endpoint_props,self._handle_import_update))

    def service_unimported(self, servicebridge, endpointid, proxy, endpoint_props):
        #_logger.info('_service_unimported endpointid='+endpointid+";proxy="+str(proxy)+";endpoint_props="+str(endpoint_props))
        ## put on task queue so no blocking, but fifo delivery to rsa
        self._queue.put((endpointid,endpoint_props,self._handle_import_close))

    @PostRegistration
    def _post_reg(self,svc_ref):
        #start the thread for processing import_service import requests
        self._thread.start()

    # this is method called by self._thread.  All it does is
    # read from queue, and import/unregister imported the discovered service
    def _worker(self):
        while True:
            # block to get items from queue placed by service_imported, service_modified,
            # and service_unimported called by Py4j handler thread
            item = self._queue.get()
            f = None
            try:
                # get the function from item[2]
                f = item[2]
            except:
                logging.error('Exception getting code in item={0}'.format(item))
            if f:
                try:
                    # get the endpoint description properties from item[1] and create
                    # EndpointDescription instance
                    ed = EndpointDescription(properties=item[1])
                except:
                    logging.error('Exception creating endpoint description from props={0}'.format(item[1]))
                if ed:
                    # call appropriate function
                    try:
                        f(ed)
                    except:
                        logging.error('Exception invoking function={0}'.format(f))
            # no matter what, we are done with this task
            self._queue.task_done()
     
    