#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix framework test module. Tests the framework, bundles handling, service
handling and events.

:author: Thomas Calmant
"""

# Tests
from tests.interfaces import IEchoService

# Pelix
from pelix.framework import FrameworkFactory, Bundle, BundleException, \
    BundleContext, ServiceReference
import pelix.constants

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class ServicesTest(unittest.TestCase):
    """
    Pelix services registry tests
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework and loads the current
        module as the first bundle
        """
        self.test_bundle_name = "tests.framework.service_bundle"

        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)

    def testBundleRegister(self):
        """
        Test the service registration, request and unregister in a well formed
        bundle (activator that unregisters the service during the stop call)
        """
        svc_filter = "(test=True)"

        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Install the service bundle
        bundle = context.install_bundle(self.test_bundle_name)
        bundle_context = bundle.get_bundle_context()
        module = bundle.get_module()

        # Assert we can't access the service
        ref1 = context.get_service_reference(IEchoService)
        self.assertIsNone(ref1,
                          "get_service_reference found: {0}".format(ref1))

        ref2 = context.get_service_reference(IEchoService, svc_filter)
        self.assertIsNone(ref2, "get_service_reference, filtered found: {0}"
                          .format(ref2))

        refs = context.get_all_service_references(IEchoService, None)
        self.assertIsNone(refs, "get_all_service_reference found: {0}"
                          .format(refs))

        refs = context.get_all_service_references(IEchoService, svc_filter)
        self.assertIsNone(refs,
                          "get_all_service_reference, filtered found: {0}"
                          .format(refs))

        # --- Start it (registers a service) ---
        bundle.start()

        # Get the reference
        ref1 = context.get_service_reference(IEchoService)
        self.assertIsNotNone(ref1, "get_service_reference found nothing")

        ref2 = context.get_service_reference(IEchoService, svc_filter)
        self.assertIsNotNone(ref2,
                             "get_service_reference, filtered found nothing")

        # Assert we found the same references
        self.assertIs(ref1, ref2, "References are not the same")

        # Get all IEchoServices
        refs = context.get_all_service_references(IEchoService, None)

        # Assert we found only one reference
        self.assertIsNotNone(refs, "get_all_service_reference found nothing")

        refs = context.get_all_service_references(IEchoService, svc_filter)

        # Assert we found only one reference
        self.assertIsNotNone(refs,
                             "get_all_service_reference filtered "
                             "found nothing")

        # Assert that the first found reference is the first of "all"
        # references
        self.assertIs(ref1, refs[0],
                      "Not the same references through get and get_all")

        # Assert that the bundle can find its own services
        self.assertListEqual(
            refs,
            bundle_context.get_service_references(IEchoService, None),
            "The bundle can't find its own services")

        self.assertListEqual(
            refs,
            bundle_context.get_service_references(IEchoService, svc_filter),
            "The bundle can't find its own filtered services")

        # Assert that the framework bundle context can't find the bundle
        # services
        self.assertListEqual(
            [], context.get_service_references(IEchoService, None),
            "Framework bundle shoudln't get the echo service")

        self.assertListEqual(
            [],
            context.get_service_references(IEchoService, svc_filter),
            "Framework bundle shoudln't get the filtered echo service")

        # Get the service
        svc = context.get_service(ref1)
        assert isinstance(svc, IEchoService)

        # Validate the reference
        self.assertIs(svc, module.service, "Not the same service instance...")

        # Unget the service
        context.unget_service(ref1)

        # --- Stop it (unregisters a service) ---
        bundle.stop()

        # Assert we can't access the service
        ref1 = context.get_service_reference(IEchoService)
        self.assertIsNone(ref1, "get_service_reference found: {0}"
                          .format(ref1))

        ref2 = context.get_service_reference(IEchoService, svc_filter)
        self.assertIsNone(ref2, "get_service_reference, filtered found: {0}"
                          .format(ref2))

        refs = context.get_all_service_references(IEchoService, None)
        self.assertIsNone(refs, "get_all_service_reference found: {0}"
                          .format(refs))

        refs = context.get_all_service_references(IEchoService, svc_filter)
        self.assertIsNone(refs,
                          "get_all_service_reference, filtered found: {0}"
                          .format(refs))

        # --- Uninstall it ---
        bundle.uninstall()

    def testBundleUninstall(self):
        """
        Tests if a registered service is correctly removed, even if its
        registering bundle doesn't have the code for that
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Install the service bundle
        bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        module = bundle.get_module()

        # --- Start it (registers a service) ---
        bundle.start()

        self.assertIsNotNone(module.service, "The service instance is missing")

        # Get the reference
        ref = context.get_service_reference(IEchoService)
        self.assertIsNotNone(ref, "get_service_reference found nothing")
        self.assertIn(ref, bundle.get_registered_services(),
                      "Reference not in registered services")

        # Get the service
        svc = context.get_service(ref)
        self.assertIsNotNone(svc, "Service not found")
        self.assertIn(ref, self.framework.get_services_in_use(),
                      "Reference usage not indicated")

        # Release the service
        context.unget_service(ref)
        self.assertNotIn(ref, self.framework.get_services_in_use(),
                         "Reference usage not removed")
        svc = None

        # --- Uninstall the bundle without stopping it first ---
        bundle.uninstall()

        # The service should be deleted
        ref = context.get_service_reference(IEchoService)
        self.assertIsNone(ref, "get_service_reference found: {0}".format(ref))

        # We shouldn't have access to the bundle services anymore
        self.assertRaises(BundleException, bundle.get_registered_services)
        self.assertRaises(BundleException, bundle.get_services_in_use)

    def testServiceReferencesCmp(self):
        """
        Tests service references comparisons
        """

        # Invalid references...
        # ... empty properties
        self.assertRaises(BundleException, ServiceReference,
                          self.framework, {})
        # ... no service ID
        self.assertRaises(BundleException, ServiceReference, self.framework,
                          {pelix.constants.OBJECTCLASS: "a"})
        # ... no object class
        self.assertRaises(BundleException, ServiceReference, self.framework,
                          {pelix.constants.SERVICE_ID: "b"})

        ref1b = ServiceReference(self.framework,
                                 {pelix.constants.OBJECTCLASS: "ref1_b",
                                  pelix.constants.SERVICE_ID: 1,
                                  pelix.constants.SERVICE_RANKING: 0})

        ref1 = ServiceReference(self.framework,
                                {pelix.constants.OBJECTCLASS: "ref1",
                                 pelix.constants.SERVICE_ID: 1})

        ref2 = ServiceReference(self.framework,
                                {pelix.constants.OBJECTCLASS: "ref2",
                                 pelix.constants.SERVICE_ID: 2})

        ref3 = ServiceReference(self.framework,
                                {pelix.constants.OBJECTCLASS: "ref3",
                                 pelix.constants.SERVICE_ID: 3,
                                 pelix.constants.SERVICE_RANKING: -20})

        ref4 = ServiceReference(self.framework,
                                {pelix.constants.OBJECTCLASS: "ref4",
                                 pelix.constants.SERVICE_ID: 4,
                                 pelix.constants.SERVICE_RANKING: 128})

        # Tests
        self.assertEqual(ref1, ref1, "ID1 == ID1")
        self.assertLessEqual(ref1, ref1, "ID1 == ID1")

        self.assertEqual(ref1, ref1b, "ID1 == ID1.0")
        self.assertGreaterEqual(ref1, ref1b, "ID1 >= ID1.0")

        # ID comparison
        self.assertLess(ref2, ref1, "ID2 < ID1")
        self.assertLessEqual(ref2, ref1, "ID2 <= ID1")
        self.assertGreater(ref1, ref2, "ID2 > ID1")
        self.assertGreaterEqual(ref1, ref2, "ID1 >= ID2")

        # Ranking comparison
        self.assertGreater(ref4, ref3, "ID4.128 > ID3.-20")
        self.assertGreaterEqual(ref4, ref3, "ID4.128 >= ID3.-20")
        self.assertLess(ref3, ref4, "ID3.-20 < ID4.128")
        self.assertLessEqual(ref3, ref4, "ID3.-20 <= ID4.128")

        # Ensure that comparison is not based on ID
        self.assertLess(ref3, ref1, "ID3.-20 < ID1.0")
        self.assertGreater(ref1, ref3, "ID3.-20 > ID1.0")

    def testServiceRegistrationUpdate(self):
        """
        Try to update service properties
        """
        context = self.framework.get_bundle_context()

        # Register service
        base_props = {pelix.constants.OBJECTCLASS: "titi",
                      pelix.constants.SERVICE_ID: -1,
                      "test": 42}

        reg = context.register_service("class", self, base_props)
        ref = reg.get_reference()

        # Ensure that reserved properties have been overridden
        object_class = ref.get_property(pelix.constants.OBJECTCLASS)
        self.assertListEqual(object_class, ["class"],
                             "Invalid objectClass property '{0}'"
                             .format(object_class))

        svc_id = ref.get_property(pelix.constants.SERVICE_ID)
        self.assertGreater(svc_id, 0, "Invalid service ID")

        # Ensure the reference uses a copy of the properties
        base_props["test"] = 21
        self.assertEqual(ref.get_property("test"), 42,
                         "Property updated by the dictionary reference")

        # Update the properties
        update_props = {pelix.constants.OBJECTCLASS: "ref2",
                        pelix.constants.SERVICE_ID: 20,
                        "test": 21}

        reg.set_properties(update_props)

        # Ensure that reserved properties have been kept
        self.assertListEqual(ref.get_property(pelix.constants.OBJECTCLASS),
                             object_class, "Modified objectClass property")

        self.assertEqual(ref.get_property(pelix.constants.SERVICE_ID), svc_id,
                         "Modified service ID")

        self.assertEqual(ref.get_property("test"), 21,
                         "Extra property not updated")

    def testGetAllReferences(self):
        """
        Tests get_all_service_references() method
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Get all references count
        all_refs = context.get_all_service_references(None, None)
        self.assertIsNotNone(all_refs,
                             "All references result must not be None")
        self.assertEqual(len(all_refs), 0, "Services list should be empty")

        # Install the service bundle
        bundle = context.install_bundle(self.test_bundle_name)

        # No services yet
        all_refs = context.get_all_service_references(None, None)
        self.assertIsNotNone(all_refs,
                             "All references result must not be None")
        self.assertEqual(len(all_refs), 0, "Services list should be empty")

        # Start the bundle
        bundle.start()

        all_refs = context.get_all_service_references(None, None)
        self.assertIsNotNone(all_refs,
                             "All references result must not be None")
        self.assertGreater(len(all_refs), 0,
                           "Services list shouldn't be empty")

        # Try with an empty filter (lists should be equal)
        all_refs_2 = context.get_all_service_references(None, "")
        self.assertListEqual(all_refs, all_refs_2,
                             "References lists should be equal")

        # Assert that the registered service is in the list
        ref = context.get_service_reference(IEchoService)
        self.assertIsNotNone(ref, "get_service_reference found nothing")
        self.assertIn(ref, all_refs,
                      "Echo service should be the complete list")

        # Remove the bundle
        bundle.uninstall()

        # Test an invalid filter
        self.assertRaises(BundleException, context.get_all_service_references,
                          None, "/// Invalid Filter ///")

    def testMultipleUnregistrations(self):
        """
        Tests behavior when unregistering the same service twice
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register a dummy service
        registration = context.register_service("test", self, None, False)

        # Unregister it twice
        registration.unregister()
        self.assertRaises(BundleException, registration.unregister)

    def testInvalidGetService(self):
        """
        Tests behavior when using get_service on an invalid service
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register a dummy service
        registration = context.register_service("test", self, None, False)

        # Get the reference
        reference = registration.get_reference()

        # Unregister the service
        registration.unregister()

        # Try to get it
        self.assertRaises(BundleException, context.get_service, reference)

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
