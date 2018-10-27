#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Redis-based discovery and event notification

*Note:* This discovery package requires the ``redis`` package (available on
PyPI), and a Redis server.

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

# Ensure that the redis package is imported and not this module
from __future__ import absolute_import

# Standard library
import logging
import math
import socket
import threading

# Redis
import redis

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

# The module's logger
_logger = logging.getLogger(__name__)

PATTERN_FRAMEWORK_KEY = "pelix/remote/frameworks/{fw_uid}"
"""
Pattern of framework heartbeat key, with the following format entry:
* ``fw_uid``: Framework UID
"""

PATTERN_ENDPOINT_KEY = "pelix/remote/services/{fw_uid}/{endpoint_uid}"
"""
Pattern of endpoints keys, with the following format entries:
* ``fw_uid``: Framework UID
* ``endpoint_uid``: Export endpoint UID
"""


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.remote.FACTORY_DISCOVERY_REDIS)
@Provides(pelix.remote.SERVICE_EXPORT_ENDPOINT_LISTENER)
@Requires("_dispatcher", pelix.remote.SERVICE_DISPATCHER)
@Requires("_registry", pelix.remote.SERVICE_REGISTRY)
@Property("_redis_host", "redis.host", "localhost")
@Property("_redis_port", "redis.port", 6379)
@Property("_redis_db", "redis.db", 0)
@Property("_redis_password", "redis.password")
@Property("_heart_delay", "heartbeat.delay", 10)
class RedisDiscovery(object):
    """
    Remote services discovery and notification using a Redis server
    """

    def __init__(self):
        """
        Sets up the component
        """
        # Endpoints registries
        self._dispatcher = None
        self._registry = None

        # Framework UID
        self._fw_uid = None

        # Hostname cache: Framework UID -> Hostname
        self._frameworks_hosts = {}

        # Redis
        self._redis_host = "localhost"
        self._redis_port = 6379
        self._redis_db = 0
        self._redis_password = None
        self._redis = None

        # PubSub thread
        self._pubsub = None
        self._pubsub_thread = None

        # Heartbeat thread
        self._heart_delay = 10
        self._heart_thread = None
        self._stop_event = threading.Event()

        # Event handlers
        self.__endpoint_handlers = {
            "set": self._handle_set,
            "del": self._handle_del,
        }

    @Invalidate
    def invalidate(self, _):
        """
        Component invalidated
        """
        # Stop the Pub/Sub thread, if any
        if self._pubsub_thread is not None:
            self._pubsub_thread.stop()
            self._pubsub_thread.join()
            self._pubsub_thread = None

        # Close the Pub/Sub object
        self._pubsub.close()
        self._pubsub = None

        # Stop the heart beat
        self._unregister_framework()

        # Clean up
        self._frameworks_hosts.clear()
        _logger.debug("Redis discovery invalidated")

    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Ensure we have valid integers
        self._redis_port = int(self._redis_port)
        self._redis_db = int(self._redis_db)

        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Connect to Redis
        self._redis = redis.StrictRedis(
            self._redis_host,
            self._redis_port,
            self._redis_db,
            self._redis_password,
        )

        # Configure the server to send key events
        config_key = "notify-keyspace-events"
        current = set(self._redis.config_get(config_key)[config_key])
        current.update("K$sg")
        self._redis.config_set(config_key, "".join(current))

        # Start listening to events
        keyspace = "__keyspace@{0}__".format(self._redis_db)
        patterns = {
            "pelix/remote/frameworks/*": self._handle_framework_event,
            "pelix/remote/services/*": self._handle_endpoint_event,
        }

        self._pubsub = self._redis.pubsub()
        self._pubsub.psubscribe(
            **{
                ":".join((keyspace, pattern)): handler
                for pattern, handler in patterns.items()
            }
        )

        # Start the event thread
        self._pubsub_thread = self._pubsub.run_in_thread()

        # Set the discovery key
        self._stop_event.clear()
        self._register_framework()
        _logger.debug("Redis discovery validated")

    def _register_framework(self):
        """
        Registers the framework and its current services in Redis
        """
        # The framework key
        fw_key = PATTERN_FRAMEWORK_KEY.format(fw_uid=self._fw_uid)

        # The host name
        hostname = socket.gethostname()
        if hostname == "localhost":
            logging.warning(
                "Hostname is '%s': this will be a problem for "
                "multi-host remote services",
                hostname,
            )

        def heart():
            """
            Heartbeat method
            """
            # Register the framework once
            self._redis.set(
                fw_key, hostname, int(math.ceil(self._heart_delay * 1.2))
            )

            # Loop while we're up
            while not self._stop_event.wait(self._heart_delay):
                # Re-set the key with a new time to live
                self._redis.set(
                    fw_key, hostname, int(math.ceil(self._heart_delay * 1.2))
                )

            # Stop event set: delete the key immediately
            self._redis.delete(fw_key)

        # Start the heartbeat thread
        self._heart_thread = threading.Thread(
            target=heart, name="Redis Discovery Heartbeat"
        )
        self._heart_thread.daemon = True
        self._heart_thread.start()

        # Load existing services
        self._load_existing_endpoints()

        # Register all already exported services
        for endpoint in self._dispatcher.get_endpoints():
            self._register_service(endpoint)

    def _load_existing_endpoints(self):
        """
        Loads already-registered endpoints
        """
        fw_cache = {}
        for key in self._redis.keys(
            PATTERN_ENDPOINT_KEY.format(fw_uid="*", endpoint_uid="*")
        ):
            # Extract UIDs
            key = key.decode("utf-8")
            fw_uid, _ = self._extract_uids(key)

            # Check if the framework is still there
            try:
                # Check cached information
                register = fw_cache[fw_uid]
            except KeyError:
                # Check a new framework
                register = fw_cache[fw_uid] = self._redis.exists(
                    PATTERN_FRAMEWORK_KEY.format(fw_uid=fw_uid)
                )

            if register:
                # Framework exists: store the endpoint
                self._handle_set(key)
            else:
                # Framework has expired: cleanup the remaining keys
                self._redis.delete(key)

    def _unregister_framework(self):
        """
        Removes all entries related to the framework in Redis
        """
        # Stop the thread setting the entry
        self._stop_event.set()
        self._heart_thread.join()
        self._heart_thread = None

        # The framework is already unregistered: remove all the endpoints
        endpoints = self._redis.keys(
            PATTERN_ENDPOINT_KEY.format(fw_uid=self._fw_uid, endpoint_uid="*")
        )
        if endpoints:
            self._redis.delete(*endpoints)

    def _register_service(self, endpoint):
        """
        Registers/Updates an exported service to Redis.

        :param endpoint: A :class:`~pelix.remote.ExportEndpoint` object
        """
        # Convert to EDEF
        key = PATTERN_ENDPOINT_KEY.format(
            fw_uid=self._fw_uid, endpoint_uid=endpoint.uid
        )
        xml_string = EDEFWriter().to_string(
            [beans.EndpointDescription.from_export(endpoint)]
        )

        # Send to Redis (without expiration)
        self._redis.set(key, xml_string)

    def _unregister_service(self, endpoint):
        """
        Unregisters an endpoint from Redis

        :param endpoint: A :class:`~pelix.remote.ExportEndpoint` object
        """
        self._redis.delete(
            PATTERN_ENDPOINT_KEY.format(
                fw_uid=self._fw_uid, endpoint_uid=endpoint.uid
            )
        )

    def endpoints_added(self, endpoints):
        """
        Multiple endpoints have been added

        :param endpoints: A list of ExportEndpoint beans
        """
        for endpoint in endpoints:
            self._register_service(endpoint)

    def endpoint_updated(self, endpoint, _):
        """
        An end point is updated

        :param endpoint: The updated endpoint
                         (:class:`~pelix.remote.ExportEndpoint`)
        :param _: Previous end point properties (not used)
        """
        # Update and registration are the same with Redis
        self._register_service(endpoint)

    def endpoint_removed(self, endpoint):
        """
        An end point is removed

        :param endpoint: :class:`~pelix.remote.ExportEndpoint` being removed
        """
        self._unregister_service(endpoint)

    def _handle_framework_event(self, data):
        """
        Handles a Redis notification about a framework

        :param data: Redis notification data
        """
        event = data["data"].decode("utf-8")

        # Compute framework UID
        # 1: remove the Redis channel prefix
        # 2: remove the key prefix (pelix/remote/frameworks)
        fw_key = data["channel"].decode("utf-8").split(":", 1)[1]
        fw_uid = fw_key.split("/", 3)[-1]

        if event == "expired":
            # A framework has expired: clean it up
            logging.warning("Framework %s has expired", fw_uid)

            # Forget about its hostname
            try:
                del self._frameworks_hosts[fw_uid]
            except KeyError:
                pass

            # Forget all of its endpoints
            self._registry.lost_framework(fw_uid)

            # Remove all of its endpoints (many frameworks will do that)
            keys = self._redis.keys(
                PATTERN_ENDPOINT_KEY.format(fw_uid=fw_uid, endpoint_uid="*")
            )
            if keys:
                self._redis.delete(*keys)
        elif event == "expire" and fw_uid not in self._frameworks_hosts:
            # Unknown framework found: store its hostname
            hostname = self._redis.get(fw_key)
            if hostname:
                self._frameworks_hosts[fw_uid] = hostname.decode("utf-8")

    def _handle_endpoint_event(self, data):
        """
        Handles a Redis notification about an endpoint

        :param data: Redis notification data
        """
        event = data["data"].decode("utf-8")
        try:
            # Get the event method
            method = self.__endpoint_handlers[event]
        except KeyError:
            # Ignored event
            pass
        else:
            # Extract the endpoint UID and call the handler
            method(data["channel"].decode("utf-8").split(":", 1)[1])

    @staticmethod
    def _extract_uids(endpoint_key):
        """
        Extracts the framework UID and the endpoint UID from a Redis key name

        :param endpoint_key: Name of a Redis key
        :return: A (framework UID, endpoint UID) tuple
        """
        tokens = endpoint_key.split("/")

        # Framework UID can be customized: remove prefix and the endpoint UID
        # Endpoint UID is always a well formatted UUID (no slash)
        return "/".join(tokens[3:-1]), tokens[-1]

    def _handle_set(self, endpoint_key):
        """
        An endpoint has been set or updated in Redis

        :param endpoint_key: Name of the Redis key describing the endpoint
        :return: True if an endpoint was added, False if it was a pending
                 endpoint and None if it was an echo
        """
        fw_uid, _ = self._extract_uids(endpoint_key)
        if fw_uid == self._fw_uid:
            # Got an echo
            return False

        # Not an echo: handle the event
        # 1. Get the framework hostname
        try:
            # Find in cache
            hostname = self._frameworks_hosts[fw_uid]
        except KeyError:
            # Get it from Redis
            hostname = self._redis.get(
                PATTERN_FRAMEWORK_KEY.format(fw_uid=fw_uid)
            )
            if not hostname:
                # Endpoint's framework has been removed: ignore
                # (happens when two frameworks clear traces of an old one)
                logging.debug(
                    "Framework of endpoint key %s, doesn't have a hostname",
                    endpoint_key,
                )
                return False
            else:
                # Valid hostname found, convert it to a string
                hostname = self._frameworks_hosts[fw_uid] = hostname.decode(
                    "utf-8"
                )

        # 2. Read the EDEF content
        content = self._redis.get(endpoint_key)
        if not content:
            logging.debug("Endpoint description removed while handling it")
            return False

        content = content.decode("utf-8")
        for endpoint in EDEFReader().parse(content):
            # Convert to a Pelix ImportEndpoint, and set the server hostname
            endpoint = endpoint.to_import()
            endpoint.server = hostname

            if self._registry.contains(endpoint):
                # Update endpoint
                self._registry.update(endpoint.uid, endpoint.properties)
            else:
                # New endpoint
                self._registry.add(endpoint)
        return True

    def _handle_del(self, endpoint_key):
        """
        A Redis key has been deleted

        :param endpoint_key: Name of the Redis key describing the endpoint
        """
        fw_uid, endpoint_uid = self._extract_uids(endpoint_key)
        if fw_uid != self._fw_uid and self._registry.contains(endpoint_uid):
            self._registry.remove(endpoint_uid)
