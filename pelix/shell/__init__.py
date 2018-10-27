#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix shell package

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

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

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

SERVICE_SHELL = "pelix.shell"
"""
Core shell service:

* register_command(ns, command, method): Registers a command in the given name
  space, executing the given method
* unregister(namespace, command): If command is given, unregisters it, else
  unregisters the whole given namespace
* execute(cmdline, stdin, stdout): Executes the given command line with the
  given input and output streams
"""

SERVICE_SHELL_COMMAND = "pelix.shell.command"
"""
Shell commands service, for auto-registration (white board pattern).

* get_namespace(): returns the name space of the handler
* get_methods(): returns a command name → method dictionary
"""

SERVICE_SHELL_UTILS = "pelix.shell.utilities"
"""
Shell utility service:

* make_table(headers, lines): to make ASCII arrays
* bundlestate_to_str(state): to get the string representation of a bundle state
"""

SERVICE_SHELL_REMOTE = "pelix.shell.remote"
"""
Remote shell service

* get_access(): returns the (host, port) tuple where the remote shell is
  waiting clients.
"""

SERVICE_SHELL_REPORT = "pelix.shell.report"
"""
Report command service: gives access to the report methods for a future reuse

* get_levels():  Returns a copy of the dictionary of levels. The key is the
  name of the report level, the value is the tuple of methods to call for that
  level. Multiple levels can call the same method. The methods take no argument
  and return a dictionary.
* to_json(dict): Converts a dictionary to JSON, replacing inconvertible values
  to their string representation.
"""

# ------------------------------------------------------------------------------
# Temporary constants, for compatibility with previous shell developments

SHELL_SERVICE_SPEC = SERVICE_SHELL
""" Compatibility constant """

SHELL_COMMAND_SPEC = SERVICE_SHELL_COMMAND
""" Compatibility constant """

SHELL_UTILS_SERVICE_SPEC = SERVICE_SHELL_UTILS
""" Compatibility constant """

REMOTE_SHELL_SPEC = SERVICE_SHELL_REMOTE
""" Compatibility constant """

# ------------------------------------------------------------------------------

FACTORY_REMOTE_SHELL = "ipopo-remote-shell-factory"
""" Name of remote shell component factory """

FACTORY_XMPP_SHELL = "ipopo-xmpp-shell-factory"
""" Name of XMPP shell component factory """
