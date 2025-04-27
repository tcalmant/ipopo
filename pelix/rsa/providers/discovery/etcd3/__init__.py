#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Etcd Discovery Provider

:author: Scott Lewis
:copyright: Copyright 2025, Scott Lewis
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2025 Scott Lewis

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
from collections.abc import Callable

from pelix.framework import BundleContext
from pelix.ipopo.decorators import (
    ComponentFactory,
    Invalidate,
    Property,
    Provides,
    ValidateComponent
)
from pelix.rsa import create_uuid
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

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Standard logging
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------


def to_bytes(bytes_or_str):
    if isinstance(bytes_or_str, bytes):
        return bytes_or_str
    else:
        return bytes_or_str.encode('utf-8')


# etcd3endpoint discovery properties.  see Etcd3Endpoint
ETCD_NAME_PREFIX = "etcd"

# etcd.hostname prop; type: str; Default: "localhost"
ETCD_HOSTNAME_PROP = ".".join([ETCD_NAME_PREFIX, "hostname"])
ETCD_HOSTNAME_DEFAULT = "localhost"
# etcd.port prop; type: int;  Default: 2379
ETCD_PORT_PROP = ".".join([ETCD_NAME_PREFIX, "port"])
ETCD_PORT_DEFAULT = 2379
# etcd.top_key prop; type: str;
# Default: "org.eclipse.ecf.provider.etcd3.container.Etcd3DiscoveryContainer"
# NOTE:  the top_path must be set to some unique string that
# all etcd3 endpoint description discovery clients can share
# it should have only no forward slashes ('/') as that is used
# as a a separator character
ETCD_TOPKEY_PROP = ".".join([ETCD_NAME_PREFIX, "top_key"])
ETCD_TOPKEY_DEFAULT = "org.eclipse.ecf.provider.etcd3.container.Etcd3DiscoveryContainer"
# etcd.grpc_credentials prop; type: Optional[grpc.ChannelCredentials]; Default: None
# if credentials is not None then a secure channel will be created.  If None then insecure channel will
# be created
ETCD_GRPCCREDENTIALS_PROP = ".".join([ETCD_NAME_PREFIX, "grpc_credentials"])
ETCD_GRPCCREDENTIALS_DEFAULT = None
# etcd.grpc_options prop; type: Optional[Sequence[Tuple[str, Any]]]; Default: None
# See grpc documentation for 'options' and 'compression' argument at following
# https://grpc.github.io/grpc/python/grpc_asyncio.html#grpc.aio.insecure_channel
ETCD_GRPCOPTIONS_PROP = ".".join([ETCD_NAME_PREFIX, "grpc_options"])
ETCD_GRPCOPTIONS_DEFAULT = None
# etcd.grpc_compression prop; type: Optional[grpc.Compression]; Default: None
ETCD_GRPCCOMPRESSION_PROP = ".".join([ETCD_NAME_PREFIX, "grpc_compression"])
ETCD_GRPCCOMPRESSION_DEFAULT = None
# etcd.session_id prop; type: str; Default: value returned from call to create_uuid()
# upon __init_
ETCD_SESSIONID_PROP = ".".join([ETCD_NAME_PREFIX, "session_id"])
ETCD_SESSIONID_DEFAULT = create_uuid()
# etcd.session_id prop; type: str; Default: None
ETCD_CONNECTED_CALLBACK_PROP = ".".join([ETCD_NAME_PREFIX, "connected_callback"])
ETCD_CONNECTED_CALLBACK_DEFAULT = None
# etcd.lease_ttl prop; type: int;  Default: 30 seconds
# When a lease is request for the client, a ttl of the value of etcd.lease_ttl will
# be requests
ETCD_LEASETTL_PROP = ".".join([ETCD_NAME_PREFIX, "lease_ttl"])
ETCD_LEASETTL_DEFAULT = 30
# etcd.keepalive_interval prop; type: int;  Default: 25 seconds
# Once a lease is granted, an  etcd lease keepalive request will be sent every
# etcd.keepalive_interval seconds.  This value should be a few seconds
# less than the value of etcd.lease_ttl value
# be requests
ETCD_KEEPALIVEINTERVAL_PROP = ".".join([ETCD_NAME_PREFIX, "keepalive_interval"])
ETCD_KEEPALIVEINTERVAL_DEFAULT = 25
# etcd.call_timeout prop; type: int;  Default: 3 seconds
# When making blocking calls to advertise/unadvertise or _get,
# these calls will timeout (and raise TimeoutError
ETCD_CALLTIMEOUT_PROP = ".".join([ETCD_NAME_PREFIX, "call_timeout"])
ETCD_CALLTIMEOUT_DEFAULT = 3
# etcd.disconnect_timeout prop; type: int;  Default: 5 seconds
# When disconnect is called, it will wait block the calling thread
# until disconnect is complete and wait etcd.disconnect_timeout before
# raising a TimeoutError
ETCD_DISCONNECTTIMEOUT_PROP = ".".join([ETCD_NAME_PREFIX, "disconnect_timeout"])
ETCD_DISCONNECTTIMEOUT_DEFAULT = 5
# etcd.hostip prop; type: str;  Default: string returned from call to
# socket.gethostbyname(socket.gethostname())
ETCD_HOSTIP_PROP = ".".join([ETCD_NAME_PREFIX, "hostip"])
ETCD_HOSTIP_DEFAULT = socket.gethostbyname(socket.gethostname())
# etcd._call_executor; type: Optional[ThreadPoolExecutor]; Default: None (uses asyncio ThreadPoolExecutor
ETCD_CALLEXECUTOR_PROP = ".".join([ETCD_NAME_PREFIX, "call_executor"])
ETCD_CALLEXECUTOR_DEFAULT = None

ETCD_FACTORY_NAME = "etcd3-endpoint-discovery-factory"
ETCD_INSTANCE_NAME = "etcd3-endpoint-discovery"


@ComponentFactory(ETCD_FACTORY_NAME)
@Provides(EndpointAdvertiser)
@Property(
    "_hostname",
    ETCD_HOSTNAME_PROP,
    ETCD_HOSTNAME_DEFAULT
)
@Property("_port",
    ETCD_PORT_PROP,
    ETCD_PORT_DEFAULT
)
@Property(
    "_top_key",
    ETCD_TOPKEY_PROP,
    ETCD_TOPKEY_DEFAULT,
)
@Property(
    "_grpc_credentials",
    ETCD_GRPCCREDENTIALS_PROP,
    ETCD_GRPCCREDENTIALS_DEFAULT,
)
@Property(
    "_grpc_options",
    ETCD_GRPCOPTIONS_PROP,
    ETCD_GRPCOPTIONS_DEFAULT,
)
@Property(
    "_grpc_compression",
    ETCD_GRPCCOMPRESSION_PROP,
    ETCD_GRPCCOMPRESSION_DEFAULT
)
@Property(
    "_session_id",
    ETCD_SESSIONID_PROP,
    ETCD_SESSIONID_DEFAULT
)
@Property(
    "_connected_callback",
    ETCD_CONNECTED_CALLBACK_PROP,
    ETCD_CONNECTED_CALLBACK_DEFAULT,
)
@Property("_lease_ttl",
    ETCD_LEASETTL_PROP,
    ETCD_LEASETTL_DEFAULT
)
@Property("_keepalive_interval",
    ETCD_KEEPALIVEINTERVAL_PROP,
    ETCD_KEEPALIVEINTERVAL_DEFAULT
)
@Property("_call_timeout",
    ETCD_CALLTIMEOUT_PROP,
    ETCD_CALLTIMEOUT_DEFAULT
)
@Property("_disconnect_timeout",
    ETCD_DISCONNECTTIMEOUT_PROP,
    ETCD_DISCONNECTTIMEOUT_DEFAULT
)
@Property("_hostip",
    ETCD_HOSTIP_PROP,
    ETCD_HOSTIP_DEFAULT
)
@Property(
    "_call_executor",
    ETCD_CALLEXECUTOR_PROP,
    ETCD_CALLEXECUTOR_DEFAULT,
)
class Etcd3EndpointDiscovery(EndpointAdvertiser, EndpointSubscriber):
    """
    Etcd3-based remote service endpoint discovery.  Extends both EndpointAdvertiser
    and EndpointSubscriber so can be called to advertise/unadvertise
    exported endpoints (typically via the topology manager), and will notify
    SERVICE_ENDPOINT_LISTENERs (also typically topology manager)
    when an endpoint has been discovered via the etcd3 server/cluster watch.

    """
    _hostname: str
    _port: int
    _top_key: str
    _grpc_credentials: Optional[grpc.ChannelCredentials]
    _grpc_options: Optional[Sequence[Tuple[str, Any]]]
    _grpc_compression: Optional[grpc.Compression]
    _channel: Optional[grpc.Channel]
    _lease_ttl: int
    _keepalive_interval: int
    _call_timeout: int
    _disconnect_timeout: int
    _session_id: str = None
    _connected_callback: Optional[Callable]
    _hostip: str
    _call_executor: Optional[ThreadPoolExecutor]
    _encoding: str = "utf-8"

    def __init__(self) -> None:
        EndpointAdvertiser.__init__(self)
        EndpointSubscriber.__init__(self)
        # asyncio loop set in validate
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # lease_id and watch_id set during connection
        self._lease_id: Optional[int] = None
        self._watch_id: Optional[int] = None
        # task for doing keepalive requests setup during connect
        self._keepalive_task: Optional[asyncio.Task] = None
        # event is set in _connect and waited on by endpoint advertisers
        self._connected_event = asyncio.Event()

    def _get_session_path(self) -> str:
        return f"{self._top_key}/{self._session_id}"

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
        resp = await rpc_pb2_grpc.KVStub(self._channel).Range(rpc_pb2.RangeRequest(key=to_bytes(key)))
        if resp.kvs and len(resp.kvs) > 0:
            return str(resp.kvs.pop().value, self._encoding)

    def _get_value(self, endpoint_id: str) -> str:
        return self._run_coroutine(self._get_key_value(endpoint_id))

    # entry point method
    @ValidateComponent()
    def _validate_component(self) -> None:
        # setup service name and service_props
        servicename = f"osgirsvc_{self._session_id}"
        self._service_props = {
            "location": f"ecfosgisvc://{self._hostip}:32565/{servicename}",
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
        # create new event loop
        self._loop = asyncio.new_event_loop()

        # setup connected callback for asyncio thread
        async def connected():
            # wait until we get thec onnected event set
            await self._connected_event.wait()
            _logger.debug("CONNECTED etcd3 session_id=%s to host=%s port=%s", self._session_id, self._hostname, self._port)
            if self._connected_callback:
                self._connected_callback()

        # define working for our asyncio thread
        def worker():
            asyncio.set_event_loop(self._loop)
            self._loop_thread_id = threading.current_thread().ident
            asyncio.run_coroutine_threadsafe(connected(), self._loop)
            self._loop.run_until_complete(self._connect())

        # create and start thread
        threading.Thread(target=worker, name="etcd3[{}]".format(self._session_id), daemon=True).start()

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
        return self._top_key

    def _get_session_key(self):
        return "/".join([self._get_key_prefix(), self._session_id])

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
            _logger.debug("session_id=%s removed endpoint description with=%s ", self._session_id, endpoint_key)
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
                    "session_id=%s added endpoint key=%s value=%s", self._session_id, endpoint_key, value
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
                        "session_id=%s modified endpoint key=%s value=%s", self._session_id, endpoint_key, value
                    )
        # fire event outside lock
        self._fire_endpoint_event(event_type, new_ed)

    def _process_kv(self, key: str, value: str, add_remove: bool):
        endpoint_key = self._create_endpoint_key(key)
        # only do anything if valid endpoint_key and not our sessionid
        if endpoint_key and not endpoint_key.sessionid == self._session_id:
            if add_remove and value:
                self._add_or_modify_endpoint(endpoint_key, value)
            else:
                self._remove_endpoint(endpoint_key)

    def _fire_endpoint_event(self, event_type:int, ed:EndpointDescription) -> None:  #
        # send notifications via thread so doesn't block asyncio loop thread
        self._loop.run_in_executor(self._call_executor, EndpointSubscriber._fire_endpoint_event, self, event_type, ed)

    async def _putKV(self, key, value) -> rpc_pb2.PutResponse:
        return await rpc_pb2_grpc.KVStub(self._channel).Put(rpc_pb2.PutRequest(key=to_bytes(key), value=to_bytes(value), lease=self._lease_id))

    def _create_async_channel(self) -> grpc.Channel:
        target = "{}:{}".format(self._hostname, self._port)
        if self._grpc_credentials:
            return grpc.aio.secure_channel(target, self._grpc_credentials, self._grpc_options, self._grpc_compression)
        else:
            return grpc.aio.insecure_channel(target, self._grpc_options, self._grpc_compression)

    async def _request_lease(self) -> None:
        resp = await rpc_pb2_grpc.LeaseStub(self._channel).LeaseGrant(rpc_pb2.LeaseGrantRequest(TTL=self._lease_ttl))
        if resp.error:
            _logger.error("session_id={} request_lease error={}".format(self._session_id, resp.error))
            await self._disconnect()
        self._lease_id = resp.ID
        self._lease_ttl = resp.TTL

        async def keepalive():

            async def generate_ka_request():
                while True:
                    try:
                        await asyncio.sleep(self._keepalive_interval)
                    except asyncio.exceptions.CancelledError:
                        return
                    if self._lease_id:
                        yield rpc_pb2.LeaseKeepAliveRequest(ID=self._lease_id)
                    else:
                        return

            async for resp in rpc_pb2_grpc.LeaseStub(self._channel).LeaseKeepAlive(generate_ka_request()):
                if resp.ID == self._lease_id and resp.TTL:
                    self._lease_ttl = resp.TTL

        # keep alive task is created  here
        if not self._keepalive_task:
            self._keepalive_task = self._loop.create_task(keepalive())

    def _generate_watch_request(self, create_request: rpc_pb2.WatchCreateRequest, cancel_request: rpc_pb2.WatchCancelRequest) -> Iterable[rpc_pb2.WatchRequest]:
        yield rpc_pb2.WatchRequest(create_request=create_request, cancel_request=None)

    async def _connect(self) -> None:
        # create channel
        self._channel = self._create_async_channel()
        # create lease and start keepalive
        await self._request_lease()
        # we are now connected so notify by setting self._connected_event
        kp = self._get_key_prefix()
        kp_bytes = to_bytes(kp)
        kp_range_end_bytes = to_bytes("".join([kp, "\\0"]))
        range_resp = await rpc_pb2_grpc.KVStub(self._channel).Range(rpc_pb2.RangeRequest(key=kp_bytes, range_end=kp_range_end_bytes))
        for kv in range_resp.kvs:
            self._process_kv(str(kv.key, self._encoding), str(kv.value, self._encoding), True)
        # Now announce us as present by putting key on etcd server
        await self._putKV(self._get_session_key(), self._session_id)

        async for watch_response in rpc_pb2_grpc.WatchStub(self._channel).Watch(self._generate_watch_request(rpc_pb2.WatchCreateRequest(key=kp_bytes, range_end=kp_range_end_bytes), None)):
            if watch_response.created:
                self._watch_id = watch_response.watch_id
                self._connected_event.set()
            elif watch_response.canceled:
                _logger.error("session_id={} watch_cancelled ".format(self._session_id))
                return
            else:
                for event in watch_response.events:
                    key = str(event.kv.key, self._encoding)
                    value = str(event.kv.value, self._encoding)
                    from .etcdrpc.kv_pb2 import Event
                    if key:
                        if event.type == Event.EventType.PUT:
                            self._process_kv(key, value, True)
                        elif event.type == Event.EventType.DELETE:
                            self._process_kv(key, value, False)

    async def _delete_range(self, key: str) -> rpc_pb2.DeleteRangeResponse:
        await self._connected_event.wait()
        return await rpc_pb2_grpc.KVStub(self._channel).Range(rpc_pb2.DeleteRangeRequest(key=to_bytes(key), range_end=to_bytes("".join([key, "\\0"]))))

    async def _disconnect(self) -> None:
        """
        Disconnects the etcd3 client
        """
        if self._lease_id:
            await self._connected_event.wait()
            if self._keepalive_task:
                self._keepalive_task.cancel("keepalive canceled")
                self._keepalive_task = None
                _logger.debug("session_id={} keepalive canceled".format(self._session_id))

            await self._delete_range(self._get_session_path())
            _logger.debug("session_id={} range deleted".format(self._session_id))
            await rpc_pb2_grpc.LeaseStub(self._channel).LeaseRevoke(rpc_pb2.LeaseRevokeRequest(ID=self._lease_id))
            _logger.debug("session_id={} lease_id={} revoked".format(self._session_id, self._lease_id))
            self._lease_id = None

            await self._channel.close()
            _logger.debug("session_id={} closed channel".format(self._session_id))
            self._channel = None


def instantiate_etcd3_discovery_provider(context: BundleContext, properties: Optional[Dict[str, Any]]=None):
    from pelix.rsa import instantiate_rsa_component
    return instantiate_rsa_component(context, ETCD_FACTORY_NAME, ETCD_INSTANCE_NAME, properties)
