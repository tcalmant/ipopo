#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO decorators.

:author: Thomas Calmant
"""

import code
import os
import sys
import unittest

import pelix.ipopo.constants as constants
import pelix.ipopo.decorators as decorators
from pelix.framework import FrameworkFactory
from tests import log_off, log_on
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class UtilityMethodsTest(unittest.TestCase):
    """
    Tests the utility methods used to validate decorated methods
    """

    def _dummy(self):
        pass

    @staticmethod
    def _static_dummy():
        pass

    @classmethod
    def _class_dummy(cls):
        pass

    def _some_args_dummy(self, a, b, c):
        pass

    def _args_dummy(self, *args):
        pass

    def _args_dummy_bad(self, other, *args):
        pass

    def test_arity(self):
        """
        Tests validate_method_arity()
        """
        # Check without argument
        decorators.validate_method_arity(self._dummy)
        decorators.validate_method_arity(self._static_dummy)
        decorators.validate_method_arity(self._class_dummy)

        # Check with positional or keyword arguments
        decorators.validate_method_arity(self._some_args_dummy, "a", "b", "c")

        self.assertRaises(TypeError, decorators.validate_method_arity, self._some_args_dummy)
        self.assertRaises(TypeError, decorators.validate_method_arity, self._some_args_dummy, "a")
        self.assertRaises(TypeError, decorators.validate_method_arity, self._some_args_dummy, "a", "b")
        self.assertRaises(
            TypeError, decorators.validate_method_arity, self._some_args_dummy, "a", "b", "c", "d"
        )

        # Check with variable arguments
        decorators.validate_method_arity(self._args_dummy)
        decorators.validate_method_arity(self._args_dummy, "a")
        decorators.validate_method_arity(self._args_dummy, "a", "b")

        # Refuse methods with both positional and variable arguments
        self.assertRaises(
            TypeError, decorators.validate_method_arity, self._args_dummy_bad, "other", "a", "b"
        )

    def test_method_description(self):
        """
        Tests get_method_description()
        """
        if os.name == "nt":
            # Caution: it seems Python mixes upper/lower case drive letters on Windows
            file_path = __file__[:-2].lower()
        else:
            file_path = __file__[:-2]

        description = decorators.get_method_description(self._dummy)
        if os.name == "nt":
            # Compare in lower case on Windows
            description = description.lower()

        self.assertNotIn(":-1", description)
        self.assertIn(file_path, description)
        self.assertIn("_dummy", description)

        description = decorators.get_method_description(self._some_args_dummy)
        if os.name == "nt":
            # Compare in lower case on Windows
            description = description.lower()

        self.assertNotIn(":-1", description)
        self.assertIn(file_path, description)
        self.assertIn("_some_args_dummy", description)

        # Try with a compiled method
        local_vars = {}
        mod = code.compile_command("def foobar():\n    pass\n", "<generated>")
        exec(mod, {}, local_vars)
        foobar = local_vars["foobar"]

        description = decorators.get_method_description(foobar)
        if os.name == "nt":
            # Compare in lower case on Windows
            description = description.lower()

        self.assertIn(":-1", description)
        self.assertNotIn(file_path, description)
        self.assertIn("<generated>", description)
        self.assertIn("foobar", description)

        # Try with any object with a name
        class Foo:
            pass

        # __name__ is missing in instances
        self.assertRaises(AttributeError, decorators.get_method_description, Foo())

        # ... not on type
        self.assertIn(repr(Foo.__name__), decorators.get_method_description(Foo))

        class Bar:
            __name__ = "<Bar>"

        # Name exists in instance
        description = decorators.get_method_description(Bar())
        self.assertIn(repr(Bar().__name__), description)


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
        FrameworkFactory.delete_framework()

    def testCallbacks(self):
        """
        Tests callbacks definitions
        """
        # Define what the method should contain
        callbacks = {
            decorators.Bind: constants.IPOPO_CALLBACK_BIND,
            decorators.Unbind: constants.IPOPO_CALLBACK_UNBIND,
            decorators.Validate: constants.IPOPO_CALLBACK_VALIDATE,
            decorators.Invalidate: constants.IPOPO_CALLBACK_INVALIDATE,
            decorators.ValidateComponent(constants.ARG_BUNDLE_CONTEXT): constants.IPOPO_CALLBACK_VALIDATE,
            decorators.InvalidateComponent(constants.ARG_BUNDLE_CONTEXT): constants.IPOPO_CALLBACK_INVALIDATE,
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

        self.assertFalse(
            hasattr(empty_method, constants.IPOPO_METHOD_CALLBACKS), "The method is already tagged"
        )

        self.assertFalse(
            hasattr(correct_method, constants.IPOPO_METHOD_CALLBACKS), "The method is already tagged"
        )

        for decorator, callback in callbacks.items():
            # Ensure that the empty  method will fail being decorated
            for bad_method in bad_methods:
                try:
                    self.assertRaises(TypeError, decorator, bad_method)
                except:
                    print(bad_method)
                    raise

            # Decorate the method
            decorated = decorator(correct_method)

            # Assert the method is the same
            self.assertIs(decorated, correct_method, "Method ID changed")

            # Assert the decoration has been done
            self.assertIn(
                callback, getattr(correct_method, constants.IPOPO_METHOD_CALLBACKS), "Decoration failed"
            )

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
            self.assertRaises(TypeError, decorators.ComponentFactory("test"), invalid)

        # Transform the class into a component
        decorators.ComponentFactory()(DummyClass)

        # No name -> generated one
        parent_context = decorators.get_factory_context(DummyClass)
        self.assertEqual(parent_context.name, "DummyClassFactory", "Invalid generated name")

        # Transform the child class
        decorators.ComponentFactory()(ChildClass)
        child_context = decorators.get_factory_context(ChildClass)

        # Ensure the instantiation was not removed after inheritance
        self.assertIn(instance_name, parent_context.get_instances(), "Instance disappeared of parent")

        # Ensure the instantiation was not inherited
        self.assertNotIn(instance_name, child_context.get_instances(), "Instance kept in child")

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
            self.assertRaises(TypeError, decorators.Instantiate, "test", invalid)

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.Instantiate("test"), invalid)

        # 1st injection
        decorators.Instantiate("test", {"id": 1})(DummyClass)

        # 2nd injection: nothing happens
        log_off()
        decorators.Instantiate("test", {"id": 2})(DummyClass)
        log_on()

        # Get the factory context
        context = decorators.get_factory_context(DummyClass)
        instances = context.get_instances()
        self.assertEqual(instances["test"]["id"], 1, "Instance properties have been overridden")

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
            self.assertRaises(TypeError, decorators.Property("field", "name"), invalid)

    def testProvides(self):
        """
        Tests the @Provides decorator
        """

        class DummyClass(object):
            pass

        def method():
            pass

        # Field name with a space
        self.assertRaises(ValueError, decorators.Provides, "spec", "a space")

        # Invalid specification type
        for invalid in ([1, 2, 3], tuple((1, 2, 3)), 123):
            self.assertRaises(ValueError, decorators.Provides, "spec", invalid)

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.Provides("spec", "field"), invalid)

    def test_provides_factory(self):
        """
        Tests the @Provides decorator for a service factory
        """

        class DummyClass(object):
            pass

        def invalid_method(self, foo):
            pass

        def valid_method(self, bundle, svc_reg):
            pass

        # Missing method in class
        self.assertRaises(TypeError, decorators.Provides("spec", factory=True), DummyClass)

        # One of two methods
        DummyClass.get_service = valid_method
        self.assertRaises(TypeError, decorators.Provides("spec", factory=True), DummyClass)

        # Both methods
        DummyClass.unget_service = valid_method
        try:
            decorators.Provides("spec", factory=True)(DummyClass)
        except TypeError:
            self.fail("Error on valid class")

        # Invalid arity
        DummyClass.get_service = invalid_method
        self.assertRaises(TypeError, decorators.Provides("spec", factory=True), DummyClass)

    def test_provides_prototype(self):
        """
        Tests the @Provides decorator for a prototype service factory
        """

        class DummyClass(object):
            pass

        def invalid_method(self, foo):
            pass

        def valid_method(self, bundle, svc_reg):
            pass

        def valid_instance_method(self, bundle, svc_reg, svc):
            pass

        # Missing method in class
        self.assertRaises(TypeError, decorators.Provides("spec", prototype=True), DummyClass)

        # One of three methods
        DummyClass.get_service = valid_method
        self.assertRaises(TypeError, decorators.Provides("spec", prototype=True), DummyClass)

        # Two of three methods
        DummyClass.unget_service = valid_method
        self.assertRaises(TypeError, decorators.Provides("spec", prototype=True), DummyClass)

        # Two (other) of three methods
        del DummyClass.unget_service
        DummyClass.unget_service_instance = valid_instance_method
        self.assertRaises(TypeError, decorators.Provides("spec", prototype=True), DummyClass)

        # All methods
        DummyClass.unget_service = valid_method
        try:
            decorators.Provides("spec", prototype=True)(DummyClass)
        except TypeError:
            self.fail("Error on valid class")

        # Invalid arity
        DummyClass.get_service = invalid_method
        self.assertRaises(TypeError, decorators.Provides("spec", prototype=True), DummyClass)

        DummyClass.get_service = valid_method
        DummyClass.unget_service_instance = invalid_method
        self.assertRaises(TypeError, decorators.Provides("spec", prototype=True), DummyClass)

    def test_requires_base(self):
        """
        Tests the @Requires* decorators basic arguments checks
        """

        def method():
            pass

        for decorator in (
            decorators.Requires,
            decorators.RequiresBest,
            decorators.RequiresVarFilter,
            decorators.Temporal,
        ):
            # Empty field or specification
            for empty in (None, "", "   "):
                self.assertRaises(ValueError, decorator, empty, "spec")
                self.assertRaises(ValueError, decorator, "field", empty)

            # Invalid field or specification type
            for invalid in ([1, 2, 3], tuple((1, 2, 3)), 123):
                self.assertRaises(TypeError, decorator, invalid)
                self.assertRaises(ValueError, decorator, "field", invalid)

            # Invalid target
            for invalid in (None, method, 123):
                self.assertRaises(TypeError, decorator("field", "spec"), invalid)

    def test_requires_map(self):
        """
        Tests the @RequiresMap decorator
        """

        class DummyClass(object):
            pass

        def method():
            pass

        # Empty field or specification
        for empty in (None, "", "   "):
            self.assertRaises(ValueError, decorators.RequiresMap, empty, "spec", "key")
            self.assertRaises(ValueError, decorators.RequiresMap, "field", empty, "key")

        # Empty key
        for empty in (None, ""):
            self.assertRaises(ValueError, decorators.RequiresMap, "field", "spec", empty)

        # Invalid field or specification type
        for invalid in ([1, 2, 3], tuple((1, 2, 3)), 123):
            self.assertRaises(TypeError, decorators.RequiresMap, invalid)
            self.assertRaises(ValueError, decorators.RequiresMap, "field", invalid, "key")

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.RequiresMap("field", "spec", "key"), invalid)

    def test_temporal(self):
        """
        @Temporal specific tests
        """
        for value in (-100, -10.0, 0):
            temporal = decorators.Temporal("field", "spec", timeout=value)
            self.assertGreater(temporal._timeout, 0)

        for value in (0.1, 10, 100):
            temporal = decorators.Temporal("field", "spec", timeout=value)
            self.assertEqual(temporal._timeout, value)


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

        # Compatibility issue
        if sys.version_info[0] < 3:
            self.assertCountEqual = self.assertItemsEqual

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def testGetFactoryContext(self):
        """
        Tests the _get_factory_context() method
        """

        class DummyClass(object):
            pass

        class ChildClass(DummyClass):
            pass

        # Assert the field doesn't exist yet
        self.assertRaises(AttributeError, getattr, DummyClass, constants.IPOPO_FACTORY_CONTEXT)

        # Convert the parent into a component
        DummyClass = decorators.ComponentFactory("dummy-factory")(
            decorators.Requires("field", "req")(DummyClass)
        )

        # Get the context
        class_context = decorators.get_factory_context(DummyClass)
        self.assertIsNotNone(decorators.get_factory_context(DummyClass), "Invalid factory context")

        # The child has a copy of the parent context
        child_context = decorators.get_factory_context(ChildClass)
        self.assertIsNot(child_context, class_context, "The child must have a copy of the context")

    def testGetMethodDescription(self):
        """
        Tests the ipopo.decorators.get_method_description() method
        """
        bundle_name = "tests.framework.simple_bundle"
        bundle = install_bundle(self.framework, bundle_name)
        descr = decorators.get_method_description(bundle.ActivatorTest.start)

        # Assert we found sufficient data
        self.assertTrue(descr.startswith("'start'"), "Method name not found")
        self.assertIn(bundle_name.replace(".", os.sep) + ".py", descr, "File couldn't determined")

        # Some methods are unreadable
        self.assertEqual(
            "'getpid'", decorators.get_method_description(os.getpid), "Invalid description of getpid()"
        )

    def test_provides_get_specifications(self):
        """
        Tests the _get_specifications method for the @Provides decorator
        """
        # Invalid entry
        for invalid in (None, "", [], tuple(), {"spec": 1}, [1, 2, 3], tuple((1, 2, 3)), 123):
            self.assertRaises(ValueError, decorators._get_specifications, invalid)

        # Test inheritance
        from tests.ipopo import ipopo_bundle
        from tests.ipopo.ipopo_bundle import Child

        base_names = ["Father", "Mother"]
        full_names = ["{0}.{1}".format(ipopo_bundle.__name__, name) for name in base_names]

        # New behavior
        decorators.Provides.USE_MODULE_QUALNAME = True
        try:
            Child.__qualname__
        except AttributeError:
            self.assertRaises(ValueError, decorators._get_specifications, Child.__bases__)
        else:
            specs = decorators._get_specifications(Child.__bases__)
            self.assertCountEqual(full_names, specs)

        # Legacy behavior
        decorators.Provides.USE_MODULE_QUALNAME = False
        specs = decorators._get_specifications(Child.__bases__)
        self.assertCountEqual(base_names, specs)

        # Class specification
        class Spec(object):
            pass

        self.assertEqual(
            decorators._get_specifications(Spec), [Spec.__name__], "Class not converted into string"
        )

        # String specification
        simple_spec = ["simple.spec"]
        self.assertEqual(
            decorators._get_specifications(simple_spec[0]),
            simple_spec,
            "Simple string not converted into a list",
        )

        # Multiple specifications
        multiple_spec = ["spec.1", "spec.2", Spec]
        result_spec = ["spec.1", "spec.2", Spec.__name__]

        self.assertEqual(
            decorators._get_specifications(multiple_spec),
            result_spec,
            "Invalid conversion of multiple specifications",
        )


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
