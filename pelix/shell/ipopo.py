#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO shell commands

Provides commands to the Pelix shell to get the state of iPOPO instances.

:author: Thomas Calmant
:copyright: Copyright 2012, isandlaTech
:license: GPLv3
:version: 0.1
:status: Alpha

..

    This file is part of iPOPO.

    iPOPO is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    iPOPO is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with iPOPO. If not, see <http://www.gnu.org/licenses/>.
"""

__version__ = (0, 1, 0)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

from pelix.ipopo.constants import IPOPO_SERVICE_SPECIFICATION
from pelix.ipopo.decorators import ComponentFactory, Requires, Provides, \
    Instantiate

import logging

# ------------------------------------------------------------------------------

SHELL_COMMAND_SPEC = "pelix.shell.command"
SHELL_UTILS_SERVICE_SPEC = "pelix.shell.utilities"

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

def ipopo_state_to_str(state):
    """
    Converts the state of a component instance to its string representation
    
    :param state: The state of an iPOPO component
    :return: A string representation of the state
    """
    ipopo_states = {0: "INVALID",
                    1:"VALID",
                    2:"KILLED",
                    3:"VALIDATING"
    }

    return ipopo_states.get(state, "Unknown state (%d)".format(state))

# ------------------------------------------------------------------------------

@ComponentFactory("ipopo-shell-commands-factory")
@Requires("_ipopo", IPOPO_SERVICE_SPECIFICATION)
@Requires("_utils", SHELL_UTILS_SERVICE_SPEC)
@Provides(SHELL_COMMAND_SPEC)
@Instantiate("ipopo-shell-commands")
class IPopoCommands(object):
    """
    iPOPO shell commands
    """
    def __init__(self):
        """
        Sets up the object
        """
        self._ipopo = None
        self._utils = None


    def get_namespace(self):
        """
        Retrieves the name space of this command handler
        """
        return "ipopo"


    def get_methods(self):
        """
        Retrieves the list of tuples (command, method) for this command handler
        """
        return [("factories", self.list_factories),
                ("instances", self.list_instances),
                ("instance", self.instance_details),
                ("instantiate", self.instantiate),
                ("kill", self.kill),
                ]


    def get_methods_names(self):
        """
        Retrieves the list of tuples (command, method name) for this command
        handler.
        """
        result = []
        for command, method in self.get_methods():
            result.append((command, method.__name__))

        return result


    def list_factories(self, stdin, stdout):
        """
        Lists the available iPOPO component factories
        """
        header = ('Factory', 'Bundle')
        lines = [(name, self._ipopo.get_factory_bundle(name))
                 for name in self._ipopo.get_factories()]
        stdout.write(self._utils.make_table(header, lines))


    def list_instances(self, stdin, stdout):
        """
        Lists the active iPOPO component instances
        """
        headers = ('Name', 'Factory', 'State')
        lines = [(name, factory, ipopo_state_to_str(state))
                 for name, factory, state in self._ipopo.get_instances()]

        stdout.write(self._utils.make_table(headers, lines))


    def instance_details(self, stdin, stdout, name):
        """
        instance <name> - Prints the details of the given component instance
        """
        lines = []

        try:
            details = self._ipopo.get_instance_details(name)

        except ValueError as ex:
            stdout.write("Error getting instance details: %s\n" % ex)
            return

        lines.append("Name   : {0}".format(details["name"]))
        lines.append("Factory: {0}".format(details["factory"]))
        lines.append("State  : {0}".format(ipopo_state_to_str(
                                                        details["state"])))
        if "service" in details:
            lines.append("Service: {0}".format(details["service"]))

        lines.append("Dependencies:")
        for field, infos in details["dependencies"].items():
            lines.append("\tField: {0}".format(field))
            lines.append("\t\tOptional : {0}".format(infos["optional"]))
            lines.append("\t\tAggregate: {0}".format(infos["aggregate"]))
            if "filter" in infos:
                lines.append("\t\tFilter   : {0}".format(infos["filter"]))

            lines.append("\t\tHandler  : {0}".format(infos["handler"]))
            lines.append("\t\tBindings :")
            for ref in infos["bindings"]:
                lines.append('\t\t\t{0}'.format(ref))

        lines.append("")
        stdout.write('\n'.join(lines))


    def instantiate(self, stdin, stdout, factory, name, **kwargs):
        """
        instantiate <factory> <name> [<property=value> ...] - Instantiate a
        component of the given factory with the given name and properties
        """
        try:
            self._ipopo.instantiate(factory, name, kwargs)
            stdout.write("Component '%s' instantiated.\n" % name)

        except ValueError as ex:
            stdout.write("Invalid parameter: %s\n" % ex)

        except TypeError as ex:
            stdout.write("Invalid factory: %s\n" % ex)

        except Exception as ex:
            stdout.write("Error instantiating the component: %s\n" % ex)


    def kill(self, stdin, stdout, name):
        """
        kill <name> - Kills the given component instance
        """
        try:
            self._ipopo.kill(name)
            stdout.write("Component '%s' killed.\n" % name)

        except ValueError as ex:
            stdout.write("Invalid parameter: %s\n" % ex)
