#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix shell service bundle.

Provides the basic command parsing and execution support to make a Pelix shell.

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
import os
import sys
import threading
from types import FrameType
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple, Union

import pelix.constants as constants
import pelix.shell.parser as parser
from pelix.framework import Bundle, BundleContext
from pelix.internals.events import ServiceEvent
from pelix.internals.registry import ServiceListener, ServiceReference, ServiceRegistration
from pelix.shell import ShellCommandsProvider, ShellService, ShellUtils
from pelix.shell.completion import BUNDLE, SERVICE
from pelix.shell.completion.decorators import Completion
from pelix.shell.report import format_frame_info

if TYPE_CHECKING:
    from pelix.shell.beans import ShellSession

# ------------------------------------------------------------------------------

# Public API
__all__ = ()

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class _ShellUtils(ShellUtils):
    """
    Utility methods for the shell
    """

    @staticmethod
    def bundlestate_to_str(state: int) -> str:
        """
        Converts a bundle state integer to a string
        """
        states = {
            Bundle.INSTALLED: "INSTALLED",
            Bundle.ACTIVE: "ACTIVE",
            Bundle.RESOLVED: "RESOLVED",
            Bundle.STARTING: "STARTING",
            Bundle.STOPPING: "STOPPING",
            Bundle.UNINSTALLED: "UNINSTALLED",
        }

        return states.get(state, f"Unknown state ({state})")

    @staticmethod
    def make_table(headers: Iterable[str], lines: Iterable[Any], prefix: Optional[str] = None) -> str:
        """
        Generates an ASCII table according to the given headers and lines

        :param headers: List of table headers (N-tuple)
        :param lines: List of table lines (N-tuples)
        :param prefix: Optional prefix for each line
        :return: The ASCII representation of the table
        :raise ValueError: Different number of columns between headers and lines
        """
        # Normalize the prefix
        prefix = str(prefix or "")

        # Maximum lengths
        lengths = [len(title) for title in headers]

        # Store the number of columns (0-based)
        nb_columns = len(lengths) - 1

        # Lines
        str_lines = []
        for idx, line in enumerate(lines):
            # Recompute lengths
            str_line: List[str] = []
            str_lines.append(str_line)
            column = -1

            try:
                for column, entry in enumerate(line):
                    str_entry = str(entry)
                    str_line.append(str_entry)

                    if len(str_entry) > lengths[column]:
                        lengths[column] = len(str_entry)

            except IndexError:
                # Line too small/big
                raise ValueError("Different sizes for header and lines " "(line {0})".format(idx + 1))

            except (TypeError, AttributeError):
                # Invalid type of line
                raise ValueError("Invalid type of line: %s", type(line).__name__)

            else:
                if column != nb_columns:
                    # Check if all lines have the same number of columns
                    raise ValueError("Different sizes for header and lines " "(line {0})".format(idx + 1))

        # Prepare the head (centered text)
        format_str = f"{prefix}|"
        for column, length in enumerate(lengths):
            format_str += " {%d:^%d} |" % (column, length)

        head_str = format_str.format(*headers)

        # Prepare the separator, according the length of the headers string
        separator = f"{prefix}{'-' * (len(head_str) - len(prefix))}"
        idx = head_str.find("|")
        while idx != -1:
            separator = "+".join((separator[:idx], separator[idx + 1 :]))
            idx = head_str.find("|", idx + 1)

        # Prepare the output
        output = [separator, head_str, separator.replace("-", "=")]

        # Compute the lines
        format_str = format_str.replace("^", "<")
        for line in str_lines:
            output.append(format_str.format(*line))
            output.append(separator)

        # Force the last end of line
        output.append("")

        # Join'em
        return "\n".join(output)


# ------------------------------------------------------------------------------


class _ShellService(parser.Shell, ShellService):
    # pylint: disable=R0904
    """
    Provides the core shell service for Pelix
    """

    def __init__(self, context: BundleContext, utilities: _ShellUtils) -> None:
        """
        Sets up the shell

        :param context: The bundle context
        """
        super(_ShellService, self).__init__(context.get_framework(), __name__)
        self._context = context
        self._utils = utilities

        # Bound services: reference -> service
        self._bound_references: Dict[ServiceReference[ShellCommandsProvider], ShellCommandsProvider] = {}

        # Service reference -> (name space, [commands])
        self._reference_commands: Dict[ServiceReference[ShellCommandsProvider], Tuple[str, List[str]]] = {}

        # Last working directory
        self._previous_path: Optional[str] = None

        # Register basic commands
        self.register_command(None, "bd", self.bundle_details)
        self.register_command(None, "bl", self.bundles_list)

        self.register_command(None, "sd", self.service_details)
        self.register_command(None, "sl", self.services_list)

        self.register_command(None, "start", self.start)
        self.register_command(None, "stop", self.stop)
        self.register_command(None, "update", self.update)
        self.register_command(None, "install", self.install)
        self.register_command(None, "uninstall", self.uninstall)

        self.register_command(None, "properties", self.properties_list)
        self.register_command(None, "property", self.property_value)

        self.register_command(None, "sysprops", self.environment_list)
        self.register_command(None, "sysprop", self.environment_value)

        self.register_command(None, "threads", self.threads_list)
        self.register_command(None, "thread", self.thread_details)

        self.register_command(None, "loglevel", self.log_level)

        self.register_command(None, "cd", self.change_dir)
        self.register_command(None, "pwd", self.print_dir)

    def bind_handler(self, svc_ref: ServiceReference[ShellCommandsProvider]) -> bool:
        """
        Called if a command service has been found.
        Registers the methods of this service.

        :param svc_ref: A reference to the found service
        :return: True if the commands have been registered
        """
        if svc_ref in self._bound_references:
            # Already bound service
            return False

        # Get the service
        handler = self._context.get_service(svc_ref)

        # Get its name space
        namespace = handler.get_namespace()
        commands: List[str] = []

        # Register all service methods directly
        for command, method in handler.get_methods():
            self.register_command(namespace, command, method)
            commands.append(command)

        # Store the reference
        self._bound_references[svc_ref] = handler
        self._reference_commands[svc_ref] = (namespace, commands)
        return True

    def unbind_handler(self, svc_ref: ServiceReference[ShellCommandsProvider]) -> bool:
        """
        Called if a command service is gone.
        Unregisters its commands.

        :param svc_ref: A reference to the unbound service
        :return: True if the commands have been unregistered
        """
        if svc_ref not in self._bound_references:
            # Unknown reference
            return False

        # Unregister its commands
        namespace, commands = self._reference_commands[svc_ref]
        for command in commands:
            self.unregister(namespace, command)

        # Release the service
        self._context.unget_service(svc_ref)
        del self._bound_references[svc_ref]
        del self._reference_commands[svc_ref]
        return True

    @staticmethod
    def get_banner() -> str:
        """
        Returns the Shell banner
        """
        return "** Pelix Shell prompt **\n"

    def var_set(self, session: "ShellSession", **kwargs: Any) -> Any:
        """
        Sets the given variables or prints the current ones. "set answer=42"
        """
        if not kwargs:
            session.write_line(self._utils.make_table(("Name", "Value"), session.variables.items()))
        else:
            for name, value in kwargs.items():
                name = name.strip()
                session.set(name, value)
                session.write_line("{0}={1}", name, value)

    @Completion(BUNDLE)
    def bundle_details(self, session: "ShellSession", bundle_id: Union[int, str]) -> Any:
        """
        Prints the details of the bundle with the given ID or name
        """
        bundle = None

        try:
            # Convert the given ID into an integer
            bundle_id = int(bundle_id)
        except ValueError:
            # Not an integer, suppose it's a bundle name
            for bundle in self._context.get_bundles():
                if bundle.get_symbolic_name() == bundle_id:
                    break
            else:
                # Bundle not found
                bundle = None
        else:
            # Integer ID: direct access
            try:
                bundle = self._context.get_bundle(bundle_id)
            except constants.BundleException:
                pass

        if bundle is None:
            # No matching bundle
            session.write_line(f"Unknown bundle ID: {bundle_id}")
            return False

        lines = [
            f"ID......: {bundle.get_bundle_id()}",
            f"Name....: {bundle.get_symbolic_name()}",
            f"Version.: {bundle.get_version()}",
            f"State...: {self._utils.bundlestate_to_str(bundle.get_state())}",
            f"Location: {bundle.get_location()}",
            "Published services:",
        ]
        try:
            services = bundle.get_registered_services()
            if services:
                for svc_ref in services:
                    lines.append(f"\t{svc_ref}")
            else:
                lines.append("\tn/a")
        except constants.BundleException as ex:
            # Bundle in a invalid state
            lines.append(f"\tError: {ex}")

        lines.append("Services used by this bundle:")
        try:
            services = bundle.get_services_in_use()
            if services:
                for svc_ref in services:
                    lines.append(f"\t{svc_ref}")
            else:
                lines.append("\tn/a")
        except constants.BundleException as ex:
            # Bundle in a invalid state
            lines.append(f"\tError: {ex}")

        lines.append("")
        session.write("\n".join(lines))
        return None

    def bundles_list(self, session: "ShellSession", name: Optional[str] = None) -> Any:
        """
        Lists the bundles in the framework and their state. Possibility to
        filter on the bundle name.
        """
        # Head of the table
        headers = ("ID", "Name", "State", "Version")

        # Get the bundles
        bundles = self._context.get_bundles()

        # The framework is not in the result of get_bundles()
        bundles.insert(0, self._context.get_framework())

        if name is not None:
            # Filter the list
            bundles = [bundle for bundle in bundles if name in bundle.get_symbolic_name()]

        # Make the entries
        lines = [
            [
                str(entry)
                for entry in (
                    bundle.get_bundle_id(),
                    bundle.get_symbolic_name(),
                    self._utils.bundlestate_to_str(bundle.get_state()),
                    bundle.get_version(),
                )
            ]
            for bundle in bundles
        ]

        # Print'em all
        session.write(self._utils.make_table(headers, lines))

        if name is None:
            session.write_line(f"{len(lines)} bundles installed")
        else:
            session.write_line(f"{len(lines)} filtered bundles")

    @Completion(SERVICE)
    def service_details(self, session: "ShellSession", service_id: str) -> Any:
        """
        Prints the details of the service with the given ID
        """
        svc_ref: Optional[ServiceReference[Any]] = self._context.get_service_reference(
            None, f"({constants.SERVICE_ID}={service_id})"
        )
        if svc_ref is None:
            session.write_line(f"Service not found: {service_id}")
            return False

        lines = [
            f"ID............: {svc_ref.get_property(constants.SERVICE_ID)}",
            f"Rank..........: {svc_ref.get_property(constants.SERVICE_RANKING)}",
            f"Specifications: {svc_ref.get_property(constants.OBJECTCLASS)}",
            f"Bundle........: {svc_ref.get_bundle()}",
            "Properties....:",
        ]
        for key, value in sorted(svc_ref.get_properties().items()):
            lines.append(f"\t{key} = {value}")

        lines.append("Bundles using this service:")
        for bundle in svc_ref.get_using_bundles():
            lines.append(f"\t{bundle}")

        lines.append("")
        session.write("\n".join(lines))
        return None

    def services_list(self, session: "ShellSession", specification: Optional[str] = None) -> Any:
        """
        Lists the services in the framework. Possibility to filter on an exact
        specification.
        """
        # Head of the table
        headers = ("ID", "Specifications", "Bundle", "Ranking")

        # Lines
        references: List[ServiceReference[Any]] = (
            self._context.get_all_service_references(specification, None) or []
        )

        # Construct the list of services
        lines = [
            [
                str(entry)
                for entry in (
                    ref.get_property(constants.SERVICE_ID),
                    ref.get_property(constants.OBJECTCLASS),
                    ref.get_bundle(),
                    ref.get_property(constants.SERVICE_RANKING),
                )
            ]
            for ref in references
        ]

        if not lines and specification:
            # No matching service found
            session.write_line(f"No service provides '{specification}'")
            return False

        # Print'em all
        session.write(self._utils.make_table(headers, lines))
        session.write_line(f"{len(lines)} services registered")
        return None

    def properties_list(self, session: "ShellSession") -> Any:
        """
        Lists the properties of the framework
        """
        # Get the framework
        framework = self._context.get_framework()

        # Head of the table
        headers = ("Property Name", "Value")

        # Lines
        lines = [item for item in framework.get_properties().items()]

        # Sort lines
        lines.sort()

        # Print the table
        session.write(self._utils.make_table(headers, lines))

    def property_value(self, session: "ShellSession", name: str) -> Any:
        """
        Prints the value of the given property, looking into
        framework properties then environment variables.
        """
        value = self._context.get_property(name)
        if value is None:
            # Avoid printing "None"
            value = ""

        session.write_line(str(value))

    def environment_list(self, session: "ShellSession") -> Any:
        """
        Lists the framework process environment variables
        """
        # Head of the table
        headers = ("Environment Variable", "Value")

        # Lines
        lines = [item for item in os.environ.items()]

        # Sort lines
        lines.sort()

        # Print the table
        session.write(self._utils.make_table(headers, lines))

    @staticmethod
    def environment_value(session: "ShellSession", name: str) -> Any:
        """
        Prints the value of the given environment variable
        """
        session.write_line(os.getenv(name))

    @staticmethod
    def threads_list(session: "ShellSession", max_depth: Optional[int] = 1) -> Any:
        """
        Lists the active threads and their current code line
        """
        # Normalize maximum depth
        try:
            max_depth = int(max_depth or 0)
            if max_depth < 1:
                max_depth = None
        except (ValueError, TypeError):
            max_depth = None

        # pylint: disable=W0212
        try:
            # Extract frames
            frames = sys._current_frames()

            # Get the thread ID -> Thread mapping
            names = getattr(threading, "_active").copy()
        except AttributeError:
            session.write_line("sys._current_frames() is not available.")
            return

        # Sort by thread ID
        thread_ids = sorted(frames.keys())
        lines = []
        for thread_id in thread_ids:
            # Get the corresponding stack
            stack = frames[thread_id]

            # Try to get the thread name
            try:
                name = names[thread_id].name
            except KeyError:
                name = "<unknown>"

            # Construct the code position
            lines.append(f"Thread ID: {thread_id} - Name: {name}")
            lines.append("Stack Trace:")

            trace_lines = []
            depth = 0
            frame: Optional[FrameType] = stack
            while frame is not None and (max_depth is None or depth < max_depth):
                # Store the line information
                trace_lines.append(format_frame_info(frame))

                # Previous frame...
                frame = frame.f_back
                depth += 1

            # Reverse the lines
            trace_lines.reverse()

            # Add them to the printed lines
            lines.extend(trace_lines)
            lines.append("")

        lines.append("")

        # Sort the lines
        session.write("\n".join(lines))

    @staticmethod
    def thread_details(
        session: "ShellSession", thread_id: Union[str, int], max_depth: Optional[int] = 0
    ) -> Any:
        """
        Prints details about the thread with the given ID (not its name)
        """
        # Normalize maximum depth
        try:
            max_depth = int(max_depth or 0)
            if max_depth < 1:
                max_depth = None
        except (ValueError, TypeError):
            max_depth = None

        # pylint: disable=W0212
        try:
            # Get the stack
            thread_id = int(thread_id)
            stack = sys._current_frames()[thread_id]
        except KeyError:
            session.write_line(f"Unknown thread ID: {thread_id}")
        except ValueError:
            session.write_line(f"Invalid thread ID: {thread_id}")
        except AttributeError:
            session.write_line("sys._current_frames() is not available.")
        else:
            # Get the name
            try:
                name = getattr(threading, "_active")[thread_id].name
            except KeyError:
                name = "<unknown>"

            lines = [
                f"Thread ID: {thread_id} - Name: {name}",
                "Stack trace:",
            ]

            trace_lines = []
            depth = 0
            frame: Optional[FrameType] = stack
            while frame is not None and (max_depth is None or depth < max_depth):
                # Store the line information
                trace_lines.append(format_frame_info(frame))

                # Previous frame...
                frame = frame.f_back
                depth += 1

            # Reverse the lines
            trace_lines.reverse()

            # Add them to the printed lines
            lines.extend(trace_lines)

            lines.append("")
            session.write("\n".join(lines))

    @staticmethod
    def log_level(session: "ShellSession", level: Optional[str] = None, name: Optional[str] = None) -> None:
        """
        Prints/Changes log level
        """
        # Get the logger
        logger = logging.getLogger(name)

        # Normalize the name
        if not name:
            name = "Root"

        if not level:
            # Level not given: print the logger level
            session.write_line(
                "{0} log level: {1} (real: {2})",
                name,
                logging.getLevelName(logger.getEffectiveLevel()),
                logging.getLevelName(logger.level),
            )
        else:
            # Set the logger level
            try:
                logger.setLevel(level.upper())
                session.write_line("New level for {0}: {1}", name, level)
            except ValueError:
                session.write_line("Invalid log level: {0}", level)

    def change_dir(self, session: "ShellSession", path: str) -> None:
        """
        Changes the working directory
        """
        if path == "-":
            # Previous directory
            path = self._previous_path or "."

        try:
            previous = os.getcwd()
            os.chdir(path)
        except IOError as ex:
            # Can't change directory
            session.write_line(f"Error changing directory: {ex}")
        else:
            # Store previous path
            self._previous_path = previous
            session.write_line(os.getcwd())

    @staticmethod
    def print_dir(session: "ShellSession") -> str:
        """
        Prints the current working directory
        """
        pwd = os.getcwd()
        session.write_line(pwd)
        return pwd

    def __get_bundle(self, session: "ShellSession", bundle_id: Union[int, str]) -> Optional[Bundle]:
        """
        Retrieves the Bundle object with the given bundle ID. Writes errors
        through the I/O handler if any.

        :param session: I/O Handler
        :param bundle_id: String or integer bundle ID
        :return: The Bundle object matching the given ID, None if not found
        """
        assert self._context is not None

        try:
            bundle_id = int(bundle_id)
            return self._context.get_bundle(bundle_id)
        except (TypeError, ValueError):
            session.write_line(f"Invalid bundle ID: {bundle_id}")
        except constants.BundleException:
            session.write_line(f"Unknown bundle: {bundle_id}")
        return None

    @Completion(BUNDLE, multiple=True)
    def start(
        self, session: "ShellSession", bundle_id: Union[int, str], *bundles_ids: Union[int, str]
    ) -> Any:
        """
        Starts the bundles with the given IDs. Stops on first failure.
        """
        for bid in (bundle_id,) + bundles_ids:
            try:
                # Got an int => it's a bundle ID
                bid = int(bid)
            except ValueError:
                # Got something else, we will try to install it first
                bid = self.install(session, str(bid))

            bundle = self.__get_bundle(session, bid)
            if bundle is not None:
                session.write_line(
                    "Starting bundle {0} ({1})...",
                    bid,
                    bundle.get_symbolic_name(),
                )
                bundle.start()
            else:
                return False

        return None

    @Completion(BUNDLE, multiple=True)
    def stop(self, session: "ShellSession", bundle_id: Union[int, str], *bundles_ids: Union[int, str]) -> Any:
        """
        Stops the bundles with the given IDs. Stops on first failure.
        """
        for bid in (bundle_id,) + bundles_ids:
            bundle = self.__get_bundle(session, bid)
            if bundle is not None:
                session.write_line(
                    "Stopping bundle {0} ({1})...",
                    bid,
                    bundle.get_symbolic_name(),
                )
                bundle.stop()
            else:
                return False

        return None

    @Completion(BUNDLE, multiple=True)
    def update(
        self, session: "ShellSession", bundle_id: Union[int, str], *bundles_ids: Union[int, str]
    ) -> Any:
        """
        Updates the bundles with the given IDs. Stops on first failure.
        """
        for bid in (bundle_id,) + bundles_ids:
            bundle = self.__get_bundle(session, bid)
            if bundle is not None:
                session.write_line(
                    "Updating bundle {0} ({1})...",
                    bid,
                    bundle.get_symbolic_name(),
                )
                bundle.update()
            else:
                return False

        return None

    def install(self, session: "ShellSession", module_name: str) -> int:
        """
        Installs the bundle with the given module name
        """
        bundle = self._context.install_bundle(module_name)
        session.write_line("Bundle ID: {0}", bundle.get_bundle_id())
        return bundle.get_bundle_id()

    @Completion(BUNDLE, multiple=True)
    def uninstall(
        self, session: "ShellSession", bundle_id: Union[int, str], *bundles_ids: Union[int, str]
    ) -> Any:
        """
        Uninstalls the bundles with the given IDs. Stops on first failure.
        """
        for bid in (bundle_id,) + bundles_ids:
            bundle = self.__get_bundle(session, bid)
            if bundle is not None:
                session.write_line(
                    "Uninstalling bundle {0} ({1})...",
                    bid,
                    bundle.get_symbolic_name(),
                )
                bundle.uninstall()
            else:
                return False

        return None


# ------------------------------------------------------------------------------


@constants.BundleActivator
class Activator(constants.ActivatorProto, ServiceListener):
    """
    Activator class for Pelix
    """

    def __init__(self) -> None:
        """
        Sets up the activator
        """
        self._shell: Optional[_ShellService] = None
        self._shell_reg: Optional[ServiceRegistration[ShellService]] = None
        self._utils_reg: Optional[ServiceRegistration[ShellUtils]] = None
        self._logger = logging.getLogger(__name__)

    def service_changed(self, event: ServiceEvent[ShellCommandsProvider]) -> None:
        """
        Called when a command provider service event occurred
        """
        assert self._shell is not None

        kind = event.get_kind()
        reference = event.get_service_reference()

        if kind in (ServiceEvent.REGISTERED, ServiceEvent.MODIFIED):
            # New or modified service
            self._shell.bind_handler(reference)
        else:
            # Service gone or not matching anymore
            self._shell.unbind_handler(reference)

    def start(self, context: BundleContext) -> None:
        """
        Bundle starting

        :param context: The bundle context
        """
        try:
            # Prepare the shell utility service
            utils = _ShellUtils()
            self._shell = _ShellService(context, utils)
            self._shell_reg = context.register_service(ShellService, self._shell, {})
            self._utils_reg = context.register_service(ShellUtils, utils, {})

            # Register the service listener
            context.add_service_listener(self, None, ShellCommandsProvider)

            # Register existing command services
            refs = context.get_all_service_references(ShellCommandsProvider)
            if refs is not None:
                for ref in refs:
                    self._shell.bind_handler(ref)

            self._logger.info("Shell services registered")

        except constants.BundleException as ex:
            self._logger.exception("Error registering the shell service: %s", ex)

    def stop(self, context: BundleContext) -> None:
        """
        Bundle stopping

        :param context: The bundle context
        """
        # Unregister the service listener
        context.remove_service_listener(self)

        # Unregister the services
        if self._shell_reg is not None:
            self._shell_reg.unregister()
            self._shell_reg = None

        if self._utils_reg is not None:
            self._utils_reg.unregister()
            self._utils_reg = None

        self._shell = None
        self._logger.info("Shell services unregistered")
