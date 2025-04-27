#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Common parser for shell implementations

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0
:status: Alpha

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

import collections
import inspect
import logging
import shlex
import string
import sys
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, cast

import pelix.shell.beans as beans
from pelix.shell import ShellCommandMethod
from pelix.shell.completion import ATTR_COMPLETERS, CompletionInfo
from pelix.utilities import get_method_arguments, to_str

if TYPE_CHECKING:
    from pelix.framework import Framework

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

DEFAULT_NAMESPACE = "default"
""" Default command name space: default """

# ------------------------------------------------------------------------------


def _find_assignment(arg_token: str) -> int:
    """
    Find the first non-escaped assignment in the given argument token.
    Returns -1 if no assignment was found.

    :param arg_token: The argument token
    :return: The index of the first assignment, or -1
    """
    idx = arg_token.find("=")
    while idx != -1:
        if idx != 0 and arg_token[idx - 1] != "\\":
            # No escape character
            return idx

        idx = arg_token.find("=", idx + 1)

    # No assignment found
    return -1


class _ArgTemplate(string.Template):
    """
    Argument string template class
    """

    idpattern = r"[_a-z\?][_a-z0-9\.]*"


def _make_args(
    args_list: List[str], session: beans.ShellSession, fw_props: Dict[str, Any]
) -> Tuple[List[str], Dict[str, str]]:
    """
    Converts the given list of arguments into a list (args) and a
    dictionary (kwargs).
    All arguments with an assignment are put into kwargs, others in args.

    :param args_list: The list of arguments to be treated
    :param session: The current shell session
    :return: The (arg_token, kwargs) tuple.
    """
    args = []
    kwargs = {}

    for arg_token in args_list:
        idx = _find_assignment(arg_token)
        if idx != -1:
            # Assignment
            key = arg_token[:idx]
            value = arg_token[idx + 1 :]
            kwargs[key] = value
        else:
            # Direct argument
            args.append(arg_token)

    # Prepare the dictionary of variables
    variables: Dict[str, Any] = collections.defaultdict(str)
    variables.update(fw_props)
    variables.update(session.variables)

    # Replace variables
    args = [_ArgTemplate(arg).safe_substitute(variables) for arg in args]
    kwargs = {key: _ArgTemplate(value).safe_substitute(variables) for key, value in kwargs.items()}
    return args, kwargs


def _split_ns_command(cmd_token: str) -> Tuple[str, str]:
    """
    Extracts the name space and the command name of the given command token.

    :param cmd_token: The command token
    :return: The extracted (name space, command) tuple
    """
    namespace = None
    cmd_split = cmd_token.split(".", 1)
    if len(cmd_split) == 1:
        # No name space given
        command = cmd_split[0]
    else:
        # Got a name space and a command
        namespace = cmd_split[0]
        command = cmd_split[1]

    if not namespace:
        # No name space given: given an empty one
        namespace = ""

    # Use lower case values only
    return namespace.lower(), command.lower()


# ------------------------------------------------------------------------------


class Shell:
    """
    A simple shell, based on shlex.

    Allows the use of name spaces.
    """

    def __init__(self, framework: "Framework", logname: Optional[str] = None) -> None:
        """
        Sets up members

        :param framework: The Pelix Framework instance
        :param logname: Custom name for the shell logger
        """
        self._commands: Dict[str, Dict[str, ShellCommandMethod]] = {}
        self._framework = framework
        self._logger = logging.getLogger(logname or __name__)

        # Register the help command
        self.register_command(None, "help", self.print_help)
        self.register_command(None, "?", self.print_help)

        # Basic commands
        self.register_command(None, "echo", self.echo)
        self.register_command(None, "quit", self.quit)
        self.register_command(None, "exit", self.quit)

        # Variable commands
        self.register_command(None, "set", self.var_set)
        self.register_command(None, "unset", self.var_unset)

        # File commands
        self.register_command(None, "run", self.run_file)

    @staticmethod
    def get_banner() -> str:
        """
        Returns the Shell banner
        """
        return "** Shell prompt **\n"

    @staticmethod
    def get_ps1() -> str:
        """
        Returns the PS1, the basic shell prompt
        """
        return "$ "

    def register_command(self, namespace: Optional[str], command: str, method: ShellCommandMethod) -> bool:
        """
        Registers the given command to the shell.

        The namespace can be None, empty or "default"

        :param namespace: The command name space.
        :param command: The shell name of the command
        :param method: The method to call
        :return: True if the method has been registered, False if it was already known or invalid
        """
        if method is None:
            self._logger.error("No method given for %s.%s", namespace, command)
            return False

        # Store everything in lower case
        namespace = (namespace or "").strip().lower()
        command = (command or "").strip().lower()

        if not namespace:
            namespace = DEFAULT_NAMESPACE

        if not command:
            self._logger.error("No command name given")
            return False

        if namespace not in self._commands:
            space = self._commands[namespace] = cast(Dict[str, Callable[..., Any]], {})
        else:
            space = self._commands[namespace]

        if command in space:
            self._logger.error("Command already registered: %s.%s", namespace, command)
            return False

        space[command] = method
        return True

    def get_command_completers(self, namespace: str, command: str) -> Optional[CompletionInfo]:
        """
        Returns the completer method associated to the given command, or None

        :param namespace: The command name space.
        :param command: The shell name of the command
        :return: A CompletionConfiguration object
        :raise KeyError: Unknown command or name space
        """
        # Find the method (can raise a KeyError)
        method = self._commands[namespace][command]

        # Return the completer, if any
        return getattr(method, ATTR_COMPLETERS, None)

    def unregister(self, namespace: str, command: Optional[str] = None) -> bool:
        """
        Unregisters the given command. If command is None, the whole name space
        is unregistered.

        :param namespace: The command name space.
        :param command: The shell name of the command, or None
        :return: True if the command was known, else False
        """
        if not namespace:
            namespace = DEFAULT_NAMESPACE

        namespace = namespace.strip().lower()
        if namespace not in self._commands:
            self._logger.warning("Unknown name space: %s", namespace)
            return False

        if command is not None:
            # Remove the command
            command = command.strip().lower()
            if command not in self._commands[namespace]:
                self._logger.warning("Unknown command: %s.%s", namespace, command)
                return False

            del self._commands[namespace][command]

            # Remove the name space if necessary
            if not self._commands[namespace]:
                del self._commands[namespace]
        else:
            # Remove the whole name space
            del self._commands[namespace]

        return True

    def __find_command_ns(self, command: str) -> List[str]:
        """
        Returns the name spaces where the given command named is registered.
        If the command exists in the default name space, the returned list will
        only contain the default name space.
        Returns an empty list of the command is unknown

        :param command: A command name
        :return: A list of name spaces
        """
        # Look for the spaces where the command name appears
        namespaces: List[str] = []
        for namespace, commands in self._commands.items():
            if command in commands:
                namespaces.append(namespace)

        # Sort name spaces
        namespaces.sort()

        # Default name space must always come first
        try:
            namespaces.remove(DEFAULT_NAMESPACE)
            namespaces.insert(0, DEFAULT_NAMESPACE)
        except ValueError:
            # Default name space wasn't present
            pass

        return namespaces

    def get_namespaces(self) -> List[str]:
        """
        Retrieves the list of known name spaces (without the default one)

        :return: The list of known name spaces
        """
        namespaces = list(self._commands.keys())
        namespaces.remove(DEFAULT_NAMESPACE)
        namespaces.sort()
        return namespaces

    def get_commands(self, namespace: Optional[str]) -> List[str]:
        """
        Retrieves the commands of the given name space. If *namespace* is None
        or empty, it retrieves the commands of the default name space

        :param namespace: The commands name space
        :return: A list of commands names
        """
        if not namespace:
            # Default name space:
            namespace = DEFAULT_NAMESPACE

        try:
            namespace.strip().lower()
            commands = list(self._commands[namespace].keys())
            commands.sort()
            return commands
        except KeyError:
            # Unknown name space
            return []

    def get_ns_commands(self, cmd_name: str) -> List[Tuple[str, str]]:
        """
        Retrieves the possible name spaces and commands associated to the given
        command name.

        :param cmd_name: The given command name
        :return: A list of 2-tuples (name space, command)
        :raise ValueError: Unknown command name
        """
        namespace, command = _split_ns_command(cmd_name)
        if not namespace:
            # Name space not given, look for the commands
            spaces = self.__find_command_ns(command)
            if not spaces:
                # Unknown command
                raise ValueError(f"Unknown command {command}")

            # Return a sorted list of tuples
            return sorted((namespace, command) for namespace in spaces)

        # Single match
        return [(namespace, command)]

    def get_ns_command(self, cmd_name: str) -> Tuple[str, str]:
        """
        Retrieves the name space and the command associated to the given
        command name.

        :param cmd_name: The given command name
        :return: A 2-tuple (name space, command)
        :raise ValueError: Unknown command name
        """
        namespace, command = _split_ns_command(cmd_name)
        if not namespace:
            # Name space not given, look for the command
            spaces = self.__find_command_ns(command)
            if not spaces:
                # Unknown command
                raise ValueError(f"Unknown command {command}")

            if len(spaces) > 1:
                # Multiple possibilities
                if spaces[0] == DEFAULT_NAMESPACE:
                    # Default name space has priority
                    namespace = DEFAULT_NAMESPACE
                else:
                    # Ambiguous name
                    raise ValueError(
                        f"Multiple name spaces for command '{command}': {', '.join(sorted(spaces))}"
                    )
            else:
                # Use the found name space
                namespace = spaces[0]

        # Command found
        return namespace, command

    def execute(self, cmdline: str, session: Optional[beans.ShellSession] = None) -> bool:
        """
        Executes the command corresponding to the given line

        :param cmdline: Command line to parse
        :param session: Current shell session
        :return: True if command succeeded, else False
        """
        if session is None:
            # Default session
            session = beans.ShellSession(beans.IOHandler(sys.stdin, sys.stdout), {})

        assert isinstance(session, beans.ShellSession)

        # Split the command line
        if not cmdline:
            return False

        # Convert the line into a string
        cmdline = to_str(cmdline)

        try:
            line_split = shlex.split(cmdline, True, True)
        except ValueError as ex:
            session.write_line(f"Error reading line: {ex}")
            return False

        if not line_split:
            return False

        try:
            # Extract command information
            namespace, command = self.get_ns_command(line_split[0])
        except ValueError as ex:
            # Unknown command
            session.write_line(str(ex))
            return False

        # Get the content of the name space
        space = self._commands.get(namespace, None)
        if not space:
            session.write_line(
                f"Unknown name space {namespace}",
            )
            return False

        # Get the method object
        method = space.get(command, None)
        if method is None:
            session.write_line(f"Unknown command: {namespace}.{command}")
            return False

        # Make arguments and keyword arguments
        args, kwargs = _make_args(line_split[1:], session, self._framework.get_properties())
        try:
            # Execute it
            result = method(session, *args, **kwargs)

            # Store the result as $?
            if result is not None:
                session.set(beans.RESULT_VAR_NAME, result)

            # 0, None are considered as success, so don't use not nor bool
            return result is not False
        except TypeError as ex:
            # Invalid arguments...
            self._logger.error("Error calling %s.%s: %s", namespace, command, ex)
            session.write_line(f"Invalid method call: {ex}")
            self.__print_namespace_help(session, namespace, command)
            return False
        except Exception as ex:
            # Error
            self._logger.exception("Error calling %s.%s: %s", namespace, command, ex)
            session.write_line(f"{type(ex).__name__}: {ex}")
            return False
        finally:
            # Try to flush in any case
            try:
                session.flush()
            except IOError:
                pass

    @staticmethod
    def __extract_help(method: Callable[..., Any]) -> Tuple[str, str]:
        """
        Formats the help string for the given method

        :param method: The method to document
        :return: A tuple: (arguments list, documentation line)
        """
        if method is None:
            return "", "(No associated method)"

        # Get the arguments
        arg_spec = get_method_arguments(method)

        # Ignore the session argument
        start_arg = 1

        # Compute the number of arguments with default value
        if arg_spec.defaults is not None:
            nb_optional = len(arg_spec.defaults)

            # Let the mandatory arguments as they are
            args = [f"<{arg}>" for arg in arg_spec.args[start_arg:-nb_optional]]

            # Add the other arguments
            for name, value in zip(arg_spec.args[-nb_optional:], arg_spec.defaults[-nb_optional:]):
                if value is not None:
                    args.append(f"[<{name}>={value}]")
                else:
                    args.append(f"[<{name}>]")
        else:
            # All arguments are mandatory
            args = [f"<{arg}>" for arg in arg_spec.args[start_arg:]]

        # Extra arguments
        if arg_spec.keywords:
            args.append("[<property=value> ...]")

        if arg_spec.varargs:
            args.append(f"[<{arg_spec.varargs} ...>]")

        # Get the documentation string
        doc = inspect.getdoc(method) or "(Documentation missing)"
        return " ".join(args), " ".join(doc.split())

    def __print_command_help(self, session: beans.ShellSession, namespace: str, cmd_name: str) -> None:
        """
        Prints the documentation of the given command

        :param session: Session handler
        :param namespace: Name space of the command
        :param cmd_name: Name of the command
        """
        # Extract documentation
        args, doc = self.__extract_help(self._commands[namespace][cmd_name])

        # Print the command name, and its arguments
        if args:
            session.write_line("- {0} {1}", cmd_name, args)
        else:
            session.write_line("- {0}", cmd_name)

        # Print the documentation line
        session.write_line("\t\t{0}", doc)

    def __print_namespace_help(
        self, session: beans.ShellSession, namespace: str, cmd_name: Optional[str] = None
    ) -> None:
        """
        Prints the documentation of all the commands in the given name space,
        or only of the given command

        :param session: Session Handler
        :param namespace: Name space of the command
        :param cmd_name: Name of the command to show, None to show them all
        """
        session.write_line(f"=== Name space '{namespace}' ===")

        # Get all commands in this name space
        if cmd_name is None:
            names = list(self._commands[namespace])
            names.sort()
        else:
            names = [cmd_name]

        first_cmd = True
        for command in names:
            if not first_cmd:
                # Print an empty line
                session.write_line("\n")

            self.__print_command_help(session, namespace, command)
            first_cmd = False

    def print_help(self, session: beans.ShellSession, command: Optional[str] = None) -> Any:
        """
        Prints the available methods and their documentation, or the
        documentation of the given command.
        """
        if command:
            # Single command mode
            if command in self._commands:
                # Argument is a name space
                self.__print_namespace_help(session, command)
                was_namespace = True
            else:
                was_namespace = False

            # Also print the name of matching commands
            try:
                # Extract command name space and name
                possibilities = self.get_ns_commands(command)
            except ValueError as ex:
                # Unknown command
                if not was_namespace:
                    # ... and no name space were matching either -> error
                    session.write_line(str(ex))
                    return False
            else:
                # Print the help of the found command
                if was_namespace:
                    # Give some space
                    session.write_line("\n\n")

                for namespace, cmd_name in possibilities:
                    self.__print_namespace_help(session, namespace, cmd_name)
        else:
            # Get all name spaces
            namespaces = list(self._commands.keys())
            namespaces.remove(DEFAULT_NAMESPACE)
            namespaces.sort()
            namespaces.insert(0, DEFAULT_NAMESPACE)

            first_ns = True
            for namespace in namespaces:
                if not first_ns:
                    # Add empty lines
                    session.write_line("\n\n")

                # Print the help of all commands
                self.__print_namespace_help(session, namespace)
                first_ns = False

        return None

    @staticmethod
    def echo(session: beans.ShellSession, *words: str) -> None:
        """
        Echoes the given words
        """
        session.write_line(" ".join(words))

    @staticmethod
    def quit(session: beans.ShellSession) -> None:
        """
        Stops the current shell session (raises a KeyboardInterrupt exception)
        """
        session.write_line("Raising KeyboardInterrupt to stop main thread")
        raise KeyboardInterrupt()

    def var_set(self, session: beans.ShellSession, **kwargs: Any) -> None:
        """
        Sets the given variables or prints the current ones. "set answer=42"
        """
        if not kwargs:
            for name, value in session.variables.items():
                session.write_line(f"{name}={value}")
        else:
            for name, value in kwargs.items():
                name = name.strip()
                session.set(name, value)
                session.write_line(f"{name}={value}")

    @staticmethod
    def var_unset(session: beans.ShellSession, name: str) -> Any:
        """
        Unsets the given variable
        """
        name = name.strip()
        try:
            session.unset(name)
            session.write_line(f"Variable {name} unset.")
        except KeyError:
            session.write_line(f"Unknown variable: {name}")
            return False

        return None

    def run_file(self, session: beans.ShellSession, filename: str) -> Any:
        """
        Runs the given "script" file
        """
        try:
            with open(filename, "r", encoding="utf8") as filep:
                for lineno, line in enumerate(filep):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        # Ignore comments and empty lines
                        continue

                    # Print out the executed line
                    session.write_line("[{0:02d}] >> {1}", lineno, line)

                    # Execute the line
                    if not self.execute(line, session):
                        session.write_line("Command at line {0} failed. Abandon.", lineno + 1)
                        return False

                session.write_line("Script execution succeeded")
        except IOError as ex:
            session.write_line("Error reading file {0}: {1}", filename, ex)
            return False

        return None
