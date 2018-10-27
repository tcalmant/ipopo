#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Defines the shell completion handlers for Pelix concepts

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1
:status: Alpha

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

from __future__ import absolute_import

# Try to import readline
try:
    import readline
except ImportError:
    readline = None

# Add some typing
try:
    # pylint: disable=W0611
    from typing import List
    from pelix.framework import BundleContext
    from pelix.shell.beans import ShellSession
except ImportError:
    pass

# Pelix
from pelix.constants import SERVICE_ID, BundleActivator

# Completion classes
from .decorators import SVC_COMPLETER, PROP_COMPLETER_ID, BUNDLE, SERVICE
from .core import Completer

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class BundleCompleter(Completer):
    """
    Completes a bundle ID and display a bundle name in current matches
    """

    @staticmethod
    def display_hook(prompt, session, context, matches, longest_match_len):
        # type: (str, ShellSession, BundleContext, List[str], int) -> None
        """
        Displays the available bundle matches and the bundle name

        :param prompt: Shell prompt string
        :param session: Current shell session (for display)
        :param context: BundleContext of the shell
        :param matches: List of words matching the substitution
        :param longest_match_len: Length of the largest match
        """
        # Prepare a line pattern for each match
        match_pattern = "{{0: >{}}}: {{1}}".format(longest_match_len)

        # Sort matching IDs
        matches = sorted(int(match) for match in matches)

        # Print the match and the associated name
        session.write_line()
        for bnd_id in matches:
            bnd = context.get_bundle(bnd_id)
            session.write_line(match_pattern, bnd_id, bnd.get_symbolic_name())

        # Print the prompt, then current line
        session.write(prompt)
        session.write_line_no_feed(readline.get_line_buffer())
        readline.redisplay()

    def complete(
        self, config, prompt, session, context, current_arguments, current
    ):
        # type: (CompletionInfo, str, ShellSession, BundleContext, List[str], str) -> List[str]
        """
        Returns the list of bundle IDs matching the current state

        :param config: Configuration of the current completion
        :param prompt: Shell prompt (for re-display)
        :param session: Shell session (to display in shell)
        :param context: Bundle context of the Shell bundle
        :param current_arguments: Current arguments (without the command itself)
        :param current: Current word
        :return: A list of matches
        """
        # Register a method to display helpful completion
        self.set_display_hook(self.display_hook, prompt, session, context)

        # Return a list of bundle IDs (strings) matching the current value
        # and not yet in arguments
        rl_matches = []
        for bnd in context.get_bundles():
            bnd_id = "{0} ".format(bnd.get_bundle_id())
            if bnd_id.startswith(current):
                rl_matches.append(bnd_id)

        return rl_matches


class ServiceCompleter(Completer):
    """
    Completes a service ID and display a specification in current matches
    """

    @staticmethod
    def display_hook(prompt, session, context, matches, longest_match_len):
        # type: (str, ShellSession, BundleContext, List[str], int) -> None
        """
        Displays the available services matches and the service details

        :param prompt: Shell prompt string
        :param session: Current shell session (for display)
        :param context: BundleContext of the shell
        :param matches: List of words matching the substitution
        :param longest_match_len: Length of the largest match
        """
        try:
            # Prepare a line pattern for each match
            match_pattern = "{{0: >{}}}: {{1}}".format(longest_match_len)

            # Sort matching IDs
            matches = sorted(int(match) for match in matches)

            # Print the match and the associated name
            session.write_line()
            for svc_id in matches:
                svc_ref = context.get_service_reference(
                    None, "({}={})".format(SERVICE_ID, svc_id)
                )
                session.write_line(match_pattern, svc_id, str(svc_ref))

            # Print the prompt, then current line
            session.write(prompt)
            session.write_line_no_feed(readline.get_line_buffer())
            readline.redisplay()
        except Exception as ex:
            session.write_line("\n{}\n\n", ex)

    def complete(
        self, config, prompt, session, context, current_arguments, current
    ):
        # type: (CompletionInfo, str, ShellSession, BundleContext, List[str], str) -> List[str]
        """
        Returns the list of services IDs matching the current state

        :param config: Configuration of the current completion
        :param prompt: Shell prompt (for re-display)
        :param session: Shell session (to display in shell)
        :param context: Bundle context of the Shell bundle
        :param current_arguments: Current arguments (without the command itself)
        :param current: Current word
        :return: A list of matches
        """
        # Register a method to display helpful completion
        self.set_display_hook(self.display_hook, prompt, session, context)

        # Return a list of bundle IDs (strings) matching the current value
        # and not yet in arguments
        rl_matches = []
        for svc_ref in context.get_all_service_references(None, None):
            svc_id = "{0} ".format(svc_ref.get_property(SERVICE_ID))
            if svc_id.startswith(current):
                rl_matches.append(svc_id)

        return rl_matches


# ------------------------------------------------------------------------------


# All completers for this bundle
COMPLETERS = {BUNDLE: BundleCompleter, SERVICE: ServiceCompleter}


@BundleActivator
class _Activator:
    """
    Bundle activator
    """

    def __init__(self):
        self._registrations = []

    def start(self, context):
        # type: (BundleContext) -> None
        """
        Bundle starting

        :param context: The bundle context
        """
        # Register all completers we know
        self._registrations = [
            context.register_service(
                SVC_COMPLETER,
                completer_class(),
                {PROP_COMPLETER_ID: completer_id},
            )
            for completer_id, completer_class in COMPLETERS.items()
        ]

    def stop(self, _):
        # type: (BundleContext) -> None
        """
        Bundle stopping
        """
        # Clean up
        for svc_reg in self._registrations:
            svc_reg.unregister()
        del self._registrations[:]
