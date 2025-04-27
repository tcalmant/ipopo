#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the component life cycle callbacks decorators

:author: Thomas Calmant
"""

import itertools
import unittest

import pelix.ipopo.constants as constants
import pelix.ipopo.decorators as decorators
from pelix.framework import BundleContext, FrameworkFactory
from pelix.ipopo.contexts import ComponentContext
from pelix.ipopo.instance import StoredInstance
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class ValidateComponentTest(unittest.TestCase):
    """
    Tests the @ValidateComponent decorator
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.module = install_bundle(self.framework)

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.delete(True)

    def test_type_check(self):
        """
        Tests type checking of @ValidateComponent
        """

        class Dummy:
            pass

        self.assertRaises(TypeError, decorators.ValidateComponent(), Dummy)

    def test_arguments(self):
        """
        Tests arguments handling in @ValidateComponent
        """
        valid_args = [
            constants.ARG_BUNDLE_CONTEXT,
            constants.ARG_COMPONENT_CONTEXT,
            constants.ARG_PROPERTIES,
        ]

        types = {
            constants.ARG_BUNDLE_CONTEXT: BundleContext,
            constants.ARG_COMPONENT_CONTEXT: ComponentContext,
            constants.ARG_PROPERTIES: dict,
        }

        factory_name = "test"
        instance_name = "test"
        ctx = self.framework.get_bundle_context()

        for nb_args in range(len(valid_args) + 1):
            for decorator_args in itertools.combinations(valid_args, nb_args):

                @decorators.ComponentFactory(factory_name)
                class Sample:
                    @decorators.ValidateComponent(*decorator_args)
                    def validate(*args):
                        # Ignore self
                        args = args[1:]

                        for idx, arg in enumerate(args):
                            self.assertIsInstance(arg, types[decorator_args[idx]])

                try:
                    self.ipopo.register_factory(ctx, Sample)
                    self.ipopo.instantiate(factory_name, instance_name, {})
                finally:
                    self.ipopo.unregister_factory(factory_name)

    def test_error(self):
        """
        Tests the erroneous state after exception in @ValidateComponent
        """
        factory_name = "erroneous"

        @decorators.ComponentFactory(factory_name)
        @decorators.Property("_raise", "raise", True)
        class Erroneous(object):
            def __init__(self):
                self.calls = []
                self._raise = True

            @decorators.ValidateComponent()
            def validate_component(self):
                self.calls.append("ValidateComponent")
                if self._raise:
                    raise ValueError("Bad things happen")

            @decorators.Invalidate
            def invalidate(self, ctx):
                self.calls.append("Invalidate")

        # Register factory
        self.ipopo.register_factory(self.framework.get_bundle_context(), Erroneous)

        # Instantiate once
        instance_name = "test"
        instance = self.ipopo.instantiate(factory_name, instance_name, {"raise": True})

        # Check calls
        self.assertListEqual(["ValidateComponent", "Invalidate"], instance.calls)

        # Check state
        details = self.ipopo.get_instance_details(instance_name)
        self.assertEqual(details["state"], StoredInstance.ERRONEOUS)

        # Retry
        del instance.calls[:]
        self.ipopo.retry_erroneous(instance_name, {"raise": False})

        # Check calls
        self.assertListEqual(["ValidateComponent"], instance.calls)

        # Check state
        details = self.ipopo.get_instance_details(instance_name)
        self.assertEqual(details["state"], StoredInstance.VALID)

        # Kill it
        del instance.calls[:]
        self.ipopo.kill(instance_name)
        self.assertListEqual(["Invalidate"], instance.calls)


# ------------------------------------------------------------------------------


class InvalidateComponentTest(unittest.TestCase):
    """
    Tests the @InvalidateComponent decorator
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.module = install_bundle(self.framework)

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.delete(True)

    def test_type_check(self):
        """
        Tests type checking of @InvalidateComponentTest
        """

        class Dummy:
            pass

        self.assertRaises(TypeError, decorators.InvalidateComponent(), Dummy)

    def test_arguments(self):
        """
        Tests arguments handling in @InvalidateComponent
        """
        valid_args = [
            constants.ARG_BUNDLE_CONTEXT,
            constants.ARG_COMPONENT_CONTEXT,
            constants.ARG_PROPERTIES,
        ]

        types = {
            constants.ARG_BUNDLE_CONTEXT: BundleContext,
            constants.ARG_COMPONENT_CONTEXT: ComponentContext,
            constants.ARG_PROPERTIES: dict,
        }

        factory_name = "test"
        instance_name = "test"
        ctx = self.framework.get_bundle_context()

        for nb_args in range(len(valid_args) + 1):
            for decorator_args in itertools.combinations(valid_args, nb_args):

                @decorators.ComponentFactory(factory_name)
                class Sample:
                    @decorators.InvalidateComponent(*decorator_args)
                    def validate(*args):
                        # Ignore self
                        args = args[1:]

                        for idx, arg in enumerate(args):
                            self.assertIsInstance(arg, types[decorator_args[idx]])

                try:
                    self.ipopo.register_factory(ctx, Sample)
                    self.ipopo.instantiate(factory_name, instance_name, {})
                finally:
                    self.ipopo.unregister_factory(factory_name)

    def test_error(self):
        """
        Tests the erroneous state after exception in @InvalidateComponent
        """
        factory_name = "erroneous"
        svc_interface = "foo.bar"

        @decorators.ComponentFactory(factory_name)
        @decorators.Requires("_toto", svc_interface)
        class Erroneous(object):
            @decorators.InvalidateComponent()
            def invalidate(self):
                raise ValueError("Bad things happen")

        # Register factory
        self.ipopo.register_factory(self.framework.get_bundle_context(), Erroneous)

        # Register a service so that it can become active
        ctx = self.framework.get_bundle_context()
        svc_reg = ctx.register_service(svc_interface, object(), {})

        # Instantiate once
        instance_name = "test"
        self.ipopo.instantiate(factory_name, instance_name)

        # Check state
        details = self.ipopo.get_instance_details(instance_name)
        self.assertEqual(details["state"], StoredInstance.VALID)

        # Remove the service to invalidate the component
        svc_reg.unregister()

        # Check state
        details = self.ipopo.get_instance_details(instance_name)
        self.assertEqual(details["state"], StoredInstance.INVALID)

        # Kill it
        self.ipopo.kill(instance_name)


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
