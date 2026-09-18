#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Regression tests for issue #114: deadlock when a managed service changes the
properties of a service it provides while being configured.

Each risky step runs in a daemon thread: a deadlock makes the test fail after
a timeout instead of hanging the whole test suite.

:author: Thomas Calmant
"""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from typing import Any

import pelix.framework
from pelix import constants, services
from pelix.ipopo.constants import use_ipopo
from tests.services import configadmin_deadlock_bundle as bundle_module

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

DEADLOCK_TIMEOUT = 10
""" Time given to a step before considering it is deadlocked (in seconds) """

EVENT_TIMEOUT = 5
""" Time given to an asynchronous notification (in seconds) """

MANAGED_PID = "any_pid"
VALIDATE_PID = "validate_pid"
FACTORY_PID = "any_factory_pid"

# ------------------------------------------------------------------------------


class ConfigAdminDeadlockTest(unittest.TestCase):
    """
    Tests the scenarios of issue #114
    """

    framework: pelix.framework.Framework
    context: pelix.framework.BundleContext

    def setUp(self) -> None:
        """
        Starts a framework with iPOPO and the test components, but without
        ConfigurationAdmin
        """
        self.conf_folder = tempfile.mkdtemp(prefix="ipopo-ca-deadlock-")
        self.deadlocked = False

        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "tests.services.configadmin_deadlock_bundle"),
            {"configuration.folder": self.conf_folder},
        )
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        self.configadmin_bundle = self.context.install_bundle("pelix.services.configadmin")

    def tearDown(self) -> None:
        """
        Stops the framework, without hanging if a thread is deadlocked
        """
        if not self.deadlocked:
            thread = threading.Thread(target=pelix.framework.FrameworkFactory.delete_framework, daemon=True)
            thread.start()
            thread.join(DEADLOCK_TIMEOUT)
            if thread.is_alive():
                self.fail("Deadlock while stopping the framework")

        shutil.rmtree(self.conf_folder, ignore_errors=True)

    def run_bounded(self, method: Callable[..., Any], *args: Any) -> Any:
        """
        Runs the given method in a daemon thread and fails if it doesn't return
        in time

        :param method: The method to call
        :param args: Its arguments
        :return: The result of the method
        """
        result: list[Any] = []
        errors: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(method(*args))
            except BaseException as ex:  # noqa: BLE001
                # Given back to the test thread
                errors.append(ex)

        thread = threading.Thread(target=runner, daemon=True, name="ca-deadlock-test")
        thread.start()
        thread.join(DEADLOCK_TIMEOUT)
        if thread.is_alive():
            # Don't try to stop the framework: it would hang too
            self.deadlocked = True
            self.fail(f"Deadlock calling {getattr(method, '__name__', method)}")

        if errors:
            raise errors[0]

        return result[0]

    def wait_event(self, event: threading.Event, what: str) -> None:
        """
        Waits for an event to be set
        """
        self.assertTrue(event.wait(EVENT_TIMEOUT), f"Timeout waiting for {what}")

    def wait_property(self, spec: str, key: str, value: Any, ldap_filter: str | None = None) -> None:
        """
        Waits for the service with the given specification to have the given
        property value
        """
        deadline = time.monotonic() + EVENT_TIMEOUT
        current: Any = None
        while time.monotonic() < deadline:
            ref = self.context.get_service_reference(spec, ldap_filter)
            if ref is not None:
                current = ref.get_property(key)
                if current == value:
                    return

            time.sleep(0.01)

        self.fail(f"Property {key} of {spec} is {current!r}, not {value!r}")

    def instantiate(self, factory: str, name: str, properties: dict[str, Any] | None = None) -> Any:
        """
        Instantiates a component, in a bounded thread
        """

        def do_instantiate() -> Any:
            with use_ipopo(self.context) as ipopo:
                return ipopo.instantiate(factory, name, properties)

        return self.run_bounded(do_instantiate)

    def start_configadmin(self) -> None:
        """
        Starts the ConfigurationAdmin bundle, in a bounded thread
        """
        self.run_bounded(self.configadmin_bundle.start)

    def stop_configadmin(self) -> None:
        """
        Stops the ConfigurationAdmin bundle, in a bounded thread
        """
        self.run_bounded(self.configadmin_bundle.stop)

    def get_config_admin(self) -> services.IConfigurationAdmin:
        """
        Returns the ConfigurationAdmin service
        """
        ref = self.context.get_service_reference(services.IConfigurationAdmin)
        assert ref is not None
        return self.context.get_service(ref)

    def write_configuration(self, pid: str, properties: dict[str, Any]) -> None:
        """
        Writes a configuration as the JSON persistence does, before
        ConfigurationAdmin starts
        """
        properties = properties.copy()
        properties[services.CONFIG_PROP_PID] = pid
        with open(os.path.join(self.conf_folder, f"{pid}.config.js"), "w") as filep:
            json.dump(properties, filep)

    def test_configadmin_started_after_managed_service(self) -> None:
        """
        Issue #114: the managed service is there before ConfigurationAdmin,
        which starts with a stored configuration for it
        """
        self.write_configuration(MANAGED_PID, {"name": "configured"})

        component: bundle_module.ManagedComponent = self.instantiate(
            bundle_module.FACTORY_MANAGED, "managed", {constants.SERVICE_PID: MANAGED_PID}
        )
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "asd")

        # Start ConfigurationAdmin: it notifies the service from its validation
        self.start_configadmin()
        self.wait_event(component.updated_event, "the initial configuration")
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "configured")

        # Runtime update and deletion
        config = self.get_config_admin().get_configuration(MANAGED_PID)
        component.updated_event.clear()
        self.run_bounded(config.update, {"name": "updated"})
        self.wait_event(component.updated_event, "the configuration update")
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "updated")

        component.updated_event.clear()
        self.run_bounded(config.delete)
        self.wait_event(component.updated_event, "the configuration deletion")
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "None")

    def test_configadmin_restarted(self) -> None:
        """
        Issue #114: the configuration has been created by a previous run of
        ConfigurationAdmin, which is restarted while the service is there
        """
        component: bundle_module.ManagedComponent = self.instantiate(
            bundle_module.FACTORY_MANAGED, "managed", {constants.SERVICE_PID: MANAGED_PID}
        )

        self.start_configadmin()
        config = self.get_config_admin().get_configuration(MANAGED_PID)
        self.run_bounded(config.update, {"name": "first-run"})
        self.wait_event(component.updated_event, "the first configuration")
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "first-run")

        # Restart ConfigurationAdmin: the configuration is loaded again
        self.stop_configadmin()
        component.updated_event.clear()
        self.start_configadmin()
        self.wait_event(component.updated_event, "the configuration after restart")
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "first-run")

    def test_configadmin_started_before_managed_service(self) -> None:
        """
        The managed service comes after ConfigurationAdmin and its
        configuration
        """
        self.start_configadmin()
        config = self.get_config_admin().get_configuration(MANAGED_PID)
        self.run_bounded(config.update, {"name": "configured"})

        component: bundle_module.ManagedComponent = self.instantiate(
            bundle_module.FACTORY_MANAGED, "managed", {constants.SERVICE_PID: MANAGED_PID}
        )
        self.wait_event(component.updated_event, "the initial configuration")
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "configured")

        # Update from the test thread, as a user would do
        component.updated_event.clear()
        self.run_bounded(config.update, {"name": "updated"})
        self.wait_event(component.updated_event, "the configuration update")
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "updated")

    def test_update_from_validate(self) -> None:
        """
        Rarer variant of issue #114: a component updates configurations from
        its @Validate method, notifying itself and an already registered
        managed service, and changes its own provided properties
        """
        self.start_configadmin()

        managed: bundle_module.ManagedComponent = self.instantiate(
            bundle_module.FACTORY_MANAGED, "managed", {constants.SERVICE_PID: MANAGED_PID}
        )
        validating: bundle_module.ValidateComponent = self.instantiate(
            bundle_module.FACTORY_VALIDATE,
            "validating",
            {constants.SERVICE_PID: VALIDATE_PID, "other.pid": MANAGED_PID},
        )

        self.wait_event(validating.validated, "the validation")
        self.wait_event(validating.updated_event, "the update of the validated component")
        self.wait_event(managed.updated_event, "the update of the other managed service")
        self.wait_property(bundle_module.SPEC_VALIDATE, "name", "from-validate")
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "from-other-validate")

    def test_update_from_validate_triggered_by_configadmin(self) -> None:
        """
        Same as test_update_from_validate, but the component is validated by
        the arrival of ConfigurationAdmin, i.e. from a service event
        """
        managed: bundle_module.ManagedComponent = self.instantiate(
            bundle_module.FACTORY_MANAGED, "managed", {constants.SERVICE_PID: MANAGED_PID}
        )
        validating: bundle_module.ValidateComponent = self.instantiate(
            bundle_module.FACTORY_VALIDATE,
            "validating",
            {constants.SERVICE_PID: VALIDATE_PID, "other.pid": MANAGED_PID},
        )
        self.assertFalse(validating.validated.is_set())

        self.start_configadmin()

        self.wait_event(validating.validated, "the validation")
        self.wait_event(validating.updated_event, "the update of the validated component")
        self.wait_event(managed.updated_event, "the update of the other managed service")
        self.wait_property(bundle_module.SPEC_VALIDATE, "name", "from-validate")
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "from-other-validate")

    def test_managed_factory_started_before_configadmin(self) -> None:
        """
        Managed service factory there before ConfigurationAdmin, which starts
        with a stored factory configuration. The factory changes its provided
        properties and instantiates a component from its callback.
        """
        pid = f"{FACTORY_PID}-stored"
        self.write_configuration(pid, {services.CONFIG_PROP_FACTORY_PID: FACTORY_PID, "value": 42})

        factory: bundle_module.ManagedFactoryComponent = self.instantiate(
            bundle_module.FACTORY_MSF, "msf", {constants.SERVICE_PID: FACTORY_PID}
        )

        self.start_configadmin()
        self.wait_event(factory.updated_event, "the initial factory configuration")
        self.wait_property(bundle_module.SPEC_MSF, "count", 1)
        self.wait_property(bundle_module.SPEC_CHILD, "value", 42, f"(config.pid={pid})")

    def test_managed_factory_started_after_configadmin(self) -> None:
        """
        Managed service factory configured at runtime
        """
        self.start_configadmin()
        config_admin = self.get_config_admin()

        factory: bundle_module.ManagedFactoryComponent = self.instantiate(
            bundle_module.FACTORY_MSF, "msf", {constants.SERVICE_PID: FACTORY_PID}
        )

        config = self.run_bounded(config_admin.create_factory_configuration, FACTORY_PID)
        pid = config.get_pid()
        self.run_bounded(config.update, {"value": 1})
        self.wait_event(factory.updated_event, "the factory configuration")
        self.wait_property(bundle_module.SPEC_MSF, "count", 1)
        self.wait_property(bundle_module.SPEC_CHILD, "value", 1, f"(config.pid={pid})")

        factory.updated_event.clear()
        self.run_bounded(config.update, {"value": 2})
        self.wait_event(factory.updated_event, "the factory configuration update")
        self.wait_property(bundle_module.SPEC_MSF, "count", 2)

        self.run_bounded(config.delete)
        self.wait_event(factory.deleted_event, "the factory configuration deletion")
        self.wait_property(bundle_module.SPEC_MSF, "count", 3)
        self.assertIsNone(self.context.get_service_reference(bundle_module.SPEC_CHILD))

    def test_fileinstall_update(self) -> None:
        """
        The configuration file is written while everything runs: the managed
        service is notified from the FileInstall threads
        """
        fileinstall_bundle = self.context.install_bundle("pelix.services.fileinstall")
        self.run_bounded(fileinstall_bundle.start)

        # Speed up the polling
        fileinstall_ref = self.context.get_service_reference(services.FileInstall)
        assert fileinstall_ref is not None
        self.context.get_service(fileinstall_ref)._poll_time = 0.1  # type: ignore
        self.start_configadmin()

        component: bundle_module.ManagedComponent = self.instantiate(
            bundle_module.FACTORY_MANAGED, "managed", {constants.SERVICE_PID: MANAGED_PID}
        )

        # Let FileInstall see the configuration folder before writing
        time.sleep(0.3)
        self.write_configuration(MANAGED_PID, {"name": "from-file"})
        self.wait_event(component.updated_event, "the configuration file")
        self.wait_property(bundle_module.SPEC_MANAGED, "name", "from-file")
