#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Etcd Discovery Provider

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
from threading import Thread, RLock
import time
import socket
import json
from pelix.rsa.endpointdescription import encode_endpoint_props,\
    decode_endpoint_props, EndpointDescription
from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate,\
    ValidateComponent, Property, Invalidate
from pelix.rsa.providers.discovery import SERVICE_ENDPOINT_ADVERTISER,\
    EndpointAdvertiser, EndpointEvent, EndpointSubscriber
from pelix.rsa import create_uuid
from pelix.ipopo.constants import ARG_BUNDLE_CONTEXT
   
import etcd

@ComponentFactory('ecf.namespace.etcd-endpoint-discovery-factory')
@Provides(SERVICE_ENDPOINT_ADVERTISER)
@Property('_hostname','hostname','localhost')
@Property('_port','port',2379)
@Property('_top_path','top_path','/org.eclipse.ecf.provider.etcd.EtcdDiscoveryContainer')
@Property('_session_ttl','_session_ttl',30)
@Property('_watch_start_wait','watch_start_wait',5)
@Instantiate('ecf.namespace.etcd-endpoint-discovery')
class EtcdEndpointDiscovery(EndpointAdvertiser,EndpointSubscriber):
    '''
    Etcd-based endpoint discovery.  Extends both EndpointAdvertiser
    and EndpointSubscriber so can be called to advertise/unadvertise
    exported endpoints, and will notify SERVICE_ENDPOINT_LISTENERs
    when an endpoint has been discovered via the etcd service.
    
    Note that this depends upon the python-etcd client library.
    '''
    # Property names that are read upon ValidateComponent to set
    # the etcd hostname,port,toppath,session ttl (time to live)
    # See above for defaults
    ETCD_HOSTNAME_PROP = 'etcd.hostname'
    ETCD_PORT_PROP = 'etcd.port'
    ETCD_TOP_PATH_PROP = 'etcd.toppath'
    ETCD_SESSION_TTL_PROP = 'etcd.sesssionttl'
    ETCD_WATCH_START_WAIT_PROP = 'etc.watchstartwait'
    
    REMOVE_ACTIONS = ['delete','expire']
    ADD_ACTIONS = ['set','create']
    
    def __init__(self):
        EndpointAdvertiser.__init__(self)
        EndpointSubscriber.__init__(self)
        self._hostname = None
        self._port = None
        self._top_path = None
        self._sessionid = create_uuid()   
        self._session_ttl = None
        self._watch_start_wait = None
        self._client = None 
        self._client_lock = RLock() 
        self._top_nodes = None
        self._wait_index = None
        self._ttl_thread = None
        self._watch_thread = None
        servicename = 'osgirsvc_{0}'.format(create_uuid())
        hostip = socket.gethostbyname(socket.gethostname())
        self._service_props = {'location':'ecfosgisvc://{0}:32565/{1}'.format(hostip,servicename),'priority': 0,'weight': 0,
             'servicename':servicename,'ttl': 0,
             'servicetype': {'services':['ecfosgirsvc'],'scopes':['default'],'protocols':['default'],'namingauth':'iana'}}
        
    @ValidateComponent(ARG_BUNDLE_CONTEXT)
    def _validate_component(self,bundle_context):
        hostname = bundle_context.get_property(self.ETCD_HOSTNAME_PROP)
        if hostname:
            self._hostname = hostname
        port = bundle_context.get_property(self.ETCD_PORT_PROP)
        if port:
            self._port = int(port)
        top_path = bundle_context.get_property(self.ETCD_TOP_PATH_PROP)
        if top_path:
            self._top_path = top_path
        session_ttl = bundle_context.get_property(self.ETCD_SESSION_TTL_PROP)
        if session_ttl:
            self._session_ttl = int(session_ttl)
        watch_start_wait = bundle_context.get_property(self.ETCD_WATCH_START_WAIT_PROP)
        if watch_start_wait:
            self._watch_start_wait = int(watch_start_wait)
        # now connect
        self._connect()
    
    @Invalidate
    def _invalidate(self,bundle_context):
        self._disconnect()
        
    # implementation of EndpointAdvertiser service.  These methods
    # are called when (e.g.) RSA asks us to advertise/unadvertise
    # an endpoint_description
    def _advertise(self,endpoint_description):
        _logger.debug('advertising ed={0}'.format(endpoint_description))
        # encode props as string -> string
        encoded_props = encode_endpoint_props(endpoint_description)
        # get copy of service props
        service_props = self._service_props.copy()
        # set 'properties field'
        service_props['properties'] = [{ 'type':'string', 'name': key, 'value': encoded_props.get(key)} for key in encoded_props]
        # dump service_props to json
        props_json = json.dumps(service_props)
        # write to etcd
        with self._client_lock:
            return self._client.write(key=self._get_endpoint_path(endpoint_description.get_id()),value=props_json)
    
    def _unadvertise(self,advertised):
        _logger.debug('unadvertising ed={0}'.format(advertised[0]))
        # get endpoint id
        endpointid = advertised[0].get_id()
        # write to etcd
        with self._client_lock:
            return self._client.delete(key=self._get_endpoint_path(endpointid))
    

    def _get_session_path(self):
        return '{0}/{1}'.format(self._top_path,self._sessionid)
    
    def _get_endpoint_path(self,endpointid):
        return '{0}/{1}'.format(self._get_session_path(),endpointid)
    
    def _disconnect(self):
        with self._client_lock:
            if self._client:
                session_path = self._get_session_path()
                try:
                    self._client.delete(session_path, True, True)
                except:
                    _logger.exception('Exception deleting session_path={0}'.format(session_path))
                self._client = None
                
    def _connect(self):
        with self._client_lock:
            if self._client:
                raise Exception('already connected')
            
            self._client = etcd.Client(host=self._hostname, port=self._port)
            # now make request against basic
            try:
                top_response = self._client.read(self._top_path,recursive=True)
            except etcd.EtcdKeyNotFound:
                # if this happens, attempt to write it
                try:
                    top_response = self._client.write(self._top_path,None,0,True)
                except Exception as e:
                    _logger.exception('Exception attempting to create top dir={0}'.format(self._top_path))
                    raise e
            # set top nodes
            self._top_nodes = [x for x in list(top_response.get_subtree()) if x.dir and x.key != self._top_path]
            try:
                session_exists_result = self._client.write(key=self._get_session_path(),
                                                           value=None,ttl=self._session_ttl,dir=True,prevExist=False)
            except Exception as e:
                _logger.exception('Exception creating session for client at session_path={0}'.format(self._get_session_path()))
                raise e
            self._wait_index = session_exists_result.createdIndex + 1
            self._ttl_thread = Thread(target = self._ttl_job, name='Etcd TTL Job')
            self._ttl_thread.daemon = True
            self._watch_thread = Thread(target = self._watch_job, name='Etcd Watch Job')
            self._watch_thread.daemon = True
            self._ttl_thread.start()
            self._watch_thread.start()

    def _get_start_wait(self):
        return int(self._session_ttl - (self._session_ttl/10))
    
    def _handle_add_dir(self,dir_node):
        # get sessionid from key 
        sessionid = dir_node.key[len(self._top_path)+1:]
        _logger.debug('_handle_add_dir sessionid={0}'.format(sessionid))
        self._add_other_session(sessionid)
        self._handle_add_nodes([node for node in list(dir_node.children) if not node.dir])
    
    def _handle_remove_dir(self,sessionid):
        _logger.debug('_handle_remove_dir sessionid={0}'.format(sessionid))
        self._remove_other_session(sessionid)
            
    def _handle_add_nodes(self,nodes):
        for node in nodes:
            # we only care about properties
            node_val = node.value
            if node_val:
                json_obj = json.loads(node_val)
                if isinstance(json_obj,dict):
                    json_properties = json_obj['properties']
                    # get the name and value from each entry
                    raw_props = {entry['name']:entry['value'] for entry in json_properties if entry['type'] == 'string'}
                    # decode
                    decoded_props = decode_endpoint_props(raw_props)
                    ed = EndpointDescription(properties=decoded_props)
                    
                    self._add_discovered_endpoint(ed)
                    # dispatch
                    self._fire_endpoint_event(EndpointEvent.ADDED, ed)

    def _handle_remove_node(self,endpointid):
        ed = self._remove_discovered_endpoint(endpointid)
        if ed:
            self._fire_endpoint_event(EndpointEvent.REMOVED, ed)
            
    def _watch_job(self):
        # sleep for a few seconds to allow endpoint listeners to be asynchronously 
        # added before the top nodes are processed
        time.sleep(5)
        # first thing is to process the existing nodes from connect
        if self._top_nodes:
            #guaranteed to be directory
            for dir_node in self._top_nodes:
                self._handle_add_dir(dir_node)
                self._top_nodes = None
        # then loop forever
        while True:
            with self._client_lock:
                client = self._client
            if not client:
                return
            try:
                result = client.read(key=self._top_path,recursive=True,wait=True,waitIndex=self._wait_index)
                # reset wait_index
                self._wait_index = result.modifiedIndex + 1
                key = result.key
                action = result.action
                if key.endswith(self._sessionid):
                    if action == 'delete':
                        print('watch_job: session dir deleted...exiting')
                        #we are done
                        return
                else:
                    if action != 'update':
                        # split id into [sessionid] or [sessionid,endpointid]
                        splitid = key[len(self._top_path)+1:].split('/')
                        sessionid = splitid[0]
                        if self._sessionid != sessionid:
                            if isinstance(splitid,list):
                                endpointid = splitid[len(splitid)-1]
                            else:
                                endpointid = None
                            if not endpointid:
                                if action in self.REMOVE_ACTIONS:
                                    # other session deleted
                                    self._handle_remove_dir(sessionid)
                                elif action in self.ADD_ACTIONS:
                                    self._handle_add_dir(result)
                            else:
                                if action in self.REMOVE_ACTIONS:
                                    self._handle_remove_node(endpointid)
                                elif action in self.ADD_ACTIONS:
                                    self._handle_add_nodes([result])
            except:
                _logger.exception('watch_job:Exception in watch loop')
           
            
    def _ttl_job(self):
        waittime = self._get_start_wait()
        while True: 
            _logger.debug('ttl_job: starting sleep with waittime={0}'.format(waittime))
            time.sleep(1)
            with self._client_lock:
                client = self._client
            if not client:
                _logger.debug('ttl_job: exiting')
                return
            waittime -= 1
            _logger.debug('ttl_job: testing waittime <= 0 with waittime={0}'.format(waittime))
            if waittime <= 0:
                try:
                    session_ttl = self._session_ttl
                    _logger.debug('ttl_job: updating with session_ttl='.format(waittime,session_ttl))
                    with self._client_lock:
                        if self._client:
                            self._client.write(key=self._get_session_path(),value=None,ttl=session_ttl,dir=True,prevExist=True)
                    _logger.debug('ttl_job: updated with session_ttl='.format(waittime,session_ttl))
                except:
                    _logger.exception('Exception updating in ttl job')
                waittime = self._get_start_wait()
        
