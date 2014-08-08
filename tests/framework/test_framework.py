#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix framework test module. Tests the framework, bundles handling, service
handling and events.

:author: Thomas Calmant
"""

# Tests
from tests import log_on, log_off

# Pelix
from pelix.framework import FrameworkFactory, Bundle, BundleException, \
    BundleContext

# Standard library
import os
import sys
import threading
import time

try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

SIMPLE_BUNDLE = "tests.framework.simple_bundle"

# ------------------------------------------------------------------------------


def _framework_killer(framework, wait_time):
    """
    Waits *time* seconds before calling framework.stop().

    :param framework: Framework to stop
    :param wait_time: Time to wait (seconds) before stopping the framework
    """
    time.sleep(wait_time)
    framework.stop()


class FrameworkTest(unittest.TestCase):
    """
    Tests the framework factory properties
    """
    def setUp(self):
        """
        Sets up tests variables
        """
        self.stopping = False

    def tearDown(self):
        """
        Cleans up the tests variables
        """
        if SIMPLE_BUNDLE in sys.modules:
            del sys.modules[SIMPLE_BUNDLE]

    def testBundleZero(self):
        """
        Tests if bundle 0 is the framework
        """
        framework = FrameworkFactory.get_framework()

        self.assertIsNone(framework.get_bundle_by_name(None),
                          "None name is not bundle 0")

        self.assertIs(framework, framework.get_bundle_by_id(0),
                      "Invalid bundle 0")

        pelix_name = framework.get_symbolic_name()
        self.assertIs(framework, framework.get_bundle_by_name(pelix_name),
                      "Invalid system bundle name")

        FrameworkFactory.delete_framework(framework)

    def testBundleStart(self):
        """
        Tests if a bundle can be started before the framework itself
        """
        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Install a bundle
        bundle = context.install_bundle(SIMPLE_BUNDLE)

        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Bundle should be in RESOLVED state")

        # Starting the bundle now should fail
        self.assertRaises(BundleException, bundle.start)
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Bundle should be in RESOLVED state")

        # Start the framework
        framework.start()

        # Bundle should have been started now
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE,
                         "Bundle should be in ACTIVE state")

        # Stop the framework
        framework.stop()

        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Bundle should be in RESOLVED state")

        # Try to start the bundle again (must fail)
        self.assertRaises(BundleException, bundle.start)
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Bundle should be in RESOLVED state")

        FrameworkFactory.delete_framework(framework)

    def testFrameworkDoubleStart(self):
        """
        Tests double calls to start and stop
        """
        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()

        # Register the stop listener
        context.add_framework_stop_listener(self)

        self.assertTrue(framework.start(), "Framework couldn't be started")
        self.assertFalse(framework.start(), "Framework started twice")

        # Stop the framework
        self.assertTrue(framework.stop(), "Framework couldn't be stopped")
        self.assertTrue(self.stopping, "Stop listener not called")
        self.stopping = False

        self.assertFalse(framework.stop(), "Framework stopped twice")
        self.assertFalse(self.stopping, "Stop listener called twice")

        FrameworkFactory.delete_framework(framework)

    def testFrameworkRestart(self):
        """
        Tests call to Framework.update(), that restarts the framework
        """
        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()

        # Register the stop listener
        context.add_framework_stop_listener(self)

        # Calling update while the framework is stopped should do nothing
        framework.update()
        self.assertFalse(self.stopping, "Stop listener called")

        # Start and update the framework
        self.assertTrue(framework.start(), "Framework couldn't be started")
        framework.update()

        # The framework must have been stopped and must be active
        self.assertTrue(self.stopping, "Stop listener not called")
        self.assertEqual(framework.get_state(), Bundle.ACTIVE,
                         "Framework hasn't been restarted")

        framework.stop()
        FrameworkFactory.delete_framework(framework)

    def testFrameworkStartRaiser(self):
        """
        Tests framework start and stop with a bundle raising exception
        """
        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()

        # Register the stop listener
        context.add_framework_stop_listener(self)

        # Install the bundle
        bundle = context.install_bundle(SIMPLE_BUNDLE)
        module = bundle.get_module()

        # Set module in raiser mode
        module.raiser = True

        # Framework can start...
        log_off()
        self.assertTrue(framework.start(), "Framework should be started")
        log_on()

        self.assertEqual(framework.get_state(), Bundle.ACTIVE,
                         "Framework should be in ACTIVE state")

        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Bundle should be in RESOLVED state")

        # Stop the framework
        self.assertTrue(framework.stop(), "Framework should be stopped")

        # Remove raiser mode
        module.raiser = False

        # Framework can start
        self.assertTrue(framework.start(), "Framework couldn't be started")
        self.assertEqual(framework.get_state(), Bundle.ACTIVE,
                         "Framework should be in ACTIVE state")
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE,
                         "Bundle should be in ACTIVE state")

        # Set module in raiser mode
        module.raiser = True

        # Stop the framework
        log_off()
        self.assertTrue(framework.stop(), "Framework couldn't be stopped")
        log_on()

        self.assertTrue(self.stopping, "Stop listener not called")

        FrameworkFactory.delete_framework(framework)

    def testFrameworkStopRaiser(self):
        """
        Tests framework start and stop with a bundle raising exception
        """
        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()

        # Register the stop listener
        context.add_framework_stop_listener(self)

        # Install the bundle
        bundle = context.install_bundle(SIMPLE_BUNDLE)
        module = bundle.get_module()

        # Set module in non-raiser mode
        module.raiser = False

        # Framework can start...
        log_off()
        self.assertTrue(framework.start(), "Framework should be started")
        self.assertEqual(framework.get_state(), Bundle.ACTIVE,
                         "Framework should be in ACTIVE state")
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE,
                         "Bundle should be in ACTIVE state")
        log_on()

        # Set module in raiser mode
        module.raiser = True

        # Bundle must raise the exception and stay active
        log_off()
        self.assertRaises(BundleException, bundle.stop)
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Bundle should be in RESOLVED state")
        log_on()

        # Stop framework
        framework.stop()
        FrameworkFactory.delete_framework(framework)

    def testFrameworkStopper(self):
        """
        Tests FrameworkException stop flag handling
        """
        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()

        # Install the bundle
        bundle = context.install_bundle(SIMPLE_BUNDLE)
        module = bundle.get_module()

        # Set module in raiser stop mode
        module.fw_raiser = True
        module.fw_raiser_stop = True

        log_off()
        self.assertFalse(framework.start(), "Framework should be stopped")
        self.assertEqual(framework.get_state(), Bundle.RESOLVED,
                         "Framework should be stopped")
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Bundle should be stopped")
        log_on()

        # Set module in raiser non-stop mode
        module.fw_raiser_stop = False

        log_off()
        self.assertTrue(framework.start(), "Framework should be stopped")
        self.assertEqual(framework.get_state(), Bundle.ACTIVE,
                         "Framework should be started")
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Bundle should be stopped")
        log_on()

        # Start the module
        module.fw_raiser = False
        bundle.start()
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE,
                         "Bundle should be active")

        # Set module in raiser mode
        module.fw_raiser = True
        module.fw_raiser_stop = True

        # Stop the framework
        log_off()
        self.assertTrue(framework.stop(), "Framework couldn't be stopped")
        self.assertEqual(framework.get_state(), Bundle.RESOLVED,
                         "Framework should be stopped")
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Bundle should be stopped")
        log_on()

        FrameworkFactory.delete_framework(framework)

    def testPropertiesWithPreset(self):
        """
        Test framework properties
        """
        pelix_test_name = "PELIX_TEST"
        pelix_test = "42"
        pelix_test_2 = "421"

        # Test with pre-set properties
        props = {pelix_test_name: pelix_test}
        framework = FrameworkFactory.get_framework(props)

        self.assertEqual(framework.get_property(pelix_test_name), pelix_test,
                         "Invalid property value (preset value not set)")

        # Pre-set property has priority
        os.environ[pelix_test_name] = pelix_test_2
        self.assertEqual(framework.get_property(pelix_test_name), pelix_test,
                         "Invalid property value (preset has priority)")
        del os.environ[pelix_test_name]

        FrameworkFactory.delete_framework(framework)

    def testPropertiesWithoutPreset(self):
        """
        Test framework properties
        """
        pelix_test_name = "PELIX_TEST"
        pelix_test = "42"

        # Test without pre-set properties
        framework = FrameworkFactory.get_framework()

        self.assertIsNone(framework.get_property(pelix_test_name),
                          "Magic property value")

        os.environ[pelix_test_name] = pelix_test
        self.assertEqual(framework.get_property(pelix_test_name), pelix_test,
                         "Invalid property value")
        del os.environ[pelix_test_name]

        FrameworkFactory.delete_framework(framework)

    def testAddedProperty(self):
        """
        Tests the add_property method
        """
        pelix_test_name = "PELIX_TEST"
        pelix_test = "42"
        pelix_test_2 = "123"

        # Test without pre-set properties
        framework = FrameworkFactory.get_framework()

        self.assertIsNone(framework.get_property(pelix_test_name),
                          "Magic property value")

        # Add the property
        self.assertTrue(framework.add_property(pelix_test_name, pelix_test),
                        "add_property shouldn't fail on first call")

        self.assertEqual(framework.get_property(pelix_test_name), pelix_test,
                         "Invalid property value")

        # Update the property (must fail)
        self.assertFalse(framework.add_property(pelix_test_name, pelix_test_2),
                         "add_property must fail on second call")

        self.assertEqual(framework.get_property(pelix_test_name), pelix_test,
                         "Invalid property value")

        FrameworkFactory.delete_framework(framework)

    def framework_stopping(self):
        """
        Called when framework is stopping
        """
        self.stopping = True

    def testStopListener(self):
        """
        Test the framework stop event
        """
        # Set up a framework
        framework = FrameworkFactory.get_framework()
        framework.start()
        context = framework.get_bundle_context()

        # Assert initial state
        self.assertFalse(self.stopping, "Invalid initial state")

        # Register the stop listener
        self.assertTrue(context.add_framework_stop_listener(self),
                        "Can't register the stop listener")

        log_off()
        self.assertFalse(context.add_framework_stop_listener(self),
                         "Stop listener registered twice")
        log_on()

        # Assert running state
        self.assertFalse(self.stopping, "Invalid running state")

        # Stop the framework
        framework.stop()

        # Assert the listener has been called
        self.assertTrue(self.stopping, "Stop listener hasn't been called")

        # Unregister the listener
        self.assertTrue(context.remove_framework_stop_listener(self),
                        "Can't unregister the stop listener")

        log_off()
        self.assertFalse(context.remove_framework_stop_listener(self),
                         "Stop listener unregistered twice")
        log_on()

        FrameworkFactory.delete_framework(framework)

    def testUninstall(self):
        """
        Tests if the framework raises an exception if uninstall() is called
        """
        # Set up a framework
        framework = FrameworkFactory.get_framework()
        self.assertRaises(BundleException, framework.uninstall)

        # Even once started...
        framework.start()
        self.assertRaises(BundleException, framework.uninstall)
        framework.stop()

        FrameworkFactory.delete_framework(framework)

    def testWaitForStop(self):
        """
        Tests the wait_for_stop() method
        """
        # Set up a framework
        framework = FrameworkFactory.get_framework()

        # No need to wait for the framework...
        self.assertTrue(framework.wait_for_stop(),
                        "wait_for_stop() must return True "
                        "on stopped framework")

        # Start the framework
        framework.start()

        # Start the framework killer
        threading.Thread(target=_framework_killer,
                         args=(framework, 0.5)).start()

        # Wait for stop
        start = time.time()
        self.assertTrue(framework.wait_for_stop(),
                        "wait_for_stop(None) should return True")
        end = time.time()
        self.assertLess(end - start, 1, "Wait should be less than 1 sec")

        FrameworkFactory.delete_framework(framework)

    def testWaitForStopTimeout(self):
        """
        Tests the wait_for_stop() method
        """
        # Set up a framework
        framework = FrameworkFactory.get_framework()
        framework.start()

        # Start the framework killer
        threading.Thread(target=_framework_killer,
                         args=(framework, 0.5)).start()

        # Wait for stop (timeout not raised)
        start = time.time()
        self.assertTrue(framework.wait_for_stop(1),
                        "wait_for_stop() should return True")
        end = time.time()
        self.assertLess(end - start, 1, "Wait should be less than 1 sec")

        # Restart framework
        framework.start()

        # Start the framework killer
        threading.Thread(target=_framework_killer,
                         args=(framework, 2)).start()

        # Wait for stop (timeout raised)
        start = time.time()
        self.assertFalse(framework.wait_for_stop(1),
                         "wait_for_stop() should return False")
        end = time.time()
        self.assertLess(end - start, 1.2, "Wait should be less than 1.2 sec")

        # Wait for framework to really stop
        framework.wait_for_stop()

        FrameworkFactory.delete_framework(framework)

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
