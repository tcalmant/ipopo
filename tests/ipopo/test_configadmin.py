#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the bridge between ConfigurationAdmin and iPOPO

:author: Thomas Calmant
"""

import json
import os
import shutil
import threading
import time
import unittest
from typing import Any

import pelix.framework
from pelix import services
from pelix.constants import SERVICE_PID
from pelix.ipopo.constants import (
    IPOPO_CONFIG_FACTORY_NAME,
    IPOPO_CONFIG_UPDATE_POLICY,
    IPOPO_CONFIGADMIN_FACTORY_PID,
    IPOPO_INSTANCE_NAME,
    UPDATE_POLICY_RESTART,
    IPopoService,
    IPopoWaitingList,
    use_ipopo,
)
from tests.ipopo.configadmin_bundle import (
    FACTORY_BASIC,
    PID_GATED,
    PID_HIDDEN,
    PID_INSTANCE,
    PID_OPTIONAL,
    PID_OWN,
    PID_RESTART,
    PID_UNDECLARED,
    SPEC_BASIC,
    SPEC_UNDECLARED_PID,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Folder of the configurations of the tests
conf_folder = os.path.join(os.path.dirname(__file__), "conf")

# Bundles required to run the bridge
BRIDGE_BUNDLES = (
    "pelix.ipopo.core",
    "pelix.ipopo.waiting",
    "pelix.ipopo.handlers.configadmin",
    "pelix.services.configadmin",
    "pelix.ipopo.configadmin",
)

# ------------------------------------------------------------------------------


class ConfigAdminBridgeTest(unittest.TestCase):
    """
    Tests the components managed by ConfigurationAdmin
    """

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Removes the configuration folder created by the tests
        """
        shutil.rmtree(conf_folder, ignore_errors=True)

    def setUp(self) -> None:
        """
        Starts a framework with the ConfigurationAdmin bridge
        """
        # Each test starts with an empty set of configurations
        shutil.rmtree(conf_folder, ignore_errors=True)
        self.start_framework()

    def tearDown(self) -> None:
        """
        Cleans up the framework and the stored configurations
        """
        self.stop_framework()
        shutil.rmtree(conf_folder, ignore_errors=True)

    def start_framework(self) -> None:
        """
        Starts a framework, keeping the configurations already stored
        """
        self.framework = pelix.framework.create_framework(
            BRIDGE_BUNDLES, {"configuration.folder": conf_folder}
        )
        self.addCleanup(self.framework.delete, True)
        self.framework.start()

        self.context = self.framework.get_bundle_context()
        config_ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert config_ref is not None
        self.config_ref = config_ref
        self.config = self.context.get_service(config_ref)

    def stop_framework(self) -> None:
        """
        Stops the framework, keeping the stored configurations
        """
        self.context.unget_service(self.config_ref)
        pelix.framework.FrameworkFactory.delete_framework()

    @staticmethod
    def pause() -> None:
        """
        Small pause to let the task pool notify the services
        """
        time.sleep(0.2)

    def install_test_bundle(self) -> pelix.framework.Bundle:
        """
        Installs and starts the bundle defining the test components
        """
        bundle = self.context.install_bundle("tests.ipopo.configadmin_bundle")
        bundle.start()
        return bundle

    def get_ipopo(self) -> IPopoService:
        """
        Returns the iPOPO service
        """
        ref = self.context.get_service_reference(IPopoService)
        assert ref is not None
        return self.context.get_service(ref)

    def get_instance(self, name: str) -> Any:
        """
        Returns the component instance with the given name
        """
        with use_ipopo(self.context) as ipopo:
            return ipopo.get_instance(name)

    def get_property(self, name: str, key: str) -> Any:
        """
        Returns a property of the component with the given name
        """
        with use_ipopo(self.context) as ipopo:
            return ipopo.get_instance_details(name)["properties"].get(key)

    def is_running(self, name: str) -> bool:
        """
        Checks if a component with the given name is instantiated
        """
        with use_ipopo(self.context) as ipopo:
            return ipopo.is_registered_instance(name)

    def make_component(self, instance_name: str, **properties: Any) -> services.Configuration:
        """
        Creates a factory configuration describing a component of the "basic"
        test factory

        :param instance_name: Name of the component instance
        :param properties: Additional component properties
        :return: The new configuration
        """
        config = self.config.create_factory_configuration(IPOPO_CONFIGADMIN_FACTORY_PID)
        config.update(
            {
                IPOPO_CONFIG_FACTORY_NAME: FACTORY_BASIC,
                IPOPO_INSTANCE_NAME: instance_name,
                **properties,
            }
        )
        self.pause()
        return config

    def testCreateDelete(self) -> None:
        """
        A factory configuration must create a component, its deletion must kill it
        """
        self.install_test_bundle()
        self.assertFalse(self.is_running("test-1"))

        config = self.make_component("test-1", name="hello")
        self.assertTrue(self.is_running("test-1"))
        self.assertEqual(self.get_property("test-1", "name"), "hello")
        self.assertEqual(self.get_instance("test-1").validated, 1)

        # The component provides its service
        self.assertIsNotNone(self.context.get_service_reference(SPEC_BASIC))

        config.delete()
        self.pause()
        self.assertFalse(self.is_running("test-1"))
        self.assertIsNone(self.context.get_service_reference(SPEC_BASIC))

    def testDefaultInstanceName(self) -> None:
        """
        Without an instance name, the component is named after the configuration PID
        """
        self.install_test_bundle()

        config = self.config.create_factory_configuration(IPOPO_CONFIGADMIN_FACTORY_PID)
        config.update({IPOPO_CONFIG_FACTORY_NAME: FACTORY_BASIC})
        self.pause()

        self.assertTrue(self.is_running(config.get_pid()))

    def testMissingFactoryName(self) -> None:
        """
        A configuration without the name of a factory must be ignored
        """
        self.install_test_bundle()

        config = self.config.create_factory_configuration(IPOPO_CONFIGADMIN_FACTORY_PID)
        config.update({IPOPO_INSTANCE_NAME: "test-no-factory", "name": "hello"})
        self.pause()

        self.assertFalse(self.is_running("test-no-factory"))

    def testFactoryNameRemoved(self) -> None:
        """
        An update dropping the name of the factory must kill the component
        """
        self.install_test_bundle()
        config = self.make_component("test-lost-factory", name="hello")
        self.assertTrue(self.is_running("test-lost-factory"))

        # An update replaces the whole set of properties: the caller can forget
        # to give the name of the factory back
        config.update({IPOPO_INSTANCE_NAME: "test-lost-factory", "name": "world"})
        self.pause()

        self.assertFalse(self.is_running("test-lost-factory"))

    def testUpdateInPlace(self) -> None:
        """
        An update must reconfigure the component without restarting it
        """
        self.install_test_bundle()
        config = self.make_component("test-2", name="hello")

        instance = self.get_instance("test-2")
        self.assertEqual(instance.validated, 1)

        properties = config.get_properties()
        assert properties is not None
        properties["name"] = "world"
        config.update(properties)
        self.pause()

        # Same instance, updated property
        self.assertIs(self.get_instance("test-2"), instance)
        self.assertEqual(instance.validated, 1)
        self.assertEqual(instance._name, "world")
        self.assertEqual(self.get_property("test-2", "name"), "world")

        # The property of the provided service follows
        svc_ref = self.context.get_service_reference(SPEC_BASIC, "(instance.name=test-2)")
        assert svc_ref is not None
        self.assertEqual(svc_ref.get_property("name"), "world")

    def testUpdateRestartPolicy(self) -> None:
        """
        With the "restart" policy, the component must be killed and created again
        """
        self.install_test_bundle()
        config = self.make_component(
            "test-3", name="hello", **{IPOPO_CONFIG_UPDATE_POLICY: UPDATE_POLICY_RESTART}
        )

        instance = self.get_instance("test-3")

        # The directives of the bridge are not component properties
        self.assertIsNone(self.get_property("test-3", IPOPO_CONFIG_UPDATE_POLICY))
        self.assertIsNone(self.get_property("test-3", IPOPO_CONFIG_FACTORY_NAME))

        properties = config.get_properties()
        assert properties is not None
        properties["name"] = "world"
        config.update(properties)
        self.pause()

        new_instance = self.get_instance("test-3")
        self.assertIsNot(new_instance, instance)
        self.assertEqual(instance.invalidated, 1)
        self.assertEqual(new_instance.validated, 1)
        self.assertEqual(new_instance._name, "world")

    def testUpdateRenameInstance(self) -> None:
        """
        Changing the name of the instance must kill the old component
        """
        self.install_test_bundle()
        config = self.make_component("test-4", name="hello")

        properties = config.get_properties()
        assert properties is not None
        properties[IPOPO_INSTANCE_NAME] = "test-4-bis"
        config.update(properties)
        self.pause()

        self.assertFalse(self.is_running("test-4"))
        self.assertTrue(self.is_running("test-4-bis"))

    def testRemovedPropertyGoesBackToDefault(self) -> None:
        """
        A property removed from the configuration must go back to its declared value
        """
        self.install_test_bundle()
        config = self.make_component("test-5", name="hello")
        self.assertEqual(self.get_property("test-5", "name"), "hello")

        properties = config.get_properties()
        assert properties is not None
        del properties["name"]
        config.update(properties)
        self.pause()

        self.assertEqual(self.get_property("test-5", "name"), "default")

    def testRemovedPropertyWithoutFactory(self) -> None:
        """
        A property removed while the factory is absent must go back to its
        declared value, not to None
        """
        bundle = self.install_test_bundle()
        config = self.make_component("test-5b", name="hello")
        self.assertEqual(self.get_property("test-5b", "name"), "hello")

        # The component is killed but stays in the waiting list
        bundle.stop()
        self.assertFalse(self.is_running("test-5b"))

        properties = config.get_properties()
        assert properties is not None
        del properties["name"]
        config.update(properties)
        self.pause()

        # The factory declares the value again when it comes back
        bundle.start()
        self.assertTrue(self.is_running("test-5b"))
        self.assertEqual(self.get_property("test-5b", "name"), "default")

    def testForgottenComponentIsCreatedAgain(self) -> None:
        """
        A component removed from the waiting list behind the back of the bridge
        must be created again by the next update of its configuration
        """
        self.install_test_bundle()
        config = self.make_component("test-5c", name="hello")
        self.assertTrue(self.is_running("test-5c"))

        # Remove the component from the waiting list, which kills it
        ref = self.context.get_service_reference(IPopoWaitingList)
        assert ref is not None
        self.context.get_service(ref).remove("test-5c")
        self.assertFalse(self.is_running("test-5c"))

        properties = config.get_properties()
        assert properties is not None
        properties["name"] = "world"
        config.update(properties)
        self.pause()

        self.assertTrue(self.is_running("test-5c"))
        self.assertEqual(self.get_property("test-5c", "name"), "world")

    def testDuplicateInstanceName(self) -> None:
        """
        A configuration naming an instance which already exists must be
        rejected, and must not touch the component of the other configuration
        """
        self.install_test_bundle()
        first = self.make_component("test-dup", name="from-first")
        second = self.make_component("test-dup", name="from-second")

        # The second configuration didn't create anything
        self.assertTrue(self.is_running("test-dup"))
        self.assertEqual(self.get_property("test-dup", "name"), "from-first")

        # Updating it must not reconfigure the component of the first one
        properties = second.get_properties()
        assert properties is not None
        properties["name"] = "from-second-updated"
        second.update(properties)
        self.pause()

        self.assertEqual(self.get_property("test-dup", "name"), "from-first")

        # Deleting it must not kill the component of the first one
        second.delete()
        self.pause()

        self.assertTrue(self.is_running("test-dup"))
        self.assertEqual(self.get_property("test-dup", "name"), "from-first")

        # The first configuration still drives its component
        properties = first.get_properties()
        assert properties is not None
        properties["name"] = "from-first-updated"
        first.update(properties)
        self.pause()

        self.assertEqual(self.get_property("test-dup", "name"), "from-first-updated")

        first.delete()
        self.pause()
        self.assertFalse(self.is_running("test-dup"))

    def testConcurrentUpdates(self) -> None:
        """
        Two updates of the same configuration must not make the bridge lose
        the ownership of the component it created
        """
        self.install_test_bundle()
        instantiator = self.get_instance("ipopo-configadmin-instantiator")

        # Deschedule the first instantiation, to force the interleaving of two
        # updates of the same configuration: ConfigurationAdmin notifies from
        # a pool of threads
        original = instantiator._ConfigAdminInstantiator__add
        calls = []

        def slow_add(config: Any) -> bool:
            calls.append(config.name)
            if len(calls) == 1:
                time.sleep(1)
            return original(config)

        instantiator._ConfigAdminInstantiator__add = slow_add

        config = self.config.create_factory_configuration(IPOPO_CONFIGADMIN_FACTORY_PID)
        description = {IPOPO_CONFIG_FACTORY_NAME: FACTORY_BASIC, IPOPO_INSTANCE_NAME: "test-raced"}
        threads = [
            threading.Thread(
                target=instantiator.updated, args=(config.get_pid(), {**description, "name": name})
            )
            for name in ("one", "two")
        ]

        threads[0].start()
        time.sleep(0.3)
        threads[1].start()
        for thread in threads:
            thread.join()

        self.assertTrue(self.is_running("test-raced"))

        # The last update wins: the first one must not be applied afterwards
        self.assertEqual(self.get_property("test-raced", "name"), "two")

        # The bridge still owns the component: the deletion of the
        # configuration must kill it
        instantiator.deleted(config.get_pid())
        self.assertFalse(self.is_running("test-raced"), "The component is not managed anymore")

    def testFactoryComesLater(self) -> None:
        """
        A configuration naming an unknown factory must wait for it
        """
        config = self.make_component("test-6", name="hello")
        self.assertFalse(self.is_running("test-6"))

        bundle = self.install_test_bundle()
        self.assertTrue(self.is_running("test-6"))
        self.assertEqual(self.get_property("test-6", "name"), "hello")

        # Stopping the bundle kills the component, restarting it creates it again
        bundle.stop()
        self.assertFalse(self.is_running("test-6"))

        bundle.start()
        self.assertTrue(self.is_running("test-6"))

        config.delete()
        self.pause()
        self.assertFalse(self.is_running("test-6"))

    def testStopBridgeKillsComponents(self) -> None:
        """
        Stopping the bridge must kill the components it created
        """
        self.install_test_bundle()
        self.make_component("test-7", name="hello")
        self.assertTrue(self.is_running("test-7"))

        for bundle in self.context.get_bundles():
            if bundle.get_symbolic_name() == "pelix.ipopo.configadmin":
                bundle.stop()
                break
        else:
            self.fail("Bridge bundle not found")

        self.assertFalse(self.is_running("test-7"))

    def testPersistence(self) -> None:
        """
        A configuration stored on disk must create its component at the next start
        """
        self.install_test_bundle()
        config = self.make_component("test-8", name="stored")
        pid = config.get_pid()

        # Restart the framework, keeping the configuration folder
        self.stop_framework()
        self.start_framework()
        self.install_test_bundle()
        self.pause()

        self.assertTrue(self.is_running("test-8"))
        self.assertEqual(self.get_property("test-8", "name"), "stored")
        self.assertEqual(self.config.get_configuration(pid).get_pid(), pid)


# ------------------------------------------------------------------------------


class ConfigAdminBridgeStartupTest(unittest.TestCase):
    """
    Tests the start of the bridge when ConfigurationAdmin notifies it while
    iPOPO is busy instantiating components
    """

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Removes the configuration folder created by the tests
        """
        shutil.rmtree(conf_folder, ignore_errors=True)

    def setUp(self) -> None:
        """
        Stores a configuration describing a component
        """
        shutil.rmtree(conf_folder, ignore_errors=True)
        os.makedirs(conf_folder)

        with open(os.path.join(conf_folder, "test-startup.config.js"), "w") as filep:
            json.dump(
                {
                    services.CONFIG_PROP_PID: "test-startup",
                    services.CONFIG_PROP_FACTORY_PID: IPOPO_CONFIGADMIN_FACTORY_PID,
                    IPOPO_CONFIG_FACTORY_NAME: FACTORY_BASIC,
                    IPOPO_INSTANCE_NAME: "test-startup",
                },
                filep,
            )

    def tearDown(self) -> None:
        """
        Cleans up the stored configurations
        """
        shutil.rmtree(conf_folder, ignore_errors=True)

    def testConfigAdminStartedLast(self) -> None:
        """
        A stored configuration is given to the bridge while iPOPO is
        instantiating ConfigurationAdmin: the start must not be blocked
        """
        # ConfigurationAdmin is started after the bridge: it notifies it from
        # inside the instantiation of its own components
        framework = pelix.framework.create_framework(
            (
                "pelix.ipopo.core",
                "pelix.ipopo.waiting",
                "pelix.ipopo.handlers.configadmin",
                "pelix.ipopo.configadmin",
                "tests.ipopo.configadmin_bundle",
                "pelix.services.configadmin",
            ),
            {"configuration.folder": conf_folder},
        )

        # Start in another thread: a blocked start would else freeze the tests
        starter = threading.Thread(target=framework.start, daemon=True)
        starter.start()
        starter.join(30)
        if starter.is_alive():
            self.fail("The framework start is blocked")

        # The framework is running: it can be deleted safely
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)

        with use_ipopo(framework.get_bundle_context()) as ipopo:
            self.assertTrue(ipopo.is_registered_instance("test-startup"))


# ------------------------------------------------------------------------------


class ConfiguredInstanceTest(unittest.TestCase):
    """
    Tests the configuration of components which are not created by
    ConfigurationAdmin
    """

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Removes the configuration folder created by the tests
        """
        shutil.rmtree(conf_folder, ignore_errors=True)

    def setUp(self) -> None:
        """
        Starts a framework with the ConfigurationAdmin bridge
        """
        # Each test starts with an empty set of configurations
        shutil.rmtree(conf_folder, ignore_errors=True)

        self.framework = pelix.framework.create_framework(
            BRIDGE_BUNDLES, {"configuration.folder": conf_folder}
        )
        self.addCleanup(self.framework.delete, True)
        self.framework.start()

        self.context = self.framework.get_bundle_context()
        config_ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert config_ref is not None
        self.config_ref = config_ref
        self.config = self.context.get_service(config_ref)

        self.bundle = self.context.install_bundle("tests.ipopo.configadmin_bundle")
        self.bundle.start()

    def tearDown(self) -> None:
        """
        Cleans up the framework and the stored configurations
        """
        self.context.unget_service(self.config_ref)
        pelix.framework.FrameworkFactory.delete_framework()
        shutil.rmtree(conf_folder, ignore_errors=True)

    @staticmethod
    def pause() -> None:
        """
        Small pause to let the task pool notify the services
        """
        time.sleep(0.2)

    def get_instance(self, name: str) -> Any:
        """
        Returns the component instance with the given name
        """
        with use_ipopo(self.context) as ipopo:
            return ipopo.get_instance(name)

    def get_state(self, name: str) -> int:
        """
        Returns the state of the component with the given name
        """
        with use_ipopo(self.context) as ipopo:
            return ipopo.get_instance_details(name)["state"]

    def testComponentWithPid(self) -> None:
        """
        A component declaring a service.pid property must follow the
        configuration with that PID
        """
        instance = self.get_instance("configadmin-pid")
        self.assertEqual(instance._name, "default")
        self.assertEqual(instance.validated, 1)

        config = self.config.get_configuration(PID_INSTANCE)
        config.update({"name": "configured"})
        self.pause()

        # Updated in place
        self.assertEqual(instance._name, "configured")
        self.assertEqual(instance.validated, 1)

        config.delete()
        self.pause()
        self.assertEqual(instance._name, "default")

    def testKilledWhileTracked(self) -> None:
        """
        A component killed while the bridge reads its properties must not keep
        a managed service registered
        """
        configurator = self.get_instance("ipopo-configadmin-configurator")

        # The component declares no PID: it is not followed when it is created
        with use_ipopo(self.context) as ipopo:
            ipopo.instantiate(FACTORY_BASIC, "raced-instance", {})

        def component_pid(factory: str, name: str) -> str:
            # The component is killed while its properties are read
            with use_ipopo(self.context) as ipopo:
                ipopo.kill(name)
            return "raced-pid"

        configurator._ConfigAdminConfigurator__component_pid = component_pid
        configurator._ConfigAdminConfigurator__track(FACTORY_BASIC, "raced-instance")

        self.assertNotIn("raced-instance", configurator._registrations)
        self.assertIsNone(
            self.context.get_service_reference(services.IManagedService, "(service.pid=raced-pid)")
        )

    def testRequiresConfiguration(self) -> None:
        """
        A component using @RequiresConfiguration must wait for its configuration
        """
        from pelix.ipopo.instance import StoredInstance

        instance = self.get_instance("configadmin-gated")
        self.assertEqual(instance.validated, 0)
        self.assertEqual(self.get_state("configadmin-gated"), StoredInstance.INVALID)

        config = self.config.get_configuration(PID_GATED)
        config.update({"name": "configured"})
        self.pause()

        self.assertEqual(instance.validated, 1)
        self.assertEqual(instance._name, "configured")
        self.assertEqual(self.get_state("configadmin-gated"), StoredInstance.VALID)

        config.delete()
        self.pause()

        self.assertEqual(instance.invalidated, 1)
        self.assertEqual(instance._name, "default")
        self.assertEqual(self.get_state("configadmin-gated"), StoredInstance.INVALID)

    def testRemovedPropertyGoesBackToDefault(self) -> None:
        """
        A property removed from the configuration of a gated component must go
        back to its declared value
        """
        instance = self.get_instance("configadmin-gated")

        config = self.config.get_configuration(PID_GATED)
        config.update({"name": "configured", "extra": 42})
        self.pause()
        self.assertEqual(instance._name, "configured")

        config.update({"extra": 42})
        self.pause()
        self.assertEqual(instance._name, "default")

        # The component is still valid: it still has a configuration
        self.assertEqual(instance.invalidated, 0)

    def testPidFromProperties(self) -> None:
        """
        Without a PID, @RequiresConfiguration must use the service.pid property
        of the component
        """
        instance = self.get_instance("configadmin-own-pid")
        self.assertEqual(instance.validated, 0)

        config = self.config.get_configuration(PID_OWN)
        config.update({"name": "configured"})
        self.pause()

        self.assertEqual(instance.validated, 1)
        self.assertEqual(instance._name, "configured")

    def testOptionalConfiguration(self) -> None:
        """
        A component using an optional @RequiresConfiguration must be validated
        without configuration
        """
        instance = self.get_instance("configadmin-optional")
        self.assertEqual(instance.validated, 1)
        self.assertEqual(instance._name, "default")

        config = self.config.get_configuration(PID_OPTIONAL)
        config.update({"name": "configured"})
        self.pause()

        self.assertEqual(instance.validated, 1)
        self.assertEqual(instance._name, "configured")

    def testRestartUpdatePolicy(self) -> None:
        """
        With the "restart" policy, @RequiresConfiguration must invalidate the
        component before applying the new properties
        """
        instance = self.get_instance("configadmin-restart")
        self.assertEqual((instance.validated, instance.invalidated), (0, 0))

        config = self.config.get_configuration(PID_RESTART)
        config.update({"name": "configured"})
        self.pause()
        self.assertEqual((instance.validated, instance.invalidated), (1, 0))
        self.assertEqual(instance._name, "configured")

        # An update invalidates then validates the component again
        config.update({"name": "updated"})
        self.pause()
        self.assertEqual((instance.validated, instance.invalidated), (2, 1))
        self.assertEqual(instance._name, "updated")

        config.delete()
        self.pause()
        self.assertEqual((instance.validated, instance.invalidated), (2, 2))
        self.assertEqual(instance._name, "default")

    def testMissingPid(self) -> None:
        """
        A component using @RequiresConfiguration without any PID can't be
        validated
        """
        from pelix.ipopo.instance import StoredInstance

        instance = self.get_instance("configadmin-no-pid")
        self.assertEqual(instance.validated, 0)
        self.assertEqual(self.get_state("configadmin-no-pid"), StoredInstance.INVALID)

    def testHiddenPropertyIsKept(self) -> None:
        """
        A configuration entry named after a hidden property must be ignored
        """
        instance = self.get_instance("configadmin-hidden")
        self.assertEqual(instance._secret, "declared-secret")

        config = self.config.get_configuration(PID_HIDDEN)
        config.update({"name": "configured", "secret": "from-configuration"})
        self.pause()

        # The visible property has been updated, the hidden one hasn't
        self.assertEqual(instance._name, "configured")
        self.assertEqual(instance._secret, "declared-secret")

        # ... and the value of the configuration hasn't become public
        with use_ipopo(self.context) as ipopo:
            properties = ipopo.get_instance_details("configadmin-hidden")["properties"]

        self.assertNotIn("secret", properties)

    def testHiddenPropertyWarnsOnce(self) -> None:
        """
        The whole configuration is sent again on each update: the refusal to
        update a hidden property must not be logged every time
        """
        config = self.config.get_configuration(PID_HIDDEN)

        with self.assertLogs("InstanceManager-configadmin-hidden", "WARNING") as logs:
            config.update({"name": "first", "secret": "from-configuration"})
            self.pause()
            config.update({"name": "second", "secret": "from-configuration"})
            self.pause()

        self.assertEqual(len(logs.records), 1, "Hidden property warning logged more than once")

    def testHiddenPropertyDotOverride(self) -> None:
        """
        A configuration entry named after a hidden property, prefixed with a
        dot, must update it confidentially
        """
        instance = self.get_instance("configadmin-hidden")
        self.assertEqual(instance._secret, "declared-secret")

        config = self.config.get_configuration(PID_HIDDEN)
        config.update({"name": "configured", ".secret": "rotated-secret"})
        self.pause()

        self.assertEqual(instance._name, "configured")
        self.assertEqual(instance._secret, "rotated-secret")

        # ... and the value still hasn't become public
        with use_ipopo(self.context) as ipopo:
            properties = ipopo.get_instance_details("configadmin-hidden")["properties"]

        self.assertNotIn("secret", properties)
        self.assertNotIn(".secret", properties)

    def testHiddenPropertyDotOverrideRestoresDefault(self) -> None:
        """
        Removing the dot-prefixed override from the configuration must
        restore the hidden property's declared default, not None
        """
        instance = self.get_instance("configadmin-hidden")

        config = self.config.get_configuration(PID_HIDDEN)
        config.update({"name": "configured", ".secret": "rotated-secret"})
        self.pause()
        self.assertEqual(instance._secret, "rotated-secret")

        config.update({"name": "configured"})
        self.pause()
        self.assertEqual(instance._secret, "declared-secret")

    def testPidSurvivesConfigurationDeletion(self) -> None:
        """
        Deleting a configuration must not take away the PID of the component:
        the factory doesn't declare that value, so it can't be restored
        """
        instance = self.get_instance("configadmin-undeclared-pid")
        ldap_filter = f"({SERVICE_PID}={PID_UNDECLARED})"
        self.assertIsNotNone(self.context.get_service_reference(SPEC_UNDECLARED_PID, ldap_filter))

        config = self.config.get_configuration(PID_UNDECLARED)
        config.update({"name": "configured"})
        self.pause()
        self.assertEqual(instance._name, "configured")

        config.delete()
        self.pause()

        # The property given by the configuration is back to its declared value
        self.assertEqual(instance._name, "default")

        # ... but the component is still reachable by its PID
        self.assertIsNotNone(self.context.get_service_reference(SPEC_UNDECLARED_PID, ldap_filter))

    def testConfigAdminEntriesAreNotProperties(self) -> None:
        """
        The entries describing the configuration itself must never become
        properties of the component
        """

        def properties() -> dict[str, Any]:
            with use_ipopo(self.context) as ipopo:
                return ipopo.get_instance_details("configadmin-gated")["properties"]

        config = self.config.get_configuration(PID_GATED)
        config.update({"name": "configured"})
        self.pause()
        self.assertNotIn(services.CONFIG_PROP_PID, properties())
        self.assertNotIn(services.CONFIG_PROP_FACTORY_PID, properties())

        config.delete()
        self.pause()
        self.assertNotIn(services.CONFIG_PROP_PID, properties())
        self.assertNotIn(services.CONFIG_PROP_FACTORY_PID, properties())

    def testUnsetPidIsNotTracked(self) -> None:
        """
        A component which declares a service.pid property without giving it a
        value must not be associated to any configuration
        """
        instance = self.get_instance("configadmin-unset-pid")
        self.assertEqual(instance._name, "default")

        # No managed service must have been registered for that component
        managed_pids = {
            ref.get_property(SERVICE_PID)
            for ref in self.context.get_all_service_references(services.IManagedService) or []
        }
        self.assertNotIn(str(None), managed_pids)
        self.assertNotIn(None, managed_pids)

        # A configuration named after the string representation of None must
        # not reach the component
        config = self.config.get_configuration(str(None))
        config.update({"name": "hijacked"})
        self.pause()

        self.assertEqual(instance._name, "default")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
