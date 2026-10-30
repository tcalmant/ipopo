#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests for the ConfigurationAdmin tests

:author: Thomas Calmant
"""

import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import pelix.framework
from pelix import constants, services
from pelix.internals.registry import ServiceReference, ServiceRegistration
from pelix.services.configadmin import (
    Configuration,
    ConfigurationAdmin,
    ConfigurationDirectory,
    IConfigurationAdminDirectory,
    JsonPersistence,
)
from pelix.utilities import use_service

if TYPE_CHECKING:
    from .configadmin_bundle import Configurable
    from .configadmin_factory_bundle import ConfigurableFactory

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
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
        self.config = None

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
        config = None

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
        self.config = None

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
        self.config = None

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
        # Work on a local reference: reset() can clear the member
        thread = threading.Thread(target=self.__create_configuration, daemon=True)
        self.__thread = thread
        thread.start()
        thread.join(5)
        self.directory_free = not thread.is_alive()

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
        # so this first notification always goes through. The pool can be the
        # one giving it, while notifying the registration of the service: wait
        # for it, so that the tests start with a quiet service
        configuration.update({"answer": 0})
        pool = cast(ConfigurationAdmin, self.config)._pool
        assert pool is not None
        pool.enqueue(lambda: None).result(5)
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
        self.config = None

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

    def wait_until(self, condition: Callable[[], bool], timeout: float = 5) -> None:
        """
        Waits for a condition to become true: FileInstall polls the folder, so
        a change is seen after a delay which depends on the load of the host

        :param condition: Condition to wait for
        :param timeout: Maximum time to wait, in seconds
        """
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            time.sleep(0.05)

    def touch(self, filepath: str) -> None:
        """
        Updates the modification time of the given file
        """
        with open(filepath):
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

        # Check if the service has been updated
        with use_service(context, ref) as svc:
            svc = cast("Configurable", svc)
            self.wait_until(lambda: svc.value == value)
            self.assertEqual(svc.value, value, "Incorrect initial value")
            self.check_call_count(svc, 1)

        # Update the properties
        value = "Ecky-ecky-ecky-ecky-pikang-zoom-boing"
        self.write(filepath, value)

        # Check if the service has been updated
        with use_service(context, ref) as svc:
            svc = cast("Configurable", svc)
            self.wait_until(lambda: svc.value == value)
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

        with use_service(context, ref) as svc:
            svc = cast("Configurable", svc)
            self.wait_until(lambda: svc.deleted)
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

        with use_service(context, factory_ref) as svc:
            svc = cast("ConfigurableFactory", svc)
            self.wait_until(lambda: pid in svc.configurations)
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

    def test_other_files_are_ignored(self) -> None:
        """
        Files which are not configurations can live in the configuration folder
        """
        for name in ("README.md", "notes.txt", "spam.config.js.bak", "spam.config.json", ".config.js"):
            with self.subTest(name=name):
                self.assertIsNone(self.persistence._get_pid(name))

        self.assertEqual(self.persistence._get_pid("spam.config.js"), "spam")
        self.assertEqual(self.persistence._get_pid(os.path.join("any", "eggs.config.js")), "eggs")

        # Listing the configurations must not fail because of them
        self.persistence.store("spam", {"answer": 42})
        for name in ("README.md", "spam.config.js.bak"):
            with open(os.path.join(self.conf_folder, name), "w") as filep:
                filep.write("not a configuration\n")

        self.assertEqual(set(self.persistence.get_pids()), {"spam"})


class JsonPersistenceAtomicTest(unittest.TestCase):
    """
    The JSON persistence must never leave a partial configuration file
    """

    PID = "test.atomic"

    def setUp(self) -> None:
        """
        Prepares a persistence service with its own configuration folder
        """
        self.conf_folder = tempfile.mkdtemp(prefix="ipopo-configadmin-atomic-")
        self.persistence = JsonPersistence()
        self.persistence._conf_folder = self.conf_folder
        self.path = os.path.join(self.conf_folder, f"{self.PID}.config.js")

    def tearDown(self) -> None:
        """
        Cleans up the temporary folder
        """
        shutil.rmtree(self.conf_folder, ignore_errors=True)

    def test_store_replaces_file(self) -> None:
        """
        The stored file is valid JSON and no temporary file is left
        """
        self.persistence.store(self.PID, {"answer": 42})
        self.persistence.store(self.PID, {"answer": 21, "spam": "eggs"})

        with open(self.path) as filep:
            self.assertDictEqual(json.load(filep), {"answer": 21, "spam": "eggs"})

        self.assertEqual(os.listdir(self.conf_folder), [f"{self.PID}.config.js"])
        self.assertEqual(set(self.persistence.get_pids()), {self.PID})

    def test_store_keeps_permissions(self) -> None:
        """
        Replacing a configuration file keeps its permissions
        """
        self.persistence.store(self.PID, {"answer": 42})
        os.chmod(self.path, 0o600)

        self.persistence.store(self.PID, {"answer": 21})
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_write_error_keeps_previous_file(self) -> None:
        """
        An error while writing leaves the previous file untouched and removes
        the temporary one
        """
        self.persistence.store(self.PID, {"answer": 42})

        with (
            mock.patch("pelix.services.configadmin.os.fsync", side_effect=OSError("disk full")),
            self.assertRaises(OSError),
        ):
            self.persistence.store(self.PID, {"answer": 21})

        # Nothing that can't be serialized reaches the file either
        with self.assertRaises(TypeError):
            self.persistence.store(self.PID, {"answer": object()})

        self.assertDictEqual(self.persistence.load(self.PID), {"answer": 42})
        self.assertEqual(os.listdir(self.conf_folder), [f"{self.PID}.config.js"])


class _MutatingService(services.IManagedService):
    """
    Managed service which modifies the properties it is given
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.received: list[dict[str, Any] | None] = []

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        self.received.append(None if properties is None else properties.copy())
        if properties is not None:
            properties["mutated"] = True


class PropertiesCopyTest(unittest.TestCase):
    """
    Each managed service must get its own copy of the configuration properties
    """

    PID = "test.ca.copy"

    def setUp(self) -> None:
        """
        Starts a framework with ConfigurationAdmin
        """
        self.conf_folder = tempfile.mkdtemp(prefix="ipopo-configadmin-copy-")
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": self.conf_folder}
        )
        self.framework.start()
        self.context = self.framework.get_bundle_context()

    def tearDown(self) -> None:
        """
        Stops the framework
        """
        pelix.framework.FrameworkFactory.delete_framework()
        shutil.rmtree(self.conf_folder, ignore_errors=True)

    def test_services_get_copies(self) -> None:
        """
        A managed service modifying its properties must not alter those given
        to the others, nor the stored configuration
        """
        managed = [_MutatingService(), _MutatingService()]
        for svc in managed:
            self.context.register_service(services.IManagedService, svc, {constants.SERVICE_PID: self.PID})

        ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert ref is not None
        config = self.context.get_service(ref).get_configuration(self.PID)

        # Notified synchronously, one service after the other
        config.update({"answer": 42})
        for svc in managed:
            self.assertEqual(len(svc.received), 1)
            received = svc.received[0]
            assert received is not None
            self.assertEqual(received["answer"], 42)
            self.assertNotIn("mutated", received)

        properties = config.get_properties()
        assert properties is not None
        self.assertNotIn("mutated", properties)


class DirectoryConcurrencyTest(unittest.TestCase):
    """
    The configurations directory must support being listed while it is
    modified by another thread
    """

    def test_list_while_adding(self) -> None:
        """
        Listing the configurations while others are added must not fail
        """
        directory = ConfigurationDirectory()
        directory._admin = cast(services.IConfigurationAdmin, object())
        persistence = _MemoryPersistence()
        for idx in range(1000):
            directory.add(f"base.{idx}", None, persistence)

        def add_configurations() -> None:
            for idx in range(2000):
                directory.add(f"added.{idx}", None, persistence)
                directory.exists(f"added.{idx}")

        errors: list[Exception] = []
        nb_lists = 0

        # Switch threads as often as possible, to interleave the iterations
        # with the additions
        switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-5)
        try:
            adder = threading.Thread(target=add_configurations)
            adder.start()
            try:
                while adder.is_alive():
                    directory.list_configurations()
                    directory.list_configurations("(answer=42)")
                    nb_lists += 1
            except RuntimeError as ex:
                # "dictionary changed size during iteration"
                errors.append(ex)
            finally:
                adder.join()
        finally:
            sys.setswitchinterval(switch_interval)

        self.assertEqual(errors, [])
        self.assertGreater(nb_lists, 0)
        self.assertEqual(len(list(directory.list_configurations())), 3000)
        self.assertTrue(directory.exists("added.1999"))


class _SlowService(services.IManagedService):
    """
    Managed service taking some time to handle its configuration, recording
    the order of its notifications and how many ran at the same time
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.received: list[Any] = []
        self.max_concurrent = 0
        self.__concurrent = 0
        self.__lock = threading.Lock()
        self.done = threading.Event()
        self.expected = 0

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        with self.__lock:
            self.__concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.__concurrent)

        # Leave time for another delivery to start
        time.sleep(0.05)

        with self.__lock:
            self.__concurrent -= 1
            self.received.append(None if properties is None else properties.get("index"))
            if len(self.received) >= self.expected:
                self.done.set()


class DeliveryOrderTest(unittest.TestCase):
    """
    The asynchronous notifications to a managed service must be given one at a
    time, in the order they have been triggered
    """

    def setUp(self) -> None:
        """
        Starts a framework with ConfigurationAdmin
        """
        self.conf_folder = tempfile.mkdtemp(prefix="ipopo-configadmin-order-")
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": self.conf_folder}
        )
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert ref is not None
        self.config = self.context.get_service(ref)

    def tearDown(self) -> None:
        """
        Stops the framework
        """
        pelix.framework.FrameworkFactory.delete_framework()
        shutil.rmtree(self.conf_folder, ignore_errors=True)

    def test_ordered_delivery(self) -> None:
        """
        Successive notifications given by the pool must not overlap nor be
        reordered
        """
        nb_pids = 5
        for idx in range(nb_pids):
            self.config.get_configuration(f"test.ca.order.{idx}").update({"index": idx})

        # Each registration makes the pool deliver the configuration of its PID
        svc = _SlowService()
        svc.expected = nb_pids
        for idx in range(nb_pids):
            self.context.register_service(
                services.IManagedService, svc, {constants.SERVICE_PID: f"test.ca.order.{idx}"}
            )

        self.assertTrue(svc.done.wait(5), "Configurations not delivered")
        self.assertEqual(svc.max_concurrent, 1, "Concurrent notifications")
        self.assertEqual(svc.received, list(range(nb_pids)))


# ------------------------------------------------------------------------------


def _in_pool() -> bool:
    """
    Checks if the current thread is the one of the ConfigurationAdmin pool
    """
    name = threading.current_thread().name
    return name.startswith("ConfigAdmin") and name != "ConfigAdmin-stop"


class _RecordingService(services.IManagedService):
    """
    Managed service recording its notifications and how many ran at the same
    time. Its first notification from the pool can be held until released.
    """

    def __init__(self, hold_pool: bool = False) -> None:
        """
        :param hold_pool: If True, hold the first notification from the pool
        """
        self.received: list[Any] = []
        self.max_concurrent = 0
        self.__concurrent = 0
        self.__lock = threading.Lock()

        self.__hold_pool = hold_pool
        self.entered = threading.Event()
        self.release = threading.Event()

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        with self.__lock:
            self.__concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.__concurrent)
            hold = self.__hold_pool and _in_pool()
            if hold:
                self.__hold_pool = False

        if hold:
            self.entered.set()
            self.release.wait(5)

        with self.__lock:
            self.__concurrent -= 1
            self.received.append(None if properties is None else properties.get("index"))


class _RecordingFactory(services.IManagedServiceFactory):
    """
    Managed service factory recording the last properties given for each PID
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.configurations: dict[str, Any] = {}

    def updated(self, pid: str, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        self.configurations[pid] = None if properties is None else properties.get("index")

    def deleted(self, pid: str) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        self.configurations.pop(pid, None)


class _LockingService(_RecordingService):
    """
    Managed service needing a lock to handle the first notification given by
    the pool, once allowed to go on
    """

    def __init__(self, lock: Any, go: threading.Event) -> None:
        """
        :param lock: Lock needed to handle the first pool notification
        :param go: Event to wait for before taking the lock
        """
        super().__init__()
        self.__lock = lock
        self.__go = go
        self.__first = True
        self.lock_timeout = False

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        if self.__first and _in_pool():
            self.__first = False
            self.entered.set()
            self.__go.wait(5)

            # Short timeout: a deadlock is the failure being tested
            if not self.__lock.acquire(timeout=2):
                self.lock_timeout = True
            else:
                self.__lock.release()

        super().updated(properties)


class _SelfUpdatingService(services.IManagedService):
    """
    Managed service updating its own configuration when given the first one
    """

    def __init__(self, configuration: services.Configuration) -> None:
        """
        :param configuration: The configuration of this service
        """
        self.__configuration = configuration
        self.__depth = 0
        self.max_depth = 0
        self.received: list[Any] = []

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        self.__depth += 1
        self.max_depth = max(self.max_depth, self.__depth)
        try:
            index = None if properties is None else properties.get("index")
            self.received.append(index)
            if index == 0:
                self.__configuration.update({"index": 1})
        finally:
            self.__depth -= 1


class PoolDeliveryRaceTest(unittest.TestCase):
    """
    The configuration given by the pool when a managed service is bound must not
    race with the one given by the thread updating or deleting it
    """

    PID = "test.ca.race"
    FACTORY_PID = "test.ca.race.factory"

    def setUp(self) -> None:
        """
        Starts a framework with ConfigurationAdmin
        """
        self.conf_folder = tempfile.mkdtemp(prefix="ipopo-configadmin-race-")
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": self.conf_folder}
        )
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert ref is not None
        self.config = self.context.get_service(ref)

        # Let the pool go through the start up notifications
        self.wait_pool()

    def tearDown(self) -> None:
        """
        Stops the framework
        """
        pelix.framework.FrameworkFactory.delete_framework()
        shutil.rmtree(self.conf_folder, ignore_errors=True)

    def wait_pool(self) -> None:
        """
        Waits for the pool to execute the tasks given so far
        """
        pool = cast(ConfigurationAdmin, self.config)._pool
        assert pool is not None
        # The pool has a single thread: the previous tasks are done once this
        # one is
        pool.enqueue(lambda: None).result(5)

    def hold_pool_read(
        self, configuration: services.Configuration
    ) -> tuple[threading.Event, threading.Event]:
        """
        Makes the pool wait, once, between reading the properties of a
        configuration and giving them to a service

        :param configuration: A configuration of the current framework
        :return: The "read" and "release" events
        """
        read = threading.Event()
        release = threading.Event()

        # Patch the class of the running bundle: the module is imported again
        # each time a framework installs it
        conf_class = type(configuration)
        original = conf_class.get_properties

        def get_properties(conf: Configuration) -> dict[str, Any] | None:
            properties = original(conf)
            if _in_pool() and not read.is_set():
                read.set()
                release.wait(5)
            return properties

        patcher = mock.patch.object(conf_class, "get_properties", get_properties)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(release.set)
        return read, release

    def run_while_held(self, release: threading.Event, method: Any, *args: Any) -> None:
        """
        Calls a method from another thread while the pool is held, then
        releases the pool and waits for both to finish

        :param release: Event releasing the pool
        :param method: Method to call
        :param args: Method arguments
        """
        caller = threading.Thread(target=method, args=args, daemon=True)
        caller.start()

        # Let the caller notify the service, or wait for the pool to do it
        caller.join(0.2)
        release.set()
        caller.join(5)
        self.assertFalse(caller.is_alive(), "Caller blocked")
        self.wait_pool()

    def test_no_stale_delivery_after_update(self) -> None:
        """
        A managed service must end up with the latest properties when its
        configuration is updated while the pool notifies it of its binding
        """
        configuration = self.config.get_configuration(self.PID)
        configuration.update({"index": 0})

        read, release = self.hold_pool_read(configuration)
        svc = _RecordingService()
        self.context.register_service(services.IManagedService, svc, {constants.SERVICE_PID: self.PID})
        self.assertTrue(read.wait(5), "Pool didn't look for the configuration")

        self.run_while_held(release, configuration.update, {"index": 1})

        self.assertEqual(svc.received[-1], 1, f"Stale configuration given last: {svc.received}")

    def test_no_stale_delivery_after_delete(self) -> None:
        """
        A managed service must end up without configuration when it is deleted
        while the pool notifies it of its binding
        """
        configuration = self.config.get_configuration(self.PID)
        configuration.update({"index": 0})

        read, release = self.hold_pool_read(configuration)
        svc = _RecordingService()
        self.context.register_service(services.IManagedService, svc, {constants.SERVICE_PID: self.PID})
        self.assertTrue(read.wait(5), "Pool didn't look for the configuration")

        self.run_while_held(release, configuration.delete)

        self.assertIsNone(svc.received[-1], f"Deleted configuration given last: {svc.received}")

    def test_factory_no_stale_delivery_after_update(self) -> None:
        """
        A managed service factory must end up with the latest properties when a
        configuration is updated while the pool notifies it of its binding
        """
        configuration = self.config.create_factory_configuration(self.FACTORY_PID)
        configuration.update({"index": 0})
        pid = configuration.get_pid()

        read, release = self.hold_pool_read(configuration)
        factory = _RecordingFactory()
        self.context.register_service(
            services.IManagedServiceFactory, factory, {constants.SERVICE_PID: self.FACTORY_PID}
        )
        self.assertTrue(read.wait(5), "Pool didn't look for the configurations")

        self.run_while_held(release, configuration.update, {"index": 1})

        self.assertEqual(factory.configurations.get(pid), 1, "Stale configuration given last")

    def test_no_concurrent_notifications(self) -> None:
        """
        A managed service must not be notified by the updating thread while the
        pool is notifying it
        """
        configuration = self.config.get_configuration(self.PID)
        configuration.update({"index": 0})

        svc = _RecordingService(hold_pool=True)
        self.addCleanup(svc.release.set)
        self.context.register_service(services.IManagedService, svc, {constants.SERVICE_PID: self.PID})
        self.assertTrue(svc.entered.wait(5), "Pool didn't notify the service")

        # Update from another thread: it could wait for the pool notification
        updater = threading.Thread(target=configuration.update, args=({"index": 1},), daemon=True)
        updater.start()
        updater.join(0.5)

        svc.release.set()
        updater.join(5)
        self.assertFalse(updater.is_alive(), "Update blocked")
        self.wait_pool()

        self.assertEqual(svc.max_concurrent, 1, "Concurrent notifications")
        self.assertEqual(svc.received[-1], 1, f"Stale configuration given last: {svc.received}")

    def test_reentrant_update(self) -> None:
        """
        A managed service updating its own configuration from updated() must
        be given the new properties once that call is over, not in a nested
        one
        """
        configuration = self.config.get_configuration(self.PID)
        svc = _SelfUpdatingService(configuration)
        self.context.register_service(services.IManagedService, svc, {constants.SERVICE_PID: self.PID})

        configuration.update({"index": 0})
        self.wait_pool()

        self.assertEqual(svc.received, [0, 1])
        self.assertEqual(svc.max_depth, 1, "Nested notification")

    def test_no_deadlock_with_caller_lock(self) -> None:
        """
        Updating a configuration while holding a lock that the service needs
        to handle the notification given by the pool must not deadlock, e.g. a
        component updating a configuration in its validation callback, called
        while iPOPO holds its instances lock
        """
        configuration = self.config.get_configuration(self.PID)
        configuration.update({"index": 0})

        shared_lock = threading.Lock()
        go = threading.Event()
        self.addCleanup(go.set)
        svc = _LockingService(shared_lock, go)
        self.context.register_service(services.IManagedService, svc, {constants.SERVICE_PID: self.PID})
        self.assertTrue(svc.entered.wait(5), "Pool didn't notify the service")

        def update_holding_lock() -> None:
            with shared_lock:
                # The pool now waits for the lock this thread holds
                go.set()
                configuration.update({"index": 1})

        updater = threading.Thread(target=update_holding_lock, daemon=True)
        updater.start()
        updater.join(5)
        self.assertFalse(updater.is_alive(), "update() blocked")
        self.wait_pool()

        self.assertFalse(svc.lock_timeout, "Service couldn't get the lock: deadlock")
        self.assertEqual(svc.max_concurrent, 1, "Concurrent notifications")
        self.assertEqual(svc.received[-1], 1, f"Stale configuration given last: {svc.received}")


# ------------------------------------------------------------------------------


class _EventRecorder(services.IConfigurationListener):
    """
    Configuration listener recording the events
    """

    def __init__(self) -> None:
        self.events: list[tuple[int, str, str | None]] = []

    def configuration_event(self, event: services.ConfigurationEvent) -> None:
        self.events.append((event.type, event.pid, event.factory_pid))


class _FailingListener(services.IConfigurationListener):
    """
    Configuration listener raising an error
    """

    def configuration_event(self, event: services.ConfigurationEvent) -> None:
        raise RuntimeError("Listener error")


class _OrderedFactory(_RecordingFactory):
    """
    Managed service factory writing in a shared journal
    """

    def __init__(self, name: str, journal: list[str]) -> None:
        super().__init__()
        self.__name = name
        self.__journal = journal
        self.deleted_pids: list[str] = []

    def updated(self, pid: str, properties: dict[str, Any] | None) -> None:
        super().updated(pid, properties)
        self.__journal.append(self.__name)

    def deleted(self, pid: str) -> None:
        super().deleted(pid)
        self.deleted_pids.append(pid)


class FactoryConfigurationTest(unittest.TestCase):
    """
    Factory configurations: names, change count, events, persistence and
    notifications of the managed service factories
    """

    FACTORY_PID = "test.ca.factory"

    def setUp(self) -> None:
        self.conf_folder = tempfile.mkdtemp(prefix="ipopo-configadmin-factory-")
        self.addCleanup(shutil.rmtree, self.conf_folder, ignore_errors=True)
        self.start_framework()

    def start_framework(self) -> None:
        """
        Starts a framework with ConfigurationAdmin on the test folder
        """
        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.services.configadmin"), {"configuration.folder": self.conf_folder}
        )
        self.framework.start()
        self.context = self.framework.get_bundle_context()
        ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert ref is not None
        self.config = self.context.get_service(ref)
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)
        self.wait_pool()

    def stop_framework(self) -> None:
        """
        Stops the framework, keeping the configuration folder
        """
        pelix.framework.FrameworkFactory.delete_framework()

    def wait_pool(self) -> None:
        """
        Waits for the pool to execute the tasks given so far
        """
        pool = cast(ConfigurationAdmin, self.config)._pool
        assert pool is not None
        pool.enqueue(lambda: None).result(5)

    def register_factory(
        self, factory: services.IManagedServiceFactory, ranking: int = 0
    ) -> ServiceRegistration[Any]:
        """
        Registers a managed service factory for the test factory PID
        """
        registration = self.context.register_service(
            services.IManagedServiceFactory,
            factory,
            {constants.SERVICE_PID: self.FACTORY_PID, constants.SERVICE_RANKING: ranking},
        )
        self.wait_pool()
        return registration

    def test_factory_configuration_name(self) -> None:
        """
        The PID of a named factory configuration is "<factory>~<name>", and
        getting it again gives the same configuration
        """
        config = self.config.get_factory_configuration(self.FACTORY_PID, "first")
        self.assertEqual(config.get_pid(), f"{self.FACTORY_PID}~first")
        self.assertEqual(config.get_factory_pid(), self.FACTORY_PID)
        self.assertIsNone(config.get_properties())
        self.assertIs(self.config.get_factory_configuration(self.FACTORY_PID, "first"), config)

        config.update({"a": 1})
        self.assertEqual(
            list(self.config.list_configurations(f"(service.factoryPid={self.FACTORY_PID})")), [config]
        )

        # The factory PID is not the one of a managed service configuration
        self.config.get_configuration("test.ca.managed~x").update({"a": 1})
        for factory_pid, name in (
            ("test.ca.managed", "x"),
            ("", "x"),
            (None, "x"),
            (self.FACTORY_PID, ""),
            (self.FACTORY_PID, "  "),
            (self.FACTORY_PID, None),
        ):
            with self.subTest(factory_pid=factory_pid, name=name), self.assertRaises(ValueError):
                self.config.get_factory_configuration(factory_pid, name)

    def test_factory_configuration_restart(self) -> None:
        """
        Factory configurations are stored and reloaded, with their factory
        PID, and given to the factory registered after the restart
        """
        for name, value in (("a", 1), ("b", 2)):
            self.config.get_factory_configuration(self.FACTORY_PID, name).update({"index": value})
        self.config.create_factory_configuration(self.FACTORY_PID).update({"index": 3})

        self.stop_framework()
        self.start_framework()
        factory = _RecordingFactory()
        self.register_factory(factory)

        self.assertEqual(factory.configurations[f"{self.FACTORY_PID}~a"], 1)
        self.assertEqual(factory.configurations[f"{self.FACTORY_PID}~b"], 2)
        self.assertEqual(sorted(factory.configurations.values()), [1, 2, 3])

        # The reloaded configuration is the same as the named one
        config = self.config.get_factory_configuration(self.FACTORY_PID, "a")
        self.assertEqual(config.get_factory_pid(), self.FACTORY_PID)
        self.assertIsNotNone(config.get_properties())

    def test_change_count(self) -> None:
        """
        The change count grows with each change only
        """
        config = self.config.get_configuration("test.ca.count")
        self.assertEqual(config.get_change_count(), 0)

        for properties, expected_changed, expected_count in (
            ({"a": 1}, True, 1),
            ({"a": 1}, False, 1),
            ({"a": 2}, True, 2),
            ({}, False, 2),
        ):
            with self.subTest(properties=properties):
                self.assertEqual(config.update_if_different(properties), expected_changed)
                self.assertEqual(config.get_change_count(), expected_count)

        config.set_bundle_location("here")
        self.assertEqual(config.get_change_count(), 3)
        config.set_bundle_location("here")
        self.assertEqual(config.get_change_count(), 3)

    def test_events(self) -> None:
        """
        The listeners get the update, deletion and location events, once the
        change is stored; a failing listener doesn't prevent the others
        """
        recorder = _EventRecorder()
        self.context.register_service(services.IConfigurationListener, _FailingListener(), {})
        self.context.register_service(services.IConfigurationListener, recorder, {})

        managed = self.config.get_configuration("test.ca.event")
        factory = self.config.get_factory_configuration(self.FACTORY_PID, "e")
        managed.update({"a": 1})
        managed.update({"a": 1})
        factory.update({"a": 1})
        managed.set_bundle_location("somewhere")
        factory_pid = factory.get_pid()
        factory.delete()
        managed.delete()

        self.assertEqual(
            recorder.events,
            [
                (services.CM_UPDATED, "test.ca.event", None),
                (services.CM_UPDATED, factory_pid, self.FACTORY_PID),
                (services.CM_LOCATION_CHANGED, "test.ca.event", None),
                (services.CM_DELETED, factory_pid, self.FACTORY_PID),
                (services.CM_DELETED, "test.ca.event", None),
            ],
        )

    def test_location_persisted(self) -> None:
        """
        The bundle location is stored with the configuration and reloaded,
        but can't be set with the properties
        """
        config = self.config.get_configuration("test.ca.location")
        config.update({"a": 1, services.CONFIG_PROP_BUNDLE_LOCATION: "forged"})
        self.assertIsNone(config.get_bundle_location())

        config.set_bundle_location("here")
        with open(os.path.join(self.conf_folder, "test.ca.location.config.js")) as filep:
            self.assertEqual(json.load(filep)[services.CONFIG_PROP_BUNDLE_LOCATION], "here")

        self.stop_framework()
        self.start_framework()
        config = self.config.get_configuration("test.ca.location")
        self.assertEqual(config.get_bundle_location(), "here")
        self.assertEqual(config.get_properties(), {"a": 1, services.CONFIG_PROP_PID: "test.ca.location"})

    def test_factory_notifications(self) -> None:
        """
        A factory gets the new and updated configurations, the deletions of the
        ones it knew, and everything again when it comes back
        """
        pre = self.config.get_factory_configuration(self.FACTORY_PID, "pre")
        pre.update({"index": 1})
        never_given = self.config.get_factory_configuration(self.FACTORY_PID, "empty")

        factory = _OrderedFactory("f", [])
        registration = self.register_factory(factory)
        self.assertEqual(factory.configurations, {pre.get_pid(): 1})

        pre.update({"index": 2})
        late = self.config.get_factory_configuration(self.FACTORY_PID, "late")
        late.update({"index": 3})
        self.assertEqual(factory.configurations, {pre.get_pid(): 2, late.get_pid(): 3})

        # Nothing is given to the factory for a configuration it never got
        never_given.delete()
        self.assertEqual(factory.deleted_pids, [])
        late_pid = late.get_pid()
        late.delete()
        self.assertEqual(factory.deleted_pids, [late_pid])

        # Recreating a deleted name gives a new configuration
        again = self.config.get_factory_configuration(self.FACTORY_PID, "late")
        self.assertIsNot(again, late)
        again.update({"index": 4})
        self.assertEqual(factory.configurations[late_pid], 4)

        # The factory goes away and comes back
        registration.unregister()
        self.wait_pool()
        factory = _OrderedFactory("f", [])
        self.register_factory(factory)
        self.assertEqual(factory.configurations, {pre.get_pid(): 2, late_pid: 4})

    def test_factories_ranking(self) -> None:
        """
        Factories with the same PID are notified by decreasing ranking
        """
        journal: list[str] = []
        self.register_factory(_OrderedFactory("low", journal), 1)
        self.register_factory(_OrderedFactory("high", journal), 10)
        self.register_factory(_OrderedFactory("mid", journal), 5)

        self.config.get_factory_configuration(self.FACTORY_PID, "r").update({"index": 1})
        self.assertEqual(journal, ["high", "mid", "low"])


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
