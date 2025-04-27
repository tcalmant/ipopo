#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Pelix shell completion package

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

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Protocol

from pelix.constants import Specification

if TYPE_CHECKING:
    from pelix.framework import BundleContext
    from pelix.shell.beans import ShellSession

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

DUMMY = "dummy"
""" Completer ID: a completer that does nothing """

BUNDLE = "pelix.bundle"
""" Completer ID: Pelix Bundle ID completer """

SERVICE = "pelix.service"
""" Completer ID: Pelix Service ID completer """

FACTORY = "ipopo.factory"
""" Completer ID: iPOPO Factory Name completer """

FACTORY_PROPERTY = "ipopo.factory.property"
""" Completer ID: iPOPO Property Name completer """

COMPONENT = "ipopo.component"
""" Completer ID: iPOPO Component Name completer """

# ------------------------------------------------------------------------------

SVC_COMPLETER = "pelix.shell.completer"
""" Specification of a completer service """

PROP_COMPLETER_ID = "completer.id"
""" Completer service property: ID of the completer """

ATTR_COMPLETERS = "__pelix_shell_completers__"
""" Attribute added to methods to keep the list of completers """


@dataclass(frozen=True)
class CompletionInfo:
    """
    Keep track of the configuration of a completion
    """

    completers: List[str]
    """
    List of IDs of shell completers
    """

    multiple: bool
    """
    Flag indicating of the last completer can be reused multiple times
    """


@Specification(SVC_COMPLETER)
class Completer(Protocol):
    """
    Specification of a service providing completions
    """

    def complete(
        self,
        config: CompletionInfo,
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
        ...
