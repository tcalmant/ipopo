#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @RequiresBest decorator.

:author: Thomas Calmant
"""

import unittest

from pelix.constants import SERVICE_RANKING
from pelix.framework import BundleContext, FrameworkFactory
from pelix.ipopo.constants import IPopoEvent
from pelix.ipopo.decorators import RequiresBest, get_factory_context
from tests.interfaces import IEchoService
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

NAME_A = "componentA"

# ------------------------------------------------------------------------------


class RequiresBestTest(unittest.TestCase):
    """
    Tests the "requires best" handler behavior
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

        # Assert that the service is not yet available
        self.assertIsNone(context.get_service_reference(IEchoService), "Service is already registered")

        # Instantiate the component
        consumer = self.ipopo.instantiate(module.FACTORY_REQUIRES_BEST, NAME_A)

        # Component must be invalid
        self.assertListEqual(
            [IPopoEvent.INSTANTIATED],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states),
        )
        consumer.reset()

        # Instantiate a service
        svc1 = object()
        reg1 = context.register_service(IEchoService, svc1, {SERVICE_RANKING: 10})

        # The consumer must have been validated
        self.assertListEqual(
            [IPopoEvent.BOUND, IPopoEvent.VALIDATED],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states),
        )
        self.assertIs(consumer.service, svc1, "Wrong service injected")
        consumer.reset()

        # New service, with less priority
        svc2 = object()
        reg2 = context.register_service(IEchoService, svc2, {SERVICE_RANKING: 5})

        # The consumer must not have been modified
        self.assertListEqual([], consumer.states, "Invalid component states: {0}".format(consumer.states))
        self.assertIs(consumer.service, svc1, "Wrong service injected")
        consumer.reset()

        # New service, with higher priority
        svc3 = object()
        reg3 = context.register_service(IEchoService, svc3, {SERVICE_RANKING: 15})

        self.assertListEqual(
            rebind_states, consumer.states, "Invalid component states: {0}".format(consumer.states)
        )
        self.assertIs(consumer.service, svc3, "Old service injected")
        consumer.reset()

        # Increase ranking of service 2
        reg2.set_properties({SERVICE_RANKING: 20})
        self.assertListEqual(
            rebind_states, consumer.states, "Invalid component states: {0}".format(consumer.states)
        )
        self.assertIs(consumer.service, svc2, "Old service injected")
        consumer.reset()

        # Lower the ranking of service 2 (a bit)
        reg2.set_properties({SERVICE_RANKING: 18})
        self.assertListEqual([], consumer.states, "Invalid component states: {0}".format(consumer.states))
        self.assertIs(consumer.service, svc2, "Injected service changed")
        consumer.reset()

        # Lower the ranking of service 2 (very low)
        reg2.set_properties({SERVICE_RANKING: 0})
        self.assertListEqual(
            rebind_states, consumer.states, "Invalid component states: {0}".format(consumer.states)
        )
        self.assertIs(consumer.service, svc3, "Old service injected")
        consumer.reset()

        # Remove service 2
        reg2.unregister()
        self.assertListEqual([], consumer.states, "Invalid component states: {0}".format(consumer.states))
        self.assertIs(consumer.service, svc3, "Injected service changed")
        consumer.reset()

        # Re-register service, with the same ranking as service 1
        rank1 = reg1.get_reference().get_property(SERVICE_RANKING)
        reg2 = context.register_service(IEchoService, svc2, {SERVICE_RANKING: rank1})
        self.assertListEqual([], consumer.states, "Invalid component states: {0}".format(consumer.states))
        self.assertIs(consumer.service, svc3, "Injected service changed")
        consumer.reset()

        # Remove service 3 -> service 1 must be injected
        # (same ranking as 2, but older)
        reg3.unregister()
        self.assertListEqual(
            rebind_states, consumer.states, "Invalid component states: {0}".format(consumer.states)
        )
        self.assertIs(consumer.service, svc1, "Old service injected")
        consumer.reset()

        # Remove service 2 (again)
        reg2.unregister()
        self.assertListEqual([], consumer.states, "Invalid component states: {0}".format(consumer.states))
        self.assertIs(consumer.service, svc1, "Injected service changed")
        consumer.reset()

        # Remove service 1 (last one)
        reg1.unregister()
        self.assertListEqual(
            [IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states),
        )
        self.assertIsNone(consumer.service, "Service still injected")
        consumer.reset()

    def test_requires_best(self):
        """
        Tests the @RequiresBest handler with immediate_rebind (default)
        """
        module = install_bundle(self.framework)
        self.__internal_test(module, [IPopoEvent.UNBOUND, IPopoEvent.BOUND])

    def test_no_rebind(self):
        """
        Tests the @RequiresBest handler without immediate_rebind
        """
        # Modify the component factory
        module = install_bundle(self.framework)
        context = get_factory_context(module.RequiresBestComponentFactory)
        configs = context.get_handler(RequiresBest.HANDLER_ID)
        configs["service"].immediate_rebind = False

        self.__internal_test(
            module, [IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND, IPopoEvent.BOUND, IPopoEvent.VALIDATED]
        )


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
