#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix shell bundle.

Provides the basic command parsing and execution support to make a Pelix shell.

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

# Shell constants
from pelix.shell import SERVICE_SHELL, SERVICE_SHELL_COMMAND, \
    SERVICE_SHELL_UTILS

# Pelix modules
from pelix.utilities import to_str, to_bytes
import pelix.constants as constants
import pelix.framework as pelix

# Standard library
import inspect
import linecache
import logging
import os
import shlex
import sys
import traceback
import threading

# Before Python 3, input() was raw_input()
if sys.version_info[0] < 3:
    safe_input = raw_input

else:
    safe_input = input

# ------------------------------------------------------------------------------

DEFAULT_NAMESPACE = "default"
""" Default command name space: default """

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


def _find_assignment(arg_token):
    """
    Find the first non-escaped assignment in the given argument token.
    Returns -1 if no assignment was found.

    :param arg_token: The argument token
    :return: The index of the first assignment, or -1
    """
    idx = arg_token.find('=')
    while idx != -1:
        if idx != 0:
            if arg_token[idx - 1] != '\\':
                # No escape character
                return idx

        idx = arg_token.find('=', idx + 1)

    # No assignment found
    return -1


def _make_args(args_list):
    """
    Converts the given list of arguments into a list (args) and a
    dictionary (kwargs).
    All arguments with an assignment are put into kwargs, others in args.

    :param args_list: The list of arguments to be treated
    :return: The (arg_token, kwargs) tuple.
    """
    args = []
    kwargs = {}

    for arg_token in args_list:
        idx = _find_assignment(arg_token)
        if idx != -1:
            # Assignment
            key = arg_token[:idx]
            value = arg_token[idx + 1:]
            kwargs[key] = value

        else:
            # Direct argument
            args.append(arg_token)

    return args, kwargs


def _split_ns_command(cmd_token):
    """
    Extracts the name space and the command name of the given command token.

    :param cmd_token: The command token
    :return: The extracted (name space, command) tuple
    """
    namespace = None
    cmd_split = cmd_token.split('.', 1)
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


class IOHandler(object):
    """
    Handles I/O operations between the command handler and the client
    It automatically converts the given data to bytes in Python 3.
    """
    def __init__(self, in_stream, out_stream, encoding='UTF-8'):
        """
        Sets up the printer

        :param in_stream: Input stream
        :param out_stream: Output stream
        :param encoding: Output encoding
        """
        self.input = in_stream
        self.output = out_stream
        self.encoding = encoding

        # Standard behavior
        self.flush = self.output.flush
        self.write = self.output.write

        # Specific behavior
        if sys.version_info[0] >= 3:
            if 'b' in getattr(out_stream, 'mode', ''):
                # Bytes conversion
                self.write = self._write_bytes
            else:
                # Strings accepted
                self.write = self._write_str

        # Very specific
        if in_stream is sys.stdin:
            # Warning: conflicts with the console
            self.prompt = safe_input
        else:
            self.prompt = self._prompt

    def _prompt(self, prompt=None):
        """
        Reads a line written by the user

        :param prompt: An optional prompt message
        :return: The read line, after a conversion to str
        """
        if prompt:
            # Print the prompt
            self.write(prompt)
            self.output.flush()

        # Read the line
        return to_str(self.input.readline())

    def _write_bytes(self, data):
        """
        Converts the given data then writes it

        :param data: Data to be written
        :return: The result of ``self.output.write()``
        """
        self.output.write(to_bytes(data, self.encoding))

    def _write_str(self, data):
        """
        Converts the given data then writes it

        :param data: Data to be written
        :return: The result of ``self.output.write()``
        """
        self.output.write(to_str(data, self.encoding))

    def write_line(self, line, *args, **kwargs):
        """
        Formats and writes a line to the output
        """
        if line is None:
            # Empty line
            self.write('\n')

        else:
            # Format the line, if arguments have been given
            if args or kwargs:
                line = line.format(*args, **kwargs)

            # Write it
            self.write(line)

            try:
                if line[-1] != '\n':
                    # Add the trailing new line
                    self.write('\n')

            except IndexError:
                # Got an empty string
                self.write('\n')

        self.flush()

    def write_line_no_feed(self, line, *args, **kwargs):
        """
        Formats and writes a line to the output
        """
        if line is None:
            # Empty line
            line = ""

        else:
            # Format the line, if arguments have been given
            if args or kwargs:
                line = line.format(*args, **kwargs)

            # Remove the trailing line feed
            if line[-1] == '\n':
                line = line[:-1]

        # Write it
        self.write(line)
        self.flush()

# ------------------------------------------------------------------------------


class ShellUtils(object):
    """
    Utility methods for the shell
    """
    def bundlestate_to_str(self, state):
        """
        Converts a bundle state integer to a string
        """
        states = {
            pelix.Bundle.INSTALLED: "INSTALLED",
            pelix.Bundle.ACTIVE: "ACTIVE",
            pelix.Bundle.RESOLVED: "RESOLVED",
            pelix.Bundle.STARTING: "STARTING",
            pelix.Bundle.STOPPING: "STOPPING",
            pelix.Bundle.UNINSTALLED: "UNINSTALLED"
        }

        return states.get(state, "Unknown state ({0})".format(state))

    def make_table(self, headers, lines, prefix=None):
        """
        Generates an ASCII table according to the given headers and lines

        :param headers: List of table headers (N-tuple)
        :param lines: List of table lines (N-tuples)
        :param prefix: Optional prefix for each line
        :return: The ASCII representation of the table
        :raise ValueError: Different number of columns between headers and
                           lines
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
            str_line = []
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
                raise ValueError("Different sizes for header and lines "
                                 "(line {0})".format(idx + 1))

            except (TypeError, AttributeError):
                # Invalid type of line
                raise ValueError("Invalid type of line: %s",
                                 type(line).__name__)

            else:
                if column != nb_columns:
                    # Check if all lines have the same number of columns
                    raise ValueError("Different sizes for header and lines "
                                     "(line {0})".format(idx + 1))

        # Prepare the head (centered text)
        format_str = "{0}|".format(prefix)
        for column, length in enumerate(lengths):
            format_str += " {%d:^%d} |" % (column, length)

        head_str = format_str.format(*headers)

        # Prepare the separator, according the length of the headers string
        separator = '{0}{1}'.format(prefix,
                                    '-' * (len(head_str) - len(prefix)))
        idx = head_str.find('|')
        while idx != -1:
            separator = '+'.join((separator[:idx], separator[idx + 1:]))
            idx = head_str.find('|', idx + 1)

        # Prepare the output
        output = [separator,
                  head_str,
                  separator.replace('-', '=')]

        # Compute the lines
        format_str = format_str.replace('^', '<')
        for line in str_lines:
            output.append(format_str.format(*line))
            output.append(separator)

        # Force the last end of line
        output.append("")

        # Join'em
        return '\n'.join(output)

# ------------------------------------------------------------------------------


class Shell(object):
    """
    A simple shell, based on shlex.

    Allows to use name spaces.
    """
    def __init__(self, context, utilities):
        """
        Sets up the shell

        :param context: The bundle context
        """
        self._commands = {}
        self._context = context
        self._utils = utilities

        # Bound services: reference -> service
        self._bound_references = {}

        # Service reference -> (name space, [commands])
        self._reference_commands = {}

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

        self.register_command(None, "echo", self.echo)

        self.register_command(None, "loglevel", self.log_level)

        self.register_command(None, "help", self.print_help)
        self.register_command(None, "?", self.print_help)

        self.register_command(None, "quit", self.quit)
        self.register_command(None, "close", self.quit)
        self.register_command(None, "exit", self.quit)

    def _bind_handler(self, svc_ref):
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
        commands = []

        # Register all service methods directly
        for command, method in handler.get_methods():
            self.register_command(namespace, command, method)
            commands.append(command)

        # Store the reference
        self._bound_references[svc_ref] = handler
        self._reference_commands[svc_ref] = (namespace, commands)
        return True

    def _unbind_handler(self, svc_ref):
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

    def register_command(self, namespace, command, method):
        """
        Registers the given command to the shell.

        The namespace can be None, empty or "default"

        :param namespace: The command name space.
        :param command: The shell name of the command
        :param method: The method to call
        :return: True if the method has been registered, False if it was
                 already known or invalid
        """
        if method is None:
            _logger.error("No method given for %s.%s", namespace, command)
            return False

        # Store everything in lower case
        namespace = (namespace or "").strip().lower()
        command = (command or "").strip().lower()

        if not namespace:
            namespace = DEFAULT_NAMESPACE

        if not command:
            _logger.error("No command name given")
            return False

        if namespace not in self._commands:
            space = self._commands[namespace] = {}
        else:
            space = self._commands[namespace]

        if command in space:
            _logger.error("Command already registered: %s.%s", namespace,
                          command)
            return False

        space[command] = method
        return True

    def unregister(self, namespace, command=None):
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
            _logger.warning("Unknown name space: %s", namespace)
            return False

        if command is not None:
            # Remove the command
            command = command.strip().lower()
            if command not in self._commands[namespace]:
                _logger.warning("Unknown command: %s.%s", namespace, command)
                return False

            del self._commands[namespace][command]

            # Remove the name space if necessary
            if not self._commands[namespace]:
                del self._commands[namespace]

        else:
            # Remove the whole name space
            del self._commands[namespace]

        return True

    def __find_command_ns(self, command):
        """
        Returns the name spaces where the given command named is registered.
        If the command exists in the default name space, the returned list will
        only contain the default name space.
        Returns an empty list of the command is unknown

        :param command: A command name
        :return: A list of name spaces
        """
        # Look for the spaces where the command name appears
        namespaces = []
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

    def get_ns_commands(self, cmd_name):
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
                raise ValueError("Unknown command {0}".format(command))

            else:
                # Return a sorted list of tuples
                return sorted((namespace, command) for namespace in spaces)

        # Single match
        return [(namespace, command)]

    def get_ns_command(self, cmd_name):
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
                raise ValueError("Unknown command {0}".format(command))

            elif len(spaces) > 1:
                # Multiple possibilities
                if spaces[0] == DEFAULT_NAMESPACE:
                    # Default name space has priority
                    namespace = DEFAULT_NAMESPACE

                else:
                    # Ambiguous name
                    raise ValueError("Multiple name spaces for {0}: {1}"
                                     .format(command, ', '.join(spaces)))

            else:
                # Use the found name space
                namespace = spaces[0]

        # Command found
        return namespace, command

    def execute(self, cmdline, stdin=sys.stdin, stdout=sys.stdout):
        """
        Executes the command corresponding to the given line
        """
        # Split the command line
        if not cmdline:
            return False

        # Convert the line into a string
        cmdline = to_str(cmdline)

        # Prepare the I/O handler
        io_handler = IOHandler(stdin, stdout)

        try:
            line_split = shlex.split(cmdline, True, True)

        except ValueError as ex:
            io_handler.write_line("Error reading line: {0}", ex)
            return False

        if not line_split:
            return False

        try:
            # Extract command information
            namespace, command = self.get_ns_command(line_split[0])

        except ValueError as ex:
            # Unknown command
            io_handler.write_line(str(ex))
            return False

        # Get the content of the name space
        space = self._commands.get(namespace, None)
        if not space:
            io_handler.write_line("Unknown name space {0}", namespace)
            return False

        # Get the method object
        method = space.get(command, None)
        if method is None:
            io_handler.write_line("Unknown command: {0}.{1}", namespace,
                                  command)
            return False

        # Make arguments and keyword arguments
        args, kwargs = _make_args(line_split[1:])

        # Execute it
        try:
            result = method(io_handler, *args, **kwargs)
            # None is considered as a success
            return result is None or result

        except TypeError as ex:
            # Invalid arguments...
            _logger.error("Error calling %s.%s: %s", namespace, command, ex)
            io_handler.write_line("Invalid method call: {0}", ex)
            self.__print_namespace_help(io_handler, namespace, command)
            return False

        except Exception as ex:
            # Error
            _logger.exception("Error calling %s.%s: %s",
                              namespace, command, ex)
            io_handler.write_line("{0}: {1}", type(ex).__name__, str(ex))
            return False

        finally:
            # Try to flush in any case
            try:
                io_handler.flush()
            except:
                pass

    def get_banner(self):
        """
        Returns the Shell banner
        """
        return "** Pelix Shell prompt **\n"

    def get_ps1(self):
        """
        Returns the PS1, the basic shell prompt
        """
        return "$ "

    def get_namespaces(self):
        """
        Retrieves the list of known name spaces (without the default one)

        :return: The list of known name spaces
        """
        namespaces = list(self._commands.keys())
        namespaces.remove(DEFAULT_NAMESPACE)
        namespaces.sort()
        return namespaces

    def get_commands(self, namespace):
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

    def echo(self, io_handler, *words):
        """
        Echoes the given words
        """
        io_handler.write_line(' '.join(words))

    def bundle_details(self, io_handler, bundle_id):
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
            io_handler.write_line("Unknown bundle ID: {0}", bundle_id)
            return

        lines = ["ID......: {0}".format(bundle.get_bundle_id()),
                 "Name....: {0}".format(bundle.get_symbolic_name()),
                 "Version.: {0}".format(bundle.get_version()),
                 "State...: {0}".format(
                     self._utils.bundlestate_to_str(bundle.get_state())),
                 "Location: {0}".format(bundle.get_location()),
                 "Published services:"]
        try:
            services = bundle.get_registered_services()
            if services:
                for svc_ref in services:
                    lines.append("\t{0}".format(svc_ref))
            else:
                lines.append("\tn/a")

        except constants.BundleException as ex:
            # Bundle in a invalid state
            lines.append("\tError: {0}".format(ex))

        lines.append("Services used by this bundle:")
        try:
            services = bundle.get_services_in_use()
            if services:
                for svc_ref in services:
                    lines.append("\t{0}".format(svc_ref))

            else:
                lines.append("\tn/a")

        except constants.BundleException as ex:
            # Bundle in a invalid state
            lines.append("\tError: {0}".format(ex))

        lines.append("")
        io_handler.write('\n'.join(lines))

    def bundles_list(self, io_handler, name=None):
        """
        Lists the bundles in the framework and their state. Possibility to
        filter on the bundle name.
        """
        # Head of the table
        headers = ('ID', 'Name', 'State', 'Version')

        # Get the bundles
        bundles = self._context.get_bundles()

        # The framework is not in the result of get_bundles()
        bundles.insert(0, self._context.get_bundle(0))

        if name is not None:
            # Filter the list
            bundles = [bundle for bundle in bundles
                       if name in bundle.get_symbolic_name()]

        # Make the entries
        lines = [[str(entry)
                  for entry in (bundle.get_bundle_id(),
                                bundle.get_symbolic_name(),
                                self._utils.bundlestate_to_str(
                                    bundle.get_state()),
                                bundle.get_version())]
                 for bundle in bundles]

        # Print'em all
        io_handler.write(self._utils.make_table(headers, lines))

        if name is None:
            io_handler.write_line("{0} bundles installed", len(lines))

        else:
            io_handler.write_line("{0} filtered bundles", len(lines))

    def service_details(self, io_handler, service_id):
        """
        Prints the details of the service with the given ID
        """
        svc_ref = self._context.get_service_reference(
            None, '({0}={1})'.format(constants.SERVICE_ID, service_id))
        if svc_ref is None:
            io_handler.write_line('Service not found: {0}', service_id)
            return

        lines = [
            "ID............: {0}".format(
                svc_ref.get_property(constants.SERVICE_ID)),
            "Rank..........: {0}".format(
                svc_ref.get_property(constants.SERVICE_RANKING)),
            "Specifications: {0}".format(
                svc_ref.get_property(constants.OBJECTCLASS)),
            "Bundle........: {0}".format(svc_ref.get_bundle()),
            "Properties....:"]
        for key, value in sorted(svc_ref.get_properties().items()):
            lines.append("\t{0} = {1}".format(key, value))

        lines.append("Bundles using this service:")
        for bundle in svc_ref.get_using_bundles():
            lines.append("\t{0}".format(bundle))

        lines.append("")
        io_handler.write('\n'.join(lines))

    def services_list(self, io_handler, specification=None):
        """
        Lists the services in the framework. Possibility to filter on an exact
        specification.
        """
        # Head of the table
        headers = ('ID', 'Specifications', 'Bundle', 'Ranking')

        # Lines
        references = self._context.get_all_service_references(None, None)

        # Use the reverse order (ascending service IDs instead of descending)
        references.reverse()

        if specification is not None:
            # Filter on specifications
            references = [ref for ref in references
                          if specification
                          in ref.get_property(constants.OBJECTCLASS)]

        # Construct the list of services
        lines = [[str(entry)
                  for entry in (ref.get_property(constants.SERVICE_ID),
                                ref.get_property(constants.OBJECTCLASS),
                                ref.get_bundle(),
                                ref.get_property(constants.SERVICE_RANKING))]
                 for ref in references]

        if not lines and specification:
            # No matching service found
            io_handler.write_line("No service provides '{0}'", specification)
        else:
            # Print'em all
            io_handler.write(self._utils.make_table(headers, lines))
            io_handler.write_line("{0} services registered", len(lines))

    def __extract_help(self, method):
        """
        Formats the help string for the given method

        :param method: The method to document
        :return: A tuple: (arguments list, documentation line)
        """
        if method is None:
            return "(No associated method)"

        # Get the arguments
        argspec = inspect.getargspec(method)

        # Compute the number of arguments with default value
        if argspec.defaults is not None:
            nb_optional = len(argspec.defaults)

            # Let the mandatory arguments as they are
            args = ["<{0}>".format(arg)
                    for arg in argspec.args[2:-nb_optional]]

            # Add the other arguments
            for name, value in zip(argspec.args[-nb_optional:],
                                   argspec.defaults[-nb_optional:]):
                if value is not None:
                    args.append('[<{0}>={1}]'.format(name, value))
                else:
                    args.append('[<{0}>]'.format(name))

        else:
            # All arguments are mandatory
            args = ["<{0}>".format(arg) for arg in argspec.args[2:]]

        # Extra arguments
        if argspec.keywords:
            args.append('[<property=value> ...]')

        if argspec.varargs:
            args.append("...")

        # Get the documentation string
        doc = inspect.getdoc(method) or "(Documentation missing)"

        return ' '.join(args), ' '.join(doc.split())

    def __print_command_help(self, io_handler, namespace, cmd_name):
        """
        Prints the documentation of the given command

        :param io_handler: I/O handler
        :param namespace: Name space of the command
        :param cmd_name: Name of the command
        """
        # Extract documentation
        args, doc = self.__extract_help(self._commands[namespace][cmd_name])

        # Print the command name, and its arguments
        if args:
            io_handler.write_line("- {0} {1}", cmd_name, args)
        else:
            io_handler.write_line("- {0}", cmd_name)

        # Print the documentation line
        io_handler.write_line("\t\t{0}", doc)

    def __print_namespace_help(self, io_handler, namespace, cmd_name=None):
        """
        Prints the documentation of all the commands in the given name space,
        or only of the given command

        :param io_handler: I/O Handler
        :param namespace: Name space of the command
        :param cmd_name: Name of the command to show, None to show them all
        """
        io_handler.write_line("=== Name space '{0}' ===", namespace)

        # Get all commands in this name space
        if cmd_name is None:
            names = [command for command in self._commands[namespace]]
            names.sort()

        else:
            names = [cmd_name]

        first_cmd = True
        for command in names:
            if not first_cmd:
                # Print an empty line
                io_handler.write_line('\n')

            self.__print_command_help(io_handler, namespace, command)
            first_cmd = False

    def print_help(self, io_handler, command=None):
        """
        Prints the available methods and their documentation, or the
        documentation of the given command.
        """
        if command:
            # Single command mode
            if command in self._commands:
                # Argument is a name space
                self.__print_namespace_help(io_handler, command)
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
                    io_handler.write_line(str(ex))
                    return False

            else:
                # Print the help of the found command
                if was_namespace:
                    # Give some space
                    io_handler.write_line('\n\n')

                for namespace, cmd_name in possibilities:
                    self.__print_namespace_help(io_handler, namespace,
                                                cmd_name)

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
                    io_handler.write_line('\n\n')

                # Print the help of all commands
                self.__print_namespace_help(io_handler, namespace)
                first_ns = False

    def properties_list(self, io_handler):
        """
        Lists the properties of the framework
        """
        # Get the framework
        framework = self._context.get_bundle(0)

        # Head of the table
        headers = ('Property Name', 'Value')

        # Lines
        lines = [item for item in framework.get_properties().items()]

        # Sort lines
        lines.sort()

        # Print the table
        io_handler.write(self._utils.make_table(headers, lines))

    def property_value(self, io_handler, name):
        """
        Prints the value of the given property, looking into
        framework properties then environment variables.
        """
        value = self._context.get_property(name)
        if value is None:
            # Avoid printing "None"
            value = ""

        io_handler.write_line(str(value))

    def environment_list(self, io_handler):
        """
        Lists the framework process environment variables
        """
        # Head of the table
        headers = ('Environment Variable', 'Value')

        # Lines
        lines = [item for item in os.environ.items()]

        # Sort lines
        lines.sort()

        # Print the table
        io_handler.write(self._utils.make_table(headers, lines))

    def environment_value(self, io_handler, name):
        """
        Prints the value of the given environment variable
        """
        io_handler.write_line(os.getenv(name))

    def threads_list(self, io_handler):
        """
        Lists the active threads and their current code line
        """
        # Extract frames
        frames = sys._current_frames()

        # Get the thread ID -> Thread mapping
        names = threading._active.copy()

        # Sort by thread ID
        thread_ids = list(frames.keys())
        thread_ids.sort()

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
            lines.append('Thread ID: {0} - Name: {1}'.format(thread_id, name))
            lines.append('Line:')
            lines.extend((line.rstrip()
                          for line in traceback.format_stack(stack, 1)))
            lines.append('')

        lines.append('')

        # Sort the lines
        io_handler.write('\n'.join(lines))

    def thread_details(self, io_handler, thread_id):
        """
        Prints details about the thread with the given ID (not its name)
        """
        try:
            # Get the stack
            thread_id = int(thread_id)
            stack = sys._current_frames()[thread_id]

        except KeyError:
            io_handler.write_line("Unknown thread ID: {0}", thread_id)

        except ValueError:
            io_handler.write_line("Invalid thread ID: {0}", thread_id)

        else:
            # Get the name
            try:
                name = threading._active[thread_id].name

            except KeyError:
                name = "<unknown>"

            lines = ['Thread ID: {0} - Name: {1}'.format(thread_id, name),
                     'Stack trace:']

            trace_lines = []
            frame = stack
            while frame is not None:
                # Store the line information
                trace_lines.append(self.__format_frame_info(frame))

                # Previous frame...
                frame = frame.f_back

            # Reverse the lines
            trace_lines.reverse()

            # Add them to the printed lines
            lines.extend(trace_lines)

            lines.append('')
            io_handler.write('\n'.join(lines))

    def __format_frame_info(self, frame):
        """
        Formats the given stack frame to show its position in the code and
        part of its context

        :param frame: A stack frame
        """
        # Same as in traceback.extract_stack
        lineno = frame.f_lineno
        code = frame.f_code
        filename = code.co_filename
        method_name = code.co_name
        linecache.checkcache(filename)

        output_lines = []

        try:
            # Try to get the type of the calling object
            instance = frame.f_locals['self']
            method_name = '{0}::{1}'.format(type(instance).__name__,
                                            method_name)
        except KeyError:
            # Not called from a bound method
            pass

        # File & line
        output_lines.append('  File "{0}", line {1}, in {2}'
                            .format(filename, lineno, method_name))

        # Arguments
        arginfo = inspect.getargvalues(frame)
        for name in arginfo.args:
            output_lines.append('    - {0:s} = {1}'
                                .format(name, repr(frame.f_locals[name])))

        if arginfo.varargs:
            output_lines.append('    - *{0:s} = {1}'
                                .format(arginfo.varargs,
                                        frame.f_locals[arginfo.varargs]))

        if arginfo.keywords:
            output_lines.append('    - **{0:s} = {1}'
                                .format(arginfo.keywords,
                                        frame.f_locals[arginfo.keywords]))

        # Line block
        lines = self.__extract_lines(filename, frame.f_globals, lineno, 3)
        if lines:
            output_lines.append('')
            prefix = '      '
            output_lines.append('{0}{1}'
                                .format(prefix,
                                        '\n{0}'.format(prefix).join(lines)))

        return '\n'.join(output_lines)

    def __extract_lines(self, filename, f_globals, lineno, around):
        """
        Extracts a block of lines from the given file

        :param filename: Name of the source file
        :param f_globals: Globals of the frame of the current code
        :param lineno: Current line of code
        :param around: Number of line to print before and after the current one
        """
        current_line = linecache.getline(filename, lineno, f_globals)
        if not current_line:
            # No data on this line
            return ''

        lines = []
        # Add some lines before
        for pre_lineno in range(lineno - around, lineno):
            pre_line = linecache.getline(filename, pre_lineno, f_globals)
            lines.append('{0}'.format(pre_line.rstrip()))

        # The line itself
        lines.append('{0}'.format(current_line.rstrip()))

        # Add some lines after
        for pre_lineno in range(lineno + 1, lineno + around + 1):
            pre_line = linecache.getline(filename, pre_lineno, f_globals)
            lines.append('{0}'.format(pre_line.rstrip()))

        # Smart left strip
        minimal_tab = None
        for line in lines:
            if line.strip():
                tab = len(line) - len(line.lstrip())
                if minimal_tab is None or tab < minimal_tab:
                    minimal_tab = tab

        if minimal_tab > 0:
            lines = [line[minimal_tab:] for line in lines]

        # Add some place for a marker
        marked_line = '>> {0}'.format(lines[around])
        lines = ['   {0}'.format(line) for line in lines]
        lines[around] = marked_line
        lines.append('')

        # Return the lines
        return lines

    def log_level(self, io_handler, level=None, name=None):
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
            io_handler.write_line(
                "{0} log level: {1} (real: {2})",
                name,
                logging.getLevelName(logger.getEffectiveLevel()),
                logging.getLevelName(logger.level))

        else:
            # Set the logger level
            try:
                logger.setLevel(level.upper())
                io_handler.write_line("New level for {0}: {1}", name, level)

            except ValueError:
                io_handler.write_line("Invalid log level: {0}", level)

    def quit(self, io_handler):
        """
        Stops the current shell session (raises a KeyboardInterrupt exception)
        """
        io_handler.write_line("Raising KeyboardInterrupt to stop main thread")
        raise KeyboardInterrupt()

    def __get_bundle(self, io_handler, bundle_id):
        """
        Retrieves the Bundle object with the given bundle ID. Writes errors
        through the I/O handler if any.

        :param io_handler: I/O Handler
        :param bundle_id: String or integer bundle ID
        :return: The Bundle object matching the given ID, None if not found
        """
        try:
            bundle_id = int(bundle_id)
            return self._context.get_bundle(bundle_id)

        except (TypeError, ValueError):
            io_handler.write_line("Invalid bundle ID: {0}", bundle_id)

        except constants.BundleException:
            io_handler.write_line("Unknown bundle: {0}", bundle_id)

    def start(self, io_handler, bundle_id):
        """
        Starts the bundle with the given ID
        """
        bundle = self.__get_bundle(io_handler, bundle_id)
        if bundle is not None:
            bundle.start()

    def stop(self, io_handler, bundle_id):
        """
        Stops the bundle with the given ID
        """
        bundle = self.__get_bundle(io_handler, bundle_id)
        if bundle is not None:
            bundle.stop()

    def update(self, io_handler, bundle_id):
        """
        Updates the bundle with the given ID
        """
        bundle = self.__get_bundle(io_handler, bundle_id)
        if bundle is not None:
            bundle.update()

    def install(self, io_handler, module_name):
        """
        Installs the bundle with the given module name
        """
        bundle = self._context.install_bundle(module_name)
        io_handler.write_line("Bundle ID: {0}", bundle.get_bundle_id())

    def uninstall(self, io_handler, bundle_id):
        """
        Uninstalls the bundle with the given ID
        """
        bundle = self.__get_bundle(io_handler, bundle_id)
        if bundle is not None:
            bundle.uninstall()

# ------------------------------------------------------------------------------


@constants.BundleActivator
class PelixActivator(object):
    """
    Activator class for Pelix
    """
    def __init__(self):
        """
        Sets up the activator
        """
        self._shell = None
        self._shell_reg = None
        self._utils_reg = None

    def service_changed(self, event):
        """
        Called when a command provider service event occurred
        """
        kind = event.get_kind()
        reference = event.get_service_reference()

        if kind in (pelix.ServiceEvent.REGISTERED,
                    pelix.ServiceEvent.MODIFIED):
            # New or modified service
            self._shell._bind_handler(reference)

        else:
            # Service gone or not matching anymore
            self._shell._unbind_handler(reference)

    def start(self, context):
        """
        Bundle starting

        :param context: The bundle context
        """
        try:
            # Prepare the shell utility service
            utils = ShellUtils()
            self._shell = Shell(context, utils)

            self._shell_reg = context.register_service(SERVICE_SHELL,
                                                       self._shell, {})

            self._utils_reg = context.register_service(SERVICE_SHELL_UTILS,
                                                       utils, {})

            # Register the service listener
            context.add_service_listener(self, None, SERVICE_SHELL_COMMAND)

            # Register existing command services
            refs = context.get_all_service_references(SERVICE_SHELL_COMMAND,
                                                      None)
            if refs is not None:
                for ref in refs:
                    self._shell._bind_handler(ref)

            _logger.info("Shell services registered")

        except constants.BundleException as ex:
            _logger.exception("Error registering the shell service: %s", ex)

    def stop(self, context):
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
        _logger.info("Shell services unregistered")
