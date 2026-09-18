#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the IPv6 utility methods

:author: Thomas Calmant
"""

import socket
import types
import unittest
from typing import Any, cast
from unittest import mock

from pelix import ipv6utils

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class RecordingSocket:
    """
    Socket stand-in recording the options it is given
    """

    def __init__(self) -> None:
        self.options: list[tuple[int, int, int]] = []

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.options.append((level, option, value))


def fake_system(os_name: str = "posix", system: str = "Linux", **socket_attrs: Any) -> Any:
    """
    Patches the modules used by ipv6utils to simulate another system

    :param os_name: Value of os.name
    :param system: Value of platform.system()
    :param socket_attrs: Constants provided by the socket module
    """
    return mock.patch.multiple(
        ipv6utils,
        os=types.SimpleNamespace(name=os_name),
        platform=types.SimpleNamespace(system=lambda: system),
        socket=types.SimpleNamespace(**socket_attrs),
    )


class Ipv6UtilsTest(unittest.TestCase):
    """
    Tests the IPv6 utility methods
    """

    def test_ipproto_ipv6(self) -> None:
        """
        The socket constant is used when available, with a fallback on
        Windows only
        """
        self.assertEqual(socket.IPPROTO_IPV6, ipv6utils.ipproto_ipv6())

        with fake_system(IPPROTO_IPV6=1234):
            self.assertEqual(1234, ipv6utils.ipproto_ipv6())

        with fake_system("nt"):
            self.assertEqual(41, ipv6utils.ipproto_ipv6())

        with fake_system("posix"), self.assertRaises(AttributeError):
            ipv6utils.ipproto_ipv6()

    def test_double_stack_option(self) -> None:
        """
        The IPV6_V6ONLY option is the opposite of the double stack flag
        """
        for double_stack, expected in ((True, 0), (False, 1)):
            sock = RecordingSocket()
            with fake_system(IPPROTO_IPV6=41, IPV6_V6ONLY=26):
                ipv6utils.set_double_stack(cast(socket.socket, sock), double_stack)
            self.assertEqual([(41, 26, expected)], sock.options)

    def test_double_stack_fallback(self) -> None:
        """
        Known option values are used when the socket module lacks them
        """
        for os_name, system, expected in (("nt", "Windows", 27), ("posix", "Linux", 26)):
            sock = RecordingSocket()
            with fake_system(os_name, system, IPPROTO_IPV6=41):
                ipv6utils.set_double_stack(cast(socket.socket, sock))
            self.assertEqual([(41, expected, 0)], sock.options)

        # Unknown system: nothing is done
        sock = RecordingSocket()
        with fake_system("posix", "Darwin", IPPROTO_IPV6=41), self.assertRaises(AttributeError):
            ipv6utils.set_double_stack(cast(socket.socket, sock))
        self.assertEqual([], sock.options)

    def test_real_socket(self) -> None:
        """
        Applies the double stack option on a real IPv6 socket
        """
        try:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        except OSError as ex:
            self.skipTest(f"IPv6 not supported: {ex}")

        with sock:
            for double_stack, expected in ((False, 1), (True, 0)):
                ipv6utils.set_double_stack(sock, double_stack)
                self.assertEqual(expected, sock.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY))


if __name__ == "__main__":
    unittest.main()
