#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Configuration Admin shell commands

Provides commands to the Pelix shell to work with the Configuration Admin
service

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

# Shell constants
from pelix.shell import SERVICE_SHELL_COMMAND

# iPOPO Decorators
from pelix.ipopo.decorators import (
    ComponentFactory,
    Requires,
    Provides,
    Instantiate,
    Invalidate,
)
import pelix.services

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# -----------------------------------------------------------------------------


@ComponentFactory("configadmin-shell-commands-factory")
@Requires("_config_admin", pelix.services.SERVICE_CONFIGURATION_ADMIN)
@Provides(SERVICE_SHELL_COMMAND)
@Instantiate("configadmin-shell-commands")
class ConfigAdminCommands(object):
    """
    Configuration Admin shell commands
    """

    def __init__(self):
        """
        Sets up members
        """
        # Injected services
        self._config_admin = None

        # Handled configurations (PID -> Configuration)
        self._configs = {}

    @Invalidate
    def invalidate(self, _):
        """
        Component invalidated
        """
        # Clean up
        self._configs.clear()

    @staticmethod
    def get_namespace():
        """
        Retrieves the name space of this command handler
        """
        return "config"

    def get_methods(self):
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

    def create(self, io_handler, factory_pid, **kwargs):
        """
        Creates a factory configuration
        """
        config = self._config_admin.create_factory_configuration(factory_pid)

        # Print the configuration PID
        pid = config.get_pid()
        io_handler.write_line("New configuration: {0}", pid)

        if kwargs:
            # Update it immediately if some properties are already set
            config.update(kwargs)

    def update(self, _, pid, **kwargs):
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

    def reload(self, io_handler, pid):
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
            io_handler.write_line("Error reloading {0}: {1}", pid, ex)

    def delete(self, _, pid):
        """
        Deletes a configuration
        """
        self._config_admin.get_configuration(pid).delete()

        try:
            del self._configs[pid]
        except KeyError:
            # Configuration was unknown
            pass

    def list(self, io_handler, pid=None):
        """
        Lists known configurations
        """
        configs = self._config_admin.list_configurations()
        if not configs:
            io_handler.write_line("No configuration.")
            return

        # Filter with PID
        if pid is not None:
            for config in configs:
                if config.get_pid() == pid:
                    configs = [config]
                    break

            else:
                io_handler.write_line("No configuration with PID {0}.", pid)
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
                    lines.extend(
                        "\t\t{0} = {1}".format(key, value)
                        for key, value in properties.items()
                    )

            except ValueError:
                lines.append("\t** Deleted **")

        lines.append("")
        io_handler.write_line("{0}", "\n".join(lines))
