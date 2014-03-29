#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO test module. Tests both the iPOPO core module and decorators

:author: Thomas Calmant
"""

from pelix.ipopo.constants import IPopoEvent
from pelix.framework import FrameworkFactory, Bundle, BundleContext

from tests import log_on, log_off
from tests.interfaces import IEchoService

import pelix.ipopo.constants as constants
import pelix.ipopo.decorators as decorators
import pelix.ipopo.contexts as contexts
import pelix.framework as pelix

import logging
import os

try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# Documentation strings format
__docformat__ = "restructuredtext en"

NAME_A = "componentA"
NAME_B = "componentB"
NAME_C = "componentC"

# ------------------------------------------------------------------------------

def install_bundle(framework, bundle_name="tests.ipopo_bundle"):
    """
    Installs and starts the test bundle and returns its module

    @param framework: A Pelix framework instance
    @param bundle_name: A bundle name
    @return: The installed bundle Python module
    """
    context = framework.get_bundle_context()

    bundle = context.install_bundle(bundle_name)
    bundle.start()

    return bundle.get_module()


def install_ipopo(framework):
    """
    Installs and starts the iPOPO bundle. Returns the iPOPO service

    @param framework: A Pelix framework instance
    @return: The iPOPO service
    @raise Exception: The iPOPO service cannot be found
    """
    context = framework.get_bundle_context()
    assert isinstance(context, BundleContext)

    # Install & start the bundle
    install_bundle(framework, "pelix.ipopo.core")

    # Get the service
    service = constants.get_ipopo_svc_ref(context)
    if service is None:
        raise Exception("iPOPO Service not found")

    return service[1]

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
            self.assertRaises(ValueError, decorators.Requires, "field", invalid)

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
            self.assertRaises(ValueError, decorators.Requires, "field", invalid)

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.Requires("field", "spec"),
                              invalid)

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
        self.assertTrue(instance.controller, "Default service controller is On")
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
        self.assertTrue(instance._test_ctrl, "Default service controller is On")
        self.assertIsNone(instance._req_1, "Requirement is not None")
        self.assertEqual(instance.prop_1, 10, "Constructor property value lost")
        self.assertEqual(instance.usable, True, "Incorrect property value")
        del instance

        # Instantiate component A (validated)
        instance = ipopo.instantiate(module.FACTORY_A, NAME_A)

        # Check fields presence and values
        self.assertTrue(instance._test_ctrl, "Default service controller is On")
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
        module_A = install_bundle(self.framework, "tests.ipopo_bundle")
        module_B = install_bundle(self.framework, "tests.ipopo_bundle_copy")

        # Ensure that the module providing the factory is the correct one
        self.assertIs(module_A,
                  ipopo.get_factory_bundle(module_A.BASIC_FACTORY).get_module(),
                  "Duplicated factory is not provided by the first module")
        self.assertIs(module_A,
                  ipopo.get_factory_bundle(module_B.BASIC_FACTORY).get_module(),
                  "Duplicated factory is not provided by the first module")

        # Component of module A must be there
        self.assertIsNotNone(
                         ipopo.get_instance_details(module_A.BASIC_INSTANCE),
                         "Component from module A not started")

        # Component of module B must be absent
        self.assertRaises(ValueError,
                          ipopo.get_instance_details, module_B.BASIC_INSTANCE)


# ------------------------------------------------------------------------------

class LifeCycleTest(unittest.TestCase):
    """
    Tests the component life cycle
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
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)


    def testSingleNormal(self):
        """
        Test a single component life cycle
        """
        # Assert it is not yet in the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A),
                        "Instance is already in the registry")

        # Instantiate the component
        compoA = self.ipopo.instantiate(self.module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A),
                        "Instance is not in the registry")

        # Invalidate the component
        self.ipopo.invalidate(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Assert it is still in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A),
                        "Instance is not in the registry")

        # Kill (remove) the component
        self.ipopo.kill(NAME_A)

        # No event
        self.assertEqual([], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))

        # Assert it has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A),
                        "Instance is still in the registry")


    def testSingleKill(self):
        """
        Test a single component life cycle
        """
        # Assert it is not yet in the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A),
                        "Instance is already in the registry")

        # Instantiate the component
        compoA = self.ipopo.instantiate(self.module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A),
                        "Instance is not in the registry")

        # Kill the component without invalidating it
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Assert it has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A),
                        "Instance is still in the registry")


    def testAutoRestart(self):
        """
        Tests the automatic re-instantiation of a component on bundle update
        """
        # Instantiate both kinds of components
        self.ipopo.instantiate(self.module.FACTORY_A, NAME_A,
                               {constants.IPOPO_AUTO_RESTART: True})

        self.ipopo.instantiate(self.module.FACTORY_B, NAME_B,
                               {constants.IPOPO_AUTO_RESTART: False})

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A),
                        "Instance A is not in the registry")
        self.assertTrue(self.ipopo.is_registered_instance(NAME_B),
                        "Instance B is not in the registry")

        # Update its bundle
        bundle = self.framework.get_bundle_by_name("tests.ipopo_bundle")
        bundle.update()

        # Assert the auto-restart component is still in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A),
                        "Instance A is not in the registry after update")

        # Assert the other one has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_B),
                         "Instance B is still in the registry")

        # Clean up
        self.ipopo.kill(NAME_A)

# ------------------------------------------------------------------------------

class FieldCallbackTest(unittest.TestCase):
    """
    Tests the component life cycle
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.module = install_bundle(self.framework,
                                     "tests.ipopo_fields_bundle")


    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)


    def testLifeCycleFieldCallback(self):
        """
        Tests the order of field notifications
        """
        # Consumer
        compo = self.ipopo.instantiate(self.module.FACTORY_C, "consumer")
        self.assertEqual(compo.states, [], "States should be empty")

        # Service A
        svc_a = self.ipopo.instantiate(self.module.FACTORY_A, "svcA")
        self.assertEqual(compo.states,
                          [self.module.BIND_A, self.module.BIND_FIELD_A],
                          "Service A bound incorrectly")
        del compo.states[:]

        # Service B
        svc_b = self.ipopo.instantiate(self.module.FACTORY_B, "svcB")
        self.assertEqual(compo.states,
                          [self.module.BIND_B, self.module.BIND_FIELD_B],
                          "Service B bound incorrectly")
        del compo.states[:]

        # Update A
        self.assertNotEqual(svc_a._prop, 42,
                             "Value already at requested value")
        compo.change_a(42)
        self.assertEqual(svc_a._prop, 42, "Value not changed")
        self.assertEqual(compo.states,
                          [self.module.UPDATE_FIELD_A, self.module.UPDATE_A],
                          "Service A updated incorrectly")
        del compo.states[:]

        # Update B
        self.assertNotEqual(svc_b._prop, -123,
                             "Value already at requested value")
        compo.change_b(-123)
        self.assertEqual(svc_b._prop, -123, "Value not changed")
        self.assertEqual(compo.states,
                          [self.module.UPDATE_FIELD_B, self.module.UPDATE_B],
                          "Service B updated incorrectly")
        del compo.states[:]

        # Kill service A
        self.ipopo.kill("svcA")
        self.assertEqual(compo.states,
                          [self.module.UNBIND_FIELD_A, self.module.UNBIND_A],
                          "Service A unbound incorrectly")
        del compo.states[:]

        # Kill service B
        self.ipopo.kill("svcB")
        self.assertEqual(compo.states,
                          [self.module.UNBIND_FIELD_B, self.module.UNBIND_B],
                          "Service B unbound incorrectly")
        del compo.states[:]

        # Kill consumer
        self.ipopo.kill("consumer")


    def testLifeCycleFieldCallbackIfValid(self):
        """
        Tests the order of field notifications with the "if_valid" flag
        """
        # Consumer
        compo = self.ipopo.instantiate(self.module.FACTORY_D, "consumer")
        self.assertEqual(compo.states, [], "States should be empty")

        # -- Component is invalid

        # Start Service B
        svc_b = self.ipopo.instantiate(self.module.FACTORY_B, "svcB")
        self.assertEqual(compo.states, [], "Service B bound: called")
        del compo.states[:]

        # Update B
        self.assertNotEqual(svc_b._prop, -123,
                             "Value already at requested value")
        compo.change_b(-123)
        self.assertEqual(svc_b._prop, -123, "Value not changed")
        self.assertEqual(compo.states, [], "Service B updated: called")
        del compo.states[:]

        # Kill service B
        self.ipopo.kill("svcB")
        self.assertEqual(compo.states, [], "Service B unbound: called")
        del compo.states[:]

        # Start Service A
        self.ipopo.instantiate(self.module.FACTORY_A, "svcA")
        del compo.states[:]

        # -- Component is valid

        # Start Service B
        svc_b = self.ipopo.instantiate(self.module.FACTORY_B, "svcB")
        self.assertEqual(compo.states, [self.module.BIND_FIELD_B],
                         "Service B bound: not called")
        del compo.states[:]

        # Update B
        self.assertNotEqual(svc_b._prop, -123,
                             "Value already at requested value")
        compo.change_b(-123)
        self.assertEqual(svc_b._prop, -123, "Value not changed")
        self.assertEqual(compo.states, [self.module.UPDATE_FIELD_B],
                         "Service B updated: not called")
        del compo.states[:]

        # Kill service B
        self.ipopo.kill("svcB")
        self.assertEqual(compo.states, [self.module.UNBIND_FIELD_B],
                         "Service B unbound: not called")
        del compo.states[:]

        # Restart Service B
        svc_b = self.ipopo.instantiate(self.module.FACTORY_B, "svcB")
        self.assertEqual(compo.states, [self.module.BIND_FIELD_B],
                         "Service B bound: not called")
        del compo.states[:]

        # Kill service A
        self.ipopo.kill("svcA")
        del compo.states[:]

        # -- Component is invalid (again)

        # Update B
        self.assertNotEqual(svc_b._prop, -123,
                             "Value already at requested value")
        compo.change_b(-123)
        self.assertEqual(svc_b._prop, -123, "Value not changed")
        self.assertEqual(compo.states, [], "Service B updated: called")
        del compo.states[:]

        # Kill service B
        self.ipopo.kill("svcB")
        self.assertEqual(compo.states, [], "Service B unbound: called")
        del compo.states[:]

        # Kill consumer
        self.ipopo.kill("consumer")

# ------------------------------------------------------------------------------

class InstantiateTest(unittest.TestCase):
    """
    Specific test case to test @Instantiate, as it needs a pure framework
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

        # Clean up
        self.ipopo = None
        self.framework = None


    def testInstantiate(self):
        """
        Tests the life cycle with an @Instantiate decorator
        """
        factory = "basic-component-factory"
        name = "basic-component"
        svc_spec = "basic-component-svc"

        # Assert the framework is clean
        self.assertFalse(self.ipopo.is_registered_factory(factory),
                         "Factory already registered")

        self.assertFalse(self.ipopo.is_registered_instance(name),
                         "Instance already registered")

        # Install the bundle
        context = self.framework.get_bundle_context()
        bundle = context.install_bundle("tests.ipopo_bundle")

        # Bundle is installed, assert that the framework is still clean
        self.assertFalse(self.ipopo.is_registered_factory(factory),
                         "Factory registered while the bundle is stopped")

        self.assertFalse(self.ipopo.is_registered_instance(name),
                         "Instance registered while the bundle is stopped")

        # Start the bundle
        bundle.start()

        # Assert the component has been registered
        self.assertTrue(self.ipopo.is_registered_factory(factory),
                         "Factory not registered while the bundle is started")

        self.assertTrue(self.ipopo.is_registered_instance(name),
                         "Instance not registered while the bundle is started")

        # Assert it has been validated
        ref = context.get_service_reference(svc_spec)
        self.assertIsNotNone(ref,
                             "No reference found (component not validated)")

        compo = context.get_service(ref)

        self.assertEqual(compo.states, [IPopoEvent.INSTANTIATED,
                                        IPopoEvent.VALIDATED],
                         "@Instantiate component should have been validated")
        del compo.states[:]

        # Stop the bundle
        bundle.stop()

        # Assert the component has been invalidated
        self.assertEqual(compo.states, [IPopoEvent.INVALIDATED],
                         "@Instantiate component should have been invalidated")

        # Assert the framework has been cleaned up
        self.assertFalse(self.ipopo.is_registered_factory(factory),
                         "Factory registered while the bundle has been stopped")

        self.assertFalse(self.ipopo.is_registered_instance(name),
                         "Instance registered while the bundle has been "
                         "stopped")

        # Ensure the service has been unregistered properly
        self.assertIsNone(context.get_service_reference(svc_spec),
                          "@Instantiate service is still there")


    def testNotRunning(self):
        """
        Checks that the instantiation is refused when iPOPO is stopped
        """
        # Stop the framework
        self.framework.stop()

        # iPOPO shouldn't be accessible, it must raise an exception
        self.assertRaises(ValueError, self.ipopo.instantiate,
                          'dummy', 'dummy', {})

# ------------------------------------------------------------------------------

class ProvidesTest(unittest.TestCase):
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
        FrameworkFactory.delete_framework(self.framework)


    def testProvides(self):
        """
        Tests if the provides decorator works
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Assert that the service is not yet available
        self.assertIsNone(context.get_service_reference(IEchoService),
                          "Service is already registered")

        # Instantiate the component
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        try:
            # Service should be there
            ref = context.get_service_reference(IEchoService)
            self.assertIsNotNone(ref, "Service hasn't been registered")

            # Second service should be there
            ref2 = context.get_service_reference("TestService")
            self.assertIsNotNone(ref, "Service hasn't been registered")

            # References must be different
            self.assertNotEqual(ref, ref2,
                                "Service references must be different")

            # Compare service instances
            svc = context.get_service(ref)
            self.assertIs(svc, compoA,
                          "Different instances for service and component")

            svc2 = context.get_service(ref2)
            self.assertEqual(svc, svc2, "Got different service instances")

            # Clean up
            context.unget_service(ref)
            context.unget_service(ref2)
            svc = None
            svc2 = None

            # Invalidate the component
            self.ipopo.invalidate(NAME_A)

            # Service should not be there anymore
            self.assertIsNone(context.get_service_reference(IEchoService),
                              "Service is still registered")

        finally:
            try:
                self.ipopo.kill(NAME_A)
            except:
                pass


    def testController(self):
        """
        Tests the service controller
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Assert that the service is not yet available
        self.assertIsNone(context.get_service_reference(IEchoService),
                          "Service is already registered")
        self.assertIsNone(context.get_service_reference("TestService"),
                          "TestService is already registered")

        # Instantiate the component
        self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        try:
            # Service should be there (controller default value is True)
            self.assertIsNotNone(context.get_service_reference(IEchoService),
                                 "EchoService hasn't been registered")

            ref = context.get_service_reference("TestService")
            self.assertIsNotNone(ref, "TestService hasn't been registered")

            # Get the service instance
            svc = context.get_service(ref)

            # Change the value of the controller
            svc.change_controller(False)
            self.assertIsNone(context.get_service_reference("TestService"),
                              "TestService hasn't been unregistered")
            self.assertIsNotNone(context.get_service_reference(IEchoService),
                                 "EchoService has been unregistered")

            # Re-change the value
            svc.change_controller(True)
            self.assertIsNotNone(context.get_service_reference("TestService"),
                                 "TestService hasn't been re-registered")
            self.assertIsNotNone(context.get_service_reference(IEchoService),
                                 "EchoService has been unregistered")

            # Invalidate the component
            self.ipopo.invalidate(NAME_A)

            # Re-change the value (once invalidated)
            svc.change_controller(True)

            # Service should not be there anymore
            self.assertIsNone(context.get_service_reference("TestService"),
                              "TestService is still registered")
            self.assertIsNone(context.get_service_reference(IEchoService),
                              "EchoService is still registered")

            # Clean up
            context.unget_service(ref)
            svc = None
            ref = None

        finally:
            try:
                self.ipopo.kill(NAME_A)
            except:
                pass

# ------------------------------------------------------------------------------

class RequirementTest(unittest.TestCase):
    """
    Tests the component requirements behavior
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


    def testCycleInner(self):
        """
        Tests if the component is bound, validated then invalidated.
        The component unbind call must come after it has been killed
        """
        module = install_bundle(self.framework)

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Instantiate B (bound then validated)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.BOUND,
                          IPopoEvent.VALIDATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Invalidate B
        self.ipopo.invalidate(NAME_B)
        self.assertEqual([IPopoEvent.INVALIDATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Uninstantiate B
        self.ipopo.kill(NAME_B)
        self.assertEqual([IPopoEvent.UNBOUND], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))

        # Uninstantiate A
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))


    def testCycleOuterEnd(self):
        """
        Tests if the required service is correctly unbound after the component
        invalidation
        """
        module = install_bundle(self.framework)

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # Instantiate B (bound then validated)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.BOUND,
                          IPopoEvent.VALIDATED], compoB.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoB.reset()

        # Uninstantiate A
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))

        self.assertEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Uninstantiate B
        self.ipopo.kill(NAME_B)
        self.assertEqual([], compoB.states,
                         "Invalid component states: {0}".format(compoA.states))


    def testCycleOuterStart(self):
        """
        Tests if the required service is correctly bound after the component
        instantiation
        """
        module = install_bundle(self.framework)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # B must have been validated
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Invalidate B
        self.ipopo.invalidate(NAME_B)
        self.assertEqual([IPopoEvent.INVALIDATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Uninstantiate B
        self.ipopo.kill(NAME_B)
        self.assertEqual([IPopoEvent.UNBOUND], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))

        # Uninstantiate A
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))


    def testConfiguredInstance(self):
        """
        Tests if the filter can be overridden by instance properties
        """
        module = install_bundle(self.framework)

        # The module filter
        properties_b = {constants.IPOPO_REQUIRES_FILTERS: \
                        {"service": "({0}=True)".format(module.PROP_USABLE)}}

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        # Set A unusable
        compoA.change(False)

        # Instantiate B (must not be bound)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B,
                                        properties_b)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Set A usable
        compoA.change(True)

        # B must be bound and validated
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Set A unusable (again)
        compoA.change(False)

        # B must have been invalidated
        self.assertEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))


    def testAggregateDependency(self):
        """
        Tests a component that aggregates dependencies
        """
        # Install the test bundle
        module = install_bundle(self.framework)

        # Instantiate C (no requirement present, but they are optional)
        compoC = self.ipopo.instantiate(module.FACTORY_C, NAME_C)
        self.assertIsNone(compoC.services,
                          "Aggregate dependency without value must be None")
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Register a first service
        context = self.framework.get_bundle_context()
        reg = context.register_service(IEchoService, self, None)

        # The dependency must be injected
        self.assertIn(self, compoC.services, "Service not injected")
        self.assertEqual([IPopoEvent.BOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Instantiate A
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        # The dependency must be injected
        self.assertIn(self, compoC.services, "Service illegally removed")
        self.assertIn(compoA, compoC.services, "Service not injected")
        self.assertEqual([IPopoEvent.BOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Delete A
        self.ipopo.kill(NAME_A)

        # The dependency must have been removed
        self.assertNotIn(compoA, compoC.services, "Service not removed")
        self.assertIn(self, compoC.services, "Service illegally removed")
        self.assertEqual([IPopoEvent.UNBOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Instantiate A
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        self.assertIn(self, compoC.services, "Service illegally removed")
        self.assertIn(compoA, compoC.services, "Service not injected")
        self.assertEqual([IPopoEvent.BOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Unregister the first service
        reg.unregister()

        # The dependency must have been removed
        self.assertNotIn(self, compoC.services, "Service not removed")
        self.assertIn(compoA, compoC.services, "Service illegally removed")
        self.assertEqual([IPopoEvent.UNBOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Delete A
        self.ipopo.kill(NAME_A)

        # The dependency must have been removed
        self.assertIsNone(compoC.services,
                          "Aggregate dependency without value must be None")
        self.assertEqual([IPopoEvent.UNBOUND], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))
        compoC.reset()

        # Delete C
        self.ipopo.kill(NAME_C)
        self.assertEqual([IPopoEvent.INVALIDATED], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))


    def testAggregateDependencyLate(self):
        """
        Tests a component that aggregates dependencies, with one dependency
        already present before its instantiation
        """
        # Install the test bundle
        module = install_bundle(self.framework)

        # Register a first service
        context = self.framework.get_bundle_context()
        context.register_service(IEchoService, self, None)

        # Instantiate C (no requirement present, but they are optional)
        compoC = self.ipopo.instantiate(module.FACTORY_C, NAME_C)
        self.assertIn(self, compoC.services,
                      "Existing service not injected")
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.BOUND,
                          IPopoEvent.VALIDATED], compoC.states,
                         "Invalid component states: {0}".format(compoC.states))


    def testCallbackRaiser(self):
        """
        Tests exception handling during a callback
        """
        module = install_bundle(self.framework)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Set B in raiser mode
        compoB.raiser = True

        # Instantiate A (validated)
        log_off()
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        log_on()

        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # B must have been validated
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Uninstantiate A
        log_off()
        self.ipopo.kill(NAME_A)
        log_on()

        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states,
                         "Invalid component states: {0}".format(compoA.states))

        # Uninstantiate B
        self.assertEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))


    def testCallbackInstantiateStopper(self):
        """
        Tests exception handling during a callback
        """
        module = install_bundle(self.framework)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Set B in raiser mode
        compoB.fw_raiser = True
        compoB.fw_raiser_stop = False

        # Instantiate A (validated)
        log_off()
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        log_on()

        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states: {0}".format(compoA.states))
        compoA.reset()

        # B must have failed to start
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.UNBOUND],
                         compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Framework must still be active
        self.assertEqual(self.framework.get_state(), Bundle.ACTIVE,
                         "Framework has stopped")

        # B must have been automatically killed
        instances = [info[0] for info in self.ipopo.get_instances()]
        self.assertIn(NAME_A, instances, "Component A should still be there")
        self.assertNotIn(NAME_B, instances, "Component B still in instances")

        # Kill A
        self.ipopo.kill(NAME_A)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states,
                         "Invalid component states: {0}".format(compoB.states))
        compoB.reset()

        # Set B in raiser mode
        compoB.fw_raiser = True
        compoB.fw_raiser_stop = True

        # Instantiate A (validated)
        log_off()
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        log_on()

        # Framework must have stopped now
        self.assertEqual(self.framework.get_state(), Bundle.RESOLVED,
                         "Framework hasn't stopped")


    def testRequiresMap(self):
        """
        Tests the behavior of RequiresMap
        """
        module = install_bundle(self.framework)
        context = self.framework.get_bundle_context()

        # Instantiate "map" component
        compo = self.ipopo.instantiate(module.FACTORY_MAP, "map.component")
        self.assertListEqual([IPopoEvent.INSTANTIATED], compo.states,
                             "Component not instantiated...")
        compo.reset()

        # Add a service, with no property
        svc1 = object()
        reg1 = context.register_service(module.MAP_SPEC_TEST, svc1, {})

        # Check insertion in dictionaries accepting None
        self.assertDictEqual({}, compo.single, "Injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({None: svc1}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1]}, compo.multiple_none,
                             "Not injected in multiple_none")

        # Check state
        self.assertListEqual([], compo.states, "Component validated...")
        compo.reset()

        # Add a service, with property for "single"
        svc2 = object()
        value2 = 42
        reg2 = context.register_service(module.MAP_SPEC_TEST, svc2,
                                        {"single.key": value2})

        # Check state
        self.assertListEqual([IPopoEvent.VALIDATED], compo.states,
                             "Component not validated...")
        compo.reset()

        # Check insertion in dictionaries "single"
        self.assertDictEqual({value2: svc2}, compo.single,
                             "Not injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({None: svc1, value2: svc2}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1, svc2]}, compo.multiple_none,
                             "Not injected in multiple_none")

        # Update the service to be injected in both single and multiple
        value2b = "some test value"
        reg2.set_properties({"single.key": value2, "other.key": value2b})

        # Check insertion in both dictionaries
        self.assertDictEqual({value2: svc2}, compo.single,
                             "Not injected in single")
        self.assertDictEqual({value2b: [svc2]}, compo.multiple,
                             "Not injected in multiple")
        self.assertDictEqual({None: svc1, value2: svc2}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1], value2b: [svc2]},
                             compo.multiple_none,
                             "Not injected in multiple_none")

        # Remove the "other key"
        reg2.set_properties({"other.key": None})

        # Check removal in dictionaries "multiple"
        self.assertDictEqual({value2: svc2}, compo.single,
                             "Not injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({None: svc1, value2: svc2}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1, svc2]}, compo.multiple_none,
                             "Injected in multiple_none")

        # Remove the "single key"
        reg2.set_properties({"single.key": None})

        # Check state
        self.assertListEqual([IPopoEvent.INVALIDATED], compo.states,
                             "Component not invalidated...")
        compo.reset()

        self.assertDictEqual({}, compo.single, "Injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({None: svc1}, compo.single_none,
                             "Replacement in single_none")
        self.assertDictEqual({None: [svc1, svc2]}, compo.multiple_none,
                             "Not injected in multiple_none")

        # Unregister service
        reg2.unregister()

        self.assertDictEqual({}, compo.single, "Injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({None: svc1}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1]}, compo.multiple_none,
                             "Not injected in multiple_none")

        # Update service 1 properties
        value1 = ("why", "not", "use", "tuple")
        reg1.set_properties({"single.key": value1})

        # Check state
        self.assertListEqual([IPopoEvent.VALIDATED], compo.states,
                             "Component not validated...")
        compo.reset()

        self.assertDictEqual({value1: svc1}, compo.single,
                             "Not injected in single")
        self.assertDictEqual({}, compo.multiple, "Injected in multiple")
        self.assertDictEqual({value1: svc1}, compo.single_none,
                             "Not injected in single_none")
        self.assertDictEqual({None: [svc1]}, compo.multiple_none,
                             "Injected in multiple_none")

        # Remove components
        reg1.unregister()

        # Check state
        self.assertListEqual([IPopoEvent.INVALIDATED], compo.states,
                             "Component not invalidated...")
        compo.reset()

# ------------------------------------------------------------------------------

class UtilitiesTest(unittest.TestCase):
    """
    Tests the utility methods
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
        self.framework = None
        self.context = None


    def testConstantGetReference(self):
        """
        Tests the ipopo.constants.get_service_reference() method
        """
        # Try without the bundle
        self.assertIsNone(constants.get_ipopo_svc_ref(self.context),
                          "iPOPO service found while not installed.")

        # Install the iPOPO bundle
        ipopo_svc = install_ipopo(self.framework)

        # Test the method result
        ref, svc = constants.get_ipopo_svc_ref(self.context)
        self.assertIsNotNone(ref, "Invalid service reference")
        self.assertIs(svc, ipopo_svc, "Found a different service.")

        # Stop the iPOPO bundle
        ref.get_bundle().stop()

        # Ensure the service is not accessible anymore
        self.assertIsNone(constants.get_ipopo_svc_ref(self.context),
                          "iPOPO service found while stopped.")

        # Uninstall the bundle
        ref.get_bundle().uninstall()

        # Ensure the service is not accessible anymore
        self.assertIsNone(constants.get_ipopo_svc_ref(self.context),
                          "iPOPO service found while stopped.")


    def testConstantContext(self):
        """
        Tests ipopo.constants.use_ipopo()
        """
        # Try without the bundle
        self.assertRaises(pelix.BundleException,
                          constants.use_ipopo(self.context).__enter__)

        # Start the iPOPO bundle
        bundle = self.context.install_bundle("pelix.ipopo.core")
        bundle.start()

        # Get the iPOPO service reference
        # (the only one registered in this bundle)
        ipopo_ref = bundle.get_registered_services()[0]

        # Use it
        with constants.use_ipopo(self.context) as ipopo:
            # Test the usage information
            self.assertIn(self.context.get_bundle(),
                          ipopo_ref.get_using_bundles(),
                          "Bundles using iPOPO not updated")

            # Get the service the Pelix way
            ipopo_svc = self.context.get_service(ipopo_ref)

            # Test the service object
            self.assertIs(ipopo, ipopo_svc, "Found a different service.")

            # Clean up the test usage
            self.context.unget_service(ipopo_ref)
            ipopo_svc = None

            # Re-test the usage information
            self.assertIn(self.context.get_bundle(),
                          ipopo_ref.get_using_bundles(),
                          "Bundles using iPOPO not kept")

        # Test the usage information
        self.assertNotIn(self.context.get_bundle(),
                         ipopo_ref.get_using_bundles(),
                         "Bundles using iPOPO kept after block")

        # Stop the iPOPO bundle
        bundle.stop()

        # Ensure the service is not accessible anymore
        self.assertRaises(pelix.BundleException,
                          constants.use_ipopo(self.context).__enter__)

        # Uninstall the bundle
        bundle.uninstall()

        # Ensure the service is not accessible anymore
        self.assertRaises(pelix.BundleException,
                          constants.use_ipopo(self.context).__enter__)

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
        DummyClass = decorators.ComponentFactory("dummy-factory") \
                     (
                        decorators.Requires("field", "req")
                        (DummyClass)
                     )

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
        bundle_name = "tests.simple_bundle"
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
            self.assertRaises(ValueError, decorators._get_specifications, empty)

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

class SimpleCoreTests(unittest.TestCase):
    """
    Tests the core methods and classes
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo_bundle = install_bundle(self.framework, "pelix.ipopo.core")


    def tearDown(self):
        """
        Called after each test
        """
        FrameworkFactory.delete_framework(self.framework)


    def testRequirement(self):
        """
        Tests the Requirement class type checking
        """
        Requirement = contexts.Requirement

        # Invalid specification type
        for invalid in (None, ["specification"], 1234):
            self.assertRaises(TypeError, Requirement, invalid)

        # Empty content
        self.assertRaises(ValueError, Requirement, "")

        # Invalid filter type
        for invalid in (123, ["a", "b"]):
            self.assertRaises(TypeError, Requirement, "spec",
                              spec_filter=invalid)

        # Valid values
        without_filter = Requirement("spec")
        with_filter = Requirement("spec", spec_filter="(test=True)")

        # Match test
        self.assertFalse(without_filter.matches(None),
                        "Should never match with None")
        self.assertFalse(with_filter.matches(None),
                         "Should never match with None")

        for invalid in (None, "False", False, [False]):
            props = {pelix.OBJECTCLASS: "spec", "test": invalid}
            self.assertTrue(without_filter.matches(props),
                            "Should match without filter: {0}".format(props))
            self.assertFalse(with_filter.matches(props),
                             "Shouldn't match with filter: {0}".format(props))

        for valid in ("True", True, [True]):
            props = {pelix.OBJECTCLASS: "spec", "test": valid}
            self.assertTrue(without_filter.matches(props),
                            "Should match without filter: {0}".format(props))
            self.assertTrue(with_filter.matches(props),
                            "Should match with filter: {0}".format(props))


    def testRequirementEquality(self):
        """
        Tests Requirement equality test
        """
        Requirement = contexts.Requirement

        req_1 = Requirement("spec_1", True, True, spec_filter="(test=True)")

        # Identity
        self.assertEqual(req_1, req_1, "Requirement is not equal to itself")

        # Different types
        for req_2 in (None, "spec_1", [], {}):
            self.assertNotEqual(req_1, req_2,
                                "Requirement should not be equal to {0}" \
                                .format(req_1))

        # Copy
        req_2 = req_1.copy()
        self.assertEqual(req_1, req_1, "Requirement is not equal to its copy")

        # Different filter
        req_2.set_filter("(test=False)")
        self.assertNotEqual(req_1, req_2,
                            "Requirements are equal with different filter")
        req_2.filter = req_1.filter

        # Different flags
        req_2.optional = not req_1.optional
        self.assertNotEqual(req_1, req_2,
                        "Requirements are equal with different optional flag")

        req_2.aggregate = not req_1.aggregate
        self.assertNotEqual(req_1, req_2,
                        "Requirements are equal with different flags")

        req_2.optional = req_1.optional
        self.assertNotEqual(req_1, req_2,
                        "Requirements are equal with different aggregate flags")


    def testCopyFactoryContext(self):
        """
        Tests the copy of a FactoryContext bean
        """
        FactoryContext = contexts.FactoryContext
        Requirement = contexts.Requirement

        # Prepare a requirement
        req_1 = Requirement("spec_1", True, True,
                            spec_filter="(test=True)")

        # Prepare a context (content type is not tested)
        context = FactoryContext()
        context.bundle_context = 0
        context.callbacks['callback'] = 'fct'
        context.name = 'name'
        context.properties['prop'] = 42
        context.properties_fields['field_prop'] = 'prop'

        context.set_handler(constants.HANDLER_PROVIDES, ('provides', None))
        context.set_handler(constants.HANDLER_REQUIRES,
                            {'field_req': req_1})

        # Identity test
        self.assertEqual(context, context, "Identity error")

        # Copy test
        context_2 = context.copy()
        self.assertEqual(context, context_2, "Copy equality error")
        self.assertIsNot(req_1, context_2, "Requirements must be copied")

# ------------------------------------------------------------------------------

class IPopoServiceTest(unittest.TestCase):
    """
    Tests the utility methods of the iPOPO service
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


    def testFactoriesRegistration(self):
        """
        Tests the (un)register_factory and get_factories behavior
        """
        FACTORY = "dummy-factory"
        context = self.framework.get_bundle_context()

        @decorators.ComponentFactory(FACTORY)
        class TestComponent(object):
            pass

        class UnManipulatedClass(object):
            pass

        # Test if the framework is clean
        factories_1 = self.ipopo.get_factories()
        self.assertEqual(len(factories_1), 0,
                         "Some factories are already registered.")

        self.assertFalse(self.ipopo.is_registered_factory(FACTORY),
                         "Test factory already registered")

        # Test type checking
        self.assertRaises(ValueError, self.ipopo.register_factory, None, None)
        self.assertRaises(ValueError, self.ipopo.register_factory, context,
                          None)
        self.assertRaises(ValueError, self.ipopo.register_factory, None,
                          TestComponent)
        self.assertRaises(TypeError, self.ipopo.register_factory, context,
                          UnManipulatedClass)
        self.assertRaises(TypeError, self.ipopo.register_factory, context,
                          TestComponent())

        self.assertEqual(len(factories_1), 0,
                         "Some factories have already bean registered.")
        self.assertFalse(self.ipopo.is_registered_factory(FACTORY),
                         "Test factory already registered")

        # Register the factory
        self.assertTrue(self.ipopo.register_factory(context, TestComponent))

        self.assertTrue(self.ipopo.is_registered_factory(FACTORY),
                         "Test factory not registered")

        # Can't do it twice
        self.assertRaises(ValueError, self.ipopo.register_factory, context,
                          TestComponent)

        # Test the get_factories method
        factories_2 = self.ipopo.get_factories()
        self.assertIn(FACTORY, factories_2,
                      "Test factory not in get_factories()")

        self.assertIsNot(factories_1, factories_2,
                         "get_factories() must not return the same object")

        # Unregister the factory
        for invalid in (None, "", "Dummy", [FACTORY]):
            self.assertFalse((self.ipopo.unregister_factory(invalid)),
                             "Invalid factory unregistered: {0}"\
                             .format(invalid))

        self.assertTrue(self.ipopo.unregister_factory(FACTORY))
        self.assertNotIn(FACTORY, self.ipopo.get_factories(),
                         "Test factory still in get_factories()")

        self.assertFalse(self.ipopo.is_registered_factory(FACTORY),
                         "Test factory still registered")

        # We can do it only once
        self.assertFalse(self.ipopo.unregister_factory(FACTORY))


    def testGetFactoryBundle(self):
        """
        Tests the get_factory_bundle() method
        """
        FACTORY = "dummy-factory"
        context = self.framework.get_bundle_context()

        @decorators.ComponentFactory(FACTORY)
        class TestComponent(object):
            pass

        # We must have a ValueError
        self.assertRaises(ValueError, self.ipopo.get_factory_bundle, FACTORY)

        # Register the factory
        self.ipopo.register_factory(context, TestComponent)

        # Test the factory bundle
        self.assertIs(self.ipopo.get_factory_bundle(FACTORY), self.framework,
                      "Invalid factory bundle")

        # Unregister it
        self.ipopo.unregister_factory(FACTORY)

        # We must have a ValueError
        self.assertRaises(ValueError, self.ipopo.get_factory_bundle, FACTORY)


    def testGetInstanceDetails(self):
        """
        Instance details method test
        """
        module = install_bundle(self.framework)

        # Invalid component names
        for invalid in (None, "", [1], ["a", "b"]):
            self.assertRaises(ValueError, self.ipopo.get_instance_details,
                              invalid)

        # Get its details
        details = self.ipopo.get_instance_details(module.BASIC_INSTANCE)

        # Test if instance details are really in the output
        self.assertIs(type(details), dict,
                      "Details result must be a dictionary")

        self.assertEqual(details['factory'], module.BASIC_FACTORY,
                         "Invalid factory name")
        self.assertEqual(details['name'], module.BASIC_INSTANCE,
                         "Invalid component name")

        self.assertIs(type(details['state']), int,
                      "Component state must be an integer")
        self.assertIs(type(details['services']), dict,
                      "Services details must be in a dictionary")
        self.assertIs(type(details['dependencies']), dict,
                      "Dependencies details must be in a dictionary")


    def testIPopoStartInstalled(self):
        """
        Tests if iPOPO starts instances of already installed bundles
        """
        # Uninstall the iPOPO bundle
        ipopo_bundle = self.framework.get_bundle_by_name("pelix.ipopo.core")
        ipopo_bundle.uninstall()
        self.ipopo = None

        # Install the test bundle
        module = install_bundle(self.framework)

        # Install iPOPO
        self.ipopo = install_ipopo(self.framework)

        # Test if the automatic instance is there
        self.assertTrue(self.ipopo.is_registered_factory(module.BASIC_FACTORY),
                        "Factory not registered")

        self.assertTrue(
                    self.ipopo.is_registered_instance(module.BASIC_INSTANCE),
                    "Component not created")


    def testInstantiate(self):
        """
        Tests the instantiate method
        """
        FACTORY = "dummy-factory"
        FACTORY_2 = "dummy-factory-2"
        INSTANCE = "dummy-instance"
        context = self.framework.get_bundle_context()

        @decorators.ComponentFactory(FACTORY)
        class TestComponent(object):
            pass

        # Invalid name
        for invalid in (None, "", [1]):
            self.assertRaises(ValueError, self.ipopo.instantiate,
                              invalid, INSTANCE)

            self.assertRaises(ValueError, self.ipopo.instantiate,
                              FACTORY, invalid)

        # Unknown factory -> Type Error
        self.assertRaises(TypeError, self.ipopo.instantiate, FACTORY, INSTANCE)

        # Register factory
        self.ipopo.register_factory(context, TestComponent)
        self.ipopo.instantiate(FACTORY, INSTANCE)

        # Already running -> Value Error
        self.assertRaises(ValueError, self.ipopo.instantiate, FACTORY, INSTANCE)
        self.ipopo.kill(INSTANCE)

        # Exception on instantiate -> Type Error
        @decorators.ComponentFactory(FACTORY_2)
        class TestComponent2(object):
            def __init__(self):
                raise NotImplementedError

        self.ipopo.register_factory(context, TestComponent2)

        log_off()
        self.assertRaises(TypeError, self.ipopo.instantiate, FACTORY_2,
                          INSTANCE)
        log_on()


    def testIPopoEvents(self):
        """
        Tests iPOPO event listener
        """
        FACTORY = "dummy-factory"
        INSTANCE = "dummy-instance"
        context = self.framework.get_bundle_context()

        @decorators.ComponentFactory(FACTORY)
        class TestComponent(object):
            pass

        class Listener(object):
            """
            iPOPO event listener
            """
            def __init__(self):
                self.events = []

            def count(self):
                return len(self.events)

            def reset(self):
                del self.events[:]

            def handle_ipopo_event(self, event):
                self.events.append(event)


        def check_event(event, kind, factory, instance):
            """
            Tests the validity of an event
            """
            self.assertEqual(event.get_kind(), kind,
                             "Excepted kind: {0} / got: {1}" \
                             .format(kind, event.get_kind()))

            self.assertEqual(event.get_factory_name(), factory,
                             "Excepted factory: {0} / got: {1}" \
                             .format(factory, event.get_factory_name()))

            self.assertEqual(event.get_component_name(), instance,
                             "Excepted instance: {0} / got: {1}" \
                             .format(instance, event.get_component_name()))


        # Register the listener
        listener = Listener()
        self.assertTrue(self.ipopo.add_listener(listener),
                        "Listener not registered")

        self.assertFalse(self.ipopo.add_listener(listener),
                        "Listener registered twice")

        # Test events
        self.assertEqual(listener.count(), 0, "Non empty events list")

        # .. register factory
        self.ipopo.register_factory(context, TestComponent)
        self.assertEqual(listener.count(), 1, "Registration event not received")
        check_event(listener.events[0], IPopoEvent.REGISTERED, FACTORY, None)

        # .. instantiate
        listener.reset()
        self.ipopo.instantiate(FACTORY, INSTANCE)

        self.assertEqual(listener.count(), 2,
                         "Validation event not received")
        check_event(listener.events[0], IPopoEvent.INSTANTIATED, FACTORY,
                    INSTANCE)
        check_event(listener.events[1], IPopoEvent.VALIDATED, FACTORY, INSTANCE)

        # .. kill
        listener.reset()
        self.ipopo.kill(INSTANCE)

        self.assertEqual(listener.count(), 2, "Kill events not received")
        check_event(listener.events[0], IPopoEvent.INVALIDATED, FACTORY,
                    INSTANCE)
        check_event(listener.events[1], IPopoEvent.KILLED, FACTORY, INSTANCE)

        # .. unregister factory
        listener.reset()
        self.ipopo.unregister_factory(FACTORY)

        self.assertEqual(listener.count(), 1,
                         "Unregistration event not received")
        check_event(listener.events[0], IPopoEvent.UNREGISTERED, FACTORY, None)


        # Unregister the listener
        self.assertTrue(self.ipopo.remove_listener(listener),
                        "Listener not unregistered")

        self.assertFalse(self.ipopo.remove_listener(listener),
                        "Listener unregistered twice")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
