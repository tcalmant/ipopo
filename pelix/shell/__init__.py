#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix shell package

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


from typing import TYPE_CHECKING, Any, Callable, Iterable, List, Optional, Protocol, Set, Tuple

from pelix.constants import Specification

if TYPE_CHECKING:
    from pelix.shell.beans import ShellSession
    from pelix.shell.completion import CompletionInfo


# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

SERVICE_SHELL = "pelix.shell"
"""
Core shell service:

* register_command(ns, command, method): Registers a command in the given name
  space, executing the given method
* unregister(namespace, command): If command is given, unregisters it, else
  unregisters the whole given namespace
* execute(cmdline, stdin, stdout): Executes the given command line with the
  given input and output streams
"""

SERVICE_SHELL_COMMAND = "pelix.shell.command"
"""
Shell commands service, for auto-registration (white board pattern).

* get_namespace(): returns the name space of the handler
* get_methods(): returns a command name → method dictionary
"""

SERVICE_SHELL_UTILS = "pelix.shell.utilities"
"""
Shell utility service:

* make_table(headers, lines): to make ASCII arrays
* bundlestate_to_str(state): to get the string representation of a bundle state
"""

SERVICE_SHELL_REMOTE = "pelix.shell.remote"
"""
Remote shell service

* get_access(): returns the (host, port) tuple where the remote shell is waiting clients.
"""

SERVICE_SHELL_REPORT = "pelix.shell.report"
"""
Report command service: gives access to the report methods for a future reuse

* get_levels():  Returns a copy of the dictionary of levels. The key is the
  name of the report level, the value is the tuple of methods to call for that
  level. Multiple levels can call the same method. The methods take no argument
  and return a dictionary.
* to_json(dict): Converts a dictionary to JSON, replacing inconvertible values
  to their string representation.
"""

ShellCommandMethod = Callable[..., Any]


@Specification(SERVICE_SHELL)
class ShellService(Protocol):
    """
    Shell service specification
    """

    def get_banner(self) -> str:
        """
        Returns the shell banner
        """
        ...

    def get_ps1(self) -> str:
        """
        Returns the prompt of the shell
        """
        ...

    def get_namespaces(self) -> List[str]:
        """
        Retrieves the list of known name spaces (without the default one)

        :return: The list of known name spaces
        """
        ...

    def get_commands(self, namespace: Optional[str]) -> List[str]:
        """
        Retrieves the commands of the given name space. If *namespace* is None
        or empty, it retrieves the commands of the default name space

        :param namespace: The commands name space
        :return: A list of commands names
        """
        ...

    def get_ns_commands(self, cmd_name: str) -> List[Tuple[str, str]]:
        """
        Retrieves the possible name spaces and commands associated to the given
        command name.

        :param cmd_name: The given command name
        :return: A list of 2-tuples (name space, command)
        :raise ValueError: Unknown command name
        """
        ...

    def get_ns_command(self, cmd_name: str) -> Tuple[str, str]:
        """
        Retrieves the name space and the command associated to the given
        command name.

        :param cmd_name: The given command name
        :return: A 2-tuple (name space, command)
        :raise ValueError: Unknown command name
        """
        ...

    def execute(self, cmdline: str, session: Optional["ShellSession"] = None) -> bool:
        """
        Executes the command corresponding to the given line

        :param cmdline: Command line to parse
        :param session: Current shell session
        :return: True if command succeeded, else False
        """
        ...

    def get_command_completers(self, namespace: str, command: str) -> Optional["CompletionInfo"]:
        """
        Returns the completer method associated to the given command, or None

        :param namespace: The command name space.
        :param command: The shell name of the command
        :return: A CompletionConfiguration object
        :raise KeyError: Unknown command or name space
        """
        ...

    def register_command(self, namespace: Optional[str], command: str, method: ShellCommandMethod) -> bool:
        """
        Registers the given command to the shell.

        The namespace can be None, empty or "default"

        :param namespace: The command name space.
        :param command: The shell name of the command
        :param method: The method to call
        :return: True if the method has been registered, False if it was already known or invalid
        """
        ...

    def unregister(self, namespace: str, command: Optional[str] = None) -> bool:
        """
        Unregisters the given command. If command is None, the whole name space
        is unregistered.

        :param namespace: The command name space.
        :param command: The shell name of the command, or None
        :return: True if the command was known, else False
        """
        ...


@Specification(SERVICE_SHELL_UTILS)
class ShellUtils(Protocol):
    """
    Specification of the shell utility service
    """

    @staticmethod
    def bundlestate_to_str(state: int) -> str:
        """
        Converts a bundle state integer to a string
        """
        ...

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
        ...


@Specification(SERVICE_SHELL_COMMAND)
class ShellCommandsProvider(Protocol):
    """
    Specification of a provider of shell commands
    """

    def get_namespace(self) -> str:
        """
        Retrieves the name space of this command handler
        """
        ...

    def get_methods(self) -> List[Tuple[str, ShellCommandMethod]]:
        """
        Retrieves the list of tuples (command, method) for this command handler
        """
        ...


@Specification(SERVICE_SHELL_REPORT)
class ShellReport(Protocol):
    """
    Specification of the shell report service
    """

    def get_levels(self) -> Set[str]:
        """
        Returns the available levels of reports

        :return: The list of report levels
        """
        ...


@Specification(SERVICE_SHELL_REMOTE)
class RemoteShell(Protocol):
    """
    Specification of the remote shell service
    """

    def get_access(self) -> Tuple[Optional[str], Optional[int]]:
        """
        Returns the real access to this remote shell.
        Can raise an exception or return default values if not ready.

        :return: A (host, port) tuple
        """
        ...

    def get_encoding(self) -> str:
        """
        Returns the stream encoding using in the transport
        """
        ...

    def get_banner(self) -> str:
        """
        Retrieves the remote shell banner
        """
        ...

    def get_ps1(self) -> str:
        """
        Returns the remote shell prompt string
        """
        ...


# ------------------------------------------------------------------------------
# Temporary constants, for compatibility with previous shell developments

SHELL_SERVICE_SPEC = SERVICE_SHELL
""" Compatibility constant """

SHELL_COMMAND_SPEC = SERVICE_SHELL_COMMAND
""" Compatibility constant """

SHELL_UTILS_SERVICE_SPEC = SERVICE_SHELL_UTILS
""" Compatibility constant """

REMOTE_SHELL_SPEC = SERVICE_SHELL_REMOTE
""" Compatibility constant """

# ------------------------------------------------------------------------------

FACTORY_REMOTE_SHELL = "ipopo-remote-shell-factory"
""" Name of remote shell component factory """

FACTORY_XMPP_SHELL = "ipopo-xmpp-shell-factory"
""" Name of XMPP shell component factory """
