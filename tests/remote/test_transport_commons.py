#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Remote Services abstract transport classes

:author: Thomas Calmant
"""

import socket
import threading
import time
import unittest
import uuid
import xmlrpc.client as xmlrpclib
from typing import Any, Protocol, Self, cast
from unittest import mock

import jsonrpclib.jsonrpc

import pelix.constants
import pelix.framework
import pelix.remote
from pelix.internals.registry import ServiceReference
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.decorators import ComponentFactory, Property, Provides
from pelix.remote import RemoteServiceDispatcher, RemoteServiceError, json_rpc, security, xml_rpc
from pelix.remote.beans import ImportEndpoint
from pelix.remote.transport import commons, jabsorb_rpc, xmlrpc_client
from pelix.rsa.providers.distribution.xmlrpc import XmlRpcImportContainer
from pelix.security import ANONYMOUS, AccessDenied, AuthenticationRequired, Authorization, Subject, run_as
from tests.remote.test_security import FakeAuthorization

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Test factories
TEST_EXPORTER_FACTORY = "test-endpoint-exporter-factory"
TEST_IMPORTER_FACTORY = "test-endpoint-importer-factory"

# RS configuration
TEST_CONFIGURATION = "test.config"

# Test property
TEST_PROPERTY = "test.config.test_property"

# Events
EXPORT_MAKE = 1
IMPORT_MAKE = 2
IMPORT_CLEAR = 3
SERVICE_CALLED = 4

SERVICE_SECRET = "s3cr3t-value"

# ------------------------------------------------------------------------------


class DummyService:
    """
    Dummy exported service
    """

    def __init__(self) -> None:
        """
        Sets up a random value to be returned by the service method
        """
        self.value = uuid.uuid4()
        self.events: list[int] = []
        self._secret = SERVICE_SECRET

    def clear(self) -> None:
        """
        Clears the state
        """
        del self.events[:]

    def call_me(self) -> Any:
        """
        Sample call
        """
        self.events.append(SERVICE_CALLED)
        return self.value

    def _private_method(self) -> str:
        """
        Private method: it must not be callable by a remote caller
        """
        self.events.append(SERVICE_CALLED)
        return self._secret


@pelix.constants.Specification("sample.typed")
class TypedSpec(Protocol):
    """
    Specification of the typed service
    """

    def call_me(self) -> Any: ...


class TypedService(DummyService, TypedSpec):
    """
    Exported service implementing a typed specification and an extra public method
    """

    def extra(self) -> str:
        return "extra"


@ComponentFactory(TEST_EXPORTER_FACTORY)
@Provides(pelix.remote.RemoteServiceExportProvider)
@Property("_kinds", pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED, (TEST_CONFIGURATION,))
class Exporter(commons.AbstractRpcServiceExporter):
    """
    Service exporter
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Call parent
        super().__init__()

        self.events: list[int] = []
        self.raise_exception = False
        self.local_only = True

    def clear(self) -> None:
        """
        Clears the state
        """
        del self.events[:]

    def is_local_only(self) -> bool:
        return self.local_only

    def make_endpoint_properties(
        self, svc_ref: ServiceReference[Any], name: str, fw_uid: str | None
    ) -> dict[str, Any]:
        """
        Prepare properties for the ExportEndpoint to be created

        :param svc_ref: Service reference
        :param name: Endpoint name
        :param fw_uid: Framework UID
        :return: A dictionary of extra endpoint properties
        """
        assert fw_uid is not None
        self.events.append(EXPORT_MAKE)
        return {TEST_PROPERTY: fw_uid}


# ------------------------------------------------------------------------------


class Proxy:
    """
    Small test proxy
    """

    def __init__(self, fw_uid: str | None) -> None:
        """
        Sets up proxy data
        """
        self.fw_uid = fw_uid


@ComponentFactory(TEST_IMPORTER_FACTORY)
@Provides(pelix.remote.RemoteServiceImportEndpointListener)
@Property("_kinds", pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED, (TEST_CONFIGURATION,))
class Importer(commons.AbstractRpcServiceImporter):
    """
    Service importer
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Call parent
        super().__init__()

        self.events: list[int] = []
        self.raise_exception = False

    def clear(self) -> None:
        """
        Clears the state
        """
        del self.events[:]

    def make_service_proxy(self, endpoint: ImportEndpoint) -> Any:
        """
        Creates the proxy for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        :return: A service proxy
        """
        self.events.append(IMPORT_MAKE)
        fw_uid = endpoint.properties.get(TEST_PROPERTY)
        return Proxy(fw_uid)

    def clear_service_proxy(self, endpoint: ImportEndpoint) -> None:
        """
        Destroys the proxy made for the given ImportEndpoint

        :param endpoint: An ImportEndpoint bean
        """
        self.events.append(IMPORT_CLEAR)


# ------------------------------------------------------------------------------


class AbstractCommonExporterTest(unittest.TestCase):
    """
    Tests for the common code for exporters
    """

    framework: pelix.framework.Framework
    dispatcher: RemoteServiceDispatcher

    def setUp(self) -> None:
        """
        Sets up the test
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(("pelix.ipopo.core", "pelix.remote.dispatcher"))
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)
        self.framework.start()

        # Get the framework UID
        context = self.framework.get_bundle_context()
        self.framework_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Get the dispatcher and the imports registry
        svc_ref = context.get_service_reference(pelix.remote.RemoteServiceDispatcher)
        assert svc_ref is not None
        self.dispatcher = context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        self.framework.stop()
        pelix.framework.FrameworkFactory.delete_framework()

        # Clean up members
        self.framework = None  # type: ignore
        self.dispatcher = None

    def _install_exporter(self) -> Exporter:
        """
        Installs the service exporter

        :return: The Exporter component instance
        """
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            # Register the factory
            ipopo.register_factory(context, Exporter)

            # Instantiate the component
            return cast(Exporter, ipopo.instantiate(TEST_EXPORTER_FACTORY, "exporter", {}))

    def testExportAny(self) -> None:
        """
        Tests the call to the exporter, even if no configuration is given
        """
        # Install the export transport
        exporter = self._install_exporter()
        self.assertListEqual(exporter.events, [])

        # Register an exported service
        context = self.framework.get_bundle_context()
        service = object()
        svc_reg = context.register_service(
            "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # The exporter must have been called
        self.assertListEqual(exporter.events, [EXPORT_MAKE])
        exporter.clear()

        # Check the dispatcher content
        self.assertEqual(len(self.dispatcher.get_endpoints()), 1, "Export endpoint creation error ?")

        # Update the service
        svc_reg.set_properties({"some.property": 42})

        # Unregister the service
        svc_reg.unregister()

        # No call of the exporter
        self.assertListEqual(exporter.events, [])

    def testExportConfig(self) -> None:
        """
        Tests the call to the exporter, with a given configuration
        """
        # Install the export transport
        exporter = self._install_exporter()
        self.assertListEqual(exporter.events, [])

        for config in (exporter._kinds, "*"):
            # Register an exported service
            context = self.framework.get_bundle_context()
            service = object()
            svc_reg = context.register_service(
                "sample.spec",
                service,
                {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_EXPORTED_CONFIGS: config},
            )

            # Check if handle works correctly
            self.assertTrue(exporter.handles(config), f"Exporter doesn't handle {config}")

            # The exporter must have been called
            self.assertListEqual(exporter.events, [EXPORT_MAKE])
            exporter.clear()

            # Check the dispatcher content
            self.assertEqual(len(self.dispatcher.get_endpoints()), 1, "Export endpoint creation error ?")

            # Unregister the service
            svc_reg.unregister()

    def testExportDispatch(self) -> None:
        """
        Tests the call to the exported service
        """
        # Install the export transport
        exporter = self._install_exporter()

        # Register an exported service
        context = self.framework.get_bundle_context()
        service = DummyService()
        svc_reg = context.register_service(
            "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # The exporter must have been called
        self.assertListEqual(exporter.events, [EXPORT_MAKE])
        exporter.clear()

        # Get the export endpoint
        endpoint = self.dispatcher.get_endpoints()[0]

        # Call the test method
        method_name = f"{endpoint.name}.call_me"
        self.assertEqual(exporter.dispatch(method_name, []), service.value)
        self.assertListEqual(service.events, [SERVICE_CALLED], "Service not called")
        service.clear()

        # Call an unknown method
        self.assertRaises(RemoteServiceError, exporter.dispatch, f"{endpoint.name}.unknown", [])

        # Unregister the service
        svc_reg.unregister()

        # An exception must be raised
        self.assertRaises(RemoteServiceError, exporter.dispatch, method_name, [])
        self.assertListEqual(service.events, [], "Service called after unregistration")

    def testExportDispatchRestrictions(self) -> None:
        """
        Tests that only the public API of an exported service can be called.

        A remote caller must not be able to reach the special or private members
        of a service, e.g. to read its internal state or to reset it.
        """
        # Install the export transport
        exporter = self._install_exporter()

        # Register an exported service
        context = self.framework.get_bundle_context()
        service = DummyService()
        svc_reg = context.register_service(
            "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )
        exporter.clear()

        # Get the export endpoint
        endpoint = self.dispatcher.get_endpoints()[0]

        def dispatch(method_name: str, params: Any = None) -> Any:
            """
            Calls a method of the exported service
            """
            return exporter.dispatch(f"{endpoint.name}.{method_name}", params if params is not None else [])

        # Special methods must be refused
        for method_name in (
            "__init__",
            "__class__",
            "__dict__",
            "__str__",
            "__repr__",
            "__getattribute__",
            "__setattr__",
            "__reduce__",
        ):
            with self.subTest(method_name=method_name):
                self.assertRaises(RemoteServiceError, dispatch, method_name)

        # Private methods and attributes must be refused
        for method_name in ("_private_method", "_secret"):
            with self.subTest(method_name=method_name):
                self.assertRaises(RemoteServiceError, dispatch, method_name)

        # Public but non-callable attributes must be refused
        for method_name in ("value", "events"):
            with self.subTest(method_name=method_name):
                self.assertRaises(RemoteServiceError, dispatch, method_name)

        # Dotted names must be refused
        for method_name in ("clear.__self__", "a.b"):
            with self.subTest(method_name=method_name):
                self.assertRaises(RemoteServiceError, dispatch, method_name)

        # None of the above must have called the service
        self.assertListEqual(service.events, [], "Service called by a refused method")

        # The private state must not be readable through a special method
        self.assertRaises(RemoteServiceError, dispatch, "__getattribute__", ["_secret"])
        self.assertRaises(RemoteServiceError, dispatch, "__getattribute__", ["value"])

        # The public API must still work
        self.assertEqual(dispatch("call_me"), service.value)
        self.assertListEqual(service.events, [SERVICE_CALLED], "Service not called")
        service.clear()

        # The service must not have been altered by the refused calls
        self.assertEqual(service._secret, SERVICE_SECRET)

        # Unregister the service
        svc_reg.unregister()

    def testExportDispatchSecurity(self) -> None:
        """
        Tests the authorization of the calls and the restriction to the exported specification
        """
        exporter = self._install_exporter()
        context = self.framework.get_bundle_context()
        context.register_service(Authorization, FakeAuthorization({"granted"}), {})
        alice = Subject("alice", authenticated=True)

        # local only, export permission, subject, method, expected exception
        cases: list[tuple[bool, str | None, Subject, str, type[Exception] | None]] = [
            (True, None, ANONYMOUS, "call_me", None),
            (True, None, ANONYMOUS, "extra", RemoteServiceError),
            (False, None, ANONYMOUS, "call_me", AuthenticationRequired),
            (False, None, alice, "call_me", AccessDenied),
            (False, "*", ANONYMOUS, "call_me", None),
            (False, "granted", alice, "call_me", None),
            (True, "other", alice, "call_me", AccessDenied),
        ]
        for local_only, permission, subject, method, expected in cases:
            with self.subTest(
                local_only=local_only, permission=permission, subject=subject.name, method=method
            ):
                exporter.local_only = local_only
                properties: dict[str, Any] = {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
                if permission is not None:
                    properties[security.PROP_PERMISSION] = permission
                service = TypedService()
                svc_reg = context.register_service(TypedSpec, service, properties)
                try:
                    name = f"{self.dispatcher.get_endpoints()[0].name}.{method}"
                    with run_as(subject):
                        if expected is None:
                            self.assertEqual(exporter.dispatch(name, []), service.value)
                        else:
                            self.assertRaises(expected, exporter.dispatch, name, [])
                            self.assertListEqual(service.events, [])
                finally:
                    svc_reg.unregister()

    def testExportRename(self) -> None:
        """
        Tests the rename of an exported endpoint
        """
        # Install the export transport
        exporter = self._install_exporter()

        # Register an exported service
        context = self.framework.get_bundle_context()
        service = DummyService()
        service_2 = DummyService()
        svc_reg = context.register_service(
            "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # Get the export endpoint
        endpoint = self.dispatcher.get_endpoints()[0]

        # Call the test method
        method_name = f"{endpoint.name}.call_me"
        self.assertEqual(exporter.dispatch(method_name, []), service.value)
        service.clear()

        # Update the service endpoint name
        name = "endpoint_test"
        svc_reg.set_properties({pelix.remote.PROP_ENDPOINT_NAME: name})

        # Ensure the modification has been stored
        self.assertEqual(endpoint.name, name)

        # Call the test method
        method_name = f"{name}.call_me"
        self.assertEqual(exporter.dispatch(method_name, []), service.value)
        self.assertListEqual(service.events, [SERVICE_CALLED], "Service not called")
        service.clear()

        # Update another property
        svc_reg.set_properties({pelix.remote.PROP_ENDPOINT_NAME: name, "other.prop": 42})

        # Call the test method
        self.assertEqual(exporter.dispatch(method_name, []), service.value)
        self.assertListEqual(service.events, [SERVICE_CALLED], "Service not called")
        service.clear()

        # Register another service with the same name
        svc_reg_2 = context.register_service(
            "sample.spec",
            service_2,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_ENDPOINT_NAME: name},
        )

        # Call the test method
        # (the replacement endpoint should not be callable yet)
        self.assertEqual(exporter.dispatch(method_name, []), service.value)
        # The second service must be callable now
        self.assertListEqual(service.events, [SERVICE_CALLED], "Old service not called")
        self.assertListEqual(service_2.events, [], "New service called after registration")
        service.clear()
        service_2.clear()

        # Unregister the service
        svc_reg.unregister()

        # Check replacement of an endpoint by a previously
        # refused one.

        # Call the test method (the new replacement endpoint should be used)
        self.assertEqual(exporter.dispatch(method_name, []), service_2.value)

        # The second service must be callable now
        self.assertListEqual(service_2.events, [SERVICE_CALLED], "New service not called")
        self.assertListEqual(service.events, [], "Old service called after unregistration")
        service.clear()
        service_2.clear()

        # Unregister the second service
        svc_reg_2.unregister()


# ------------------------------------------------------------------------------


class AbstractCommonImporterTest(unittest.TestCase):
    """
    Tests for the common importer
    """

    framework: pelix.framework.Framework
    registry: pelix.remote.RemoteServiceRegistry

    def setUp(self) -> None:
        """
        Sets up the test
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(("pelix.ipopo.core", "pelix.remote.registry"))
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)
        self.framework.start()

        # Get the framework UID
        context = self.framework.get_bundle_context()
        self.framework_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Get the imports registry
        svc_ref = context.get_service_reference(pelix.remote.RemoteServiceRegistry)
        assert svc_ref is not None
        self.registry = context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        self.framework.stop()
        pelix.framework.FrameworkFactory.delete_framework()

        # Clean up members
        self.framework = None  # type: ignore
        self.registry = None

    def _install_importer(self) -> Importer:
        """
        Installs the service importer

        :return: The Importer component instance
        """
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            # Register the factory
            ipopo.register_factory(context, Importer)

            # Instantiate the component
            return cast(Importer, ipopo.instantiate(TEST_IMPORTER_FACTORY, "importer", {}))

    def testImportAny(self) -> None:
        """
        Tests the import of an endpoint for any configuration
        """
        # Install the importer
        importer = self._install_importer()

        # Prepare an import endpoint matching any configuration
        endpoint = ImportEndpoint("import-uid", "other-framework", "*", "endpoint_name", ["some.spec"], {})

        # Ensure the importer has not been called yet
        self.assertListEqual(importer.events, [], "Importer called before registration")

        # Register it
        self.registry.add(endpoint)
        self.assertListEqual(importer.events, [IMPORT_MAKE], "Importer not called after registration")
        importer.clear()

        # Update it
        props = endpoint.properties.copy()
        props["other.value"] = 42
        self.registry.update(endpoint.uid, props)

        # The import has not been called
        self.assertListEqual(importer.events, [], "Importer called after update")

        # Clear it
        self.registry.remove(endpoint.uid)
        self.assertListEqual(importer.events, [IMPORT_CLEAR], "Importer not called after unregistration")

    def testImportUnknownConfig(self) -> None:
        """
        Tests the import of an endpoint for an unknown configuration
        """
        # Install the importer
        importer = self._install_importer()

        # Prepare an import endpoint with an unknown configuration
        endpoint = ImportEndpoint(
            "import-uid", "other-framework", "unknown-config", "endpoint_name", ["some.spec"], {}
        )

        # Register it
        self.registry.add(endpoint)
        self.assertListEqual(importer.events, [], "Importer called for an unknown configuration")

        # Remove it
        self.registry.remove(endpoint.uid)
        self.assertListEqual(importer.events, [], "Importer called for an unknown configuration")

    def testImportKnownConfig(self) -> None:
        """
        Tests the import of an endpoint for a known configuration
        """
        # Install the importer
        importer = self._install_importer()

        # Prepare an import endpoint with a known configuration
        endpoint = ImportEndpoint(
            "import-uid", "other-framework", importer._kinds, "endpoint_name", ["some.spec"], {}
        )

        # Register it
        self.registry.add(endpoint)
        self.assertListEqual(importer.events, [IMPORT_MAKE], "Importer not called for a known configuration")
        importer.clear()

        # Clear it
        self.registry.remove(endpoint.uid)
        self.assertListEqual(importer.events, [IMPORT_CLEAR], "Importer not called after unregistration")

    def testLostFramework(self) -> None:
        """
        Tests the loss of a framework
        """
        # Install the importer
        importer = self._install_importer()

        # Prepare an import endpoint matching any configuration
        fw_uid = "other-framework"
        endpoint = ImportEndpoint("import-uid", fw_uid, "*", "endpoint_name", ["some.spec"], {})

        # Register it
        self.registry.add(endpoint)
        self.assertListEqual(importer.events, [IMPORT_MAKE], "Importer not called after registration")
        importer.clear()

        # Clear it
        self.registry.lost_framework(endpoint.framework)
        self.assertListEqual(importer.events, [IMPORT_CLEAR], "Importer not called after framework loss")


# ------------------------------------------------------------------------------


class HostileServer:
    """
    An HTTP server which never answers (``body`` is None) or answers the given body
    """

    def __init__(self, body: bytes | None) -> None:
        self.__body = body
        self.__server = socket.create_server(("127.0.0.1", 0))
        self.__server.settimeout(10)
        self.port: int = self.__server.getsockname()[1]
        self.__stop = threading.Event()
        self.__thread = threading.Thread(target=self.__serve, daemon=True)

    def __enter__(self) -> Self:
        self.__thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.__stop.set()
        self.__server.close()
        self.__thread.join(10)

    def __serve(self) -> None:
        while not self.__stop.is_set():
            try:
                client, _ = self.__server.accept()
            except OSError:
                return

            with client:
                client.recv(65536)
                if self.__body is not None:
                    client.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/xml\r\n"
                        + f"Content-Length: {len(self.__body)}\r\n\r\n".encode()
                        + self.__body
                    )
                self.__stop.wait(10)


class ClientLimitsTest(unittest.TestCase):
    """
    Tests the limits of the calls to other frameworks
    """

    def test_get_client_limits(self) -> None:
        """
        Tests the parsing of the framework properties
        """
        defaults = (commons.DEFAULT_CLIENT_TIMEOUT, commons.DEFAULT_CLIENT_MAX_RESPONSE_SIZE)
        for timeout, max_size, expected in (
            (None, None, defaults),
            ("2.5", "100", (2.5, 100)),
            (3, 200, (3.0, 200)),
            ("0", "-1", (None, None)),
            ("abc", "1.5", defaults),
        ):
            with self.subTest(timeout=timeout, max_size=max_size):
                properties = {
                    pelix.remote.PROP_CLIENT_TIMEOUT: timeout,
                    pelix.remote.PROP_CLIENT_MAX_RESPONSE_SIZE: max_size,
                }
                context = mock.Mock(get_property=properties.get)
                self.assertEqual(tuple(commons.get_client_limits(context)), expected)

    def test_transports(self) -> None:
        """
        Tests that the RPC proxies give up on a server which doesn't answer or sends too much
        """
        limits = commons.ClientLimits(0.5, 1024)
        for proxy_class, make_transport in (
            (xmlrpclib.ServerProxy, xmlrpc_client.make_client_transport),
            (jsonrpclib.jsonrpc.ServerProxy, json_rpc.make_client_transport),
        ):
            for body, error in ((None, TimeoutError), (b" " * 4096, RemoteServiceError)):
                with (
                    self.subTest(proxy=proxy_class.__module__, body=body is not None),
                    HostileServer(body) as server,
                ):
                    url = f"http://127.0.0.1:{server.port}/"
                    proxy = proxy_class(url, transport=make_transport(url, limits))
                    start = time.monotonic()
                    with self.assertRaises(error):
                        proxy.some.method()
                    self.assertLess(time.monotonic() - start, 5)

    def test_proxies(self) -> None:
        """
        Tests that the proxies of the imported services apply the limits
        """
        context = mock.Mock(get_property={pelix.remote.PROP_CLIENT_TIMEOUT: 0.5}.get)
        container = XmlRpcImportContainer()

        with (
            HostileServer(None) as server,
            mock.patch.object(container, "_get_bundle_context", lambda: context),
        ):
            url = f"http://127.0.0.1:{server.port}/"
            limits = commons.get_client_limits(context)
            for proxy in (
                json_rpc._ServiceCallProxy("name", url, limits),
                xml_rpc._ServiceCallProxy("name", url, limits),
                jabsorb_rpc._ServiceCallProxy("name", url, limits),
                container._prepare_proxy(mock.Mock(get_remoteservice_id=lambda: (("ns", url), 1))),
            ):
                with self.subTest(proxy=type(proxy).__module__):
                    start = time.monotonic()
                    with self.assertRaises(TimeoutError):
                        proxy.method()
                    self.assertLess(time.monotonic() - start, 5)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
