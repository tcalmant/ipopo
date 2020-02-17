#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Pelix framework test module. Tests the framework, bundles handling, service
handling and events.

:author: Thomas Calmant, Angelo Cutaia
"""

# Standard library
import os
import pytest

# Pelix
from pelix.framework import FrameworkFactory

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class TestServices:
    """
    Pelix services registry tests
    """
    @pytest.mark.asyncio
    async def test_factory(self):
        """
        Tests the basic behaviour of a service factory
        """
        # Setup
        test_bundle_name = "tests.framework.service_factory_bundle"
        framework = FrameworkFactory.get_framework()
        await framework.start()

        context_fw = framework.get_bundle_context()
        id_fw = (await context_fw.get_bundle()).get_bundle_id()

        # Install the bundle providing a service factory
        factory_bundle = await context_fw.install_bundle(test_bundle_name)
        factory_module = factory_bundle.get_module()
        await factory_bundle.start()

        # Install another harmless bundle, to have two different contexts
        bundle_a = await context_fw.install_bundle(
            "tests.framework.simple_bundle")
        await bundle_a.start()
        context_a = bundle_a.get_bundle_context()
        id_a = (await context_a.get_bundle()).get_bundle_id()

        # Find the service
        svc_ref = context_fw.get_service_reference(factory_module.SVC)

        # Get the service from the Framework context
        svc_fw = context_fw.get_service(svc_ref)
        assert svc_fw.requester_id() == (await context_fw.get_bundle()).get_bundle_id()
        assert factory_module.FACTORY.made_for == [id_fw]

        # Get the service from the bundle context
        svc_a = context_a.get_service(svc_ref)
        assert svc_a.requester_id() == id_a, "Bad request bundle ID"
        assert factory_module.FACTORY.made_for == [id_fw, id_a]

        # Get the service twice
        svc_b = context_a.get_service(svc_ref)
        assert svc_b.requester_id() == id_a, "Bad request bundle ID"

        # Ensure per-bundle variety
        assert factory_module.FACTORY.made_for == [id_fw, id_a]
        assert svc_a is svc_b, "Got different instances for a bundle"
        assert svc_a is not svc_fw, "Got the same instance for two bundles"

        # Release the service:
        # the framework reference must be clean immediately
        context_fw.unget_service(svc_ref)
        assert factory_module.FACTORY.made_for == [id_a]

        # First release of second bundle: no change
        context_a.unget_service(svc_ref)
        assert factory_module.FACTORY.made_for == [id_a]

        # All references of second bundle gone: factory must have been notified
        context_a.unget_service(svc_ref)
        assert factory_module.FACTORY.made_for == []

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """
        Tests the behavior of the framework when cleaning up a bundle
        """
        # Setup
        test_bundle_name = "tests.framework.service_factory_bundle"
        framework = FrameworkFactory.get_framework()
        await framework.start()

        ctx = framework.get_bundle_context()

        # Install the bundle providing a service factory
        factory_bundle = await ctx.install_bundle(test_bundle_name)
        factory_module = factory_bundle.get_module()
        await factory_bundle.start()

        assert os.environ.get("factory.get") is None
        assert os.environ.get("factory.unget") is None

        # Find the service
        svc_ref = ctx.get_service_reference(factory_module.SVC_NO_CLEAN)

        # Get the service from the Framework context
        svc = ctx.get_service(svc_ref)

        assert os.environ.get("factory.get") == "OK"
        assert os.environ.get("factory.unget") is None

        # Check if we got the registration correctly
        assert svc.real is svc.given
        assert svc_ref.get_using_bundles() == [framework]
        assert svc.real.get_reference() == svc_ref, "Wrong reference"

        # Clean up environment
        del os.environ['factory.get']

        # Uninstall the bundle
        await factory_bundle.uninstall()

        assert os.environ.get("factory.get") is None
        assert os.environ.get("factory.unget") == "OK"

        # Clean up environment
        os.environ.pop('factory.get', None)
        del os.environ['factory.unget']

        # Check clean up
        assert svc.real is svc.given
        assert svc_ref.get_using_bundles() == []

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_auto_release(self):
        """
        Tests auto-release of a service factory
        """
        # Setup
        test_bundle_name = "tests.framework.service_factory_bundle"
        framework = FrameworkFactory.get_framework()
        await framework.start()

        # Register a service for the framework
        context_fw = framework.get_bundle_context()

        # Install the bundle providing a service factory
        factory_bundle = await context_fw.install_bundle(test_bundle_name)
        factory_module = factory_bundle.get_module()
        await factory_bundle.start()

        # Find the service
        svc_ref = context_fw.get_service_reference(factory_module.SVC)

        # Start a dummy bundle for its context
        bnd = await context_fw.install_bundle("tests.dummy_1")
        await bnd.start()
        ctx = bnd.get_bundle_context()

        # Consume the service
        svc = ctx.get_service(svc_ref)
        assert svc is not None
        assert bnd in svc_ref.get_using_bundles()

        # Stop the bundle
        await bnd.stop()

        # Ensure the release of the service
        assert bnd not in svc_ref.get_using_bundles()

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()


if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)
