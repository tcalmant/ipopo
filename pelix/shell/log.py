#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Shell commands for the log service

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

# Standard library
import logging

# Pelix
from pelix.ipopo.decorators import (
    ComponentFactory,
    Requires,
    Provides,
    Instantiate,
    PostRegistration,
)
from pelix.misc import LOG_SERVICE, LOG_READER_SERVICE
from pelix.shell import SERVICE_SHELL_COMMAND

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


@ComponentFactory("pelix-shell-log-factory")
@Provides(SERVICE_SHELL_COMMAND)
@Requires("_logger", LOG_SERVICE, optional=True)
@Requires("_reader", LOG_READER_SERVICE, optional=True)
@Instantiate("pelix-shell-log")
class ShellLogCommand(object):
    """
    Provides shell commands to print the content of the log service
    """

    def __init__(self):
        """
        Sets up members
        """
        self._logger = None
        self._reader = None
        self.__svc_ref = None

    @PostRegistration
    def _post_register(self, svc_ref):
        """
        Called when the service has been provided
        """
        self.__svc_ref = svc_ref

    @staticmethod
    def get_namespace():
        """
        Returns the name space of the commands
        """
        return "log"

    def get_methods(self):
        """
        Returns the methods of the shell command
        """
        return [
            ("log", self._log),
            ("debug", self._debug),
            ("info", self._info),
            ("warn", self._warning),
            ("warning", self._warning),
            ("error", self._error),
        ]

    def _log(self, session, level="WARNING", count=None):
        """
        Prints the content of the log
        """
        if self._reader is None:
            session.write_line("No LogService available.")
            return

        # Normalize arguments
        if isinstance(level, str):
            level = logging.getLevelName(level.upper())

        if not isinstance(level, int):
            level = logging.WARNING

        if count is not None:
            try:
                safe_count = int(count)
            except (TypeError, ValueError):
                safe_count = 0
        else:
            safe_count = 0

        # Filter the entries and keep the last ones only
        try:
            for entry in [
                entry
                for entry in self._reader.get_log()
                if entry.level >= level
            ][-safe_count:]:
                session.write_line(str(entry))
        except StopIteration:
            pass

    def _trace(self, session, level, words):
        """
        Logs a message using the log service

        :param session: The shell Session object
        :param level: Log level (string)
        :param words: Message to log
        """
        if self._logger is not None:
            self._logger.log(
                level,
                " ".join(str(word) for word in words),
                None,
                self.__svc_ref,
            )
        else:
            session.write_line("No LogService available.")

    def _debug(self, session, *message):
        """
        Logs a trace
        """
        self._trace(session, logging.DEBUG, message)

    def _info(self, session, *message):
        """
        Logs an informative message
        """
        self._trace(session, logging.INFO, message)

    def _warning(self, session, *message):
        """
        Logs a warning message
        """
        self._trace(session, logging.WARNING, message)

    def _error(self, session, *message):
        """
        Logs an informative message
        """
        self._trace(session, logging.ERROR, message)
