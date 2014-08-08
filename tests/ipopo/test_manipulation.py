#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO class manipulation.

:author: Thomas Calmant
"""

# Tests
from tests.ipopo import install_bundle, install_ipopo

# Pelix
from pelix.framework import FrameworkFactory

# iPOPO
import pelix.ipopo.decorators as decorators

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

NAME_A = "componentA"

# ------------------------------------------------------------------------------


class ManipulatedClassTest(unittest.TestCase):
    """
    Tests the usage as a classic class of a manipulated component factory
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = None

    def tearDown(self):
        """
        Called after each test
        """
        if self.framework is not None:
            FrameworkFactory.delete_framework(self.framework)

    def testOutsideFramework(self):
        """
        Tests the behavior of a manipulated class outside a framework
        """
        # Prepare the class
        @decorators.ComponentFactory("test-factory")
        @decorators.Instantiate("test-instance")
        @decorators.Provides("spec_1")
        @decorators.Provides("spec_2", "controller")
        @decorators.Requires("req_1", "spec_1")
        @decorators.Requires("req_2", "spec_1", True, True)
        @decorators.Property("prop_1", "prop.1")
        @decorators.Property("prop_2", "prop.2", 42)
        class TestClass(object):
            pass

        # Instantiate
        instance = TestClass()

        # Check fields presence and values
        self.assertTrue(
            instance.controller, "Default service controller is On")
        self.assertIsNone(instance.req_1, "Requirement is not None")
        self.assertIsNone(instance.req_2, "Requirement is not None")
        self.assertIsNone(instance.prop_1, "Default property value is None")
        self.assertEqual(instance.prop_2, 42, "Incorrect property value")

        # Check property modification
        instance.prop_1 = 10
        instance.prop_2 = False

        self.assertEqual(instance.prop_1, 10, "Property value not modified")
        self.assertEqual(instance.prop_2, False, "Property value not modified")

    def testInsideFramework(self):
        """
        Tests the behavior of a manipulated class attributes
        """
        # Start the framework
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        ipopo = install_ipopo(self.framework)
        module = install_bundle(self.framework)

        # Instantiate the test class
        instance = module.ComponentFactoryA()

        # Check fields presence and values
        self.assertTrue(
            instance._test_ctrl, "Default service controller is On")
        self.assertIsNone(instance._req_1, "Requirement is not None")
        self.assertEqual(
            instance.prop_1, 10, "Constructor property value lost")
        self.assertEqual(instance.usable, True, "Incorrect property value")
        del instance

        # Instantiate component A (validated)
        instance = ipopo.instantiate(module.FACTORY_A, NAME_A)

        # Check fields presence and values
        self.assertTrue(
            instance._test_ctrl, "Default service controller is On")
        self.assertIsNone(instance._req_1, "Requirement is not None")
        self.assertIsNone(instance.prop_1, "Default property value is None")
        self.assertEqual(instance.usable, True, "Incorrect property value")

        instance.prop_1 = 42
        instance.usable = False

        self.assertEqual(instance.prop_1, 42, "Property value not modified")
        self.assertEqual(instance.usable, False, "Property value not modified")

        # Set A usable again
        instance.change(True)

        self.assertEqual(instance.usable, True, "Property value not modified")

    def testDuplicatedFactory(self):
        """
        Tests the behavior of iPOPO if two bundles provide the same factory.
        """
        # Start the framework
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        ipopo = install_ipopo(self.framework)

        # Install bundles: both provide a "basic-component-factory" factory
        # and instantiate a component (both with different names)
        module_A = install_bundle(self.framework, "tests.ipopo.ipopo_bundle")
        module_B = install_bundle(self.framework,
                                  "tests.ipopo.ipopo_bundle_copy")

        # Ensure that the module providing the factory is the correct one
        self.assertIs(module_A,
                      ipopo.get_factory_bundle(
                          module_A.BASIC_FACTORY).get_module(),
                      "Duplicated factory is not provided by the first module")
        self.assertIs(module_A,
                      ipopo.get_factory_bundle(
                          module_B.BASIC_FACTORY).get_module(),
                      "Duplicated factory is not provided by the first module")

        # Component of module A must be there
        self.assertIsNotNone(
            ipopo.get_instance_details(module_A.BASIC_INSTANCE),
            "Component from module A not started")

        # Component of module B must be absent
        self.assertRaises(ValueError,
                          ipopo.get_instance_details, module_B.BASIC_INSTANCE)

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
