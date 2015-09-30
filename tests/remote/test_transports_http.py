#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Tests remote services transports based on HTTP

:author: Thomas Calmant
:copyright: Copyright 2015, isandlaTech
:license: Apache License 2.0
:version: 0.5.9
:status: Alpha

..

    Copyright 2015 isandlaTech

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

# Pelix
from pelix.framework import create_framework, FrameworkFactory
from pelix.ipopo.constants import use_ipopo
import pelix.http
import pelix.remote

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

# Local utilities
from tests.utilities import WrappedProcess

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 5, 9)
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

    def dummy(self):
        """
        No argument, no result
        """
        self.state_queue.put("call-dummy")

    def echo(self, value):
        """
        Returns the given value
        """
        self.state_queue.put("call-echo")
        return value

    def keywords(self, text, to_lower=False):
        """
        Return the string value in lower or upper case
        """
        self.state_queue.put("call-keyword")
        if to_lower:
            return text.lower()
        else:
            return text.upper()

    def error(self):
        """
        Raises an error
        """
        self.state_queue.put("call-error")
        raise ValueError("Some error")

    def stop(self):
        """
        Stops the peer
        """
        self.event.set()

# ------------------------------------------------------------------------------


def load_framework(transport, components):
    """
    Starts a Pelix framework in the local process

    :param transport: Name of the transport bundle to install
    :param components: Tuples (factory, name) of instances to start
    """
    all_bundles = ['pelix.ipopo.core',
                   'pelix.http.basic',
                   'pelix.remote.dispatcher',
                   'pelix.remote.registry',
                   'pelix.remote.discovery.multicast',
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

        # Start the multicast discovery
        ipopo.instantiate(pelix.remote.FACTORY_DISCOVERY_MULTICAST,
                          "multicast-discovery")

        # Start other components
        for factory, name in components:
            ipopo.instantiate(factory, name)

    return framework


def export_framework(state_queue, transport, components):
    """
    Starts a Pelix framework, on the export side

    :param state_queue: Queue to store status
    :param transport: Name of the transport bundle to install
    :param components: Tuples (factory, name) of instances to start
    """
    try:
        # Load the framework
        framework = load_framework(transport, components)
        context = framework.get_bundle_context()

        # Register the exported service
        event = threading.Event()
        context.register_service(SVC_SPEC,
                                 RemoteService(state_queue, event),
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


class TransportsTest(unittest.TestCase):
    """
    Tests Pelix built-in Remote Services transports
    """
    def __run_test(self, transport_bundle, exporter_factory, importer_factory,
                   test_kwargs=True):
        """
        Runs a remote service call test

        :param transport_bundle: Transport implementation bundle to use
        :param exporter_factory: Name of the RS exporter factory
        :param importer_factory: Name of the RS importer factory
        :param test_kwargs: Test keyword arguments
        :raise queue.Empty: Peer took to long to answer
        :raise ValueError: Test failed
        """
        # Define components
        components = [(exporter_factory, "rs-exporter"),
                      (importer_factory, "rs-importer")]

        # Start the remote framework
        status_queue = Queue()
        peer = WrappedProcess(target=export_framework,
                              args=(status_queue, transport_bundle,
                                    components))
        peer.start()

        try:
            # Wait for the ready state
            state = status_queue.get(4)
            self.assertEqual(state, "ready")

            # Load the local framework (after the fork)
            framework = load_framework(transport_bundle, components)
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

            # Dummy call
            result = svc.dummy()
            state = status_queue.get(2)
            self.assertEqual(state, "call-dummy")
            self.assertIsNone(result, "Dummy didn't returned None: {0}"
                              .format(result))

            # Echo call
            for value in (None, "Test", 42, [1, 2, 3], {"a": "b"}):
                result = svc.echo(value)

                # Check state
                state = status_queue.get(2)
                self.assertEqual(state, "call-echo")

                # Check result
                self.assertEqual(result, value)

            if test_kwargs:
                # Keyword arguments
                sample_text = "SomeSampleText"

                # Test as-is with default arguments
                result = svc.keywords(text=sample_text)
                state = status_queue.get(2)
                self.assertEqual(state, "call-keyword")
                self.assertEqual(result, sample_text.upper())

                # Test with keywords in the same order as positional arguments
                result = svc.keywords(text=sample_text, to_lower=True)
                state = status_queue.get(2)
                self.assertEqual(state, "call-keyword")
                self.assertEqual(result, sample_text.lower())

                result = svc.keywords(text=sample_text, to_lower=False)
                state = status_queue.get(2)
                self.assertEqual(state, "call-keyword")
                self.assertEqual(result, sample_text.upper())

                # Test with keywords in a different order
                # than positional arguments
                result = svc.keywords(to_lower=True, text=sample_text)
                state = status_queue.get(2)
                self.assertEqual(state, "call-keyword")
                self.assertEqual(result, sample_text.lower())

            # Exception handling
            try:
                svc.error()
            except:
                # The error has been propagated
                state = status_queue.get(2)
                self.assertEqual(state, "call-error")
            else:
                self.fail("No exception raised calling 'error'")

            # Call undefined method
            try:
                svc.undefined()
            except:
                # The error has been propagated: OK
                pass
            else:
                self.fail("No exception raised calling an undefined method")

            # Stop the peer
            svc.stop()

            # Wait for the peer to stop
            state = status_queue.get(2)
            self.assertEqual(state, "stopping")

            # Wait a bit more, to let coverage save its files
            time.sleep(.1)
        finally:
            # Stop everything (and delete the framework in any case
            FrameworkFactory.delete_framework()
            peer.terminate()
            status_queue.close()

    def test_xmlrpc(self):
        """
        Tests the XML-RPC transport
        """
        try:
            self.__run_test("pelix.remote.xml_rpc",
                            pelix.remote.FACTORY_TRANSPORT_XMLRPC_EXPORTER,
                            pelix.remote.FACTORY_TRANSPORT_XMLRPC_IMPORTER,
                            False)
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_jsonrpc(self):
        """
        Tests the JSON-RPC transport
        """
        try:
            self.__run_test("pelix.remote.json_rpc",
                            pelix.remote.FACTORY_TRANSPORT_JSONRPC_EXPORTER,
                            pelix.remote.FACTORY_TRANSPORT_JSONRPC_IMPORTER)
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_jabsorbrpc(self):
        """
        Tests the JABSORB-RPC transport
        """
        try:
            self.__run_test("pelix.remote.transport.jabsorb_rpc",
                            pelix.remote.FACTORY_TRANSPORT_JABSORBRPC_EXPORTER,
                            pelix.remote.FACTORY_TRANSPORT_JABSORBRPC_IMPORTER)
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
