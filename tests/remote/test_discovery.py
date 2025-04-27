#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Tests remote services discovery using the JSON-RPC transport

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0

..

    Copyright 2025 Thomas Calmant

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

import queue
import threading
import time
import traceback
import unittest
from typing import Any, Dict, Iterable, Optional, Tuple, Union

import pelix.http
import pelix.remote
from pelix.framework import Bundle, Framework, FrameworkFactory, create_framework
from pelix.internals.registry import ServiceReference
from pelix.ipopo.constants import use_ipopo
from tests.utilities import WrappedProcess

try:
    # Try to import modules
    import multiprocessing
    from multiprocessing import Process, Queue

    # IronPython fails when creating a queue
    Queue()

    # Trick to avoid pytest hanging
    multiprocessing.set_start_method("spawn", force=True)
except ImportError:
    # Some interpreters don't have support for multiprocessing
    raise unittest.SkipTest("Interpreter doesn't support multiprocessing")

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

SVC_SPEC = "pelix.test.remote"


class RemoteService:
    """
    Exported service
    """

    def __init__(self, state_queue: Queue, event: threading.Event) -> None:
        """
        Sets up members

        ;param state_queue: Queue to store status
        :param event: Stop event
        """
        self.state_queue = state_queue
        self.event = event

    def echo(self, value: Any) -> Any:
        """
        Returns the given value
        """
        self.state_queue.put("call-echo")
        return value

    def stop(self) -> None:
        """
        Stops the peer
        """
        self.event.set()


# ------------------------------------------------------------------------------


def load_framework(
    transport: str,
    discovery: str,
    components: Iterable[Union[Tuple[str, str], Tuple[str, str, Dict[str, Any]]]],
) -> Framework:
    """
    Starts a Pelix framework in the local process

    :param transport: Name of the transport bundle to install
    :param discovery: Name of the discovery bundle to install
    :param components: Tuples (factory, name, props) of instances to start
    """
    all_bundles = [
        "pelix.ipopo.core",
        "pelix.http.basic",
        "pelix.remote.dispatcher",
        "pelix.remote.registry",
        discovery,
        transport,
    ]

    # Start the framework
    framework = create_framework(all_bundles)
    framework.start()

    with use_ipopo(framework.get_bundle_context()) as ipopo:
        # Start a HTTP service on a random port
        ipopo.instantiate(
            pelix.http.FACTORY_HTTP_BASIC,
            "http-server",
            {pelix.http.HTTP_SERVICE_ADDRESS: "0.0.0.0", pelix.http.HTTP_SERVICE_PORT: 0},
        )

        ipopo.instantiate(pelix.remote.FACTORY_REGISTRY_SERVLET, "dispatcher-servlet")

        # Start other components
        for component in components:
            factory = component[0]
            name = component[1]
            opts = component[2] if len(component) == 3 else {}
            ipopo.instantiate(factory, name, opts)

    return framework


def export_framework(
    state_queue: Queue,
    transport: str,
    discovery: str,
    components: Iterable[Union[Tuple[str, str], Tuple[str, str, Dict[str, Any]]]],
) -> None:
    """
    Starts a Pelix framework, on the export side

    :param state_queue: Queue to store status
    :param transport: Name of the transport bundle to install
    :param discovery: Name of the discovery bundle to install
    :param components: Tuples (factory, name) of instances to start
    """
    try:
        # Load the framework
        framework = load_framework(transport, discovery, components)
        context = framework.get_bundle_context()

        # Ensure everything is there
        bundles = {b.get_symbolic_name(): b for b in context.get_bundles()}
        assert bundles[transport].get_state() == Bundle.ACTIVE
        assert bundles[discovery].get_state() == Bundle.ACTIVE

        # Register the exported service
        event = threading.Event()
        context.register_service(
            SVC_SPEC, RemoteService(state_queue, event), {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # Send the ready state
        state_queue.put("ready")

        # Loop until the end message
        event.wait()

        # Stopping
        state_queue.put("stopping")
        framework.stop()
        framework.delete()
    except Exception as ex:
        state_queue.put(f"Error: {ex}\n{traceback.format_exc()}")


# ------------------------------------------------------------------------------


class HttpTransportsTest(unittest.TestCase):
    """
    Tests Pelix built-in Remote Services transports
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(HttpTransportsTest, self).__init__(*args, **kwargs)
        self._load_framework = load_framework
        self._export_framework = export_framework

    def _run_test(
        self, discovery_bundle: str, discovery_factory: str, discovery_opts: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Runs a remote service call test

        :param discovery_bundle: Discovery implementation bundle to use
        :param discovery_factory: Name of the discovery factory
        :param discovery_opts: Initial parameters of the discovery component
        :raise queue.Empty: Peer took to long to answer
        :raise ValueError: Test failed
        """
        transport_bundle = "pelix.remote.json_rpc"

        # Define components
        components = [
            (pelix.remote.FACTORY_TRANSPORT_JSONRPC_EXPORTER, "rs-exporter"),
            (pelix.remote.FACTORY_TRANSPORT_JSONRPC_IMPORTER, "rs-importer"),
            (discovery_factory, "discovery", discovery_opts),
        ]

        # Start the remote framework
        status_queue = Queue()
        peer = WrappedProcess(
            target=self._export_framework, args=(status_queue, transport_bundle, discovery_bundle, components)
        )
        peer.start()

        try:
            # Wait for the ready state
            state = status_queue.get(True, 4)
            self.assertEqual(state, "ready")

            # Load the local framework (after the fork)
            framework = self._load_framework(transport_bundle, discovery_bundle, components)
            context = framework.get_bundle_context()

            # Look for the remote service
            for _ in range(10):
                svc_ref: Optional[ServiceReference[Any]] = context.get_service_reference(SVC_SPEC)
                if svc_ref is not None:
                    break
                time.sleep(0.5)
            else:
                self.fail("Remote Service not found")

            # Get it
            svc = context.get_service(svc_ref)

            # Echo call
            for value in (None, "Test", 42, [1, 2, 3], {"a": "b"}):
                result = svc.echo(value)
                # Check state
                state = status_queue.get(True, 2)
                self.assertEqual(state, "call-echo")
                # Check result
                self.assertEqual(result, value)

            # Stop the peer
            svc.stop()

            # Wait for the peer to stop
            state = status_queue.get(True, 2)
            self.assertEqual(state, "stopping")

            # Wait a bit more, to let coverage save its files
            peer.join(1)

            # Check the remote service
            # Look for the remote service
            for _ in range(10):
                svc_ref = context.get_service_reference(SVC_SPEC)
                if svc_ref is None:
                    break
                time.sleep(2)
            else:
                self.fail("Remote Service still registered")
        finally:
            # Stop everything (and delete the framework in any case
            try:
                FrameworkFactory.delete_framework()
            except:
                pass

            try:
                peer.kill()
                peer.join(5)
                peer.close()
            finally:
                status_queue.close()

    def test_multicast(self) -> None:
        """
        Tests the Multicast discovery
        """
        try:
            self._run_test("pelix.remote.discovery.multicast", pelix.remote.FACTORY_DISCOVERY_MULTICAST)
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_mdns(self) -> None:
        """
        Tests the mDNS/Zeroconf discovery
        """
        try:
            import zeroconf
        except ImportError:
            self.skipTest("zeroconf is missing: can't test mDNS discovery")

        try:
            self._run_test(
                "pelix.remote.discovery.mdns", pelix.remote.FACTORY_DISCOVERY_ZEROCONF, {"zeroconf.ttl": 10}
            )
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_mqtt(self) -> None:
        """
        Tests the MQTT discovery
        """
        try:
            import paho
        except ImportError:
            self.skipTest("paho is missing: can't test MQTT discovery")

        try:
            self._run_test("pelix.remote.discovery.mqtt", pelix.remote.FACTORY_DISCOVERY_MQTT)
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_redis(self) -> None:
        """
        Tests the Redis discovery
        """
        try:
            import redis
        except ImportError:
            self.skipTest("redis is missing: can't test Redis discovery")

        try:
            self._run_test("pelix.remote.discovery.redis", pelix.remote.FACTORY_DISCOVERY_REDIS)
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_zookeeper(self) -> None:
        """
        Tests the ZooKeeper discovery
        """
        try:
            import kazoo
        except ImportError:
            self.skipTest("Kazoo is missing: can't test ZooKeeper discovery")

        try:
            self._run_test(
                "pelix.remote.discovery.zookeeper",
                pelix.remote.FACTORY_DISCOVERY_ZOOKEEPER,
                {"zookeeper.hosts": "localhost:2181"},
            )
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
