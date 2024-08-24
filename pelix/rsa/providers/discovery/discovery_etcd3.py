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
import socket
import threading
from typing import Any, Dict, List, Optional, Tuple
import etcd3

from pelix.framework import BundleContext
from pelix.ipopo.decorators import (
    ComponentFactory,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    ValidateComponent,
)
from pelix.rsa import create_uuid, prop_dot_suffix
from pelix.rsa.endpointdescription import EndpointDescription, decode_endpoint_props, encode_endpoint_props
from pelix.rsa.providers.discovery import EndpointAdvertiser, EndpointEvent, EndpointSubscriber
from etcd3.etcdrpc.rpc_pb2 import WatchResponse
from threading import Timer
import uuid

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (3, 0, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Standard logging
_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

ETCD_NAME_PROP = "etcd"
ETCD_HOSTNAME_PROP = "hostname"
ETCD_PORT_PROP = "port"
ETCD_TOPPATH_PROP = "toppath"
ETCD_SESSIONTTL_PROP = "sessionttl"
ETCD_WATCHSTART_WAIT_PROP = "watchstartwait"

# ------------------------------------------------------------------------------


class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False


@ComponentFactory("etcd-endpoint-discovery-factory")
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
    "org.eclipse.ecf.provider.etcd3.Etcd3DiscoveryContainer",
)
@Property("_session_ttl", prop_dot_suffix(ETCD_NAME_PROP, ETCD_SESSIONTTL_PROP), 30)
@Property(
    "_watch_start_wait",
    prop_dot_suffix(ETCD_NAME_PROP, ETCD_WATCHSTART_WAIT_PROP),
    5,
)
@Instantiate("etcd-endpoint-discovery")
class Etcd3EndpointDiscovery(EndpointAdvertiser, EndpointSubscriber):
    """
    Etcd-based endpoint discovery.  Extends both EndpointAdvertiser
    and EndpointSubscriber so can be called to advertise/unadvertise
    exported endpoints, and will notify SERVICE_ENDPOINT_LISTENERs
    when an endpoint has been discovered via the etcd service.

    Note that this depends upon the python-etcd client library.
    """

    REMOVE_ACTIONS: List[str] = ["delete", "expire"]
    ADD_ACTIONS: List[str] = ["set", "create"]

    def __init__(self) -> None:
        EndpointAdvertiser.__init__(self)
        EndpointSubscriber.__init__(self)
        self._encoding = "utf-8"
        self._hostname: str = "localhost"
        self._port: int = 2379
        self._top_path: str = None
        self._sessionid = create_uuid()
        self._session_ttl: int = 30  # in seconds
        self._client: Optional[etcd3.Etcd3Client] = None
        self._lease: Optional[etcd3.Lease] = None
        self._lease_scheduler: Optional[etcd3.Lease] = None
        self._client_lock = threading.RLock()
        self._watch_id = None
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

    @ValidateComponent()
    def _validate_component(self) -> None:
        # now connect
        self._connect()

    @Invalidate
    def _invalidate(self, _: BundleContext) -> None:
        self._disconnect()

    def _encode_description(self, endpoint_description: EndpointDescription) -> Dict[str, Any]:
        encoded_props = encode_endpoint_props(endpoint_description)
        # get copy of service props
        service_props = self._service_props.copy()
        # set 'properties field'
        service_props["properties"] = [
            {"type": "string", "name": key, "value": encoded_props.get(key)} for key in encoded_props
        ]
        return service_props

    def _write_description(
        self, endpoint_description: EndpointDescription
    ) -> etcd3.etcdrpc.rpc_pb2.PutResponse:
        # encode props as string -> string
        service_props = self._encode_description(endpoint_description)
        # dump service_props to json
        props_json = json.dumps(service_props)
        # write to etcd
        with self._client_lock:
            if self._client is None:
                raise Exception("etcd client not available")

            return self._client.put(
                key=self._get_endpoint_path(endpoint_description.get_id()),
                value=props_json,
                lease=self._lease,
            )

    # implementation of EndpointAdvertiser service.  These methods
    # are called when (e.g.) RSA asks us to advertise/unadvertise
    # an endpoint_description
    def _advertise(self, endpoint_description: EndpointDescription) -> etcd3.etcdrpc.rpc_pb2.PutResponse:
        _logger.debug("advertising ed=%s", endpoint_description)
        return self._write_description(endpoint_description)

    def _update(self, endpoint_description: EndpointDescription) -> etcd3.etcdrpc.rpc_pb2.PutResponse:
        _logger.debug("updating ed=%s", endpoint_description)
        return self._write_description(endpoint_description)

    def _unadvertise(self, advertised: Tuple[EndpointDescription, Any]) -> etcd3.etcdrpc.rpc_pb2.PutResponse:
        _logger.debug("unadvertising ed=%s", advertised[0])
        # get endpoint id
        endpointid = advertised[0].get_id()
        # write to etcd
        with self._client_lock:
            if self._client is None:
                raise Exception("etcd client not available")
            return self._client.delete(key=self._get_endpoint_path(endpointid))

    def _get_session_path(self) -> str:
        return f"{self._top_path}/{self._sessionid}"

    def _get_endpoint_path(self, endpointid: str) -> str:
        return f"{self._get_session_path()}/{endpointid}"

    def _delete_all_prefix(self, key):
        delete_request = self._client._build_delete_request(key, "true\\0")
        return self._client.kvstub.DeleteRange(
            delete_request,
            self._client.timeout,
            credentials=self._client.call_credentials,
            metadata=self._client.metadata,
        )

    def _disconnect(self) -> None:
        """
        Disconnects the etcd client
        """
        with self._client_lock:
            if self._client:
                _logger.debug("sessid=%s disconnecting", self._sessionid)
                # cancel watch
                if self._watch_id != None:
                    try:
                        self._client.cancel_watch(self._watch_id)
                        self._watch_id = None
                    except Exception:
                        _logger.exception("Exception canceling watch_id=%s", self._watch_id)
                # stop lease scheduler and revoke our lease
                if self._lease:
                    if self._lease_scheduler:
                        self._lease_scheduler.stop()
                        self._lease_scheduler = None
                    self._lease.revoke()
                    self._lease = None

                if self._client:
                    self._client = None
                _logger.debug("sessid=%s disconnected", self._sessionid)

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
            if self._get_key_prefix()[1:] == split_key[0]:
                if self._sessionid == split_key[1]:
                    _logger.debug("Ignoring local sessionid=%s", split_key[1])
                else:
                    _logger.debug("Ignoring remote sessionid=%s", split_key[1])
            else:
                _logger.debug("Ignoring invalid keyprefix=%s", split_key[0])
            return None
        else:
            session_key = split_key[1]
            endpoint_key = split_key[2]
            try:
                uuid.UUID("urn:uuid:{}".format(session_key), version=4)
            except ValueError:
                _logger.debug(
                    "_create_endpoint_key error, GUID creation failed for sessionId=%s", session_key
                )
                return None
            return self.EndpointKey(session_key, endpoint_key)

    def _get_full_key(self, endpoint_fk):
        return "/".join([self._get_key_prefix(), endpoint_fk])

    def _remove_endpoint(self, endpoint_key: EndpointKey):
        _logger.debug("sessid=%s removing endpoint_key=%s", self._sessionid, endpoint_key)
        removed_ep = self._remove_discovered_endpoint(endpoint_key.ed_id)
        if removed_ep:
            _logger.debug("sessid=%s removed endpoint_key=%s ", self._sessionid, endpoint_key)
            self._fire_endpoint_event(EndpointEvent.REMOVED, removed_ep)
        else:
            _logger.debug("sessid=%s not removed endpoint_key=%s ", self._sessionid, endpoint_key)

    def _add_or_modify_endpoint(self, endpoint_key: EndpointKey, value: str):
        _logger.debug("sessid=%s adding endpoint_key=%s value=%s", self._sessionid, endpoint_key, value)
        # get actual value from endpoint key
        json_value = json.loads(value)
        json_properties = json_value["properties"]
        # get the name and value from each entry
        raw_props = {entry["name"]: entry["value"] for entry in json_properties if entry["type"] == "string"}
        # create new EndpointDescription from deserialized properties
        new_ed = EndpointDescription(properties=decode_endpoint_props(raw_props))
        event_type = EndpointEvent.ADDED
        with self._discovered_endpoints_lock:
            # check to see if already there
            old_ed = self._has_discovered_endpoint(new_ed.get_id())
            if not old_ed:
                # add discovered endpoint to our internal list
                self._add_discovered_endpoint(endpoint_key.sessionid, new_ed)
                _logger.debug(
                    "sessid=%s added endpoint_key=%s value=%s", self._sessionid, endpoint_key, value
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
                        "sessid=%s modified endpoint_key=%s value=%s", self._sessionid, endpoint_key, value
                    )
        # fire event outside lock
        self._fire_endpoint_event(event_type, new_ed)

    def _process_kv(self, key: str, value: str, add_remove: bool):
        endpoint_key = self._create_endpoint_key(key)
        # only do anything if valid endpoint_key and not our sessionid
        if endpoint_key and not endpoint_key.sessionid == self._sessionid:
            if add_remove:
                # handle add
                self._add_or_modify_endpoint(endpoint_key, value)
            else:
                # handle remove
                self._remove_endpoint(endpoint_key)

    # declare callback
    def _callback(self, resp: WatchResponse):
        with self._client_lock:
            if not self._client:
                return
            self._watch_callback(resp)

    def _watch_callback(self, resp: etcd3.watch.WatchResponse):
        if isinstance(resp, etcd3.watch.WatchResponse):
            for event in resp.events:
                key = str(event.key, self._encoding)
                value = str(event.value, self._encoding)
                if key and not key == "":
                    if isinstance(event, etcd3.events.PutEvent):
                        self._process_kv(key, value, True)
                    elif isinstance(event, etcd3.events.DeleteEvent):
                        self._process_kv(key, value, False)

    def _connect(self) -> None:
        """
        Connects to etcd
        """
        _logger.debug(
            "connecting sessid=%s to etcd3 host=%s port=%s", self._sessionid, self._hostname, self._port
        )
        with self._client_lock:
            if self._client:
                raise Exception(
                    "sessid={} already connected to etcd3 host={} port={}".format(
                        self._sessionid, self._hostname, self._port
                    )
                )
            # create etcd Client instance
            try:
                self._client = etcd3.client(host=self._hostname, port=self._port)
                # create lease and setup lease_scheduler
                self._lease = self._client.lease(self._session_ttl)
            except Exception as e:
                _logger.debug(
                    "sessid={} had exception on connect to etcd3 host={} port={}".format(
                        self._sessionid, self._hostname, self._port
                    )
                )
                raise e
            # start lease scheduler
            self._lease_scheduler = RepeatedTimer(self._session_ttl - 5, self._lease.refresh)
            # add watch
            self._watch_id = self._client.add_watch_callback(
                self._get_key_prefix(), self._callback, "true\\0"
            )
            # put our session key
            self._client.put(self._get_session_key(), self._sessionid, self._lease)
            # build range request to get all existing endpoint keys
            range_request = self._client._build_get_range_request(key=self._top_path, range_end="true\\0")
            # make the actual call
            resp = self._client.kvstub.Range(
                range_request,
                self._client.timeout,
                credentials=self._client.call_credentials,
                metadata=self._client.metadata,
            )
            # make sure is valid
            if resp:
                # iterate through all kvs
                for kv in resp.kvs:
                    # first create strings with encoding and call _process_kv
                    self._process_kv(str(kv.key, self._encoding), str(kv.value, self._encoding), True)
        _logger.debug(
            "connected sessid=%s to etcd3 host=%s port=%s", self._sessionid, self._hostname, self._port
        )
