#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Utility methods for SSL

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.2

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
import ssl
from ssl import _RESTRICTED_SERVER_CIPHERS

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def wrap_socket(socket, certfile, keyfile, password=None):
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

    # The default context factory
    default_context = ssl.create_default_context()

    # Create an SSL context and set its options
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)

    # Copy options
    context.options = default_context.options

    # disallow ciphers with known vulnerabilities
    context.set_ciphers(_RESTRICTED_SERVER_CIPHERS)

    # Load the certificate, with a password
    context.load_cert_chain(certfile, keyfile, password)

    # Return the wrapped socket
    return context.wrap_socket(socket, server_side=True)
    