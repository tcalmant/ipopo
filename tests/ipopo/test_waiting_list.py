#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO waiting list service

:author: Thomas Calmant
"""

import unittest

from pelix.framework import FrameworkFactory
from pelix.ipopo import constants
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

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
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        context = self.framework.get_bundle_context()

        # Install & start the waiting list bundle
        install_bundle(self.framework, "pelix.ipopo.waiting")

        # Get the service
        svc_ref = context.get_service_reference(constants.SERVICE_IPOPO_WAITING_LIST)
        assert svc_ref is not None
        self.waiting = context.get_service(svc_ref)

    def tearDown(self):
        """
        Called after each test
        """
        # Destroy the framework
        FrameworkFactory.delete_framework()
        self.framework = None
        self.waiting = None

    def testAddRemove(self):
        """
        The waiting list must raise an error if we try to instantiate two
        components with the same name
        """
        assert self.waiting is not None
        # Store the component
        self.waiting.add("some.factory", "some.instance", {})

        # Same name & factory
        self.assertRaises(ValueError, self.waiting.add, "some.factory", "some.instance", {})

        # Same name, different factory
        self.assertRaises(ValueError, self.waiting.add, "some.other.factory", "some.instance", {})

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
        assert self.framework is not None
        assert self.waiting is not None

        # Add the component to the waiting list
        self.waiting.add(FACTORY_A, NAME_A)

        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # The component must be absent
        self.assertFalse(ipopo.is_registered_instance(NAME_A), "Instance already there")

        # Install the component bundle
        install_bundle(self.framework)

        # The instance must have been started
        self.assertTrue(ipopo.is_registered_instance(NAME_A), "Instance not there")

        # Remove the component from the waiting list
        self.waiting.remove(NAME_A)

        # The instance must have been kill
        self.assertFalse(ipopo.is_registered_instance(NAME_A), "Instance still there")

    def testInstantiateKillAfterIPopoBeforeBundle(self):
        """
        Tests if the component is correctly instantiated when added and killed
        when removed
        """
        assert self.framework is not None
        assert self.waiting is not None

        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # Add the component to the waiting list
        self.waiting.add(FACTORY_A, NAME_A)

        # The component must be absent
        self.assertFalse(ipopo.is_registered_instance(NAME_A), "Instance already there")

        # Install the component bundle
        install_bundle(self.framework)

        # The instance must have been started
        self.assertTrue(ipopo.is_registered_instance(NAME_A), "Instance not there")

        # Remove the component from the waiting list
        self.waiting.remove(NAME_A)

        # The instance must have been kill
        self.assertFalse(ipopo.is_registered_instance(NAME_A), "Instance still there")

    def testInstantiateKillAfterIPopoAfterBundle(self):
        """
        Tests if the component is correctly instantiated when added and killed
        when removed
        """
        assert self.framework is not None
        assert self.waiting is not None

        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # Install the component bundle
        install_bundle(self.framework)

        # The component must be absent
        self.assertFalse(ipopo.is_registered_instance(NAME_A), "Instance already there")

        # Add the component to the waiting list
        self.waiting.add(FACTORY_A, NAME_A)

        # The instance must have been started
        self.assertTrue(ipopo.is_registered_instance(NAME_A), "Instance not there")

        # Remove the component from the waiting list
        self.waiting.remove(NAME_A)

        # The instance must have been kill
        self.assertFalse(ipopo.is_registered_instance(NAME_A), "Instance still there")

    def testInstantiateConflict(self):
        """
        Try to instantiate a component with a name already used
        """
        assert self.framework is not None
        assert self.waiting is not None

        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # Install the component bundle
        module = install_bundle(self.framework)

        # The component must be present
        self.assertTrue(ipopo.is_registered_instance(module.BASIC_INSTANCE), "Auto-instance not yet there")

        # This addition must not fail, but must be logger
        self.waiting.add(module.BASIC_FACTORY, module.BASIC_INSTANCE)

        # The original instance must still be there
        self.assertTrue(ipopo.is_registered_instance(module.BASIC_INSTANCE), "Instance has been killed")

    def testUpdateQueuedComponent(self):
        """
        An update of a queued component must be merged into its properties,
        as it is for a running one
        """
        assert self.framework is not None
        assert self.waiting is not None

        # Add the component to the waiting list, before iPOPO is there
        self.waiting.add(FACTORY_A, NAME_A, {"kept": 1, "changed": 2})

        # Only mention one of the properties
        self.waiting.update(NAME_A, {"changed": 3, "added": 4})

        # Install iPOPO and the component bundle
        ipopo = install_ipopo(self.framework)
        install_bundle(self.framework)

        self.assertTrue(ipopo.is_registered_instance(NAME_A), "Instance not there")

        properties = ipopo.get_instance_details(NAME_A)["properties"]
        self.assertEqual(properties["kept"], "1", "Untouched property has been lost")
        self.assertEqual(properties["changed"], "3", "Property has not been updated")
        self.assertEqual(properties["added"], "4", "Property has not been added")

    def testUpdateRemovedProperties(self):
        """
        The properties named in "removed" must be dropped from the queue, so
        that the factory gives them their declared value again
        """
        assert self.framework is not None
        assert self.waiting is not None

        # Add the component to the waiting list, before iPOPO is there
        self.waiting.add(FACTORY_A, NAME_A, {"kept": 1, "dropped": 2})

        # Drop a property, giving it the value the factory would give it
        self.waiting.update(NAME_A, {"dropped": None}, {"dropped"})

        # Install iPOPO and the component bundle
        ipopo = install_ipopo(self.framework)
        install_bundle(self.framework)

        self.assertTrue(ipopo.is_registered_instance(NAME_A), "Instance not there")

        properties = ipopo.get_instance_properties(NAME_A)
        self.assertEqual(properties["kept"], 1, "Untouched property has been lost")
        self.assertNotIn("dropped", properties, "Property has not been dropped")

    def testUpdateUnknownComponent(self):
        """
        Updating a component which is not in the waiting list must raise a
        KeyError
        """
        assert self.waiting is not None
        self.assertRaises(KeyError, self.waiting.update, NAME_A, {"name": "value"})

    def testUpdateDuringInstantiation(self):
        """
        An update which happens while the component is being instantiated must
        not be lost: its reconfiguration is ignored, as the component is not
        registered yet
        """
        assert self.framework is not None
        assert self.waiting is not None

        # Install iPOPO and the component bundle
        ipopo = install_ipopo(self.framework)
        install_bundle(self.framework)

        waiting = self.waiting
        original_instantiate = ipopo.instantiate

        def racing_instantiate(factory, name, properties=None):
            """
            Updates the queued properties before the component is registered
            """
            # Race only once
            ipopo.instantiate = original_instantiate
            waiting.update(NAME_A, {"changed": 3})
            return original_instantiate(factory, name, properties)

        ipopo.instantiate = racing_instantiate

        self.waiting.add(FACTORY_A, NAME_A, {"kept": 1, "changed": 2})
        self.assertTrue(ipopo.is_registered_instance(NAME_A), "Instance not there")

        properties = ipopo.get_instance_properties(NAME_A)
        self.assertEqual(properties["kept"], 1, "Untouched property has been lost")
        self.assertEqual(properties["changed"], 3, "Concurrent update has been lost")

    def testAddDuringRemoval(self):
        """
        A component queued again while the previous one is being killed must
        stay instantiated
        """
        assert self.framework is not None
        assert self.waiting is not None

        # Install iPOPO and the component bundle
        ipopo = install_ipopo(self.framework)
        install_bundle(self.framework)

        self.waiting.add(FACTORY_A, NAME_A, {})
        self.assertTrue(ipopo.is_registered_instance(NAME_A), "Instance not there")

        waiting = self.waiting
        original_kill = ipopo.kill

        def racing_kill(name):
            """
            Queues the component again before it is killed
            """
            # Race only once
            ipopo.kill = original_kill

            # The component is still running: this add() only queues it back,
            # which is what the removal must take into account
            waiting.add(FACTORY_A, NAME_A, {})
            return original_kill(name)

        ipopo.kill = racing_kill

        self.waiting.remove(NAME_A)
        self.assertTrue(ipopo.is_registered_instance(NAME_A), "Queued component has been killed")


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
