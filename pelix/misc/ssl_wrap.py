#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Utility methods for SSL

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
import ssl

try:
    from ssl import _RESTRICTED_SERVER_CIPHERS
except ImportError:
    # Restricted and more secure ciphers for the server side, from Python 3.5
    _RESTRICTED_SERVER_CIPHERS = (
        "ECDH+AESGCM:DH+AESGCM:ECDH+AES256:DH+AES256:ECDH+AES128:DH+AES:"
        "ECDH+HIGH:DH+HIGH:ECDH+3DES:DH+3DES:RSA+AESGCM:RSA+AES:RSA+HIGH:"
        "RSA+3DES:!aNULL:!eNULL:!MD5:!DSS:!RC4"
    )

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
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

    def _password_support_error():
        """
        Logs a warning and raises an OSError if a password has been given but
        Python doesn't support ciphered key files.

        :raise OSError: If a password has been given
        """
        if password:
            logger.error(
                "The ssl.wrap_socket() fallback method doesn't "
                "support key files with a password."
            )
            raise OSError(
                "Can't decode the SSL key file: "
                "this version of Python doesn't support it"
            )

    try:
        # Prefer the default context factory, as it will be updated to reflect
        # security issues (Python >= 2.7.9 and >= 3.4)
        default_context = ssl.create_default_context()
    except AttributeError:
        default_context = None

    try:
        # Try to equivalent to create_default_context() in Python 3.5
        # Create an SSL context and set its options
        context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)

        if default_context is not None:
            # Copy options
            context.options = default_context.options
        else:
            # Set up the context as create_default_context() does in Python 3.5
            # SSLv2 considered harmful
            # SSLv3 has problematic security
            context.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3

        # disallow ciphers with known vulnerabilities
        context.set_ciphers(_RESTRICTED_SERVER_CIPHERS)

        try:
            # Load the certificate, with a password
            context.load_cert_chain(certfile, keyfile, password)
        except TypeError:
            # The "password" argument isn't supported
            # Check support for key file password
            _password_support_error()

            # Load the certificate, without the password argument
            context.load_cert_chain(certfile, keyfile)

        # Return the wrapped socket
        return context.wrap_socket(socket, server_side=True)

    except AttributeError as ex:
        # Log a warning to advise the user of possible security holes
        logger.warning(
            "Can't create a custom SSLContext. "
            "The server should be considered insecure."
        )
        logger.debug("Missing attribute: %s", ex)

    # Check support for key file password
    _password_support_error()

    # Fall back to the "old" wrap_socket method
    return ssl.wrap_socket(
        socket, server_side=True, certfile=certfile, keyfile=keyfile
    )
