#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Configuration Admin shell commands

Provides commands to the Pelix shell to work with the Configuration Admin
service

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2025 Thomas Calmant

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

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import pelix.services
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Invalidate, Provides, Requires
from pelix.shell import ShellCommandMethod, ShellCommandsProvider

if TYPE_CHECKING:
    from pelix.framework import BundleContext
    from pelix.shell.beans import ShellSession


# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# -----------------------------------------------------------------------------


@ComponentFactory("configadmin-shell-commands-factory")
@Requires("_config_admin", pelix.services.IConfigurationAdmin)
@Provides(ShellCommandsProvider)
@Instantiate("configadmin-shell-commands")
class ConfigAdminCommands(ShellCommandsProvider):
    """
    Configuration Admin shell commands
    """

    # Injected services
    _config_admin: pelix.services.IConfigurationAdmin

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Handled configurations (PID -> Configuration)
        self._configs: Dict[str, pelix.services.Configuration] = {}

    @Invalidate
    def invalidate(self, _: "BundleContext") -> None:
        """
        Component invalidated
        """
        # Clean up
        self._configs.clear()

    @staticmethod
    def get_namespace() -> str:
        """
        Retrieves the name space of this command handler
        """
        return "config"

    def get_methods(self) -> List[Tuple[str, ShellCommandMethod]]:
        """
        Retrieves the list of tuples (command, method) for this command handler
        """
        return [
            ("create", self.create),
            ("update", self.update),
            ("reload", self.reload),
            ("delete", self.delete),
            ("list", self.list),
        ]

    def create(self, session: "ShellSession", factory_pid: str, **kwargs: Any) -> None:
        """
        Creates a factory configuration
        """
        config = self._config_admin.create_factory_configuration(factory_pid)

        # Print the configuration PID
        pid = config.get_pid()
        session.write_line(f"New configuration: {pid}")

        if kwargs:
            # Update it immediately if some properties are already set
            config.update(kwargs)

    def update(self, _: "ShellSession", pid: str, **kwargs: Any) -> None:
        """
        Updates a configuration
        """
        # Get the configuration with given PID
        self._configs[pid] = config = self._config_admin.get_configuration(pid)

        # Get previous values
        old_properties = config.get_properties()
        if old_properties is None:
            new_properties = {}
        else:
            new_properties = old_properties.copy()

        # Update properties
        new_properties.update(kwargs)

        # Remove properties which value is now None
        for key, value in kwargs.items():
            if value == "None":
                del new_properties[key]

        # Update configuration
        config.update(new_properties)

    def reload(self, session: "ShellSession", pid: str) -> None:
        """
        Reloads the configuration with the given PID from the persistence
        """
        # Get the configuration with given PID
        self._configs[pid] = config = self._config_admin.get_configuration(pid)

        try:
            # Reload the file
            config.reload()
        except Exception as ex:
            # Log errors
            session.write_line("Error reloading {0}: {1}", pid, ex)

    def delete(self, _: "ShellSession", pid: str) -> None:
        """
        Deletes a configuration
        """
        self._config_admin.get_configuration(pid).delete()

        try:
            del self._configs[pid]
        except KeyError:
            # Configuration was unknown
            pass

    def list(self, session: "ShellSession", pid: Optional[str] = None) -> None:
        """
        Lists known configurations
        """
        configs = self._config_admin.list_configurations()
        if not configs:
            session.write_line("No configuration.")
            return

        # Filter with PID
        if pid is not None:
            for config in configs:
                if config.get_pid() == pid:
                    configs = [config]
                    break

            else:
                session.write_line("No configuration with PID {0}.", pid)
                return

        lines = []
        for config in configs:
            lines.append("* {0}:".format(config.get_pid()))
            factory_pid = config.get_factory_pid()
            if factory_pid:
                lines.append("\tFactory PID: {0}".format(factory_pid))
            lines.append("\tLocation: {0}".format(config.get_bundle_location()))

            try:
                properties = config.get_properties()
                if properties is None:
                    lines.append("\tNot yet updated")

                else:
                    lines.append("\tProperties:")
                    lines.extend("\t\t{0} = {1}".format(key, value) for key, value in properties.items())

            except ValueError:
                lines.append("\t** Deleted **")

        lines.append("")
        session.write_line("{0}", "\n".join(lines))
