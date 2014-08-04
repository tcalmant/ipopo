#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
IPv6 double stack utility module

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 0.5.7
:status: Beta

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

# Standard library
import os
import platform
import socket

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 5, 7)
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
        return socket.IPPROTO_IPV6
    except AttributeError:
        if os.name == 'nt':
            # Known bug: http://bugs.python.org/issue6926
            return 41
        else:
            # Unknown value
            raise


def set_double_stack(socket_obj, double_stack=True):
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
        if os.name == 'nt':
            # Windows: see ws2ipdef.h
            opt_ipv6_only = 27
        elif platform.system() == 'Linux':
            # Linux: see linux/in6.h (in recent kernels)
            opt_ipv6_only = 26
        else:
            # Unknown value: do nothing
            raise

    # Setup the socket (can raise a socket.error)
    socket_obj.setsockopt(ipproto_ipv6(), opt_ipv6_only, int(not double_stack))
