#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Utility methods for SSL

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

import logging
import socket
import ssl
from typing import Optional

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def wrap_socket(
    socket: socket.socket, certfile: str, keyfile: str, password: Optional[str] = None
) -> socket.socket:
    """
    Wraps an existing TCP socket and returns an SSLSocket object

    :param socket: The socket to wrap
    :param certfile: The server certificate file
    :param keyfile: The server private key file
    :param password: Password for the private key file (Python >= 3.3)
    :return: The wrapped socket
    :raise SSLError: Error wrapping the socket / loading the certificate
    :raise OSError: A password has been given, but ciphered key files are not
                    supported by the current version of Python
    """
    # Log warnings when some
    logger = logging.getLogger("ssl_wrap")

    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)

    try:
        # Load the certificate, with a password
        context.load_cert_chain(certfile, keyfile, password)
    except TypeError:
        # The "password" argument isn't supported
        # Check support for key file password
        if password:
            logger.error(
                "The ssl.wrap_socket() fallback method doesn't " "support key files with a password."
            )
            raise OSError("Can't decode the SSL key file: " "this version of Python doesn't support it")

        # Load the certificate, without the password argument
        context.load_cert_chain(certfile, keyfile)

    # Return the wrapped socket
    return context.wrap_socket(socket, server_side=True)
