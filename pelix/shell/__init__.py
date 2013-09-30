#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix shell package

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
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

# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

SHELL_SERVICE_SPEC = "pelix.shell"
"""
Core shell service:

* register_command(ns, command, method): Registers a command in the given name
  space, executing the given method
* unregister(namespace, command): If command is given, unregisters it, else
  unregisters the whole given namespace
* execute(cmdline, stdin, stdout): Executes the given command line with the
  given input and output streams
"""

SHELL_COMMAND_SPEC = "pelix.shell.command"
"""
Shell commands service, for auto-registration (white board pattern).

* get_namespace(): returns the name space of the handler
* get_methods(): returns a command name -> method dictionary
"""

SHELL_UTILS_SERVICE_SPEC = "pelix.shell.utilities"
"""
Shell utility service:

* make_table(headers, lines): to make ASCII arrays
* bundlestate_to_str(state): to get the string representation of a bundle state
"""

REMOTE_SHELL_SPEC = "pelix.shell.remote"
"""
Remote shell service

* get_access(): returns the (host, port) tuple where the remote shell is waiting
  clients.
"""

# ------------------------------------------------------------------------------

FACTORY_REMOTE_SHELL = "ipopo-remote-shell-factory"
""" Name of remote shell component factory """
