#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests for the ConfigurationAdmin tests

:author: Thomas Calmant
"""

import json
import os
import shutil
import time
import unittest
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

import pelix.framework
import pelix.services as services
from pelix.internals.registry import ServiceReference
from pelix.utilities import use_service

if TYPE_CHECKING:
    from .configadmin_bundle import Configurable

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Use a local configuration folder
conf_folder = os.path.join(os.path.dirname(__file__), "conf")


class ConfigurationAdminTest(unittest.TestCase):
    """
    Tests for configuration admin methods
    """

    framework: pelix.framework.Framework
    config_ref: Optional[ServiceReference[services.IConfigurationAdmin]]
    config: services.IConfigurationAdmin

    def assertDictContains(
        self, subset: Dict[str, Any], tested: Optional[Dict[str, Any]], msg: Any = None
    ) -> None:
        assert tested is not None
        self.assertEqual(tested, tested | subset, msg)

    def setUp(self) -> None:
        """
        Sets up the test
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": conf_folder}
        )
        self.framework.start()
        context = self.framework.get_bundle_context()

        # Get the service
        self.config_ref = context.get_service_reference(services.IConfigurationAdmin)
        assert self.config_ref is not None
        self.config = context.get_service(self.config_ref)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Release the service
        if self.config_ref is not None:
            self.framework.get_bundle_context().unget_service(self.config_ref)
            self.config_ref = None

        pelix.framework.FrameworkFactory.delete_framework()
        self.config = None  # type: ignore

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Cleans up after all tests have been executed
        """
        shutil.rmtree(conf_folder)

    def testCreateFactoryConfiguration(self) -> None:
        """
        Tests the create factory configuration method
        """
        # Invalid name
        value: Any
        for value in (None, "", "   "):
            self.assertRaises(ValueError, self.config.create_factory_configuration, value)

        # Invalid type
        for value in ([], 12, True):
            self.assertRaises(ValueError, self.config.create_factory_configuration, value)

        # Create a configuration
        factory_pid = "test.ca.factory"
        config = self.config.create_factory_configuration(factory_pid)
        pid = config.get_pid()

        # Check validity
        self.assertIsNotNone(config, "No configuration returned")
        self.assertEqual(config.get_factory_pid(), factory_pid, "Wrong factory PID")
        self.assertIn(factory_pid, pid, "PID doesn't contain the Factory PID")
        self.assertIsNone(config.get_properties(), "Fresh factory configuration has properties")

        # Check Factory/Configuration PIDs
        self.assertRaises(KeyError, self.config.get_configuration, factory_pid)

        # Delete the configuration
        config.delete()

        # Create a new one
        config2 = self.config.create_factory_configuration(factory_pid)

        # They must be different and have different PID
        self.assertIsNot(config, config2, "ConfigAdmin returned a deleted factory configuration")
        self.assertNotEqual(pid, config2.get_pid(), "Same PID for new configuration")

        # Delete the new one
        config2.delete()

    def testGetConfiguration(self) -> None:
        """
        Tests the get_configuration method (and the configuration bean)
        """
        # Create the configuration
        pid = "test.ca.get"
        config = self.config.get_configuration(pid)

        # It is not valid and has no properties
        self.assertFalse(config.is_valid(), "Fresh configuration is valid")
        self.assertIsNone(config.get_properties(), "Fresh configuration has properties")

        # Update properties
        config.update({"answer": 42})

        # Ensure we still have the same object
        self.assertIs(config, self.config.get_configuration(pid), "Configuration object changed")

        # Ensure we have the new properties
        self.assertTrue(config.is_valid(), "Configuration is still invalid")
        properties = config.get_properties()
        assert properties is not None
        self.assertEqual(properties[services.CONFIG_PROP_PID], pid, "Different PID in properties")
        self.assertEqual(properties["answer"], 42, "Configuration not updated")

        # Delete the configuration
        config.delete()

        # Ensure we'll get a new one
        config2 = self.config.get_configuration(pid)
        self.assertIsNot(config, config2, "ConfigAdmin returned a deleted configuration")

        # Clean up
        config2.delete()

    def testListConfiguration(self) -> None:
        """
        Tests the list configuration method
        """
        # There should be nothing at first
        configs = self.config.list_configurations()
        assert configs is not None
        self.assertSetEqual(set(configs), set(), "Non-empty result set")

        # Add a configuration
        pid = "test.ca.list"
        config = self.config.get_configuration(pid)

        # Simple pre-check
        self.assertFalse(config.is_valid(), "Fresh configuration is valid")

        # It must be visible, but must not match filters
        self.assertSetEqual(set(self.config.list_configurations()), {config}, "Incorrect result set")

        ldap_filter = f"({services.CONFIG_PROP_PID}={pid})"
        self.assertSetEqual(
            set(self.config.list_configurations(ldap_filter)), set(), "Invalid configuration matches a filter"
        )

        # Update the configuration
        config.update({"arthur": "dent"})

        # It must be visible, even with filters
        self.assertSetEqual(set(self.config.list_configurations()), {config}, "Incorrect result set")

        filters = [  # PID
            f"({services.CONFIG_PROP_PID}={pid})".format(services.CONFIG_PROP_PID, pid),
            # Property
            "(arthur=dent)",
            # Both
            f"(&({services.CONFIG_PROP_PID}={pid})(arthur=dent))",
        ]

        for ldap_filter in filters:
            self.assertSetEqual(
                set(self.config.list_configurations(ldap_filter)),
                {config},
                f"Configuration doesn't match filter {ldap_filter}",
            )

        # Add a new configuration
        config2 = self.config.get_configuration(pid + "-bis")
        self.assertSetEqual(set(self.config.list_configurations()), {config, config2}, "Incorrect result set")

        # Delete it
        config2.delete()
        self.assertSetEqual(set(self.config.list_configurations()), {config}, "Incorrect result set")

        # Delete the first one
        config.delete()
        self.assertSetEqual(set(configs), set(), "Non-empty result set")

    def testPersistence(self) -> None:
        """
        Tests configuration reload
        """
        pid = "test.ca.persistence"
        props = {"zaphod": "beeblebrox"}

        # Create a configuration
        config = self.config.get_configuration(pid)
        config.update(props)

        # Forget it locally
        config = None  # type: ignore

        # Stop the framework
        self.tearDown()

        # Restart it
        self.setUp()

        # Reload the configuration
        config = self.config.get_configuration(pid)

        # Compare properties
        self.assertDictContains(
            props, config.get_properties() or {}, "Properties lost with framework restart"
        )

        # Delete the configuration
        config.delete()


# ------------------------------------------------------------------------------


class ManagedServiceTest(unittest.TestCase):
    """
    Tests the behavior of managed services
    """

    framework: pelix.framework.Framework
    config_ref: Optional[ServiceReference[services.IConfigurationAdmin]]
    config: services.IConfigurationAdmin

    def setUp(self) -> None:
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": conf_folder}
        )
        self.framework.start()
        context = self.framework.get_bundle_context()

        # Get the ConfigAdmin service
        self.config_ref = context.get_service_reference(services.SERVICE_CONFIGURATION_ADMIN)
        assert self.config_ref is not None
        self.config = context.get_service(self.config_ref)

        # Install the test bundle (don't start it)
        self.bundle = context.install_bundle("tests.services.configadmin_bundle")
        self.pid = self.bundle.get_module().CONFIG_PID

        # Remove existing configurations
        for config in self.config.list_configurations():
            config.delete()

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Remove existing configurations
        for config in self.config.list_configurations():
            config.delete()

        # Release the service
        if self.config_ref is not None:
            self.framework.get_bundle_context().unget_service(self.config_ref)
            self.config_ref = None

        pelix.framework.FrameworkFactory.delete_framework()
        self.config = None  # type: ignore

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Cleans up after all tests have been executed
        """
        shutil.rmtree(conf_folder)

    def get_ref(self) -> ServiceReference[services.IManagedService]:
        """
        Retrieves the reference to the managed service provided by the test
        bundle
        """
        return self.bundle.get_registered_services()[0]

    def pause(self) -> None:
        """
        Small pause to let the task pool notify the services
        """
        time.sleep(0.2)

    def check_call_count(self, test_svc: "Configurable", expected_count: int) -> None:
        """
        Checks if the given test service has been called X times
        """
        self.assertEqual(
            test_svc.call_count, expected_count, f"updated() called more than {expected_count} times"
        )
        test_svc.call_count = 0

    def testNoConfigDelete(self) -> None:
        """
        Tests the behaviour of the service with an empty configuration
        """
        # Start the test bundle
        self.bundle.start()

        # Get the service
        with use_service(self.framework.get_bundle_context(), self.get_ref()) as svc:
            svc = cast("Configurable", svc)

            # Create the configuration
            config = self.config.get_configuration(self.pid)

            # Give some time for the possible erroneous notification
            self.pause()

            # Nothing should have happened yet
            self.assertIsNone(svc.value, "Value has been set")
            self.assertFalse(svc.deleted, "Configuration considered as deleted")

            # Delete the configuration
            config.delete()

            # Give some time for the possible erroneous notification
            self.pause()

            # Nothing should have happened either
            self.assertIsNone(svc.value, "Value has been set")
            self.assertFalse(svc.deleted, "Configuration considered as deleted")

    def testEarlyConfig(self) -> None:
        """
        Tests the behaviour if a configuration is already set when the managed
        service is registered
        """
        # Create the configuration
        config = self.config.get_configuration(self.pid)
        config.update({"config.value": 42})

        # Start the test bundle
        self.bundle.start()

        # Get the service
        with use_service(self.framework.get_bundle_context(), self.get_ref()) as svc:
            svc = cast("Configurable", svc)

            # Give some time for the notification
            self.pause()

            # The service should already have been configured
            self.assertEqual(svc.value, 42, "Value hasn't been set")
            self.assertFalse(svc.deleted, "Configuration considered as deleted")

            # Delete the configuration
            config.delete()

            # Give some time for the notification
            self.pause()

            # The flag must have been set
            self.assertTrue(svc.deleted, "Configuration considered as deleted")

    def testLateConfig(self) -> None:
        """
        Tests the behaviour if a configuration is created after the managed
        service has been registered
        """
        # Start the test bundle
        self.bundle.start()

        # Get the service
        with use_service(self.framework.get_bundle_context(), self.get_ref()) as svc:
            svc = cast("Configurable", svc)

            # Give some time for the notification
            self.pause()

            # Nothing should have happened yet
            self.assertIsNone(svc.value, "Value has been set")
            self.assertFalse(svc.deleted, "Configuration considered as deleted")

            # Create the configuration
            config = self.config.get_configuration(self.pid)
            config.update({"config.value": 42})

            # Update is done a another thread
            self.pause()

            # The service should have been configured
            self.assertEqual(svc.value, 42, "Value hasn't been set")
            self.assertFalse(svc.deleted, "Configuration considered as deleted")

            # Delete the configuration
            config.delete()

            # Give some time for the notification
            self.pause()

            # The flag must have been set
            self.assertTrue(svc.deleted, "Configuration considered as deleted")

    def testUpdateConfig(self) -> None:
        """
        Tests the behaviour if a configuration is updated
        """
        # Create the configuration
        config = self.config.get_configuration(self.pid)

        # Start the test bundle
        self.bundle.start()

        # Get the service
        with use_service(self.framework.get_bundle_context(), self.get_ref()) as svc:
            svc = cast("Configurable", svc)

            # Give some time for the notification
            self.pause()

            # Nothing should have happened yet
            self.check_call_count(svc, 0)
            self.assertIsNone(svc.value, "Value has been set")
            self.assertFalse(svc.deleted, "Configuration considered as deleted")

            # Update the configuration
            config.update({"config.value": 42})

            # Update is done a another thread
            self.pause()

            # The service should have been configured
            self.check_call_count(svc, 1)
            self.assertEqual(svc.value, 42, "Value hasn't been set")
            self.assertFalse(svc.deleted, "Configuration considered as deleted")

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

    framework: pelix.framework.Framework
    config_ref: Optional[ServiceReference[services.IConfigurationAdmin]]
    config: services.IConfigurationAdmin

    def setUp(self) -> None:
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": conf_folder}
        )
        self.framework.start()
        context = self.framework.get_bundle_context()

        # in FileInstall
        self.bnd_fileinstall = context.install_bundle("pelix.services.fileinstall")

        # Get the ConfigAdmin service
        self.config_ref = context.get_service_reference(services.SERVICE_CONFIGURATION_ADMIN)
        assert self.config_ref is not None
        self.config = context.get_service(self.config_ref)

        # Install the test bundle (don't start it)
        self.bundle = context.install_bundle("tests.services.configadmin_bundle")
        self.pid = self.bundle.get_module().CONFIG_PID

    def start_fileinstall(self) -> None:
        """
        Starts the file install bundle and tweaks its service
        """
        # Start the bundle
        self.bnd_fileinstall.start()

        # Speed up the poll time
        context = self.framework.get_bundle_context()
        fileinstall_ref = context.get_service_reference(services.FileInstall)
        assert fileinstall_ref is not None
        with use_service(context, fileinstall_ref) as svc:
            svc._poll_time = 0.1  # type: ignore
            time.sleep(0.5)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        if self.config_ref is not None:
            # Release the service
            self.framework.get_bundle_context().unget_service(self.config_ref)
        self.config_ref = None

        pelix.framework.FrameworkFactory.delete_framework()
        self.config = None  # type: ignore

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Cleans up after all tests have been executed
        """
        shutil.rmtree(conf_folder)

    def get_ref(self) -> ServiceReference[services.IManagedService]:
        """
        Retrieves the reference to the managed service provided by the test
        bundle
        """
        return self.bundle.get_registered_services()[0]

    def check_call_count(self, test_svc: "Configurable", expected_count: int) -> None:
        """
        Checks if the given test service has been called X times
        """
        self.assertEqual(test_svc.call_count, expected_count)
        test_svc.call_count = 0

    def touch(self, filepath: str) -> None:
        """
        Updates the modification time of the given file
        """
        with open(filepath, "r"):
            os.utime(filepath, None)

    def write(self, filepath: str, value: Any) -> None:
        """
        Writes the property dictionary in JSON
        """
        props = {"config.value": value}
        with open(filepath, "w") as filep:
            filep.write(json.dumps(props))

        try:
            # Change modification time to bypass weak time resolution of
            # the underlying file system
            module_stat = os.stat(filepath)
            os.utime(filepath, (module_stat.st_atime, module_stat.st_mtime + 1))
        except OSError:
            # Can't touch the file, hope that the OS will see the write update
            pass

    def testAddUpdateDelete(self) -> None:
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
        time.sleep(0.4)

        with use_service(context, ref) as svc:
            svc = cast("Configurable", svc)
            self.check_call_count(svc, 0)
            self.assertIsNone(svc.value, "Value has been set")

        # Get the watched folder
        persistence_ref = context.get_service_reference(services.IConfigurationAdminPersistence)
        assert persistence_ref is not None
        folder = persistence_ref.get_property(services.PROP_FILEINSTALL_FOLDER)

        # JSON persistence file name
        filepath = os.path.join(folder, self.pid + ".config.js")

        # Create the empty configuration
        value = "Ni !"
        self.write(filepath, value)

        # Wait a little
        time.sleep(0.4)

        # Check if the service has been updated
        with use_service(context, ref) as svc:
            svc = cast("Configurable", svc)
            self.assertEqual(svc.value, value, "Incorrect initial value")
            self.check_call_count(svc, 1)

        # Update the properties
        value = "Ecky-ecky-ecky-ecky-pikang-zoom-boing"
        self.write(filepath, value)

        # Wait a little
        time.sleep(0.4)

        # Check if the service has been updated
        with use_service(context, ref) as svc:
            svc = cast("Configurable", svc)
            self.assertEqual(svc.value, value, "Value not updated")
            self.check_call_count(svc, 1)

            # Reset the flags
            svc.reset()

        # Touch the file
        self.touch(filepath)

        # Wait a little
        time.sleep(0.4)

        # Check if the service has been updated
        with use_service(context, ref) as svc:
            svc = cast("Configurable", svc)
            self.check_call_count(svc, 0)
            self.assertIsNone(svc.value, "File updated after simple touch")
            self.assertFalse(svc.deleted, "Configuration considered deleted")

        # Delete the file
        os.remove(filepath)

        # Wait a little
        time.sleep(0.4)

        with use_service(context, ref) as svc:
            svc = cast("Configurable", svc)
            self.check_call_count(svc, 1)
            self.assertTrue(svc.deleted, "Configuration not deleted")


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
