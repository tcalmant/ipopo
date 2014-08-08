#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @Provides decorator.

:author: Thomas Calmant
"""

# Tests
from tests.interfaces import IEchoService
from tests.ipopo import install_bundle, install_ipopo

# Pelix
from pelix.framework import FrameworkFactory, BundleContext

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

NAME_A = "componentA"

# ------------------------------------------------------------------------------


class ProvidesTest(unittest.TestCase):
    """
    Tests the component "provides" behavior
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)

    def testProvides(self):
        """
        Tests if the provides decorator works
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Assert that the service is not yet available
        self.assertIsNone(context.get_service_reference(IEchoService),
                          "Service is already registered")

        # Instantiate the component
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        try:
            # Service should be there
            ref = context.get_service_reference(IEchoService)
            self.assertIsNotNone(ref, "Service hasn't been registered")

            # Second service should be there
            ref2 = context.get_service_reference("TestService")
            self.assertIsNotNone(ref, "Service hasn't been registered")

            # References must be different
            self.assertNotEqual(ref, ref2,
                                "Service references must be different")

            # Compare service instances
            svc = context.get_service(ref)
            self.assertIs(svc, compoA,
                          "Different instances for service and component")

            svc2 = context.get_service(ref2)
            self.assertEqual(svc, svc2, "Got different service instances")

            # Clean up
            context.unget_service(ref)
            context.unget_service(ref2)
            svc = None
            svc2 = None

            # Invalidate the component
            self.ipopo.invalidate(NAME_A)

            # Service should not be there anymore
            self.assertIsNone(context.get_service_reference(IEchoService),
                              "Service is still registered")

        finally:
            try:
                self.ipopo.kill(NAME_A)
            except:
                pass

    def testController(self):
        """
        Tests the service controller
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Assert that the service is not yet available
        self.assertIsNone(context.get_service_reference(IEchoService),
                          "Service is already registered")
        self.assertIsNone(context.get_service_reference("TestService"),
                          "TestService is already registered")

        # Instantiate the component
        self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        try:
            # Service should be there (controller default value is True)
            self.assertIsNotNone(context.get_service_reference(IEchoService),
                                 "EchoService hasn't been registered")

            ref = context.get_service_reference("TestService")
            self.assertIsNotNone(ref, "TestService hasn't been registered")

            # Get the service instance
            svc = context.get_service(ref)

            # Change the value of the controller
            svc.change_controller(False)
            self.assertIsNone(context.get_service_reference("TestService"),
                              "TestService hasn't been unregistered")
            self.assertIsNotNone(context.get_service_reference(IEchoService),
                                 "EchoService has been unregistered")

            # Re-change the value
            svc.change_controller(True)
            self.assertIsNotNone(context.get_service_reference("TestService"),
                                 "TestService hasn't been re-registered")
            self.assertIsNotNone(context.get_service_reference(IEchoService),
                                 "EchoService has been unregistered")

            # Invalidate the component
            self.ipopo.invalidate(NAME_A)

            # Re-change the value (once invalidated)
            svc.change_controller(True)

            # Service should not be there anymore
            self.assertIsNone(context.get_service_reference("TestService"),
                              "TestService is still registered")
            self.assertIsNone(context.get_service_reference(IEchoService),
                              "EchoService is still registered")

            # Clean up
            context.unget_service(ref)
            svc = None
            ref = None

        finally:
            try:
                self.ipopo.kill(NAME_A)
            except:
                pass

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
