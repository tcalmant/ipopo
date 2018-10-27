#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: ZooKeeper-based discovery and event notification

*Note:* This discovery package requires the ``kazoo`` package (available on
PyPI), and a ZooKeeper server.

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Thomas Calmant

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
import posixpath
import socket
import threading
import uuid

# ZooKeeper library
from kazoo.client import KazooClient, KazooState, EventType
from kazoo.exceptions import KazooException, NodeExistsError

# iPOPO decorators
from pelix.ipopo.decorators import (
    ComponentFactory,
    Requires,
    Provides,
    Invalidate,
    Validate,
    Property,
)

# Pelix utilities
import pelix.constants
from pelix.utilities import to_bytes, to_str
from pelix.threadpool import ThreadPool

# Remote services
from pelix.remote.edef_io import EDEFWriter, EDEFReader
import pelix.remote
import pelix.remote.beans as beans

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

_logger = logging.getLogger(__name__)
""" Module's logger """

FRAMEWORKS_ROOT = "/frameworks"
""" Path to the Z-node parent of frameworks definition Z-node """

ENDPOINTS_ROOT = "/endpoints"
""" Path to the Z-node containing the endpoints of each framework """

# ------------------------------------------------------------------------------


class ZooKeeperClient:
    """
    Handles basic ZooKeeper events
    """

    def __init__(self, zk_hosts, log_name="ZooKeeperClient", prefix=""):
        """
        :param zk_hosts: List of ZooKeepers hosts
        :param log_name: Name of the logger to use
        :param prefix: Prefix to all paths
        """
        self._zk = KazooClient(zk_hosts)
        self._zk.add_listener(self.__conn_listener)
        self.__prefix = prefix

        # Session state
        self.__connected = False
        self.__online = False
        self.__stop = False

        # Notification queue
        self._logger = logging.getLogger(log_name)
        self._queue = ThreadPool(1, 1, logname=log_name)

    @property
    def prefix(self):
        """
        Prefix to all ZooKeeper nodes
        """
        return self.__prefix

    @property
    def connected(self):
        """
        ZooKeeper client state: connected to the quorum
        """
        return self.__connected

    @property
    def online(self):
        """
        ZooKeeper client state: connected & online (session active)
        """
        return self.__online

    @property
    def stopped(self):
        """
        ZooKeeper client status (stop requested)
        """
        return self.__stop

    def __conn_listener(self, state):
        """
        Connection event listener

        :param state: The new connection state
        """
        if state == KazooState.CONNECTED:
            self.__online = True
            if not self.__connected:
                self.__connected = True
                self._logger.info("Connected to ZooKeeper")
                self._queue.enqueue(self.on_first_connection)
            else:
                self._logger.warning("Re-connected to ZooKeeper")
                self._queue.enqueue(self.on_client_reconnection)
        elif state == KazooState.SUSPENDED:
            self._logger.warning("Connection suspended")
            self.__online = False
        elif state == KazooState.LOST:
            self.__online = False
            self.__connected = False

            if self.__stop:
                self._logger.info("Disconnected from ZooKeeper (requested)")
            else:
                self._logger.warning("Connection lost")

    def start(self):
        """
        Starts the connection
        """
        self.__stop = False
        self._queue.start()
        self._zk.start()

    def stop(self):
        """
        Stops the connection
        """
        self.__stop = True
        self._queue.stop()
        self._zk.stop()

    @staticmethod
    def on_first_connection():
        """
        Called when the client is connected for the first time
        """
        pass

    @staticmethod
    def on_client_reconnection():
        """
        Called when the client is reconnected to the server
        """
        pass

    def __path(self, path):
        """
        Adds the prefix to the given path

        :param path: Z-Path
        :return: Prefixed Z-Path
        """
        if path.startswith(self.__prefix):
            return path

        return "{}{}".format(self.__prefix, path)

    def create(self, path, data, ephemeral=False, sequence=False):
        """
        Creates a ZooKeeper node

        :param path: Z-Path
        :param data: Node Content
        :param ephemeral: Ephemeral flag
        :param sequence: Sequential flag
        """
        return self._zk.create(
            self.__path(path), data, ephemeral=ephemeral, sequence=sequence
        )

    def ensure_path(self, path):
        """
        Ensures that a path exists, creates it if necessary

        :param path: Z-Path
        """
        return self._zk.ensure_path(self.__path(path))

    def get(self, path, watch=None):
        """
        Gets the content of a ZooKeeper node

        :param path: Z-Path
        :param watch: Watch method
        """
        return self._zk.get(self.__path(path), watch=watch)

    def get_children(self, path, watch=None):
        """
        Gets the list of children of a node

        :param path: Z-Path
        :param watch: Watch method
        """
        return self._zk.get_children(self.__path(path), watch=watch)

    def set(self, path, data):
        """
        Sets the content of a ZooKeeper node

        :param path: Z-Path
        :param data: New content
        """
        return self._zk.set(self.__path(path), data)

    def delete(self, path):
        """
        Deletes a node

        :param path: Z-Path
        """
        return self._zk.delete(self.__path(path))


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.remote.FACTORY_DISCOVERY_ZOOKEEPER)
@Provides(
    pelix.remote.SERVICE_EXPORT_ENDPOINT_LISTENER, controller="_controller"
)
@Requires("_dispatcher", pelix.remote.SERVICE_DISPATCHER)
@Requires("_registry", pelix.remote.SERVICE_REGISTRY)
@Property("_prefix", "zookeeper.prefix", "/pelix")
@Property("_zk_hosts", "zookeeper.hosts", "localhost:2181")
class ZooKeeperDiscovery(object):
    """
    Pelix Remote Service discovery provider based on ZooKeeper
    """

    def __init__(self):
        # Requirements
        self._dispatcher = None
        self._registry = None

        # Properties
        self._controller = False
        self._prefix = None
        self._zk_hosts = None
        self._zk = None  # type: ZooKeeperClient

        # Framework properties
        self._fw_uid = None

        # Session state
        self.__uuid = str(uuid.uuid4())
        self.__master = threading.Event()

        # Keep track of frameworks hosts
        self._frameworks_hosts = {}

    @Validate
    def _validate(self, context):
        """
        Component validated
        """
        self._controller = False

        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Check configuration
        if not self._zk_hosts:
            raise ValueError("ZooKeeper hosts configuration is missing")

        # Start ZooKeeper client
        self._zk = ZooKeeperClient(self._zk_hosts, _logger.name, self._prefix)
        self._zk.on_first_connection = self._on_first_connection
        self._zk.start()
        _logger.debug("ZooKeeper Discovery validated")

    @staticmethod
    def _endpoint_path(fw_uid, endpoint_uid):
        # type: (str, str) -> str
        """
        Returns the path to the given endpoint

        :param fw_uid: Framework UID (host of endpoint)
        :param endpoint_uid: Endpoint UID
        :return: The path to the endpoint Z-node
        """
        return posixpath.join(ENDPOINTS_ROOT, fw_uid, endpoint_uid)

    @staticmethod
    def _endpoints_path(fw_uid):
        # type: (str) -> str
        """
        Returns the path to the endpoints parent Z-node for the given framework

        :param fw_uid: Framework UID (host of endpoints)
        :return: The path to the endpoints Z-node
        """
        return posixpath.join(ENDPOINTS_ROOT, fw_uid)

    @staticmethod
    def _framework_path(fw_uid):
        # type: (str) -> str
        """
        Returns the path to the framework Z-node

        :param fw_uid: Framework UID
        :return: The path to the framework Z-node
        """
        return posixpath.join(FRAMEWORKS_ROOT, fw_uid)

    @Invalidate
    def _invalidate(self, _):
        """
        Component invalidated
        """
        self._controller = False

        # Clean up properly
        self._clear_framework(self._fw_uid)

        # Stop the Kazoo Client
        self._zk.stop()

    def _clear_framework(self, fw_uid):
        # type: (str) -> None
        """
        Clears all references to the given framework

        :param fw_uid: A framework UID
        """
        # Clear all endpoints
        fw_endpoints_path = self._endpoints_path(fw_uid)
        try:
            # Get the list of endpoints for the given framework
            endpoints = self._zk.get_children(fw_endpoints_path)
        except KazooException:
            # Already done
            pass
        else:
            for endpoint_uid in endpoints:
                try:
                    # Delete each endpoint
                    self._zk.delete(self._endpoint_path(fw_uid, endpoint_uid))
                except KazooException:
                    # Already done
                    pass

        # Clear remaining paths
        for root_path in (fw_endpoints_path, self._framework_path(fw_uid)):
            try:
                self._zk.delete(root_path)
            except KazooException:
                # Already done
                pass

    def _on_first_connection(self):
        """
        Called on first connection to ZooKeeper
        """
        _logger.debug("Connected to ZooKeeper")

        # Ensure paths
        for path in (
            FRAMEWORKS_ROOT,
            ENDPOINTS_ROOT,
            self._endpoints_path(self._fw_uid),
        ):
            self._zk.ensure_path(path)

        # Register the framework
        self._register_framework()

        # Listen to local events
        self._controller = True

    def _register_framework(self):
        """
        Registers the framework and its current services in Redis
        """
        # The framework key
        fw_node = self._framework_path(self._fw_uid)

        # The host name
        hostname = socket.gethostname()
        if hostname == "localhost":
            logging.warning(
                "Hostname is '%s': this will be a problem for "
                "multi-host remote services",
                hostname,
            )

        # Prepare an ephemeral Z-Node
        self._zk.create(fw_node, to_bytes(hostname), True)

        # Load existing services
        self._load_existing_endpoints()

        # Register all already exported services
        for endpoint in self._dispatcher.get_endpoints():
            self._register_service(endpoint)

    def _cache_fw_host(self, fw_uid):
        # type: (str) -> str
        """
        Gets the host name associated to a framework. Caches it if necessary.
        Also, adds a watcher on the framework Z-Node

        :param fw_uid: UID of a framework
        :return: The framework host name
        """
        try:
            return self._frameworks_hosts[fw_uid]
        except KeyError:
            fw_host = self._frameworks_hosts[fw_uid] = to_str(
                self._zk.get(
                    self._framework_path(fw_uid), self._on_framework_event
                )[0]
            )
            return fw_host

    def __read_endpoint(self, path):
        # type: (str) -> beans.EndpointDescription
        """
        Reads the description of an endpoint at the given Z-Node path.
        Also set the endpoint event listener on the node.

        :param path: Path to the Z-Node describing the endpoint
        :return: An EndpointDescription bean
        """
        return EDEFReader().parse(
            to_str(self._zk.get(path, self._on_endpoint_event)[0])
        )[0]

    def _load_existing_endpoints(self):
        """
        Loads already-registered endpoints
        """
        # Get the list of frameworks
        frameworks = self._zk.get_children(
            FRAMEWORKS_ROOT, watch=self._on_frameworks_event
        )

        for fw_uid in frameworks:
            # Avoid ourselves
            if fw_uid == self._fw_uid:
                continue

            # Store the host name of this framework
            self._cache_fw_host(fw_uid)

            # List all endpoints of this framework
            endpoints = self._zk.get_children(
                self._endpoints_path(fw_uid), self._on_fw_endpoints_event
            )

            for endpoint_uid in endpoints:
                # Get JSON description
                endpoint = self.__read_endpoint(
                    self._endpoint_path(fw_uid, endpoint_uid)
                )

                # Register the remote service
                self._register_remote(endpoint)

    def _register_service(self, endpoint):
        # type: (beans.ExportEndpoint) -> None
        """
        Register a local endpoint

        :param endpoint: A local endpoint
        """
        # Prepare node content
        path = self._endpoint_path(self._fw_uid, endpoint.uid)
        data = to_bytes(
            EDEFWriter().to_string(
                [beans.EndpointDescription.from_export(endpoint)]
            )
        )

        try:
            try:
                # Create an ephemeral node
                self._zk.create(path, data, True)
            except NodeExistsError:
                # Service already exists: update it
                self._zk.set(path, data)
        except KazooException as ex:
            _logger.warning(
                "Error registering local service: %s", type(ex).__name__
            )

    def _unregister_service(self, endpoint):
        # type: (beans.ExportEndpoint) -> None
        """
        Unregisters an endpoint from Redis

        :param endpoint: A :class:`~pelix.remote.ExportEndpoint` object
        """
        try:
            self._zk.delete(self._endpoint_path(self._fw_uid, endpoint.uid))
        except KazooException as ex:
            _logger.error("Error unregistering service %s:", ex)

    def endpoints_added(self, endpoints):
        # type: (list) -> None
        """
        Multiple endpoints have been added

        :param endpoints: A list of ExportEndpoint beans
        """
        for endpoint in endpoints:  # type: beans.ExportEndpoint
            self._register_service(endpoint)

    def endpoint_updated(self, endpoint, _):
        # type: (beans.ExportEndpoint, dict) -> None
        """
        An end point is updated

        :param endpoint: The updated endpoint
                         (:class:`~pelix.remote.ExportEndpoint`)
        :param _: Previous end point properties (not used)
        """
        # Update and registration are the same with Redis
        self._register_service(endpoint)

    def endpoint_removed(self, endpoint):
        # type: (beans.ExportEndpoint) -> None
        """
        An end point is removed

        :param endpoint: :class:`~pelix.remote.ExportEndpoint` being removed
        """
        self._unregister_service(endpoint)

    def _register_remote(self, endpoint_desc):
        # type: (beans.EndpointDescription) -> bool
        """
        Registers a discovered remote endpoint

        :param endpoint_desc: A remote endpoint description
        """
        # Get the host of the parent framework
        fw_uid = endpoint_desc.get_framework_uuid()
        fw_host = self._cache_fw_host(fw_uid)

        # Register the endpoint
        endpoint = endpoint_desc.to_import()
        endpoint.server = fw_host
        if self._registry.contains(endpoint):
            # Update endpoint
            self._registry.update(endpoint.uid, endpoint.properties)
        else:
            # New endpoint
            self._registry.add(endpoint)
        return True

    def _on_frameworks_event(self, event):
        # type: (WatchedEvent) -> None
        """
        Handles an event on the Frameworks Z-node
        """
        if event.type == EventType.CHILD:
            self.__check_frameworks()
        else:
            # Reset the listener in any case
            self._zk.get(event.path, self._on_frameworks_event)

    def _on_framework_event(self, event):
        # type: (WatchedEvent) -> None
        """
        Handles an event on a framework's Z-node
        """
        if event.type == EventType.CHANGED:
            _logger.warning("Unhandled change of host name for a framework")
        elif event.type == EventType.DELETED:
            # Framework is gone
            fw_uid = event.path.rsplit("/", 1)[-1]
            self._registry.lost_framework(fw_uid)
        else:
            # Reset the listener in any case
            self._zk.get(event.path, self._on_framework_event)

    def __check_frameworks(self):
        """
        Checks the list of frameworks in ZooKeeper
        """
        try:
            # Get the list of frameworks
            frameworks = self._zk.get_children(
                FRAMEWORKS_ROOT, watch=self._on_frameworks_event
            )
        except KazooException:
            # Error reading the list of frameworks
            _logger.warning("Error looking for new frameworks")
            return

        # Find delta with our current state
        to_add = set(frameworks) - set(self._frameworks_hosts) - {self._fw_uid}
        to_del = set(self._frameworks_hosts) - set(frameworks)

        # Consider frameworks lost (the registry will handle the endpoints)
        for fw_uid in to_del:
            del self._frameworks_hosts[fw_uid]
            self._registry.lost_framework(fw_uid)

        # Get the host names of the new frameworks
        for fw_uid in to_add:
            self._cache_fw_host(fw_uid)

            endpoints = self._zk.get_children(
                self._endpoints_path(fw_uid), self._on_fw_endpoints_event
            )

            for endpoint_uid in endpoints:
                endpoint = self.__read_endpoint(
                    self._endpoint_path(fw_uid, endpoint_uid)
                )
                self._register_remote(endpoint)

    def _on_fw_endpoints_event(self, event):
        # type: (WatchedEvent) -> None
        """
        Handles an event on the endpoints Z-node of a framework
        """
        if event.type == EventType.CHILD:
            fw_uid = event.path.rsplit("/", 1)[-1]
            self.__check_framework_endpoints(fw_uid)
        elif event.type != EventType.DELETED:
            # Reset the listener in any case
            self._zk.get(event.path, self._on_fw_endpoints_event)

    def _on_endpoint_event(self, event):
        # type: (WatchedEvent) -> None
        """
        Handles an event on an endpoint Z-node
        """
        if event.type == EventType.CHANGED:
            # Endpoint updated
            endpoint = self.__read_endpoint(event.path)
            self._register_remote(endpoint)
        elif event.type == EventType.DELETED:
            # Endpoint deleted
            endpoint_uid = event.path.rsplit("/", 1)[-1]
            self._registry.remove(endpoint_uid)

    def __check_framework_endpoints(self, fw_uid):
        # type: (str) -> None
        """
        Checks the list of endpoints for a framework in ZooKeeper
        """
        try:
            # Get the list of frameworks
            endpoints = self._zk.get_children(
                self._endpoints_path(fw_uid), self._on_fw_endpoints_event
            )
        except KazooException:
            # No more endpoints for this framework
            return

        for endpoint_uid in endpoints:
            if not self._registry.contains(endpoint_uid):
                try:
                    # New endpoint found
                    self._register_remote(
                        self.__read_endpoint(
                            self._endpoint_path(fw_uid, endpoint_uid)
                        )
                    )
                except KazooException:
                    logging.warning(
                        "Error reading endpoint %s of framework %s",
                        fw_uid,
                        endpoint_uid,
                    )
