#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Tests remote services discovery using the JSON-RPC transport

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0

..

    Copyright 2023 Thomas Calmant

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
import time
import threading

try:
    import unittest2 as unittest
except ImportError:
    import unittest

try:
    # Try to import modules
    from multiprocessing import Process, Queue
    # IronPython fails when creating a queue
    Queue()
except ImportError:
    # Some interpreters don't have support for multiprocessing
    raise unittest.SkipTest("Interpreter doesn't support multiprocessing")

try:
    import queue
except ImportError:
    import Queue as queue

# Pelix
from pelix.framework import create_framework, FrameworkFactory
from pelix.ipopo.constants import use_ipopo
import pelix.http
import pelix.remote

# Local utilities
from tests.utilities import WrappedProcess

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

SVC_SPEC = "pelix.test.remote"


class RemoteService(object):
    """
    Exported service
    """
    def __init__(self, state_queue, event):
        """
        Sets up members

        ;param state_queue: Queue to store status
        :param event: Stop event
        """
        self.state_queue = state_queue
        self.event = event

    def echo(self, value):
        """
        Returns the given value
        """
        self.state_queue.put("call-echo")
        return value

    def stop(self):
        """
        Stops the peer
        """
        self.event.set()

# ------------------------------------------------------------------------------


def load_framework(transport, discovery, components):
    """
    Starts a Pelix framework in the local process

    :param transport: Name of the transport bundle to install
    :param discovery: Name of the discovery bundle to install
    :param components: Tuples (factory, name) of instances to start
    """
    all_bundles = ['pelix.ipopo.core',
                   'pelix.http.basic',
                   'pelix.remote.dispatcher',
                   'pelix.remote.registry',
                   discovery,
                   transport]

    # Start the framework
    framework = create_framework(all_bundles)
    framework.start()

    with use_ipopo(framework.get_bundle_context()) as ipopo:
        # Start a HTTP service on a random port
        ipopo.instantiate(pelix.http.FACTORY_HTTP_BASIC,
                          "http-server",
                          {pelix.http.HTTP_SERVICE_ADDRESS: "0.0.0.0",
                           pelix.http.HTTP_SERVICE_PORT: 0})

        ipopo.instantiate(pelix.remote.FACTORY_REGISTRY_SERVLET,
                          "dispatcher-servlet")

        # Start other components
        for component in components:
            try:
                factory, name, opts = component
            except ValueError:
                factory, name = component
                opts = {}

            ipopo.instantiate(factory, name, opts)

    return framework


def export_framework(state_queue, transport, discovery, components):
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

        # Register the exported service
        event = threading.Event()
        context.register_service(
            SVC_SPEC, RemoteService(state_queue, event),
            {pelix.remote.PROP_EXPORTED_INTERFACES: '*'})

        # Send the ready state
        state_queue.put("ready")

        # Loop until the end message
        event.wait()

        # Stopping
        state_queue.put("stopping")
        framework.stop()
    except Exception as ex:
        state_queue.put("Error: {0}".format(ex))

# ------------------------------------------------------------------------------


class HttpTransportsTest(unittest.TestCase):
    """
    Tests Pelix built-in Remote Services transports
    """
    def __init__(self, *args, **kwargs):
        super(HttpTransportsTest, self).__init__(*args, **kwargs)
        self._load_framework = load_framework
        self._export_framework = export_framework

    def _run_test(self, discovery_bundle, discovery_factory,
                  discovery_opts=None):
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
            (discovery_factory, "discovery", discovery_opts)]

        # Start the remote framework
        status_queue = Queue()
        peer = WrappedProcess(target=self._export_framework,
                              args=(status_queue, transport_bundle,
                                    discovery_bundle, components))
        peer.start()

        try:
            # Wait for the ready state
            state = status_queue.get(4)
            self.assertEqual(state, "ready")

            # Load the local framework (after the fork)
            framework = self._load_framework(
                transport_bundle, discovery_bundle, components)
            context = framework.get_bundle_context()

            # Look for the remote service
            for _ in range(10):
                svc_ref = context.get_service_reference(SVC_SPEC)
                if svc_ref is not None:
                    break
                time.sleep(.5)
            else:
                self.fail("Remote Service not found")

            # Get it
            svc = context.get_service(svc_ref)

            # Echo call
            for value in (None, "Test", 42, [1, 2, 3], {"a": "b"}):
                result = svc.echo(value)
                # Check state
                state = status_queue.get(2)
                self.assertEqual(state, "call-echo")
                # Check result
                self.assertEqual(result, value)

            # Stop the peer
            svc.stop()

            # Wait for the peer to stop
            state = status_queue.get(2)
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
            peer.terminate()
            status_queue.close()

    def test_multicast(self):
        """
        Tests the Multicast discovery
        """
        try:
            self._run_test("pelix.remote.discovery.multicast",
                           pelix.remote.FACTORY_DISCOVERY_MULTICAST)
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_mdns(self):
        """
        Tests the mDNS/Zeroconf discovery
        """
        try:
            import zeroconf
        except ImportError:
            self.skipTest("zeroconf is missing: can't test mDNS discovery")

        try:
            self._run_test("pelix.remote.discovery.mdns",
                           pelix.remote.FACTORY_DISCOVERY_ZEROCONF,
                           {"zeroconf.ttl": 10})
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_mqtt(self):
        """
        Tests the MQTT discovery
        """
        try:
            import paho
        except ImportError:
            self.skipTest("paho is missing: can't test MQTT discovery")

        try:
            self._run_test("pelix.remote.discovery.mqtt",
                           pelix.remote.FACTORY_DISCOVERY_MQTT)
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_redis(self):
        """
        Tests the Redis discovery
        """
        try:
            import redis
        except ImportError:
            self.skipTest("redis is missing: can't test Redis discovery")

        try:
            self._run_test("pelix.remote.discovery.redis",
                           pelix.remote.FACTORY_DISCOVERY_REDIS)
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_zookeeper(self):
        """
        Tests the ZooKeeper discovery
        """
        try:
            import kazoo
        except ImportError:
            self.skipTest("Kazoo is missing: can't test ZooKeeper discovery")

        try:
            self._run_test("pelix.remote.discovery.zookeeper",
                           pelix.remote.FACTORY_DISCOVERY_ZOOKEEPER,
                           {"zookeeper.hosts": "localhost:2181"})
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
