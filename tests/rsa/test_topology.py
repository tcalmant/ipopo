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

__version_info__ = (3, 1, 0)
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
                svc_val = export_ref.get_description().get_properties()[key]
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
