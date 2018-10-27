#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Etcd Discovery Provider

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0
:version: 0.8.1

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

from threading import Thread, RLock
import logging
import json
import socket
import time

try:
    # pylint: disable=W0611
    from typing import List
except ImportError:
    pass

import etcd

from pelix.ipopo.decorators import (
    ComponentFactory,
    Provides,
    Instantiate,
    ValidateComponent,
    Property,
    Invalidate,
)

from pelix.rsa import create_uuid, prop_dot_suffix
from pelix.rsa.endpointdescription import (
    encode_endpoint_props,
    decode_endpoint_props,
    EndpointDescription,
)
from pelix.rsa.providers.discovery import (
    SERVICE_ENDPOINT_ADVERTISER,
    EndpointAdvertiser,
    EndpointEvent,
    EndpointSubscriber,
)

# ------------------------------------------------------------------------------
# Module version

__version_info__ = (0, 8, 1)
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


@ComponentFactory("etcd-endpoint-discovery-factory")
@Provides(SERVICE_ENDPOINT_ADVERTISER)
@Property(
    "_hostname",
    prop_dot_suffix(ETCD_NAME_PROP, ETCD_HOSTNAME_PROP),
    "localhost",
)
@Property("_port", prop_dot_suffix(ETCD_NAME_PROP, ETCD_PORT_PROP), 2379)
@Property(
    "_top_path",
    prop_dot_suffix(ETCD_NAME_PROP, ETCD_TOPPATH_PROP),
    "/org.eclipse.ecf.provider.etcd.EtcdDiscoveryContainer",
)
@Property(
    "_session_ttl", prop_dot_suffix(ETCD_NAME_PROP, ETCD_SESSIONTTL_PROP), 30
)
@Property(
    "_watch_start_wait",
    prop_dot_suffix(ETCD_NAME_PROP, ETCD_WATCHSTART_WAIT_PROP),
    5,
)
@Instantiate("etcd-endpoint-discovery")
class EtcdEndpointDiscovery(EndpointAdvertiser, EndpointSubscriber):
    """
    Etcd-based endpoint discovery.  Extends both EndpointAdvertiser
    and EndpointSubscriber so can be called to advertise/unadvertise
    exported endpoints, and will notify SERVICE_ENDPOINT_LISTENERs
    when an endpoint has been discovered via the etcd service.

    Note that this depends upon the python-etcd client library.
    """

    REMOVE_ACTIONS = ["delete", "expire"]
    ADD_ACTIONS = ["set", "create"]

    def __init__(self):
        EndpointAdvertiser.__init__(self)
        EndpointSubscriber.__init__(self)
        self._hostname = self._port = self._top_path = None
        self._sessionid = create_uuid()
        self._session_ttl = self._watch_start_wait = None
        self._client = None  # type: etcd.Client
        self._client_lock = RLock()
        self._top_nodes = (
            self._wait_index
        ) = self._ttl_thread = self._watch_thread = None
        servicename = "osgirsvc_{0}".format(create_uuid())
        hostip = socket.gethostbyname(socket.gethostname())
        self._service_props = {
            "location": "ecfosgisvc://{0}:32565/{1}".format(
                hostip, servicename
            ),
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
    def _validate_component(self):
        # now connect
        self._connect()

    @Invalidate
    def _invalidate(self, _):
        self._disconnect()

    def _encode_description(self, endpoint_description):
        # type: (EndpointDescription) -> dict
        encoded_props = encode_endpoint_props(endpoint_description)
        # get copy of service props
        service_props = self._service_props.copy()
        # set 'properties field'
        service_props["properties"] = [
            {"type": "string", "name": key, "value": encoded_props.get(key)}
            for key in encoded_props
        ]
        return service_props

    def _write_description(self, endpoint_description):
        # type: (EndpointDescription) -> etcd.EtcdResult
        # encode props as string -> string
        service_props = self._encode_description(endpoint_description)
        # dump service_props to json
        props_json = json.dumps(service_props)
        # write to etcd
        with self._client_lock:
            return self._client.write(
                key=self._get_endpoint_path(endpoint_description.get_id()),
                value=props_json,
            )

    # implementation of EndpointAdvertiser service.  These methods
    # are called when (e.g.) RSA asks us to advertise/unadvertise
    # an endpoint_description
    def _advertise(self, endpoint_description):
        # type: (EndpointDescription) -> etcd.EtcdResult
        _logger.debug("advertising ed=%s", endpoint_description)
        return self._write_description(endpoint_description)

    def _update(self, endpoint_description):
        # type: (EndpointDescription) -> etcd.EtcdResult
        _logger.debug("updating ed=%s", endpoint_description)
        return self._write_description(endpoint_description)

    def _unadvertise(self, advertised):
        # type: (List[EndpointDescription]) -> etcd.EtcdResult
        _logger.debug("unadvertising ed=%s", advertised[0])
        # get endpoint id
        endpointid = advertised[0].get_id()
        # write to etcd
        with self._client_lock:
            return self._client.delete(key=self._get_endpoint_path(endpointid))

    def _get_session_path(self):
        # type: () -> str
        return "{0}/{1}".format(self._top_path, self._sessionid)

    def _get_endpoint_path(self, endpointid):
        # type: (str) -> str
        return "{0}/{1}".format(self._get_session_path(), endpointid)

    def _disconnect(self):
        """
        Disconnects the etcd client
        """
        with self._client_lock:
            if self._client:
                session_path = self._get_session_path()
                try:
                    self._client.delete(session_path, True, True)
                except Exception:
                    _logger.exception(
                        "Exception deleting session_path=%s", session_path
                    )
                self._client = None

    def _connect(self):
        """
        Connects to etcd
        """
        with self._client_lock:
            if self._client:
                raise Exception("already connected")
            # create etcd Client instance
            self._client = etcd.Client(host=self._hostname, port=self._port)
            # now make request against basic
            try:
                top_response = self._client.read(self._top_path, recursive=True)
            except etcd.EtcdKeyNotFound:
                # if this happens, attempt to write it
                try:
                    top_response = self._client.write(
                        self._top_path, None, None, True
                    )
                except Exception as e:
                    _logger.exception(
                        "Exception attempting to create top dir=%s",
                        self._top_path,
                    )
                    raise e
            # set top nodes with list comprehension base top_response subtree
            self._top_nodes = [
                x
                for x in list(top_response.get_subtree())
                if x.dir and x.key != self._top_path
            ]
            try:
                session_exists_result = self._client.write(
                    key=self._get_session_path(),
                    value=None,
                    ttl=self._session_ttl,
                    dir=True,
                    prevExist=False,
                )
            except Exception as e:
                _logger.exception(
                    "Exception creating session for client at session_path=%s",
                    self._get_session_path(),
                )
                raise e

            # Note: error disabled as EtcdResult object is too dynamic
            # pylint: disable=E1101
            self._wait_index = session_exists_result.createdIndex + 1
            self._ttl_thread = Thread(target=self._ttl_job, name="Etcd TTL Job")
            self._ttl_thread.daemon = True
            self._watch_thread = Thread(
                target=self._watch_job, name="Etcd Listen Job"
            )
            self._watch_thread.daemon = True
            self._ttl_thread.start()
            self._watch_thread.start()

    def _get_start_wait(self):
        # type: () -> int
        return int(self._session_ttl - (self._session_ttl / 10))

    def _handle_add_dir(self, dir_node):
        sessionid = dir_node.key[len(self._top_path) + 1 :]
        _logger.debug("_handle_add_dir sessionid=%s", sessionid)
        self._handle_add_nodes(
            sessionid,
            [node for node in list(dir_node.children) if not node.dir],
        )

    def _handle_remove_dir(self, sessionid):
        _logger.debug("_handle_remove_dir sessionid=%s", sessionid)
        endpointids = self._get_endpointids_for_sessionid(sessionid)
        self._handle_remove_nodes(endpointids)

    def _handle_add_nodes(self, sessionid, nodes):
        for node in nodes:
            # we only care about properties
            node_val = node.value
            if node_val:
                json_obj = json.loads(node_val)
                if isinstance(json_obj, dict):
                    json_properties = json_obj["properties"]
                    # get the name and value from each entry
                    raw_props = {
                        entry["name"]: entry["value"]
                        for entry in json_properties
                        if entry["type"] == "string"
                    }
                    # decode
                    decoded_props = decode_endpoint_props(raw_props)
                    new_ed = EndpointDescription(properties=decoded_props)
                    old_ed = self._has_discovered_endpoint(new_ed.get_id())
                    if not old_ed:
                        # add discovered endpoint to our internal list
                        self._add_discovered_endpoint(sessionid, new_ed)
                        # dispatch
                        self._fire_endpoint_event(EndpointEvent.ADDED, new_ed)
                    else:
                        # get timestamp and make sure new one is newer (an
                        # update)
                        old_ts = old_ed.get_timestamp()
                        new_ts = new_ed.get_timestamp()
                        if new_ts > old_ts:
                            self._remove_discovered_endpoint(old_ed.get_id())
                            self._add_discovered_endpoint(sessionid, new_ed)
                            self._fire_endpoint_event(
                                EndpointEvent.MODIFIED, new_ed
                            )

    def _handle_remove_nodes(self, endpointids):
        for endpointid in endpointids:
            self._handle_remove_node(endpointid)

    def _handle_remove_node(self, endpointid):
        ed = self._remove_discovered_endpoint(endpointid)
        if ed:
            self._fire_endpoint_event(EndpointEvent.REMOVED, ed)

    def _watch_job(self):
        # sleep for a few seconds to allow endpoint listeners to be
        # asynchronously added before the top nodes are processed
        time.sleep(5)
        # first thing is to process the existing nodes from connect
        if self._top_nodes:
            # guaranteed to be directory
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
                result = client.read(
                    key=self._top_path,
                    recursive=True,
                    wait=True,
                    waitIndex=self._wait_index,
                )

                # reset wait_index
                # Note: error disabled as EtcdResult object is too dynamic
                # pylint: disable=E1101
                self._wait_index = result.modifiedIndex + 1
                key = result.key
                action = result.action
                if key.endswith(self._sessionid):
                    if action == "delete":
                        _logger.debug(
                            "watch_job: session dir deleted...exiting"
                        )
                        # we are done
                        return
                else:
                    # split id into [sessionid] or [sessionid,endpointid]
                    splitid = key[len(self._top_path) + 1 :].split("/")
                    sessionid = splitid[0]
                    # only process sessionids that are not ours
                    if self._sessionid != sessionid:
                        # if length of splitid list is > 1 then it's a leaf
                        # node
                        if len(splitid) > 1:
                            endpointid = splitid[len(splitid) - 1]
                            if action in self.REMOVE_ACTIONS:
                                self._handle_remove_node(endpointid)
                            elif action in self.ADD_ACTIONS:
                                self._handle_add_nodes(sessionid, [result])
                        # otherwise it's a branch/dir node
                        else:
                            if action in self.REMOVE_ACTIONS:
                                self._handle_remove_dir(sessionid)
                            elif action in self.ADD_ACTIONS:
                                self._handle_add_dir(result)

            except Exception:
                _logger.exception("watch_job:Exception in watch loop")

    def _ttl_job(self):
        waittime = self._get_start_wait()
        while True:
            _logger.debug("ttl_job: starting sleep with waittime=%s", waittime)
            time.sleep(1)
            with self._client_lock:
                client = self._client
            if not client:
                _logger.debug("ttl_job: exiting")
                return
            waittime -= 1
            _logger.debug(
                "ttl_job: testing waittime <= 0 with waittime=%s", waittime
            )
            if waittime <= 0:
                try:
                    session_ttl = self._session_ttl
                    _logger.debug(
                        "ttl_job: updating with session_ttl=%s", session_ttl
                    )
                    with self._client_lock:
                        if self._client:
                            self._client.write(
                                key=self._get_session_path(),
                                value=None,
                                ttl=session_ttl,
                                dir=True,
                                prevExist=True,
                            )
                    _logger.debug(
                        "ttl_job: updated with session_ttl=%s", session_ttl
                    )
                except Exception:
                    _logger.exception("Exception updating in ttl job")
                waittime = self._get_start_wait()
