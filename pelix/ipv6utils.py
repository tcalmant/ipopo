#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
IPv6 double stack utility module

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
import os
import platform
import socket

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def ipproto_ipv6():
    """
    Returns the value of socket.IPPROTO_IPV6

    :return: The value of socket.IPPROTO_IPV6
    :raise AttributeError: Python or system doesn't support IPv6
    """
    try:
        # pylint: disable=E1101
        return socket.IPPROTO_IPV6
    except AttributeError:
        if os.name == "nt":
            # Known bug: http://bugs.python.org/issue6926
            return 41
        else:
            # Unknown value
            raise


def set_double_stack(socket_obj, double_stack=True):
    # type: (socket.socket, bool) -> None
    """
    Sets up the IPv6 double stack according to the operating system

    :param socket_obj: A socket object
    :param double_stack: If True, use the double stack, else only support IPv6
    :raise AttributeError: Python or system doesn't support V6
    :raise socket.error: Error setting up the double stack value
    """
    try:
        # Use existing value
        opt_ipv6_only = socket.IPV6_V6ONLY
    except AttributeError:
        # Use "known" value
        if os.name == "nt":
            # Windows: see ws2ipdef.h
            opt_ipv6_only = 27
        elif platform.system() == "Linux":
            # Linux: see linux/in6.h (in recent kernels)
            opt_ipv6_only = 26
        else:
            # Unknown value: do nothing
            raise

    # Setup the socket (can raise a socket.error)
    socket_obj.setsockopt(ipproto_ipv6(), opt_ipv6_only, int(not double_stack))
