#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Remote Service Admin implementation (export/import registrations,
their life cycle, error paths and events) with fake distribution containers

:author: Thomas Calmant
"""

import io
import sys
import unittest
from typing import Any, cast

import pelix.framework
import pelix.rsa.remoteserviceadmin as rsa
from pelix.constants import OBJECTCLASS, OSGI_FRAMEWORK_UUID, SERVICE_BUNDLEID, SERVICE_ID, SERVICE_RANKING
from pelix.framework import BundleContext, Framework
from pelix.internals.registry import ServiceReference
from pelix.rsa import (
    ENDPOINT_FRAMEWORK_UUID,
    ERROR_ECF_EP_ID,
    ERROR_IMPORTED_CONFIGS,
    ERROR_NAMESPACE,
    REMOTE_CONFIGS_SUPPORTED,
    SERVICE_EXPORTED_CONFIGS,
    SERVICE_EXPORTED_INTENTS,
    SERVICE_EXPORTED_INTENTS_EXTRA,
    SERVICE_EXPORTED_INTERFACES,
    SERVICE_IMPORTED,
    SERVICE_INTENTS,
    RemoteServiceAdminEvent,
    RemoteServiceError,
    SelectImporterError,
    get_current_time_millis,
    get_ecf_props,
    get_edef_props,
    get_extra_props,
    get_next_rsid,
    get_rsa_props,
    merge_dicts,
)
from pelix.rsa.endpointdescription import EndpointDescription

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

FAKE_CONFIG = "test.fake.config"
FAKE_NAMESPACE = "test.fake.namespace"
SPEC = "test.rsa.spec"
REMOTE_FW_UUID = "remote-framework-uuid"

# ------------------------------------------------------------------------------


class FakeExportContainer:
    """
    Export container recording its calls, with configurable failures
    """

    def __init__(self, container_id: str = "fake-exporter") -> None:
        self._id = container_id
        self.prepare_error: Exception | None = None
        self.export_error: Exception | None = None
        self.export_returns_none = False
        self.unexport_error: Exception | None = None
        self.exported: list[EndpointDescription] = []
        self.unexported: list[EndpointDescription] = []

    def get_id(self) -> str:
        return self._id

    def get_namespace(self) -> str:
        return FAKE_NAMESPACE

    def prepare_endpoint_props(
        self, intfs: list[str], svc_ref: ServiceReference[Any], export_props: dict[str, Any]
    ) -> dict[str, Any]:
        if self.prepare_error is not None:
            raise self.prepare_error

        rsa_props = get_rsa_props(
            intfs,
            [FAKE_CONFIG],
            None,
            svc_ref.get_property(SERVICE_ID),
            export_props.get(ENDPOINT_FRAMEWORK_UUID),
        )
        ecf_props = get_ecf_props(self._id, FAKE_NAMESPACE, get_next_rsid(), get_current_time_millis())
        return merge_dicts(rsa_props, ecf_props, get_extra_props(export_props))

    def export_service(self, svc_ref: ServiceReference[Any], props: dict[str, Any]) -> Any:
        if self.export_error is not None:
            raise self.export_error

        if self.export_returns_none:
            return None

        ed = EndpointDescription.fromprops(props)
        self.exported.append(ed)
        return ed

    def unexport_service(self, ed: EndpointDescription) -> None:
        self.unexported.append(ed)
        if self.unexport_error is not None:
            raise self.unexport_error


class FakeImportContainer:
    """
    Import container registering a dummy proxy, with configurable failures
    """

    def __init__(self, context: BundleContext) -> None:
        self._context = context
        self.import_error: Exception | None = None
        self.import_returns_none = False
        self.unimport_error: Exception | None = None
        self.imported: list[EndpointDescription] = []
        self.unimported: list[EndpointDescription] = []

    def get_id(self) -> str:
        return "fake-importer"

    def get_namespace(self) -> str:
        return FAKE_NAMESPACE

    def _prepare_proxy_props(self, ed: EndpointDescription) -> dict[str, Any]:
        props = ed.get_properties()
        for key in (OBJECTCLASS, SERVICE_ID, SERVICE_BUNDLEID):
            props.pop(key, None)
        props[SERVICE_IMPORTED] = True
        return props

    def import_service(self, ed: EndpointDescription) -> Any:
        if self.import_error is not None:
            raise self.import_error

        if self.import_returns_none:
            return None

        self.imported.append(ed)
        return self._context.register_service(ed.get_interfaces(), object(), self._prepare_proxy_props(ed))

    def unimport_service(self, ed: EndpointDescription) -> None:
        self.unimported.append(ed)
        if self.unimport_error is not None:
            raise self.unimport_error


class FakeExportSelector:
    """
    Export container selector returning the configured containers
    """

    def __init__(self) -> None:
        self.containers: list[Any] = []
        self.error: Exception | None = None

    def select_export_containers(
        self, service_ref: ServiceReference[Any], exported_intfs: list[str], export_props: dict[str, Any]
    ) -> list[Any]:
        if self.error is not None:
            raise self.error
        return self.containers


class FakeImportSelector:
    """
    Import container selector returning the configured container
    """

    def __init__(self) -> None:
        self.container: Any = None
        self.remote_configs: list[str] | None = None

    def select_import_container(
        self, remote_configs: list[str], endpoint_description: EndpointDescription
    ) -> Any:
        self.remote_configs = remote_configs
        return self.container


class EventCollector:
    """
    RSA listener keeping track of the events it receives
    """

    def __init__(self) -> None:
        self.events: list[RemoteServiceAdminEvent] = []

    def remote_admin_event(self, event: RemoteServiceAdminEvent) -> None:
        self.events.append(event)

    def types(self) -> list[int]:
        return [event.get_type() for event in self.events]


class FailingListener:
    """
    RSA listener which always fails: it must not break the RSA
    """

    def remote_admin_event(self, event: RemoteServiceAdminEvent) -> None:
        raise ValueError("Listener failure")


class FakeExportProvider:
    """
    Export distribution provider supporting only a given configuration
    """

    def __init__(self, config: str, container: Any) -> None:
        self._config = config
        self._container = container
        self.calls: list[tuple[list[str] | None, list[str], dict[str, Any]]] = []

    def supports_export(
        self, exported_configs: list[str] | None, service_intents: list[str], export_props: dict[str, Any]
    ) -> Any:
        self.calls.append((exported_configs, service_intents, export_props))
        if exported_configs and self._config in exported_configs:
            return self._container
        return None


class FakeImportProvider:
    """
    Import distribution provider supporting only a given configuration
    """

    def __init__(self, config: str, container: Any) -> None:
        self._config = config
        self._container = container

    def supports_import(self, remote_configs: list[str], intents: list[str], props: dict[str, Any]) -> Any:
        if self._config in remote_configs:
            return self._container
        return None


def make_remote_ed(service_id: int = 42, **extra: Any) -> EndpointDescription:
    """
    Prepares the description of an endpoint of a remote framework
    """
    props = get_edef_props(
        [SPEC],
        [FAKE_CONFIG],
        FAKE_NAMESPACE,
        "unused",
        "remote-container",
        service_id,
        get_current_time_millis(),
        fw_id=REMOTE_FW_UUID,
    )
    props.update(extra)
    return EndpointDescription.fromprops(props)


# ------------------------------------------------------------------------------


class RSATestBase(unittest.TestCase):
    """
    Starts a framework with the RSA, fake selectors and an event collector
    """

    framework: Framework
    context: BundleContext
    rsa: rsa.RemoteServiceAdminImpl

    def setUp(self) -> None:
        self.framework = pelix.framework.create_framework(["pelix.ipopo.core"])
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        self.exporter = FakeExportContainer()
        self.importer = FakeImportContainer(self.context)
        self.export_selector = FakeExportSelector()
        self.import_selector = FakeImportSelector()
        self.collector = EventCollector()

        # Registered before the RSA bundle so that it binds to our selectors
        # instead of its lowest-ranked defaults
        self.context.register_service(
            rsa.ExportContainerSelector, self.export_selector, {SERVICE_RANKING: 1000}
        )
        self.context.register_service(
            rsa.ImportContainerSelector, self.import_selector, {SERVICE_RANKING: 1000}
        )
        self.context.register_service(rsa.RemoteServiceAdminListener, self.collector, {})

        self.rsa_bundle = self.context.install_bundle("pelix.rsa.remoteserviceadmin")
        self.rsa_bundle.start()
        svc_ref = self.context.get_service_reference(rsa.RemoteServiceAdmin)
        assert svc_ref is not None
        self.rsa = cast(rsa.RemoteServiceAdminImpl, self.context.get_service(svc_ref))

    def tearDown(self) -> None:
        self.framework.delete(True)

    def register_exported(self, **props: Any) -> ServiceReference[Any]:
        """
        Registers a service to export
        """
        props.setdefault(SERVICE_EXPORTED_INTERFACES, "*")
        return self.context.register_service(SPEC, object(), props).get_reference()


class ExportTest(RSATestBase):
    """
    Tests the export side of the RSA
    """

    def test_invalid_arguments(self) -> None:
        """
        Missing service reference or exported interfaces are errors, not
        silently ignored
        """
        with self.assertRaises(RemoteServiceError):
            self.rsa.export_service(cast(Any, None))

        svc_ref = self.context.register_service(SPEC, object(), {}).get_reference()
        with self.assertRaises(RemoteServiceError):
            self.rsa.export_service(svc_ref)

        self.assertEqual([], self.collector.events)
        self.assertEqual([], self.rsa.get_exported_services())

    def test_interface_not_provided(self) -> None:
        """
        Exporting an interface the service doesn't provide exports nothing
        """
        self.export_selector.containers = [self.exporter]
        svc_ref = self.register_exported()

        self.assertEqual([], self.rsa.export_service(svc_ref, {SERVICE_EXPORTED_INTERFACES: ["other.spec"]}))
        self.assertEqual([], self.exporter.exported)
        self.assertEqual([], self.collector.events)

    def test_no_container(self) -> None:
        """
        No container found: nothing exported, no event
        """
        svc_ref = self.register_exported()
        self.assertEqual([], self.rsa.export_service(svc_ref))
        self.assertEqual([], self.collector.events)
        self.assertEqual([], self.rsa.get_exported_services())

    def test_selector_error(self) -> None:
        """
        An error in the container selector gives an errored registration
        """
        self.export_selector.error = KeyError("selector failure")
        svc_ref = self.register_exported()

        regs = self.rsa.export_service(svc_ref)
        self.assertEqual(1, len(regs))
        reg = regs[0]

        exception = reg.get_exception()
        assert exception is not None
        self.assertIs(exception[0], KeyError)
        self.assertEqual([RemoteServiceAdminEvent.EXPORT_ERROR], self.collector.types())
        self.assertIs(exception, self.collector.events[0].get_exception())

        # The errored reference has no service, but a description
        exp_ref = reg.get_export_reference()
        assert exp_ref is not None
        self.assertIsNone(exp_ref.get_reference())
        self.assertIsNone(reg.get_reference())
        self.assertIsNone(exp_ref.update({"a": 1}))
        self.assertEqual(ERROR_IMPORTED_CONFIGS, reg.get_description().get_configuration_types())
        self.assertEqual((ERROR_NAMESPACE, ERROR_ECF_EP_ID), reg.get_export_container_id())

        # Updating an errored registration fails
        self.assertIsNone(reg.update({"a": 1}))
        update_exc = reg.get_exception()
        assert update_exc is not None
        self.assertIs(update_exc[0], RemoteServiceError)

        # Closing it doesn't publish anything, as nothing was exported
        del self.collector.events[:]
        reg.close()
        self.assertEqual([], self.collector.events)

    def test_export_container_failures(self) -> None:
        """
        Failures of the export container give errored registrations
        """
        self.export_selector.containers = [self.exporter]

        for error in (ValueError("prepare"), None, TypeError("export")):
            if isinstance(error, ValueError):
                self.exporter.prepare_error = error
                expected = ValueError
            elif error is None:
                self.exporter.prepare_error = None
                self.exporter.export_returns_none = True
                expected = RemoteServiceError
            else:
                self.exporter.export_returns_none = False
                self.exporter.export_error = error
                expected = TypeError

            del self.collector.events[:]
            regs = self.rsa.export_service(self.register_exported())
            self.assertEqual(1, len(regs))
            exception = regs[0].get_exception()
            assert exception is not None
            self.assertIs(exception[0], expected)
            self.assertEqual([RemoteServiceAdminEvent.EXPORT_ERROR], self.collector.types())

        self.assertEqual([], self.exporter.exported)

    def test_export_and_close(self) -> None:
        """
        Nominal export life cycle
        """
        self.export_selector.containers = [self.exporter]
        svc_ref = self.register_exported(foo="bar")

        regs = self.rsa.export_service(svc_ref, {SERVICE_EXPORTED_CONFIGS: FAKE_CONFIG})
        self.assertEqual(1, len(regs))
        reg = regs[0]
        self.assertIsNone(reg.get_exception())
        self.assertIs(svc_ref, reg.get_reference())
        self.assertEqual((FAKE_NAMESPACE, self.exporter.get_id()), reg.get_export_container_id())

        ed = reg.get_description()
        self.assertEqual([ed], self.exporter.exported)
        self.assertEqual("bar", ed.get_properties()["foo"])
        self.assertEqual(ed.get_remoteservice_id(), reg.get_remoteservice_id())
        self.assertEqual(self.context.get_property(OSGI_FRAMEWORK_UUID), ed.get_framework_uuid())

        # Check the export reference and the event
        exp_ref = reg.get_export_reference()
        assert exp_ref is not None
        self.assertEqual([exp_ref], self.rsa.get_exported_services())
        self.assertIs(svc_ref, exp_ref.get_reference())
        self.assertEqual(ed, exp_ref.get_description())
        self.assertEqual(reg.get_export_container_id(), exp_ref.get_export_container_id())
        self.assertEqual(reg.get_remoteservice_id(), exp_ref.get_remoteservice_id())

        self.assertEqual([RemoteServiceAdminEvent.EXPORT_REGISTRATION], self.collector.types())
        event = self.collector.events[0]
        self.assertIs(exp_ref, event.get_export_ref())
        self.assertEqual(ed, event.get_description())
        self.assertIs(self.rsa_bundle, event.get_source())

        # Close it
        del self.collector.events[:]
        reg.close()
        self.assertEqual([ed], self.exporter.unexported)
        self.assertEqual([], self.rsa.get_exported_services())
        self.assertEqual([RemoteServiceAdminEvent.EXPORT_UNREGISTRATION], self.collector.types())
        self.assertEqual(ed, self.collector.events[0].get_description())

        # Closed registration: getters are disabled, close is idempotent
        self.assertIsNone(reg.get_export_reference())
        self.assertIsNone(reg.get_reference())
        self.assertFalse(cast(rsa.ExportRegistrationImpl, reg).match_sr(svc_ref))
        for method in (reg.get_description, reg.get_export_container_id, reg.get_remoteservice_id):
            with self.assertRaises(RemoteServiceError):
                method()

        self.assertIsNone(reg.update({"a": 1}))
        exception = reg.get_exception()
        assert exception is not None
        self.assertIs(exception[0], RemoteServiceError)

        reg.close()
        self.assertEqual([ed], self.exporter.unexported)
        self.assertEqual(1, len(self.collector.events))

    def test_update(self) -> None:
        """
        Updating an export gives a new description with the new service
        properties and publishes an update event
        """
        self.export_selector.containers = [self.exporter]
        svc_reg = self.context.register_service(SPEC, object(), {SERVICE_EXPORTED_INTERFACES: "*", "foo": 1})
        reg = self.rsa.export_service(svc_reg.get_reference())[0]
        ed = reg.get_description()

        svc_reg.set_properties({"foo": 2})
        del self.collector.events[:]
        new_ed = reg.update({"extra": "value"})
        assert new_ed is not None
        self.assertIsNone(reg.get_exception())

        # Same endpoint, new properties
        self.assertEqual(ed.get_id(), new_ed.get_id())
        self.assertEqual(2, new_ed.get_properties()["foo"])
        self.assertEqual("value", new_ed.get_properties()["extra"])
        self.assertEqual(new_ed, reg.get_description())
        self.assertEqual([RemoteServiceAdminEvent.EXPORT_UPDATE], self.collector.types())

        # An update with no property keeps the original ones
        no_props_ed = reg.update(None)
        assert no_props_ed is not None
        self.assertNotIn("extra", no_props_ed.get_properties())
        self.assertEqual(2, no_props_ed.get_properties()["foo"])

    def test_export_twice(self) -> None:
        """
        Exporting a service twice with the same container reuses the endpoint
        until all its registrations are closed
        """
        self.export_selector.containers = [self.exporter]
        svc_ref = self.register_exported()

        reg_1 = self.rsa.export_service(svc_ref)[0]
        reg_2 = self.rsa.export_service(svc_ref)[0]
        self.assertIsNot(reg_1, reg_2)
        self.assertEqual(reg_1.get_description(), reg_2.get_description())

        # Only one real export and one registration event
        self.assertEqual(1, len(self.exporter.exported))
        self.assertEqual([RemoteServiceAdminEvent.EXPORT_REGISTRATION], self.collector.types())

        # The endpoint survives the first close
        reg_1.close()
        self.assertEqual([], self.exporter.unexported)
        self.assertEqual(1, len(self.rsa.get_exported_services()))

        reg_2.close()
        self.assertEqual(self.exporter.exported, self.exporter.unexported)
        self.assertEqual([], self.rsa.get_exported_services())

    def test_export_twice_close_event(self) -> None:
        """
        Closing a registration which doesn't close the endpoint must not
        publish an EXPORT_UNREGISTRATION event: it is only published when the
        last registration is closed
        """
        self.export_selector.containers = [self.exporter]
        svc_ref = self.register_exported()

        reg_1 = self.rsa.export_service(svc_ref)[0]
        reg_2 = self.rsa.export_service(svc_ref)[0]
        del self.collector.events[:]

        reg_1.close()
        self.assertEqual([], self.collector.types())

        reg_2.close()
        self.assertEqual([RemoteServiceAdminEvent.EXPORT_UNREGISTRATION], self.collector.types())

    def test_multiple_containers(self) -> None:
        """
        Each selected container gets its own export registration
        """
        other = FakeExportContainer("other-exporter")
        self.export_selector.containers = [self.exporter, other]
        svc_ref = self.register_exported()

        regs = self.rsa.export_service(svc_ref)
        self.assertEqual(2, len(regs))
        self.assertEqual(
            {(FAKE_NAMESPACE, "fake-exporter"), (FAKE_NAMESPACE, "other-exporter")},
            {reg.get_export_container_id() for reg in regs},
        )
        self.assertEqual(1, len(self.exporter.exported))
        self.assertEqual(1, len(other.exported))
        self.assertEqual(
            [RemoteServiceAdminEvent.EXPORT_REGISTRATION] * 2,
            self.collector.types(),
        )

    def test_unexport_error(self) -> None:
        """
        An error while unexporting doesn't prevent the registration from
        being closed
        """
        self.export_selector.containers = [self.exporter]
        self.exporter.unexport_error = ValueError("unexport")
        reg = self.rsa.export_service(self.register_exported())[0]

        reg.close()
        self.assertEqual(1, len(self.exporter.unexported))
        self.assertEqual([], self.rsa.get_exported_services())
        self.assertIsNone(reg.get_export_reference())

    def test_failing_listener(self) -> None:
        """
        A failing event listener doesn't prevent other listeners from being
        notified, nor the export from succeeding
        """
        self.context.register_service(
            rsa.RemoteServiceAdminListener, FailingListener(), {SERVICE_RANKING: 100}
        )
        self.export_selector.containers = [self.exporter]

        regs = self.rsa.export_service(self.register_exported())
        self.assertIsNone(regs[0].get_exception())
        self.assertEqual([RemoteServiceAdminEvent.EXPORT_REGISTRATION], self.collector.types())

    def test_stop_rsa(self) -> None:
        """
        Stopping the RSA closes all its registrations
        """
        self.export_selector.containers = [self.exporter]
        self.import_selector.container = self.importer
        self.rsa.export_service(self.register_exported())
        self.rsa.import_service(make_remote_ed())
        self.assertIsNotNone(self.context.get_service_reference(SPEC, f"({SERVICE_IMPORTED}=*)"))

        self.rsa_bundle.stop()
        self.assertEqual(self.exporter.exported, self.exporter.unexported)
        self.assertEqual(self.importer.imported, self.importer.unimported)
        self.assertIsNone(self.context.get_service_reference(SPEC, f"({SERVICE_IMPORTED}=*)"))


class ImportTest(RSATestBase):
    """
    Tests the import side of the RSA
    """

    def test_invalid_arguments(self) -> None:
        """
        Missing description or remote configurations are errors
        """
        with self.assertRaises(RemoteServiceError):
            self.rsa.import_service(cast(Any, None))

        props = make_remote_ed().get_properties()
        del props[REMOTE_CONFIGS_SUPPORTED]
        with self.assertRaises(RemoteServiceError):
            self.rsa.import_service(EndpointDescription.fromprops(props))

        self.assertEqual([], self.collector.events)

    def test_no_importer(self) -> None:
        """
        No import container: errored registration
        """
        ed = make_remote_ed()
        reg = self.rsa.import_service(ed)
        self.assertEqual([FAKE_CONFIG], self.import_selector.remote_configs)

        exception = reg.get_exception()
        assert exception is not None
        self.assertIs(exception[0], SelectImporterError)
        self.assertIsNone(reg.get_reference())
        self.assertEqual(ed, reg.get_description())
        self.assertEqual(ed.get_container_id(), reg.get_import_container_id())
        self.assertEqual(ed.get_container_id(), reg.get_export_container_id())
        self.assertEqual(ed.get_remoteservice_id(), reg.get_remoteservice_id())
        self.assertEqual(
            FAKE_NAMESPACE,
            cast(rsa.ImportReferenceImpl, reg.get_import_reference()).get_import_container_ns(),
        )
        self.assertEqual([RemoteServiceAdminEvent.IMPORT_ERROR], self.collector.types())

        # Errored imports can't be updated and are closed silently
        self.assertFalse(reg.update(ed))
        del self.collector.events[:]
        reg.close()
        self.assertEqual([], self.collector.events)

    def test_import_container_failures(self) -> None:
        """
        Failures of the import container give errored registrations
        """
        self.import_selector.container = self.importer
        for idx, expected in enumerate((RemoteServiceError, KeyError)):
            if expected is RemoteServiceError:
                self.importer.import_returns_none = True
            else:
                self.importer.import_returns_none = False
                self.importer.import_error = KeyError("import")

            del self.collector.events[:]
            reg = self.rsa.import_service(make_remote_ed(100 + idx))
            exception = reg.get_exception()
            assert exception is not None
            self.assertIs(exception[0], expected)
            self.assertEqual([RemoteServiceAdminEvent.IMPORT_ERROR], self.collector.types())

        self.assertIsNone(self.context.get_service_reference(SPEC))

    def test_import_and_close(self) -> None:
        """
        Nominal import life cycle
        """
        self.import_selector.container = self.importer
        ed = make_remote_ed(foo="bar")

        reg = self.rsa.import_service(ed)
        self.assertIsNone(reg.get_exception())
        self.assertEqual([ed], self.importer.imported)

        # The proxy is registered with the endpoint properties
        proxy_ref = reg.get_reference()
        assert proxy_ref is not None
        self.assertEqual("bar", proxy_ref.get_property("foo"))
        self.assertIs(proxy_ref, self.context.get_service_reference(SPEC))

        self.assertEqual(ed, reg.get_description())
        self.assertEqual((FAKE_NAMESPACE, "fake-importer"), reg.get_import_container_id())
        self.assertEqual(ed.get_container_id(), reg.get_export_container_id())
        self.assertEqual(ed.get_remoteservice_id(), reg.get_remoteservice_id())

        imp_ref = reg.get_import_reference()
        self.assertEqual([imp_ref], self.rsa.get_imported_endpoints())
        self.assertIs(proxy_ref, imp_ref.get_reference())
        self.assertEqual(FAKE_NAMESPACE, cast(rsa.ImportReferenceImpl, imp_ref).get_import_container_ns())
        self.assertEqual(ed.get_container_id(), imp_ref.get_export_container_id())
        self.assertEqual(ed.get_remoteservice_id(), imp_ref.get_remoteservice_id())

        self.assertEqual([RemoteServiceAdminEvent.IMPORT_REGISTRATION], self.collector.types())
        self.assertIs(imp_ref, self.collector.events[0].get_import_ref())

        # Close it
        del self.collector.events[:]
        reg.close()
        self.assertEqual([ed], self.importer.unimported)
        self.assertIsNone(self.context.get_service_reference(SPEC))
        self.assertEqual([], self.rsa.get_imported_endpoints())
        self.assertEqual([RemoteServiceAdminEvent.IMPORT_UNREGISTRATION], self.collector.types())

        # Closed registration
        self.assertIsNone(reg.get_reference())
        self.assertIsNone(reg.get_exception())
        for method in (
            reg.get_import_reference,
            reg.get_description,
            reg.get_import_container_id,
            reg.get_export_container_id,
            reg.get_remoteservice_id,
        ):
            with self.assertRaises(RemoteServiceError):
                method()

        self.assertFalse(reg.update(ed))
        exception = reg.get_exception()
        assert exception is not None
        self.assertIs(exception[0], RemoteServiceError)

        reg.close()
        self.assertEqual([ed], self.importer.unimported)

    def test_update(self) -> None:
        """
        Updating an import updates the proxy properties
        """
        self.import_selector.container = self.importer
        reg = self.rsa.import_service(make_remote_ed(foo="bar"))
        proxy_ref = reg.get_reference()
        assert proxy_ref is not None

        del self.collector.events[:]
        self.assertTrue(reg.update(make_remote_ed(foo="baz")))
        self.assertIsNone(reg.get_exception())
        self.assertEqual("baz", proxy_ref.get_property("foo"))
        self.assertEqual("baz", reg.get_description().get_properties()["foo"])
        self.assertEqual([RemoteServiceAdminEvent.IMPORT_UPDATE], self.collector.types())

    def test_update_error(self) -> None:
        """
        An error while updating is kept in the registration
        """
        self.import_selector.container = self.importer
        reg = self.rsa.import_service(make_remote_ed())

        # Invalid description: the update fails before touching the proxy
        self.assertFalse(reg.update(cast(EndpointDescription, object())))
        exception = reg.get_exception()
        assert exception is not None
        self.assertIs(exception[0], AttributeError)

    def test_import_twice(self) -> None:
        """
        Importing the same remote service twice reuses the proxy, updated
        with the new description, until all registrations are closed
        """
        self.import_selector.container = self.importer
        reg_1 = self.rsa.import_service(make_remote_ed(foo="bar"))
        proxy_ref = reg_1.get_reference()
        assert proxy_ref is not None

        reg_2 = self.rsa.import_service(make_remote_ed(foo="baz"))
        self.assertIsNot(reg_1, reg_2)
        self.assertIs(proxy_ref, reg_2.get_reference())
        self.assertEqual("baz", proxy_ref.get_property("foo"))
        self.assertEqual(1, len(self.importer.imported))
        self.assertEqual([RemoteServiceAdminEvent.IMPORT_REGISTRATION], self.collector.types())

        # Another remote service is imported separately
        reg_3 = self.rsa.import_service(make_remote_ed(43))
        self.assertIsNot(proxy_ref, reg_3.get_reference())
        self.assertEqual(2, len(self.importer.imported))

        # The proxy survives the first close
        reg_1.close()
        self.assertEqual([], self.importer.unimported)
        self.assertIsNotNone(proxy_ref.get_bundle())
        self.assertIn(proxy_ref, self.context.get_all_service_references(SPEC) or [])

        reg_2.close()
        self.assertEqual(1, len(self.importer.unimported))
        self.assertNotIn(proxy_ref, self.context.get_all_service_references(SPEC) or [])

    def test_import_twice_close_event(self) -> None:
        """
        Closing a registration which doesn't close the endpoint must not
        publish an IMPORT_UNREGISTRATION event: it is only published when the
        last registration is closed
        """
        self.import_selector.container = self.importer
        reg_1 = self.rsa.import_service(make_remote_ed())
        reg_2 = self.rsa.import_service(make_remote_ed())
        del self.collector.events[:]

        reg_1.close()
        self.assertEqual([], self.collector.types())

        reg_2.close()
        self.assertEqual([RemoteServiceAdminEvent.IMPORT_UNREGISTRATION], self.collector.types())

    def test_unimport_error(self) -> None:
        """
        An error while unimporting still unregisters the proxy
        """
        self.import_selector.container = self.importer
        self.importer.unimport_error = ValueError("unimport")
        reg = self.rsa.import_service(make_remote_ed())

        reg.close()
        self.assertEqual(1, len(self.importer.unimported))
        self.assertIsNone(self.context.get_service_reference(SPEC))
        self.assertIsNone(reg.get_reference())


# ------------------------------------------------------------------------------


class InternalsTest(RSATestBase):
    """
    Tests the internal classes used by the RSA
    """

    def test_registration_arguments(self) -> None:
        """
        Registrations and references need an endpoint or an error
        """
        for klass in (rsa.ExportRegistrationImpl, rsa.ExportReferenceImpl, rsa.ImportRegistrationImpl):
            with self.assertRaises(RemoteServiceError):
                klass()

        imp_ref = rsa.ImportReferenceImpl()
        for method in (
            imp_ref.get_import_container_id,
            imp_ref.get_import_container_ns,
            imp_ref.get_export_container_id,
            imp_ref.get_remoteservice_id,
            imp_ref.get_description,
        ):
            with self.assertRaises(RemoteServiceError):
                method()

        self.assertFalse(imp_ref.match_ed(make_remote_ed()))
        self.assertIsNone(imp_ref.get_reference())
        self.assertIsNone(imp_ref.update(make_remote_ed()))
        self.assertFalse(imp_ref.close(cast(Any, None)))

    def test_closed_export_endpoint(self) -> None:
        """
        A closed export endpoint refuses to be used
        """
        svc_ref = self.register_exported()
        endpoint = rsa._ExportEndpoint(
            self.rsa,
            cast(Any, self.exporter),
            EndpointDescription(svc_ref, make_remote_ed().get_properties()),
            svc_ref,
        )
        reg = rsa.ExportRegistrationImpl(self.rsa, endpoint)
        self.rsa._add_exported_service(reg)
        self.assertIs(svc_ref, endpoint._originalprops() and endpoint.get_reference())

        # Only our own registrations can close the endpoint
        self.assertFalse(endpoint.close(cast(Any, object())))

        self.assertTrue(endpoint.close(reg))
        self.assertFalse(endpoint.close(reg))
        for method in (
            endpoint._rsa,
            endpoint.get_description,
            endpoint.get_reference,
            endpoint.get_export_container_id,
            endpoint.get_export_container_ns,
            endpoint.get_remoteservice_id,
        ):
            with self.assertRaises(ValueError):
                method()

        with self.assertRaises(ValueError):
            endpoint.update({})

    def test_closed_import_endpoint(self) -> None:
        """
        A closed import endpoint can't be updated nor matched anymore
        """
        ed = make_remote_ed()
        svc_reg = self.context.register_service(SPEC, object(), {})
        endpoint = rsa._ImportEndpoint(self.rsa, cast(Any, self.importer), ed, svc_reg)

        # No registration yet: nothing to match
        self.assertFalse(endpoint.match_ed(ed))

        reg = rsa.ImportRegistrationImpl(endpoint)
        self.rsa._add_imported_service(reg)
        self.assertTrue(endpoint.match_ed(ed))
        self.assertIs(endpoint, cast(Any, reg)._import_endpoint())

        # Only our own registrations can close the endpoint
        self.assertFalse(endpoint.close(cast(Any, object())))

        # The service is already gone: the endpoint must still be closed
        svc_reg.unregister()
        self.assertTrue(endpoint.close(reg))
        self.assertEqual([ed], self.importer.unimported)
        self.assertIsNone(endpoint.update(ed))
        with self.assertRaises(RemoteServiceError):
            endpoint.get_import_container_id()
        with self.assertRaises(RemoteServiceError):
            endpoint.get_import_container_ns()

    def test_default_export_selector(self) -> None:
        """
        The default export container selector asks all the providers,
        with the intents from all the intent properties
        """
        provider_1 = FakeExportProvider("config.1", "container.1")
        provider_2 = FakeExportProvider("config.2", "container.2")
        selector = rsa.ExportContainerSelectorImpl()
        selector._export_distribution_providers = cast(Any, [provider_1, provider_2])

        props = {
            SERVICE_EXPORTED_CONFIGS: "config.2",
            SERVICE_INTENTS: ["intent.1"],
            SERVICE_EXPORTED_INTENTS: ("intent.2", "intent.1"),
            SERVICE_EXPORTED_INTENTS_EXTRA: ["intent.3"],
        }
        svc_ref = self.register_exported()
        self.assertEqual(["container.2"], selector.select_export_containers(svc_ref, [SPEC], props))

        for provider in (provider_1, provider_2):
            configs, intents, _ = provider.calls[0]
            self.assertEqual(["config.2"], configs)
            self.assertEqual({"intent.1", "intent.2", "intent.3"}, set(intents))

        props[SERVICE_EXPORTED_CONFIGS] = "unknown"
        self.assertEqual([], selector.select_export_containers(svc_ref, [SPEC], props))

    def test_default_export_selector_string_intents(self) -> None:
        """
        Intent properties are "String+" properties: a single intent can be
        given as a plain string, which is not split in characters
        """
        provider = FakeExportProvider("config", "container")
        selector = rsa.ExportContainerSelectorImpl()
        selector._export_distribution_providers = cast(Any, [provider])

        props = {SERVICE_EXPORTED_CONFIGS: "config", SERVICE_INTENTS: "osgi.basic"}
        selector.select_export_containers(self.register_exported(), [SPEC], props)
        self.assertEqual(["osgi.basic"], provider.calls[0][1])

    def test_default_import_selector(self) -> None:
        """
        The default import container selector returns the first matching
        container
        """
        selector = rsa.ImportContainerSelectorImpl()
        selector._import_distribution_providers = cast(
            Any,
            [
                FakeImportProvider("other.config", "container.0"),
                FakeImportProvider(FAKE_CONFIG, "container.1"),
                FakeImportProvider(FAKE_CONFIG, "container.2"),
            ],
        )
        ed = make_remote_ed()
        self.assertEqual("container.1", selector.select_import_container([FAKE_CONFIG], ed))
        self.assertIsNone(selector.select_import_container(["unknown"], ed))


# ------------------------------------------------------------------------------


class DebugListenerTest(RSATestBase):
    """
    Tests the debug RSA event listener
    """

    def setUp(self) -> None:
        super().setUp()
        self.output = io.StringIO()
        self.export_selector.containers = [self.exporter]
        self.import_selector.container = self.importer

    def test_export_events(self) -> None:
        """
        Export events are printed with their endpoint description
        """
        listener = rsa.DebugRemoteServiceAdminListener(self.output)
        reg = self.rsa.export_service(self.register_exported())[0]
        reg.update({})
        reg.close()
        for event in self.collector.events:
            listener.remote_admin_event(event)

        output = self.output.getvalue()
        for name in ("EXPORT_REGISTRATION", "EXPORT_UPDATE", "EXPORT_UNREGISTRATION"):
            self.assertIn(f";{name};", output)
        self.assertIn(f"local=('{FAKE_NAMESPACE}', 'fake-exporter')", output)
        self.assertIn("---Endpoint Description---", output)
        self.assertNotIn("---Exception Stack---", output)

    def test_error_events(self) -> None:
        """
        Error events are printed with their stack trace
        """
        listener = rsa.DebugRemoteServiceAdminListener(self.output, write_endpoint=False)
        self.importer.import_error = KeyError("import failure")
        self.rsa.import_service(make_remote_ed())
        listener.remote_admin_event(self.collector.events[0])

        output = self.output.getvalue()
        self.assertIn(";IMPORT_ERROR;", output)
        self.assertIn("---Exception Stack---", output)
        self.assertIn("import failure", output)
        self.assertNotIn("---Endpoint Description---", output)

    def test_import_events(self) -> None:
        """
        Import events contain the imported service reference
        """
        listener = rsa.DebugRemoteServiceAdminListener(self.output, write_endpoint=False)
        reg = self.rsa.import_service(make_remote_ed())
        listener.remote_admin_event(self.collector.events[0])

        output = self.output.getvalue()
        self.assertIn(";IMPORT_REGISTRATION;", output)
        self.assertIn(str(reg.get_reference()), output)
        self.assertIn(";remote=remote-container:42", output)

    def test_raw_output(self) -> None:
        """
        Unknown event types and remote service IDs are written as is
        """
        listener = rsa.DebugRemoteServiceAdminListener(self.output)
        listener.write_type(-1)
        listener.write_ref(None, ("ns", "cid"), cast(Any, "raw-rsid"), None)
        self.assertIn(";UNKNOWN;local=('ns', 'cid');remote=raw-rsid\n", self.output.getvalue())

        try:
            raise ValueError("raw exception")
        except ValueError:
            listener.write_exception(cast(Any, sys.exc_info()))
        self.assertIn("ValueError: raw exception", self.output.getvalue())


class ActivatorTest(unittest.TestCase):
    """
    Tests the RSA bundle activator
    """

    def test_debug_listener_lifecycle(self) -> None:
        """
        The debug listener is registered only when asked, and removed when
        the bundle stops
        """
        for debug, expected in (("true", True), ("false", False), (None, False)):
            properties = {} if debug is None else {rsa.DEBUG_PROPERTY: debug}
            framework = pelix.framework.create_framework(["pelix.ipopo.core"], properties)
            try:
                framework.start()
                context = framework.get_bundle_context()
                bundle = context.install_bundle("pelix.rsa.remoteserviceadmin")
                bundle.start()
                listener_ref = context.get_service_reference(rsa.RemoteServiceAdminListener)
                self.assertEqual(expected, listener_ref is not None, debug)
                if listener_ref is not None:
                    # The framework loads its own copy of the module
                    self.assertIsInstance(
                        context.get_service(listener_ref), bundle.get_module().DebugRemoteServiceAdminListener
                    )

                bundle.stop()
                self.assertIsNone(context.get_service_reference(rsa.RemoteServiceAdminListener))
            finally:
                framework.delete(True)
                pelix.framework.FrameworkFactory.delete_framework()


if __name__ == "__main__":
    unittest.main()
