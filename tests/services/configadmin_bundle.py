#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining a component to be updated by ConfigAdmin

:author: Thomas Calmant
"""

from typing import Any

from pelix import constants, services
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Property, Provides

# ------------------------------------------------------------------------------

CONFIG_PID = "test.ca.bundle"

# ------------------------------------------------------------------------------


@ComponentFactory()
@Provides(services.IManagedService)
@Property("_config_pid", constants.SERVICE_PID, CONFIG_PID)
@Instantiate("configadmin-test")
class Configurable(services.IManagedService):
    """
    Configurable component
    """

    _config_pid: str

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.value: Any = None
        self.deleted = False
        self.call_count = 0

    def reset(self) -> None:
        """
        Resets the flags
        """
        self.value = None
        self.deleted = False
        self.call_count = 0

    def updated(self, properties: dict[str, Any] | None) -> None:
        """
        Called by the ConfigurationAdmin service
        """
        self.call_count += 1

        if properties is None:
            # Deleted
            self.value = None
            self.deleted = True
        else:
            # Updated
            self.value = properties.get("config.value", "<not set>")
