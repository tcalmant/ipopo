#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO decorators.

:author: Thomas Calmant
"""

# Tests
from tests import log_on, log_off
from tests.ipopo import install_bundle, install_ipopo

# Pelix
from pelix.framework import FrameworkFactory

# iPOPO
import pelix.ipopo.constants as constants
import pelix.ipopo.decorators as decorators

# Standard library
import os
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class DecoratorsTest(unittest.TestCase):
    """
    Tests the iPOPO decorators
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
        FrameworkFactory.delete_framework(self.framework)

    def testCallbacks(self):
        """
        Tests callbacks definitions
        """
        # Define what the method should contain
        callbacks = {
            decorators.Bind: constants.IPOPO_CALLBACK_BIND,
            decorators.Unbind: constants.IPOPO_CALLBACK_UNBIND,
            decorators.Validate: constants.IPOPO_CALLBACK_VALIDATE,
            decorators.Invalidate: constants.IPOPO_CALLBACK_INVALIDATE
        }

        # Define some non decorable types
        class BadClass(object):
            pass

        # Define a decorable method
        def empty_method():
            pass

        def args_method(abc, *args):
            pass

        def kwargs_method(abc, **kwargs):
            pass

        def correct_method(self, *args):
            pass

        bad_types = (None, 12, "Bad", BadClass)
        bad_methods = (None, empty_method, args_method, kwargs_method)

        self.assertFalse(hasattr(empty_method,
                                 constants.IPOPO_METHOD_CALLBACKS),
                         "The method is already tagged")

        self.assertFalse(hasattr(correct_method,
                                 constants.IPOPO_METHOD_CALLBACKS),
                         "The method is already tagged")

        for decorator, callback in callbacks.items():
            # Ensure that the empty  method will fail being decorated
            for bad_method in bad_methods:
                self.assertRaises(TypeError, decorator, bad_method)

            # Decorate the method
            decorated = decorator(correct_method)

            # Assert the method is the same
            self.assertIs(decorated, correct_method, "Method ID changed")

            # Assert the decoration has been done
            self.assertIn(callback, getattr(correct_method,
                                            constants.IPOPO_METHOD_CALLBACKS),
                          "Decoration failed")

            # Assert that the decorator raises a TypeError on invalid elements
            for bad in bad_types:
                self.assertRaises(TypeError, decorator, bad)

    def testComponentFactory(self):
        """
        Tests the @decorators.ComponentFactory decorator
        """
        instance_name = "test"

        @decorators.Instantiate(instance_name)
        class DummyClass(object):
            pass

        class ChildClass(DummyClass):
            pass

        def method():
            pass

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.ComponentFactory("test"),
                              invalid)

        # Transform the class into a component
        decorators.ComponentFactory()(DummyClass)

        # No name -> generated one
        parent_context = decorators.get_factory_context(DummyClass)
        self.assertEqual(parent_context.name, "DummyClassFactory",
                         "Invalid generated name")

        # Transform the child class
        decorators.ComponentFactory()(ChildClass)
        child_context = decorators.get_factory_context(ChildClass)

        # Ensure the instantiation was not removed after inheritance
        self.assertIn(instance_name, parent_context.get_instances(),
                      "Instance disappeared of parent")

        # Ensure the instantiation was not inherited
        self.assertNotIn(instance_name, child_context.get_instances(),
                         "Instance kept in child")

    def testInstantiate(self):
        """
        Tests the @Instantiate decorator
        """
        class DummyClass(object):
            pass

        def method():
            pass

        # Empty name
        for empty in ("", "   "):
            self.assertRaises(ValueError, decorators.Instantiate, empty)

        # Invalid name type
        for invalid in (None, [], tuple(), 123):
            self.assertRaises(TypeError, decorators.Instantiate, invalid)

        # Invalid properties type
        for invalid in ("props", [1, 2], tuple((1, 2, 3)), 123):
            self.assertRaises(TypeError, decorators.Instantiate, "test",
                              invalid)

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.Instantiate("test"),
                              invalid)

        # 1st injection
        decorators.Instantiate("test", {"id": 1})(DummyClass)

        # 2nd injection: nothing happens
        log_off()
        decorators.Instantiate("test", {"id": 2})(DummyClass)
        log_on()

        # Get the factory context
        context = decorators.get_factory_context(DummyClass)
        instances = context.get_instances()
        self.assertEqual(instances["test"]["id"], 1,
                         "Instance properties have been overridden")

    def testProperty(self):
        """
        Tests the @Property decorator
        """
        class DummyClass(object):
            pass

        def method():
            pass

        # Empty or invalid field name
        for invalid in ("", "   ", "a space"):
            self.assertRaises(ValueError, decorators.Property, invalid)

        for empty in ("", "   "):
            # No error should be raised
            decorators.Property("field", empty)

        # Invalid type
        self.assertRaises(TypeError, decorators.Property, None)
        for invalid in ([1, 2, 3], tuple((1, 2, 3)), 123):
            self.assertRaises(TypeError, decorators.Property, invalid)
            self.assertRaises(TypeError, decorators.Property, "field", invalid)

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.Property("field", "name"),
                              invalid)

    def testProvides(self):
        """
        Tests the @Provides decorator
        """
        class DummyClass(object):
            pass

        def method():
            pass

        # Empty specification
        for empty in (None, "", "   "):
            self.assertRaises(ValueError, decorators.Provides, empty)

            # No error should be raised
            log_off()
            decorators.Provides("spec", empty)
            log_on()

        # Field name with a space
        self.assertRaises(ValueError, decorators.Provides, "spec", "a space")

        # Invalid specification type
        for invalid in ([1, 2, 3], tuple((1, 2, 3)), 123):
            self.assertRaises(ValueError, decorators.Provides, invalid)
            self.assertRaises(ValueError, decorators.Provides, "spec", invalid)

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.Provides("spec", "field"),
                              invalid)

    def testRequires(self):
        """
        Tests the @Requires decorator
        """
        class DummyClass(object):
            pass

        def method():
            pass

        # Empty field or specification
        for empty in (None, "", "   "):
            self.assertRaises(ValueError, decorators.Requires, empty, "spec")
            self.assertRaises(ValueError, decorators.Requires, "field", empty)

        # Invalid field or specification type
        for invalid in ([1, 2, 3], tuple((1, 2, 3)), 123):
            self.assertRaises(TypeError, decorators.Requires, invalid)
            self.assertRaises(
                ValueError, decorators.Requires, "field", invalid)

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.Requires("field", "spec"),
                              invalid)

    def testRequiresMap(self):
        """
        Tests the @RequiresMap decorator
        """
        class DummyClass(object):
            pass

        def method():
            pass

        # Empty field or specification
        for empty in (None, "", "   "):
            self.assertRaises(ValueError, decorators.RequiresMap,
                              empty, "spec", "key")
            self.assertRaises(ValueError, decorators.RequiresMap,
                              "field", empty, "key")

        # Empty key
        for empty in (None, ""):
            self.assertRaises(ValueError, decorators.RequiresMap,
                              "field", "spec", empty)

        # Invalid field or specification type
        for invalid in ([1, 2, 3], tuple((1, 2, 3)), 123):
            self.assertRaises(TypeError, decorators.Requires, invalid)
            self.assertRaises(
                ValueError, decorators.Requires, "field", invalid)

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.Requires("field", "spec"),
                              invalid)

# ------------------------------------------------------------------------------


class SimpleDecoratorsTests(unittest.TestCase):
    """
    Tests the decorators utility methods
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.context = self.framework.get_bundle_context()

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)

    def testGetFactoryContext(self):
        """
        Tests the _get_factory_context() method
        """
        class DummyClass(object):
            pass

        class ChildClass(DummyClass):
            pass

        # Assert the field doesn't exist yet
        self.assertRaises(AttributeError, getattr, DummyClass,
                          constants.IPOPO_FACTORY_CONTEXT)

        # Convert the parent into a component
        DummyClass = decorators.ComponentFactory("dummy-factory")(
            decorators.Requires("field", "req")
            (DummyClass))

        # Get the context
        class_context = decorators.get_factory_context(DummyClass)
        self.assertIsNotNone(decorators.get_factory_context(DummyClass),
                             "Invalid factory context")

        # The child has a copy of the parent context
        child_context = decorators.get_factory_context(ChildClass)
        self.assertIsNot(child_context, class_context,
                         "The child must have a copy of the context")

    def testGetMethodDescription(self):
        """
        Tests the ipopo.decorators.get_method_description() method
        """
        bundle_name = "tests.framework.simple_bundle"
        bundle = install_bundle(self.framework, bundle_name)
        descr = decorators.get_method_description(bundle.ActivatorTest.start)

        # Assert we found sufficient data
        self.assertTrue(descr.startswith("'start'"), "Method name not found")
        self.assertIn(bundle_name.replace(".", os.sep) + ".py", descr,
                      "File couldn't determined")

        # Some methods are unreadable
        self.assertEqual("'getpid'",
                         decorators.get_method_description(os.getpid),
                         "Invalid description of getpid()")

    def testGetSpecifications(self):
        """
        Tests the _get_specifications() method
        """
        for empty in (None, "", [], tuple()):
            self.assertRaises(
                ValueError, decorators._get_specifications, empty)

        # Class specification
        class Spec(object):
            pass

        self.assertEqual(decorators._get_specifications(Spec),
                         [Spec.__name__],
                         "Class not converted into string")

        # String specification
        simple_spec = ["simple.spec"]
        self.assertEqual(decorators._get_specifications(simple_spec[0]),
                         simple_spec,
                         "Simple string not converted into a list")

        # Multiple specifications
        multiple_spec = ["spec.1", "spec.2", Spec]
        result_spec = ["spec.1", "spec.2", Spec.__name__]

        self.assertEqual(decorators._get_specifications(multiple_spec),
                         result_spec,
                         "Invalid conversion of multiple specifications")

        # Unhandled types
        for invalid in (123, {"spec": 1}):
            self.assertRaises(ValueError, decorators._get_specifications,
                              invalid)

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
