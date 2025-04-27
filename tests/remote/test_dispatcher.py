#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Remote Services Exports Dispatcher

:author: Thomas Calmant
"""

import unittest
import uuid
from typing import Any, Dict, List, Optional

import pelix.constants
import pelix.framework
import pelix.remote
import pelix.remote.beans as beans
from pelix.internals.registry import ServiceReference

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

ADDED = 1
UPDATED = 2
REMOVED = 3

# ------------------------------------------------------------------------------


class Exporter:
    """
    Service exporter
    """

    def __init__(
        self,
        context: pelix.framework.BundleContext,
        name: Optional[str] = None,
        configs: Optional[List[str]] = None,
    ) -> None:
        """
        Sets up members
        """
        self.context = context
        self.events: List[int] = []
        self.raise_exception = False

        self.endpoint: Optional[beans.ExportEndpoint] = None
        self.name = name or "test.endpoint"
        self.configs = configs[:] if configs else ["test.config"]

    def clear(self) -> None:
        """
        Clears the listener state
        """
        del self.events[:]

    def export_service(self, svc_ref: ServiceReference[Any], name: str, fw_uid: str) -> beans.ExportEndpoint:
        """
        Endpoint registered
        """
        self.events.append(ADDED)
        service = self.context.get_service(svc_ref)
        self.endpoint = beans.ExportEndpoint(
            str(uuid.uuid4()), fw_uid, self.configs, self.name, svc_ref, service, {}
        )
        return self.endpoint

    def update_export(
        self, endpoint: beans.ExportEndpoint, new_name: str, old_properties: Dict[str, Any]
    ) -> None:
        """
        Endpoint updated
        """
        self.events.append(UPDATED)
        if self.raise_exception:
            raise NameError("Update exception: new name refused")

    def unexport_service(self, endpoint: beans.ExportEndpoint) -> None:
        """
        Endpoint removed
        """
        self.events.append(REMOVED)


class Listener:
    """
    Export endpoints listener
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.events: List[int] = []
        self.raise_exception = False

    def clear(self) -> None:
        """
        Clears the listener state
        """
        del self.events[:]

    def endpoints_added(self, endpoints: List[beans.ExportEndpoint]) -> None:
        """
        Endpoints registered
        """
        if endpoints:
            self.events.append(ADDED)

        if self.raise_exception:
            raise Exception("Endpoints added exception")

    def endpoint_updated(self, endpoint: beans.ExportEndpoint, old_props: Dict[str, Any]) -> None:
        """
        Endpoint updated
        """
        self.events.append(UPDATED)
        if self.raise_exception:
            raise Exception("Endpoints updated exception")

    def endpoint_removed(self, endpoint: beans.ExportEndpoint) -> None:
        """
        Endpoint removed
        """
        self.events.append(REMOVED)
        if self.raise_exception:
            raise Exception("Endpoints removed exception")


# ------------------------------------------------------------------------------


class DispatcherTest(unittest.TestCase):
    """
    Tests for the Remote Services dispatcher
    """

    framework: pelix.framework.Framework
    service: pelix.remote.RemoteServiceDispatcher

    def setUp(self) -> None:
        """
        Sets up the test
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(["pelix.ipopo.core"])
        self.framework.start()

        # Install the registry
        context = self.framework.get_bundle_context()
        context.install_bundle("pelix.remote.dispatcher").start()

        # Get the framework UID
        self.framework_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Get the service
        svc_ref = context.get_service_reference(pelix.remote.RemoteServiceDispatcher)
        assert svc_ref is not None
        self.service = context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework()

        self.framework = None  # type: ignore
        self.service = None  # type: ignore

    def testEmpty(self) -> None:
        """
        Tests the behavior of the dispatcher without listener
        """
        # Register an exported service
        context = self.framework.get_bundle_context()
        service = object()
        svc_reg = context.register_service(
            "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # Look for the endpoint
        self.assertEqual(self.service.get_endpoints(), [], "An endpoint has been created")

        # Unregister the service
        svc_reg.unregister()

    def testExporterAfterRegistration(self) -> None:
        """
        Tests the behavior of the dispatcher with a exporter
        """
        # Register an exported service
        context = self.framework.get_bundle_context()
        service = object()

        for raise_exception in (False, True):
            # Register the exported service
            svc_reg = context.register_service(
                "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
            )

            # Prepare a exporter
            exporter = Exporter(context)
            exporter.raise_exception = raise_exception

            # Register it
            exporter_reg = context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

            # Check the state of the exporter
            self.assertListEqual(exporter.events, [ADDED], "Exporter not notified")
            exporter.clear()

            # Look for the endpoint
            endpoints = self.service.get_endpoints()
            self.assertEqual(len(endpoints), 1, "The endpoint has not been created")
            endpoint = endpoints[0]
            self.assertIs(endpoint.instance, service)

            # Check access
            self.assertIs(
                self.service.get_endpoint(endpoint.uid), endpoint, "Different endpoint on UID access"
            )

            # Update the service
            svc_reg.set_properties({"some": "property"})
            if raise_exception:
                # The new properties have been refused
                self.assertListEqual(
                    exporter.events, [UPDATED, REMOVED], "Exporter not notified of name removal"
                )

            else:
                # Check the state of the exporter
                self.assertListEqual(exporter.events, [UPDATED], "Exporter not notified of update")
            exporter.clear()

            # Unregister the exported service
            svc_reg.unregister()

            if raise_exception:
                # Exception raised: the exporter has not been notified
                self.assertListEqual(exporter.events, [], "Exporter notified of ignored removal")

            else:
                # Check the state of the exporter
                self.assertListEqual(exporter.events, [REMOVED], "Exporter not notified of removal")
            exporter.clear()

            # Ensure there is no more endpoint
            self.assertEqual(self.service.get_endpoints(), [], "Endpoint still there")
            self.assertIsNone(self.service.get_endpoint(endpoint.uid), "Endpoint still there")

            # Unregister the service
            exporter_reg.unregister()

    def testExporterBeforeRegistration(self) -> None:
        """
        Tests the behavior of the dispatcher with a exporter
        """
        # Register an exported service
        context = self.framework.get_bundle_context()
        service = object()

        for raise_exception in (False, True):
            # Prepare a exporter
            exporter = Exporter(context)
            exporter.raise_exception = raise_exception

            # Register it
            exporter_reg = context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

            # Register the exported service
            svc_reg = context.register_service(
                "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
            )

            # Check the state of the exporter
            self.assertListEqual(exporter.events, [ADDED], "Exporter not notified")
            exporter.clear()

            # Look for the endpoint
            endpoints = self.service.get_endpoints()
            self.assertEqual(len(endpoints), 1, "The endpoint has not been created")
            endpoint = endpoints[0]
            self.assertIs(endpoint.instance, service)

            # Check access
            self.assertIs(
                self.service.get_endpoint(endpoint.uid), endpoint, "Different endpoint on UID access"
            )

            # Update the service
            svc_reg.set_properties({"some": "property"})
            if raise_exception:
                # The new properties have been refused
                self.assertListEqual(
                    exporter.events, [UPDATED, REMOVED], "Exporter not notified of name removal"
                )

            else:
                # Check the state of the exporter
                self.assertListEqual(exporter.events, [UPDATED], "Exporter not notified of update")
            exporter.clear()

            # Unregister the exported service
            svc_reg.unregister()

            if raise_exception:
                # Exception raised: the exporter has not been notified
                self.assertListEqual(exporter.events, [], "Exporter notified of ignored removal")

            else:
                # Check the state of the exporter
                self.assertListEqual(exporter.events, [REMOVED], "Exporter not notified of removal")
            exporter.clear()

            # Ensure there is no more endpoint
            self.assertEqual(self.service.get_endpoints(), [], "Endpoint still there")
            self.assertIsNone(self.service.get_endpoint(endpoint.uid), "Endpoint still there")

            # Unregister the service
            exporter_reg.unregister()

    def testListenerBefore(self) -> None:
        """
        Tests the notification of endpoint listeners
        """
        # Register an exported service
        context = self.framework.get_bundle_context()
        service = object()

        for name_error in (True, False):
            for raise_exception in (False, True):
                # Prepare a listener
                listener = Listener()
                listener.raise_exception = raise_exception
                listener_reg = context.register_service(
                    pelix.remote.SERVICE_EXPORT_ENDPOINT_LISTENER, listener, {}
                )

                # Register the exported service
                svc_reg = context.register_service(
                    "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
                )

                # Check the state of the listener
                self.assertListEqual(listener.events, [], "Listener notified too soon")
                listener.clear()

                # Prepare a exporter
                exporter = Exporter(context)
                exporter.raise_exception = name_error
                exporter_reg = context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

                # Check the state of the listener
                self.assertListEqual(listener.events, [ADDED], "Listener not notified")
                listener.clear()

                # Update the service
                svc_reg.set_properties({"some": "property"})
                if name_error:
                    # The new properties have been refused
                    self.assertListEqual(listener.events, [REMOVED], "Listener not notified of name removal")

                else:
                    # Check the state of the exporter
                    self.assertListEqual(listener.events, [UPDATED], "Listener not notified of update")
                listener.clear()

                # Unregister the exported service
                svc_reg.unregister()

                if name_error:
                    # Exception raised: the listener has not been notified
                    self.assertListEqual(listener.events, [], "Listener notified of ignored removal")

                else:
                    # Check the state of the listener
                    self.assertListEqual(listener.events, [REMOVED], "Listener not notified of removal")
                listener.clear()

                # Unregister the services
                exporter_reg.unregister()
                listener_reg.unregister()

    def testListenerAfter(self) -> None:
        """
        Tests the notification of endpoint listeners
        """
        # Prepare an exported service
        context = self.framework.get_bundle_context()
        service = object()

        for raise_exception in (False, True):
            # Prepare a exporter
            exporter = Exporter(context)
            exporter_reg = context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

            # Register the exported service
            svc_reg = context.register_service(
                "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
            )

            # Prepare a listener
            listener = Listener()
            listener.raise_exception = raise_exception
            listener_reg = context.register_service(
                pelix.remote.SERVICE_EXPORT_ENDPOINT_LISTENER, listener, {}
            )

            # Check the state of the listener
            self.assertListEqual(listener.events, [ADDED], "Listener not notified")
            listener.clear()

            # Unregister the exporter
            exporter_reg.unregister()

            # Check the state of the listener
            self.assertListEqual(listener.events, [REMOVED], "Listener not notified of removal")
            listener.clear()

            # Unregister the exported service
            svc_reg.unregister()

            # Check the state of the listener
            self.assertListEqual(listener.events, [], "Listener notified of removal")
            listener.clear()

            # Unregister the services
            listener_reg.unregister()

    def testGetEndpoints(self) -> None:
        """
        Tests the behavior of the get_endpoints() method
        """
        context = self.framework.get_bundle_context()

        # Register exporters
        exporterA = Exporter(context, "nameA", ["configA"])
        exporterA_reg = context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporterA, {})

        exporterB = Exporter(context, "nameB", ["configB"])
        exporterB_reg = context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporterB, {})

        # Register the remote service
        service = object()
        svc_reg = context.register_service(
            "sample.spec", service, {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # Get all endpoints
        self.assertCountEqual(
            [exporterA.endpoint, exporterB.endpoint],
            self.service.get_endpoints(),
            "Invalid result for get_endpoints()",
        )

        # Get endpoint by name
        self.assertListEqual(
            [exporterA.endpoint],
            self.service.get_endpoints(name="nameA"),
            "Invalid result for get_endpoints(name)",
        )
        self.assertListEqual(
            [exporterB.endpoint],
            self.service.get_endpoints(name="nameB"),
            "Invalid result for get_endpoints(name)",
        )

        # Get endpoint by configuration
        self.assertListEqual(
            [exporterA.endpoint],
            self.service.get_endpoints(kind="configA"),
            "Invalid result for get_endpoints(kind)",
        )
        self.assertListEqual(
            [exporterB.endpoint],
            self.service.get_endpoints(kind="configB"),
            "Invalid result for get_endpoints(kind)",
        )

        # Filter with both
        self.assertListEqual(
            [exporterA.endpoint],
            self.service.get_endpoints("configA", "nameA"),
            "Invalid result for get_endpoints(kind, name)",
        )

        # Filter with no result
        self.assertListEqual(
            [], self.service.get_endpoints("configB", "nameA"), "Invalid result for get_endpoints(kind, name)"
        )

        # Unregister exporter B
        exporterB_reg.unregister()

        # Get all endpoints
        self.assertListEqual(
            [exporterA.endpoint], self.service.get_endpoints(), "Endpoint of B still in get_endpoints()"
        )

        # Unregister service
        svc_reg.unregister()

        # Get all endpoints
        self.assertListEqual([], self.service.get_endpoints(), "Endpoint of A still in get_endpoints()")

        # Unregister exporter A
        exporterA_reg.unregister()

    def testExportReject(self) -> None:
        """
        Tests the "pelix.remote.export.reject" property
        """
        spec_1 = "sample.spec.1"
        full_spec_1 = "python:/" + spec_1
        spec_2 = "sample.spec.2"
        full_spec_2 = "python:/" + spec_2
        spec_3 = "sample.spec.3"
        full_spec_3 = "python:/" + spec_3

        # Register an exporter
        context = self.framework.get_bundle_context()
        exporter = Exporter(context)
        context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

        # Register an exported service: No filter
        service = object()
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3],
            service,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_EXPORT_REJECT: None},
        )

        # Look for the endpoint: all services must be exported
        endpoint = self.service.get_endpoints()[0]
        self.assertCountEqual([full_spec_1, full_spec_2, full_spec_3], endpoint.specifications)
        svc_reg.unregister()

        # Check with a string
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3],
            service,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_EXPORT_REJECT: spec_1},
        )

        # Look for the endpoint: all services must be exported
        endpoint = self.service.get_endpoints()[0]
        self.assertCountEqual([full_spec_2, full_spec_3], endpoint.specifications)
        svc_reg.unregister()

        for reject in ([spec_1], [spec_1, spec_2]):
            # Register the service
            svc_reg = context.register_service(
                [spec_1, spec_2, spec_3],
                service,
                {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_EXPORT_REJECT: reject},
            )

            # Compute exported interfaces
            exported = ["python:/" + spec for spec in {spec_1, spec_2, spec_3}.difference(reject)]

            # Check it
            endpoint = self.service.get_endpoints()[0]
            self.assertCountEqual(exported, endpoint.specifications)

            # Unregister the service
            svc_reg.unregister()

        # Reject everything
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3],
            service,
            {
                pelix.remote.PROP_EXPORTED_INTERFACES: "*",
                pelix.remote.PROP_EXPORT_REJECT: [spec_1, spec_2, spec_3],
            },
        )
        self.assertListEqual([], self.service.get_endpoints(), "Endpoint registered while it exports nothing")
        svc_reg.unregister()

    def testExportOnly(self) -> None:
        """
        Tests the "pelix.remote.export.only" property
        """
        spec_1 = "sample.spec.1"
        full_spec_1 = "python:/" + spec_1
        spec_2 = "sample.spec.2"
        full_spec_2 = "python:/" + spec_2
        spec_3 = "sample.spec.3"
        full_spec_3 = "python:/" + spec_3

        # Register an exporter
        context = self.framework.get_bundle_context()
        exporter = Exporter(context)
        context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

        # Register an exported service: No filter
        service = object()
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3],
            service,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_EXPORT_ONLY: None},
        )

        # Look for the endpoint: all services must be exported
        endpoint = self.service.get_endpoints()[0]
        self.assertCountEqual([full_spec_1, full_spec_2, full_spec_3], endpoint.specifications)
        svc_reg.unregister()

        # Check with a string
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3],
            service,
            {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_EXPORT_ONLY: spec_1},
        )

        # Look for the endpoint: all services must be exported
        endpoint = self.service.get_endpoints()[0]
        self.assertCountEqual([full_spec_1], endpoint.specifications)
        svc_reg.unregister()

        for export_only in ([spec_1], [spec_1, spec_2]):
            # Register the service
            svc_reg = context.register_service(
                [spec_1, spec_2, spec_3],
                service,
                {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_EXPORT_ONLY: export_only},
            )

            # Check it
            exported = ["python:/" + spec for spec in export_only]
            endpoint = self.service.get_endpoints()[0]
            self.assertCountEqual(exported, endpoint.specifications)

            # Unregister the service
            svc_reg.unregister()

        # The reject property must be ignored
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3],
            service,
            {
                pelix.remote.PROP_EXPORTED_INTERFACES: "*",
                pelix.remote.PROP_EXPORT_ONLY: [spec_1, spec_2, spec_3],
                pelix.remote.PROP_EXPORT_REJECT: [spec_1, spec_2],
            },
        )
        endpoint = self.service.get_endpoints()[0]
        self.assertCountEqual(
            [full_spec_1, full_spec_2, full_spec_3],
            endpoint.specifications,
            "Some specifications were rejected",
        )
        svc_reg.unregister()

    def testExportNone(self) -> None:
        """
        Tests the "pelix.remote.export.reject" property
        """
        spec_1 = "sample.spec.1"
        full_spec_1 = "python:/" + spec_1
        spec_2 = "sample.spec.2"
        full_spec_2 = "python:/" + spec_2
        spec_3 = "sample.spec.3"
        full_spec_3 = "python:/" + spec_3

        # Register an exporter
        context = self.framework.get_bundle_context()
        exporter = Exporter(context)
        context.register_service(pelix.remote.SERVICE_EXPORT_PROVIDER, exporter, {})

        # Prepare the service
        service = object()

        # Check with false values
        for value in ("", 0, False, None):
            svc_reg = context.register_service(
                [spec_1, spec_2, spec_3],
                service,
                {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_EXPORT_NONE: value},
            )

            # Look for the endpoint: all services must be exported
            endpoint = self.service.get_endpoints()[0]
            self.assertCountEqual([full_spec_1, full_spec_2, full_spec_3], endpoint.specifications)
            svc_reg.unregister()

        # Check with true values
        for value in ("*", "true", "false", 1, True):
            svc_reg = context.register_service(
                [spec_1, spec_2, spec_3],
                service,
                {pelix.remote.PROP_EXPORTED_INTERFACES: "*", pelix.remote.PROP_EXPORT_NONE: value},
            )

            # Look for the endpoint: all services must be exported
            self.assertListEqual(
                [], self.service.get_endpoints(), "Service exported even with export.none={0}".format(value)
            )
            svc_reg.unregister()

        # Check with reject
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3],
            service,
            {
                pelix.remote.PROP_EXPORTED_INTERFACES: "*",
                pelix.remote.PROP_EXPORT_NONE: True,
                pelix.remote.PROP_EXPORT_REJECT: [spec_3],
            },
        )
        self.assertListEqual(
            [], self.service.get_endpoints(), "export.reject worked while export.none was set"
        )
        svc_reg.unregister()

        # Check with only
        svc_reg = context.register_service(
            [spec_1, spec_2, spec_3],
            service,
            {
                pelix.remote.PROP_EXPORTED_INTERFACES: "*",
                pelix.remote.PROP_EXPORT_NONE: True,
                pelix.remote.PROP_EXPORT_ONLY: [spec_1, spec_2, spec_3],
            },
        )
        self.assertListEqual([], self.service.get_endpoints(), "export.only worked while export.none was set")
        svc_reg.unregister()


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
