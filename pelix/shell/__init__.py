#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix shell package

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.1
:status: Beta

..

    Copyright 2013 isandlaTech

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
