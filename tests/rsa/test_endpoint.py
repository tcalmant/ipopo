#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Tests the RSA endpoint description

:author: Thomas Calmant
"""

# Standard library
import unittest
import pytest
pytest.skip("Endpoint not implemented yet", allow_module_level=True)
from typing import List


# Pelix
from pelix.framework import FRAMEWORK_UID, OSGI_FRAMEWORK_UUID
from pelix.ipopo.constants import use_ipopo
import pelix.constants
import pelix.framework

# Remote Services
import pelix.rsa.endpointdescription as rsa_ed
import pelix.rsa.remoteserviceadmin as rsa

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class EndpointDescriptionTests(unittest.TestCase):
    """
    Tests the RSA EndpointDescription module/class
    """

    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ["pelix.ipopo.core", "pelix.http.basic",
             "pelix.rsa.remoteserviceadmin",
             "pelix.rsa.providers.distribution.xmlrpc"],
            {"ecf.xmlrpc.server.hostname": "localhost"})
        self.framework.start()

        # Get the RSA service
        context = self.framework.get_bundle_context()
        self.rsa = context.get_service(
            context.get_service_reference(
                rsa.SERVICE_REMOTE_SERVICE_ADMIN))  # type: rsa.RemoteServiceAdminImpl

        # Start an HTTP server, required by XML-RPC
        with use_ipopo(context) as ipopo:
            ipopo.instantiate(
                'pelix.http.service.basic.factory',
                'http-server',
                {'pelix.http.address': 'localhost',
                 'pelix.http.port': 0})

    def tearDown(self):
        """
        Stops the framework
        """
        self.framework.delete(True)

    def test_encode_list(self):
        """
        Tests encode_list()
        """
        # Encode
        for empty in (None, [], {}, ()):
            self.assertEqual({}, rsa_ed.encode_list("toto", empty))

        list_ = [1, 2, 3, 4]
        res = rsa_ed.encode_list("toto", list_)
        self.assertIn("toto", res)
        self.assertEqual(" ".join(str(i) for i in list_), res["toto"])

        # Decode
        res_2 = rsa_ed.decode_list(res, "toto")
        for l, r in zip(list_, res_2):
            self.assertEqual(r, str(l))

    def test_package_name(self):
        """
        Tests package_name()
        """
        for empty in (None, ""):
            self.assertEqual("", rsa_ed.package_name(empty))

        self.assertEqual("simple", rsa_ed.package_name("simple"))
        self.assertEqual("package", rsa_ed.package_name("package.simple"))
        self.assertEqual("", rsa_ed.package_name(".simple"))
        self.assertEqual(
            "root.package", rsa_ed.package_name("root.package.simple"))

    def test_encode_osgi_props(self):
        """
        Tests encode_osgi_props()
        """
        # Prepare a service for export
        context = self.framework.get_bundle_context()
        specs = ["foo", "bar"]
        svc_reg = context.register_service(specs, object(), {})
        svc_ref = svc_reg.get_reference()

        # Export the service
        export_reg = self.rsa.export_service(
            svc_ref, {rsa.SERVICE_EXPORTED_INTERFACES: '*',
                      rsa.SERVICE_EXPORTED_CONFIGS: "ecf.xmlrpc.server"})[0]
        ed = export_reg.get_description()

        # Encode properties
        res = rsa_ed.encode_osgi_props(ed)

        # Ensure everything is a string
        for key, value in res.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, str)

        # Decode
        res_2 = rsa_ed.decode_osgi_props(res)

        ed_props = ed.get_properties()
        for key in res:
            # Ensure we have list & strings
            ed_prop = ed_props[key]
            if not isinstance(ed_prop, (str, list, type(None))):
                ed_prop = str(ed_prop)

            self.assertEqual(ed_prop, res_2[key])

    def test_encode_endpoint_props(self):
        """
        Tests encode_endpoint_props()
        """
        # Prepare a service for export
        context = self.framework.get_bundle_context()
        specs = ["foo", "bar"]
        svc_reg = context.register_service(specs, object(), {})
        svc_ref = svc_reg.get_reference()

        # Export the service
        export_reg = self.rsa.export_service(
            svc_ref, {rsa.SERVICE_EXPORTED_INTERFACES: '*',
                      rsa.SERVICE_EXPORTED_CONFIGS: "ecf.xmlrpc.server"})[0]
        ed = export_reg.get_description()

        # Encode properties
        res = rsa_ed.encode_endpoint_props(ed)

        # Ensure everything is a string
        for key, value in res.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, str)

        # Decode
        res_2 = rsa_ed.decode_endpoint_props(res)

        ed_props = ed.get_properties()
        for key in res:
            # Ensure we have the same types
            ed_prop = ed_props[key]
            res_prop = res_2[key]
            if isinstance(res_prop, str):
                ed_prop = str(ed_prop)

            self.assertEqual(ed_prop, res_prop)

    def test_compare(self):
        """
        Tests endpoints comparisons
        """
        # Prepare a service for export
        context = self.framework.get_bundle_context()
        specs_1 = ["foo", "bar"]
        svc_reg_1 = context.register_service(specs_1, object(), {})
        svc_ref_1 = svc_reg_1.get_reference()

        specs_2 = ["foo", "baz"]
        svc_reg_2 = context.register_service(specs_2, object(), {})
        svc_ref_2 = svc_reg_2.get_reference()

        # Export the services
        export_reg_1 = self.rsa.export_service(
            svc_ref_1,
            {rsa.SERVICE_EXPORTED_INTERFACES: '*',
             rsa.SERVICE_EXPORTED_CONFIGS: "ecf.xmlrpc.server"})[0]
        ed_1 = export_reg_1.get_description()

        export_reg_2 = self.rsa.export_service(
            svc_ref_2,
            {rsa.SERVICE_EXPORTED_INTERFACES: '*',
             rsa.SERVICE_EXPORTED_CONFIGS: "ecf.xmlrpc.server"})[0]
        ed_2 = export_reg_2.get_description()

        # Just ensure that str() works
        fw_uid = self.framework.get_property(FRAMEWORK_UID)
        self.assertEqual(fw_uid, ed_1.get_framework_uuid())
        self.assertEqual(fw_uid, ed_2.get_framework_uuid())

        for ed in (ed_1, ed_2):
            ed_str = str(ed)
            self.assertIn(fw_uid, ed_str)
            self.assertIn(ed.get_id(), ed_str)

        self.assertNotEqual(ed_1.get_id(), ed_2.get_id())
        self.assertNotIn(ed_1.get_id(), str(ed_2))
        self.assertNotIn(ed_2.get_id(), str(ed_1))

        # Check comparison
        self.assertEqual(ed_1, ed_1)
        self.assertNotEqual(ed_1, ed_2)
        self.assertNotEqual(hash(ed_1), hash(ed_2))
