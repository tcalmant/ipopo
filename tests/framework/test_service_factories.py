#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix framework test module. Tests the framework, bundles handling, service
handling and events.

:author: Thomas Calmant
"""

# Pelix
from pelix.framework import FrameworkFactory

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
        context_fw = self.framework.get_bundle_context()
        id_fw = context_fw.get_bundle().get_bundle_id()

        # Install the bundle providing a service factory
        factory_bundle = context_fw.install_bundle(self.test_bundle_name)
        factory_module = factory_bundle.get_module()
        factory_bundle.start()

        # Install another harmless bundle, to have two different contexts
        bundle_a = context_fw.install_bundle(
            "tests.framework.simple_bundle")
        bundle_a.start()
        context_a = bundle_a.get_bundle_context()
        id_a = context_a.get_bundle().get_bundle_id()

        # Find the service
        svc_ref = context_fw.get_service_reference(factory_module.SVC)

        # Get the service from the Framework context
        svc_fw = context_fw.get_service(svc_ref)
        self.assertEqual(svc_fw.requester_id(),
                         context_fw.get_bundle().get_bundle_id())
        self.assertListEqual(factory_module.FACTORY.made_for, [id_fw])

        # Get the service from the bundle context
        svc_a = context_a.get_service(svc_ref)
        self.assertEqual(svc_a.requester_id(), id_a, "Bad request bundle ID")
        self.assertListEqual(factory_module.FACTORY.made_for, [id_fw, id_a])

        # Get the service twice
        svc_b = context_a.get_service(svc_ref)
        self.assertEqual(svc_b.requester_id(), id_a, "Bad request bundle ID")

        # Ensure per-bundle variety
        self.assertListEqual(factory_module.FACTORY.made_for, [id_fw, id_a])
        self.assertIs(svc_a, svc_b, "Got different instances for a bundle")
        self.assertIsNot(
            svc_a, svc_fw, "Got the same instance for two bundles")

        # Release the service:
        # the framework reference must be clean immediately
        context_fw.unget_service(svc_ref)
        self.assertListEqual(factory_module.FACTORY.made_for, [id_a])

        # First release of second bundle: no change
        context_a.unget_service(svc_ref)
        self.assertListEqual(factory_module.FACTORY.made_for, [id_a])

        # All references of second bundle gone: factory must have been notified
        context_a.unget_service(svc_ref)
        self.assertListEqual(factory_module.FACTORY.made_for, [])

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
