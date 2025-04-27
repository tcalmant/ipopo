#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @RequiresBest decorator.

:author: Thomas Calmant
"""

import random
import unittest

from pelix.framework import BundleContext, FrameworkFactory
from pelix.ipopo.constants import IPopoEvent
from tests.interfaces import IEchoService
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

NAME_A = "componentA"
NAME_B = "componentB"

# ------------------------------------------------------------------------------


class SampleEchoService(IEchoService):
    """
    Implementation to flag calls from the consumer
    """

    def __init__(self):
        self.called = False
        self.value = None
        self.raised = False
        self.sub_service = None

    def echo(self, value):
        self.called = True
        self.value = value
        return value

    def __call__(self, value):
        return self.echo(value)

    def reset(self):
        self.called = False
        self.value = None
        self.raised = False
        self.sub_service = None

    def raise_ex(self):
        self.raised = True
        raise KeyError("Oops")


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
        consumer = self.ipopo.instantiate(module.FACTORY_REQUIRES_BROADCAST, NAME_A)

        # Component must be valid
        self.assertListEqual(
            [IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states),
        )
        consumer.reset()

        # The proxy should indicate it's false
        self.assertFalse(consumer.service, "Proxy says it's valid")

        # We should be able to use the service
        self.assertFalse(consumer.service.echo("Hello"), "Service returned something")

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

            # Check proxy state
            self.assertTrue(consumer.service, "Proxy doesn't say True")

            # Try a call
            value = random.randint(1, 100)
            self.assertTrue(
                consumer.service.echo(value),
                "Proxy doesn't return True on call",
            )

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

            if live_svc:
                self.assertTrue(consumer.service, "Proxy should be True")
                self.assertTrue(consumer.service.echo(value), "Proxy should return True")
            else:
                self.assertFalse(consumer.service, "Proxy should be False")
                self.assertFalse(consumer.service.echo(value), "Proxy should return False")

            for _, svc_x in live_svc:
                self.assertTrue(svc_x.called, "Service not called")
                self.assertEqual(svc_x.value, value, "Wrong argument given")
                svc_x.reset()

        # Last local check
        self.assertFalse(consumer.service, "Proxy should be False")
        self.assertFalse(consumer.service.echo(random.random()), "Call shouldn't return True")

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
        consumer = self.ipopo.instantiate(module.FACTORY_REQUIRES_BROADCAST_REQUIRED, NAME_A)

        # Component must be invalid
        self.assertListEqual(
            [IPopoEvent.INSTANTIATED],
            consumer.states,
            "Invalid component states: {0}".format(consumer.states),
        )
        consumer.reset()

        # We shouldn't be able to use the service
        self.assertIsNone(consumer.service, "Proxy was injected")

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
            self.assertTrue(consumer.service, "Proxy should be True")
            self.assertTrue(consumer.service.echo(value), "Proxy should return True")

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
                self.assertTrue(consumer.service, "Proxy should be True")
                self.assertTrue(consumer.service.echo(value), "Proxy should return True")

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

    def test_early_binding(self):
        """
        Checks @RequiresBroadcast when the service is already there
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Assert that the service is not yet available
        self.assertIsNone(
            context.get_service_reference(IEchoService),
            "Service is already registered",
        )

        # Register the service
        svc_1 = SampleEchoService()
        context.register_service(IEchoService, svc_1, {})

        svc_2 = SampleEchoService()
        context.register_service(IEchoService, svc_2, {})

        live_svc = [svc_1, svc_2]

        for factory in (
            module.FACTORY_REQUIRES_BROADCAST,
            module.FACTORY_REQUIRES_BROADCAST_REQUIRED,
        ):
            for svc_x in live_svc:
                svc_x.reset()

            # Instantiate the component
            consumer = self.ipopo.instantiate(factory, NAME_A)

            # Component must be valid
            self.assertListEqual(
                [IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()

            # The proxy should indicate it's True
            self.assertTrue(consumer.service, "Proxy says it's not valid")

            # We should be able to use the service
            value = random.randint(1, 100)
            self.assertTrue(consumer.service.echo(value), "Call failed")

            for svc_x in live_svc:
                self.assertTrue(svc_x.called, "Service not called")
                self.assertEqual(svc_x.value, value, "Wrong argument given")
                svc_x.reset()

            # Clean up
            self.ipopo.kill(NAME_A)

    def test_exception(self):
        """
        Tests muffling exceptions or not
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
        consumer_muffled = self.ipopo.instantiate(module.FACTORY_REQUIRES_BROADCAST, NAME_A)
        consumer_raise = self.ipopo.instantiate(module.FACTORY_REQUIRES_BROADCAST_UNMUFFLED, NAME_B)

        # Everything should be fine
        self.assertFalse(consumer_muffled.service.raise_ex(), "Call should return False")
        self.assertFalse(consumer_raise.service.raise_ex(), "Call should return False")

        # Register the service
        svc = SampleEchoService()
        context.register_service(IEchoService, svc, {})

        # Muffled should be fine
        self.assertTrue(consumer_muffled.service.raise_ex(), "Call should return True")
        self.assertTrue(svc.raised, "Service not called")
        svc.reset()

        # The other should raise the exception
        self.assertRaises(
            KeyError,
            consumer_raise.service.raise_ex,
        )
        self.assertTrue(svc.raised, "Service not called")

    def test_paths(self):
        """
        Checks direct calls to proxy and to deeper members
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
        consumer = self.ipopo.instantiate(module.FACTORY_REQUIRES_BROADCAST, NAME_A)
        consumer.reset()

        # Register the service
        svc = SampleEchoService()
        svc_ref = context.register_service(IEchoService, svc, {})

        # Check proxy state
        self.assertTrue(consumer.service, "Proxy is False")
        self.assertTrue(consumer.service.sub_service, "Deeper member is False")

        # Direct call
        value = random.randint(1, 100)
        self.assertTrue(consumer.service(value), "Direct call returned False")
        self.assertEqual(svc.value, value, "Wrong value given")
        self.assertTrue(svc.called, "Service not called")
        svc.reset()

        # Member call
        svc.sub_service = SampleEchoService()
        value = random.randint(1, 100)
        self.assertTrue(
            consumer.service.sub_service.echo(value),
            "Member call returned False",
        )

        self.assertFalse(svc.called, "First member was called")
        self.assertIsNone(svc.value, "First member was given the value")
        self.assertTrue(svc.sub_service.called, "Deeper service not called")
        self.assertEqual(svc.sub_service.value, value, "Wrong value given")
        svc.sub_service.reset()
        svc.reset()
        svc.sub_service = SampleEchoService()

        # Unregister the service
        svc_ref.unregister()
        self.assertFalse(consumer.service, "Proxy is True")
        self.assertFalse(consumer.service.sub_service, "Deeper member is True")

        # Both calls must return False
        value = random.randint(1, 100)
        self.assertFalse(consumer.service(value), "Direct call returned True")
        self.assertFalse(
            consumer.service.sub_service.echo(value),
            "Member call returned True",
        )

        # Service must not have been called
        self.assertFalse(svc.called, "First member was called")
        self.assertIsNone(svc.value, "First member valued")
        self.assertFalse(svc.sub_service.called, "Deeper service was called")
        self.assertIsNone(svc.sub_service.value, "Deeper service valued")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
