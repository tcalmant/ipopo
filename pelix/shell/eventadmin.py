#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
EventAdmin shell commands

Provides commands to the Pelix shell to work with the EventAdmin service

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0

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

from typing import TYPE_CHECKING, Any, List, Tuple

import pelix.services
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Provides, Requires
from pelix.shell import ShellCommandMethod, ShellCommandsProvider

if TYPE_CHECKING:
    from pelix.shell.beans import ShellSession


# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# -----------------------------------------------------------------------------


@ComponentFactory("eventadmin-shell-commands-factory")
@Requires("_events", pelix.services.EventAdmin)
@Provides(ShellCommandsProvider)
@Instantiate("eventadmin-shell-commands")
class EventAdminCommands(ShellCommandsProvider):
    """
    EventAdmin shell commands
    """

    # Injected services
    _events: pelix.services.EventAdmin

    def get_namespace(self) -> str:
        """
        Retrieves the name space of this command handler
        """
        return "event"

    def get_methods(self) -> List[Tuple[str, ShellCommandMethod]]:
        """
        Retrieves the list of tuples (command, method) for this command handler
        """
        return [("send", self.send), ("post", self.post)]

    def send(self, _: "ShellSession", topic: str, **kwargs: Any) -> None:
        """
        Sends an event (blocking)
        """
        self._events.send(topic, kwargs)

    def post(self, _: "ShellSession", topic: str, **kwargs: Any) -> None:
        """
        Posts an event (asynchronous)
        """
        self._events.post(topic, kwargs)
