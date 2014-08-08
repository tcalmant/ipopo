#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix interactive shell

Provides a console interface for the Pelix shell, based on readline when
available.

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
from pelix.constants import BundleActivator
from pelix.shell import SERVICE_SHELL
import pelix.framework as pelix

# Standard library
import logging
import sys
import threading

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

try:
    # Set up readline if available
    import readline
    readline.parse_and_bind('tab: complete')
    readline.set_completer(None)
except ImportError:
    # Readline is missing, not critical
    readline = None

# Before Python 3, input() was raw_input()
if sys.version_info[0] < 3:
    safe_input = raw_input
else:
    safe_input = input

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
        self._context = context
        self._shell_ref = None
        self._shell = None

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

    def _readline_prompt(self):
        """
        Prompt using the readline module (no pre-flush)

        :return: The command line
        """
        sys.stdout.flush()
        return safe_input(self._shell.get_ps1())

    def _normal_prompt(self):
        """
        Flushes the prompt before requesting the input

        :return: The command line
        """
        sys.stdout.write(self._shell.get_ps1())
        sys.stdout.flush()
        return safe_input()

    def loop_input(self, on_quit=None):
        """
        Reads the standard input until the shell session is stopped

        :param on_quit: A call back method, called without argument when the
                        shell session has ended
        """
        try:
            first_prompt = True

            # Set up the prompt
            prompt = self._readline_prompt if readline is not None \
                else self._normal_prompt

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
                            self._shell.execute(line, sys.stdin, sys.stdout)

                        elif not self._stop_event.is_set():
                            # Shell service lost while not stopping
                            sys.stdout.write('Shell service lost.')
                            sys.stdout.flush()

        except (EOFError, KeyboardInterrupt, SystemExit):
            # Input closed or keyboard interruption
            pass

        self._stop_event.set()

        sys.stdout.write('Bye !\n')
        sys.stdout.flush()
        if on_quit is not None:
            # Call a handler if needed
            on_quit()

    def readline_completer(self, text, state):
        """
        A completer for the readline library
        """
        if state == 0:
            if '.' in text:
                # A name space is given
                namespace, prefix = text.split('.', 2)
                commands = self._shell.get_commands(namespace)

                # Filter methods according to the prefix
                self._readline_matches = ['{0}.{1}'.format(namespace, command)
                                          for command in commands
                                          if command.startswith(prefix)]

            else:
                # Complete with name space names or default commands
                prefix = text

                # Default commands goes first...
                possibilities = [command
                                 for command in self._shell.get_commands(None)
                                 if command.startswith(prefix)]

                # ... then name spaces
                namespaces = self._shell.get_namespaces()
                possibilities.extend('{0}.'.format(namespace)
                                     for namespace in namespaces
                                     if namespace.startswith(prefix))

                # ... then commands in those name spaces
                possibilities.extend(
                    '{0}.{1}'.format(namespace, command)
                    for namespace in namespaces if namespace is not None
                    for command in self._shell.get_commands(namespace)
                    if command.startswith(prefix))

                # Filter methods according to the prefix
                self._readline_matches = possibilities

            if not self._readline_matches:
                return None

            # Return the first possibility
            return self._readline_matches[0]

        elif state < len(self._readline_matches):
            # Next try
            return self._readline_matches[state]

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

        if kind in (pelix.ServiceEvent.REGISTERED,
                    pelix.ServiceEvent.MODIFIED):
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
        self._thread = threading.Thread(target=self._shell.loop_input,
                                        args=[self._quit],
                                        name="Pelix-Shell-TextConsole")
        # Set the thread as a daemon, to let it be killed by the interpreter
        # once all other threads stopped.
        self._thread.daemon = True
        self._thread.start()

    def stop(self, context):
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
            self._context.get_bundle(0).stop()

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


def main():
    """
    Entry point
    """
    # Use the utility method to create, run and delete the framework
    pelix.create_framework(('pelix.ipopo.core', 'pelix.shell.core',
                            'pelix.shell.console', 'pelix.shell.ipopo'),
                           None, True, True, True)

if __name__ == '__main__':
    # Prepare the logger
    if '-v' in sys.argv or '--verbose' in sys.argv:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Run the entry point
    main()
