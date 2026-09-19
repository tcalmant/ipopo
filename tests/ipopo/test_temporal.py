#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @Provides decorator.

:author: Thomas Calmant
"""

import random
import time
import unittest
from typing import Any

from pelix.framework import BundleContext, FrameworkFactory
from pelix.ipopo.constants import IPOPO_REQUIRES_FILTERS, IPOPO_TEMPORAL_TIMEOUTS, IPopoEvent
from pelix.ipopo.contexts import Requirement
from pelix.ipopo.decorators import Temporal, get_factory_context
from pelix.ipopo.handlers.temporal import _HandlerFactory
from tests.interfaces import IEchoService
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

NAME_A = "componentA"

# ------------------------------------------------------------------------------


class Dummy:
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
        self.addCleanup(self.framework.delete, True)
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
        with self.assertRaises(TemporalException, msg="TemporalException not raised on field access"):
            # Exception getting the field
            proxy.method  # noqa: B018

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
        with self.assertRaises(TemporalException, msg="TemporalException not raised on field access"):
            # Exception getting the field
            proxy.method  # noqa: B018

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


class TemporalConfigurationTest(unittest.TestCase):
    """
    Tests the override of the temporal requirements by component properties
    """

    def setUp(self) -> None:
        self.requirement = Requirement("test.spec", spec_filter="(a=1)")
        self.configs = {"field": (self.requirement, 5)}

    def prepare(self, filters: Any = None, timeouts: Any = None) -> dict[str, Any]:
        """
        Calls the configuration method as the handler factory does
        """
        return _HandlerFactory._prepare_configs(self.configs, filters, timeouts)

    def test_no_override(self) -> None:
        """
        Without (valid) overrides, the factory configuration is used as is
        """
        for filters, timeouts in ((None, None), ({}, {}), ("(a=2)", ["field"])):
            self.assertIs(self.configs, self.prepare(filters, timeouts))

    def test_filter_override(self) -> None:
        """
        The filter override applies to a copy of the requirement
        """
        new_configs = self.prepare({"field": "(a=2)"})
        requirement, timeout = new_configs["field"]
        self.assertIsNot(self.requirement, requirement)
        self.assertEqual("(a=2)", str(requirement.original_filter))
        self.assertEqual("(a=1)", str(self.requirement.original_filter))
        self.assertEqual(5, timeout)

        # Invalid filters are ignored
        self.assertIs(self.configs["field"], self.prepare({"field": "(a=2"})["field"])
        self.assertIs(self.configs["field"], self.prepare({"field": 42})["field"])

    def test_timeout_override(self) -> None:
        """
        Invalid timeout overrides are replaced by the factory timeout
        """
        for value, expected in (("3", 3), (7, 7), (None, 5), (0, 5), (-1, 5), ("abc", 5), ([1], 5)):
            new_configs = self.prepare(timeouts={"field": value})
            requirement, timeout = new_configs["field"]
            self.assertEqual(expected, timeout, value)
            self.assertEqual("(a=1)", str(requirement.original_filter))

    def test_float_timeout_override(self) -> None:
        """
        Sub-second and fractional timeouts are accepted by @Temporal, they are
        accepted as overrides too, but not non-finite values
        """
        self.assertEqual(0.5, self.prepare(timeouts={"field": 0.5})["field"][1])
        self.assertEqual(2.5, self.prepare(timeouts={"field": 2.5})["field"][1])
        self.assertEqual(1.5, self.prepare(timeouts={"field": "1.5"})["field"][1])
        for value in ("nan", float("inf"), -0.5):
            self.assertEqual(5, self.prepare(timeouts={"field": value})["field"][1], value)


class TemporalPropertiesTest(unittest.TestCase):
    """
    Tests the temporal requirement overrides given as instance properties
    """

    def setUp(self) -> None:
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(FrameworkFactory.delete_framework)
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.module = install_bundle(self.framework)
        self.context = self.framework.get_bundle_context()

    def test_overrides(self) -> None:
        """
        Filter and timeout overrides are applied to the injected proxy
        """
        from pelix.ipopo.handlers.temporal import TemporalException

        consumer = self.ipopo.instantiate(
            self.module.FACTORY_TEMPORAL,
            NAME_A,
            {IPOPO_REQUIRES_FILTERS: {"service": "(answer=42)"}, IPOPO_TEMPORAL_TIMEOUTS: {"service": 1}},
        )
        consumer.reset()

        # Only the service matching the overriding filter is injected
        self.context.register_service(IEchoService, Dummy(), {"answer": 0})
        self.assertListEqual([], consumer.states)

        svc = Dummy()
        reg = self.context.register_service(IEchoService, svc, {"answer": 42})
        self.assertListEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED], consumer.states)
        self.assertEqual(svc.method(), consumer.call())

        # The overriding timeout (1s) is used instead of the factory one (2s)
        reg.unregister()
        start = time.time()
        with self.assertRaises(TemporalException):
            consumer.call()
        self.assertLess(time.time() - start, 1.8)

    def test_invalid_properties(self) -> None:
        """
        Invalid overrides are logged and ignored
        """
        with self.assertLogs("pelix.ipopo.handlers.temporal", "WARNING") as logs:
            consumer = self.ipopo.instantiate(
                self.module.FACTORY_TEMPORAL,
                NAME_A,
                {IPOPO_REQUIRES_FILTERS: "(answer=42)", IPOPO_TEMPORAL_TIMEOUTS: 1},
            )
        self.assertEqual(2, len(logs.records))

        # The factory filter (none) is still used
        consumer.reset()
        self.context.register_service(IEchoService, Dummy(), {})
        self.assertListEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED], consumer.states)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
