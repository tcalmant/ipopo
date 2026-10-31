#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Tests remote services transports based on HTTP

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0

..

    Copyright 2026 Thomas Calmant

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
import queue
import threading
import time
import unittest
import xmlrpc.client
from collections.abc import Iterable
from typing import Any, cast

import pelix.http
import pelix.remote
from pelix.framework import Framework, FrameworkFactory, create_framework
from pelix.internals.registry import ServiceReference
from pelix.ipopo.constants import use_ipopo
from pelix.remote import security
from pelix.security import AccessDenied, AuthenticationRequired
from tests.utilities import WrappedProcess

try:
    # Try to import modules
    import multiprocessing
    from multiprocessing import Process, Queue  # noqa: F401

    # IronPython fails when creating a queue
    Queue()

    # Trick to avoid pytest hanging
    multiprocessing.set_start_method("spawn", force=True)
except ImportError:
    # Some interpreters don't have support for multiprocessing
    raise unittest.SkipTest("Interpreter doesn't support multiprocessing")

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
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

    def dummy(self) -> None:
        """
        No argument, no result
        """
        self.state_queue.put("call-dummy")

    def echo(self, value: Any) -> Any:
        """
        Returns the given value
        """
        self.state_queue.put("call-echo")
        return value

    def keywords(self, text: str, to_lower: bool = False) -> str:
        """
        Return the string value in lower or upper case
        """
        self.state_queue.put("call-keyword")
        if to_lower:
            return text.lower()
        else:
            return text.upper()

    def error(self) -> None:
        """
        Raises an error
        """
        self.state_queue.put("call-error")
        raise ValueError("Some error")

    def stop(self) -> None:
        """
        Stops the peer
        """
        self.event.set()


# ------------------------------------------------------------------------------


def load_framework(transport: str, components: Iterable[tuple[str, str]]) -> Framework:
    """
    Starts a Pelix framework in the local process

    :param transport: Name of the transport bundle to install
    :param components: Tuples (factory, name) of instances to start
    """
    all_bundles = [
        "pelix.ipopo.core",
        "pelix.http.basic",
        "pelix.remote.dispatcher",
        "pelix.remote.registry",
        "pelix.remote.discovery.multicast",
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

        # Peers discover each other anonymously
        ipopo.instantiate(
            pelix.remote.FACTORY_REGISTRY_SERVLET, "dispatcher-servlet", {security.PROP_PERMISSION: "*"}
        )

        # Start the multicast discovery
        ipopo.instantiate(pelix.remote.FACTORY_DISCOVERY_MULTICAST, "multicast-discovery")

        # Start other components
        for factory, name in components:
            ipopo.instantiate(factory, name)

    return framework


def export_framework(state_queue: Queue, transport: str, components: Iterable[tuple[str, str]]) -> None:
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
        context.register_service(
            SVC_SPEC,
            RemoteService(state_queue, event),
            # Bound to all interfaces, for the multicast discovery: callers need a permission
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*", security.PROP_PERMISSION: "*"},
        )

        # Send the ready state
        state_queue.put("ready")

        # Loop until the end message
        event.wait()

        # Stopping
        state_queue.put("stopping")
        framework.stop()
        framework.delete()
    except Exception as ex:  # noqa: BLE001
        state_queue.put(f"Error: {ex}")


# ------------------------------------------------------------------------------


class HttpTransportsTest(unittest.TestCase):
    """
    Tests Pelix built-in Remote Services transports
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._load_framework = load_framework
        self._export_framework = export_framework

    def _run_test(
        self, transport_bundle: str, exporter_factory: str, importer_factory: str, test_kwargs: bool = True
    ) -> None:
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
        components = [(exporter_factory, "rs-exporter"), (importer_factory, "rs-importer")]

        # Start the remote framework
        status_queue = Queue()
        peer = WrappedProcess(
            target=self._export_framework, args=(status_queue, transport_bundle, components)
        )
        peer.start()

        try:
            # Wait for the ready state
            state = status_queue.get(True, 4)
            self.assertEqual(state, "ready")

            # Load the local framework (after the fork)
            framework = self._load_framework(transport_bundle, components)
            context = framework.get_bundle_context()

            # Look for the remote service
            for _ in range(10):
                svc_ref: ServiceReference[Any] | None = context.get_service_reference(SVC_SPEC)
                if svc_ref is not None:
                    break
                time.sleep(0.5)
            else:
                self.fail("Remote Service not found")

            # Get it
            svc = context.get_service(svc_ref)

            # Dummy call
            result = svc.dummy()
            state = status_queue.get(True, 2)
            self.assertEqual(state, "call-dummy")
            self.assertIsNone(result, f"Dummy didn't returned None: {result}")

            # Echo call
            for value in (None, "Test", 42, [1, 2, 3], {"a": "b"}):
                result = svc.echo(value)

                # Check state
                state = status_queue.get(True, 2)
                self.assertEqual(state, "call-echo")

                # Check result
                self.assertEqual(result, value)

            if test_kwargs:
                # Keyword arguments
                sample_text = "SomeSampleText"

                # Test as-is with default arguments
                result = svc.keywords(text=sample_text)
                state = status_queue.get(True, 2)
                self.assertEqual(state, "call-keyword")
                self.assertEqual(result, sample_text.upper())

                # Test with keywords in the same order as positional arguments
                result = svc.keywords(text=sample_text, to_lower=True)
                state = status_queue.get(True, 2)
                self.assertEqual(state, "call-keyword")
                self.assertEqual(result, sample_text.lower())

                result = svc.keywords(text=sample_text, to_lower=False)
                state = status_queue.get(True, 2)
                self.assertEqual(state, "call-keyword")
                self.assertEqual(result, sample_text.upper())

                # Test with keywords in a different order
                # than positional arguments
                result = svc.keywords(to_lower=True, text=sample_text)
                state = status_queue.get(True, 2)
                self.assertEqual(state, "call-keyword")
                self.assertEqual(result, sample_text.lower())

            # Exception handling
            try:
                svc.error()
            except:  # noqa: E722
                # The error has been propagated
                state = status_queue.get(True, 2)
                self.assertEqual(state, "call-error")
            else:
                self.fail("No exception raised calling 'error'")

            # Call undefined method
            with self.assertRaises(Exception):  # noqa: B017
                svc.undefined()

            # Stop the peer
            svc.stop()

            # Wait for the peer to stop
            state = status_queue.get(True, 2)
            self.assertEqual(state, "stopping")

            # Wait a bit more, to let coverage save its files
            time.sleep(0.1)
        finally:
            # Stop everything (and delete the framework in any case
            FrameworkFactory.delete_framework()
            try:
                peer.kill()
                peer.join(5)
                peer.close()
            finally:
                status_queue.close()

    def test_xmlrpc(self) -> None:
        """
        Tests the XML-RPC transport
        """
        try:
            self._run_test(
                "pelix.remote.xml_rpc",
                pelix.remote.FACTORY_TRANSPORT_XMLRPC_EXPORTER,
                pelix.remote.FACTORY_TRANSPORT_XMLRPC_IMPORTER,
                False,
            )
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_jsonrpc(self) -> None:
        """
        Tests the JSON-RPC transport
        """
        try:
            self._run_test(
                "pelix.remote.json_rpc",
                pelix.remote.FACTORY_TRANSPORT_JSONRPC_EXPORTER,
                pelix.remote.FACTORY_TRANSPORT_JSONRPC_IMPORTER,
            )
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")

    def test_jabsorbrpc(self) -> None:
        """
        Tests the JABSORB-RPC transport
        """
        try:
            self._run_test(
                "pelix.remote.transport.jabsorb_rpc",
                pelix.remote.FACTORY_TRANSPORT_JABSORBRPC_EXPORTER,
                pelix.remote.FACTORY_TRANSPORT_JABSORBRPC_IMPORTER,
            )
        except queue.Empty:
            # Process error
            self.fail("Remote framework took to long to reply")


class FakeRequest:
    """
    The part of a servlet request the RPC servlets use
    """

    def __init__(self, body: str, content_type: str | None) -> None:
        self.body = body.encode()
        self.content_type = content_type

    def get_header(self, name: str, default: Any = None) -> Any:
        return self.content_type if name.lower() == "content-type" else default

    def read_data(self) -> bytes:
        return self.body


class FakeResponse:
    """
    Keeps what a servlet answers
    """

    code: int | None = None
    content: Any = None

    def send_content(self, code: int, content: Any, mime_type: str = "text/html") -> None:
        self.code, self.content = code, content


def make_rpc_servlets(calls: list[Any]) -> list[tuple[Any, str, str]]:
    """
    Returns the RPC servlets, recording their calls, with a valid request body and its content type
    """
    from pelix.remote.json_rpc import _JsonRpcServlet
    from pelix.remote.transport.jabsorb_rpc import _JabsorbRpcServlet
    from pelix.remote.xml_rpc import _XmlRpcServlet
    from pelix.rsa.providers.distribution.xmlrpc import ServerDispatcher

    json_body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "svc.method", "params": [1]})
    xml_body = xmlrpc.client.dumps((1,), "svc.method")
    return [
        (_JsonRpcServlet(lambda *args: calls.append(args)), json_body, "application/json-rpc"),
        (_JabsorbRpcServlet(lambda *args: calls.append(args)), json_body, "application/json"),
        (_XmlRpcServlet(lambda *args: calls.append(args)), xml_body, "text/xml"),
        (ServerDispatcher(lambda *args: calls.append(args)), xml_body, "text/xml; charset=utf-8"),
    ]


class RpcServletsTest(unittest.TestCase):
    """
    Tests the RPC servlets against hostile requests, without network
    """

    def test_content_type(self) -> None:
        """
        The RPC servlets only accept the content type of their protocol, which a
        browser can't send cross-site without a CORS preflight
        """
        calls: list[Any] = []
        for servlet, body, content_type in make_rpc_servlets(calls):
            for bad_type in (
                None,
                "",
                "text/plain",
                "application/x-www-form-urlencoded",
                "multipart/form-data",
            ):
                with self.subTest(servlet=type(servlet).__name__, content_type=bad_type):
                    response = FakeResponse()
                    servlet.do_POST(FakeRequest(body, bad_type), response)
                    self.assertEqual(response.code, 415)
                    self.assertEqual(calls, [])

            with self.subTest(servlet=type(servlet).__name__, content_type=content_type):
                response = FakeResponse()
                servlet.do_POST(FakeRequest(body, content_type), response)
                self.assertEqual(response.code, 200)
                self.assertEqual(len(calls), 1)
                calls.clear()

    def test_jsonclass_refused(self) -> None:
        """
        A JSON-RPC class hint must not instantiate anything
        """
        from pelix.remote.json_rpc import _JsonRpcServlet

        calls: list[Any] = []
        servlet = _JsonRpcServlet(lambda name, params: calls.append(params))
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "svc.method",
                "params": [{"__jsonclass__": ["collections.OrderedDict", [[["a", 1]]]]}],
            }
        )
        result = json.loads(servlet._marshaled_dispatch(payload, servlet._simple_dispatch))
        self.assertIn("error", result)
        self.assertEqual(calls, [])

    def test_xml_doctype(self) -> None:
        """
        The XML-RPC servlets refuse a document type declaration, which can declare entities
        """
        calls: list[Any] = []
        for servlet, body, content_type in make_rpc_servlets(calls):
            if "xml" not in content_type:
                continue

            for doctype in ("<!DOCTYPE m [<!ENTITY a 'x'>]>", "<!-- c --><!DOCTYPE m>"):
                with self.subTest(servlet=type(servlet).__name__, doctype=doctype):
                    payload = body.replace("?>", "?>" + doctype, 1).replace(
                        "<int>1</int>", "<string>&a;</string>"
                    )
                    response = FakeResponse()
                    servlet.do_POST(FakeRequest(payload, content_type), response)
                    self.assertEqual(response.code, 400)
                    self.assertEqual(calls, [])

    def test_error_details(self) -> None:
        """
        The caller gets an error ID, not the message of the exception, which only goes to the log
        """

        def fail(*_: Any) -> None:
            raise ValueError("secret detail")

        servlets = make_rpc_servlets([])
        for servlet, _, _ in servlets:
            servlet._dispatch_method = servlet._dispatch_func = fail

        broken = FakeRequest("", "application/json")
        cast(Any, broken).read_data = fail
        for servlet, request in [*((s, FakeRequest(b, t)) for s, b, t in servlets), (servlets[0][0], broken)]:
            with self.subTest(servlet=type(servlet).__name__), self.assertLogs(level="ERROR") as logs:
                response = FakeResponse()
                servlet.do_POST(request, response)
                self.assertNotIn("secret detail", str(response.content))
                self.assertIn("secret detail", "\n".join(logs.output))

    def test_refusals(self) -> None:
        """
        A refused call gets a fixed message, without the permission it lacked
        """
        for error, message in (
            (AuthenticationRequired("Not permitted: secret.permission"), "Authentication required"),
            (AccessDenied("Not permitted: secret.permission"), "Access denied"),
        ):

            def refuse(*_: Any, error: Exception = error) -> None:
                raise error

            # The RSA servlet is not covered by the remote services authorization
            for servlet, body, content_type in make_rpc_servlets([])[:3]:
                with self.subTest(servlet=type(servlet).__name__, error=type(error).__name__):
                    servlet._dispatch_method = refuse
                    response = FakeResponse()
                    servlet.do_POST(FakeRequest(body, content_type), response)
                    self.assertEqual(response.code, 200)
                    self.assertIn(message, str(response.content))
                    self.assertNotIn("secret.permission", str(response.content))


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
