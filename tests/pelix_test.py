#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix framework test module. Tests the framework, bundles handling, service
handling and events.

:author: Thomas Calmant
"""

from pelix.framework import FrameworkFactory, Bundle, BundleException, \
    BundleContext, BundleEvent, ServiceEvent, ServiceReference

from tests import log_on, log_off
from tests.interfaces import IEchoService

import pelix.framework as pelix
import os
import logging
import sys
import threading
import time

try:
    import unittest2 as unittest

except ImportError:
    import unittest
    import tests
    tests.inject_unittest_methods()

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------

class BundlesTest(unittest.TestCase):
    """
    Pelix bundle registry tests
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        self.test_bundle_name = "tests.simple_bundle"
        # File path, without extension
        self.test_bundle_loc = os.path.abspath(\
                                    self.test_bundle_name.replace('.', os.sep))


    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)


    def testImportError(self):
        """
        Tries to install an invalid bundle
        """
        # Try to install the bundle
        self.assertRaises(BundleException, self.context.install_bundle,
                          "//Invalid Name\\\\")


    def testCompatibility(self, test_bundle_id=False):
        """
        Tests a bundle installation + start + stop

        @param test_bundle_id: If True, also tests if the test bundle ID is 1
        """
        # Install the bundle
        bundle_id = self.context.install_bundle(self.test_bundle_name)
        bundle = self.context.get_bundle(bundle_id)
        assert isinstance(bundle, Bundle)
        if test_bundle_id:
            self.assertEqual(bundle.get_bundle_id(), 1,
                             "Not the first bundle in framework")

        # Get the internal module
        module = bundle.get_module()

        # Assert initial state
        self.assertFalse(module.started, "Bundle should not be started yet")
        self.assertFalse(module.stopped, "Bundle should not be stopped yet")

        # Activator
        bundle.start()

        self.assertTrue(module.started, "Bundle should be started now")
        self.assertFalse(module.stopped, "Bundle should not be stopped yet")

        # De-activate
        bundle.stop()

        self.assertTrue(module.started, "Bundle should be changed")
        self.assertTrue(module.stopped, "Bundle should be stopped now")

        # Uninstall (validated in another test)
        bundle.uninstall()


    def testLifeCycle(self, test_bundle_id=False):
        """
        Tests a bundle installation + start + stop

        @param test_bundle_id: If True, also tests if the test bundle ID is 1
        """
        # Install the bundle
        bundle = self.context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        if test_bundle_id:
            self.assertEqual(bundle.get_bundle_id(), 1,
                             "Not the first bundle in framework")

        # Get the internal module
        module = bundle.get_module()

        # Assert initial state
        self.assertFalse(module.started, "Bundle should not be started yet")
        self.assertFalse(module.stopped, "Bundle should not be stopped yet")

        # Activator
        bundle.start()

        self.assertTrue(module.started, "Bundle should be started now")
        self.assertFalse(module.stopped, "Bundle should not be stopped yet")

        # De-activate
        bundle.stop()

        self.assertTrue(module.started, "Bundle should be changed")
        self.assertTrue(module.stopped, "Bundle should be stopped now")

        # Uninstall (validated in another test)
        bundle.uninstall()


    def testLifeCycleRecalls(self):
        """
        Tests a bundle installation + start + stop

        @param test_bundle_id: If True, also tests if the test bundle ID is 1
        """
        # Install the bundle
        bundle = self.context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        # Get the internal module
        module = bundle.get_module()

        # Assert initial state
        self.assertFalse(module.started, "Bundle should not be started yet")
        self.assertFalse(module.stopped, "Bundle should not be stopped yet")

        # Activator
        bundle.start()

        self.assertEqual(bundle.get_state(), Bundle.ACTIVE,
                         "Bundle should be considered active")

        self.assertTrue(module.started, "Bundle should be started now")
        self.assertFalse(module.stopped, "Bundle should not be stopped yet")

        # Recall activator
        module.started = False
        bundle.start()
        self.assertFalse(module.started, "Bundle shouldn't be started twice")

        # Reset to previous state
        module.started = True

        # De-activate
        bundle.stop()

        self.assertNotEqual(bundle.get_state(), Bundle.ACTIVE,
                            "Bundle shouldn't be considered active")

        self.assertTrue(module.started, "Bundle should be changed")
        self.assertTrue(module.stopped, "Bundle should be stopped now")

        # Recall activator
        module.stopped = False
        bundle.stop()
        self.assertFalse(module.stopped, "Bundle shouldn't be stopped twice")

        # Uninstall (validated in another test)
        bundle.uninstall()

        self.assertEqual(bundle.get_state(), Bundle.UNINSTALLED,
                         "Bundle should be considered uninstalled")


    def testLifeCycleExceptions(self):
        """
        Tests a bundle installation + start + stop

        @param test_bundle_id: If True, also tests if the test bundle ID is 1
        """
        # Install the bundle
        bundle = self.context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        # Get the internal module
        module = bundle.get_module()

        # Assert initial state
        self.assertFalse(module.started, "Bundle should not be started yet")
        self.assertFalse(module.stopped, "Bundle should not be stopped yet")

        # Activator with exception
        module.raiser = True

        log_off()
        self.assertRaises(BundleException, bundle.start)
        log_on()

        # Assert post-exception state
        self.assertNotEqual(bundle.get_state(), Bundle.ACTIVE,
                            "Bundle shouldn't be considered active")
        self.assertFalse(module.started, "Bundle should not be started yet")
        self.assertFalse(module.stopped, "Bundle should not be stopped yet")

        # Activator, without exception
        module.raiser = False
        bundle.start()

        self.assertEqual(bundle.get_state(), Bundle.ACTIVE,
                         "Bundle should be considered active")

        self.assertTrue(module.started, "Bundle should be started now")
        self.assertFalse(module.stopped, "Bundle should not be stopped yet")

        # De-activate with exception
        module.raiser = True

        log_off()
        self.assertRaises(BundleException, bundle.stop)
        log_on()

        self.assertNotEqual(bundle.get_state(), Bundle.ACTIVE,
                            "Bundle shouldn't be considered active")
        self.assertTrue(module.started, "Bundle should be changed")
        self.assertFalse(module.stopped, "Bundle should be stopped now")

        # Uninstall (validated in another test)
        bundle.uninstall()


    def testUninstallInstall(self):
        """
        Runs the life-cycle test twice.

        The bundle is installed then un-installed twice. started and stopped
        values of the bundle should be reset to False.

        Keeping two separate calls instead of using a loop allows to see at
        which pass the test have failed
        """
        # Pass 1: normal test
        self.testLifeCycle(True)

        # Pass 2: refresh test
        self.testLifeCycle(False)


    def testUninstallWithStartStop(self):
        """
        Tests if a bundle is correctly uninstalled and if it is really
        unaccessible after its uninstallation.
        """
        # Install the bundle
        bundle = self.context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        bid = bundle.get_bundle_id()
        self.assertEqual(bid, 1, "Invalid first bundle ID '{0:d}'".format(bid))

        # Test state
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Invalid fresh install state {0:d}" \
                         .format(bundle.get_state()))

        # Start
        bundle.start()
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE,
                         "Invalid fresh start state {0:d}" \
                         .format(bundle.get_state()))

        # Stop
        bundle.stop()
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Invalid fresh stop state {0:d}" \
                         .format(bundle.get_state()))

        # Uninstall
        bundle.uninstall()
        self.assertEqual(bundle.get_state(), Bundle.UNINSTALLED,
                         "Invalid fresh stop state {0:d}" \
                         .format(bundle.get_state()))

        # The bundle must not be accessible through the framework
        self.assertRaises(BundleException, self.context.get_bundle, bid)

        self.assertRaises(BundleException, self.framework.get_bundle_by_id, bid)

        found_bundle = self.framework.get_bundle_by_name(self.test_bundle_name)
        self.assertIsNone(found_bundle, "Bundle is still accessible by name " \
                          "through the framework")


    def testUpdate(self):
        """
        Tests a bundle update
        """
        bundle_content = """#!/usr/bin/python
# Auto-generated bundle, for Pelix tests
__version__ = "{version}"
test_var = {test}

def test_fct():
    return {test}
"""
        bundle_name = "generated_bundle"

        # 0/ Clean up existing files
        for ext in ("py", "pyc"):
            path = ".{sep}{0}.{1}".format(bundle_name, ext, sep=os.path.sep)
            if os.path.exists(path):
                os.remove(path)

        # 1/ Prepare the bundle, test variable is set to False
        f = open(".{sep}{0}.py".format(bundle_name, sep=os.path.sep), "w")
        f.write(bundle_content.format(version="1.0.0", test=False))
        f.close()

        # 2/ Install the bundle and get its variable
        bundle = self.context.install_bundle(bundle_name)
        module = bundle.get_module()

        # Also start the bundle
        bundle.start()

        self.assertFalse(module.test_var, "Test variable should be False")

        # 3/ Change the bundle file
        f = open(".{sep}{0}.py".format(bundle_name, sep=os.path.sep), "w")
        f.write(bundle_content.format(version="1.0.1", test=True))
        f.close()

        # 4/ Update, keeping the module reference
        bundle.update()
        self.assertIs(module, bundle.get_module(), "Module has changed")
        self.assertTrue(module.test_var, "Test variable should be True")

        # 5/ Change the bundle file, make it erroneous
        f = open(".{sep}{0}.py".format(bundle_name, sep=os.path.sep), "w")
        f.write(bundle_content.format(version="1.0.2", test="\n"))
        f.close()

        # No error must be raised...
        bundle.update()

        # ... but the state of the module shouldn't have changed
        self.assertTrue(module.test_var, "Test variable should still be True")

        # Finally, change the test file to be a valid module
        # -> Used by coverage for its report
        f = open(".{sep}{0}.py".format(bundle_name, sep=os.path.sep), "w")
        f.write(bundle_content.format(version="1.0.0", test=False))
        f.close()



    def testVersion(self):
        """
        Tests if the version is correctly read from the bundle
        """
        # Install the bundle
        bundle = self.framework.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        bid = bundle.get_bundle_id()
        self.assertEqual(bid, 1, "Invalid first bundle ID '{0:d}'".format(bid))

        # Get the internal module
        module = bundle.get_module()

        # Validate the bundle name
        self.assertEqual(bundle.get_symbolic_name(), self.test_bundle_name,
                         "Names are different ({0} / {1})" \
                         .format(bundle.get_symbolic_name(),
                                 self.test_bundle_name))

        # Validate get_location()
        bundle_without_ext = os.path.splitext(bundle.get_location())[0]
        self.assertEqual(bundle_without_ext, self.test_bundle_loc,
                         "Not the same location {0} -> {1}" \
                         .format(self.test_bundle_loc, bundle_without_ext))

        # Validate the version number
        self.assertEqual(bundle.get_version(), module.__version__,
                         "Different versions found ({0} / {1})" \
                         .format(bundle.get_version(), module.__version__))

        # Remove the bundle
        bundle.uninstall()


# ------------------------------------------------------------------------------

class BundleEventTest(unittest.TestCase):
    """
    Pelix bundle event tests
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

        self.test_bundle_name = "tests.simple_bundle"

        self.bundle = None
        self.received = []


    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)


    def reset_state(self):
        """
        Resets the flags
        """
        del self.received[:]


    def bundle_changed(self, event):
        """
        Called by the framework when a bundle event is triggered

        @param event: The BundleEvent
        """
        assert isinstance(event, BundleEvent)

        bundle = event.get_bundle()
        kind = event.get_kind()
        if self.bundle is not None \
        and kind == BundleEvent.INSTALLED:
            # Bundle is not yet locally known...
            self.assertIs(self.bundle, bundle,
                          "Received an event for an other bundle.")

        self.assertNotIn(kind, self.received, "Event received twice")
        self.received.append(kind)


    def testBundleEvents(self):
        """
        Tests if the signals are correctly received
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        self.assertTrue(context.add_bundle_listener(self),
                        "Can't register the bundle listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        self.assertEqual([BundleEvent.INSTALLED],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([BundleEvent.STARTING, BundleEvent.STARTED],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Stop the bundle
        bundle.stop()
        # Assert the events have been received
        self.assertEqual([BundleEvent.STOPPING, BundleEvent.STOPPING_PRECLEAN,
                          BundleEvent.STOPPED], self.received,
                         "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle
        bundle.uninstall()
        # Assert the events have been received
        self.assertEqual([BundleEvent.UNINSTALLED],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Unregister from events
        context.remove_bundle_listener(self)

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
        if 'tests.simple_bundle' in sys.modules:
            del sys.modules['tests.simple_bundle']


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
        bundle = context.install_bundle("tests.simple_bundle")

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
        bundle = context.install_bundle("tests.simple_bundle")
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
        bundle = context.install_bundle("tests.simple_bundle")
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
        bundle = context.install_bundle("tests.simple_bundle")
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
                        "wait_for_stop() must return True on stopped framework")

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

class LocalBundleTest(unittest.TestCase):
    """
    Tests the installation of the __main__ bundle
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)


    def testLocalBundle(self):
        """
        Tests the correctness of the __main__ bundle objects in the framework
        """
        fw_context = self.framework.get_bundle_context()
        assert isinstance(fw_context, BundleContext)

        # Install local bundle in framework (for service installation & co)
        bundle = fw_context.install_bundle(__name__)

        # Get a reference to the bundle, by name
        bundle_2 = fw_context.get_bundle(0).get_bundle_by_name(__name__)

        self.assertIs(bundle, bundle_2,
                      "Different bundle returned by ID and by name")

        # Validate the symbolic name
        self.assertEqual(bundle.get_symbolic_name(), __name__,
                         "Bundle ({0}) and module ({1}) are different" \
                         .format(bundle.get_symbolic_name(), __name__))

        # Validate get_bundle() via bundle context
        context_bundle = bundle.get_bundle_context().get_bundle()
        self.assertIs(bundle, context_bundle,
                      "Not the same bundle:\n{0:d} / {1}\n{2:d} / {3}" \
                      .format(id(bundle), bundle,
                              id(context_bundle), context_bundle))

        # Validate get_version()
        self.assertEqual(bundle.get_version(), __version__,
                         "Not the same version {0} -> {1}" \
                         .format(__version__, bundle.get_version()))

        # Validate get_location()
        self.assertEqual(bundle.get_location(), __file__,
                         "Not the same location {0} -> {1}" \
                         .format(__file__, bundle.get_location()))

# ------------------------------------------------------------------------------

class ServicesTest(unittest.TestCase):
    """
    Pelix services registry tests
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework and loads the current
        module as the first bundle
        """
        self.test_bundle_name = "tests.service_bundle"

        self.framework = FrameworkFactory.get_framework()
        self.framework.start()


    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)


    def testBundleRegister(self):
        """
        Test the service registration, request and unregister in a well formed
        bundle (activator that unregisters the service during the stop call)
        """
        svc_filter = "(test=True)"

        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Install the service bundle
        bundle = context.install_bundle(self.test_bundle_name)
        bundle_context = bundle.get_bundle_context()
        module = bundle.get_module()

        # Assert we can't access the service
        ref1 = context.get_service_reference(IEchoService)
        self.assertIsNone(ref1, "get_service_reference found: {0}".format(ref1))

        ref2 = context.get_service_reference(IEchoService, svc_filter)
        self.assertIsNone(ref2, "get_service_reference, filtered found: {0}" \
                          .format(ref2))

        refs = context.get_all_service_references(IEchoService, None)
        self.assertIsNone(refs, "get_all_service_reference found: {0}" \
                          .format(refs))

        refs = context.get_all_service_references(IEchoService, svc_filter)
        self.assertIsNone(refs,
                          "get_all_service_reference, filtered found: {0}" \
                          .format(refs))

        # --- Start it (registers a service) ---
        bundle.start()

        # Get the reference
        ref1 = context.get_service_reference(IEchoService)
        self.assertIsNotNone(ref1, "get_service_reference found nothing")

        ref2 = context.get_service_reference(IEchoService, svc_filter)
        self.assertIsNotNone(ref2,
                             "get_service_reference, filtered found nothing")

        # Assert we found the same references
        self.assertIs(ref1, ref2, "References are not the same")

        # Get all IEchoServices
        refs = context.get_all_service_references(IEchoService, None)

        # Assert we found only one reference
        self.assertIsNotNone(refs, "get_all_service_reference found nothing")

        refs = context.get_all_service_references(IEchoService, svc_filter)

        # Assert we found only one reference
        self.assertIsNotNone(refs,
                             "get_all_service_reference filtered found nothing")

        # Assert that the first found reference is the first of "all" references
        self.assertIs(ref1, refs[0],
                      "Not the same references through get and get_all")


        # Assert that the bundle can find its own services
        self.assertListEqual(refs,
                             bundle_context.get_service_references(IEchoService,
                                                                   None),
                             "The bundle can't find its own services")

        self.assertListEqual(refs,
                             bundle_context.get_service_references(IEchoService,
                                                                   svc_filter),
                             "The bundle can't find its own filtered services")

        # Assert that the framework bundle context can't find the bundle
        # services
        self.assertListEqual([],
                             context.get_service_references(IEchoService, None),
                             "Framework bundle shoudln't get the echo service")

        self.assertListEqual([],
                             context.get_service_references(IEchoService,
                                                            svc_filter),
                             "Framework bundle shoudln't get the filtered "
                             "echo service")


        # Get the service
        svc = context.get_service(ref1)
        assert isinstance(svc, IEchoService)

        # Validate the reference
        self.assertIs(svc, module.service, "Not the same service instance...")

        # Unget the service
        context.unget_service(ref1)

        # --- Stop it (unregisters a service) ---
        bundle.stop()

        # Assert we can't access the service
        ref1 = context.get_service_reference(IEchoService)
        self.assertIsNone(ref1, "get_service_reference found: {0}".format(ref1))

        ref2 = context.get_service_reference(IEchoService, svc_filter)
        self.assertIsNone(ref2, "get_service_reference, filtered found: {0}" \
                          .format(ref2))

        refs = context.get_all_service_references(IEchoService, None)
        self.assertIsNone(refs, "get_all_service_reference found: {0}"\
                          .format(refs))

        refs = context.get_all_service_references(IEchoService, svc_filter)
        self.assertIsNone(refs,
                          "get_all_service_reference, filtered found: {0}" \
                          .format(refs))

        # --- Uninstall it ---
        bundle.uninstall()


    def testBundleUninstall(self):
        """
        Tests if a registered service is correctly removed, even if its
        registering bundle doesn't have the code for that
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Install the service bundle
        bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        module = bundle.get_module()

        # --- Start it (registers a service) ---
        bundle.start()

        self.assertIsNotNone(module.service, "The service instance is missing")

        # Get the reference
        ref = context.get_service_reference(IEchoService)
        self.assertIsNotNone(ref, "get_service_reference found nothing")

        registered_svcs = bundle.get_registered_services()
        self.assertIn(ref, registered_svcs,
                      "Reference not in registered services")

        # Get the service
        svc = context.get_service(ref)
        self.assertIsNotNone(svc, "Service not found")
        self.assertIn(ref, self.framework.get_services_in_use(),
                      "Reference usage not indicated")

        context.unget_service(ref)
        self.assertNotIn(ref, self.framework.get_services_in_use(),
                         "Reference usage not removed")
        svc = None

        # --- Uninstall the bundle without stopping it first ---
        bundle.uninstall()

        # The service should be deleted
        ref = context.get_service_reference(IEchoService)
        self.assertIsNone(ref, "get_service_reference found: {0}".format(ref))

        # We shouldn't have access to the bundle services anymore
        self.assertRaises(BundleException, bundle.get_registered_services)
        self.assertRaises(BundleException, bundle.get_services_in_use)


    def testServiceReferencesCmp(self):
        """
        Tests service references comparisons
        """

        # Invalid references...
        # ... empty properties
        self.assertRaises(BundleException, ServiceReference, self.framework, {})
        # ... no service ID
        self.assertRaises(BundleException, ServiceReference, self.framework,
                          {pelix.OBJECTCLASS: "a"})
        # ... no object class
        self.assertRaises(BundleException, ServiceReference, self.framework,
                          {pelix.SERVICE_ID: "b"})

        ref1b = ServiceReference(self.framework, {pelix.OBJECTCLASS: "ref1_b",
                                                 pelix.SERVICE_ID: 1,
                                                 pelix.SERVICE_RANKING:0})

        ref1 = ServiceReference(self.framework, {pelix.OBJECTCLASS: "ref1",
                                                 pelix.SERVICE_ID: 1})

        ref2 = ServiceReference(self.framework, {pelix.OBJECTCLASS: "ref2",
                                                 pelix.SERVICE_ID: 2})

        ref3 = ServiceReference(self.framework, {pelix.OBJECTCLASS: "ref3",
                                                 pelix.SERVICE_ID: 3,
                                                 pelix.SERVICE_RANKING:-20})

        ref4 = ServiceReference(self.framework, {pelix.OBJECTCLASS: "ref4",
                                                 pelix.SERVICE_ID: 4,
                                                 pelix.SERVICE_RANKING: 128})

        # Tests
        self.assertEqual(ref1, ref1, "ID1 == ID1")
        self.assertEqual(ref1.__cmp__(ref1), 0, "Equality per __cmp__()")

        self.assertEqual(ref1.__cmp__("titi"), -1,
                         "Lesser than unknown with  __cmp__()")
        self.assertNotEqual(ref1, "titi", "Not equal to unknown with __eq__()")
        self.assertLess(ref1, "titi", "Lesser than unknown with  __lt__()")
        self.assertLessEqual(ref1, "titi", "Lesser than unknown with  __le__()")

        self.assertEqual(ref1, ref1b, "ID1 == ID1.0")
        self.assertGreaterEqual(ref1, ref1b, "ID1 >= ID1.0")

        # ID comparison
        self.assertLess(ref2, ref1, "ID2 < ID1")
        self.assertLessEqual(ref2, ref1, "ID2 <= ID1")
        self.assertGreater(ref1, ref2, "ID2 > ID1")
        self.assertGreaterEqual(ref1, ref2, "ID1 >= ID2")

        # Ranking comparison
        self.assertGreater(ref4, ref3, "ID4.128 > ID3.-20")
        self.assertGreaterEqual(ref4, ref3, "ID4.128 >= ID3.-20")
        self.assertLess(ref3, ref4, "ID3.-20 < ID4.128")
        self.assertLessEqual(ref3, ref4, "ID3.-20 <= ID4.128")

        # Ensure that comparison is not based on ID
        self.assertLess(ref3, ref1, "ID3.-20 < ID1.0")
        self.assertGreater(ref1, ref3, "ID3.-20 > ID1.0")


    def testServiceRegistrationUpdate(self):
        """
        Try to update service properties
        """
        context = self.framework.get_bundle_context()

        # Register service
        base_props = {pelix.OBJECTCLASS: "titi",
                      pelix.SERVICE_ID:-1,
                      "test": 42}

        reg = context.register_service("class", self, base_props)
        ref = reg.get_reference()

        # Ensure that reserved properties have been overridden
        object_class = ref.get_property(pelix.OBJECTCLASS)
        self.assertListEqual(object_class, ["class"],
                             "Invalid objectClass property '{0}'" \
                             .format(object_class))

        svc_id = ref.get_property(pelix.SERVICE_ID)
        self.assertGreater(svc_id, 0, "Invalid service ID")

        # Ensure the reference uses a copy of the properties
        base_props["test"] = 21
        self.assertEqual(ref.get_property("test"), 42,
                         "Property updated by the dictionary reference")

        # Update the properties
        update_props = {pelix.OBJECTCLASS: "ref2",
                        pelix.SERVICE_ID: 20,
                        "test": 21}

        reg.set_properties(update_props)

        # Ensure that reserved properties have been kept
        self.assertListEqual(ref.get_property(pelix.OBJECTCLASS), object_class,
                          "Modified objectClass property")

        self.assertEqual(ref.get_property(pelix.SERVICE_ID), svc_id,
                         "Modified service ID")

        self.assertEqual(ref.get_property("test"), 21,
                         "Extra property not updated")


    def testGetAllReferences(self):
        """
        Tests get_all_service_references() method
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Get all references count
        all_refs = context.get_all_service_references(None, None)
        self.assertIsNotNone(all_refs, "All references result must not be None")
        self.assertEqual(len(all_refs), 0, "Services list should be empty")

        # Install the service bundle
        bundle = context.install_bundle(self.test_bundle_name)

        # No services yet
        all_refs = context.get_all_service_references(None, None)
        self.assertIsNotNone(all_refs, "All references result must not be None")
        self.assertEqual(len(all_refs), 0, "Services list should be empty")

        # Start the bundle
        bundle.start()

        all_refs = context.get_all_service_references(None, None)
        self.assertIsNotNone(all_refs, "All references result must not be None")
        self.assertGreater(len(all_refs), 0, "Services list shouldn't be empty")

        # Try with an empty filter (lists should be equal)
        all_refs_2 = context.get_all_service_references(None, "")
        self.assertListEqual(all_refs, all_refs_2,
                             "References lists should be equal")

        # Assert that the registered service is in the list
        ref = context.get_service_reference(IEchoService)
        self.assertIsNotNone(ref, "get_service_reference found nothing")
        self.assertIn(ref, all_refs, "Echo service should be the complete list")

        # Remove the bundle
        bundle.uninstall()

        # Test an invalid filter
        self.assertRaises(BundleException, context.get_all_service_references,
                          None, "/// Invalid Filter ///")


    def testMultipleUnregistrations(self):
        """
        Tests behavior when unregistering the same service twice
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register a dummy service
        registration = context.register_service("test", self, None, False)

        # Unregister it twice
        registration.unregister()
        self.assertRaises(BundleException, registration.unregister)


    def testInvalidGetService(self):
        """
        Tests behavior when using get_service on an invalid service
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register a dummy service
        registration = context.register_service("test", self, None, False)

        # Get the reference
        reference = registration.get_reference()

        # Unregister the service
        registration.unregister()

        # Try to get it
        self.assertRaises(BundleException, context.get_service, reference)


# ------------------------------------------------------------------------------

class ServiceEventTest(unittest.TestCase):
    """
    Pelix bundle event tests
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

        self.test_bundle_name = "tests.service_bundle"

        self.bundle = None
        self.received = []


    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)


    def reset_state(self):
        """
        Resets the flags
        """
        del self.received[:]


    def service_changed(self, event):
        """
        Called by the framework when a service event is triggered

        @param event: The ServiceEvent
        """
        assert isinstance(event, ServiceEvent)

        ref = event.get_service_reference()
        self.assertIsNotNone(ref, "Invalid service reference in the event")

        kind = event.get_kind()

        if kind == ServiceEvent.MODIFIED \
        or kind == ServiceEvent.MODIFIED_ENDMATCH:
            # Properties have been modified
            self.assertNotEqual(ref.get_properties(),
                                event.get_previous_properties(),
                                "Modified event for unchanged properties")

        self.assertNotIn(kind, self.received, "Event received twice")
        self.received.append(kind)


    def testDoubleListener(self):
        """
        Tests double registration / unregistration
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Double registration
        self.assertTrue(context.add_service_listener(self),
                        "Can't register the service listener")

        log_off()
        self.assertFalse(context.add_service_listener(self),
                        "Service listener registered twice")
        log_on()

        # Double unregistration
        self.assertTrue(context.remove_service_listener(self),
                        "Can't unregister the service listener")

        log_off()
        self.assertFalse(context.remove_service_listener(self),
                        "Service listener unregistered twice")
        log_on()


    def testInvalidFilterListener(self):
        """
        Tests invalid filter listener registration
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        log_off()
        self.assertRaises(BundleException, context.add_service_listener, self,
                          "Invalid")
        log_on()

        self.assertFalse(context.remove_service_listener(self),
                         "Invalid filter was registered anyway")


    def testServiceEventsNormal(self):
        """
        Tests if the signals are correctly received
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        self.assertTrue(context.add_service_listener(self),
                        "Can't register the service listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        self.assertEqual([], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.REGISTERED],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Stop the bundle
        bundle.stop()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.UNREGISTERING],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle
        bundle.uninstall()
        # Assert the events have been received
        self.assertEqual([], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Unregister from events
        context.remove_service_listener(self)


    def testServiceEventsNoStop(self):
        """
        Tests if the signals are correctly received, even if the service is not
        correctly removed
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        self.assertTrue(context.add_service_listener(self),
                        "Can't register the service listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        self.assertEqual([], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.REGISTERED],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle, without unregistering the service
        module = bundle.get_module()
        module.unregister = False
        bundle.uninstall()

        # Assert the events have been received
        self.assertEqual([ServiceEvent.UNREGISTERING],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Unregister from events
        context.remove_service_listener(self)


    def testServiceModified(self):
        """
        Tests the service modified event
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        self.assertTrue(context.add_service_listener(self, "(test=True)"),
                        "Can't register the service listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.REGISTERED],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Get the service
        ref = context.get_service_reference(IEchoService)
        self.assertIsNotNone(ref, "ServiceReference not found")

        svc = context.get_service(ref)
        self.assertIsNotNone(ref, "Invalid service instance")

        # Modify the service => Simple modification
        svc.modify({"answer": 42})
        self.assertEqual([ServiceEvent.MODIFIED],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Set the same value => No event should be sent
        svc.modify({"answer": 42})
        self.assertEqual([], self.received,
                         "Received {0}".format(self.received))
        self.reset_state()

        # Modify the service => Ends the filter match
        svc.modify({"test": False})
        # Assert the events have been received
        self.assertEqual([ServiceEvent.MODIFIED_ENDMATCH],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Modify the service => the filter matches again
        svc.modify({"test": True})
        # Assert the events have been received
        self.assertEqual([ServiceEvent.MODIFIED],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Stop the bundle
        bundle.stop()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.UNREGISTERING],
                          self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle
        bundle.uninstall()

        # Unregister from events
        context.remove_service_listener(self)

# ------------------------------------------------------------------------------

class UtilityMethodsTest(unittest.TestCase):
    """
    Pelix bundle event tests
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = None
        self.test_bundle_name = "tests.service_bundle"


    def tearDown(self):
        """
        Called after each test
        """
        if self.framework is not None:
            FrameworkFactory.delete_framework(self.framework)
            self.framework = None


    def testCreateFrameworkBasic(self):
        """
        Tests create_framework(), without parameters
        -> creates an empty framework, and doesn't start it
        """
        self.framework = pelix.create_framework([])
        self.assertEqual(self.framework.get_state(), pelix.Bundle.RESOLVED,
                         'Framework has been started')
        self.assertEqual(self.framework.get_bundles(), [],
                         'Framework is not empty')

        # Try to start two framework
        self.assertRaises(ValueError, pelix.create_framework, [])


    def testCreateFrameworkWithBundles(self):
        """
        Tests create_framework(), with specified bundles
        """
        self.framework = pelix.create_framework([self.test_bundle_name])
        self.assertEqual(self.framework.get_state(), pelix.Bundle.RESOLVED,
                         'Framework has been started')

        self.assertEqual(len(self.framework.get_bundles()), 1,
                         'Framework should only have 1 bundle')

        bundle = self.framework.get_bundle_by_id(1)
        self.assertEqual(bundle.get_symbolic_name(), self.test_bundle_name,
                         "The test bundle hasn't been installed correctly")


    def testCreateFrameworkAutoStart(self):
        """
        Tests create_framework(), with specified bundles and auto-start
        """
        # Without bundles
        self.framework = pelix.create_framework([], auto_start=True)
        self.assertEqual(self.framework.get_state(), pelix.Bundle.ACTIVE,
                         "Framework hasn't been started")
        self.assertEqual(self.framework.get_bundles(), [],
                         'Framework is not empty')
        # Clean up
        FrameworkFactory.delete_framework(self.framework)

        # With bundles
        self.framework = pelix.create_framework([self.test_bundle_name],
                                                auto_start=True)
        self.assertEqual(self.framework.get_state(), pelix.Bundle.ACTIVE,
                         "Framework hasn't been started")
        self.assertEqual(len(self.framework.get_bundles()), 1,
                         'Framework should only have 1 bundle')

        bundle = self.framework.get_bundle_by_id(1)
        self.assertEqual(bundle.get_symbolic_name(), self.test_bundle_name,
                         "The test bundle hasn't been installed correctly")
        self.assertEqual(bundle.get_state(), pelix.Bundle.ACTIVE,
                         "Bundle hasn't been started")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
