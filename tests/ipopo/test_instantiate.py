#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @Instantiate decorator.

:author: Thomas Calmant
"""

import unittest

from pelix.framework import BundleEvent, FrameworkFactory
from pelix.ipopo.constants import IPopoEvent
from tests.ipopo import install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

NAME_A = "componentA"

# ------------------------------------------------------------------------------


class InstantiateTest(unittest.TestCase):
    """
    Specific test case to test @Instantiate, as it needs a pure framework
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
        FrameworkFactory.delete_framework()

        # Clean up
        self.ipopo = None
        self.framework = None

    def testInstantiate(self):
        """
        Tests the life cycle with an @Instantiate decorator
        """
        factory = "basic-component-factory"
        name = "basic-component"
        svc_spec = "basic-component-svc"

        # Assert the framework is clean
        self.assertFalse(self.ipopo.is_registered_factory(factory), "Factory already registered")

        self.assertFalse(self.ipopo.is_registered_instance(name), "Instance already registered")

        # Install the bundle
        context = self.framework.get_bundle_context()
        bundle = context.install_bundle("tests.ipopo.ipopo_bundle")

        # Bundle is installed, assert that the framework is still clean
        self.assertFalse(
            self.ipopo.is_registered_factory(factory), "Factory registered while the bundle is stopped"
        )

        self.assertFalse(
            self.ipopo.is_registered_instance(name), "Instance registered while the bundle is stopped"
        )

        # Start the bundle
        bundle.start()

        # Assert the component has been registered
        self.assertTrue(
            self.ipopo.is_registered_factory(factory), "Factory not registered while the bundle is started"
        )

        self.assertTrue(
            self.ipopo.is_registered_instance(name), "Instance not registered while the bundle is started"
        )

        # Assert it has been validated
        ref = context.get_service_reference(svc_spec)
        self.assertIsNotNone(ref, "No reference found (component not validated)")

        compo = context.get_service(ref)

        self.assertEqual(
            compo.states,
            [IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
            "@Instantiate component should have been validated",
        )
        del compo.states[:]

        # Stop the bundle
        bundle.stop()

        # Assert the component has been invalidated
        self.assertEqual(
            compo.states, [IPopoEvent.INVALIDATED], "@Instantiate component should have been invalidated"
        )

        # Assert the framework has been cleaned up
        self.assertFalse(
            self.ipopo.is_registered_factory(factory), "Factory registered while the bundle has been stopped"
        )

        self.assertFalse(
            self.ipopo.is_registered_instance(name),
            "Instance registered while the bundle has been " "stopped",
        )

        # Ensure the service has been unregistered properly
        self.assertIsNone(context.get_service_reference(svc_spec), "@Instantiate service is still there")

    def testNotRunning(self):
        """
        Checks that the instantiation is refused when iPOPO is stopped
        """
        # Stop the framework
        self.framework.stop()

        # iPOPO shouldn't be accessible, it must raise an exception
        self.assertRaises(ValueError, self.ipopo.instantiate, "dummy", "dummy", {})

    def test_boot_order(self):
        """
        Tests when the @Validate and @Invalidate methods are called
        """
        # Install the bundle
        context = self.framework.get_bundle_context()
        bundle = context.install_bundle("tests.ipopo.ipopo_boot_order_bundle")
        module = bundle.get_module()

        # Clean up state
        del module.STATES[:]

        # Start the bundle
        bundle.start()

        # Check states
        self.assertListEqual(
            [BundleEvent.STARTED, IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED], module.STATES
        )

        # Clean up
        del module.STATES[:]

        # Stop the bundle
        bundle.stop()

        # Check states
        self.assertListEqual([IPopoEvent.INVALIDATED, BundleEvent.STOPPED], module.STATES)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
