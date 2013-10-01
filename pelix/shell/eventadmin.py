#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
EventAdmin shell commands

Provides commands to the Pelix shell to work with the EventAdmin service

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.1.2
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

# Module version
__version_info__ = (0, 1, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# -----------------------------------------------------------------------------

# Shell constants
from pelix.shell import SHELL_COMMAND_SPEC

# iPOPO Decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Provides, \
    Instantiate
import pelix.services

# ------------------------------------------------------------------------------

@ComponentFactory("eventadmin-shell-commands-factory")
@Requires("_events", pelix.services.SERVICE_EVENT_ADMIN)
@Provides(SHELL_COMMAND_SPEC)
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
