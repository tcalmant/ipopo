#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Etcd Discovery Provider

:author: Scott Lewis
:copyright: Copyright 2024, Scott Lewis
:license: Apache License 2.0
:version: 3.0.0

..

    Copyright 2024 Scott Lewis

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import json
import logging
import threading
import socket

from typing import Any, Optional, Tuple, Iterable, Sequence, Dict

from pelix.framework import BundleContext
from pelix.ipopo.decorators import (
    ComponentFactory,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    ValidateComponent
)
from pelix.rsa import create_uuid, prop_dot_suffix
from pelix.rsa.endpointdescription import EndpointDescription, decode_endpoint_props, encode_endpoint_props
from pelix.rsa.providers.discovery import EndpointAdvertiser, EndpointEvent, EndpointSubscriber
import uuid
import grpc

from .etcdrpc import rpc_pb2
from .etcdrpc import rpc_pb2_grpc

import asyncio
from concurrent.futures.thread import ThreadPoolExecutor

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (3, 0, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Standard logging
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)
# ------------------------------------------------------------------------------

ETCD_NAME_PROP = "etcd"
ETCD_HOSTNAME_PROP = "hostname"
ETCD_PORT_PROP = "port"
ETCD_TOPPATH_PROP = "toppath"

# ------------------------------------------------------------------------------

def to_bytes(bytes_or_str):
    if isinstance(bytes_or_str, bytes):
        return bytes_or_str
    else:
        return bytes_or_str.encode('utf-8')

@ComponentFactory("etcd3-endpoint-discovery-factory")
@Provides(EndpointAdvertiser)
@Property(
    "_hostname",
    prop_dot_suffix(ETCD_NAME_PROP, ETCD_HOSTNAME_PROP),
    "localhost",
)
@Property("_port", prop_dot_suffix(ETCD_NAME_PROP, ETCD_PORT_PROP), 2379)
@Property(
    "_top_path",
    prop_dot_suffix(ETCD_NAME_PROP, ETCD_TOPPATH_PROP),
    "org.eclipse.ecf.provider.etcd3.container.Etcd3DiscoveryContainer",
)
@Instantiate("etcd3-endpoint-discovery")
class Etcd3EndpointDiscovery(EndpointAdvertiser, EndpointSubscriber):
    """
    Etcd-based endpoint discovery.  Extends both EndpointAdvertiser
    and EndpointSubscriber so can be called to advertise/unadvertise
    exported endpoints, and will notify SERVICE_ENDPOINT_LISTENERs
    when an endpoint has been discovered via the etcd service.

    """

    def __init__(self, hostname: str = "localhost", 
                 port: int = 2379,
                 session_ttl: int = 30, #etcd default keep alive is 30 seconds
                 session_ttl_interval:int = 5, # ttl - ttl_interval is how often etcd keep alive is sent
                 call_timeout: int = 3000, # timeout for individual blocking calls
                 disconnect_timeout: int = 5000,
                 # if credentials is set then a secure channel will be created
                 credentials: Optional[grpc.ChannelCredentials] = None,
                 executor: Optional[ThreadPoolExecutor] = None,
                 # See grpc documentation for 'options' and 'compression' argument at following
                 # https://grpc.github.io/grpc/python/grpc_asyncio.html#grpc.aio.insecure_channel
                 grpc_options: Optional[Sequence[Tuple[str, Any]]] = None, 
                 grpc_compression: Optional[grpc.Compression] = None,
                 top_path: str = "org.eclipse.ecf.provider.etcd3.container.Etcd3DiscoveryContainer",
                 session_id: str = create_uuid()
                 ) -> None:
        EndpointAdvertiser.__init__(self)
        EndpointSubscriber.__init__(self)
        self._hostname: hostname
        self._port: int = port
        self._session_ttl: int = session_ttl  # in seconds
        self._session_ttl_interval: int = session_ttl_interval  # in seconds
        self._call_timeout: int = call_timeout
        self._disconnect_timeout: int = disconnect_timeout # in ms
        self._grpc_credentials: Optional[grpc.ChannelCredentials] = credentials
        self._grpc_options: Optional[Sequence[Tuple[str, Any]]] = grpc_options
        self._grpc_compression: Optional[grpc.Compression] = grpc_compression
        self._executor: Optional[ThreadPoolExecutor] = executor
        self._top_path: str = top_path
        self._sessionid = session_id
        self._watch_id: Optional[int] = None
        self._lease_id: Optional[int] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        self._channel: Optional[grpc.Channel] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._connected_event = asyncio.Event()
        self._encoding = "utf-8"
        # vars set in connect
        servicename = f"osgirsvc_{create_uuid()}"
        hostip = socket.gethostbyname(socket.gethostname())
        self._service_props = {
            "location": f"ecfosgisvc://{hostip}:32565/{servicename}",
            "priority": 0,
            "weight": 0,
            "servicename": servicename,
            "ttl": 0,
            "servicetype": {
                "services": ["ecfosgirsvc"],
                "scopes": ["default"],
                "protocols": ["default"],
                "namingauth": "iana",
            },
        }

    def _get_session_path(self) -> str:
        return f"{self._top_path}/{self._sessionid}"

    def _get_endpoint_path(self, endpointid: str) -> str:
        return f"{self._get_session_path()}/{endpointid}"

    async def _write_description(
        self, endpoint_description: EndpointDescription
    ) -> rpc_pb2.PutResponse:
        # make sure we are connected
        await self._connected_event.wait()
        service_props = self._encode_description(endpoint_description)
        return await self._putKV(self._get_endpoint_path(endpoint_description.get_id()), json.dumps(service_props))
    
    def _encode_description(self, endpoint_description: EndpointDescription) -> Dict[str, Any]:
        encoded_props = encode_endpoint_props(endpoint_description)
        # get copy of service props
        service_props = self._service_props.copy()
        # set 'properties field'
        service_props["properties"] = [
            {"type": "string", "name": key, "value": encoded_props.get(key)} for key in encoded_props
        ]
        return service_props

    def _run_coroutine(self, coro) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(self._call_timeout)
        
    async def _get_key_value(self, key: str) -> str:
        await self._connected_event.wait()
        resp = await rpc_pb2_grpc.KVStub(self._channel).Range(rpc_pb2.RangeRequest(key = to_bytes(key)))
        if resp.kvs and len(resp.kvs) > 0:
            return str(resp.kvs.pop().value, self._encoding)
         
    def _get_value(self, endpoint_id: str) -> str:
        return self._run_coroutine(self._get_key_value(endpoint_id))

    # entry point method
    @ValidateComponent()
    def _validate_component(self) -> None:
        self._loop = asyncio.new_event_loop()
        async def connected_callback():
            # wait until we get thec onnected event set
            await self._connected_event.wait()
            _logger.debug("CONNECTED etcd3 session_id=%s to host=%s port=%s", self._sessionid, self._hostname, self._port)
        def worker():
            asyncio.set_event_loop(self._loop)
            self._loop_thread_id = threading.current_thread().ident
            asyncio.run_coroutine_threadsafe(connected_callback(), self._loop)
            self._loop.run_until_complete(self._connect())  
        t = threading.Thread(target=worker, name="etcd3[{}]".format(self._sessionid), daemon=True)
        t.start()

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        try:
            asyncio.run_coroutine_threadsafe(self._disconnect(), self._loop).result(self._disconnect_timeout)
        except:
            pass
        

    # implementation of EndpointAdvertiser service.  These methods
    # are called when (e.g.) RSA asks us to advertise/unadvertise
    # an endpoint_description
    def _advertise(self, endpoint_description: EndpointDescription) -> None:
        return self._run_coroutine(self._write_description(endpoint_description))

    def _update(self, endpoint_description: EndpointDescription) -> None:
        return self._run_coroutine(self._write_description(endpoint_description))

    def _unadvertise(self, advertised: Tuple[EndpointDescription, Any]) -> None:
        return self._run_coroutine(self._delete_range(self._get_endpoint_path(advertised[0].get_id())))

    def _get_key_prefix(self):
        return self._top_path

    def _get_session_key(self):
        return "/".join([self._get_key_prefix(), self._sessionid])

    class EndpointKey(object):
        def __init__(self, sessionid: str, ed_id: str) -> None:
            self.sessionid = sessionid
            self.ed_id = ed_id
            self.fullkey = "/".join([self.sessionid, self.ed_id])

        def __str__(self) -> str:
            return "[EndpointKey sessionid={} ed_id={} fullKey={}]".format(
                self.sessionid, self.ed_id, self.fullkey
            )

    def _create_endpoint_key(self, key: str) -> EndpointKey:
        split_key = [x for x in key.split("/") if x != ""]
        split_key_len = len(split_key)
        if split_key_len <= 1:
            return None
        elif split_key_len == 2:
            # this means that we are getting notified about changes in our own endpoint
            return None
        else:
            try:
                uuid.UUID("urn:uuid:{}".format(split_key[1]), version=4)
            except ValueError:
                _logger.error(
                    "_create_endpoint_key error, GUID creation failed for sessionId=%s", split_key[1]
                )
                return None
            return self.EndpointKey(split_key[1], split_key[2])

    def _get_full_key(self, endpoint_fk):
        return "/".join([self._get_key_prefix(), endpoint_fk])

    def _remove_endpoint(self, endpoint_key: EndpointKey):
        removed_ep = self._remove_discovered_endpoint(endpoint_key.ed_id)
        if removed_ep:
            _logger.debug("session_id=%s removed endpoint description with=%s ", self._sessionid, endpoint_key)
            self._fire_endpoint_event(EndpointEvent.REMOVED, removed_ep)

    def _decode_endpoint_description(self, value: str):
        # get actual value from endpoint key
        json_value = json.loads(value)
        json_properties = json_value["properties"]
        # get the name and value from each entry
        raw_props = {entry["name"]: entry["value"] for entry in json_properties if entry["type"] == "string"}
        # create new EndpointDescription from deserialized properties
        return EndpointDescription(properties=decode_endpoint_props(raw_props))
            
    def _add_or_modify_endpoint(self, endpoint_key: EndpointKey, value: str):
        new_ed = self._decode_endpoint_description(value)
        event_type = EndpointEvent.ADDED
        with self._discovered_endpoints_lock:
            # check to see if already there
            old_ed = self._has_discovered_endpoint(new_ed.get_id())
            if not old_ed:
                # add discovered endpoint to our internal list
                self._add_discovered_endpoint(endpoint_key.sessionid, new_ed)
                _logger.debug(
                    "session_id=%s added endpoint key=%s value=%s", self._sessionid, endpoint_key, value
                )
            else:
                # get timestamp and make sure new one is newer (an
                # update)
                old_ts = old_ed.get_timestamp()
                new_ts = new_ed.get_timestamp()
                if new_ts > old_ts:
                    self._remove_discovered_endpoint(old_ed.get_id())
                    self._add_discovered_endpoint(endpoint_key.sessionid, new_ed)
                    event_type = EndpointEvent.MODIFIED
                    _logger.debug(
                        "session_id=%s modified endpoint key=%s value=%s", self._sessionid, endpoint_key, value
                    )
        # fire event outside lock
        self._fire_endpoint_event(event_type, new_ed)

    def _process_kv(self, key: str, value: str, add_remove: bool):
        endpoint_key = self._create_endpoint_key(key)
        # only do anything if valid endpoint_key and not our sessionid
        if endpoint_key and not endpoint_key.sessionid == self._sessionid:
            if add_remove and value:
                self._add_or_modify_endpoint(endpoint_key, value)
            else:
                self._remove_endpoint(endpoint_key)

    def _fire_endpoint_event(self, event_type:int, ed:EndpointDescription)-> None:#
        # send notifications via thread so doesn't block asyncio loop thread
        self._loop.run_in_executor(self._executor, EndpointSubscriber._fire_endpoint_event, self, event_type, ed)
        
    async def _putKV(self, key, value) -> rpc_pb2.PutResponse:
        return await rpc_pb2_grpc.KVStub(self._channel).Put(rpc_pb2.PutRequest(key = to_bytes(key), value = to_bytes(value), lease = self._lease_id))
    
    def _create_async_channel(self) -> grpc.Channel:
        target = "{}:{}".format(self._hostname, self._port)
        if self._grpc_credentials:
            return grpc.aio.secure_channel(target, self._grpc_credentials, self._grpc_options, self._grpc_compression)
        else:
            return grpc.aio.insecure_channel(target, self._grpc_options, self._grpc_compression)

    def _process_events(self, events):
        for event in events:
            key = str(event.kv.key, self._encoding)
            value = str(event.kv.value, self._encoding)
            from .etcdrpc.kv_pb2 import Event
            if key:
                if event.type == Event.EventType.PUT:
                    self._process_kv(key, value, True)
                elif event.type == Event.EventType.DELETE:
                    self._process_kv(key, value, False)
                    
    async def _request_lease(self) -> None:
        resp = await rpc_pb2_grpc.LeaseStub(self._channel).LeaseGrant(rpc_pb2.LeaseGrantRequest(TTL = self._session_ttl))
        if resp.error:
            _logger.error("session_id={} request_lease error={}".format(self._sessionid, resp.error))
            await self._disconnect()
        self._lease_id = resp.ID
        self._session_ttl = resp.TTL
        async def keepalive():
            async def generate_ka_request():
                while True:
                    try:
                        await asyncio.sleep(self._session_ttl - self._session_ttl_interval)
                    except asyncio.exceptions.CancelledError:
                        return
                    if self._lease_id:
                        yield rpc_pb2.LeaseKeepAliveRequest(ID = self._lease_id)
                    else:
                        return 
                    
            async for resp in rpc_pb2_grpc.LeaseStub(self._channel).LeaseKeepAlive(generate_ka_request()):
                if resp.ID == self._lease_id and resp.TTL:
                    self._session_ttl = resp.TTL
        # keep alive task is created  here
        if not self._keepalive_task:
            self._keepalive_task = self._loop.create_task(keepalive())

    def _generate_watch_request(self, create_request: rpc_pb2.WatchCreateRequest, cancel_request: rpc_pb2.WatchCancelRequest) -> Iterable[rpc_pb2.WatchRequest]:
        yield rpc_pb2.WatchRequest(create_request = create_request, cancel_request = None)
          
    async def _connect(self) -> None:
        #create channel
        self._channel = self._create_async_channel()
        # create lease and start keepalive
        await self._request_lease()
        # we are now connected so notify by setting self._connected_event
        kp = self._get_key_prefix()
        kp_bytes = to_bytes(kp)
        kp_range_end_bytes = to_bytes("".join([kp,"\\0"]))
        range_resp = await rpc_pb2_grpc.KVStub(self._channel).Range(rpc_pb2.RangeRequest(key=kp_bytes, range_end = kp_range_end_bytes))
        for kv in range_resp.kvs:
            self._process_kv(str(kv.key, self._encoding), str(kv.value, self._encoding), True)
        #Now announce us as present by putting key on etcd server    
        await self._putKV(self._get_session_key(), self._sessionid)
             
        async for watch_response in rpc_pb2_grpc.WatchStub(self._channel).Watch(self._generate_watch_request(rpc_pb2.WatchCreateRequest(key = kp_bytes, range_end = kp_range_end_bytes), None)):
            if watch_response.created:
                self._watch_id = watch_response.watch_id
                self._connected_event.set()
            elif watch_response.canceled:
                _logger.error("session_id={} watch_cancelled ".format(self._sessionid))
                return 
            else:
                self._process_events(watch_response.events)
        
    async def _delete_range(self, key: str) -> rpc_pb2.DeleteRangeResponse:
        await self._connected_event.wait()
        return await rpc_pb2_grpc.KVStub(self._channel).Range(rpc_pb2.DeleteRangeRequest(key=to_bytes(key), range_end = to_bytes("".join([key, "\\0"]))))
            
    async def _disconnect(self) -> None:
        """
        Disconnects the etcd client
        """
        if self._lease_id:
            await self._connected_event.wait()
            if self._keepalive_task:
                self._keepalive_task.cancel("keep alive cancelled")
                self._keepalive_task = None

            await self._delete_range(self._get_session_path())
            # stop lease scheduler and revoke our lease
            resp = await rpc_pb2_grpc.LeaseStub(self._channel).LeaseRevoke(rpc_pb2.LeaseRevokeRequest(ID = self._lease_id))
            _logger.debug("session_id={} lease_id={} revoked".format(self._sessionid, self._lease_id))
            self._lease_id = None
                            
            await self._channel.close()
            _logger.debug("session_id={} closed channel".format(self._sessionid))
            self._channel = None

                       
        