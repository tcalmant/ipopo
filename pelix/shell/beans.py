#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Definition of classes used by the Pelix shell service and its consumers

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.3.0
:status: Alpha

..

    Copyright 2026 Thomas Calmant

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

import getpass
import os
import sys
import threading
from collections.abc import Callable
from io import IOBase
from typing import IO, Any, cast

from pelix.security import ANONYMOUS, Secret, Subject
from pelix.utilities import to_bytes, to_str

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["METHOD_LOCAL", "RESULT_VAR_NAME", "IOHandler", "ShellSession", "make_local_subject"]

# ------------------------------------------------------------------------------

RESULT_VAR_NAME = "?"
""" Name of the result variable """

METHOD_LOCAL = "local"
""" Authentication method of a user the operating system identified: the console, a Unix socket """


def make_local_subject(transport: str, uid: int | None = None) -> Subject:
    """
    Makes the subject of a local user, named after its operating system account.

    The name comes from the account database rather than from ``getpass.getuser()``,
    which trusts the ``USER`` environment variable.

    :param transport: Name of the shell front end
    :param uid: The user ID, None for the effective user of the process
    :return: The authenticated subject
    """
    try:
        import pwd

        name = pwd.getpwuid(os.geteuid() if uid is None else uid).pw_name
    except (ImportError, KeyError):
        # No account database (Windows), or a user without an entry (containers)
        name = getpass.getuser() if uid is None else f"uid:{uid}"

    return Subject(name, authenticated=True, method=METHOD_LOCAL, transport=transport)


# ------------------------------------------------------------------------------


class ShellSession:
    """
    Represents a shell session. This is the kind of object given as parameter
    to shell commands
    """

    def __init__(
        self,
        io_handler: "IOHandler",
        initial_vars: dict[str, Any] | None = None,
        subject: Subject | None = None,
        trusted: bool = False,
    ) -> None:
        """
        Sets up the shell session

        :param io_handler:  The I/O handler associated to the session
        :param initial_vars: Initial variables
        :param subject: Who the front end authenticated, None for the anonymous subject
        :param trusted: A local session, run by the user of the process: no permission is
                        checked. Only for the console and the like, never for input coming
                        from the network
        """
        # Store parameters
        self._io_handler = io_handler

        # Not a session variable: those can be changed by the "set" command
        self.__subject = subject if subject is not None else ANONYMOUS
        self.__trusted = trusted

        if not isinstance(initial_vars, dict):
            initial_vars = {}
        self.__variables = initial_vars.copy()

        # Special variable for the last result
        self.__variables[RESULT_VAR_NAME] = None

    def prompt(self, prompt: str | None = None) -> str:
        """
        Reads a line written by the user

        :param prompt: An optional prompt message
        :return: The read line, after a conversion to str
        """
        return self._io_handler.prompt(prompt)

    def prompt_secret(self, prompt: str | None = None) -> Secret[str]:
        """
        Reads a secret written by the user, like a password, without echoing it when the
        front end allows it: the console does, the remote and XMPP shells can't

        :param prompt: An optional prompt message
        :return: The read line, without its end of line, as a secret
        :raise EOFError: The front end has no input, or it has been closed: the shell
                         reports it as the error of the command
        """
        return self._io_handler.prompt_secret(prompt)

    def write(self, data: str) -> None:
        """
        Write data to the output
        """
        self._io_handler.write(data)

    def write_line(self, line: str | None = None, *args: Any, **kwargs: Any) -> None:
        """
        Formats and writes a line to the output
        """
        self._io_handler.write_line(line, *args, **kwargs)

    def write_line_no_feed(self, line: str | None = None, *args: Any, **kwargs: Any) -> None:
        """
        Formats and writes a line to the output
        """
        self._io_handler.write_line_no_feed(line, *args, **kwargs)

    def flush(self) -> None:
        """
        Flush output
        """
        self._io_handler.flush()

    @property
    def subject(self) -> Subject:
        """
        Who the front end authenticated, for the whole session: the anonymous subject
        when it authenticated nobody
        """
        return self.__subject

    @property
    def trusted(self) -> bool:
        """
        Tells whether this is a local session, where no permission is checked
        """
        return self.__trusted

    @property
    def variables(self) -> dict[str, Any]:
        """
        A copy of the session variables
        """
        return self.__variables.copy()

    @property
    def last_result(self) -> Any:
        """
        Returns the content of $result
        """
        return self.__variables[RESULT_VAR_NAME]

    def get(self, name: str) -> Any:
        """
        Returns the value of a variable

        :param name: Name of the variable
        :return: The value of the variable
        :raise KeyError: Unknown name
        """
        return self.__variables[name]

    def set(self, name: str, value: Any) -> None:
        """
        Sets/overrides the value of a variable

        :param name: Variable name
        :param value: New value
        """
        self.__variables[name] = value

    def unset(self, name: str) -> None:
        """
        Unsets the variable with the given name

        :param name: Variable name
        :raise KeyError: Unknown name
        """
        del self.__variables[name]


# ------------------------------------------------------------------------------


class IOHandler:
    """
    Handles I/O operations between the command handler and the client
    It automatically converts the given data to bytes in Python 3.
    """

    def __init__(
        self,
        in_stream: None | IOBase | IO[str] | IO[bytes],
        out_stream: IOBase | IO[str] | IO[bytes],
        encoding: str = "UTF-8",
    ) -> None:
        """
        Sets up the printer

        :param in_stream: Input stream
        :param out_stream: Output stream
        :param encoding: Output encoding
        """
        self.input: None | IOBase | IO[str] | IO[bytes] = in_stream
        self.output: IOBase | IO[str] | IO[bytes] = out_stream
        self.encoding = encoding
        self.out_encoding: str = getattr(self.output, "encoding", self.encoding) or self.encoding

        # Thread safety
        self.__lock = threading.RLock()

        # Standard behavior
        self.flush = self.output.flush

        # In Python 3.6, the "mode" field is not available on file-like
        # objects, but the "encoding" field seems to be present only in
        # string compatible ones
        if "b" in getattr(out_stream, "mode", "") or not hasattr(out_stream, "encoding"):
            # Bytes conversion
            self.write = cast(Callable[[str | bytes], int], self._write_bytes)
        else:
            # Strings accepted
            self.write = cast(Callable[[str | bytes], int], self._write_str)

        # Very specific
        if in_stream is sys.stdin:
            # Warning: conflicts with the console
            self.prompt = self._real_prompt
            self.prompt_secret = self._real_prompt_secret
        else:
            self.prompt = self._prompt
            self.prompt_secret = self._prompt_secret

    def _real_prompt(self, prompt: bytes | str | None = None) -> str:
        """
        Reads a line written by the user

        :param prompt: An optional prompt message
        :return: The read line, after a conversion to str
        """
        return input(prompt)

    def _real_prompt_secret(self, prompt: str | None = None) -> Secret[str]:
        """
        Reads a secret on the terminal, without echo

        :param prompt: An optional prompt message
        :return: The read line, as a secret
        """
        return Secret(getpass.getpass(prompt or "Password: "))

    def _prompt_secret(self, prompt: str | None = None) -> Secret[str]:
        """
        Reads a secret from the input stream: a stream has no echo control, the client
        shows what it sends

        :param prompt: An optional prompt message
        :return: The read line, without its end of line, as a secret
        :raise EOFError: No input stream, or end of the stream
        """
        line = self._prompt(prompt)
        if not line:
            # Not even an end of line: an empty secret would be taken as typed
            raise EOFError("No input to read a secret from")

        # Only the end of line is removed: a password may start or end with a space
        return Secret(line.rstrip("\r\n"))

    def _prompt(self, prompt: bytes | str | None = None) -> str:
        """
        Reads a line written by the user

        :param prompt: An optional prompt message
        :return: The read line, after a conversion to str
        """
        if prompt:
            # Print the prompt
            self.write(prompt)
            self.output.flush()

        if self.input is None:
            return ""

        # Read the line
        return to_str(self.input.readline())

    def _write_bytes(self, data: bytes | str | None) -> None:
        """
        Converts the given data then writes it

        :param data: Data to be written
        :return: The result of ``self.output.write()``
        """
        if data is not None:
            with self.__lock:
                cast(IO[bytes], self.output).write(to_bytes(data, self.encoding))

    def _write_str(self, data: str | bytes | None) -> None:
        """
        Converts the given data then writes it

        :param data: Data to be written
        :return: The result of ``self.output.write()``
        """
        if data is not None:
            with self.__lock:
                cast(IO[str], self.output).write(
                    to_str(data, self.encoding).encode().decode(self.out_encoding, errors="replace")
                )

    def write_line(self, line: str | None = None, *args: Any, **kwargs: Any) -> None:
        """
        Formats and writes a line to the output
        """
        if line is None:
            # Empty line
            self.write("\n")
        else:
            # Format the line, if arguments have been given
            if args or kwargs:
                line = line.format(*args, **kwargs)

            with self.__lock:
                # Write it
                self.write(line)
                try:
                    if line[-1] != "\n":
                        # Add the trailing new line
                        self.write("\n")
                except IndexError:
                    # Got an empty string
                    self.write("\n")

        self.flush()

    def write_line_no_feed(self, line: str | None = None, *args: Any, **kwargs: Any) -> None:
        """
        Formats and writes a line to the output
        """
        if line is None:
            # Empty line
            line = ""
        else:
            # Format the line, if arguments have been given
            if args or kwargs:
                line = line.format(*args, **kwargs)

            # Remove the trailing line feed (if the line is not empty)
            if line and line[-1] == "\n":
                line = line[:-1]

        # Write it
        self.write(line)
        self.flush()
