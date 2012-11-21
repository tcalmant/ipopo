#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix interactive shell

Provides a console interface for the Pelix shell, based on readline when
available.

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

import pelix.framework as pelix
import logging
import sys
import threading

# ------------------------------------------------------------------------------

SHELL_SERVICE_SPEC = "pelix.shell"

_logger = logging.getLogger(__name__)

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
    input = raw_input

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
        ldap_filter = '({0}={1})'.format(pelix.OBJECTCLASS, SHELL_SERVICE_SPEC)
        self._context.add_service_listener(self, ldap_filter)


    def loop_input(self, on_quit=None):
        """
        Reads the standard input until the shell session is stopped
        
        :param on_quit: A call back method, called without argument when the
                        shell session has ended
        """
        try:
            first_prompt = True

            while not self._stop_event.is_set():
                # Wait for the shell to be there
                # Before Python 2.7, wait() doesn't return a result
                if self._shell_event.wait(.2) or self._shell_event.is_set():
                    with self._lock:
                        # Shell present
                        if first_prompt:
                            # Show the banner on first prompt
                            print(self._shell.get_banner())
                            first_prompt = False

                        # Read the line
                        line = input(self._shell.get_ps1())
                        # Execute it
                        self._shell.execute(line, sys.stdin, sys.stdout)

        except (EOFError, KeyboardInterrupt):
            # Input closed or keyboard interruption
            self._stop_event.set()

        print('Bye !')
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
                possibilities = self._shell.get_commands(None)
                possibilities.extend(['{0}.'.format(namespace)
                                      for namespace in self._shell.get_namespaces()])

                # Filter methods according to the prefix
                self._readline_matches = [entry for entry in possibilities
                                          if entry.startswith(prefix)]

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

            reference = self._context.get_service_reference(SHELL_SERVICE_SPEC)
            if reference is not None:
                self.set_shell(reference)


    def service_changed(self, event):
        """
        Called by Pelix when an events changes
        """
        kind = event.get_type()
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
            self._readline_matches = None


    def stop(self):
        """
        Clears all members
        """
        # Unregister from events
        with self._lock:
            self._shell_event.clear()
            self._stop_event.set()

        self._context.remove_service_listener(self)

        # Release the shell
        self.clear_shell()
        self._context = None

# ------------------------------------------------------------------------------

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
                                        args=[self._quit])
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
        self._context.get_bundle(0).stop()


    def _cleanup(self):
        """
        Cleans up the members
        """
        if self._shell is not None:
            self._shell.stop()

        if self._thread is not None \
        and self._thread is not threading.current_thread():
            # Wait for the shell to stop
            self._thread.join(1)

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
    # Ran as a script:
    # Prepare the logger
    logging.basicConfig(level=logging.WARNING)

    # Run the entry point
    main()

else:
    # Imported as a module:
    # Creates the Pelix activator
    activator = Activator()
