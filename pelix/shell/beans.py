#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Definition of classes used by the Pelix shell service and its consumers

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

import sys
import threading
from typing import IO, Any, Callable, Dict, Optional, Union, cast

from pelix.utilities import to_bytes, to_str

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

RESULT_VAR_NAME = "?"
""" Name of the result variable """

# ------------------------------------------------------------------------------


class ShellSession:
    """
    Represents a shell session. This is the kind of object given as parameter
    to shell commands
    """

    def __init__(self, io_handler: "IOHandler", initial_vars: Optional[Dict[str, Any]] = None) -> None:
        """
        Sets up the shell session

        :param io_handler:  The I/O handler associated to the session
        :param initial_vars: Initial variables
        """
        # Store parameters
        self._io_handler = io_handler

        if not isinstance(initial_vars, dict):
            initial_vars = {}
        self.__variables = initial_vars.copy()

        # Special variable for the last result
        self.__variables[RESULT_VAR_NAME] = None

    def prompt(self, prompt: Optional[str] = None) -> str:
        """
        Reads a line written by the user

        :param prompt: An optional prompt message
        :return: The read line, after a conversion to str
        """
        return self._io_handler.prompt(prompt)

    def write(self, data: str) -> None:
        """
        Write data to the output
        """
        self._io_handler.write(data)

    def write_line(self, line: Optional[str] = None, *args: Any, **kwargs: Any) -> None:
        """
        Formats and writes a line to the output
        """
        self._io_handler.write_line(line, *args, **kwargs)

    def write_line_no_feed(self, line: Optional[str] = None, *args: Any, **kwargs: Any) -> None:
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
    def variables(self) -> Dict[str, Any]:
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
        in_stream: Union[None, IO[bytes], IO[str]],
        out_stream: Union[IO[bytes], IO[str]],
        encoding: str = "UTF-8",
    ) -> None:
        """
        Sets up the printer

        :param in_stream: Input stream
        :param out_stream: Output stream
        :param encoding: Output encoding
        """
        self.input: Union[None, IO[bytes], IO[str]] = in_stream
        self.output: Union[IO[bytes], IO[str]] = out_stream
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
            self.write = cast(Callable[[Union[str, bytes]], int], self._write_bytes)
        else:
            # Strings accepted
            self.write = cast(Callable[[Union[str, bytes]], int], self._write_str)

        # Very specific
        if in_stream is sys.stdin:
            # Warning: conflicts with the console
            self.prompt = self._real_prompt
        else:
            self.prompt = self._prompt

    def _real_prompt(self, prompt: Optional[Union[bytes, str]] = None) -> str:
        """
        Reads a line written by the user

        :param prompt: An optional prompt message
        :return: The read line, after a conversion to str
        """
        return input(prompt)

    def _prompt(self, prompt: Optional[Union[bytes, str]] = None) -> str:
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

    def _write_bytes(self, data: Optional[Union[bytes, str]]) -> None:
        """
        Converts the given data then writes it

        :param data: Data to be written
        :return: The result of ``self.output.write()``
        """
        if data is not None:
            with self.__lock:
                cast(IO[bytes], self.output).write(to_bytes(data, self.encoding))

    def _write_str(self, data: Optional[Union[str, bytes]]) -> None:
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

    def write_line(self, line: Optional[str] = None, *args: Any, **kwargs: Any) -> None:
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

    def write_line_no_feed(self, line: Optional[str] = None, *args: Any, **kwargs: Any) -> None:
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

            # Remove the trailing line feed
            if line[-1] == "\n":
                line = line[:-1]

        # Write it
        self.write(line)
        self.flush()
