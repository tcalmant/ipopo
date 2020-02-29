#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Pelix framework test module. Tests the framework, bundles handling, service
handling and events.

:author: Thomas Calmant, Angelo Cutaia
"""

# Standard library
import pytest

# Tests
from tests.interfaces import IEchoService

# Pelix
from pelix.framework import FrameworkFactory, Bundle, BundleException, \
    BundleContext, ServiceReference
import pelix.constants


# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class TestServices:
    """
    Pelix services registry tests
    """
    @pytest.mark.asyncio
    async def test_bundle_register(self):
        """
        Test the service registration, request and unregister in a well formed
        bundle (activator that unregisters the service during the stop call)
        """
        # Setup
        test_bundle_name = "tests.framework.service_bundle"
        framework = FrameworkFactory.get_framework()
        await framework.start()

        svc_filter = "(test=True)"

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Install the service bundle
        bundle = await context.install_bundle(test_bundle_name)
        bundle_context = bundle.get_bundle_context()
        module_ = bundle.get_module()

        # Assert we can't access the service
        ref1 = await context.get_service_reference(IEchoService)
        assert ref1 is None, "get_service_reference found: {0}".format(ref1)

        ref2 = await context.get_service_reference(IEchoService, svc_filter)
        assert ref2 is None, "get_service_reference, filtered found: {0}".format(ref2)

        refs = await context.get_all_service_references(IEchoService, None)
        assert refs is None, "get_all_service_reference found: {0}".format(refs)

        refs = await context.get_all_service_references(IEchoService, svc_filter)
        assert refs is None, "get_all_service_reference, filtered found: {0}".format(refs)

        # --- Start it (registers a service) ---
        await bundle.start()

        # Get the reference
        ref1 = await context.get_service_reference(IEchoService)
        assert ref1 is not None, "get_service_reference found nothing"

        ref2 = await context.get_service_reference(IEchoService, svc_filter)
        assert ref2 is not None, "get_service_reference, filtered found nothing"

        # Assert we found the same references
        assert ref1 is ref2, "References are not the same"

        # Get all IEchoServices
        refs = await context.get_all_service_references(IEchoService, None)

        # Assert we found only one reference
        assert refs is not None, "get_all_service_reference found nothing"

        refs = await context.get_all_service_references(IEchoService, svc_filter)

        # Assert we found only one reference
        assert refs is not None, "get_all_service_reference filtered found nothing"

        # Assert that the first found reference is the first of "all"
        # references
        assert ref1 is refs[0], "Not the same references through get and get_all"

        # Assert that the bundle can find its own services
        assert refs == await bundle_context.get_service_references(IEchoService, None), "The bundle can't find its own services"

        assert refs == await bundle_context.get_service_references(IEchoService, svc_filter), "The bundle can't find its own filtered services"

        # Assert that the framework bundle context can't find the bundle
        # services
        assert [] == await context.get_service_references(IEchoService, None), "Framework bundle shouldn't get the echo service"

        assert [] == await context.get_service_references(IEchoService, svc_filter), "Framework bundle shouldn't get the filtered echo service"

        # Get the service
        svc = await context.get_service(ref1)
        assert isinstance(svc, IEchoService)

        # Validate the reference
        assert svc is module_.service, "Not the same service instance..."

        # Unget the service
        await context.unget_service(ref1)

        # --- Stop it (unregisters a service) ---
        await bundle.stop()

        # Assert we can't access the service
        ref1 = await context.get_service_reference(IEchoService)
        assert ref1 is None, "get_service_reference found: {0}".format(ref1)

        ref2 = await context.get_service_reference(IEchoService, svc_filter)
        assert ref2 is None, "get_service_reference, filtered found: {0}".format(ref2)

        refs = await context.get_all_service_references(IEchoService, None)
        assert refs is None, "get_all_service_reference found: {0}".format(refs)

        refs = await context.get_all_service_references(IEchoService, svc_filter)
        assert refs is None, "get_all_service_reference, filtered found: {0}".format(refs)

        # --- Uninstall it ---
        await bundle.uninstall()

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_bundle_uninstall(self):
        """
        Tests if a registered service is correctly removed, even if its
        registering bundle doesn't have the code for that
        """
        # Setup
        test_bundle_name = "tests.framework.service_bundle"
        framework = FrameworkFactory.get_framework()
        await framework.start()

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Install the service bundle
        bundle = await context.install_bundle(test_bundle_name)
        assert isinstance(bundle, Bundle)

        module_ = bundle.get_module()

        # --- Start it (registers a service) ---
        await bundle.start()

        assert module_.service is not None, "The service instance is missing"

        # Get the reference
        ref = await context.get_service_reference(IEchoService)
        assert ref is not None, "get_service_reference found nothing"
        assert ref in await bundle.get_registered_services(), "Reference not in registered services"

        # Get the service
        svc = await context.get_service(ref)
        assert svc is not None, "Service not found"
        assert ref in await framework.get_services_in_use(), "Reference usage not indicated"

        # Release the service
        await context.unget_service(ref)
        assert ref not in await framework.get_services_in_use(), "Reference usage not removed"

        # --- Uninstall the bundle without stopping it first ---
        await bundle.uninstall()

        # The service should be deleted
        ref = await context.get_service_reference(IEchoService)
        assert ref is None, "get_service_reference found: {0}".format(ref)

        # We shouldn't have access to the bundle services anymore
        with pytest.raises(BundleException):
            await bundle.get_registered_services()
        with pytest.raises(BundleException):
            await bundle.get_services_in_use()

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_service_references_cmp(self):
        """
        Tests service references comparisons
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        # Invalid references...
        # ... empty properties
        with pytest.raises(BundleException):
            ServiceReference(framework, {})
        # ... no service ID
        with pytest.raises(BundleException):
            ServiceReference(framework, {pelix.constants.OBJECTCLASS: "a"})
        # ... no object class
        with pytest.raises(BundleException):
            ServiceReference(framework, {pelix.constants.SERVICE_ID: "b"})

        ref1b = ServiceReference(framework,
                                 {pelix.constants.OBJECTCLASS: "ref1_b",
                                  pelix.constants.SERVICE_ID: 1,
                                  pelix.constants.SERVICE_RANKING: 0})

        ref1 = ServiceReference(framework,
                                {pelix.constants.OBJECTCLASS: "ref1",
                                 pelix.constants.SERVICE_ID: 1})

        ref2 = ServiceReference(framework,
                                {pelix.constants.OBJECTCLASS: "ref2",
                                 pelix.constants.SERVICE_ID: 2})

        ref3 = ServiceReference(framework,
                                {pelix.constants.OBJECTCLASS: "ref3",
                                 pelix.constants.SERVICE_ID: 3,
                                 pelix.constants.SERVICE_RANKING: -20})

        ref4 = ServiceReference(framework,
                                {pelix.constants.OBJECTCLASS: "ref4",
                                 pelix.constants.SERVICE_ID: 4,
                                 pelix.constants.SERVICE_RANKING: 128})

        # Tests
        assert ref1 == ref1, "ID1 == ID1"
        assert ref1 <= ref1, "ID1 == ID1"

        assert ref1 == ref1b, "ID1 == ID1.0"
        assert ref1 >= ref1b, "ID1 >= ID1.0"

        # ID comparison
        assert ref2 > ref1, "ID2 > ID1"
        assert ref2 >= ref1, "ID2 >= ID1"
        assert ref1 < ref2, "ID2 < ID1"
        assert ref1 <= ref2, "ID1 <= ID2"

        # Ranking comparison
        assert ref4 < ref3, "ID4.128 < ID3.-20"
        assert ref4 <= ref3, "ID4.128 <= ID3.-20"
        assert ref3 > ref4, "ID3.-20 > ID4.128"
        assert ref3 >= ref4, "ID3.-20 >= ID4.128"

        # Ensure that comparison is not based on ID
        assert ref3 > ref1, "ID3.-20 > ID1.0"
        assert ref1 < ref3, "ID3.-20 < ID1.0"

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_service_registrationupdate(self):
        """
        Try to update service properties
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        context = framework.get_bundle_context()

        # Register service
        base_props = {pelix.constants.OBJECTCLASS: "titi",
                      pelix.constants.SERVICE_ID: -1,
                      "test": 42}

        reg = await context.register_service("class", self, base_props)
        ref = reg.get_reference()

        # Ensure that reserved properties have been overridden
        object_class = await ref.get_property(pelix.constants.OBJECTCLASS)
        assert object_class == ["class"], "Invalid objectClass property '{0}'".format(object_class)

        svc_id = await ref.get_property(pelix.constants.SERVICE_ID)
        assert svc_id > 0, "Invalid service ID"

        # Ensure the reference uses a copy of the properties
        base_props["test"] = 21
        assert await ref.get_property("test") == 42, "Property updated by the dictionary reference"

        # Update the properties
        update_props = {pelix.constants.OBJECTCLASS: "ref2",
                        pelix.constants.SERVICE_ID: 20,
                        "test": 21}

        await reg.set_properties(update_props)

        # Ensure that reserved properties have been kept
        assert await ref.get_property(pelix.constants.OBJECTCLASS) == object_class, "Modified objectClass property"

        assert await ref.get_property(pelix.constants.SERVICE_ID) == svc_id, "Modified service ID"

        assert await ref.get_property("test") == 21, "Extra property not updated"

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_get_all_references(self):
        """
        Tests get_all_service_references() method
        """
        # Setup
        test_bundle_name = "tests.framework.service_bundle"
        framework = FrameworkFactory.get_framework()
        await framework.start()

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Get all references count
        all_refs = await context.get_all_service_references(None, None)
        assert all_refs is not None, "All references result must not be None"
        assert len(all_refs) == 0, "Services list should be empty"

        # Install the service bundle
        bundle = await context.install_bundle(test_bundle_name)

        # No services yet
        all_refs = await context.get_all_service_references(None, None)
        assert all_refs is not None, "All references result must not be None"
        assert len(all_refs) == 0, "Services list should be empty"

        # Start the bundle
        await bundle.start()

        all_refs = await context.get_all_service_references(None, None)
        assert all_refs is not None, "All references result must not be None"
        assert len(all_refs) > 0, "Services list shouldn't be empty"

        # Try with an empty filter (lists should be equal)
        all_refs_2 = await context.get_all_service_references(None, "")
        assert all_refs == all_refs_2, "References lists should be equal"

        # Assert that the registered service is in the list
        ref = await context.get_service_reference(IEchoService)
        assert ref is not None, "get_service_reference found nothing"
        assert ref in all_refs, "Echo service should be the complete list"

        # Remove the bundle
        await bundle.uninstall()

        # Test an invalid filter
        with pytest.raises(BundleException):
            await context.get_all_service_references(None, "/// Invalid Filter ///")

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_multiple_unregistrations(self):
        """
        Tests behavior when unregistering the same service twice
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register a dummy service
        registration = await context.register_service("test", self, None, False)

        # Unregister it twice
        await registration.unregister()
        with pytest.raises(BundleException):
            await registration.unregister()

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_invalid_get_service(self):
        """
        Tests behavior when using get_service on an invalid service
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register a dummy service
        registration = await context.register_service("test", self, None, False)

        # Get the reference
        reference = registration.get_reference()

        # Unregister the service
        await registration.unregister()

        # Try to get it
        with pytest.raises(BundleException):
            await context.get_service(reference)

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_auto_release(self):
        """
        Tests auto-release of a simple service
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        # Register a service for the framework
        context_fw = framework.get_bundle_context()
        svc_reg = await context_fw.register_service("test.cleanup", object(), {})
        svc_ref = svc_reg.get_reference()

        # Start a dummy bundle for its context
        bnd = await context_fw.install_bundle("tests.dummy_1")
        await bnd.start()
        ctx = bnd.get_bundle_context()

        # Consume the service
        svc = await ctx.get_service(svc_ref)
        assert svc is not None
        assert bnd in await svc_ref.get_using_bundles()

        # Stop the bundle
        await bnd.stop()

        # Ensure the release of the service
        assert bnd not in await svc_ref.get_using_bundles()

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)
