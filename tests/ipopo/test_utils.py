#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO utility methods.

:author: Thomas Calmant
"""

# Tests
from tests.ipopo import install_ipopo

# Pelix
from pelix.framework import FrameworkFactory
import pelix.framework as pelix

# iPOPO
import pelix.ipopo.constants as constants

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class UtilitiesTest(unittest.TestCase):
    """
    Tests the utility methods
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.context = self.framework.get_bundle_context()

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)
        self.framework = None
        self.context = None

    def testConstantGetReference(self):
        """
        Tests the ipopo.constants.get_service_reference() method
        """
        # Try without the bundle
        self.assertIsNone(constants.get_ipopo_svc_ref(self.context),
                          "iPOPO service found while not installed.")

        # Install the iPOPO bundle
        ipopo_svc = install_ipopo(self.framework)

        # Test the method result
        ref, svc = constants.get_ipopo_svc_ref(self.context)
        self.assertIsNotNone(ref, "Invalid service reference")
        self.assertIs(svc, ipopo_svc, "Found a different service.")

        # Stop the iPOPO bundle
        ref.get_bundle().stop()

        # Ensure the service is not accessible anymore
        self.assertIsNone(constants.get_ipopo_svc_ref(self.context),
                          "iPOPO service found while stopped.")

        # Uninstall the bundle
        ref.get_bundle().uninstall()

        # Ensure the service is not accessible anymore
        self.assertIsNone(constants.get_ipopo_svc_ref(self.context),
                          "iPOPO service found while stopped.")

    def testConstantContext(self):
        """
        Tests ipopo.constants.use_ipopo()
        """
        # Try without the bundle
        self.assertRaises(pelix.BundleException,
                          constants.use_ipopo(self.context).__enter__)

        # Start the iPOPO bundle
        bundle = self.context.install_bundle("pelix.ipopo.core")
        bundle.start()

        # Get the iPOPO service reference
        # (the only one registered in this bundle)
        ipopo_ref = bundle.get_registered_services()[0]

        # Use it
        with constants.use_ipopo(self.context) as ipopo:
            # Test the usage information
            self.assertIn(self.context.get_bundle(),
                          ipopo_ref.get_using_bundles(),
                          "Bundles using iPOPO not updated")

            # Get the service the Pelix way
            ipopo_svc = self.context.get_service(ipopo_ref)

            # Test the service object
            self.assertIs(ipopo, ipopo_svc, "Found a different service.")

            # Clean up the test usage
            self.context.unget_service(ipopo_ref)
            ipopo_svc = None

            # Re-test the usage information
            self.assertIn(self.context.get_bundle(),
                          ipopo_ref.get_using_bundles(),
                          "Bundles using iPOPO not kept")

        # Test the usage information
        self.assertNotIn(self.context.get_bundle(),
                         ipopo_ref.get_using_bundles(),
                         "Bundles using iPOPO kept after block")

        # Stop the iPOPO bundle
        bundle.stop()

        # Ensure the service is not accessible anymore
        self.assertRaises(pelix.BundleException,
                          constants.use_ipopo(self.context).__enter__)

        # Uninstall the bundle
        bundle.uninstall()

        # Ensure the service is not accessible anymore
        self.assertRaises(pelix.BundleException,
                          constants.use_ipopo(self.context).__enter__)

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
