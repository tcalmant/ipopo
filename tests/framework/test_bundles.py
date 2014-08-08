#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the bundles handling.

:author: Thomas Calmant
"""

# Tests
from tests import log_on, log_off

# Pelix
from pelix.framework import FrameworkFactory, Bundle, BundleException, \
    BundleContext

# Standard library
import os

try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

SERVICE_BUNDLE = "tests.framework.service_bundle"
SIMPLE_BUNDLE = "tests.framework.simple_bundle"

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

        self.test_bundle_name = SIMPLE_BUNDLE
        # File path, without extension
        self.test_bundle_loc = os.path.abspath(
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
                         "Invalid fresh install state {0:d}"
                         .format(bundle.get_state()))

        # Start
        bundle.start()
        self.assertEqual(bundle.get_state(), Bundle.ACTIVE,
                         "Invalid fresh start state {0:d}"
                         .format(bundle.get_state()))

        # Stop
        bundle.stop()
        self.assertEqual(bundle.get_state(), Bundle.RESOLVED,
                         "Invalid fresh stop state {0:d}"
                         .format(bundle.get_state()))

        # Uninstall
        bundle.uninstall()
        self.assertEqual(bundle.get_state(), Bundle.UNINSTALLED,
                         "Invalid fresh stop state {0:d}"
                         .format(bundle.get_state()))

        # The bundle must not be accessible through the framework
        self.assertRaises(BundleException, self.context.get_bundle, bid)

        self.assertRaises(
            BundleException, self.framework.get_bundle_by_id, bid)

        found_bundle = self.framework.get_bundle_by_name(self.test_bundle_name)
        self.assertIsNone(found_bundle, "Bundle is still accessible by name "
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
                         "Names are different ({0} / {1})"
                         .format(bundle.get_symbolic_name(),
                                 self.test_bundle_name))

        # Validate get_location()
        bundle_without_ext = os.path.splitext(bundle.get_location())[0]
        full_bundle_path = os.path.abspath(bundle_without_ext)
        self.assertIn(self.test_bundle_loc,
                      (bundle_without_ext, full_bundle_path))

        # Validate the version number
        self.assertEqual(bundle.get_version(), module.__version__,
                         "Different versions found ({0} / {1})"
                         .format(bundle.get_version(), module.__version__))

        # Remove the bundle
        bundle.uninstall()

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
                         "Bundle ({0}) and module ({1}) are different"
                         .format(bundle.get_symbolic_name(), __name__))

        # Validate get_bundle() via bundle context
        context_bundle = bundle.get_bundle_context().get_bundle()
        self.assertIs(bundle, context_bundle,
                      "Not the same bundle:\n{0:d} / {1}\n{2:d} / {3}"
                      .format(id(bundle), bundle,
                              id(context_bundle), context_bundle))

        # Validate get_version()
        self.assertEqual(bundle.get_version(), __version__,
                         "Not the same version {0} -> {1}"
                         .format(__version__, bundle.get_version()))

        # Validate get_location()
        self.assertEqual(bundle.get_location(), __file__,
                         "Not the same location {0} -> {1}"
                         .format(__file__, bundle.get_location()))

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
