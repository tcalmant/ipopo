#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @RequiresVarFilter decorator.

:author: Thomas Calmant
"""

# Tests
from tests.ipopo import install_bundle, install_ipopo
from tests.interfaces import IEchoService

# Pelix
from pelix.ipopo.constants import IPopoEvent
from pelix.ipopo.decorators import get_factory_context, RequiresVarFilter
from pelix.framework import FrameworkFactory, BundleContext

# Standard library
import random
import string
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

NAME_A = "componentA"

# ------------------------------------------------------------------------------


class RequiresVarFilterTest(unittest.TestCase):
    """
    Tests the "requires variable filter" handler behavior
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

    def __internal_test(self, module, rebind_states):
        """
        Tests if the provides decorator works
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Prepare random string values
        random_static_1 = ''.join(random.choice(string.ascii_letters)
                                  for _ in range(50))
        random_static_2 = ''.join(random.choice(string.ascii_letters)
                                  for _ in range(50))

        # Assert that the service is not yet available
        self.assertIsNone(context.get_service_reference(IEchoService),
                          "Service is already registered")

        # Instantiate the component
        consumer = self.ipopo.instantiate(
            module.FACTORY_REQUIRES_VAR_FILTER, NAME_A,
            {"static": random_static_1})

        # Force the "answer" property to an int
        consumer.change(42)

        # Component must be invalid
        self.assertListEqual([IPopoEvent.INSTANTIATED], consumer.states,
                             "Invalid component states: {0}"
                             .format(consumer.states))
        consumer.reset()

        # Instantiate a service, matching the filter
        svc1 = object()
        context.register_service(
            IEchoService, svc1, {"s": random_static_1, "a": consumer.answer})

        # The consumer must have been validated
        self.assertListEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED],
                             consumer.states, "Invalid component states: {0}"
                             .format(consumer.states))
        self.assertIs(consumer.service, svc1, "Wrong service injected")
        consumer.reset()

        # New service, still matching
        svc2 = object()
        context.register_service(
            IEchoService, svc2, {"s": random_static_1, "a": consumer.answer})

        # The consumer must not have been modified
        self.assertListEqual([], consumer.states,
                             "Invalid component states: {0}"
                             .format(consumer.states))
        self.assertIs(consumer.service, svc1, "Wrong service injected")
        consumer.reset()

        # Change the filter property to the same value
        consumer.change(42)

        # The consumer must not have been modified
        self.assertListEqual([], consumer.states,
                             "Invalid component states: {0}"
                             .format(consumer.states))
        self.assertIs(consumer.service, svc1, "Wrong service injected")
        consumer.reset()

        # Change the filter property to a new value
        consumer.change(10)

        # The consumer must have been invalidated
        self.assertListEqual(
            [IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states))
        self.assertIs(consumer.service, None, "A service is injected")
        consumer.reset()

        # New service, matching part of the filter
        svc3 = object()
        context.register_service(
            IEchoService, svc3, {"s": random_static_2, "a": consumer.answer})

        # The consumer must not have been modified
        self.assertListEqual([], consumer.states,
                             "Invalid component states: {0}"
                             .format(consumer.states))
        self.assertIs(consumer.service, None, "A service is injected")
        consumer.reset()

        # New service, matching the new filer
        svc4 = object()
        reg4 = context.register_service(
            IEchoService, svc4, {"s": random_static_1, "a": consumer.answer})

        # The consumer must not have been modified
        self.assertListEqual(
            [IPopoEvent.BOUND, IPopoEvent.VALIDATED],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states))
        self.assertIs(consumer.service, svc4, "Wrong service injected")
        consumer.reset()

        # New service, matching the new filer
        svc5 = object()
        reg5 = context.register_service(
            IEchoService, svc5, {"s": random_static_1, "a": consumer.answer})

        # The consumer must not have been modified
        self.assertListEqual([], consumer.states,
                             "Invalid component states: {0}"
                             .format(consumer.states))
        self.assertIs(consumer.service, svc4, "Wrong service injected")
        consumer.reset()

        # Unregister the service in a clean way
        reg4.unregister()

        # Check the rebind state
        self.assertListEqual(
            rebind_states,
            consumer.states,
            "Invalid component states: {0}".format(consumer.states))
        self.assertIs(consumer.service, svc5, "Wrong service injected")
        consumer.reset()

        # Final unregistration
        reg5.unregister()
        self.assertListEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                             consumer.states, "Invalid component states: {0}"
                             .format(consumer.states))
        self.assertIs(consumer.service, None, "A service is injected")
        consumer.reset()

    def test_requires_var_filter(self):
        """
        Tests the @RequiresVarFilter handler without immediate_rebind (default)
        """
        module = install_bundle(self.framework)
        self.__internal_test(module,
                             [IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND,
                              IPopoEvent.BOUND, IPopoEvent.VALIDATED])

    def test_immediate_rebind(self):
        """
        Tests the @RequiresVarFilter handler with immediate_rebind
        """
        # Modify the component factory
        module = install_bundle(self.framework)
        context = get_factory_context(module.RequiresVarFilterComponentFactory)
        configs = context.get_handler(RequiresVarFilter.HANDLER_ID)
        configs["service"].immediate_rebind = True

        self.__internal_test(module, [IPopoEvent.UNBOUND, IPopoEvent.BOUND])

    def test_invalid_filter(self):
        """
        Tests the behaviour with badly formatted LDAP filters
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        random_static = ''.join(random.choice(string.ascii_letters)
                                for _ in range(50))

        # Assert that the service is not yet available
        self.assertIsNone(context.get_service_reference(IEchoService),
                          "Service is already registered")

        # Instantiate the component
        consumer = self.ipopo.instantiate(
            module.FACTORY_REQUIRES_VAR_FILTER, NAME_A,
            {"static": random_static})

        # Force the "answer" property to an int
        consumer.change(42)

        # Instantiate a service, matching the filter
        svc1 = object()
        context.register_service(
            IEchoService, svc1, {"s": random_static, "a": consumer.answer})

        # Component must be valid
        self.assertListEqual(
            [IPopoEvent.INSTANTIATED, IPopoEvent.BOUND, IPopoEvent.VALIDATED],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states))
        consumer.reset()

        # Set an invalid filter
        consumer.change(")")

        # The consumer must have been validated
        self.assertListEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                             consumer.states, "Invalid component states: {0}"
                             .format(consumer.states))
        self.assertIs(consumer.service, None, "A service is injected")
        consumer.reset()

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
