#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests for the ConfigurationAdmin tests

:author: Thomas Calmant
"""

# Pelix
import pelix.framework
import pelix.services as services
from pelix.utilities import use_service

# Standard library
import json
import os
import time

try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class ConfigurationAdminTest(unittest.TestCase):
    """
    Tests for configuration admin methods
    """
    def setUp(self):
        """
        Sets up the test
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core',
             'pelix.services.configadmin'))
        self.framework.start()
        context = self.framework.get_bundle_context()

        # Get the service
        self.config_ref = context.get_service_reference(
            services.SERVICE_CONFIGURATION_ADMIN)
        self.config = context.get_service(self.config_ref)

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Release the service
        self.framework.get_bundle_context().unget_service(self.config_ref)
        self.config = None
        self.config_ref = None

        pelix.framework.FrameworkFactory.delete_framework(self.framework)

    def testCreateFactoryConfiguration(self):
        """
        Tests the create factory configuration method
        """
        # Invalid name
        for value in (None, "", "   "):
            self.assertRaises(ValueError,
                              self.config.create_factory_configuration, value)

        # Invalid type
        for value in ([], 12, True):
            self.assertRaises(ValueError,
                              self.config.create_factory_configuration, value)

        # Create a configuration
        factory_pid = "test.ca.factory"
        config = self.config.create_factory_configuration(factory_pid)
        pid = config.get_pid()

        # Check validity
        self.assertIsNotNone(config, "No configuration returned")
        self.assertEqual(config.get_factory_pid(), factory_pid,
                         "Wrong factory PID")
        self.assertIn(factory_pid, pid, "PID doesn't contain the Factory PID")
        self.assertIsNone(config.get_properties(),
                          "Fresh factory configuration has properties")

        # Check Factory/Configuration PIDs
        self.assertRaises(KeyError, self.config.get_configuration, factory_pid)

        # Delete the configuration
        config.delete()

        # Create a new one
        config2 = self.config.create_factory_configuration(factory_pid)

        # They must be different and have different PID
        self.assertIsNot(
            config, config2,
            "ConfigAdmin returned a deleted factory configuration")
        self.assertNotEqual(pid, config2.get_pid(),
                            "Same PID for new configuration")

        # Delete the new one
        config2.delete()

    def testGetConfiguration(self):
        """
        Tests the get_configuration method (and the configuration bean)
        """
        # Create the configuration
        pid = "test.ca.get"
        config = self.config.get_configuration(pid)

        # It is not valid and has no properties
        self.assertFalse(config.is_valid(), "Fresh configuration is valid")
        self.assertIsNone(config.get_properties(),
                          "Fresh configuration has properties")

        # Update properties
        config.update({"answer": 42})

        # Ensure we still have the same object
        self.assertIs(config, self.config.get_configuration(pid),
                      "Configuration object changed")

        # Ensure we have the new properties
        self.assertTrue(config.is_valid(), "Configuration is still invalid")
        properties = config.get_properties()

        self.assertEqual(properties[services.CONFIG_PROP_PID], pid,
                         "Different PID in properties")
        self.assertEqual(properties["answer"], 42, "Configuration not updated")

        # Delete the configuration
        config.delete()

        # Ensure we'll get a new one
        config2 = self.config.get_configuration(pid)
        self.assertIsNot(config, config2,
                         "ConfigAdmin returned a deleted configuration")

        # Clean up
        config2.delete()

    def testListConfiguration(self):
        """
        Tests the list configuration method
        """
        # There should be nothing at first
        configs = self.config.list_configurations()
        self.assertIsNotNone(configs,
                             "list_configurations() must not return None")
        self.assertSetEqual(configs, set(), "Non-empty result set")

        # Add a configuration
        pid = "test.ca.list"
        config = self.config.get_configuration(pid)

        # Simple pre-check
        self.assertFalse(config.is_valid(), "Fresh configuration is valid")

        # It must be visible, but must not match filters
        self.assertSetEqual(self.config.list_configurations(), set([config]),
                            "Incorrect result set")

        ldap_filter = "({0}={1})".format(services.CONFIG_PROP_PID, pid)
        self.assertSetEqual(self.config.list_configurations(ldap_filter),
                            set(), "Invalid configuration matches a filter")

        # Update the configuration
        config.update({'arthur': 'dent'})

        # It must be visible, even with filters
        self.assertSetEqual(self.config.list_configurations(), set([config]),
                            "Incorrect result set")

        filters = [  # PID
            "({0}={1})".format(services.CONFIG_PROP_PID, pid),
                     # Property
            "({0}={1})".format('arthur', 'dent'),
                     # Both
            "(&({0}={1})({2}={3}))".format(services.CONFIG_PROP_PID, pid,
                                           'arthur', 'dent'),
        ]

        for ldap_filter in filters:
            self.assertSetEqual(self.config.list_configurations(ldap_filter),
                                set([config]),
                                "Configuration doesn't match filter {0}"
                                .format(ldap_filter))

        # Add a new configuration
        config2 = self.config.get_configuration(pid + "-bis")
        self.assertSetEqual(self.config.list_configurations(),
                            set([config, config2]),
                            "Incorrect result set")

        # Delete it
        config2.delete()
        self.assertSetEqual(self.config.list_configurations(), set([config]),
                            "Incorrect result set")

        # Delete the first one
        config.delete()
        self.assertSetEqual(configs, set(), "Non-empty result set")

    def testPersistence(self):
        """
        Tests configuration reload
        """
        pid = "test.ca.persistence"
        props = {"zaphod": "beeblebrox"}

        # Create a configuration
        config = self.config.get_configuration(pid)
        config.update(props)

        # Forget it locally
        config = None

        # Stop the framework
        self.tearDown()

        # Restart it
        self.setUp()

        # Reload the configuration
        config = self.config.get_configuration(pid)

        # Compare properties
        self.assertDictContainsSubset(props, config.get_properties(),
                                      "Properties lost with framework restart")

        # Delete the configuration
        config.delete()

# ------------------------------------------------------------------------------


class ManagedServiceTest(unittest.TestCase):
    """
    Tests the behavior of managed services
    """
    def setUp(self):
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core',
             'pelix.services.configadmin'))
        self.framework.start()
        context = self.framework.get_bundle_context()

        # Get the ConfigAdmin service
        self.config_ref = context.get_service_reference(
            services.SERVICE_CONFIGURATION_ADMIN)
        self.config = context.get_service(self.config_ref)

        # Install the test bundle (don't start it)
        self.bundle = context.install_bundle(
            'tests.services.configadmin_bundle')
        self.pid = self.bundle.get_module().CONFIG_PID

        # Remove existing configurations
        for config in self.config.list_configurations():
            config.delete()

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Remove existing configurations
        for config in self.config.list_configurations():
            config.delete()

        # Release the service
        self.framework.get_bundle_context().unget_service(self.config_ref)
        self.config = None
        self.config_ref = None

        pelix.framework.FrameworkFactory.delete_framework(self.framework)

    def get_ref(self):
        """
        Retrieves the reference to the managed service provided by the test
        bundle
        """
        return self.bundle.get_registered_services()[0]

    def pause(self):
        """
        Small pause to let the task pool notify the services
        """
        time.sleep(.2)

    def check_call_count(self, test_svc, expected_count):
        """
        Checks if the given test service has been called X times
        """
        self.assertEqual(test_svc.call_count, expected_count,
                         "updated() called more than {0} times"
                         .format(expected_count))
        test_svc.call_count = 0

    def testNoConfigDelete(self):
        """
        Tests the behaviour of the service with an empty configuration
        """
        # Start the test bundle
        self.bundle.start()

        # Get the service
        with use_service(self.framework.get_bundle_context(),
                         self.get_ref()) as svc:
            # Create the configuration
            config = self.config.get_configuration(self.pid)

            # Give some time for the possible erroneous notification
            self.pause()

            # Nothing should have happened yet
            self.assertIsNone(svc.value, "Value has been set")
            self.assertFalse(
                svc.deleted, "Configuration considered as deleted")

            # Delete the configuration
            config.delete()

            # Give some time for the possible erroneous notification
            self.pause()

            # Nothing should have happened either
            self.assertIsNone(svc.value, "Value has been set")
            self.assertFalse(
                svc.deleted, "Configuration considered as deleted")

    def testEarlyConfig(self):
        """
        Tests the behaviour if a configuration is already set when the managed
        service is registered
        """
        # Create the configuration
        config = self.config.get_configuration(self.pid)
        config.update({'config.value': 42})

        # Start the test bundle
        self.bundle.start()

        # Get the service
        with use_service(self.framework.get_bundle_context(),
                         self.get_ref()) as svc:
            # Give some time for the notification
            self.pause()

            # The service should already have been configured
            self.assertEqual(svc.value, 42, "Value hasn't been set")
            self.assertFalse(
                svc.deleted, "Configuration considered as deleted")

            # Delete the configuration
            config.delete()

            # Give some time for the notification
            self.pause()

            # The flag must have been set
            self.assertTrue(svc.deleted, "Configuration considered as deleted")

    def testLateConfig(self):
        """
        Tests the behaviour if a configuration is created after the managed
        service has been registered
        """
        # Start the test bundle
        self.bundle.start()

        # Get the service
        with use_service(self.framework.get_bundle_context(),
                         self.get_ref()) as svc:
            # Give some time for the notification
            self.pause()

            # Nothing should have happened yet
            self.assertIsNone(svc.value, "Value has been set")
            self.assertFalse(
                svc.deleted, "Configuration considered as deleted")

            # Create the configuration
            config = self.config.get_configuration(self.pid)
            config.update({'config.value': 42})

            # Update is done a another thread
            self.pause()

            # The service should have been configured
            self.assertEqual(svc.value, 42, "Value hasn't been set")
            self.assertFalse(
                svc.deleted, "Configuration considered as deleted")

            # Delete the configuration
            config.delete()

            # Give some time for the notification
            self.pause()

            # The flag must have been set
            self.assertTrue(svc.deleted, "Configuration considered as deleted")

    def testUpdateConfig(self):
        """
        Tests the behaviour if a configuration is updated
        """
        # Create the configuration
        config = self.config.get_configuration(self.pid)

        # Start the test bundle
        self.bundle.start()

        # Get the service
        with use_service(self.framework.get_bundle_context(),
                         self.get_ref()) as svc:
            # Give some time for the notification
            self.pause()

            # Nothing should have happened yet
            self.check_call_count(svc, 0)
            self.assertIsNone(svc.value, "Value has been set")
            self.assertFalse(
                svc.deleted, "Configuration considered as deleted")

            # Update the configuration
            config.update({'config.value': 42})

            # Update is done a another thread
            self.pause()

            # The service should have been configured
            self.check_call_count(svc, 1)
            self.assertEqual(svc.value, 42, "Value hasn't been set")
            self.assertFalse(
                svc.deleted, "Configuration considered as deleted")

            # Delete the configuration
            config.delete()

            # Give some time for the notification
            self.pause()

            # The flag must have been set
            self.check_call_count(svc, 1)
            self.assertTrue(svc.deleted, "Configuration considered as deleted")

# ------------------------------------------------------------------------------


class FileInstallTest(unittest.TestCase):
    """
    Tests the behavior of FileInstall with ConfigurationAdmin
    """
    def setUp(self):
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core',
             'pelix.services.configadmin'))
        self.framework.start()
        context = self.framework.get_bundle_context()

        # in FileInstall
        self.bnd_fileinstall = context.install_bundle(
            'pelix.services.fileinstall')

        # Get the ConfigAdmin service
        self.config_ref = context.get_service_reference(
            services.SERVICE_CONFIGURATION_ADMIN)
        self.config = context.get_service(self.config_ref)

        # Install the test bundle (don't start it)
        self.bundle = context.install_bundle(
            'tests.services.configadmin_bundle')
        self.pid = self.bundle.get_module().CONFIG_PID

    def start_fileinstall(self):
        """
        Starts the file install bundle and tweaks its service
        """
        # Start the bundle
        self.bnd_fileinstall.start()

        # Speed up the poll time
        context = self.framework.get_bundle_context()
        fileinstall_ref = context.get_service_reference(
            services.SERVICE_FILEINSTALL)
        with use_service(context, fileinstall_ref) as svc:
            svc._poll_time = .1
            time.sleep(1)

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Release the service
        self.framework.get_bundle_context().unget_service(self.config_ref)
        self.config = None
        self.config_ref = None

        pelix.framework.FrameworkFactory.delete_framework(self.framework)

    def get_ref(self):
        """
        Retrieves the reference to the managed service provided by the test
        bundle
        """
        return self.bundle.get_registered_services()[0]

    def check_call_count(self, test_svc, expected_count):
        """
        Checks if the given test service has been called X times
        """
        self.assertEqual(test_svc.call_count, expected_count)
        test_svc.call_count = 0

    def touch(self, filepath):
        """
        Updates the modification time of the given file
        """
        with open(filepath, "r"):
            os.utime(filepath, None)

    def write(self, filepath, value):
        """
        Writes the property dictionary in JSON
        """
        props = {'config.value': value}
        with open(filepath, "w") as filep:
            filep.write(json.dumps(props))

    def testAddUpdateDelete(self):
        """
        Tests a whole file life cycle
        """
        # Start file install
        self.start_fileinstall()

        context = self.framework.get_bundle_context()

        # Start the test bundle
        self.bundle.start()
        ref = self.get_ref()

        # Wait a little
        time.sleep(.4)

        with use_service(context, ref) as svc:
            self.check_call_count(svc, 0)
            self.assertIsNone(svc.value, "Value has been set")

        # Get the watched folder
        persistence_ref = context.get_service_reference(
            services.SERVICE_CONFIGADMIN_PERSISTENCE)
        folder = persistence_ref.get_property(services.PROP_FILEINSTALL_FOLDER)

        # JSON persistence file name
        filepath = os.path.join(folder, self.pid + '.config.js')

        # Create the empty configuration
        value = 'Ni !'
        self.write(filepath, value)

        # Wait a little
        time.sleep(.4)

        # Check if the service has been updated
        with use_service(context, ref) as svc:
            self.assertEqual(svc.value, value, "Incorrect value")
            self.check_call_count(svc, 1)

        # Update the properties
        value = 'Ecky-ecky-ecky-ecky-pikang-zoom-boing'
        self.write(filepath, value)

        # Wait a little
        time.sleep(.4)

        # Check if the service has been updated
        with use_service(context, ref) as svc:
            self.assertEqual(svc.value, value, "Incorrect value")
            self.check_call_count(svc, 1)

            # Reset the flags
            svc.reset()

        # Touch the file
        self.touch(filepath)

        # Wait a little
        time.sleep(.4)

        # Check if the service has been updated
        with use_service(context, ref) as svc:
            self.check_call_count(svc, 0)
            self.assertIsNone(svc.value, "File updated after simple touch")
            self.assertFalse(svc.deleted, "Configuration considered deleted")

        # Delete the file
        os.remove(filepath)

        # Wait a little
        time.sleep(.4)

        with use_service(context, ref) as svc:
            self.check_call_count(svc, 1)
            self.assertTrue(svc.deleted, "Configuration not deleted")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
