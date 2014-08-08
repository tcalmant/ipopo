#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @Instantiate decorator.

:author: Thomas Calmant
"""

# Tests
from tests.ipopo import install_ipopo

# Pelix
from pelix.framework import FrameworkFactory

# iPOPO
from pelix.ipopo.constants import IPopoEvent

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

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
        FrameworkFactory.delete_framework(self.framework)

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
        self.assertFalse(self.ipopo.is_registered_factory(factory),
                         "Factory already registered")

        self.assertFalse(self.ipopo.is_registered_instance(name),
                         "Instance already registered")

        # Install the bundle
        context = self.framework.get_bundle_context()
        bundle = context.install_bundle("tests.ipopo.ipopo_bundle")

        # Bundle is installed, assert that the framework is still clean
        self.assertFalse(self.ipopo.is_registered_factory(factory),
                         "Factory registered while the bundle is stopped")

        self.assertFalse(self.ipopo.is_registered_instance(name),
                         "Instance registered while the bundle is stopped")

        # Start the bundle
        bundle.start()

        # Assert the component has been registered
        self.assertTrue(self.ipopo.is_registered_factory(factory),
                        "Factory not registered while the bundle is started")

        self.assertTrue(self.ipopo.is_registered_instance(name),
                        "Instance not registered while the bundle is started")

        # Assert it has been validated
        ref = context.get_service_reference(svc_spec)
        self.assertIsNotNone(ref,
                             "No reference found (component not validated)")

        compo = context.get_service(ref)

        self.assertEqual(compo.states, [IPopoEvent.INSTANTIATED,
                                        IPopoEvent.VALIDATED],
                         "@Instantiate component should have been validated")
        del compo.states[:]

        # Stop the bundle
        bundle.stop()

        # Assert the component has been invalidated
        self.assertEqual(compo.states, [IPopoEvent.INVALIDATED],
                         "@Instantiate component should have been invalidated")

        # Assert the framework has been cleaned up
        self.assertFalse(
            self.ipopo.is_registered_factory(factory),
            "Factory registered while the bundle has been stopped")

        self.assertFalse(self.ipopo.is_registered_instance(name),
                         "Instance registered while the bundle has been "
                         "stopped")

        # Ensure the service has been unregistered properly
        self.assertIsNone(context.get_service_reference(svc_spec),
                          "@Instantiate service is still there")

    def testNotRunning(self):
        """
        Checks that the instantiation is refused when iPOPO is stopped
        """
        # Stop the framework
        self.framework.stop()

        # iPOPO shouldn't be accessible, it must raise an exception
        self.assertRaises(ValueError, self.ipopo.instantiate,
                          'dummy', 'dummy', {})

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
