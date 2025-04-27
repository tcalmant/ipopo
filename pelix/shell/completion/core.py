#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Defines the ``Completer`` class, mother of all shell completion handlers

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

import abc
import logging
from typing import TYPE_CHECKING, Callable, List

from pelix.utilities import use_service

from . import PROP_COMPLETER_ID, Completer, DUMMY

try:
    import readline
except ImportError:
    pass

if TYPE_CHECKING:
    from pelix.framework import BundleContext
    from pelix.shell.beans import ShellSession

    from . import CompletionInfo


# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class AbstractCompleter(abc.ABC, Completer):
    """
    Mother class of all completers
    """

    @staticmethod
    def set_display_hook(
        display_hook: Callable[[str, "ShellSession", "BundleContext", List[str], int], None],
        prompt: str,
        session: "ShellSession",
        context: "BundleContext",
    ) -> None:
        """
        Sets up the readline completion hook, if available
        """
        try:
            readline.set_completion_display_matches_hook(  # type: ignore
                lambda sub, matches, longest: display_hook(prompt, session, context, matches, longest)
            )
        except AttributeError:
            # Display hook not available
            pass

    @abc.abstractmethod
    def complete(
        self,
        config: "CompletionInfo",
        prompt: str,
        session: "ShellSession",
        context: "BundleContext",
        current_arguments: List[str],
        current: str,
    ) -> List[str]:
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


# ------------------------------------------------------------------------------


def completion_hints(
    config: "CompletionInfo",
    prompt: str,
    session: "ShellSession",
    context: "BundleContext",
    current: str,
    arguments: List[str],
) -> List[str]:
    """
    Returns the possible completions of the current argument

    :param config: Configuration of the current completion
    :param prompt: The shell prompt string
    :param session: Current shell session
    :param context: Context of the shell UI bundle
    :param current: Current argument (to be completed)
    :param arguments: List of all arguments in their current state
    :return: A list of possible completions
    """
    if not current:
        # No word yet, so the current position is after the existing ones
        arg_idx = len(arguments)
    else:
        # Find the current word position
        arg_idx = arguments.index(current)

    # Find the ID of the next completer
    completers = config.completers
    if arg_idx > len(completers) - 1:
        # Argument is too far to be positional, try
        if config.multiple:
            # Multiple calls allowed for the last completer
            completer_id = completers[-1]
        else:
            # Nothing to return
            return []
    else:
        completer_id = completers[arg_idx]

    if completer_id == DUMMY:
        # Dummy completer: do nothing
        return []

    # Find the matching service
    svc_ref = context.get_service_reference(Completer, f"({PROP_COMPLETER_ID}={completer_id})")
    if svc_ref is None:
        # Handler not found
        _logger.debug("Unknown shell completer ID: %s", completer_id)
        return []

    # Call the completer
    try:
        with use_service(context, svc_ref) as completer:
            matches = completer.complete(config, prompt, session, context, arguments, current)
            if not matches:
                return []

            return matches
    except Exception as ex:
        _logger.exception("Error calling completer %s: %s", completer_id, ex)
        return []
