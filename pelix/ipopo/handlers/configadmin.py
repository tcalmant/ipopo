#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
ConfigurationAdmin handler, for the @RequiresConfiguration decorator

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.2.2

..

    Copyright 2026 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import logging
import threading
from collections.abc import Iterable
from typing import Any

import pelix.constants
import pelix.ipopo.constants as ipopo_constants
from pelix import services
from pelix.constants import ActivatorProto, BundleActivator
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceRegistration
from pelix.ipopo.contexts import ComponentContext
from pelix.ipopo.handlers import constants
from pelix.ipopo.instance import StoredInstance

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class _HandlerFactory(constants.HandlerFactory):
    """
    Factory service for configuration handlers
    """

    def get_handlers(self, component_context: ComponentContext, instance: Any) -> Iterable[constants.Handler]:
        """
        Sets up the configuration handler of the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
        """
        config = component_context.get_handler(ipopo_constants.HANDLER_CONFIGADMIN)
        if config is None:
            return ()

        # The PID can be given by the decorator or by a component property
        pid = config.get("pid") or component_context.properties.get(pelix.constants.SERVICE_PID)
        return (
            ConfigurationHandler(
                pid,
                config.get("optional", False),
                config.get("update_policy", ipopo_constants.UPDATE_POLICY_RECONFIGURE),
            ),
        )


@BundleActivator
class Activator(ActivatorProto):
    """
    The bundle activator
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self._registration: ServiceRegistration[constants.HandlerFactory] | None = None

    def start(self, context: BundleContext) -> None:
        """
        Bundle started
        """
        # Register the handler factory service
        self._registration = context.register_service(
            constants.HandlerFactory,
            _HandlerFactory(),
            {constants.PROP_HANDLER_ID: ipopo_constants.HANDLER_CONFIGADMIN},
        )

    def stop(self, context: BundleContext) -> None:
        """
        Bundle stopped
        """
        if self._registration is not None:
            # Unregister the service
            self._registration.unregister()
            self._registration = None


# ------------------------------------------------------------------------------


class ConfigurationHandler(constants.Handler, services.IManagedService):
    """
    Injects the properties of a ConfigurationAdmin configuration into the
    component and, if the requirement is not optional, keeps the component
    invalid until that configuration exists.
    """

    def __init__(self, pid: str | None, optional: bool, update_policy: str) -> None:
        """
        :param pid: PID of the configuration to follow
        :param optional: If True, the component is valid without configuration
        :param update_policy: Reaction to a configuration update
        """
        super().__init__()
        self._pid = pid
        self._optional = optional
        self._update_policy = update_policy

        self._ipopo_instance: StoredInstance | None = None
        self._registration: ServiceRegistration[services.IManagedService] | None = None
        self._configured = False

        # Protects the state of the handler
        self._lock = threading.RLock()

        # Serializes the updates coming from the ConfigurationAdmin pool: the
        # state lock can't be used for that, as it must not be held while
        # calling the stored instance
        self.__update_lock = threading.RLock()

        # Default value of the properties given by the configuration, to be
        # restored when the configuration is deleted
        self._defaults: dict[str, Any] = {}

    def get_kinds(self) -> tuple[str]:
        """
        Returns the kinds of this handler
        """
        return (constants.KIND_CONFIGURATION,)

    def manipulate(self, stored_instance: StoredInstance, component_instance: Any) -> None:
        """
        Stores the stored instance of the component

        :param stored_instance: The iPOPO component StoredInstance
        :param component_instance: The component instance
        """
        self._ipopo_instance = stored_instance

    def is_valid(self) -> bool:
        """
        The component can be validated only if its configuration is available,
        unless the requirement is optional
        """
        return self._optional or self._configured

    def start(self) -> None:
        """
        Registers the managed service which will receive the configuration
        """
        if self._ipopo_instance is None:
            return

        if not self._pid:
            _logger.warning(
                "Component %s requires a configuration but has no PID",
                self._ipopo_instance.name,
            )
            return

        self._registration = self._ipopo_instance.bundle_context.register_service(
            services.IManagedService, self, {pelix.constants.SERVICE_PID: self._pid}
        )

    def stop(self) -> None:
        """
        Unregisters the managed service
        """
        if self._registration is not None:
            self._registration.unregister()
            self._registration = None

    def clear(self) -> None:
        """
        Releases all references
        """
        with self._lock:
            self._ipopo_instance = None
            self._defaults.clear()

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        The configuration of the component has been updated or deleted

        :param properties: The new configuration properties, None if the
                           configuration has been deleted
        """
        # The update lock is taken first: the state lock must be released
        # before calling the stored instance, which takes its own lock
        with self.__update_lock:
            with self._lock:
                stored_instance = self._ipopo_instance
                # Read the context once: the component can be killed at any time
                context = stored_instance.context if stored_instance is not None else None
                if stored_instance is None or context is None:
                    # Component has been killed
                    return

                if properties is None:
                    # Configuration deleted: go back to the declared values
                    self._configured = False
                    update = self._defaults
                    self._defaults = {}
                else:
                    # The entries describing the configuration itself are not
                    # component properties
                    configured = {
                        key: value
                        for key, value in properties.items()
                        if key not in services.CONFIG_ADMIN_PROPERTIES
                    }

                    # Keep the declared value of the new properties, to restore
                    # them when they leave the configuration
                    current = context.properties
                    hidden_defaults = context.factory_context.hidden_properties
                    for key in configured:
                        if key not in self._defaults:
                            if key.startswith(".") and key[1:] in hidden_defaults:
                                # Dot-prefixed override of a hidden property:
                                # its declared value isn't in context.properties
                                self._defaults[key] = hidden_defaults[key[1:]]
                            else:
                                self._defaults[key] = current.get(key)

                    update = dict(configured)

                    # Give back their declared value to the properties which
                    # are not in the configuration anymore
                    for key in set(self._defaults).difference(configured):
                        update[key] = self._defaults.pop(key)

                    self._configured = True

            try:
                # With the restart policy, the component is invalidated before
                # the new properties are applied and validated again
                # afterwards, all of it in a single lock acquisition
                stored_instance.reconfigure(
                    update, self._update_policy == ipopo_constants.UPDATE_POLICY_RESTART
                )
            except ValueError:
                # Component has been killed in the meantime
                pass
