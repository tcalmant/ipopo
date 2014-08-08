#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the component requirements behavior

:author: Thomas Calmant
"""

# Tests
from tests import log_on, log_off
from tests.interfaces import IEchoService
from tests.ipopo import install_bundle, install_ipopo

# Pelix
from pelix.framework import FrameworkFactory, Bundle

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
NAME_C = "componentC"

# ------------------------------------------------------------------------------


class RequirementTest(unittest.TestCase):
    """
    Tests the component requirements behavior
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

    def testCycleInner(self):
        """
        Tests if the component is bound, validated then invalidated.
        The component unbind call must come after it has been killed
        """
        module = install_bundle(self.framework)

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Instantiate B (bound then validated)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.BOUND,
                          IPopoEvent.VALIDATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Invalidate B
        self.ipopo.invalidate(NAME_B)
        self.assertEqual([IPopoEvent.INVALIDATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Uninstantiate B
        self.ipopo.kill(NAME_B)
        self.assertEqual([IPopoEvent.UNBOUND], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))

        # Uninstantiate A
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))

    def testCycleOuterEnd(self):
        """
        Tests if the required service is correctly unbound after the component
        invalidation
        """
        module = install_bundle(self.framework)

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Instantiate B (bound then validated)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.BOUND,
                          IPopoEvent.VALIDATED], compoB.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoB.reset()

        # Uninstantiate A
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))

        self.assertEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Uninstantiate B
        self.ipopo.kill(NAME_B)
        self.assertEqual([], compoB.states,
                         "Invalid component states: {0}".format(compoA.states))

    def testCycleOuterStart(self):
        """
        Tests if the required service is correctly bound after the component
        instantiation
        """
        module = install_bundle(self.framework)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # B must have been validated
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Invalidate B
        self.ipopo.invalidate(NAME_B)
        self.assertEqual([IPopoEvent.INVALIDATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Uninstantiate B
        self.ipopo.kill(NAME_B)
        self.assertEqual([IPopoEvent.UNBOUND], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))

        # Uninstantiate A
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))

    def testConfiguredInstance(self):
        """
        Tests if the filter can be overridden by instance properties
        """
        module = install_bundle(self.framework)

        # The module filter
        properties_b = {constants.IPOPO_REQUIRES_FILTERS:
                        {"service": "({0}=True)".format(module.PROP_USABLE)}}

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        # Set A unusable
        compoA.change(False)

        # Instantiate B (must not be bound)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B,
                                        properties_b)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Set A usable
        compoA.change(True)

        # B must be bound and validated
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Set A unusable (again)
        compoA.change(False)

        # B must have been invalidated
        self.assertEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))

    def testAggregateDependency(self):
        """
        Tests a component that aggregates dependencies
        """
        # Install the test bundle
        module = install_bundle(self.framework)

        # Instantiate C (no requirement present, but they are optional)
        compoC = self.ipopo.instantiate(module.FACTORY_C, NAME_C)
        self.assertIsNone(compoC.services,
                          "Aggregate dependency without value must be None")
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Register a first service
        context = self.framework.get_bundle_context()
        reg = context.register_service(IEchoService, self, None)

        # The dependency must be injected
        self.assertIn(self, compoC.services, "Service not injected")
        self.assertEqual([IPopoEvent.BOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Instantiate A
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        # The dependency must be injected
        self.assertIn(self, compoC.services, "Service illegally removed")
        self.assertIn(compoA, compoC.services, "Service not injected")
        self.assertEqual([IPopoEvent.BOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Delete A
        self.ipopo.kill(NAME_A)

        # The dependency must have been removed
        self.assertNotIn(compoA, compoC.services, "Service not removed")
        self.assertIn(self, compoC.services, "Service illegally removed")
        self.assertEqual([IPopoEvent.UNBOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Instantiate A
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        self.assertIn(self, compoC.services, "Service illegally removed")
        self.assertIn(compoA, compoC.services, "Service not injected")
        self.assertEqual([IPopoEvent.BOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Unregister the first service
        reg.unregister()

        # The dependency must have been removed
        self.assertNotIn(self, compoC.services, "Service not removed")
        self.assertIn(compoA, compoC.services, "Service illegally removed")
        self.assertEqual([IPopoEvent.UNBOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Delete A
        self.ipopo.kill(NAME_A)

        # The dependency must have been removed
        self.assertIsNone(compoC.services,
                          "Aggregate dependency without value must be None")
        self.assertEqual([IPopoEvent.UNBOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Delete C
        self.ipopo.kill(NAME_C)
        self.assertEqual([IPopoEvent.INVALIDATED], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))

    def testAggregateDependencyLate(self):
        """
        Tests a component that aggregates dependencies, with one dependency
        already present before its instantiation
        """
        # Install the test bundle
        module = install_bundle(self.framework)

        # Register a first service
        context = self.framework.get_bundle_context()
        context.register_service(IEchoService, self, None)

        # Instantiate C (no requirement present, but they are optional)
        compoC = self.ipopo.instantiate(module.FACTORY_C, NAME_C)
        self.assertIn(self, compoC.services,
                      "Existing service not injected")
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.BOUND,
                          IPopoEvent.VALIDATED], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))

    def testCallbackRaiser(self):
        """
        Tests exception handling during a callback
        """
        module = install_bundle(self.framework)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Set B in raiser mode
        compoB.raiser = True

        # Instantiate A (validated)
        log_off()
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        log_on()

        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # B must have been validated
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Uninstantiate A
        log_off()
        self.ipopo.kill(NAME_A)
        log_on()

        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))

        # Uninstantiate B
        self.assertEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))

    def testCallbackInstantiateStopper(self):
        """
        Tests exception handling during a callback
        """
        module = install_bundle(self.framework)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Set B in raiser mode
        compoB.fw_raiser = True
        compoB.fw_raiser_stop = False

        # Instantiate A (validated)
        log_off()
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        log_on()

        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # B must have failed to start
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.UNBOUND],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Framework must still be active
        self.assertEqual(self.framework.get_state(), Bundle.ACTIVE,
                         "Framework has stopped")

        # B must have been automatically killed
        instances = [info[0] for info in self.ipopo.get_instances()]
        self.assertIn(NAME_A, instances, "Component A should still be there")
        self.assertNotIn(NAME_B, instances, "Component B still in instances")

        # Kill A
        self.ipopo.kill(NAME_A)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Set B in raiser mode
        compoB.fw_raiser = True
        compoB.fw_raiser_stop = True

        # Instantiate A (validated)
        log_off()
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        log_on()

        # Framework must have stopped now
        self.assertEqual(self.framework.get_state(), Bundle.RESOLVED,
                         "Framework hasn't stopped")

    def testRequiresMap(self):
        """
        Tests the behavior of RequiresMap
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()

        # Instantiate "map" component
        compo = self.ipopo.instantiate(module.FACTORY_MAP, "map.component")
        self.assertListEqual([IPopoEvent.INSTANTIATED], compo.states,
                             "Component not instantiated...")
        compo.reset()

        # Add a service, with no property
        svc1 = object()
        reg1 = context.register_service(module.MAP_SPEC_TEST, svc1, {})

        # Check insertion in dictionaries accepting None
        self.assertDictEqual({}, compo.single, "Injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({None: svc1}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1]}, compo.multiple_none,
                             "Not injected in multiple_none")

        # Check state
        self.assertListEqual([], compo.states, "Component validated...")
        compo.reset()

        # Add a service, with property for "single"
        svc2 = object()
        value2 = 42
        reg2 = context.register_service(module.MAP_SPEC_TEST, svc2,
                                        {"single.key": value2})

        # Check state
        self.assertListEqual([IPopoEvent.VALIDATED], compo.states,
                             "Component not validated...")
        compo.reset()

        # Check insertion in dictionaries "single"
        self.assertDictEqual({value2: svc2}, compo.single,
                             "Not injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({None: svc1, value2: svc2}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1, svc2]}, compo.multiple_none,
                             "Not injected in multiple_none")

        # Update the service to be injected in both single and multiple
        value2b = "some test value"
        reg2.set_properties({"single.key": value2, "other.key": value2b})

        # Check insertion in both dictionaries
        self.assertDictEqual({value2: svc2}, compo.single,
                             "Not injected in single")
        self.assertDictEqual({value2b: [svc2]}, compo.multiple,
                             "Not injected in multiple")
        self.assertDictEqual({None: svc1, value2: svc2}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1], value2b: [svc2]},
                             compo.multiple_none,
                             "Not injected in multiple_none")

        # Remove the "other key"
        reg2.set_properties({"other.key": None})

        # Check removal in dictionaries "multiple"
        self.assertDictEqual({value2: svc2}, compo.single,
                             "Not injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({None: svc1, value2: svc2}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1, svc2]}, compo.multiple_none,
                             "Injected in multiple_none")

        # Remove the "single key"
        reg2.set_properties({"single.key": None})

        # Check state
        self.assertListEqual([IPopoEvent.INVALIDATED], compo.states,
                             "Component not invalidated...")
        compo.reset()

        self.assertDictEqual({}, compo.single, "Injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({None: svc1}, compo.single_none,
                             "Replacement in single_none")
        self.assertDictEqual({None: [svc1, svc2]}, compo.multiple_none,
                             "Not injected in multiple_none")

        # Unregister service
        reg2.unregister()

        self.assertDictEqual({}, compo.single, "Injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({None: svc1}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1]}, compo.multiple_none,
                             "Not injected in multiple_none")

        # Update service 1 properties
        value1 = ("why", "not", "use", "tuple")
        reg1.set_properties({"single.key": value1})

        # Check state
        self.assertListEqual([IPopoEvent.VALIDATED], compo.states,
                             "Component not validated...")
        compo.reset()

        self.assertDictEqual({value1: svc1}, compo.single,
                             "Not injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({value1: svc1}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1]}, compo.multiple_none,
                             "Injected in multiple_none")

        # Remove components
        reg1.unregister()

        # Check state
        self.assertListEqual([IPopoEvent.INVALIDATED], compo.states,
                             "Component not invalidated...")
        compo.reset()

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
