#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix framework test module. Tests the framework, bundles handling, service
handling and events.

:author: Thomas Calmant
"""

import os
import unittest

from pelix.framework import FrameworkFactory

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

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
        bundle_a = context_fw.install_bundle("tests.framework.simple_bundle")
        bundle_a.start()
        context_a = bundle_a.get_bundle_context()
        id_a = context_a.get_bundle().get_bundle_id()

        # Find the service
        svc_ref = context_fw.get_service_reference(factory_module.SVC)

        # Get the service from the Framework context
        svc_fw = context_fw.get_service(svc_ref)
        self.assertEqual(svc_fw.requester_id(), context_fw.get_bundle().get_bundle_id())
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
        self.assertIsNot(svc_a, svc_fw, "Got the same instance for two bundles")

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

    def test_cleanup(self):
        """
        Tests the behavior of the framework when cleaning up a bundle
        """
        ctx = self.framework.get_bundle_context()

        # Install the bundle providing a service factory
        factory_bundle = ctx.install_bundle(self.test_bundle_name)
        factory_module = factory_bundle.get_module()
        factory_bundle.start()

        self.assertIsNone(os.environ.get("factory.get"))
        self.assertIsNone(os.environ.get("factory.unget"))

        # Find the service
        svc_ref = ctx.get_service_reference(factory_module.SVC_NO_CLEAN)

        # Get the service from the Framework context
        svc = ctx.get_service(svc_ref)

        self.assertEqual(os.environ.get("factory.get"), "OK")
        self.assertIsNone(os.environ.get("factory.unget"))

        # Check if we got the registration correctly
        self.assertIs(svc.real, svc.given)
        self.assertListEqual(svc_ref.get_using_bundles(), [self.framework])
        self.assertEqual(svc.real.get_reference(), svc_ref, "Wrong reference")

        # Clean up environment
        del os.environ["factory.get"]

        # Uninstall the bundle
        factory_bundle.uninstall()

        self.assertIsNone(os.environ.get("factory.get"))
        self.assertEqual(os.environ.get("factory.unget"), "OK")

        # Clean up environment
        os.environ.pop("factory.get", None)
        del os.environ["factory.unget"]

        # Check clean up
        self.assertIs(svc.real, svc.given)
        self.assertListEqual(svc_ref.get_using_bundles(), [])

    def test_auto_release(self):
        """
        Tests auto-release of a service factory
        """
        # Register a service for the framework
        context_fw = self.framework.get_bundle_context()

        # Install the bundle providing a service factory
        factory_bundle = context_fw.install_bundle(self.test_bundle_name)
        factory_module = factory_bundle.get_module()
        factory_bundle.start()

        # Find the service
        svc_ref = context_fw.get_service_reference(factory_module.SVC)

        # Start a dummy bundle for its context
        bnd = context_fw.install_bundle("tests.dummy_1")
        bnd.start()
        ctx = bnd.get_bundle_context()

        # Consume the service
        svc = ctx.get_service(svc_ref)
        self.assertIsNotNone(svc)
        self.assertIn(bnd, svc_ref.get_using_bundles())

        # Stop the bundle
        bnd.stop()

        # Ensure the release of the service
        self.assertNotIn(bnd, svc_ref.get_using_bundles())


if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
