#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO test module. Tests both the iPOPO core module and decorators

:author: Thomas Calmant
"""

from pelix.ipopo import constants, decorators
from pelix.ipopo.core import IPopoEvent, FactoryContext
from pelix.framework import FrameworkFactory, Bundle, BundleContext

from tests import log_on, log_off
from tests.interfaces import IEchoService

import logging
import os

try:
    import unittest2 as unittest

except ImportError:
    import unittest
    import tests
    tests.inject_unittest_methods()

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

# Set logging level
logging.basicConfig(level=logging.DEBUG)

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

    bid = context.install_bundle(bundle_name)
    bundle = context.get_bundle(bid)
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
    bid = context.install_bundle("pelix.ipopo.core")
    bundle = context.get_bundle(bid)
    bundle.start()

    # Get the service
    ref = context.get_service_reference(constants.IPOPO_SERVICE_SPECIFICATION)
    if ref is None:
        raise Exception("iPOPO Service not found")

    return context.get_service(ref)

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

        self.assertFalse(hasattr(empty_method, \
                                 constants.IPOPO_METHOD_CALLBACKS), \
                                 "The method is already tagged")

        self.assertFalse(hasattr(correct_method, \
                                 constants.IPOPO_METHOD_CALLBACKS), \
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
            self.assertIn(callback, getattr(correct_method, \
                                            constants.IPOPO_METHOD_CALLBACKS), \
                          "Decoration failed")

            # Assert that the decorator raises a TypeError on invalid elements
            for bad in bad_types:
                self.assertRaises(TypeError, decorator, bad)


    def testComponentFactory(self):
        """
        Tests the @ComponentFactory decorator
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
        parent_context = decorators._get_factory_context(DummyClass)
        self.assertEqual(parent_context.name, "DummyClassFactory",
                         "Invalid generated name")

        # Transform the child class
        decorators.ComponentFactory()(ChildClass)

        # Ensure the instantiation was not inherited
        self.assertIn(instance_name,
                      getattr(DummyClass, constants.IPOPO_INSTANCES),
                      "Instance disappeared of parent")

        # Child attribute is set to None in this case
        self.assertIsNone(getattr(ChildClass, constants.IPOPO_INSTANCES),
                          "Instances kept in child")


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
        decorators.Instantiate("test", {"id": 2})(DummyClass)

        instances = getattr(DummyClass, constants.IPOPO_INSTANCES)
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
            decorators.Provides("spec", empty)

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
            self.assertRaises(ValueError, decorators.Requires, empty)
            self.assertRaises(ValueError, decorators.Requires, "field", empty)

        # Invalid field or specification type
        for invalid in ([1, 2, 3], tuple((1, 2, 3)), 123):
            self.assertRaises(TypeError, decorators.Requires, invalid)
            self.assertRaises(ValueError, decorators.Requires, "field", invalid)

        # Invalid target
        for invalid in (None, method, 123):
            self.assertRaises(TypeError, decorators.Requires("field", "spec"),
                              invalid)

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
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A), \
                        "Instance is already in the registry")

        # Instantiate the component
        compoA = self.ipopo.instantiate(self.module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED], \
                         compoA.states, \
                         "Invalid component states : %s" % compoA.states)
        compoA.reset()

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A), \
                        "Instance is not in the registry")

        # Invalidate the component
        self.ipopo.invalidate(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states, \
                         "Invalid component states : %s" % compoA.states)
        compoA.reset()

        # Assert it is still in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A), \
                        "Instance is not in the registry")

        # Kill (remove) the component
        self.ipopo.kill(NAME_A)

        # No event
        self.assertEqual([], compoA.states, \
                         "Invalid component states : %s" % compoA.states)

        # Assert it has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A), \
                        "Instance is still in the registry")


    def testSingleKill(self):
        """
        Test a single component life cycle
        """
        # Assert it is not yet in the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A), \
                        "Instance is already in the registry")

        # Instantiate the component
        compoA = self.ipopo.instantiate(self.module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED], \
                         compoA.states, \
                         "Invalid component states : %s" % compoA.states)
        compoA.reset()

        # Assert it is in the registry
        self.assertTrue(self.ipopo.is_registered_instance(NAME_A), \
                        "Instance is not in the registry")

        # Kill the component without invalidating it
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states, \
                         "Invalid component states : %s" % compoA.states)
        compoA.reset()

        # Assert it has been removed of the registry
        self.assertFalse(self.ipopo.is_registered_instance(NAME_A), \
                        "Instance is still in the registry")

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

    def testInstantiate(self):
        """
        Tests the life cycle with an @Instantiate decorator
        """
        factory = "basic-component-factory"
        name = "basic-component"
        svc_spec = "basic-component-svc"
        bundle_name = "tests.ipopo_bundle"

        # Assert the framework is clean
        self.assertFalse(self.ipopo.is_registered_factory(factory),
                         "Factory already registered")

        self.assertFalse(self.ipopo.is_registered_instance(name),
                         "Instance already registered")

        # Install the bundle
        context = self.framework.get_bundle_context()
        bid = context.install_bundle(bundle_name)
        bundle = context.get_bundle(bid)

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
        self.assertIsNotNone(ref, "No reference found (component not validated)")

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
        self.assertIsNone(context.get_service_reference(IEchoService), \
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
            self.assertIsNone(context.get_service_reference(IEchoService), \
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
        self.assertIsNone(context.get_service_reference(IEchoService), \
                          "Service is already registered")
        self.assertIsNone(context.get_service_reference("TestService"), \
                          "TestService is already registered")

        # Instantiate the component
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)

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
            self.assertIsNone(context.get_service_reference("TestService"), \
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
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED], \
                         compoA.states, \
                         "Invalid component states : %s" % compoA.states)
        compoA.reset()

        # Instantiate B (bound then validated)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.BOUND, \
                          IPopoEvent.VALIDATED], compoB.states, \
                         "Invalid component states : %s" % compoB.states)
        compoB.reset()

        # Invalidate B
        self.ipopo.invalidate(NAME_B)
        self.assertEqual([IPopoEvent.INVALIDATED], compoB.states, \
                         "Invalid component states : %s" % compoB.states)
        compoB.reset()

        # Uninstantiate B
        self.ipopo.kill(NAME_B)
        self.assertEqual([IPopoEvent.UNBOUND], compoB.states, \
                         "Invalid component states : %s" % compoB.states)

        # Uninstantiate A
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states, \
                         "Invalid component states : %s" % compoA.states)


    def testCycleOuterEnd(self):
        """
        Tests if the required service is correctly unbound after the component
        invalidation
        """
        module = install_bundle(self.framework)

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED], \
                         compoA.states, \
                         "Invalid component states : %s" % compoA.states)
        compoA.reset()

        # Instantiate B (bound then validated)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.BOUND, \
                          IPopoEvent.VALIDATED], compoB.states, \
                         "Invalid component states : %s" % compoA.states)
        compoB.reset()

        # Uninstantiate A
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states, \
                         "Invalid component states : %s" % compoA.states)

        self.assertEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND], \
                         compoB.states, \
                         "Invalid component states : %s" % compoB.states)
        compoB.reset()

        # Uninstantiate B
        self.ipopo.kill(NAME_B)
        self.assertEqual([], compoB.states, \
                         "Invalid component states : %s" % compoA.states)


    def testCycleOuterStart(self):
        """
        Tests if the required service is correctly bound after the component
        instantiation
        """
        module = install_bundle(self.framework)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states, \
                         "Invalid component states : %s" % compoB.states)
        compoB.reset()

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED], \
                         compoA.states, \
                         "Invalid component states : %s" % compoA.states)
        compoA.reset()

        # B must have been validated
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED], \
                         compoB.states, \
                         "Invalid component states : %s" % compoB.states)
        compoB.reset()

        # Invalidate B
        self.ipopo.invalidate(NAME_B)
        self.assertEqual([IPopoEvent.INVALIDATED], compoB.states, \
                         "Invalid component states : %s" % compoB.states)
        compoB.reset()

        # Uninstantiate B
        self.ipopo.kill(NAME_B)
        self.assertEqual([IPopoEvent.UNBOUND], compoB.states, \
                         "Invalid component states : %s" % compoB.states)

        # Uninstantiate A
        self.ipopo.kill(NAME_A)
        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states, \
                         "Invalid component states : %s" % compoA.states)


    def testConfiguredInstance(self):
        """
        Tests if the filter can be overridden by instance properties
        """
        module = install_bundle(self.framework)

        # The module filter
        properties_b = {constants.IPOPO_REQUIRES_FILTERS: \
                        {"service": "(%s=True)" % module.PROP_USABLE}}

        # Instantiate A (validated)
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)

        # Set A unusable
        compoA.change(False)

        # Instantiate B (must not be bound)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B, \
                                        properties_b)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states, \
                         "Invalid component states : %s" % compoB.states)
        compoB.reset()

        # Set A usable
        compoA.change(True)

        # B must be bound and validated
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED], \
                         compoB.states, \
                         "Invalid component states : %s" % compoB.states)
        compoB.reset()

        # Set A unusable (again)
        compoA.change(False)

        # B must have been invalidated
        self.assertEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND], \
                         compoB.states, \
                         "Invalid component states : %s" % compoB.states)


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

        # TODO: set A unusable

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


    def testCallbackRaiser(self):
        """
        Tests exception handling during a callback
        """
        module = install_bundle(self.framework)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states, \
                         "Invalid component states : %s" % compoB.states)
        compoB.reset()

        # Set B in raiser mode
        compoB.raiser = True

        # Instantiate A (validated)
        log_off()
        compoA = self.ipopo.instantiate(module.FACTORY_A, NAME_A)
        log_on()

        self.assertEqual([IPopoEvent.INSTANTIATED, IPopoEvent.VALIDATED],
                         compoA.states,
                         "Invalid component states : %s" % compoA.states)
        compoA.reset()

        # B must have been validated
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.VALIDATED],
                         compoB.states,
                         "Invalid component states : %s" % compoB.states)
        compoB.reset()

        # Uninstantiate A
        log_off()
        self.ipopo.kill(NAME_A)
        log_on()

        self.assertEqual([IPopoEvent.INVALIDATED], compoA.states, \
                         "Invalid component states : %s" % compoA.states)

        # Uninstantiate B
        self.assertEqual([IPopoEvent.INVALIDATED, IPopoEvent.UNBOUND],
                         compoB.states, \
                         "Invalid component states : %s" % compoB.states)


    def testCallbackInstantiateStopper(self):
        """
        Tests exception handling during a callback
        """
        module = install_bundle(self.framework)

        # Instantiate B (no requirement present)
        compoB = self.ipopo.instantiate(module.FACTORY_B, NAME_B)
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states, \
                         "Invalid component states : %s" % compoB.states)
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
                         "Invalid component states : %s" % compoA.states)
        compoA.reset()

        # B must have failed to start
        self.assertEqual([IPopoEvent.BOUND, IPopoEvent.UNBOUND],
                         compoB.states,
                         "Invalid component states : %s" % compoB.states)
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
        self.assertEqual([IPopoEvent.INSTANTIATED], compoB.states, \
                         "Invalid component states : %s" % compoB.states)
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


# ------------------------------------------------------------------------------

class SimpleTests(unittest.TestCase):
    """
    Tests the component life cyle
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
                          constants.IPOPO_FACTORY_CONTEXT_DATA)

        # Convert the parent into a component
        DummyClass = decorators.ComponentFactory("dummy-factory") \
                     (
                        decorators.Requires("field", "req")
                        (DummyClass)
                     )

        # Get the context
        class_context = decorators._get_factory_context(DummyClass)
        self.assertIsNotNone(decorators._get_factory_context(DummyClass),
                             "Invalid factory context")

        # The child has a copy of the parent context
        child_context = decorators._get_factory_context(ChildClass)
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

if __name__ == "__main__":
    unittest.main()
