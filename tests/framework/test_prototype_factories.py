#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Tests the prototype service factory implementation
:author: Thomas Calmant, Angelo Cutaia
"""

# Standard library
import pytest

# Pelix
from pelix.framework import FrameworkFactory

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class TestPrototypeServiceFactory:
    """
    Prototype Service Factory tests
    """
    @pytest.mark.asyncio
    async def test_prototype(self):
        """
        Tests the basic behaviour of prototype service factory handling
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Start the provider
        provider_bnd = await context.install_bundle(
            "tests.framework.prototype_service_bundle")
        await provider_bnd.start()

        # Get the internal service
        svc_ref = await context.get_service_reference("test.prototype.internal")
        factory = await context.get_service(svc_ref)

        # Start the consumers
        consumer_bnd_1 = await context.install_bundle("tests.dummy_1")
        await consumer_bnd_1.start()
        ctx_1 = consumer_bnd_1.get_bundle_context()

        consumer_bnd_2 = await context.install_bundle("tests.dummy_2")
        await consumer_bnd_2.start()
        ctx_2 = consumer_bnd_2.get_bundle_context()

        # Find the service
        svc_ref = await context.get_service_reference("test.prototype")

        # Get the service objects beans
        obj_1 = ctx_1.get_service_objects(svc_ref)
        obj_2 = ctx_2.get_service_objects(svc_ref)

        # Check the service reference
        assert obj_1.get_service_reference() is svc_ref

        # Get 2 service instances for the first bundle
        svc_1_a = await obj_1.get_service()
        svc_1_b = await obj_1.get_service()
        assert svc_1_a is not svc_1_b, "Same service returned"

        # Get 2 service instances for the second bundle
        svc_2_a = await obj_2.get_service()
        svc_2_b = await obj_2.get_service()
        assert svc_2_a is not svc_2_b, "Same service returned"
        assert svc_1_a is not svc_2_a, "Same service reused"
        assert svc_1_b is not svc_2_a, "Same service reused"
        assert svc_2_a is not svc_1_a, "Same service reused"
        assert svc_2_b is not svc_1_a, "Same service reused"

        # Unget the service properly for the first bundle
        assert svc_1_a.released is False
        assert await obj_1.unget_service(svc_1_a) is True
        assert svc_1_a.released is True

        assert svc_1_b.released is False
        assert await obj_1.unget_service(svc_1_b) is True
        assert svc_1_b.released is True

        # Try a second time (should do nothing)
        assert await obj_1.unget_service(svc_1_a) is False

        # Ensure that the list of instances are in a valid state
        assert consumer_bnd_1 not in factory.instances
        assert consumer_bnd_2 in factory.instances

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_consumer_stops(self):
        """
        Tests Prototype Factory when the consumer bundle stops roughly
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Start the provider
        provider_bnd = await context.install_bundle(
            "tests.framework.prototype_service_bundle")
        await provider_bnd.start()

        # Get the internal service
        svc_ref = await context.get_service_reference("test.prototype.internal")
        factory = await context.get_service(svc_ref)

        # Start the consumers
        consumer_bnd = await context.install_bundle("tests.dummy_1")
        await consumer_bnd.start()
        ctx = consumer_bnd.get_bundle_context()

        # Find the service
        svc_ref = await context.get_service_reference("test.prototype")

        # Get the service objects beans
        obj_1 = ctx.get_service_objects(svc_ref)

        # Check the service reference
        assert obj_1.get_service_reference() is svc_ref

        # Get a service instance
        svc = await obj_1.get_service()
        assert svc in factory.instances[consumer_bnd]

        # Stop the bundle
        await consumer_bnd.stop()

        # Check the state of the factory
        assert svc.released is True
        assert consumer_bnd not in factory.instances

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_provider_stops(self):
        """
        Tests Prototype Factory when the provider bundle stops
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Start the provider
        provider_bnd = await context.install_bundle(
            "tests.framework.prototype_service_bundle")
        await provider_bnd.start()

        # Get the internal service
        svc_ref = await context.get_service_reference("test.prototype.internal")
        factory = await context.get_service(svc_ref)

        # Start the consumers
        consumer_bnd = await context.install_bundle("tests.dummy_1")
        await consumer_bnd.start()
        ctx = consumer_bnd.get_bundle_context()

        # Find the service
        svc_ref = await context.get_service_reference("test.prototype")

        # Get the service objects beans
        obj_1 = ctx.get_service_objects(svc_ref)

        # Check the service reference
        assert obj_1.get_service_reference() is svc_ref

        # Get a service instance
        svc = await obj_1.get_service()
        assert svc in factory.instances[consumer_bnd]

        # Stop the bundle
        await provider_bnd.stop()

        # Check the state of the service and the factory
        assert svc.released is True
        assert consumer_bnd not in factory.instances

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_service_objects_singleton(self):
        """
        Tests BundleContext.get_service_objects() with a singleton service
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Start two bundles for their context
        bnd_1 = await context.install_bundle("tests.dummy_1")
        await bnd_1.start()
        ctx_1 = bnd_1.get_bundle_context()

        bnd_2 = await context.install_bundle("tests.dummy_2")
        await bnd_2.start()
        ctx_2 = bnd_2.get_bundle_context()

        # Singleton service
        singleton_svc = object()
        singleton_reg = await context.register_service(
            "test.singleton", singleton_svc, {})
        singleton_ref = singleton_reg.get_reference()

        # Get the singleton object
        obj_1 = ctx_1.get_service_objects(singleton_ref)
        svc_1_a = await obj_1.get_service()
        svc_1_b = await obj_1.get_service()
        svc_1_c = await ctx_1.get_service(singleton_ref)
        assert svc_1_a is svc_1_b
        assert svc_1_a is svc_1_c

        obj_2 = ctx_2.get_service_objects(singleton_ref)
        svc_2_a = await obj_2.get_service()
        svc_2_b = await obj_2.get_service()
        svc_2_c = await ctx_2.get_service(singleton_ref)
        assert svc_2_a is svc_2_b
        assert svc_2_a is svc_2_c

        # Ensure that the same service has been retrieved
        assert svc_1_a is svc_2_a

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_service_objects_factory(self):
        """
        Tests BundleContext.get_service_objects() with a factory service
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Start two bundles for their context
        bnd_1 = await context.install_bundle("tests.dummy_1")
        await bnd_1.start()
        ctx_1 = bnd_1.get_bundle_context()

        bnd_2 = await context.install_bundle("tests.dummy_2")
        await bnd_2.start()
        ctx_2 = bnd_2.get_bundle_context()

        # Service Factory
        class Factory:
            async def get_service(self, bundle, svc_reg):
                return object()

            async def unget_service(self, bundle, svc_reg):
                pass

        factory_svc = Factory()
        factory_reg = await context.register_service(
            "test.factory", factory_svc, {}, factory=True)
        factory_ref = factory_reg.get_reference()

        # Get the factory object
        obj_1 = ctx_1.get_service_objects(factory_ref)
        svc_1_a = await obj_1.get_service()
        svc_1_b = await obj_1.get_service()
        svc_1_c = await ctx_1.get_service(factory_ref)
        assert svc_1_a is svc_1_b
        assert svc_1_a is svc_1_c

        obj_2 = ctx_2.get_service_objects(factory_ref)
        svc_2_a = await obj_2.get_service()
        svc_2_b = await obj_2.get_service()
        svc_2_c = await ctx_2.get_service(factory_ref)
        assert svc_2_a is svc_2_b
        assert svc_2_a is svc_2_c

        # Ensure that a different service has been retrieved
        assert svc_1_a is not svc_2_a

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()


if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)
