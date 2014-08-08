#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the framework utility methods.

:author: Thomas Calmant
"""

# Pelix
from pelix.framework import FrameworkFactory
import pelix.framework as pelix

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

SERVICE_BUNDLE = "tests.framework.service_bundle"

# ------------------------------------------------------------------------------


class UtilityMethodsTest(unittest.TestCase):
    """
    Pelix utility methods tests
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = None
        self.test_bundle_name = SERVICE_BUNDLE

    def tearDown(self):
        """
        Called after each test
        """
        if self.framework is not None:
            FrameworkFactory.delete_framework(self.framework)
            self.framework = None

    def testCreateFrameworkBasic(self):
        """
        Tests create_framework(), without parameters
        -> creates an empty framework, and doesn't start it
        """
        self.framework = pelix.create_framework([])
        self.assertEqual(self.framework.get_state(), pelix.Bundle.RESOLVED,
                         'Framework has been started')
        self.assertEqual(self.framework.get_bundles(), [],
                         'Framework is not empty')

        # Try to start two framework
        self.assertRaises(ValueError, pelix.create_framework, [])

    def testCreateFrameworkWithBundles(self):
        """
        Tests create_framework(), with specified bundles
        """
        self.framework = pelix.create_framework([self.test_bundle_name])
        self.assertEqual(self.framework.get_state(), pelix.Bundle.RESOLVED,
                         'Framework has been started')

        self.assertEqual(len(self.framework.get_bundles()), 1,
                         'Framework should only have 1 bundle')

        bundle = self.framework.get_bundle_by_id(1)
        self.assertEqual(bundle.get_symbolic_name(), self.test_bundle_name,
                         "The test bundle hasn't been installed correctly")

    def testCreateFrameworkAutoStart(self):
        """
        Tests create_framework(), with specified bundles and auto-start
        """
        # Without bundles
        self.framework = pelix.create_framework([], auto_start=True)
        self.assertEqual(self.framework.get_state(), pelix.Bundle.ACTIVE,
                         "Framework hasn't been started")
        self.assertEqual(self.framework.get_bundles(), [],
                         'Framework is not empty')
        # Clean up
        FrameworkFactory.delete_framework(self.framework)

        # With bundles
        self.framework = pelix.create_framework([self.test_bundle_name],
                                                auto_start=True)
        self.assertEqual(self.framework.get_state(), pelix.Bundle.ACTIVE,
                         "Framework hasn't been started")
        self.assertEqual(len(self.framework.get_bundles()), 1,
                         'Framework should only have 1 bundle')

        bundle = self.framework.get_bundle_by_id(1)
        self.assertEqual(bundle.get_symbolic_name(), self.test_bundle_name,
                         "The test bundle hasn't been installed correctly")
        self.assertEqual(bundle.get_state(), pelix.Bundle.ACTIVE,
                         "Bundle hasn't been started")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
