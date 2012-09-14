#!/usr/bin/env python
#-- Content-Encoding: UTF-8 --
"""
iPOPO test module. Tests both the iPOPO core module and decorators

:author: Thomas Calmant
"""

from pelix.ipopo import constants, decorators
from pelix.ipopo.core import IPopoEvent
from pelix.framework import FrameworkFactory, BundleContext
from tests.interfaces import IEchoService

import logging
import os
import unittest

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

# Set logging level
logging.basicConfig(level=logging.DEBUG)

NAME_A = "componentA"
NAME_B = "componentB"

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
        class BadClass:
            pass

        bad_types = (None, 12, "Bad", BadClass)

        # Define a decorable method
        def empty_method():
            """
            Dummy method
            """
            pass

        def correct_method(self, *args):
            """
            Dummy method
            """
            pass


        self.assertFalse(hasattr(empty_method, \
                                 constants.IPOPO_METHOD_CALLBACKS), \
                                 "The method is already tagged")

        self.assertFalse(hasattr(correct_method, \
                                 constants.IPOPO_METHOD_CALLBACKS), \
                                 "The method is already tagged")

        for decorator, callback in callbacks.items():

            # Ensure that the empty  method will fail being decorated
            self.assertRaises(TypeError, decorator, empty_method)

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


    def testInstantiate(self):
        """
        Tests the @Instantiate decorator
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

        self.assertEquals(compo.states, [IPopoEvent.INSTANTIATED,
                                         IPopoEvent.VALIDATED],
                          "@Instantiate component should have been validated")
        del compo.states[:]

        # Stop the bundle
        bundle.stop()

        # Assert the component has been invalidated
        self.assertEquals(compo.states, [IPopoEvent.INVALIDATED],
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


# ------------------------------------------------------------------------------

class LifeCycleTest(unittest.TestCase):
    """
    Tests the component life cyle
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

            svc = context.get_service(ref)
            self.assertIs(svc, compoA, \
                          "Different instances for service and component")
            context.unget_service(ref)
            svc = None

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
        self.assertEquals("'getpid'",
                          decorators.get_method_description(os.getpid),
                          "Invalid description of getpid()")


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
