#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests for the ConfigurationAdmin tests

:author: Thomas Calmant
"""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, cast

import pelix.framework
from pelix import constants, services
from pelix.internals.registry import ServiceReference
from pelix.services.configadmin import (
    ConfigurationDirectory,
    IConfigurationAdminDirectory,
    JsonPersistence,
)
from pelix.utilities import use_service

if TYPE_CHECKING:
    from .configadmin_bundle import Configurable
    from .configadmin_factory_bundle import ConfigurableFactory

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
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
    config_ref: ServiceReference[services.IConfigurationAdmin] | None
    config: services.IConfigurationAdmin

    def assertDictContains(
        self, subset: dict[str, Any], tested: dict[str, Any] | None, msg: Any = None
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
        self.addCleanup(self.framework.delete, True)
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
    config_ref: ServiceReference[services.IConfigurationAdmin] | None
    config: services.IConfigurationAdmin

    def setUp(self) -> None:
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": conf_folder}
        )
        self.addCleanup(self.framework.delete, True)
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

    def testNoPhantomConfiguration(self) -> None:
        """
        Registering a managed service for a PID which has no configuration
        must not create one
        """
        self.assertFalse(list(self.config.list_configurations()))

        # Start the test bundle: it registers a managed service
        self.bundle.start()
        self.pause()

        self.assertFalse(
            [config.get_pid() for config in self.config.list_configurations()],
            "A configuration has been created out of thin air",
        )

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


class ManagedServiceFactoryTest(unittest.TestCase):
    """
    Tests the behavior of managed service factories
    """

    framework: pelix.framework.Framework
    config_ref: ServiceReference[services.IConfigurationAdmin] | None
    config: services.IConfigurationAdmin

    def setUp(self) -> None:
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": conf_folder}
        )
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        context = self.framework.get_bundle_context()

        # Get the ConfigAdmin service
        self.config_ref = context.get_service_reference(services.IConfigurationAdmin)
        assert self.config_ref is not None
        self.config = context.get_service(self.config_ref)

        # Install the test bundle (don't start it)
        self.bundle = context.install_bundle("tests.services.configadmin_factory_bundle")
        self.factory_pid = self.bundle.get_module().FACTORY_PID

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
        shutil.rmtree(conf_folder, ignore_errors=True)

    def get_ref(self) -> ServiceReference[services.IManagedServiceFactory]:
        """
        Retrieves the reference to the managed service factory provided by the
        test bundle
        """
        return self.bundle.get_registered_services()[0]

    def pause(self) -> None:
        """
        Small pause to let the task pool notify the services
        """
        time.sleep(0.2)

    def testFactoryConfigurations(self) -> None:
        """
        The factory must be notified of the configurations created before and
        after its registration
        """
        # Configuration created before the factory is registered
        early = self.config.create_factory_configuration(self.factory_pid)
        early.update({"config.value": 21})

        self.bundle.start()
        self.pause()

        with use_service(self.framework.get_bundle_context(), self.get_ref()) as svc:
            svc = cast("ConfigurableFactory", svc)

            self.assertEqual(list(svc.configurations), [early.get_pid()])
            self.assertEqual(svc.configurations[early.get_pid()]["config.value"], 21)

            # The automatic properties must be there
            self.assertEqual(
                svc.configurations[early.get_pid()][services.CONFIG_PROP_FACTORY_PID],
                self.factory_pid,
            )
            self.assertEqual(svc.configurations[early.get_pid()][services.CONFIG_PROP_PID], early.get_pid())

            # Configuration created after the factory is registered
            late = self.config.create_factory_configuration(self.factory_pid)
            late.update({"config.value": 42})
            self.pause()

            self.assertEqual(len(svc.configurations), 2)
            self.assertEqual(svc.configurations[late.get_pid()]["config.value"], 42)

            # Update of an existing configuration
            svc.reset()
            late.update({"config.value": 43})
            self.pause()

            self.assertEqual(svc.call_count, 1)
            self.assertEqual(svc.configurations[late.get_pid()]["config.value"], 43)

            # Deletion
            svc.reset()
            late_pid = late.get_pid()
            late.delete()
            self.pause()

            self.assertEqual(svc.deleted_pids, [late_pid])
            self.assertNotIn(late_pid, svc.configurations)

    def testNoUpdateBeforeProperties(self) -> None:
        """
        A configuration which has never been updated must not be notified
        """
        self.config.create_factory_configuration(self.factory_pid)

        self.bundle.start()
        self.pause()

        with use_service(self.framework.get_bundle_context(), self.get_ref()) as svc:
            svc = cast("ConfigurableFactory", svc)
            self.assertEqual(svc.configurations, {})
            self.assertEqual(svc.call_count, 0)


# ------------------------------------------------------------------------------


class _ReentrantService(services.IManagedService):
    """
    Managed service which calls back into ConfigurationAdmin from its
    notification
    """

    def __init__(self, config_admin: services.IConfigurationAdmin) -> None:
        """
        :param config_admin: The ConfigurationAdmin service
        """
        self.__config_admin = config_admin
        self.__thread: threading.Thread | None = None

        self.call_count = 0

        # True if the last notification let another thread use the directory
        self.directory_free = False

    def __create_configuration(self) -> None:
        """
        Makes a call which needs the configurations directory
        """
        self.__config_admin.create_factory_configuration("test.reentrant.factory")

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        self.call_count += 1

        # Call back into ConfigurationAdmin from another thread: a direct call
        # would deadlock if the directory is locked, whereas this one is only
        # delayed until this notification returns
        self.__thread = threading.Thread(target=self.__create_configuration, daemon=True)
        self.__thread.start()
        self.__thread.join(5)
        self.directory_free = not self.__thread.is_alive()

    def reset(self) -> bool:
        """
        Waits for the end of the call back of the last notification and resets
        the flags

        :return: True if the call back is over
        """
        thread, self.__thread = self.__thread, None
        if thread is not None:
            thread.join(10)
            if thread.is_alive():
                return False

        self.call_count = 0
        self.directory_free = False
        return True


class ConfigurationDirectoryTest(unittest.TestCase):
    """
    Tests the locking of the configurations directory
    """

    PID = "test.reentrant"

    def setUp(self) -> None:
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": conf_folder}
        )
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        config_ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert config_ref is not None
        self.config = self.context.get_service(config_ref)

        directory_ref = self.context.get_service_reference(IConfigurationAdminDirectory)
        assert directory_ref is not None
        self.directory = self.context.get_service(directory_ref)

        # Register the service before the configuration is valid: it is not
        # notified yet
        self.service = _ReentrantService(self.config)
        configuration = self.config.get_configuration(self.PID)
        self.context.register_service(
            services.IManagedService, self.service, {constants.SERVICE_PID: self.PID}
        )

        # Make the configuration valid. Nothing holds the directory lock here,
        # so this first notification always goes through
        configuration.update({"answer": 0})
        self.assertTrue(self.service.reset(), "Notification of the first update didn't return")

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        self.service.reset()
        pelix.framework.FrameworkFactory.delete_framework()

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Cleans up after all tests have been executed
        """
        shutil.rmtree(conf_folder, ignore_errors=True)

    def testUpdateNotifiesOutsideOfTheLock(self) -> None:
        """
        A managed service notified of an update must be able to call back into
        ConfigurationAdmin
        """
        self.directory.update(self.PID, {"answer": 42})

        self.assertEqual(self.service.call_count, 1)
        self.assertTrue(self.service.directory_free, "Directory locked while notifying an update")

    def testDeleteNotifiesOutsideOfTheLock(self) -> None:
        """
        A managed service notified of a deletion must be able to call back into
        ConfigurationAdmin
        """
        self.directory.delete(self.PID)

        self.assertEqual(self.service.call_count, 1)
        self.assertTrue(self.service.directory_free, "Directory locked while notifying a deletion")


# ------------------------------------------------------------------------------


class _WatchingService(services.IManagedService):
    """
    Managed service which looks at ConfigurationAdmin while it is notified of
    the deletion of its configuration
    """

    def __init__(
        self,
        config_admin: services.IConfigurationAdmin,
        directory: IConfigurationAdminDirectory,
        pid: str,
    ) -> None:
        """
        :param config_admin: The ConfigurationAdmin service
        :param directory: The configurations directory
        :param pid: PID of the followed configuration
        """
        self.__config_admin = config_admin
        self.__directory = directory
        self.__pid = pid

        # Number of notified deletions
        self.deletions = 0

        # What ConfigurationAdmin showed during the deletion
        self.listed_pids: set[str] = set()
        self.directory_lookup: services.Configuration | None = None
        self.replacement: services.Configuration | None = None

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        if properties is not None:
            return

        self.deletions += 1
        self.listed_pids = {config.get_pid() for config in self.__config_admin.list_configurations()}

        try:
            self.directory_lookup = self.__directory.get_configuration(self.__pid)
        except KeyError:
            self.directory_lookup = None

        # A new configuration must be usable for this PID right away
        self.replacement = self.__config_admin.get_configuration(self.__pid)


class DeletedConfigurationTest(unittest.TestCase):
    """
    Tests the visibility of a configuration which is being deleted
    """

    PID = "test.deleted"

    def setUp(self) -> None:
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": conf_folder}
        )
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        config_ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert config_ref is not None
        self.config = self.context.get_service(config_ref)

        directory_ref = self.context.get_service_reference(IConfigurationAdminDirectory)
        assert directory_ref is not None
        self.directory = self.context.get_service(directory_ref)

        self.service = _WatchingService(self.config, self.directory, self.PID)
        self.context.register_service(
            services.IManagedService, self.service, {constants.SERVICE_PID: self.PID}
        )

        # Make the configuration valid, so that its deletion is notified
        self.config.get_configuration(self.PID).update({"answer": 42})

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        pelix.framework.FrameworkFactory.delete_framework()

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Cleans up after all tests have been executed
        """
        shutil.rmtree(conf_folder, ignore_errors=True)

    def testDeletedConfigurationIsHidden(self) -> None:
        """
        A configuration which is being deleted must not be given back by
        ConfigurationAdmin, and its PID must be usable again right away
        """
        self.directory.delete(self.PID)
        self.assertEqual(self.service.deletions, 1)

        # The dying configuration was already gone for its users
        self.assertNotIn(self.PID, self.service.listed_pids)
        self.assertIsNone(self.service.directory_lookup)

        # The configuration created in the meantime must have survived the end
        # of the deletion
        replacement = self.service.replacement
        assert replacement is not None
        self.assertIsNone(replacement.get_properties())
        self.assertIs(self.directory.get_configuration(self.PID), replacement)


class _MemoryPersistence(services.IConfigurationAdminPersistence):
    """
    Persistence service which keeps the configurations in memory
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.storage: dict[str, dict[str, Any]] = {}

    def get_pids(self) -> Iterable[str]:
        """
        Returns the PIDs of the stored configurations
        """
        return list(self.storage)

    def exists(self, pid: str) -> bool:
        """
        Checks if a configuration is stored
        """
        return pid in self.storage

    def load(self, pid: str) -> dict[str, Any]:
        """
        Loads a stored configuration
        """
        return self.storage[pid].copy()

    def store(self, pid: str, properties: dict[str, Any]) -> None:
        """
        Stores a configuration
        """
        self.storage[pid] = properties.copy()

    def delete(self, pid: str) -> bool:
        """
        Forgets a stored configuration
        """
        return self.storage.pop(pid, None) is not None


class _FailingPersistence(_MemoryPersistence):
    """
    Persistence service which refuses to delete its configurations
    """

    def delete(self, pid: str) -> bool:
        """
        Always fails to delete the configuration
        """
        raise OSError(f"Can't delete {pid}")


class _LookupPersistence(_MemoryPersistence):
    """
    Persistence service which looks for the configuration it is deleting: at
    that point, the configuration is still stored
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        super().__init__()

        # The ConfigurationAdmin service, given by the test
        self.config_admin: services.IConfigurationAdmin | None = None

        # What ConfigurationAdmin gave back during the deletion
        self.lookup: services.Configuration | None = None

    def delete(self, pid: str) -> bool:
        """
        Looks for the configuration, then forgets it
        """
        if self.config_admin is not None and self.lookup is None:
            # Look only once: the lookup itself can start a deletion
            self.lookup = self.config_admin.get_configuration(pid)

        return super().delete(pid)


class _DeletionCounter(services.IManagedService):
    """
    Managed service which counts the deletions of its configuration
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.deletions = 0

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        if properties is None:
            self.deletions += 1


class PersistenceErrorTest(unittest.TestCase):
    """
    Tests the deletion of a configuration when the persistence service fails
    """

    PID = "test.persistence.error"

    def setUp(self) -> None:
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core",), {"configuration.folder": conf_folder}
        )
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Register the services before ConfigurationAdmin is started: the best
        # ranked persistence is the one used for the new configurations
        self.persistence = _FailingPersistence()
        self.context.register_service(
            services.IConfigurationAdminPersistence,
            self.persistence,
            {constants.SERVICE_RANKING: 1000},
        )

        self.service = _DeletionCounter()
        self.context.register_service(
            services.IManagedService, self.service, {constants.SERVICE_PID: self.PID}
        )

        self.context.install_bundle("pelix.services.configadmin").start()

        config_ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert config_ref is not None
        self.config = self.context.get_service(config_ref)

        directory_ref = self.context.get_service_reference(IConfigurationAdminDirectory)
        assert directory_ref is not None
        self.directory = self.context.get_service(directory_ref)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        pelix.framework.FrameworkFactory.delete_framework()

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Cleans up after all tests have been executed
        """
        shutil.rmtree(conf_folder, ignore_errors=True)

    def testDeletionErrorStillNotifies(self) -> None:
        """
        A persistence error must be given back to the caller, but must not stop
        the deletion of the configuration
        """
        configuration = self.config.get_configuration(self.PID)
        configuration.update({"answer": 42})
        self.assertIn(self.PID, self.persistence.storage, "The test persistence wasn't used")

        self.assertRaises(OSError, configuration.delete)

        # The managed service has been notified and the configuration is gone
        self.assertEqual(self.service.deletions, 1)
        self.assertFalse(configuration.is_valid())
        self.assertRaises(KeyError, self.directory.get_configuration, self.PID)

    def testDirectoryDeletionErrorCleansUp(self) -> None:
        """
        A persistence error must not stop the directory from forgetting the
        configuration it deletes
        """
        factory_pid = f"{self.PID}.factory"
        configuration = self.config.create_factory_configuration(factory_pid)
        configuration.update({"answer": 42})

        pid = configuration.get_pid()
        self.assertIn(pid, self.persistence.storage, "The test persistence wasn't used")

        self.assertRaises(OSError, self.directory.delete, pid)

        # The configuration is gone, even though it is still stored
        directory = cast(ConfigurationDirectory, self.directory)
        self.assertFalse(directory.exists(pid), "Configuration still in the directory")
        self.assertRaises(KeyError, self.directory.get_configuration, pid)
        self.assertEqual(
            self.directory.get_factory_configurations(factory_pid),
            set(),
            "Configuration still associated to its factory",
        )


# ------------------------------------------------------------------------------


class DeletionLookupTest(unittest.TestCase):
    """
    Tests the lookup of a configuration while it is being deleted
    """

    PID = "test.deletion.lookup"

    def setUp(self) -> None:
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core",), {"configuration.folder": conf_folder}
        )
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Register the persistence before ConfigurationAdmin is started: the
        # best ranked one is used for the new configurations
        self.persistence = _LookupPersistence()
        self.context.register_service(
            services.IConfigurationAdminPersistence,
            self.persistence,
            {constants.SERVICE_RANKING: 1000},
        )

        self.context.install_bundle("pelix.services.configadmin").start()

        config_ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert config_ref is not None
        self.config = self.context.get_service(config_ref)
        self.persistence.config_admin = self.config

        directory_ref = self.context.get_service_reference(IConfigurationAdminDirectory)
        assert directory_ref is not None
        self.directory = self.context.get_service(directory_ref)

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        pelix.framework.FrameworkFactory.delete_framework()

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Cleans up after all tests have been executed
        """
        shutil.rmtree(conf_folder, ignore_errors=True)

    def testLookupDuringDeletion(self) -> None:
        """
        A lookup made while the configuration is being removed from the
        persistence must give back that configuration, not a copy loaded from
        its stored properties
        """
        configuration = self.config.get_configuration(self.PID)
        configuration.update({"answer": 42})
        self.assertIn(self.PID, self.persistence.storage, "The test persistence wasn't used")

        configuration.delete()

        self.assertIs(self.persistence.lookup, configuration, "A duplicate configuration was created")

        # The deletion went through
        self.assertNotIn(self.PID, self.persistence.storage, "Configuration still stored")
        self.assertRaises(KeyError, self.directory.get_configuration, self.PID)


# ------------------------------------------------------------------------------


class FileInstallTest(unittest.TestCase):
    """
    Tests the behavior of FileInstall with ConfigurationAdmin
    """

    framework: pelix.framework.Framework
    config_ref: ServiceReference[services.IConfigurationAdmin] | None
    config: services.IConfigurationAdmin

    def setUp(self) -> None:
        """
        Sets up the test
        """
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": conf_folder}
        )
        self.addCleanup(self.framework.delete, True)
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

    def testAddFactoryConfiguration(self) -> None:
        """
        A configuration file added in the watched folder must reach the managed
        service factories, not only the managed services
        """
        context = self.framework.get_bundle_context()

        # Install and start the managed service factory
        factory_bundle = context.install_bundle("tests.services.configadmin_factory_bundle")
        factory_bundle.start()
        factory_pid = factory_bundle.get_module().FACTORY_PID
        factory_ref = factory_bundle.get_registered_services()[0]

        # Start file install
        self.start_fileinstall()

        # Get the watched folder
        persistence_ref = context.get_service_reference(services.IConfigurationAdminPersistence)
        assert persistence_ref is not None
        folder = persistence_ref.get_property(services.PROP_FILEINSTALL_FOLDER)

        # Write a factory configuration file
        pid = f"{factory_pid}-fileinstall"
        filepath = os.path.join(folder, pid + ".config.js")
        self.addCleanup(os.remove, filepath)

        with open(filepath, "w") as filep:
            json.dump(
                {
                    services.CONFIG_PROP_PID: pid,
                    services.CONFIG_PROP_FACTORY_PID: factory_pid,
                    "config.value": 42,
                },
                filep,
            )

        # Wait for the folder to be polled
        for _ in range(30):
            time.sleep(0.2)
            with use_service(context, factory_ref) as svc:
                if cast("ConfigurableFactory", svc).configurations:
                    break

        with use_service(context, factory_ref) as svc:
            svc = cast("ConfigurableFactory", svc)
            self.assertIn(pid, svc.configurations, "Managed service factory not notified")
            self.assertEqual(svc.configurations[pid]["config.value"], 42)


# ------------------------------------------------------------------------------


class JsonPersistencePidTest(unittest.TestCase):
    """
    Tests the handling of PIDs by the JSON persistence.

    A PID is used as a file name: it must not be possible to read, write or
    delete a file outside of the configuration folder.
    """

    def setUp(self) -> None:
        """
        Prepares a persistence service with its own configuration folder
        """
        self.temp_dir = tempfile.mkdtemp(prefix="ipopo-configadmin-test-")
        self.conf_folder = os.path.join(self.temp_dir, "conf")
        self.outside_folder = os.path.join(self.temp_dir, "outside")
        os.makedirs(self.conf_folder)
        os.makedirs(self.outside_folder)

        self.persistence = JsonPersistence()
        self.persistence._conf_folder = self.conf_folder

    def tearDown(self) -> None:
        """
        Cleans up the temporary folders
        """
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def get_traversal_pids(self) -> list[str]:
        """
        Returns PIDs trying to point outside of the configuration folder
        """
        return [
            "../outside/evil",
            "../../outside/evil",
            "../" * 10 + "tmp/evil",
            "sub/evil",
            "/etc/cron.d/evil",
            "..\\..\\outside\\evil",
            "sub\\evil",
            "a\0b",
            "",
        ]

    def test_traversal_pids_are_refused(self) -> None:
        """
        A PID pointing outside of the configuration folder must be refused
        """
        for pid in self.get_traversal_pids():
            with self.subTest(pid=pid):
                self.assertRaises(ValueError, self.persistence._get_file, pid)

    def test_valid_pids_are_accepted(self) -> None:
        """
        Usual PIDs must still be usable, including the generated factory ones
        """
        for pid in (
            "test.ca.bundle",
            "Configurable",
            "pelix.services.configadmin",
            "spam.factory-4d69c0de-0000-4000-8000-000000000000",
            "pid_with_underscore",
            "pid-with-dash",
            "pid with spaces",
            "..",
        ):
            with self.subTest(pid=pid):
                path = self.persistence._get_file(pid)
                self.assertEqual(
                    os.path.dirname(path),
                    os.path.abspath(self.conf_folder),
                    "Configuration file outside of the configuration folder",
                )

    def test_store_refuses_traversal(self) -> None:
        """
        Storing a configuration must not write outside of the folder
        """
        for pid in self.get_traversal_pids():
            with self.subTest(pid=pid):
                self.assertRaises(ValueError, self.persistence.store, pid, {"pwned": True})

        self.assertListEqual(os.listdir(self.outside_folder), [], "A file has been written outside")

    def test_load_refuses_traversal(self) -> None:
        """
        Loading a configuration must not read outside of the folder
        """
        # Write a file outside of the configuration folder
        target = os.path.join(self.outside_folder, "evil.config.js")
        with open(target, "w") as filep:
            json.dump({"secret": "value"}, filep)

        for pid in self.get_traversal_pids():
            with self.subTest(pid=pid):
                self.assertRaises(ValueError, self.persistence.load, pid)

    def test_delete_refuses_traversal(self) -> None:
        """
        Deleting a configuration must not remove a file outside of the folder
        """
        target = os.path.join(self.outside_folder, "evil.config.js")
        with open(target, "w") as filep:
            json.dump({"secret": "value"}, filep)

        for pid in self.get_traversal_pids():
            with self.subTest(pid=pid):
                self.assertFalse(self.persistence.delete(pid))

        self.assertTrue(os.path.isfile(target), "A file has been deleted outside of the folder")

    def test_exists_refuses_traversal(self) -> None:
        """
        A configuration outside of the folder must not be visible
        """
        target = os.path.join(self.outside_folder, "evil.config.js")
        with open(target, "w") as filep:
            json.dump({"secret": "value"}, filep)

        for pid in self.get_traversal_pids():
            with self.subTest(pid=pid):
                self.assertFalse(self.persistence.exists(pid))

    def test_store_load_round_trip(self) -> None:
        """
        Valid configurations must still be stored and loaded
        """
        properties = {"spam": "eggs", "count": 42}
        self.assertFalse(self.persistence.exists("test.pid"))

        self.persistence.store("test.pid", properties)
        self.assertTrue(self.persistence.exists("test.pid"))
        self.assertDictEqual(self.persistence.load("test.pid"), properties)
        self.assertIn("test.pid", self.persistence.get_pids())

        self.assertTrue(self.persistence.delete("test.pid"))
        self.assertFalse(self.persistence.exists("test.pid"))


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
