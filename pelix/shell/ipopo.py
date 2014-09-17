#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO shell commands

Provides commands to the Pelix shell to get the state of iPOPO instances.

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 0.5.7
:status: Beta

..

    Copyright 2014 isandlaTech

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

# Module version
__version_info__ = (0, 5, 7)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix
from pelix.ipopo.decorators import ComponentFactory, Requires, Provides, \
    Instantiate
import pelix.ipopo.constants
import pelix.shell

# Standard library
import logging

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


def ipopo_state_to_str(state):
    """
    Converts the state of a component instance to its string representation

    :param state: The state of an iPOPO component
    :return: A string representation of the state
    """
    ipopo_states = {0: "INVALID",
                    1: "VALID",
                    2: "KILLED",
                    3: "VALIDATING"}

    return ipopo_states.get(state, "Unknown state ({0})".format(state))

# ------------------------------------------------------------------------------


@ComponentFactory("ipopo-shell-commands-factory")
@Requires("_ipopo", pelix.ipopo.constants.SERVICE_IPOPO)
@Requires("_utils", pelix.shell.SERVICE_SHELL_UTILS)
@Provides(pelix.shell.SERVICE_SHELL_COMMAND)
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
                ("factory", self.factory_details),
                ("instances", self.list_instances),
                ("waiting", self.list_waitings),
                ("instance", self.instance_details),
                ("instantiate", self.instantiate),
                ("kill", self.kill)]

    def list_factories(self, io_handler, name=None):
        """
        Lists the available iPOPO component factories
        """
        header = ('Factory', 'Bundle')

        factories = self._ipopo.get_factories()
        if name is not None:
            # Filter factories by name
            factories = [factory for factory in factories if name in factory]

        lines = sorted((name, self._ipopo.get_factory_bundle(name))
                       for name in factories)

        io_handler.write(self._utils.make_table(header, lines))
        if name is None:
            io_handler.write_line("{0} factories available", len(lines))
        else:
            io_handler.write_line("{0} filtered factories", len(lines))

    def list_instances(self, io_handler, name=None):
        """
        Lists the active iPOPO component instances
        """
        headers = ('Name', 'Factory', 'State')

        instances = self._ipopo.get_instances()
        if name is not None:
            # Filter instances by name
            instances = [instance for instance in instances
                         if name in instance[0]]

        # Lines are already sorted
        lines = ((name, factory, ipopo_state_to_str(state))
                 for name, factory, state in instances)

        io_handler.write(self._utils.make_table(headers, lines))
        if name is None:
            io_handler.write_line("{0} components running", len(instances))
        else:
            io_handler.write_line("{0} filtered components", len(instances))

    def list_waitings(self, io_handler, name=None):
        """
        Lists the components waiting to be instantiated
        """
        headers = ('Name', 'Factory', 'Missing handlers')

        components = self._ipopo.get_waiting_components()
        if name is not None:
            # Filter components by name
            components = [component for component in components
                          if name in component[0]]

        # Lines are already sorted
        lines = ((name, factory, ', '.join(missing))
                 for name, factory, missing in components)

        io_handler.write(self._utils.make_table(headers, lines))
        if name is None:
            io_handler.write_line("{0} components in the waiting queue",
                                  len(components))
        else:
            io_handler.write_line("{0} filtered components", len(components))

    def factory_details(self, io_handler, name):
        """
        Prints the details of the given component factory
        """
        try:
            details = self._ipopo.get_factory_details(name)

        except ValueError as ex:
            io_handler.write_line("Error getting details about '{0}': {1}",
                                  name, ex)
            return

        lines = [
            "Name  : {0}".format(details["name"]),
            "Bundle: {0}".format(details["bundle"])]

        properties = details.get('properties', None)
        if properties:
            lines.append("Properties:")
            prop_headers = ('Key', 'Default value')
            prop_lines = [(str(key), str(value))
                          for key, value in properties.items()]
            lines.append(self._utils.make_table(prop_headers, prop_lines))

        services = details.get('services', None)
        if services:
            lines.append("Provided services:")
            lines.extend("\t{0}".format(spec) for spec in services)
            lines.append('')

        requirements = details.get('requirements', None)
        if requirements:
            lines.append("Requirements:")
            req_headers = ('ID', 'Specification', 'Filter', 'Aggregate',
                           'Optional')
            req_lines = [(item['id'], item['specification'], item['filter'],
                          item['aggregate'], item['optional'])
                         for item in requirements]

            lines.append(self._utils.make_table(req_headers, req_lines, '\t'))

        handlers = details.get('handlers', None)
        if handlers:
            lines.append("Handlers:")
            handlers_headers = ('ID', 'Configuration')
            handlers_lines = [(key, handlers[key]) for key in sorted(handlers)]
            lines.append(self._utils.make_table(handlers_headers,
                                                handlers_lines, '\t'))

        io_handler.write('\n'.join(lines))

    def instance_details(self, io_handler, name):
        """
        Prints the details of the given component instance
        """
        try:
            details = self._ipopo.get_instance_details(name)

        except ValueError as ex:
            io_handler.write_line("Error getting details about '{0}': {1}",
                                  name, ex)
            return

        # Basic information
        lines = [
            "Name.....: {0}".format(details["name"]),
            "Factory..: {0}".format(details["factory"]),
            "Bundle ID: {0}".format(details["bundle_id"]),
            "State....: {0}".format(ipopo_state_to_str(details["state"])),
            "Services.:"]

        # Provided services
        lines.extend("\t{0}".format(svc_reference)
                     for svc_reference in details["services"].values())

        # Requirements
        lines.append("Dependencies:")
        for field, infos in details["dependencies"].items():
            lines.append("\tField: {0}".format(field))
            lines.append("\t\tSpecification: {0}"
                         .format(infos['specification']))
            if "filter" in infos:
                lines.append("\t\tFilter......: {0}".format(infos["filter"]))
            lines.append("\t\tOptional.....: {0}".format(infos["optional"]))
            lines.append("\t\tAggregate....: {0}".format(infos["aggregate"]))

            lines.append("\t\tHandler......: {0}".format(infos["handler"]))
            lines.append("\t\tBindings:")
            for ref in infos["bindings"]:
                lines.append('\t\t\t{0}'.format(ref))

        # Properties
        lines.append("Properties:")
        lines.append(self._utils.make_table(
            ("Key", "Value"), sorted(details['properties'].items()), "\t"))

        lines.append("")
        io_handler.write('\n'.join(lines))

    def instantiate(self, io_handler, factory, name, **kwargs):
        """
        Instantiates a component of the given factory with the given name and
        properties
        """
        try:
            self._ipopo.instantiate(factory, name, kwargs)
            io_handler.write_line("Component '{0}' instantiated.", name)

        except ValueError as ex:
            io_handler.write_line("Invalid parameter: {0}", ex)

        except TypeError as ex:
            io_handler.write_line("Invalid factory: {0}", ex)

        except Exception as ex:
            io_handler.write_line("Error instantiating the component: {0}", ex)
            _logger.exception("Error instantiating the component")

    def kill(self, io_handler, name):
        """
        Kills the given component instance
        """
        try:
            self._ipopo.kill(name)
            io_handler.write_line("Component '{0}' killed.", name)

        except ValueError as ex:
            io_handler.write_line("Invalid parameter: {0}", ex)
