#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the component life cycle

:author: Thomas Calmant
"""

# Tests
from tests.ipopo import install_bundle, install_ipopo

# Pelix
from pelix.framework import FrameworkFactory

# iPOPO
from pelix.ipopo.constants import IPopoEvent
import pelix.ipopo.constants as constants

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

NAME_A = "componentA"
NAME_B = "componentB"

# ------------------------------------------------------------------------------


class LifeCycleTest(unittest.TestCase):
    """
    Tests the component life cycle
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.module = install_bundle(self.framework)

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)

    def testSingleNormal(self):
        """
        Test a single component life cycle
        """
        # Assert it is not yet in the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A),
                         "Instance is already in the registry")

        # Instantiate the component
        compoA = self.ipopo.instantiate(self.module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A),
                        "Instance is not in the registry")

        # Invalidate the component
        self.ipopo.invalidate(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Assert it is still in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A),
                        "Instance is not in the registry")

        # Kill (remove) the component
        self.ipopo.kill(NAME_A)

        # No event
        self.assertEqual([], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))

        # Assert it has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A),
                         "Instance is still in the registry")

    def testSingleKill(self):
        """
        Test a single component life cycle
        """
        # Assert it is not yet in the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A),
                         "Instance is already in the registry")

        # Instantiate the component
        compoA = self.ipopo.instantiate(self.module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A),
                        "Instance is not in the registry")

        # Kill the component without invalidating it
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Assert it has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A),
                         "Instance is still in the registry")

    def testAutoRestart(self):
        """
        Tests the automatic re-instantiation of a component on bundle update
        """
        # Instantiate both kinds of components
        self.ipopo.instantiate(self.module.FACTORY_A, NAME_A,
                               {constants.IPOPO_AUTO_RESTART: True})

        self.ipopo.instantiate(self.module.FACTORY_B, NAME_B,
                               {constants.IPOPO_AUTO_RESTART: False})

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A),
                        "Instance A is not in the registry")
        self.assertTrue(self.ipopo.is_registered_instance(NAME_B),
                        "Instance B is not in the registry")

        # Update its bundle
        bundle = self.framework.get_bundle_by_name("tests.ipopo.ipopo_bundle")
        bundle.update()

        # Assert the auto-restart component is still in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A),
                        "Instance A is not in the registry after update")

        # Assert the other one has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_B),
                         "Instance B is still in the registry")

        # Clean up
        self.ipopo.kill(NAME_A)

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
