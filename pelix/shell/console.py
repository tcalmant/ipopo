#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix interactive shell

Provides a console interface for the Pelix shell, based on readline when
available.

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

# Standard library
import argparse
import logging
import os
import shlex
import sys
import threading

# Initialization file handler
from pelix.misc.init_handler import InitFileHandler, remove_duplicates

# Shell constants
from pelix.constants import BundleActivator
from pelix.shell import SERVICE_SHELL
from pelix.shell.beans import IOHandler, ShellSession, safe_input
import pelix.framework as pelix

# Shell completion
from pelix.shell.completion.core import completion_hints

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

PROP_INIT_FILE = "pelix.shell.console.init_file"
""" Shell script to execute before starting the console """

PROP_RUN_FILE = "pelix.shell.console.script_file"
""" Script to run as shell input """

# ------------------------------------------------------------------------------

try:
    # Set up readline if available
    import readline

    readline.parse_and_bind("tab: complete")
    readline.set_completer(None)
except ImportError:
    # Readline is missing, not critical
    readline = None

# ------------------------------------------------------------------------------


class InteractiveShell(object):
    """
    The interactive shell handler
    """

    def __init__(self, context):
        """
        Sets up the members

        :param context: The bundle context
        """
        self._context = context  # type: pelix.BundleContext
        self._shell_ref = None  # type: pelix.ServiceReference
        self._shell = None

        # Single session
        self.__session = ShellSession(IOHandler(sys.stdin, sys.stdout), {})

        # Read line cache
        self._readline_matches = []

        # Rendez-vous events
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._shell_event = threading.Event()

        # Try to find a shell service
        self.search_shell()

        # Register as a service listener
        self._context.add_service_listener(self, None, SERVICE_SHELL)

    def __get_ps1(self):
        """
        Gets the prompt string from the session of the shell service

        :return: The prompt string
        """
        try:
            return self.__session.get("PS1")
        except KeyError:
            return self._shell.get_ps1()

    def _readline_prompt(self):
        """
        Prompt using the readline module (no pre-flush)

        :return: The command line
        """
        sys.stdout.flush()
        return safe_input(self.__get_ps1())

    def _normal_prompt(self):
        """
        Flushes the prompt before requesting the input

        :return: The command line
        """
        sys.stdout.write(self.__get_ps1())
        sys.stdout.flush()
        return safe_input()

    def loop_input(self, on_quit=None):
        """
        Reads the standard input until the shell session is stopped

        :param on_quit: A call back method, called without argument when the
                        shell session has ended
        """
        # Start the init script
        self._run_script(
            self.__session, self._context.get_property(PROP_INIT_FILE)
        )

        # Run the script
        script_file = self._context.get_property(PROP_RUN_FILE)
        if script_file:
            self._run_script(self.__session, script_file)
        else:
            # No script: run the main loop (blocking)
            self._run_loop(self.__session)

        # Nothing more to do
        self._stop_event.set()
        sys.stdout.write("Bye !\n")
        sys.stdout.flush()
        if on_quit is not None:
            # Call a handler if needed
            on_quit()

    def _run_script(self, session, file_path):
        """
        Runs the given script file

        :param session: Current shell session
        :param file_path: Path to the file to execute
        :return: True if a file has been execute
        """
        if file_path:
            # The 'run' command returns False in case of error
            # The 'execute' method returns False if the run command fails
            return self._shell.execute('run "{0}"'.format(file_path), session)

        return None

    def _run_loop(self, session):
        """
        Runs the main input loop

        :param session: Current shell session
        """
        try:
            first_prompt = True

            # Set up the prompt
            prompt = (
                self._readline_prompt
                if readline is not None
                else self._normal_prompt
            )

            while not self._stop_event.is_set():
                # Wait for the shell to be there
                # Before Python 2.7, wait() doesn't return a result
                if self._shell_event.wait(.2) or self._shell_event.is_set():
                    # Shell present
                    if first_prompt:
                        # Show the banner on first prompt
                        sys.stdout.write(self._shell.get_banner())
                        first_prompt = False

                    # Read the next line
                    line = prompt()

                    with self._lock:
                        if self._shell_event.is_set():
                            # Execute it
                            self._shell.execute(line, session)

                        elif not self._stop_event.is_set():
                            # Shell service lost while not stopping
                            sys.stdout.write("Shell service lost.")
                            sys.stdout.flush()
        except (EOFError, KeyboardInterrupt, SystemExit):
            # Input closed or keyboard interruption
            pass

    def readline_completer(self, text, state):
        """
        A completer for the readline library
        """
        if state == 0:
            # New completion, reset the list of matches and the display hook
            self._readline_matches = []
            try:
                readline.set_completion_display_matches_hook(None)
            except AttributeError:
                pass

            # Get the full line
            full_line = readline.get_line_buffer()
            begin_idx = readline.get_begidx()

            # Parse arguments as best as we can
            try:
                arguments = shlex.split(full_line)
            except ValueError:
                arguments = full_line.split()

            # Extract the command (maybe with its namespace)
            command = arguments.pop(0)

            if begin_idx > 0:
                # We're completing after the command (and maybe some args)
                try:
                    # Find the command
                    ns, command = self._shell.get_ns_command(command)
                except ValueError:
                    # Ambiguous command: ignore
                    return None

                # Use the completer associated to the command, if any
                try:
                    configuration = self._shell.get_command_completers(
                        ns, command
                    )
                    if configuration is not None:
                        self._readline_matches = completion_hints(
                            configuration,
                            self.__get_ps1(),
                            self.__session,
                            self._context,
                            text,
                            arguments,
                        )
                except KeyError:
                    # Unknown command
                    pass

            elif "." in command:
                # Completing the command, and a name space is given
                namespace, prefix = text.split(".", 2)
                commands = self._shell.get_commands(namespace)

                # Filter methods according to the prefix
                self._readline_matches = [
                    "{0}.{1}".format(namespace, command)
                    for command in commands
                    if command.startswith(prefix)
                ]
            else:
                # Completing a command or namespace
                prefix = command

                # Default commands goes first...
                possibilities = [
                    "{0} ".format(command)
                    for command in self._shell.get_commands(None)
                    if command.startswith(prefix)
                ]

                # ... then name spaces
                namespaces = self._shell.get_namespaces()
                possibilities.extend(
                    "{0}.".format(namespace)
                    for namespace in namespaces
                    if namespace.startswith(prefix)
                )

                # ... then commands in those name spaces
                possibilities.extend(
                    "{0} ".format(command)
                    for namespace in namespaces
                    if namespace is not None
                    for command in self._shell.get_commands(namespace)
                    if command.startswith(prefix)
                )

                # Filter methods according to the prefix
                self._readline_matches = possibilities

            if not self._readline_matches:
                return None

            # Return the first possibility
            return self._readline_matches[0]

        elif state < len(self._readline_matches):
            # Next try
            return self._readline_matches[state]

        return None

    def search_shell(self):
        """
        Looks for a shell service
        """
        with self._lock:
            if self._shell is not None:
                # A shell is already there
                return

            reference = self._context.get_service_reference(SERVICE_SHELL)
            if reference is not None:
                self.set_shell(reference)

    def service_changed(self, event):
        """
        Called by Pelix when an events changes
        """
        kind = event.get_kind()
        reference = event.get_service_reference()

        if kind in (pelix.ServiceEvent.REGISTERED, pelix.ServiceEvent.MODIFIED):
            # A service matches our filter
            self.set_shell(reference)

        else:
            with self._lock:
                # Service is not matching our filter anymore
                self.clear_shell()

                # Request for a new binding
                self.search_shell()

    def set_shell(self, svc_ref):
        """
        Binds the given shell service.

        :param svc_ref: A service reference
        """
        if svc_ref is None:
            return

        with self._lock:
            # Get the service
            self._shell_ref = svc_ref
            self._shell = self._context.get_service(self._shell_ref)

            # Set the readline completer
            if readline is not None:
                readline.set_completer(self.readline_completer)

            # Set the flag
            self._shell_event.set()

    def clear_shell(self):
        """
        Unbinds the active shell service
        """
        with self._lock:
            # Clear the flag
            self._shell_event.clear()

            # Clear the readline completer
            if readline is not None:
                readline.set_completer(None)
                del self._readline_matches[:]

            if self._shell_ref is not None:
                # Release the service
                self._context.unget_service(self._shell_ref)

            self._shell_ref = None
            self._shell = None

    def stop(self):
        """
        Clears all members
        """
        # Exit the loop
        with self._lock:
            self._stop_event.set()
            self._shell_event.clear()

        if self._context is not None:
            # Unregister from events
            self._context.remove_service_listener(self)

            # Release the shell
            self.clear_shell()
            self._context = None


# ------------------------------------------------------------------------------


@BundleActivator
class Activator(object):
    """
    The bundle activator
    """

    def __init__(self):
        """
        Sets up the members
        """
        self._context = None
        self._shell = None
        self._thread = None

    def start(self, context):
        """
        Bundle started
        """
        self._context = context
        self._shell = InteractiveShell(context)

        # Run the loop thread
        self._thread = threading.Thread(
            target=self._shell.loop_input,
            args=[self._quit],
            name="Pelix-Shell-TextConsole",
        )
        # Set the thread as a daemon, to let it be killed by the interpreter
        # once all other threads stopped.
        self._thread.daemon = True
        self._thread.start()

    def stop(self, _):
        """
        Bundle stopped
        """
        self._cleanup()
        self._context = None

    def _quit(self):
        """
        Called when the shell session has ended
        """
        # Clean up members
        self._cleanup()

        # Stop the framework
        if self._context is not None:
            self._context.get_framework().stop()

    def _cleanup(self):
        """
        Cleans up the members
        """
        if self._shell is not None:
            # Stop the shell
            self._shell.stop()

        self._thread = None
        self._shell = None


# ------------------------------------------------------------------------------


def _resolve_file(file_name):
    """
    Checks if the file exists.

    If the file exists, the method returns its absolute path.
    Else, it returns None

    :param file_name: The name of the file to check
    :return: An absolute path, or None
    """
    if not file_name:
        return None

    path = os.path.realpath(file_name)
    if os.path.isfile(path):
        return path

    return None


def make_common_parser():
    """
    Creates an argument parser (argparse module) with the options that should
    be common to all shells.

    The result can be used as a parent parser (``parents`` argument in
    ``argparse.ArgumentParser``)

    :return: An ArgumentParser object
    """
    parser = argparse.ArgumentParser(add_help=False)

    # Version number
    parser.add_argument(
        "--version",
        action="version",
        version="Pelix {0} from {1}".format(pelix.__version__, pelix.__file__),
    )

    # Framework options
    group = parser.add_argument_group("Framework options")
    group.add_argument(
        "-D",
        nargs="+",
        dest="properties",
        metavar="KEY=VALUE",
        help="Sets framework properties",
    )
    group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Set loggers to DEBUG level",
    )

    # Initial configuration
    group = parser.add_argument_group("Initial configuration")
    group.add_argument(
        "-c",
        "--conf",
        dest="init_conf",
        metavar="FILE",
        help="Name of an initial configuration file to use "
        "(default configuration is also loaded)",
    )
    group.add_argument(
        "-C",
        "--exclusive-conf",
        dest="init_conf_exclusive",
        metavar="FILE",
        help="Name of an initial configuration file to use "
        "(without the default configuration)",
    )
    group.add_argument(
        "-e",
        "--empty-conf",
        dest="init_empty",
        action="store_true",
        help="Don't load any initial configuration",
    )

    # Initial script
    group = parser.add_argument_group("Script execution arguments")
    group.add_argument(
        "--init",
        action="store",
        dest="init_script",
        metavar="SCRIPT",
        help="Runs the given shell script before starting the console",
    )
    group.add_argument(
        "--run",
        action="store",
        dest="run_script",
        metavar="SCRIPT",
        help="Runs the given shell script then stops the framework",
    )
    return parser


def handle_common_arguments(parsed_args):
    """
    Handles the arguments defined by :meth:`~make_common_parser`

    :param parsed_args: Argument parsed with ``argparse`` (``Namespace``)
    :return: An :class:`~InitFileHandler` object
    :raise IOError: Initial or run script not found
    """
    # Setup the logger
    logging.basicConfig(
        level=logging.DEBUG if parsed_args.verbose else logging.WARNING
    )

    # Framework properties dictionary
    props = {}

    # Read the initial configuration script
    init = InitFileHandler()
    if not parsed_args.init_empty:
        if not parsed_args.init_conf_exclusive:
            # Load default configuration
            init.load()

        # Load the given configuration file
        conf_file = parsed_args.init_conf_exclusive or parsed_args.init_conf
        if conf_file:
            init.load(conf_file)

        # Normalize configuration
        init.normalize()

        # Set initial framework properties
        props.update(init.properties)

    # Compute framework properties
    for prop_def in parsed_args.properties or []:
        key, value = prop_def.split("=", 1)
        props[key] = value

    # Check initial run script(s)
    if parsed_args.init_script:
        path = props[PROP_INIT_FILE] = _resolve_file(parsed_args.init_script)
        if not path:
            raise IOError(
                "Initial script file not found: {0}".format(
                    parsed_args.init_script
                )
            )

    if parsed_args.run_script:
        # Find the file
        path = props[PROP_RUN_FILE] = _resolve_file(parsed_args.run_script)
        if not path:
            raise IOError(
                "Script file not found: {0}".format(parsed_args.run_script)
            )

    # Update the stored configuration
    init.properties.update(props)
    return init


def main(argv=None):
    """
    Entry point

    :param argv: Script arguments (None for sys.argv)
    :return: An exit code or None
    """
    # Parse arguments
    parser = argparse.ArgumentParser(
        prog="pelix.shell.console",
        parents=[make_common_parser()],
        description="Pelix Shell Console",
    )

    # Parse arguments
    args = parser.parse_args(argv)

    # Handle arguments
    init = handle_common_arguments(args)

    # Set the initial bundles
    bundles = [
        "pelix.ipopo.core",
        "pelix.shell.core",
        "pelix.shell.ipopo",
        "pelix.shell.completion.pelix",
        "pelix.shell.completion.ipopo",
        "pelix.shell.console",
    ]
    bundles.extend(init.bundles)

    # Use the utility method to create, run and delete the framework
    framework = pelix.create_framework(
        remove_duplicates(bundles), init.properties
    )
    framework.start()

    # Instantiate components
    init.instantiate_components(framework.get_bundle_context())

    try:
        framework.wait_for_stop()
    except KeyboardInterrupt:
        framework.stop()


if __name__ == "__main__":
    # Run the entry point
    sys.exit(main() or 0)
