#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @Provides decorator.

:author: Thomas Calmant
"""

import sys
import unittest

from pelix.framework import BundleContext, FrameworkFactory
from tests.interfaces import IEchoService
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

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

        # Compatibility issue
        if sys.version_info[0] < 3:
            self.assertCountEqual = self.assertItemsEqual

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def testProvides(self):
        """
        Tests if the provides decorator works
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Assert that the service is not yet available
        self.assertIsNone(context.get_service_reference(IEchoService), "Service is already registered")

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
            self.assertNotEqual(ref, ref2, "Service references must be different")

            # Compare service instances
            svc = context.get_service(ref)
            self.assertIs(svc, compoA, "Different instances for service and component")

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
            self.assertIsNone(context.get_service_reference(IEchoService), "Service is still registered")
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
        self.assertIsNone(context.get_service_reference(IEchoService), "Service is already registered")
        self.assertIsNone(context.get_service_reference("TestService"), "TestService is already registered")

        # Instantiate the component
        self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        try:
            # Service should be there (controller default value is True)
            self.assertIsNotNone(
                context.get_service_reference(IEchoService), "EchoService hasn't been registered"
            )

            ref = context.get_service_reference("TestService")
            self.assertIsNotNone(ref, "TestService hasn't been registered")

            # Get the service instance
            svc = context.get_service(ref)

            # Change the value of the controller
            svc.change_controller(False)
            self.assertIsNone(
                context.get_service_reference("TestService"), "TestService hasn't been unregistered"
            )
            self.assertIsNotNone(
                context.get_service_reference(IEchoService), "EchoService has been unregistered"
            )

            # Re-change the value
            svc.change_controller(True)
            self.assertIsNotNone(
                context.get_service_reference("TestService"), "TestService hasn't been re-registered"
            )
            self.assertIsNotNone(
                context.get_service_reference(IEchoService), "EchoService has been unregistered"
            )

            # Invalidate the component
            self.ipopo.invalidate(NAME_A)

            # Re-change the value (once invalidated)
            svc.change_controller(True)

            # Service should not be there anymore
            self.assertIsNone(context.get_service_reference("TestService"), "TestService is still registered")
            self.assertIsNone(context.get_service_reference(IEchoService), "EchoService is still registered")

            # Clean up
            context.unget_service(ref)
        finally:
            try:
                self.ipopo.kill(NAME_A)
            except:
                pass

    def test_post_un_registration(self):
        """
        Tests the Post(Un)Registration decorator
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Assert that the service is not yet available
        self.assertIsNone(context.get_service_reference(IEchoService), "Service is already registered")
        self.assertIsNone(context.get_service_reference("TestService"), "TestService is already registered")

        # Instantiate the component
        component = self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        try:
            # Service should be there (controller default value is True)
            ref_echo = context.get_service_reference(IEchoService)
            self.assertIsNotNone(ref_echo, "EchoService hasn't been registered")

            ref = context.get_service_reference("TestService")
            self.assertIsNotNone(ref, "TestService hasn't been registered")

            # Check if the component has been notified
            self.assertCountEqual(component.calls_register, [ref_echo, ref])
            self.assertListEqual(component.calls_unregister, [])
            del component.calls_register[:]
            del component.calls_unregister[:]

            # Get the service instance
            svc = context.get_service(ref)

            # Change the value of the controller
            svc.change_controller(False)
            self.assertIsNone(
                context.get_service_reference("TestService"), "TestService hasn't been unregistered"
            )
            self.assertIsNotNone(
                context.get_service_reference(IEchoService), "EchoService has been unregistered"
            )

            self.assertListEqual(component.calls_register, [])
            self.assertListEqual(component.calls_unregister, [ref])
            del component.calls_register[:]
            del component.calls_unregister[:]

            # Re-change the value
            svc.change_controller(True)
            ref2 = context.get_service_reference("TestService")
            self.assertIsNotNone(ref2, "TestService hasn't been re-registered")
            self.assertIsNotNone(
                context.get_service_reference(IEchoService), "EchoService has been unregistered"
            )

            self.assertListEqual(component.calls_register, [ref2])
            self.assertListEqual(component.calls_unregister, [])
            del component.calls_register[:]
            del component.calls_unregister[:]

            # Invalidate the component
            self.ipopo.invalidate(NAME_A)

            self.assertListEqual(component.calls_register, [])
            self.assertCountEqual(component.calls_unregister, [ref_echo, ref2])
            del component.calls_register[:]
            del component.calls_unregister[:]

            # Re-change the value (once invalidated)
            svc.change_controller(True)

            # Service should not be there anymore
            self.assertIsNone(context.get_service_reference("TestService"), "TestService is still registered")
            self.assertIsNone(context.get_service_reference(IEchoService), "EchoService is still registered")

            # No notification here
            self.assertListEqual(component.calls_register, [])
            self.assertListEqual(component.calls_unregister, [])

            # Clean up
            context.unget_service(ref)
        finally:
            try:
                self.ipopo.kill(NAME_A)
            except:
                pass

    def test_factory(self):
        """
        Tests @Provides service factory handling
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()

        # Instantiate the provider
        component = self.ipopo.instantiate(module.FACTORY_PROVIDES_SVC_FACTORY, "provides.factory")

        # Ensure the initial state
        self.assertIsNone(component.caller, "Invalid initial state")
        self.assertIsNone(component.registration, "Invalid initial state")

        # Consume the service
        svc_ref = context.get_service_reference("factory.service")
        svc = context.get_service(svc_ref)

        # Ensure the new state
        self.assertIs(component.caller, self.framework)
        self.assertIs(component.registration.get_reference(), svc_ref)
        self.assertIs(component.service, svc)

        # Reset state
        component.caller = None
        component.registration = None

        # Try to re-get the service
        svc2 = context.get_service(svc_ref)

        # Ensure no sub call and same service
        self.assertIsNone(component.caller)
        self.assertIsNone(component.registration)
        self.assertIs(svc, svc2)

        # Unget the service
        context.unget_service(svc_ref)
        self.assertIsNone(component.caller)
        self.assertIsNone(component.registration)
        self.assertIs(svc, svc2)

        # A second time
        context.unget_service(svc_ref)
        self.assertIs(component.caller, self.framework)
        self.assertIs(component.registration.get_reference(), svc_ref)
        self.assertFalse(component.service)

    def test_prototype(self):
        """
        Tests @Provides prototype service factory handling
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()

        # Instantiate the provider
        component = self.ipopo.instantiate(module.FACTORY_PROVIDES_SVC_PROTOTYPE, "provides.prototype")

        # Ensure the initial state
        self.assertIsNone(component.caller, "Invalid initial state")
        self.assertIsNone(component.registration, "Invalid initial state")

        # Consume the service
        svc_ref = context.get_service_reference("prototype.service")
        objs = context.get_service_objects(svc_ref)
        svc = objs.get_service()

        # Ensure the new state
        self.assertIs(component.caller, self.framework)
        self.assertIs(component.registration.get_reference(), svc_ref)
        self.assertIs(component.services[-1], svc)

        # Reset state
        component.caller = None
        component.registration = None

        # Try to re-get the service
        svc2 = objs.get_service()

        # Ensure a new call has been made and we have a new service
        self.assertIs(component.caller, self.framework)
        self.assertIs(component.registration.get_reference(), svc_ref)
        self.assertIsNot(svc, svc2)

        # Ensure that the previous service reference has been kept
        self.assertIn(svc, component.services)
        self.assertIs(component.services[-1], svc2)

        # Unget the first service
        objs.unget_service(svc)
        self.assertTrue(component.flag_unget_instance)
        self.assertFalse(component.flag_unget_service)
        self.assertIs(component.caller, self.framework)
        self.assertIs(component.registration.get_reference(), svc_ref)
        self.assertNotIn(svc, component.services)
        self.assertIn(svc2, component.services)

        # Reset state
        component.flag_unget_instance = False
        component.caller = None
        component.registration = None

        # A second time
        objs.unget_service(svc2)
        self.assertTrue(component.flag_unget_instance)
        self.assertTrue(component.flag_unget_service)
        self.assertIs(component.caller, self.framework)
        self.assertIs(component.registration.get_reference(), svc_ref)
        self.assertNotIn(svc, component.services)
        self.assertNotIn(svc2, component.services)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
