#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @Provides decorator.

:author: Thomas Calmant
"""

import random
import time
import unittest

from pelix.framework import BundleContext, FrameworkFactory
from pelix.ipopo.constants import IPopoEvent
from pelix.ipopo.decorators import Temporal, get_factory_context
from tests.interfaces import IEchoService
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

NAME_A = "componentA"

# ------------------------------------------------------------------------------


class Dummy(object):
    """
    Dummy object for tests
    """

    def __init__(self):
        """
        Sets up members
        """
        self.value = random.random()
        self.values = [random.random() for _ in range(3)]

    def method(self):
        return self.value

    def __call__(self, *args, **kwargs):
        return self.values


class TemporalTest(unittest.TestCase):
    """
    Tests the component "provides" behavior
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

    def test_proxy(self):
        """
        Tests the TemporalProxy class
        """
        # Import TemporalException here, or the type will be different from the
        # one loaded by the framework.
        # Same for _TemporalProxy. Also, it would reference modules garbage
        # collected by Python when the framework is deleted, therefore the
        # types it uses from other modules would be None.
        from pelix.ipopo.handlers.temporal import TemporalException, _TemporalProxy

        proxy = _TemporalProxy(0.1)

        # Try to call the object itself
        try:
            proxy()
        except TemporalException:
            # OK
            pass
        else:
            self.fail("TemporalException not raised on call")

        # Try to call a non-active proxy method
        try:
            # Exception getting the field
            proxy.method
        except TemporalException:
            # OK
            pass
        else:
            self.fail("TemporalException not raised on field access")

        # Check boolean value
        self.assertFalse(proxy)

        # Set a service
        svc = Dummy()
        proxy.set_service(svc)
        self.assertTrue(proxy)

        # Access valid fields
        self.assertEqual(proxy.method(), svc.method())
        self.assertEqual(proxy(), svc())
        self.assertIs(proxy.value, svc.value)
        self.assertIs(proxy.values, svc.values)

        # Access invalid fields
        try:
            proxy.invalid()
        except AttributeError:
            # OK
            pass
        else:
            self.fail("AttributeError not raised")

        # Unset the service
        proxy.unset_service()
        self.assertFalse(proxy)

        # Try to call the object itself
        try:
            proxy()
        except TemporalException:
            # OK
            pass
        else:
            self.fail("TemporalException not raised on call")

        # Try to call a non-active proxy method
        try:
            # Exception getting the field
            proxy.method
        except TemporalException:
            # OK
            pass
        else:
            self.fail("TemporalException not raised on field access")

    def test_temporal_lifecycle(self):
        """
        Tests the component life cycle
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Assert that the service is not yet available
        self.assertIsNone(context.get_service_reference(IEchoService), "Service is already registered")

        # Import TemporalException here, or the type will be different from the
        # one loaded by the framework.
        from pelix.ipopo.handlers.temporal import TemporalException

        # Get the value from the configuration of the handler
        factory_context = get_factory_context(module.TemporalComponentFactory)
        configs = factory_context.get_handler(Temporal.HANDLER_ID)
        timeout = configs["service"][1]

        # Instantiate the component
        consumer = self.ipopo.instantiate(module.FACTORY_TEMPORAL, NAME_A)

        # Component must be invalid
        self.assertListEqual([IPopoEvent.INSTANTIATED], consumer.states)
        consumer.reset()

        # Instantiate a service
        svc1 = Dummy()
        reg1 = context.register_service(IEchoService, svc1, {})

        # The consumer must have been validated
        self.assertListEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED], consumer.states)
        consumer.reset()

        # Make a call
        self.assertEqual(consumer.call(), svc1.method())

        # Register service 2
        svc2 = Dummy()
        reg2 = context.register_service(IEchoService, svc2, {})

        # No modification
        self.assertListEqual([], consumer.states)
        consumer.reset()

        # Unregister service 1
        reg1.unregister()
        self.assertListEqual([IPopoEvent.UNBOUND, IPopoEvent.BOUND], consumer.states)
        self.assertEqual(consumer.call(), svc2.method())
        consumer.reset()

        # Unregister service 2
        reg2.unregister()

        # No modification yet
        self.assertListEqual([], consumer.states)
        consumer.reset()

        # Register a new service
        svc3 = Dummy()
        reg3 = context.register_service(IEchoService, svc3, {})

        # Service must have been injected before invalidation
        self.assertListEqual([IPopoEvent.UNBOUND, IPopoEvent.BOUND], consumer.states)
        self.assertEqual(consumer.call(), svc3.method())
        consumer.reset()

        # Unregister service 3
        reg3.unregister()

        # No modification yet
        self.assertListEqual([], consumer.states)
        consumer.reset()

        start = time.time()
        try:
            # Try to call the method
            consumer.call()
        except TemporalException:
            # OK !
            pass
        else:
            self.fail("No temporal exception raised during call")
        end = time.time()

        # Check timeout
        self.assertLess(end - start, timeout * 2.0)
        self.assertGreater(end - start, timeout / 2.0)

        # Wait a little
        time.sleep(0.2)

        # Check state
        self.assertListEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND], consumer.states)
        consumer.reset()


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
