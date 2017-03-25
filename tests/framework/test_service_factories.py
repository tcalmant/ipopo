#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix framework test module. Tests the framework, bundles handling, service
handling and events.

:author: Thomas Calmant
"""

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
        self.test_bundle_name = "tests.framework.service_factory_bundle"

        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def test_factory(self):
        """
        Tests the basic behaviour of a service factory
        """
        context = self.framework.get_bundle_context()
        bundle = context.install_bundle(self.test_bundle_name)
        module = bundle.get_module()
        bundle.start()

        svc_ref = context.get_service_reference(module.SVC)
        svc = context.get_service(svc_ref)
        self.assertEqual(svc.show(), 0)
        context.unget_service(svc_ref)

        svc = context.get_service(svc_ref)
        self.assertEqual(svc.show(), 0)
        context.unget_service(svc_ref)

        bc = bundle.get_bundle_context()
        svc = bc.get_service(svc_ref)
        self.assertEqual(svc.show(), bundle.get_bundle_id())
        bc.unget_service(svc_ref)

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
