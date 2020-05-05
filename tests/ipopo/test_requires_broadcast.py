#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @RequiresBest decorator.

:author: Thomas Calmant
"""

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest
import random

# Pelix
from pelix.ipopo.constants import IPopoEvent
from pelix.framework import FrameworkFactory, BundleContext

# Tests
from tests.ipopo import install_bundle, install_ipopo
from tests.interfaces import IEchoService

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 0)
__version__ = ".".join(str(x) for x in __version_info__)

NAME_A = "componentA"

# ------------------------------------------------------------------------------


class SampleEchoService(IEchoService):
    """
    Implementation to flag calls from the consumer
    """

    def __init__(self):
        IEchoService.__init__(self)
        self.called = False
        self.value = None

    def echo(self, value):
        self.called = True
        self.value = value
        return value

    def reset(self):
        self.called = False
        self.value = None


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

    def test_optional_service(self):
        """
        Tests the basic behaviour (optional service)
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Assert that the service is not yet available
        self.assertIsNone(
            context.get_service_reference(IEchoService),
            "Service is already registered",
        )

        # Instantiate the component
        consumer = self.ipopo.instantiate(
            module.FACTORY_REQUIRES_BROADCAST, NAME_A
        )

        # Component must be valid
        self.assertListEqual(
            [IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states),
        )
        consumer.reset()

        # We should be able to use the service
        self.assertFalse(
            consumer.service.echo("Hello"), "Service returned something"
        )

        live_svc = []

        for _ in range(5):
            # Register a service
            svc = SampleEchoService()
            svc_ref = context.register_service(IEchoService, svc, {})

            live_svc.append((svc_ref, svc))

            # Nothing has changed
            self.assertListEqual(
                [],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()

            # Try a call
            value = random.randint(1, 100)
            self.assertTrue(consumer.service.echo(value))

            for _, svc_x in live_svc:
                self.assertTrue(svc_x.called, "Service not called")
                self.assertEqual(svc_x.value, value, "Wrong argument given")
                svc_x.reset()

        # Try unregistering
        for svc_ref, svc in live_svc[:]:
            # Unregister the service
            svc_ref.unregister()

            # Nothing has changed
            self.assertListEqual(
                [],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()

            # Don't check this service
            live_svc.remove((svc_ref, svc))

            # Test the call
            value = random.randint(1, 42)
            consumer.service.echo(value)

            for _, svc_x in live_svc:
                self.assertTrue(svc_x.called, "Service not called")
                self.assertEqual(svc_x.value, value, "Wrong argument given")
                svc_x.reset()

        # Last local check
        self.assertFalse(consumer.service.echo(random.random()))

    def test_required_service(self):
        """
        Tests the basic behaviour (optional service)
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Assert that the service is not yet available
        self.assertIsNone(
            context.get_service_reference(IEchoService),
            "Service is already registered",
        )

        # Instantiate the component
        consumer = self.ipopo.instantiate(
            module.FACTORY_REQUIRES_BROADCAST_REQUIRED, NAME_A
        )

        # Component must be invalid
        self.assertListEqual(
            [IPopoEvent.INSTANTIATED],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states),
        )
        consumer.reset()

        # We shouldn't be able to use the service
        self.assertIsNone(
            consumer.service, "Proxy was injected"
        )

        live_svc = []

        for _ in range(5):
            # Register a service
            svc = SampleEchoService()
            svc_ref = context.register_service(IEchoService, svc, {})

            live_svc.append((svc_ref, svc))

            if len(live_svc) == 1:
                # First service: component must be valid
                self.assertListEqual(
                    [IPopoEvent.VALIDATED],
                    consumer.states,
                    "Invalid component states: {0}".format(consumer.states),
                )
                consumer.reset()
            else:
                # Nothing has changed
                self.assertListEqual(
                    [],
                    consumer.states,
                    "Invalid component states: {0}".format(consumer.states),
                )
                consumer.reset()

            # Try a call
            value = random.randint(1, 100)
            self.assertTrue(consumer.service.echo(value))

            for _, svc_x in live_svc:
                self.assertTrue(svc_x.called, "Service not called")
                self.assertEqual(svc_x.value, value, "Wrong argument given")
                svc_x.reset()

        # Try unregistering
        for svc_ref, svc in live_svc[:]:
            # Unregister the service
            svc_ref.unregister()

            # Don't check this service
            live_svc.remove((svc_ref, svc))

            if live_svc:
                # Nothing has changed
                self.assertListEqual(
                    [],
                    consumer.states,
                    "Invalid component states: {0}".format(consumer.states),
                )
                consumer.reset()

                # Test the call
                value = random.randint(1, 42)
                consumer.service.echo(value)

                for _, svc_x in live_svc:
                    self.assertTrue(svc_x.called, "Service not called")
                    self.assertEqual(svc_x.value, value, "Wrong argument given")
                    svc_x.reset()

        # No more services: component must be invalid
        # First service: component must be valid
        self.assertListEqual(
            [IPopoEvent.INVALIDATED],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states),
        )
        consumer.reset()

        # Proxy should be removed
        self.assertIsNone(consumer.service, "Proxy is still injected")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
