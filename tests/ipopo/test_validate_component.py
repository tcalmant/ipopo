#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the component life cycle

:author: Thomas Calmant
"""

# Standard library
import itertools

try:
    import unittest2 as unittest
except ImportError:
    import unittest

# Tests
from tests.ipopo import install_bundle, install_ipopo

# Pelix
from pelix.framework import FrameworkFactory, BundleContext

# iPOPO
from pelix.ipopo.instance import ComponentContext
import pelix.ipopo.constants as constants
import pelix.ipopo.decorators as decorators

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

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

    def test_callback_order(self):
        """
        Checks if @ValidateComponent is called before @Validate
        """
        factory_name = "test.1"

        @decorators.ComponentFactory(factory_name)
        class Sample:
            def __init__(self):
                self.calls = []

            @decorators.ValidateComponent()
            def validate_component(self):
                self.calls.append("ValidateComponent")

            @decorators.Validate
            def validate(self, ctx):
                self.calls.append("Validate")

            @decorators.Invalidate
            def invalidate(self, ctx):
                self.calls.append("Invalidate")

        # Register factory
        self.ipopo.register_factory(
            self.framework.get_bundle_context(), Sample)

        # Instantiate once
        instance_name = "test"
        instance = self.ipopo.instantiate(factory_name, instance_name, {})

        # Check state
        self.assertListEqual(["ValidateComponent", "Validate"], instance.calls)

        # Kill it
        del instance.calls[:]
        self.ipopo.kill(instance_name)
        self.assertListEqual(["Invalidate"], instance.calls)

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
                            self.assertIsInstance(
                                arg, types[decorator_args[idx]])

                try:
                    self.ipopo.register_factory(ctx, Sample)
                    self.ipopo.instantiate(factory_name, instance_name, {})
                finally:
                    self.ipopo.unregister_factory(factory_name)

# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
