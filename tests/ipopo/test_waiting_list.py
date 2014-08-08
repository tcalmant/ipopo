#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO waiting list service

:author: Thomas Calmant
"""

# Tests
from tests.ipopo import install_bundle, install_ipopo

# Pelix
from pelix.framework import FrameworkFactory

# iPOPO
import pelix.ipopo.constants as constants

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

NAME_A = "componentA"
FACTORY_A = "ipopo.tests.a"

# ------------------------------------------------------------------------------


class WaitingListTest(unittest.TestCase):
    """
    Tests the iPOPO waiting list service
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        # Prepare the framework
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        context = self.framework.get_bundle_context()

        # Install & start the waiting list bundle
        install_bundle(self.framework, "pelix.ipopo.waiting")

        # Get the service
        svc_ref = context.get_service_reference(
            constants.SERVICE_IPOPO_WAITING_LIST)
        self.waiting = context.get_service(svc_ref)

    def tearDown(self):
        """
        Called after each test
        """
        # Destroy the framework
        FrameworkFactory.delete_framework(self.framework)
        self.framework = None
        self.waiting = None

    def testAddRemove(self):
        """
        The waiting list must raise an error if we try to instantiate two
        components with the same name
        """
        # Store the component
        self.waiting.add("some.factory", "some.instance", {})

        # Same name & factory
        self.assertRaises(ValueError, self.waiting.add,
                          "some.factory", "some.instance", {})

        # Same name, different factory
        self.assertRaises(ValueError, self.waiting.add,
                          "some.other.factory", "some.instance", {})

        # Remove it
        self.waiting.remove("some.instance")

        # Remove it twice
        self.assertRaises(KeyError, self.waiting.remove, "some.instance")

        # Re-add it
        self.waiting.add("some.factory", "some.instance", {})

    def testInstantiateKillBeforeIPopo(self):
        """
        Tests if the component is correctly instantiated when added and killed
        when removed
        """
        # Add the component to the waiting list
        self.waiting.add(FACTORY_A, NAME_A)

        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # The component must be absent
        self.assertFalse(ipopo.is_registered_instance(NAME_A),
                         "Instance already there")

        # Install the component bundle
        install_bundle(self.framework)

        # The instance must have been started
        self.assertTrue(ipopo.is_registered_instance(NAME_A),
                        "Instance not there")

        # Remove the component from the waiting list
        self.waiting.remove(NAME_A)

        # The instance must have been kill
        self.assertFalse(ipopo.is_registered_instance(NAME_A),
                         "Instance still there")

    def testInstantiateKillAfterIPopoBeforeBundle(self):
        """
        Tests if the component is correctly instantiated when added and killed
        when removed
        """
        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # Add the component to the waiting list
        self.waiting.add(FACTORY_A, NAME_A)

        # The component must be absent
        self.assertFalse(ipopo.is_registered_instance(NAME_A),
                         "Instance already there")

        # Install the component bundle
        install_bundle(self.framework)

        # The instance must have been started
        self.assertTrue(ipopo.is_registered_instance(NAME_A),
                        "Instance not there")

        # Remove the component from the waiting list
        self.waiting.remove(NAME_A)

        # The instance must have been kill
        self.assertFalse(ipopo.is_registered_instance(NAME_A),
                         "Instance still there")

    def testInstantiateKillAfterIPopoAfterBundle(self):
        """
        Tests if the component is correctly instantiated when added and killed
        when removed
        """
        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # Install the component bundle
        install_bundle(self.framework)

        # The component must be absent
        self.assertFalse(ipopo.is_registered_instance(NAME_A),
                         "Instance already there")

        # Add the component to the waiting list
        self.waiting.add(FACTORY_A, NAME_A)

        # The instance must have been started
        self.assertTrue(ipopo.is_registered_instance(NAME_A),
                        "Instance not there")

        # Remove the component from the waiting list
        self.waiting.remove(NAME_A)

        # The instance must have been kill
        self.assertFalse(ipopo.is_registered_instance(NAME_A),
                         "Instance still there")

    def testInstantiateConflict(self):
        """
        Try to instantiate a component with a name already used
        """
        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # Install the component bundle
        module = install_bundle(self.framework)

        # The component must be present
        self.assertTrue(ipopo.is_registered_instance(module.BASIC_INSTANCE),
                        "Auto-instance not yet there")

        # This addition must not fail, but must be logger
        self.waiting.add(module.BASIC_FACTORY, module.BASIC_INSTANCE)

        # The original instance must still be there
        self.assertTrue(ipopo.is_registered_instance(module.BASIC_INSTANCE),
                        "Instance has been killed")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
