#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining a managed service factory to be updated by ConfigAdmin

:author: Thomas Calmant
"""

from typing import Any

from pelix import constants, services
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Property, Provides

# ------------------------------------------------------------------------------

FACTORY_PID = "test.ca.factory"

# ------------------------------------------------------------------------------


@ComponentFactory()
@Provides(services.IManagedServiceFactory)
@Property("_factory_pid", constants.SERVICE_PID, FACTORY_PID)
@Instantiate("configadmin-factory-test")
class ConfigurableFactory(services.IManagedServiceFactory):
    """
    Configurable managed service factory
    """

    _factory_pid: str

    def __init__(self) -> None:
        """
        Sets up members
        """
        # PID -> configuration properties
        self.configurations: dict[str, dict[str, Any]] = {}
        self.deleted_pids: list[str] = []
        self.call_count = 0

    def reset(self) -> None:
        """
        Resets the flags
        """
        self.configurations.clear()
        del self.deleted_pids[:]
        self.call_count = 0

    def get_name(self) -> str:
        """
        Returns the name of the factory
        """
        return FACTORY_PID

    def updated(self, pid: str, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        self.call_count += 1
        self.configurations[pid] = properties or {}

    def deleted(self, pid: str) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        self.call_count += 1
        self.deleted_pids.append(pid)
        self.configurations.pop(pid, None)
