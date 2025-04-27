#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO shell commands

Provides commands to the Pelix shell to get the state of iPOPO instances.

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

import logging
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

import pelix.ipopo.constants
import pelix.shell
from pelix.ipopo.constants import IPopoService
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Provides, Requires
from pelix.shell.completion import COMPONENT, DUMMY, FACTORY, FACTORY_PROPERTY
from pelix.shell.completion.decorators import Completion

if TYPE_CHECKING:
    from pelix.shell.beans import ShellSession

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


def ipopo_state_to_str(state: int) -> str:
    """
    Converts the state of a component instance to its string representation

    :param state: The state of an iPOPO component
    :return: A string representation of the state
    """
    ipopo_states = {
        0: "INVALID",
        1: "VALID",
        2: "KILLED",
        3: "VALIDATING",
        4: "ERRONEOUS",
    }

    return ipopo_states.get(state, f"Unknown state ({state})")


# ------------------------------------------------------------------------------


@ComponentFactory("ipopo-shell-commands-factory")
@Requires("_ipopo", IPopoService)
@Requires("_utils", pelix.shell.ShellUtils)
@Provides(pelix.shell.ShellCommandsProvider)
@Instantiate("ipopo-shell-commands")
class IPopoCommands(pelix.shell.ShellCommandsProvider):
    """
    iPOPO shell commands
    """

    _ipopo: IPopoService
    _utils: pelix.shell.ShellUtils

    def get_namespace(self) -> str:
        """
        Retrieves the name space of this command handler
        """
        return "ipopo"

    def get_methods(self) -> List[Tuple[str, pelix.shell.ShellCommandMethod]]:
        """
        Retrieves the list of tuples (command, method) for this command handler
        """
        return [
            ("factories", self.list_factories),
            ("factory", self.factory_details),
            ("instances", self.list_instances),
            ("waiting", self.list_waitings),
            ("instance", self.instance_details),
            ("instantiate", self.instantiate),
            ("kill", self.kill),
            ("retry", self.retry_erroneous),
        ]

    def list_factories(self, session: "ShellSession", name: Optional[str] = None) -> None:
        """
        Lists the available iPOPO component factories
        """
        header = ("Factory", "Bundle")

        factories = self._ipopo.get_factories()
        if name is not None:
            # Filter factories by name
            factories = [factory for factory in factories if name in factory]

        lines = sorted((name, self._ipopo.get_factory_bundle(name)) for name in factories)

        session.write(self._utils.make_table(header, lines))
        if name is None:
            session.write_line("{0} factories available", len(lines))
        else:
            session.write_line("{0} filtered factories", len(lines))

    def list_instances(self, session: "ShellSession", name: Optional[str] = None) -> None:
        """
        Lists the active iPOPO component instances
        """
        headers = ("Name", "Factory", "State")

        instances = self._ipopo.get_instances()
        if name is not None:
            # Filter instances by name
            instances = [instance for instance in instances if name in instance[0]]

        # Lines are already sorted
        lines = ((name, factory, ipopo_state_to_str(state)) for name, factory, state in instances)

        session.write(self._utils.make_table(headers, lines))
        if name is None:
            session.write_line("{0} components running", len(instances))
        else:
            session.write_line("{0} filtered components", len(instances))

    def list_waitings(self, session: "ShellSession", name: Optional[str] = None) -> None:
        """
        Lists the components waiting to be instantiated
        """
        headers = ("Name", "Factory", "Missing handlers")

        components = self._ipopo.get_waiting_components()
        if name is not None:
            # Filter components by name
            components = [component for component in components if name in component[0]]

        # Lines are already sorted
        lines = ((name, factory, ", ".join(missing)) for name, factory, missing in components)

        session.write(self._utils.make_table(headers, lines))
        if name is None:
            session.write_line("{0} components in the waiting queue", len(components))
        else:
            session.write_line("{0} filtered components", len(components))

    @Completion(FACTORY)
    def factory_details(self, session: "ShellSession", name: str) -> Any:
        """
        Prints the details of the given component factory
        """
        try:
            details = self._ipopo.get_factory_details(name)
        except ValueError as ex:
            session.write_line("Error getting details about '{0}': {1}", name, ex)
            return False

        lines = [
            f"Name  : {details['name']}",
            f"Bundle: {details['bundle']}",
        ]

        properties = details.get("properties", None)
        if properties:
            lines.append("Properties:")
            prop_headers = ("Key", "Default value")
            prop_lines = [(str(key), str(value)) for key, value in properties.items()]
            lines.append(self._utils.make_table(prop_headers, prop_lines))

        services = details.get("services", None)
        if services:
            lines.append("Provided services:")
            lines.extend(f"\t{spec}" for spec in services)
            lines.append("")

        requirements = details.get("requirements", None)
        if requirements:
            lines.append("Requirements:")
            req_headers = (
                "ID",
                "Specification",
                "Filter",
                "Aggregate",
                "Optional",
            )
            req_lines = [
                (
                    item["id"],
                    item["specification"],
                    item["filter"],
                    item["aggregate"],
                    item["optional"],
                )
                for item in requirements
            ]

            lines.append(self._utils.make_table(req_headers, req_lines, "\t"))

        handlers = details.get("handlers", None)
        if handlers:
            lines.append("Handlers:")
            handlers_headers = ("ID", "Configuration")
            handlers_lines = [(key, handlers[key]) for key in sorted(handlers)]
            lines.append(self._utils.make_table(handlers_headers, handlers_lines, "\t"))

        session.write("\n".join(lines))
        return None

    @Completion(COMPONENT)
    def instance_details(self, session: "ShellSession", name: str) -> Any:
        """
        Prints the details of the given component instance
        """
        try:
            details = self._ipopo.get_instance_details(name)
        except ValueError as ex:
            session.write_line("Error getting details about '{0}': {1}", name, ex)
            return False

        # Basic information
        lines = [
            f"Name.....: {details['name']}",
            f"Factory..: {details['factory']}",
            f"Bundle ID: {details['bundle_id']}",
            f"State....: {ipopo_state_to_str(details['state'])}",
            "Services.:",
        ]

        # Provided services
        lines.extend(f"\t{svc_reference}" for svc_reference in details["services"].values())

        # Requirements
        lines.append("Dependencies:")
        for field, infos in details["dependencies"].items():
            lines.append(f"\tField: {field}")
            lines.append(f"\t\tSpecification: {infos['specification']}")
            lines.append(f"\t\tFilter.......: {infos['filter']}")
            lines.append(f"\t\tOptional.....: {infos['optional']}")
            lines.append(f"\t\tAggregate....: {infos['aggregate']}")

            lines.append(f"\t\tHandler......: {infos['handler']}")
            lines.append("\t\tBindings:")
            for ref in infos["bindings"]:
                lines.append(f"\t\t\t{ref}")

        # Properties
        lines.append("Properties:")
        lines.append(self._utils.make_table(("Key", "Value"), sorted(details["properties"].items()), "\t"))

        # Error trace, for erroneous components
        error_trace = details["error_trace"]
        if error_trace:
            lines.append("Error trace:")
            lines.append(error_trace)

        lines.append("")
        session.write("\n".join(lines))
        return None

    @Completion(FACTORY, DUMMY, FACTORY_PROPERTY, multiple=True)
    def instantiate(self, session: "ShellSession", factory: str, name: str, **properties: Any) -> Any:
        """
        Instantiates a component of the given factory with the given name and
        properties
        """
        try:
            self._ipopo.instantiate(factory, name, properties)
            session.write_line("Component '{0}' instantiated.", name)
            # Return the instance name as a result
            return name
        except ValueError as ex:
            session.write_line("Invalid parameter: {0}", ex)
        except TypeError as ex:
            session.write_line("Invalid factory: {0}", ex)
        except Exception as ex:
            session.write_line("Error instantiating the component: {0}", ex)
            _logger.exception("Error instantiating the component")

        # We're here if an exception occurred
        return False

    @Completion(COMPONENT)
    def kill(self, session: "ShellSession", name: str) -> Any:
        """
        Kills the given component instance
        """
        try:
            self._ipopo.kill(name)
            session.write_line("Component '{0}' killed.", name)
        except ValueError as ex:
            session.write_line("Invalid parameter: {0}", ex)
            return False

        return None

    @Completion(COMPONENT, FACTORY_PROPERTY, multiple=True)
    def retry_erroneous(self, session: "ShellSession", name: str, **properties: Any) -> Any:
        """
        Removes the erroneous flag from a component and retries to validate it
        """
        try:
            new_state = self._ipopo.retry_erroneous(name, properties)
            session.write_line(
                "Component '{0}' is now in state {1}.",
                name,
                ipopo_state_to_str(new_state),
            )
        except ValueError as ex:
            session.write_line("Invalid parameter: {0}", ex)
            return False

        return None
