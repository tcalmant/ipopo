#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Remote Services EDEF I/O operations

:author: Thomas Calmant
"""

import unittest
from typing import Any, Dict, Optional

import pelix.constants
import pelix.framework
import pelix.remote
import pelix.remote.beans as beans
from pelix.internals.registry import ServiceReference
from pelix.remote.edef_io import EDEFReader, EDEFWriter

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class EdefIOTest(unittest.TestCase):
    """
    Tests for the Remote Services EDEF I/O operations
    """

    framework: pelix.framework.Framework
    svc_ref: ServiceReference[Any]

    def assertDictContains(
        self, subset: Dict[str, Any], tested: Optional[Dict[str, Any]], msg: Any = None
    ) -> None:
        assert tested is not None
        self.assertEqual(tested, tested | subset, msg)

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
                pelix.remote.PROP_EXPORTED_INTENTS: "*",
                pelix.remote.PROP_EXPORTED_CONFIGS: "*",
                "some.property": "some value",
            },
        )
        self.svc_ref = svc_reg.get_reference()
        assert self.svc_ref is not None

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
        original = beans.EndpointDescription(
            self.svc_ref,
            {
                pelix.remote.PROP_ENDPOINT_ID: "toto",
                pelix.remote.PROP_IMPORTED_CONFIGS: ["titi"],
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
        all_props[pelix.remote.PROP_ENDPOINT_ID] = "toto"
        all_props[pelix.remote.PROP_IMPORTED_CONFIGS] = ["titi"]

        # Prepare an endpoint description with different property values
        endpoint = beans.EndpointDescription(self.svc_ref, all_props)

        # Write it & parse it
        xml_string = EDEFWriter().to_string([endpoint])
        parsed = EDEFReader().parse(xml_string)[0]
        parsed_properties = parsed.get_properties()

        # Check values
        self.assertDictContains(endpoint.get_properties(), parsed_properties)


# ------------------------------------------------------------------------------


class BeansTest(unittest.TestCase):
    """
    Tests beans methods
    """

    framework: pelix.framework.Framework
    svc_ref: ServiceReference[Any]

    def assertDictContains(
        self, subset: Dict[str, Any], tested: Optional[Dict[str, Any]], msg: Any = None
    ) -> None:
        assert tested is not None
        self.assertEqual(tested, tested | subset, msg)

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
                pelix.remote.PROP_EXPORTED_INTENTS: "*",
                pelix.remote.PROP_EXPORTED_CONFIGS: "*",
                "some.property": "some value",
            },
        )
        self.svc_ref = svc_reg.get_reference()
        assert self.svc_ref is not None

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
        self.assertRaises(ValueError, beans.EndpointDescription, self.svc_ref, None)

        # Must not fail
        beans.EndpointDescription(
            self.svc_ref,
            {pelix.remote.PROP_ENDPOINT_ID: "toto", pelix.remote.PROP_IMPORTED_CONFIGS: ["titi"]},
        )

        # Must fail due to the lack of properties
        for mandatory in (pelix.remote.PROP_ENDPOINT_ID, pelix.remote.PROP_IMPORTED_CONFIGS):
            self.assertRaises(
                ValueError,
                beans.EndpointDescription,
                None,
                {mandatory: "toto", pelix.constants.OBJECTCLASS: "spec", pelix.constants.SERVICE_ID: 1},
            )

        # Must not fail
        beans.EndpointDescription(
            None,
            {
                pelix.remote.PROP_ENDPOINT_ID: "toto",
                pelix.remote.PROP_IMPORTED_CONFIGS: ["titi"],
                pelix.constants.OBJECTCLASS: "spec",
                pelix.constants.SERVICE_ID: 1,
            },
        )

    def testProperties(self) -> None:
        """
        There must be no "service.exported.*" property in an endpoint
        description
        """
        # Original endpoint description
        original = beans.EndpointDescription(
            self.svc_ref,
            {
                pelix.remote.PROP_ENDPOINT_ID: "toto",
                pelix.remote.PROP_IMPORTED_CONFIGS: ["titi"],
                pelix.constants.OBJECTCLASS: "spec",
            },
        )
        for key in original.get_properties().keys():
            self.assertFalse(key.startswith("service.exported"), "An export property has been found")

    def testConvertBeans(self) -> None:
        """
        Tests the conversion of an ExportEndpoint to an EndpointDescription
        and of an EndpointDescription to an ImportEndpoint bean
        """
        # Prepare ExportEndpoint & ImportEndpoint beans
        specifications = self.svc_ref.get_property(pelix.constants.OBJECTCLASS)
        export_bean = beans.ExportEndpoint(
            "some.endpoint.uid",
            "some.framework.uid",
            ["configurationA"],
            "some.endpoint.name",
            self.svc_ref,
            self.service,
            {"extra.property": 42},
        )

        import_bean = beans.ImportEndpoint(
            export_bean.uid,
            export_bean.framework,
            export_bean.configurations,
            export_bean.name,
            export_bean.specifications,
            export_bean.make_import_properties(),
        )

        # Convert it to an EndpointDescription bean
        description_bean = beans.EndpointDescription.from_export(export_bean)

        # ... ensure its content is valid
        self.assertEqual(description_bean.get_id(), export_bean.uid)
        self.assertEqual(description_bean.get_framework_uuid(), export_bean.framework)
        self.assertEqual(description_bean.get_configuration_types(), export_bean.configurations)

        # ExportEndpoint specifications are prefixed by "python:/"
        self.assertEqual(description_bean.get_interfaces(), specifications)

        self.assertDictContains(export_bean.make_import_properties(), description_bean.get_properties())

        # Convert the result to an ImportEndpoint bean
        descripted_import = description_bean.to_import()

        # ... ensure its content is valid
        for field in ("uid", "framework", "configurations", "specifications"):
            self.assertEqual(getattr(descripted_import, field), getattr(import_bean, field))

        self.assertDictContains(import_bean.properties, descripted_import.properties)
