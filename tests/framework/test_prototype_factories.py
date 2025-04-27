#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the prototype service factory implementation

:author: Thomas Calmant
"""

import unittest

from pelix.framework import FrameworkFactory

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class PrototypeServiceFactoryTest(unittest.TestCase):
    """
    Prototype Service Factory tests
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
        FrameworkFactory.delete_framework()

    def test_prototype(self):
        """
        Tests the basic behaviour of prototype service factory handling
        """
        # Start the provider
        provider_bnd = self.context.install_bundle("tests.framework.prototype_service_bundle")
        provider_bnd.start()

        # Get the internal service
        svc_ref = self.context.get_service_reference("test.prototype.internal")
        factory = self.context.get_service(svc_ref)

        # Start the consumers
        consumer_bnd_1 = self.context.install_bundle("tests.dummy_1")
        consumer_bnd_1.start()
        ctx_1 = consumer_bnd_1.get_bundle_context()

        consumer_bnd_2 = self.context.install_bundle("tests.dummy_2")
        consumer_bnd_2.start()
        ctx_2 = consumer_bnd_2.get_bundle_context()

        # Find the service
        svc_ref = self.context.get_service_reference("test.prototype")

        # Get the service objects beans
        obj_1 = ctx_1.get_service_objects(svc_ref)
        obj_2 = ctx_2.get_service_objects(svc_ref)

        # Check the service reference
        self.assertIs(obj_1.get_service_reference(), svc_ref)

        # Get 2 service instances for the first bundle
        svc_1_a = obj_1.get_service()
        svc_1_b = obj_1.get_service()
        self.assertIsNot(svc_1_a, svc_1_b, "Same service returned")

        # Get 2 service instances for the second bundle
        svc_2_a = obj_2.get_service()
        svc_2_b = obj_2.get_service()
        self.assertIsNot(svc_2_a, svc_2_b, "Same service returned")
        self.assertIsNot(svc_1_a, svc_2_a, "Same service reused")
        self.assertIsNot(svc_1_b, svc_2_a, "Same service reused")
        self.assertIsNot(svc_2_a, svc_1_a, "Same service reused")
        self.assertIsNot(svc_2_b, svc_1_a, "Same service reused")

        # Unget the service properly for the first bundle
        self.assertFalse(svc_1_a.released)
        self.assertTrue(obj_1.unget_service(svc_1_a))
        self.assertTrue(svc_1_a.released)

        self.assertFalse(svc_1_b.released)
        self.assertTrue(obj_1.unget_service(svc_1_b))
        self.assertTrue(svc_1_b.released)

        # Try a second time (should do nothing)
        self.assertFalse(obj_1.unget_service(svc_1_a))

        # Ensure that the list of instances are in a valid state
        self.assertNotIn(consumer_bnd_1, factory.instances)
        self.assertIn(consumer_bnd_2, factory.instances)

    def test_consumer_stops(self):
        """
        Tests Prototype Factory when the consumer bundle stops roughly
        """
        # Start the provider
        provider_bnd = self.context.install_bundle("tests.framework.prototype_service_bundle")
        provider_bnd.start()

        # Get the internal service
        svc_ref = self.context.get_service_reference("test.prototype.internal")
        factory = self.context.get_service(svc_ref)

        # Start the consumers
        consumer_bnd = self.context.install_bundle("tests.dummy_1")
        consumer_bnd.start()
        ctx = consumer_bnd.get_bundle_context()

        # Find the service
        svc_ref = self.context.get_service_reference("test.prototype")

        # Get the service objects beans
        obj_1 = ctx.get_service_objects(svc_ref)

        # Check the service reference
        self.assertIs(obj_1.get_service_reference(), svc_ref)

        # Get a service instance
        svc = obj_1.get_service()
        self.assertIn(svc, factory.instances[consumer_bnd])

        # Stop the bundle
        consumer_bnd.stop()

        # Check the state of the factory
        self.assertTrue(svc.released)
        self.assertNotIn(consumer_bnd, factory.instances)

    def test_provider_stops(self):
        """
        Tests Prototype Factory when the provider bundle stops
        """
        # Start the provider
        provider_bnd = self.context.install_bundle("tests.framework.prototype_service_bundle")
        provider_bnd.start()

        # Get the internal service
        svc_ref = self.context.get_service_reference("test.prototype.internal")
        factory = self.context.get_service(svc_ref)

        # Start the consumers
        consumer_bnd = self.context.install_bundle("tests.dummy_1")
        consumer_bnd.start()
        ctx = consumer_bnd.get_bundle_context()

        # Find the service
        svc_ref = self.context.get_service_reference("test.prototype")

        # Get the service objects beans
        obj_1 = ctx.get_service_objects(svc_ref)

        # Check the service reference
        self.assertIs(obj_1.get_service_reference(), svc_ref)

        # Get a service instance
        svc = obj_1.get_service()
        self.assertIn(svc, factory.instances[consumer_bnd])

        # Stop the bundle
        provider_bnd.stop()

        # Check the state of the service and the factory
        self.assertTrue(svc.released)
        self.assertNotIn(consumer_bnd, factory.instances)

    def test_service_objects_singleton(self):
        """
        Tests BundleContext.get_service_objects() with a singleton service
        """
        # Start two bundles for their context
        bnd_1 = self.context.install_bundle("tests.dummy_1")
        bnd_1.start()
        ctx_1 = bnd_1.get_bundle_context()

        bnd_2 = self.context.install_bundle("tests.dummy_2")
        bnd_2.start()
        ctx_2 = bnd_2.get_bundle_context()

        # Singleton service
        singleton_svc = object()
        singleton_reg = self.context.register_service("test.singleton", singleton_svc, {})
        singleton_ref = singleton_reg.get_reference()

        # Get the singleton object
        obj_1 = ctx_1.get_service_objects(singleton_ref)
        svc_1_a = obj_1.get_service()
        svc_1_b = obj_1.get_service()
        svc_1_c = ctx_1.get_service(singleton_ref)
        self.assertIs(svc_1_a, svc_1_b)
        self.assertIs(svc_1_a, svc_1_c)

        obj_2 = ctx_2.get_service_objects(singleton_ref)
        svc_2_a = obj_2.get_service()
        svc_2_b = obj_2.get_service()
        svc_2_c = ctx_2.get_service(singleton_ref)
        self.assertIs(svc_2_a, svc_2_b)
        self.assertIs(svc_2_a, svc_2_c)

        # Ensure that the same service has been retrieved
        self.assertIs(svc_1_a, svc_2_a)

    def test_service_objects_factory(self):
        """
        Tests BundleContext.get_service_objects() with a factory service
        """
        # Start two bundles for their context
        bnd_1 = self.context.install_bundle("tests.dummy_1")
        bnd_1.start()
        ctx_1 = bnd_1.get_bundle_context()

        bnd_2 = self.context.install_bundle("tests.dummy_2")
        bnd_2.start()
        ctx_2 = bnd_2.get_bundle_context()

        # Service Factory
        class Factory:
            def get_service(self, bundle, svc_reg):
                return object()

            def unget_service(self, bundle, svc_reg):
                pass

        factory_svc = Factory()
        factory_reg = self.context.register_service("test.factory", factory_svc, {}, factory=True)
        factory_ref = factory_reg.get_reference()

        # Get the factory object
        obj_1 = ctx_1.get_service_objects(factory_ref)
        svc_1_a = obj_1.get_service()
        svc_1_b = obj_1.get_service()
        svc_1_c = ctx_1.get_service(factory_ref)
        self.assertIs(svc_1_a, svc_1_b)
        self.assertIs(svc_1_a, svc_1_c)

        obj_2 = ctx_2.get_service_objects(factory_ref)
        svc_2_a = obj_2.get_service()
        svc_2_b = obj_2.get_service()
        svc_2_c = ctx_2.get_service(factory_ref)
        self.assertIs(svc_2_a, svc_2_b)
        self.assertIs(svc_2_a, svc_2_c)

        # Ensure that a different service has been retrieved
        self.assertIsNot(svc_1_a, svc_2_a)


if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
