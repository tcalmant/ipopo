#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Event hook sample shell commands

Provides commands to the Pelix shell to generate some service events

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2023 Thomas Calmant

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

from typing import Callable, List, Optional, Tuple
from pelix.framework import BundleContext
import pelix.shell
from pelix.ipopo.decorators import (
    ComponentFactory,
    Provides,
    Instantiate,
    Validate,
)
from pelix.shell.beans import ShellSession

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"


# ------------------------------------------------------------------------------


@ComponentFactory()
@Provides(pelix.shell.ShellCommandsProvider)
@Instantiate("event-hook-shell-commands")
class EventHookCommands(pelix.shell.ShellCommandsProvider):
    """
    EventHook shell commands
    """

    _context: BundleContext

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        Component validated

        :param context: Bundle context
        """
        self._context = context

    @staticmethod
    def get_namespace() -> str:
        """
        Retrieves the name space of this command handler
        """
        return "hook"

    def get_methods(self) -> List[Tuple[str, pelix.shell.ShellCommandMethod]]:
        """
        Retrieves the list of tuples (command, method) for this command handler
        """
        return [
            ("gen_event", self.gen_event),
            ("gen_filtered_event", self.gen_filtered_event),
        ]

    def gen_event(self, session: ShellSession) -> None:
        """
        Generates a service event
        """
        session.write_line("Registering a new service...")
        self._context.register_service(
            "sample-service", object(), {"to_filter": False}
        )

    def gen_filtered_event(self, session: ShellSession) -> None:
        """
        Generates a service event that will be filtered by the event hook after
        its 3rd appearance
        """
        session.write_line(
            "Registering a new service to be filtered "
            "by the hook after the 3rd time..."
        )

        self._context.register_service(
            "sample-service", object(), {"to_filter": True}
        )
