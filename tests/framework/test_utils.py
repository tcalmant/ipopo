#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Tests the framework utility methods.

:author: Thomas Calmant, Angelo Cutaia
"""

# Standard library
import pytest

# Pelix
from pelix.framework import FrameworkFactory
import pelix.framework as pelix


# ------------------------------------------------------------------------------

__version__ = "1.0.0"

SERVICE_BUNDLE = "tests.framework.service_bundle"

# ------------------------------------------------------------------------------


class TestUtilityMethods:
    """
    Pelix utility methods tests
    """
    @pytest.mark.asyncio
    async def test_create_framework_basic(self):
        """
        Tests create_framework(), without parameters
        -> creates an empty framework, and doesn't start it
        """
        #Setup
        framework = await pelix.create_framework([])
        assert framework.get_state() == pelix.Bundle.RESOLVED, 'Framework has been started'
        assert await framework.get_bundles() == [], 'Framework is not empty'

        # Try to start two framework
        with pytest.raises(ValueError):
            await pelix.create_framework([])

        #Teardown
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_create_framework_bundles(self):
        """
        Tests create_framework(), with specified bundles
        """
        #Setup
        test_bundle_name = SERVICE_BUNDLE
        framework = await pelix.create_framework([test_bundle_name])

        assert framework.get_state() == pelix.Bundle.RESOLVED, 'Framework has been started'

        assert len(await framework.get_bundles()) == 1, 'Framework should only have 1 bundle'

        bundle = await framework.get_bundle_by_id(1)
        assert bundle.get_symbolic_name() == test_bundle_name, "The test bundle hasn't been installed correctly"

        #Teardown
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_create_framework_start(self):
        """
        Tests create_framework(), with specified bundles and auto-start
        """
        #Setup
        test_bundle_name = SERVICE_BUNDLE

        # Without bundles
        framework = await pelix.create_framework([], auto_start=True)
        assert framework.get_state() == pelix.Bundle.ACTIVE, "Framework hasn't been started"

        assert await framework.get_bundles() == [], 'Framework is not empty'

        # Clean up
        await FrameworkFactory.delete_framework()

        # With bundles
        framework = await pelix.create_framework([test_bundle_name], auto_start=True)
        assert framework.get_state() == pelix.Bundle.ACTIVE, "Framework hasn't been started"

        assert len(await framework.get_bundles()) == 1, 'Framework should only have 1 bundle'

        bundle = await framework.get_bundle_by_id(1)
        assert bundle.get_symbolic_name() == test_bundle_name, "The test bundle hasn't been installed correctly"
        assert bundle.get_state() == pelix.Bundle.ACTIVE, "Bundle hasn't been started"

        #Teardown
        await FrameworkFactory.delete_framework()

# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)
