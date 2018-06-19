#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the RSA basic methods

:author: Thomas Calmant
"""

# Standard library
import tempfile
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# Pelix
from pelix.ipopo.constants import use_ipopo
import pelix.constants
import pelix.framework

# Remote Services
from pelix.rsa.edef import EDEFReader, EDEFWriter
import pelix.rsa.remoteserviceadmin as rsa

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class RSABundleTests(unittest.TestCase):
    """
    Tests the RSA bundle behaviour
    """

    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(["pelix.ipopo.core"])
        self.framework.start()

    def tearDown(self):
        """
        Stops the framework
        """
        self.framework.delete(True)

    def test_start(self):
        """
        Simple check of the services/instances started with the bundle
        """
        context = self.framework.get_bundle_context()

        # Disable debug mode
        self.framework.add_property(rsa.DEBUG_PROPERTY, "false")

        # Start RSA bundle
        context.install_bundle("pelix.rsa.remoteserviceadmin").start()

        # Check services
        # No debug service (disabled)
        self.assertIsNone(
            context.get_service_reference(rsa.SERVICE_RSA_EVENT_LISTENER)
        )

        # Check all services that should be started with the bundle
        for spec in (
            rsa.SERVICE_EXPORT_CONTAINER_SELECTOR,
            rsa.SERVICE_IMPORT_CONTAINER_SELECTOR,
            rsa.SERVICE_REMOTE_SERVICE_ADMIN,
        ):
            self.assertIsNotNone(context.get_service_reference(spec))

    def test_start_debug(self):
        """
        Simple check of the services/instances started with the bundle
        """
        context = self.framework.get_bundle_context()

        # Disable debug mode
        self.framework.add_property(rsa.DEBUG_PROPERTY, "true")

        # Start RSA bundle
        context.install_bundle("pelix.rsa.remoteserviceadmin").start()

        # Check all services that should be started with the bundle
        # Debug service must be active
        for spec in (
            rsa.SERVICE_EXPORT_CONTAINER_SELECTOR,
            rsa.SERVICE_IMPORT_CONTAINER_SELECTOR,
            rsa.SERVICE_REMOTE_SERVICE_ADMIN,
            rsa.SERVICE_RSA_EVENT_LISTENER,
        ):
            self.assertIsNotNone(context.get_service_reference(spec))

# ------------------------------------------------------------------------------


class RSABasicFeatures(unittest.TestCase):
    """
    Tests RSA basic features
    """

    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ["pelix.ipopo.core", "pelix.rsa.remoteserviceadmin"])
        self.framework.start()

        # Get the RSA service
        context = self.framework.get_bundle_context()
        self.rsa = context.get_service(
            context.get_service_reference(
                rsa.SERVICE_REMOTE_SERVICE_ADMIN))  # type: rsa.RemoteServiceAdminImpl

    def tearDown(self):
        """
        Stops the framework
        """
        self.framework.delete(True)

    def test_export_import(self):
        """
        Tests an export of a service (with XML-RPC)
        """
        context = self.framework.get_bundle_context()

        # Start an HTTP server, required by XML-RPC
        context.install_bundle("pelix.http.basic").start()
        with use_ipopo(context) as ipopo:
            ipopo.instantiate(
                'pelix.http.service.basic.factory',
                'http-server',
                {'pelix.http.address': 'localhost',
                 'pelix.http.port': 0})

        # Install the XML-RPC provider to have an endpoint
        # Indicate the XML-RPC server
        self.framework.add_property("ecf.xmlrpc.server.hostname", "localhost")
        context.install_bundle(
            "pelix.rsa.providers.distribution.xmlrpc").start()

        # Register a service to be exported
        spec = "test.svc"
        svc = object()
        svc_reg = context.register_service(spec, svc, {})
        svc_ref = svc_reg.get_reference()

        # Export the service
        export_regs = self.rsa.export_service(
            svc_ref, {rsa.SERVICE_EXPORTED_INTERFACES: '*',
                      rsa.SERVICE_EXPORTED_CONFIGS: "ecf.xmlrpc.server"})

        # Get the export endpoints
        export_endpoints = []
        for export_reg in export_regs:
            exp = export_reg.get_exception()
            if exp:
                self.fail("Error exporting service: {}".format(exp))

            export_endpoints.append(export_reg.get_description())

        if not export_endpoints:
            self.fail("No exported endpoints")

        # Temporary file
        tmp_file = tempfile.mktemp()

        # Write the EDEF XML file
        EDEFWriter().write(export_endpoints, tmp_file)

        # Reload it
        with open(tmp_file, "r") as fd:
            parsed_endpoints = EDEFReader().parse(fd.read())

        for parsed_endpoint in parsed_endpoints:
            import_reg = self.rsa.import_service(parsed_endpoint)
            if import_reg:
                exp = import_reg.get_exception()
                endpoint_desc = import_reg.get_description()

                if exp:
                    self.fail("Error importing service: {}".format(exp))
                else:
                    break
        else:
            self.fail("No imported service")
