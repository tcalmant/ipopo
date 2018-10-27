#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Defines the shell completion handlers for iPOPO concepts

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
    from .decorators import CompletionInfo
except ImportError:
    pass

# Pelix
from pelix.constants import BundleActivator
from pelix.ipopo.constants import use_ipopo

# Completion classes
from .decorators import (
    SVC_COMPLETER,
    PROP_COMPLETER_ID,
    FACTORY,
    COMPONENT,
    FACTORY_PROPERTY,
)
from .core import Completer

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class ComponentFactoryCompleter(Completer):
    """
    Completes an iPOPO Component factory name
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
        # Prepare a line pattern for each match (-1 for the trailing space)
        match_pattern = "{{0: <{}}} from {{1}}".format(longest_match_len - 1)

        # Sort matching names
        matches = sorted(match for match in matches)

        # Print the match and the associated name
        session.write_line()
        with use_ipopo(context) as ipopo:
            for factory_name in matches:
                # Remove the spaces added for the completion
                factory_name = factory_name.strip()
                bnd = ipopo.get_factory_bundle(factory_name)
                session.write_line(
                    match_pattern, factory_name, bnd.get_symbolic_name()
                )

        # Print the prompt, then current line
        session.write(prompt)
        session.write_line_no_feed(readline.get_line_buffer())
        readline.redisplay()

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

        # Return a list of component factories
        with use_ipopo(context) as ipopo:
            return [
                "{} ".format(factory)
                for factory in ipopo.get_factories()
                if factory.startswith(current)
            ]


class ComponentInstanceCompleter(Completer):
    """
    Completes an iPOPO Component instance name
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
        # Prepare a line pattern for each match (-1 for the trailing space)
        match_pattern = "{{0: <{}}} from {{1}}".format(longest_match_len - 1)

        # Sort matching names
        matches = sorted(match for match in matches)

        # Print the match and the associated name
        session.write_line()
        with use_ipopo(context) as ipopo:
            for name in matches:
                # Remove the spaces added for the completion
                name = name.strip()
                details = ipopo.get_instance_details(name)
                description = "of {factory} ({state})".format(**details)
                session.write_line(match_pattern, name, description)

        # Print the prompt, then current line
        session.write(prompt)
        session.write_line_no_feed(readline.get_line_buffer())
        readline.redisplay()

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

        # Return a list of component factories
        with use_ipopo(context) as ipopo:
            return [
                "{} ".format(name)
                for name, _, _ in ipopo.get_instances()
                if name.startswith(current)
            ]


class ComponentFactoryPropertiesCompleter(Completer):
    """
    Completes the property names of iPOPO Component factories
    """

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
        with use_ipopo(context) as ipopo:
            try:
                # Find the factory name
                for idx, completer_id in enumerate(config.completers):
                    if completer_id == FACTORY:
                        factory_name = current_arguments[idx]
                        break
                else:
                    # No factory completer found in signature
                    for idx, completer_id in enumerate(config.completers):
                        if completer_id == COMPONENT:
                            name = current_arguments[idx]
                            details = ipopo.get_instance_details(name)
                            factory_name = details["factory"]
                            break
                    else:
                        # No factory name can be found
                        return []

                # Get the details about this factory
                details = ipopo.get_factory_details(factory_name)
                properties = details["properties"]
            except (IndexError, ValueError):
                # No/unknown factory name
                return []
            else:
                return [
                    "{}=".format(key)
                    for key in properties
                    if key.startswith(current)
                ]


# ------------------------------------------------------------------------------


# All completers for this bundle
COMPLETERS = {
    FACTORY: ComponentFactoryCompleter,
    FACTORY_PROPERTY: ComponentFactoryPropertiesCompleter,
    COMPONENT: ComponentInstanceCompleter,
}


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

        :param context: The bundle context
        """
        # Clean up
        for svc_reg in self._registrations:
            svc_reg.unregister()
        del self._registrations[:]
