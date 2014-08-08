#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO core service.

:author: Thomas Calmant
"""

# Tests
from tests import log_on, log_off
from tests.ipopo import install_bundle, install_ipopo

# Pelix
from pelix.framework import FrameworkFactory

# iPOPO
from pelix.ipopo.constants import IPopoEvent
import pelix.ipopo.decorators as decorators

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class IPopoServiceTest(unittest.TestCase):
    """
    Tests the utility methods of the iPOPO service
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

    def testFactoriesRegistration(self):
        """
        Tests the (un)register_factory and get_factories behavior
        """
        FACTORY = "dummy-factory"
        context = self.framework.get_bundle_context()

        @decorators.ComponentFactory(FACTORY)
        class TestComponent(object):
            pass

        class UnManipulatedClass(object):
            pass

        # Test if the framework is clean
        factories_1 = self.ipopo.get_factories()
        self.assertEqual(len(factories_1), 0,
                         "Some factories are already registered.")

        self.assertFalse(self.ipopo.is_registered_factory(FACTORY),
                         "Test factory already registered")

        # Test type checking
        self.assertRaises(ValueError, self.ipopo.register_factory, None, None)
        self.assertRaises(ValueError, self.ipopo.register_factory, context,
                          None)
        self.assertRaises(ValueError, self.ipopo.register_factory, None,
                          TestComponent)
        self.assertRaises(TypeError, self.ipopo.register_factory, context,
                          UnManipulatedClass)
        self.assertRaises(TypeError, self.ipopo.register_factory, context,
                          TestComponent())

        self.assertEqual(len(factories_1), 0,
                         "Some factories have already bean registered.")
        self.assertFalse(self.ipopo.is_registered_factory(FACTORY),
                         "Test factory already registered")

        # Register the factory
        self.assertTrue(self.ipopo.register_factory(context, TestComponent))

        self.assertTrue(self.ipopo.is_registered_factory(FACTORY),
                        "Test factory not registered")

        # Can't do it twice
        self.assertRaises(ValueError, self.ipopo.register_factory, context,
                          TestComponent)

        # Test the get_factories method
        factories_2 = self.ipopo.get_factories()
        self.assertIn(FACTORY, factories_2,
                      "Test factory not in get_factories()")

        self.assertIsNot(factories_1, factories_2,
                         "get_factories() must not return the same object")

        # Unregister the factory
        for invalid in (None, "", "Dummy", [FACTORY]):
            self.assertFalse((self.ipopo.unregister_factory(invalid)),
                             "Invalid factory unregistered: {0}"
                             .format(invalid))

        self.assertTrue(self.ipopo.unregister_factory(FACTORY))
        self.assertNotIn(FACTORY, self.ipopo.get_factories(),
                         "Test factory still in get_factories()")

        self.assertFalse(self.ipopo.is_registered_factory(FACTORY),
                         "Test factory still registered")

        # We can do it only once
        self.assertFalse(self.ipopo.unregister_factory(FACTORY))

    def testGetFactoryBundle(self):
        """
        Tests the get_factory_bundle() method
        """
        FACTORY = "dummy-factory"
        context = self.framework.get_bundle_context()

        @decorators.ComponentFactory(FACTORY)
        class TestComponent(object):
            pass

        # We must have a ValueError
        self.assertRaises(ValueError, self.ipopo.get_factory_bundle, FACTORY)

        # Register the factory
        self.ipopo.register_factory(context, TestComponent)

        # Test the factory bundle
        self.assertIs(self.ipopo.get_factory_bundle(FACTORY), self.framework,
                      "Invalid factory bundle")

        # Unregister it
        self.ipopo.unregister_factory(FACTORY)

        # We must have a ValueError
        self.assertRaises(ValueError, self.ipopo.get_factory_bundle, FACTORY)

    def testGetInstanceDetails(self):
        """
        Instance details method test
        """
        module = install_bundle(self.framework)

        # Invalid component names
        for invalid in (None, "", [1], ["a", "b"]):
            self.assertRaises(ValueError, self.ipopo.get_instance_details,
                              invalid)

        # Get its details
        details = self.ipopo.get_instance_details(module.BASIC_INSTANCE)

        # Test if instance details are really in the output
        self.assertIs(type(details), dict,
                      "Details result must be a dictionary")

        self.assertEqual(details['factory'], module.BASIC_FACTORY,
                         "Invalid factory name")
        self.assertEqual(details['name'], module.BASIC_INSTANCE,
                         "Invalid component name")

        self.assertIs(type(details['state']), int,
                      "Component state must be an integer")
        self.assertIs(type(details['services']), dict,
                      "Services details must be in a dictionary")
        self.assertIs(type(details['dependencies']), dict,
                      "Dependencies details must be in a dictionary")

    def testIPopoStartInstalled(self):
        """
        Tests if iPOPO starts instances of already installed bundles
        """
        # Uninstall the iPOPO bundle
        ipopo_bundle = self.framework.get_bundle_by_name("pelix.ipopo.core")
        ipopo_bundle.uninstall()
        self.ipopo = None

        # Install the test bundle
        module = install_bundle(self.framework)

        # Install iPOPO
        self.ipopo = install_ipopo(self.framework)

        # Test if the automatic instance is there
        self.assertTrue(self.ipopo.is_registered_factory(module.BASIC_FACTORY),
                        "Factory not registered")

        self.assertTrue(
            self.ipopo.is_registered_instance(module.BASIC_INSTANCE),
            "Component not created")

    def testInstantiate(self):
        """
        Tests the instantiate method
        """
        FACTORY = "dummy-factory"
        FACTORY_2 = "dummy-factory-2"
        INSTANCE = "dummy-instance"
        context = self.framework.get_bundle_context()

        @decorators.ComponentFactory(FACTORY)
        class TestComponent(object):
            pass

        # Invalid name
        for invalid in (None, "", [1]):
            self.assertRaises(ValueError, self.ipopo.instantiate,
                              invalid, INSTANCE)

            self.assertRaises(ValueError, self.ipopo.instantiate,
                              FACTORY, invalid)

        # Unknown factory -> Type Error
        self.assertRaises(TypeError, self.ipopo.instantiate, FACTORY, INSTANCE)

        # Register factory
        self.ipopo.register_factory(context, TestComponent)
        self.ipopo.instantiate(FACTORY, INSTANCE)

        # Already running -> Value Error
        self.assertRaises(
            ValueError, self.ipopo.instantiate, FACTORY, INSTANCE)
        self.ipopo.kill(INSTANCE)

        # Exception on instantiate -> Type Error
        @decorators.ComponentFactory(FACTORY_2)
        class TestComponent2(object):

            def __init__(self):
                raise NotImplementedError

        self.ipopo.register_factory(context, TestComponent2)

        log_off()
        self.assertRaises(TypeError, self.ipopo.instantiate, FACTORY_2,
                          INSTANCE)
        log_on()

    def testIPopoEvents(self):
        """
        Tests iPOPO event listener
        """
        FACTORY = "dummy-factory"
        INSTANCE = "dummy-instance"
        context = self.framework.get_bundle_context()

        @decorators.ComponentFactory(FACTORY)
        class TestComponent(object):
            pass

        class Listener(object):

            """
            iPOPO event listener
            """

            def __init__(self):
                self.events = []

            def count(self):
                return len(self.events)

            def reset(self):
                del self.events[:]

            def handle_ipopo_event(self, event):
                self.events.append(event)

        def check_event(event, kind, factory, instance):
            """
            Tests the validity of an event
            """
            self.assertEqual(event.get_kind(), kind,
                             "Excepted kind: {0} / got: {1}"
                             .format(kind, event.get_kind()))

            self.assertEqual(event.get_factory_name(), factory,
                             "Excepted factory: {0} / got: {1}"
                             .format(factory, event.get_factory_name()))

            self.assertEqual(event.get_component_name(), instance,
                             "Excepted instance: {0} / got: {1}"
                             .format(instance, event.get_component_name()))

        # Register the listener
        listener = Listener()
        self.assertTrue(self.ipopo.add_listener(listener),
                        "Listener not registered")

        self.assertFalse(self.ipopo.add_listener(listener),
                         "Listener registered twice")

        # Test events
        self.assertEqual(listener.count(), 0, "Non empty events list")

        # .. register factory
        self.ipopo.register_factory(context, TestComponent)
        self.assertEqual(
            listener.count(), 1, "Registration event not received")
        check_event(listener.events[0], IPopoEvent.REGISTERED, FACTORY, None)

        # .. instantiate
        listener.reset()
        self.ipopo.instantiate(FACTORY, INSTANCE)

        self.assertEqual(listener.count(), 2,
                         "Validation event not received")
        check_event(listener.events[0], IPopoEvent.INSTANTIATED, FACTORY,
                    INSTANCE)
        check_event(
            listener.events[1], IPopoEvent.VALIDATED, FACTORY, INSTANCE)

        # .. kill
        listener.reset()
        self.ipopo.kill(INSTANCE)

        self.assertEqual(listener.count(), 2, "Kill events not received")
        check_event(listener.events[0], IPopoEvent.INVALIDATED, FACTORY,
                    INSTANCE)
        check_event(listener.events[1], IPopoEvent.KILLED, FACTORY, INSTANCE)

        # .. unregister factory
        listener.reset()
        self.ipopo.unregister_factory(FACTORY)

        self.assertEqual(listener.count(), 1,
                         "Unregistration event not received")
        check_event(listener.events[0], IPopoEvent.UNREGISTERED, FACTORY, None)

        # Unregister the listener
        self.assertTrue(self.ipopo.remove_listener(listener),
                        "Listener not unregistered")

        self.assertFalse(self.ipopo.remove_listener(listener),
                         "Listener unregistered twice")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
