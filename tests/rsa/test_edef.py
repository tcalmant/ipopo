#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the RSA EDEF I/O operations

:author: Thomas Calmant
"""

import unittest

import pelix.constants
import pelix.framework
import pelix.rsa
from pelix.rsa.edef import EDEFReader, EDEFWriter
from pelix.rsa.endpointdescription import EndpointDescription

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class EdefIOTest(unittest.TestCase):
    """
    Tests for the Remote Services EDEF I/O operations
    """

    def setUp(self) -> None:
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(["pelix.ipopo.core"])
        self.framework.start()

        # Register an exported service
        context = self.framework.get_bundle_context()
        svc_reg = context.register_service(
            "sample.spec",
            object(),
            {
                pelix.rsa.SERVICE_EXPORTED_INTENTS: "*",
                pelix.rsa.SERVICE_EXPORTED_CONFIGS: "*",
                "some.property": "some value",
            },
        )
        self.svc_ref = svc_reg.get_reference()

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework()

        self.framework = None  # type: ignore
        self.svc_ref = None  # type: ignore

    def testEdefStringReload(self) -> None:
        """
        Tries to convert an EndpointDescription to its XML format (EDEF) and to
        reload this string
        """
        original = EndpointDescription(
            self.svc_ref,
            {
                pelix.rsa.ENDPOINT_ID: "toto",
                pelix.rsa.ECF_ENDPOINT_ID: "toto",
                pelix.rsa.ECF_ENDPOINT_CONTAINERID_NAMESPACE: "test",
                pelix.rsa.ENDPOINT_FRAMEWORK_UUID: "other-fw",
                pelix.rsa.SERVICE_IMPORTED_CONFIGS: ["titi"],
                pelix.constants.OBJECTCLASS: "spec",
            },
        )

        # Write the endpoint to an XML string
        writer = EDEFWriter()
        xml_string = writer.to_string([original])

        # Parse the XML
        reader = EDEFReader()
        endpoints = reader.parse(xml_string)

        # Ensure we have a valid result
        self.assertEqual(len(endpoints), 1, "Parsed more than one endpoint")
        endpoint = endpoints[0]

        # Ensure equality
        self.assertIsNot(original, endpoint, "Same exact endpoint object returned")

        self.assertEqual(original, endpoint, "Parsed endpoint is different")
        self.assertEqual(endpoint, original, "Parsed endpoint is different")

        # Ensure properties equality
        self.assertDictEqual(
            original.get_properties(), endpoint.get_properties(), "Endpoint properties changed"
        )

    def testEdefIOTypes(self) -> None:
        """
        Tests the writing and parsing of an EndpointDescription bean with
        "complex" properties
        """
        properties = {  # Strings whitespaces are not well kept in XML
            "string": "some string just to see...",
            "int": 12,
            "float": 12.0,
            "tuple_str": ("a", "b", "c"),
            "tuple_int": (1, 2, 3),
            "tuple_float": (1.0, 2.0, 3.0),
            "list_str": ["a", "b", "c"],
            "list_int": [1, 2, 3],
            "list_float": [1.0, 2.0, 3.0],
            "set_str": {"a", "b", "c"},
            "set_int": {1, 2, 3},
            "set_float": {1.0, 2.0, 3.0},
        }

        all_props = properties.copy()
        all_props[pelix.rsa.ENDPOINT_ID] = "toto"
        all_props[pelix.rsa.SERVICE_IMPORTED_CONFIGS] = ["titi"]
        all_props[pelix.rsa.ECF_ENDPOINT_ID] = "toto"
        all_props[pelix.rsa.ECF_ENDPOINT_CONTAINERID_NAMESPACE] = "test"
        all_props[pelix.rsa.ENDPOINT_FRAMEWORK_UUID] = "other-fw"

        # Prepare an endpoint description with different property values
        endpoint = EndpointDescription(self.svc_ref, all_props)

        # Write it & parse it
        xml_string = EDEFWriter().to_string([endpoint])
        parsed = EDEFReader().parse(xml_string)[0]
        parsed_properties = parsed.get_properties()

        # Check values
        for key, initial_value in properties.items():
            if isinstance(initial_value, tuple):
                # EDEF transformation merges the tuple/list types
                initial_value = list(initial_value)

            self.assertEqual(parsed_properties[key], initial_value)


# ------------------------------------------------------------------------------


class BeansTest(unittest.TestCase):
    """
    Tests beans methods
    """

    def setUp(self) -> None:
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(["pelix.ipopo.core"])
        self.framework.start()

        # Register an exported service
        context = self.framework.get_bundle_context()
        self.service = object()
        svc_reg = context.register_service(
            "sample.spec",
            self.service,
            {
                pelix.rsa.SERVICE_EXPORTED_INTENTS: "*",
                pelix.rsa.SERVICE_EXPORTED_CONFIGS: "*",
                "some.property": "some value",
            },
        )
        self.svc_ref = svc_reg.get_reference()

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework()

        self.framework = None  # type: ignore
        self.svc_ref = None  # type: ignore

    def testConstructor(self) -> None:
        """
        Tests the behavior of the __init__ method
        """
        # Must fail due to the lack of endpoint.id
        self.assertRaises(ValueError, EndpointDescription, self.svc_ref, None)

        # Must not fail
        EndpointDescription(
            self.svc_ref,
            {
                pelix.rsa.ENDPOINT_ID: "toto",
                pelix.rsa.ECF_ENDPOINT_ID: "toto",
                pelix.rsa.ECF_ENDPOINT_CONTAINERID_NAMESPACE: "test",
                pelix.rsa.ENDPOINT_FRAMEWORK_UUID: "other-fw",
                pelix.rsa.SERVICE_IMPORTED_CONFIGS: ["titi"],
            },
        )

        # Must fail due to the lack of properties
        for mandatory in (pelix.rsa.ENDPOINT_ID, pelix.rsa.SERVICE_IMPORTED_CONFIGS):
            self.assertRaises(
                ValueError,
                EndpointDescription,
                None,
                {mandatory: "toto", pelix.constants.OBJECTCLASS: "spec", pelix.constants.SERVICE_ID: 1},
            )

        # Must not fail
        EndpointDescription(
            None,
            {
                pelix.rsa.ENDPOINT_ID: "toto",
                pelix.rsa.ECF_ENDPOINT_ID: "toto",
                pelix.rsa.ECF_ENDPOINT_CONTAINERID_NAMESPACE: "test",
                pelix.rsa.ENDPOINT_FRAMEWORK_UUID: "other-fw",
                pelix.rsa.SERVICE_IMPORTED_CONFIGS: ["titi"],
                pelix.constants.OBJECTCLASS: "spec",
                pelix.constants.SERVICE_ID: 1,
            },
        )
