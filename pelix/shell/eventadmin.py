#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
EventAdmin shell commands

Provides commands to the Pelix shell to work with the EventAdmin service

:author: Thomas Calmant
:copyright: Copyright 2015, isandlaTech
:license: Apache License 2.0
:version: 0.5.9
:status: Beta

..

    Copyright 2015 isandlaTech

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
__version_info__ = (0, 5, 9)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# -----------------------------------------------------------------------------

# Shell constants
from pelix.shell import SERVICE_SHELL_COMMAND

# iPOPO Decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Provides, \
    Instantiate
import pelix.services

# ------------------------------------------------------------------------------


@ComponentFactory("eventadmin-shell-commands-factory")
@Requires("_events", pelix.services.SERVICE_EVENT_ADMIN)
@Provides(SERVICE_SHELL_COMMAND)
@Instantiate("eventadmin-shell-commands")
class EventAdminCommands(object):
    """
    EventAdmin shell commands
    """
    def __init__(self):
        """
        Sets up members
        """
        # Injected services
        self._events = None

    def get_namespace(self):
        """
        Retrieves the name space of this command handler
        """
        return "event"

    def get_methods(self):
        """
        Retrieves the list of tuples (command, method) for this command handler
        """
        return [("send", self.send),
                ("post", self.post)]

    def send(self, io_handler, topic, **kwargs):
        """
        Sends an event (blocking)
        """
        self._events.send(topic, kwargs)

    def post(self, io_handler, topic, **kwargs):
        """
        Posts an event (asynchronous)
        """
        self._events.post(topic, kwargs)
