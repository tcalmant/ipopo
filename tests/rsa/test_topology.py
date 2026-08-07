#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the RSA basic topology manager

:author: Thomas Calmant
"""

import unittest
from typing import cast

import pelix.framework
import pelix.rsa.remoteserviceadmin as rsa
from pelix.ipopo.constants import use_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class TopologyManagerTest(unittest.TestCase):
    """
    Tests RSA basic topology manager
    """

    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            [
                "pelix.ipopo.core",
                "pelix.http.basic",
                "pelix.rsa.remoteserviceadmin",
                "pelix.rsa.providers.distribution.xmlrpc",
            ],
            {"ecf.xmlrpc.server.hostname": "localhost"},
        )
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)
        self.framework.start()

        # Get the RSA service
        context = self.framework.get_bundle_context()
        svc_ref = context.get_service_reference(rsa.RemoteServiceAdmin)
        assert svc_ref is not None
        self.rsa = cast(rsa.RemoteServiceAdminImpl, context.get_service(svc_ref))

        # Start an HTTP server, required by XML-RPC
        with use_ipopo(context) as ipopo:
            ipopo.instantiate(
                "pelix.http.service.basic.factory",
                "http-server",
                {"pelix.http.address": "localhost", "pelix.http.port": 0},
            )

    def tearDown(self):
        """
        Stops the framework
        """
        self.framework.delete(True)

    def test_auto_export(self):
        """
        Tests an export of a service (with XML-RPC)
        """
        # Install the topology manager
        context = self.framework.get_bundle_context()
        context.install_bundle("pelix.rsa.topologymanagers.basic").start()
        from pelix.rsa.topologymanagers.basic import instantiate_basic_topology_manager

        instantiate_basic_topology_manager(context)
        # Register a service to be exported
        spec = "test.svc"
        svc = object()
        svc_reg = context.register_service(
            spec,
            svc,
            {
                rsa.SERVICE_EXPORTED_INTERFACES: "*",
                rsa.SERVICE_EXPORTED_CONFIGS: "ecf.xmlrpc.server",
            },
        )
        svc_ref = svc_reg.get_reference()

        # Check if it has been exported
        for export_ref in self.rsa.get_exported_services():
            if export_ref.get_reference() is svc_ref:
                break
        else:
            self.fail("Service not automatically exported")

        # Update service
        key = "foo"
        val = "bar"
        svc_reg.set_properties({key: val})
        for export_ref in self.rsa.get_exported_services():
            if export_ref.get_reference() is svc_ref:
                svc_val = export_ref.get_description().get_properties()[key]  # type: ignore
                self.assertEqual(val, svc_val)
                break
        else:
            self.fail("No update of service properties")

        # Unregister the service
        svc_reg.unregister()

        # Check if it is still exported
        for export_ref in self.rsa.get_exported_services():
            if export_ref.get_reference() is svc_ref:
                self.fail("Service not automatically removed")

    def test_endpoint_changed(self):
        """
        Tests the handling of discovery endpoint events (import side)
        """
        from pelix.rsa.edef import EDEFReader, EDEFWriter
        from pelix.rsa.providers.discovery import EndpointEvent
        from pelix.rsa.topologymanagers.basic import instantiate_basic_topology_manager

        context = self.framework.get_bundle_context()
        context.install_bundle("pelix.rsa.topologymanagers.basic").start()
        topology_manager = instantiate_basic_topology_manager(context)

        # Export a service to get a valid endpoint description
        spec = "test.svc"
        svc_reg = context.register_service(spec, object(), {})
        export_regs = self.rsa.export_service(
            svc_reg.get_reference(),
            {rsa.SERVICE_EXPORTED_INTERFACES: "*", rsa.SERVICE_EXPORTED_CONFIGS: "ecf.xmlrpc.server"},
        )
        self.assertTrue(export_regs)
        self.assertIsNone(export_regs[0].get_exception())
        export_endpoint = export_regs[0].get_description()

        # Round-trip through EDEF, like a discovery provider would
        parsed_endpoint = EDEFReader().parse(EDEFWriter().to_string([export_endpoint]))[0]

        # ADDED event: the endpoint must be imported
        topology_manager.endpoint_changed(EndpointEvent(EndpointEvent.ADDED, parsed_endpoint), None)
        imported = [
            import_ref
            for import_ref in self.rsa.get_imported_endpoints()
            if import_ref.get_description().get_id() == parsed_endpoint.get_id()  # type: ignore
        ]
        self.assertTrue(imported, "Endpoint not imported on ADDED event")

        # MODIFIED event: the imported endpoint must be updated
        topology_manager.endpoint_changed(EndpointEvent(EndpointEvent.MODIFIED, parsed_endpoint), None)

        # REMOVED event: the imported endpoint must be closed
        topology_manager.endpoint_changed(EndpointEvent(EndpointEvent.REMOVED, parsed_endpoint), None)
        imported = [
            import_ref
            for import_ref in self.rsa.get_imported_endpoints()
            if import_ref.get_description().get_id() == parsed_endpoint.get_id()  # type: ignore
        ]
        self.assertFalse(imported, "Endpoint still imported after REMOVED event")

        # ADDED event with an endpoint no provider can import: the import
        # registration carries an exception and no service is imported
        from pelix.rsa import REMOTE_CONFIGS_SUPPORTED
        from pelix.rsa.endpointdescription import EndpointDescription

        bad_props = dict(parsed_endpoint.get_properties())
        bad_props[REMOTE_CONFIGS_SUPPORTED] = ["unknown.config"]
        bad_endpoint = EndpointDescription(properties=bad_props)

        with self.assertLogs("pelix.rsa.topologymanagers.basic", "ERROR") as log_ctx:
            topology_manager.endpoint_changed(EndpointEvent(EndpointEvent.ADDED, bad_endpoint), None)
        self.assertTrue(any("import failed" in line for line in log_ctx.output))
