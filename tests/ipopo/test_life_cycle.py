#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the component life cycle

:author: Thomas Calmant
"""

import unittest

import pelix.ipopo.constants as constants
import pelix.ipopo.decorators as decorators
from pelix.framework import FrameworkFactory
from pelix.ipopo.constants import IPopoEvent
from pelix.ipopo.instance import StoredInstance
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

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
        FrameworkFactory.delete_framework()

    def testSingleNormal(self):
        """
        Test a single component life cycle
        """
        # Assert it is not yet in the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A), "Instance is already in the registry")

        # Instantiate the component
        compoA = self.ipopo.instantiate(self.module.FACTORY_A, NAME_A)
        self.assertEqual(
            [IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
            compoA.states,
            "Invalid component states: {0}".format(compoA.states),
        )
        compoA.reset()

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A), "Instance is not in the registry")

        # Invalidate the component
        self.ipopo.invalidate(NAME_A)
        self.assertEqual(
            [IPopoEvent.INVALIDATED], compoA.states, "Invalid component states: {0}".format(compoA.states)
        )
        compoA.reset()

        # Assert it is still in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A), "Instance is not in the registry")

        # Kill (remove) the component
        self.ipopo.kill(NAME_A)

        # No event
        self.assertEqual([], compoA.states, "Invalid component states: {0}".format(compoA.states))

        # Assert it has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A), "Instance is still in the registry")

    def testSingleKill(self):
        """
        Test a single component life cycle
        """
        # Assert it is not yet in the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A), "Instance is already in the registry")

        # Instantiate the component
        compoA = self.ipopo.instantiate(self.module.FACTORY_A, NAME_A)
        self.assertEqual(
            [IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
            compoA.states,
            "Invalid component states: {0}".format(compoA.states),
        )
        compoA.reset()

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A), "Instance is not in the registry")

        # Kill the component without invalidating it
        self.ipopo.kill(NAME_A)
        self.assertEqual(
            [IPopoEvent.INVALIDATED], compoA.states, "Invalid component states: {0}".format(compoA.states)
        )
        compoA.reset()

        # Assert it has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A), "Instance is still in the registry")

    def testAutoRestart(self):
        """
        Tests the automatic re-instantiation of a component on bundle update
        """
        # Instantiate both kinds of components
        self.ipopo.instantiate(self.module.FACTORY_A, NAME_A, {constants.IPOPO_AUTO_RESTART: True})

        self.ipopo.instantiate(self.module.FACTORY_B, NAME_B, {constants.IPOPO_AUTO_RESTART: False})

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A), "Instance A is not in the registry")
        self.assertTrue(self.ipopo.is_registered_instance(NAME_B), "Instance B is not in the registry")

        # Update its bundle
        bundle = self.framework.get_bundle_by_name("tests.ipopo.ipopo_bundle")
        bundle.update()

        # Assert the auto-restart component is still in the registry
        self.assertTrue(
            self.ipopo.is_registered_instance(NAME_A), "Instance A is not in the registry after update"
        )

        # Assert the other one has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_B), "Instance B is still in the registry")

        # Clean up
        self.ipopo.kill(NAME_A)

    def testSingleton(self):
        """
        Tests singleton factory handling
        """
        factory_name = "singleton-factory"
        name_a = "singleton.A"
        name_b = "singleton.B"

        @decorators.SingletonFactory(factory_name)
        class Singleton(object):
            pass

        # Register factory
        self.ipopo.register_factory(self.framework.get_bundle_context(), Singleton)

        # Instantiate once
        self.ipopo.instantiate(factory_name, name_a, {})

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(name_a), "Instance A is not in the registry")

        # Try instantiate twice
        self.assertRaises(ValueError, self.ipopo.instantiate, factory_name, name_b, {})
        self.assertFalse(self.ipopo.is_registered_instance(name_b), "Instance B is in the registry")

        # Kill the instance
        self.ipopo.kill(name_a)
        self.assertFalse(self.ipopo.is_registered_instance(name_a), "Instance A is still in the registry")

        # Re-instantiate with same name and different name
        for name in (name_a, name_b):
            self.ipopo.instantiate(factory_name, name, {})
            self.assertTrue(self.ipopo.is_registered_instance(name), "Instance is not in the registry")

            # Kill the instance
            self.ipopo.kill(name)
            self.assertFalse(self.ipopo.is_registered_instance(name), "Instance is still in the registry")

    def testErroneous(self):
        """
        Tests the handling of erroneous components
        """
        # The method must raise an error if the component is unknown
        self.assertRaises(ValueError, self.ipopo.retry_erroneous, NAME_A)

        # Instantiate an erroneous component
        component = self.ipopo.instantiate(self.module.FACTORY_ERRONEOUS, NAME_A, {})

        # Assert it failed
        self.assertEqual(self.ipopo.get_instance_details(NAME_A)["state"], StoredInstance.ERRONEOUS)

        # => invalidate() must have been called
        self.assertEqual(component.states, [IPopoEvent.INSTANTIATED, IPopoEvent.INVALIDATED])
        component.reset()

        # Retry immediately
        new_state = self.ipopo.retry_erroneous(NAME_A)
        self.assertEqual(new_state, StoredInstance.ERRONEOUS)
        self.assertEqual(self.ipopo.get_instance_details(NAME_A)["state"], StoredInstance.ERRONEOUS)
        self.assertEqual(component.states, [IPopoEvent.INVALIDATED])
        component.reset()

        # Remove exception
        component.raise_exception = False

        # Retry immediately
        new_state = self.ipopo.retry_erroneous(NAME_A)
        self.assertEqual(new_state, StoredInstance.VALID)
        self.assertEqual(self.ipopo.get_instance_details(NAME_A)["state"], StoredInstance.VALID)
        self.assertEqual(component.states, [IPopoEvent.VALIDATED])
        component.reset()

        # Retry when valid => should not call validate again
        new_state = self.ipopo.retry_erroneous(NAME_A)
        self.assertEqual(new_state, StoredInstance.VALID)
        self.assertEqual(self.ipopo.get_instance_details(NAME_A)["state"], StoredInstance.VALID)
        self.assertEqual(component.states, [])

        # Kill instance
        self.ipopo.kill(NAME_A)

    def testErroneousProperty(self):
        """
        Tests the handling of erroneous components when updating properties
        """
        # Instantiate an erroneous component
        component = self.ipopo.instantiate(self.module.FACTORY_ERRONEOUS, NAME_A, {"erroneous": True})

        # Assert it failed
        self.assertEqual(self.ipopo.get_instance_details(NAME_A)["state"], StoredInstance.ERRONEOUS)

        # => invalidate() must have been called
        self.assertEqual(component.states, [IPopoEvent.INSTANTIATED, IPopoEvent.INVALIDATED])
        component.reset()

        # Retry with the new state
        new_state = self.ipopo.retry_erroneous(NAME_A, {"erroneous": False})
        self.assertEqual(new_state, StoredInstance.VALID)
        self.assertEqual(self.ipopo.get_instance_details(NAME_A)["state"], StoredInstance.VALID)
        self.assertEqual(component.states, [IPopoEvent.VALIDATED])
        component.reset()

        # Kill instance
        self.ipopo.kill(NAME_A)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
