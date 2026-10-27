#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the remote shell on a Unix domain socket

:author: Thomas Calmant
"""

import os
import pathlib
import shutil
import socket
import stat
import sys
import tempfile
import threading
import unittest
from typing import Any, cast
from unittest import mock

from pelix.framework import Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.instance import StoredInstance
from pelix.shell import FACTORY_REMOTE_SHELL
from pelix.shell.remote import (
    PROP_UNIX_CHECK_PEER,
    PROP_UNIX_PATH,
    UNIX_SOCKET_MODE,
    IPopoRemoteShell,
    ThreadingUnixServer,
    main,
)
from pelix.utilities import to_bytes, to_str

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------

PS1 = "$ "

if sys.platform == "win32" or not hasattr(socket, "AF_UNIX"):
    raise unittest.SkipTest("Unix sockets are not available")


def read_until(sock: socket.socket, marker: str) -> str:
    """
    Reads until the marker is received

    :return: Everything received
    """
    sock.settimeout(10)
    received = ""
    while marker not in received:
        data = sock.recv(4096)
        if not data:
            raise AssertionError(f"Connection closed before {marker!r}. Got: {received!r}")

        received += to_str(data)

    return received


class RemoteShellUnixTest(unittest.TestCase):
    """
    Tests the remote shell listening on a Unix socket
    """

    framework: Framework
    folder: pathlib.Path

    def setUp(self) -> None:
        # Short path: the length of a socket path is limited (104 on macOS)
        self.folder = pathlib.Path(tempfile.mkdtemp(prefix="ipsh"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

        self.framework = create_framework(("pelix.ipopo.core", "pelix.shell.core", "pelix.shell.remote"))
        self.framework.start()
        self.context = self.framework.get_bundle_context()

    def tearDown(self) -> None:
        try:
            self.framework.stop()
        finally:
            FrameworkFactory.delete_framework()

    def start_shell(self, properties: dict[str, Any]) -> IPopoRemoteShell:
        with use_ipopo(self.context) as ipopo:
            return cast(IPopoRemoteShell, ipopo.instantiate(FACTORY_REMOTE_SHELL, "remote-shell", properties))

    def connect(self, path: pathlib.Path) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        sock.settimeout(10)
        sock.connect(str(path))
        read_until(sock, PS1)
        return sock

    def get_state(self) -> int:
        with use_ipopo(self.context) as ipopo:
            return ipopo.get_instance_details("remote-shell")["state"]

    def is_valid(self) -> bool:
        return self.get_state() == StoredInstance.VALID

    def test_session(self) -> None:
        """
        A client runs a command over the socket
        """
        path = self.folder / "shell.sock"
        shell = self.start_shell({PROP_UNIX_PATH: str(path)})
        self.assertEqual(shell.get_access(), (str(path), None))
        self.assertTrue(shell.is_unix())

        # Only the owner can connect or change the socket
        self.assertEqual(stat.S_IMODE(path.lstat().st_mode), UNIX_SOCKET_MODE)

        sock = self.connect(path)
        sock.sendall(to_bytes("echo hello\n"))
        self.assertIn("hello", read_until(sock, PS1))

    def test_no_tcp_when_unix(self) -> None:
        """
        The address and port are not used when a Unix socket is configured
        """
        path = self.folder / "shell.sock"
        self.start_shell(
            {PROP_UNIX_PATH: str(path), "pelix.shell.port": 1, "pelix.shell.address": "nowhere.invalid"}
        )
        self.assertTrue(self.is_valid())

    def test_removed_on_stop(self) -> None:
        """
        The socket file is removed when the shell stops
        """
        path = self.folder / "shell.sock"
        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.assertTrue(path.exists())

        with use_ipopo(self.context) as ipopo:
            ipopo.kill("remote-shell")

        self.assertFalse(path.exists())

    def test_stop_keeps_a_replaced_socket(self) -> None:
        """
        A socket file which is not ours any more is not removed
        """
        path = self.folder / "shell.sock"
        self.start_shell({PROP_UNIX_PATH: str(path)})
        path.unlink()
        path.write_text("someone else")

        with use_ipopo(self.context) as ipopo:
            ipopo.kill("remote-shell")

        self.assertEqual(path.read_text(), "someone else")

    def test_stale_socket_removed(self) -> None:
        """
        The socket file left by a crashed server is replaced
        """
        path = self.folder / "shell.sock"
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(path))
        # Closed without unlink: nobody listens, the file remains
        stale.close()
        self.assertTrue(path.exists())

        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.connect(path)

    def test_regular_file_not_removed(self) -> None:
        """
        A file which is not a socket is never removed: the shell doesn't start
        """
        path = self.folder / "shell.sock"
        path.write_text("precious")

        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.assertEqual(self.get_state(), StoredInstance.ERRONEOUS)
        self.assertEqual(path.read_text(), "precious")

    def test_symlink_not_removed(self) -> None:
        """
        A symbolic link is never followed nor removed
        """
        target = self.folder / "target"
        target.write_text("precious")
        path = self.folder / "shell.sock"
        path.symlink_to(target)

        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.assertEqual(self.get_state(), StoredInstance.ERRONEOUS)
        self.assertTrue(path.is_symlink())
        self.assertEqual(target.read_text(), "precious")

    def test_live_socket_not_removed(self) -> None:
        """
        The socket of a running server is not taken over
        """
        path = self.folder / "shell.sock"
        other = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(other.close)
        other.bind(str(path))
        other.listen(1)

        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.assertEqual(self.get_state(), StoredInstance.ERRONEOUS)
        self.assertTrue(path.exists())

    def test_unsafe_folder(self) -> None:
        """
        A folder others can write in (without sticky bit) is refused
        """
        self.folder.chmod(0o777)
        path = self.folder / "shell.sock"

        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.assertEqual(self.get_state(), StoredInstance.ERRONEOUS)
        self.assertFalse(path.exists())

        # Same folder with the sticky bit, like /tmp: accepted
        self.folder.chmod(0o1777)
        with use_ipopo(self.context) as ipopo:
            ipopo.kill("remote-shell")
        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.assertTrue(self.is_valid())

    def test_tls_refused(self) -> None:
        """
        TLS properties can't be used with a Unix socket
        """
        path = self.folder / "shell.sock"
        for prop in ("ssl.ca", "ssl.cert", "ssl.key", "ssl.key_password"):
            with self.subTest(prop=prop):
                self.start_shell({PROP_UNIX_PATH: str(path), f"pelix.shell.{prop}": "/nonexistent"})
                self.assertEqual(self.get_state(), StoredInstance.ERRONEOUS)
                self.assertFalse(path.exists())

                with use_ipopo(self.context) as ipopo:
                    error = ipopo.get_instance_details("remote-shell")["error_trace"]
                    self.assertIn("cannot be used with", error)
                    ipopo.kill("remote-shell")

    def test_peer_check(self) -> None:
        """
        A client of another user is refused (simulated: the server believes it is another user)
        """
        if not hasattr(socket, "SO_PEERCRED"):
            self.skipTest("The system doesn't tell the user of a client")

        real_uid = os.geteuid()
        if real_uid == 0:
            self.skipTest("root is always accepted")

        path = self.folder / "shell.sock"
        self.start_shell({PROP_UNIX_PATH: str(path)})

        with mock.patch("os.geteuid", return_value=real_uid + 1):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(sock.close)
            sock.settimeout(10)
            sock.connect(str(path))
            # Closed without a word
            self.assertEqual(sock.recv(4096), b"")

        # Same client, with the check disabled
        with use_ipopo(self.context) as ipopo:
            ipopo.kill("remote-shell")

        self.start_shell({PROP_UNIX_PATH: str(path), PROP_UNIX_CHECK_PEER: False})
        with mock.patch("os.geteuid", return_value=real_uid + 1):
            self.connect(path)

    def test_peer_accepted(self) -> None:
        """
        A client of the same user is accepted with the check enabled
        """
        path = self.folder / "shell.sock"
        self.start_shell({PROP_UNIX_PATH: str(path), PROP_UNIX_CHECK_PEER: True})
        self.connect(path)

    def test_max_clients(self) -> None:
        """
        The client limit also applies on a Unix socket
        """
        path = self.folder / "shell.sock"
        self.start_shell({PROP_UNIX_PATH: str(path), "pelix.shell.max_clients": 1})
        self.connect(path)

        second = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(second.close)
        second.settimeout(10)
        second.connect(str(path))
        self.assertEqual(second.recv(4096), b"")

    def test_password_login(self) -> None:
        """
        A password prompt works on a Unix socket, without the clear-text warning
        """
        path = self.folder / "shell.sock"
        self.start_shell({PROP_UNIX_PATH: str(path), "pelix.shell.auth.required": True})
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        sock.settimeout(10)
        sock.connect(str(path))
        with self.assertNoLogs("pelix.shell.remote", "WARNING"):
            read_until(sock, "Login: ")

    def test_main_unix(self) -> None:
        """
        The script starts on a Unix socket, and refuses it with TLS options
        """
        with self.assertRaises(SystemExit):
            main(["--unix", str(self.folder / "s.sock"), "--cert", "x"])

    def test_server_class_direct(self) -> None:
        """
        The server class can be used on its own
        """
        path = str(self.folder / "direct.sock")
        server = ThreadingUnixServer(path, socketserver_handler(), 1)
        server.server_bind()
        server.server_activate()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertTrue(os.path.exists(path))
        finally:
            server.shutdown()
            server.server_close()
        self.assertFalse(os.path.exists(path))


def socketserver_handler() -> Any:
    import socketserver

    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            pass

    return Handler


if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
