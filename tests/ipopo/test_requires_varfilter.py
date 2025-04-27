#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @RequiresVarFilter decorator.

:author: Thomas Calmant
"""

import random
import string
import unittest

from pelix.framework import BundleContext, FrameworkFactory
from pelix.ipopo.constants import IPopoEvent
from pelix.ipopo.decorators import RequiresVarFilter, get_factory_context
from pelix.ipopo.instance import StoredInstance
from tests.interfaces import IEchoService
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

NAME_A = "componentA"
NAME_B = "componentB"

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
        random_static_1 = "".join(random.choice(string.ascii_letters) for _ in range(50))
        random_static_2 = "".join(random.choice(string.ascii_letters) for _ in range(50))

        # Assert that the service is not yet available
        self.assertIsNone(
            context.get_service_reference(IEchoService),
            "Service is already registered",
        )

        # Instantiate the components
        consumer_single = self.ipopo.instantiate(
            module.FACTORY_REQUIRES_VAR_FILTER,
            NAME_A,
            {"static": random_static_1},
        )
        consumer_multi = self.ipopo.instantiate(
            module.FACTORY_REQUIRES_VAR_FILTER_AGGREGATE,
            NAME_B,
            {"static": random_static_1},
        )
        consumers = (consumer_single, consumer_multi)

        # Force the "answer" property to an int
        for consumer in consumers:
            consumer.change(42)

        # Component must be invalid
        for consumer in consumers:
            self.assertListEqual(
                [IPopoEvent.INSTANTIATED],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()

        # Instantiate a service, matching the filter
        svc1 = object()
        context.register_service(
            IEchoService,
            svc1,
            {"s": random_static_1, "a": consumer_single.answer},
        )

        # The consumer must have been validated
        for consumer in consumers:
            self.assertListEqual(
                [IPopoEvent.BOUND, IPopoEvent.VALIDATED],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()

        self.assertIs(consumer_single.service, svc1, "Wrong service injected")
        self.assertListEqual(consumer_multi.service, [svc1], "Wrong service injected")

        # New service, still matching
        svc2 = object()
        reg2 = context.register_service(
            IEchoService,
            svc2,
            {"s": random_static_1, "a": consumer_single.answer},
        )

        # The single consumer must not have been modified
        self.assertListEqual(
            [],
            consumer_single.states,
            "Invalid component states: {0}".format(consumer_single.states),
        )
        self.assertIs(consumer_single.service, svc1, "Wrong service injected")

        # The aggregate consumer must have been modified
        self.assertListEqual(
            [IPopoEvent.BOUND],
            consumer_multi.states,
            "Invalid component states: {0}".format(consumer_multi.states),
        )
        self.assertListEqual(consumer_multi.service, [svc1, svc2], "Second service not injected")

        # Reset states
        for consumer in consumers:
            consumer.reset()

        # Remove the second service
        reg2.unregister()

        # The single consumer must not have been modified
        self.assertListEqual(
            [],
            consumer_single.states,
            "Invalid component states: {0}".format(consumer_single.states),
        )
        self.assertIs(consumer_single.service, svc1, "Wrong service injected")

        # The aggregate consumer must have been modified
        self.assertListEqual(
            [IPopoEvent.UNBOUND],
            consumer_multi.states,
            "Invalid component states: {0}".format(consumer_multi.states),
        )
        self.assertListEqual(consumer_multi.service, [svc1], "Second service not removed")

        # Change the filter property to the exact same value
        for consumer in consumers:
            consumer.reset()
            consumer.change(42)

            # The consumer must not have been modified
            self.assertListEqual(
                [],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()

        self.assertIs(consumer_single.service, svc1, "Wrong service injected")
        self.assertListEqual(consumer_multi.service, [svc1], "Wrong service injected")

        # Change the filter property to a new value
        for consumer in consumers:
            consumer.change(10)

        # The consumer must have been invalidated
        for consumer in consumers:
            self.assertListEqual(
                [IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            self.assertIs(consumer.service, None, "A service is injected")
            consumer.reset()

        # New service, matching part of the filter
        svc3 = object()
        context.register_service(
            IEchoService,
            svc3,
            {"s": random_static_2, "a": consumer_single.answer},
        )

        # The consumer must not have been modified
        for consumer in consumers:
            self.assertListEqual(
                [],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            self.assertIs(consumer.service, None, "A service is injected")
            consumer.reset()

        # New service, matching the new filer
        svc4 = object()
        reg4 = context.register_service(
            IEchoService,
            svc4,
            {"s": random_static_1, "a": consumer_single.answer},
        )

        # The consumer must not have been modified
        for consumer in consumers:
            self.assertListEqual(
                [IPopoEvent.BOUND, IPopoEvent.VALIDATED],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()

        self.assertIs(consumer_single.service, svc4, "Wrong service injected")
        self.assertListEqual(consumer_multi.service, [svc4], "Wrong service injected")

        # New service, matching the new filer
        svc5 = object()
        reg5 = context.register_service(
            IEchoService,
            svc5,
            {"s": random_static_1, "a": consumer_single.answer},
        )

        # The single consumer must not have been modified
        self.assertListEqual(
            [],
            consumer_single.states,
            "Invalid component states: {0}".format(consumer_single.states),
        )
        self.assertIs(consumer_single.service, svc4, "Wrong service injected")

        # The aggregate consumer must have been modified
        self.assertListEqual(
            [IPopoEvent.BOUND],
            consumer_multi.states,
            "Invalid component states: {0}".format(consumer_multi.states),
        )
        self.assertListEqual(consumer_multi.service, [svc4, svc5], "Second service not injected")

        # Reset states
        for consumer in consumers:
            consumer.reset()

        # Unregister the service in a clean way
        reg4.unregister()

        # Check the rebind state for the single dependency
        self.assertListEqual(
            rebind_states,
            consumer_single.states,
            "Invalid component states: {0}".format(consumer_single.states),
        )
        self.assertIs(consumer_single.service, svc5, "Wrong service injected")

        # The aggregate consumer must have been modified
        self.assertListEqual(
            [IPopoEvent.UNBOUND],
            consumer_multi.states,
            "Invalid component states: {0}".format(consumer_multi.states),
        )
        self.assertListEqual(consumer_multi.service, [svc5], "First service not removed")

        # Reset states
        for consumer in consumers:
            consumer.reset()

        # Final unregistration
        reg5.unregister()

        for consumer in consumers:
            self.assertListEqual(
                [IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            self.assertIs(consumer.service, None, "A service is still injected")
            consumer.reset()

    def test_requires_var_filter(self):
        """
        Tests the @RequiresVarFilter handler without immediate_rebind (default)
        """
        module = install_bundle(self.framework)
        self.__internal_test(
            module,
            [
                IPopoEvent.INVALIDATED,
                IPopoEvent.UNBOUND,
                IPopoEvent.BOUND,
                IPopoEvent.VALIDATED,
            ],
        )

    def test_immediate_rebind(self):
        """
        Tests the @RequiresVarFilter handler with immediate_rebind
        """
        # Modify component factories
        module = install_bundle(self.framework)

        for clazz in (
            module.RequiresVarFilterComponentFactory,
            module.RequiresVarFilterAggregateComponentFactory,
        ):
            context = get_factory_context(clazz)
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

        random_static = "".join(random.choice(string.ascii_letters) for _ in range(50))

        # Assert that the service is not yet available
        self.assertIsNone(
            context.get_service_reference(IEchoService),
            "Service is already registered",
        )

        # Instantiate the components
        consumer_single = self.ipopo.instantiate(
            module.FACTORY_REQUIRES_VAR_FILTER,
            NAME_A,
            {"static": random_static},
        )
        consumer_multi = self.ipopo.instantiate(
            module.FACTORY_REQUIRES_VAR_FILTER_AGGREGATE,
            NAME_B,
            {"static": random_static},
        )
        consumers = (consumer_single, consumer_multi)

        # Force the "answer" property to an int
        for consumer in consumers:
            consumer.change(42)

        # Instantiate a service, matching the filter
        svc1 = object()
        context.register_service(
            IEchoService,
            svc1,
            {"s": random_static, "a": consumer_single.answer},
        )

        # Component must be valid
        for consumer in consumers:
            self.assertListEqual(
                [
                    IPopoEvent.INSTANTIATED,
                    IPopoEvent.BOUND,
                    IPopoEvent.VALIDATED,
                ],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()

        # Set an invalid filter
        for consumer in consumers:
            consumer.change(")")

            # The consumer must have been validated
            self.assertListEqual(
                [IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()
            self.assertIs(consumer.service, None, "A service is injected")

        # Check other invalid filters
        for consumer in consumers:
            for invalid in ("", "=", "("):
                # Force the "answer" property to an invalid value
                consumer.change(invalid)

                # Instantiate a service, matching the filter
                svc = object()
                reg = context.register_service(IEchoService, svc, {"s": random_static, "a": invalid})

                # Nothing should happen
                self.assertListEqual(
                    [],
                    consumer.states,
                    "Invalid component states: {0}".format(consumer.states),
                )
                consumer.reset()

                reg.unregister()

    def test_no_change(self):
        """
        Test the behaviour when the LDAP filter doesn't change with the
        property
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        random_static = "".join(random.choice(string.ascii_letters) for _ in range(50))

        # Assert that the service is not yet available
        self.assertIsNone(
            context.get_service_reference(IEchoService),
            "Service is already registered",
        )

        # Instantiate the components
        consumer_single = self.ipopo.instantiate(
            module.FACTORY_REQUIRES_VAR_FILTER,
            NAME_A,
            {"static": random_static},
        )
        consumer_multi = self.ipopo.instantiate(
            module.FACTORY_REQUIRES_VAR_FILTER_AGGREGATE,
            NAME_B,
            {"static": random_static},
        )
        consumers = (consumer_single, consumer_multi)

        # Force the "answer" property to an int
        for consumer in consumers:
            consumer.change(42)

        # Instantiate a service, matching the filter
        svc1 = object()
        context.register_service(
            IEchoService,
            svc1,
            {"s": random_static, "a": consumer_single.answer},
        )

        # Component must be valid
        for consumer in consumers:
            self.assertListEqual(
                [
                    IPopoEvent.INSTANTIATED,
                    IPopoEvent.BOUND,
                    IPopoEvent.VALIDATED,
                ],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()

        # Set the filter with a similar value (same once formatted)
        for consumer in consumers:
            consumer.change("42")

        # The consumer should not be notified
        for consumer in consumers:
            self.assertListEqual(
                [],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            consumer.reset()

        self.assertIs(consumer_single.service, svc1, "Wrong service injected")
        self.assertListEqual(consumer_multi.service, [svc1], "Wrong service injected")

    def test_incomplete_properties(self):
        """
        Tests the behaviour when a property is missing
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        answer = 42
        random_static = "".join(random.choice(string.ascii_letters) for _ in range(50))

        # Assert that the service is not yet available
        self.assertIsNone(
            context.get_service_reference(IEchoService),
            "Service is already registered",
        )

        # Instantiate a service, matching the filter
        svc1 = object()
        context.register_service(IEchoService, svc1, {"s": random_static, "a": answer})

        for name, factory in (
            (NAME_A, module.FACTORY_REQUIRES_VAR_FILTER),
            (NAME_B, module.FACTORY_REQUIRES_VAR_FILTER_AGGREGATE),
        ):
            # Instantiate the component, without the static property
            consumer = self.ipopo.instantiate(factory, name, {})

            # Force the "answer" property to an int
            consumer.change(answer)

            # Component must be instantiated, but not valid
            self.assertListEqual(
                [IPopoEvent.INSTANTIATED],
                consumer.states,
                "Invalid component states: {0}".format(consumer.states),
            )
            self.assertIs(consumer.service, None, "Service injected")

    def test_late_binding(self):
        """
        Tests late binding, see issue #119:
        https://github.com/tcalmant/ipopo/issues/119
        """
        install_bundle(self.framework, "tests.ipopo.issue_119_bundle")
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        self.ipopo.instantiate("varservice-factory", "varservice-instance")
        self.ipopo.instantiate("provider-factory", "provider-instance-1", {"prop": "svc1"})
        self.ipopo.instantiate("provider-factory", "provider-instance-2", {"prop": "svc2"})

        svc1 = self.ipopo.get_instance("provider-instance-1")
        svc2 = self.ipopo.get_instance("provider-instance-2")
        consumer = self.ipopo.get_instance("varservice-instance")

        self.assertEqual(
            self.ipopo.get_instance_details("provider-instance-1")["state"], StoredInstance.VALID
        )
        self.assertEqual(
            self.ipopo.get_instance_details("provider-instance-2")["state"], StoredInstance.VALID
        )
        self.assertEqual(
            self.ipopo.get_instance_details("varservice-instance")["state"], StoredInstance.INVALID
        )

        consumer.search = "svc1"
        self.assertEqual(
            self.ipopo.get_instance_details("varservice-instance")["state"], StoredInstance.VALID
        )
        self.assertEqual(consumer.depends, svc1)

        consumer.search = "svc2"
        self.assertEqual(
            self.ipopo.get_instance_details("varservice-instance")["state"], StoredInstance.VALID
        )
        self.assertEqual(consumer.depends, svc2)

        consumer.search = "non-existent"
        self.assertEqual(
            self.ipopo.get_instance_details("varservice-instance")["state"], StoredInstance.INVALID
        )
        self.assertIsNone(consumer.depends)

        consumer.search = "svc1"
        self.assertEqual(
            self.ipopo.get_instance_details("varservice-instance")["state"], StoredInstance.VALID
        )
        self.assertEqual(consumer.depends, svc1)

        consumer.search = None
        self.assertEqual(
            self.ipopo.get_instance_details("varservice-instance")["state"], StoredInstance.INVALID
        )
        self.assertIsNone(consumer.depends)

    def test_late_binding_2(self):
        """
        Instantiate the 3 services (2 instances from the same service) with a var require.
        The variable is set before the required service is instantiated
        """
        install_bundle(self.framework, "tests.ipopo.issue_119_bundle")
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        self.ipopo.instantiate("varservice-factory", "varservice-instance-1")
        self.ipopo.instantiate("varservice-factory", "varservice-instance-2")
        service1 = self.ipopo.get_instance("varservice-instance-1")
        service1.search = "my-service-0"
        service2 = self.ipopo.get_instance("varservice-instance-2")
        service2.search = "my-service-0"
        self.assertEqual(
            self.ipopo.get_instance_details("varservice-instance-1")["state"], StoredInstance.INVALID
        )
        self.assertEqual(
            self.ipopo.get_instance_details("varservice-instance-2")["state"], StoredInstance.INVALID
        )

        self.ipopo.instantiate("provider-factory", "provider-instance", {"prop": "my-service-0"})
        self.assertEqual(self.ipopo.get_instance_details("provider-instance")["state"], StoredInstance.VALID)
        self.assertEqual(
            self.ipopo.get_instance_details("varservice-instance-1")["state"], StoredInstance.VALID
        )
        self.assertEqual(
            self.ipopo.get_instance_details("varservice-instance-2")["state"], StoredInstance.VALID
        )


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
