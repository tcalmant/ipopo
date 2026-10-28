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
import time
import unittest
from typing import Any, cast
from unittest import mock

from pelix.framework import Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.instance import StoredInstance
from pelix.shell import FACTORY_REMOTE_SHELL, ShellCommandMethod, ShellCommandsProvider, beans
from pelix.shell.remote import (
    PROP_UNIX_CHECK_PEER,
    PROP_UNIX_PATH,
    STOP_TIMEOUT,
    UNIX_SOCKET_MODE,
    IPopoRemoteShell,
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

    def connect(self, path: pathlib.Path, marker: str = PS1) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        sock.settimeout(10)
        sock.connect(str(path))
        read_until(sock, marker)
        return sock

    def kill_shell(self) -> None:
        with use_ipopo(self.context) as ipopo:
            ipopo.kill("remote-shell")

    def get_state(self) -> int:
        with use_ipopo(self.context) as ipopo:
            return ipopo.get_instance_details("remote-shell")["state"]

    def is_valid(self) -> bool:
        return self.get_state() == StoredInstance.VALID

    def test_session(self) -> None:
        """
        A client runs a command over the socket; the address and port are not used,
        the client limit applies
        """
        path = self.folder / "shell.sock"
        shell = self.start_shell(
            {
                PROP_UNIX_PATH: str(path),
                "pelix.shell.port": 1,
                "pelix.shell.address": "nowhere.invalid",
                "pelix.shell.max_clients": 1,
            }
        )
        self.assertEqual(shell.get_access(), (str(path), None))
        self.assertTrue(shell.is_unix())

        # Only the owner can connect or change the socket
        self.assertEqual(stat.S_IMODE(path.lstat().st_mode), UNIX_SOCKET_MODE)

        # Trusted as the user of the process, as the system tells: no login
        sock = self.connect(path)
        sock.sendall(to_bytes("echo hello\n"))
        self.assertIn("hello", read_until(sock, PS1))
        sock.sendall(to_bytes("whoami\n"))
        self.assertRegex(read_until(sock, PS1), r"Method\s+: local")

        second = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(second.close)
        second.settimeout(10)
        second.connect(str(path))
        self.assertEqual(second.recv(4096), b"")

    def test_removed_on_stop(self) -> None:
        """
        The socket file is removed when the shell stops, unless it is not ours any more
        """
        path = self.folder / "shell.sock"
        for replaced in (False, True):
            self.start_shell({PROP_UNIX_PATH: str(path)})
            self.assertTrue(path.exists())
            if replaced:
                path.unlink()
                path.write_text("someone else")

            self.kill_shell()
            self.assertEqual(path.exists(), replaced)

    def test_existing_file(self) -> None:
        """
        Only the socket file left by a crashed server is replaced: a regular file, a
        symbolic link or the socket of a running server are kept, the shell fails
        """
        path = self.folder / "shell.sock"
        target = self.folder / "target"
        target.write_text("precious")

        path.write_text("precious")
        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.assertEqual(self.get_state(), StoredInstance.ERRONEOUS)
        self.kill_shell()
        self.assertEqual(path.read_text(), "precious")

        path.unlink()
        path.symlink_to(target)
        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.assertEqual(self.get_state(), StoredInstance.ERRONEOUS)
        self.kill_shell()
        self.assertTrue(path.is_symlink())
        self.assertEqual(target.read_text(), "precious")

        path.unlink()
        other = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(other.close)
        other.bind(str(path))
        other.listen(1)
        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.assertEqual(self.get_state(), StoredInstance.ERRONEOUS)
        self.kill_shell()

        # Closed without unlink: nobody listens, the file remains
        other.close()
        self.start_shell({PROP_UNIX_PATH: str(path)})
        self.connect(path)

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

        # Same client, with the check disabled: accepted, but it must log in, without the
        # clear-text warning of TCP
        with use_ipopo(self.context) as ipopo:
            ipopo.kill("remote-shell")

        self.start_shell({PROP_UNIX_PATH: str(path), PROP_UNIX_CHECK_PEER: False})
        with (
            mock.patch("os.geteuid", return_value=real_uid + 1),
            self.assertNoLogs("pelix.shell.remote", "WARNING"),
        ):
            self.connect(path, "Login: ")

        # Checked again at login: enabling it on the running shell, whose server still
        # accepts other users, doesn't make their sessions trusted
        with use_ipopo(self.context) as ipopo:
            ipopo.reconfigure("remote-shell", {PROP_UNIX_CHECK_PEER: True})
        with mock.patch("os.geteuid", return_value=real_uid + 1):
            self.connect(path, "Login: ")

    def test_main_unix(self) -> None:
        """
        The script starts on a Unix socket, and refuses it with TLS options
        """
        with self.assertRaises(SystemExit):
            main(["--unix", str(self.folder / "s.sock"), "--cert", "x"])

    def read_to_end(self, sock: socket.socket, timeout: float) -> str:
        """
        Reads what the shell sent until it closed the connection, without waiting more
        than the given time
        """
        sock.settimeout(timeout)
        received = b""
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                received += data
        except TimeoutError:
            pass

        return to_str(received)

    def test_stop_ends_the_sessions(self) -> None:
        """
        The stop of the shell waits for its sessions to end, even one running a command
        """
        started = threading.Event()

        class SlowCommand(ShellCommandsProvider):
            def get_namespace(self) -> str:
                return "test"

            def get_methods(self) -> list[tuple[str, ShellCommandMethod]]:
                return [("slow", self.slow)]

            def slow(self, session: beans.ShellSession) -> None:
                started.set()
                time.sleep(STOP_TIMEOUT / 2)

        self.context.register_service(ShellCommandsProvider, SlowCommand(), {})
        path = self.folder / "shell.sock"
        self.start_shell({PROP_UNIX_PATH: str(path)})

        # "exit" closes the session politely, without an interruption message
        leaving = self.connect(path)
        leaving.sendall(to_bytes("exit\n"))
        output = self.read_to_end(leaving, 5)
        self.assertIn("Session closed. Good bye.", output)
        self.assertNotIn("Interruption", output)
        self.assertNotIn("KeyboardInterrupt", output)

        idle = self.connect(path)
        busy = self.connect(path)
        busy.sendall(to_bytes("test.slow\n"))
        self.assertTrue(started.wait(5))

        with use_ipopo(self.context) as ipopo:
            ipopo.kill("remote-shell")

        # Already sent when the stop returns: nothing more to wait for
        for sock in (idle, busy):
            self.assertIn("Session closed. Good bye.", self.read_to_end(sock, 0.1))

        self.assertFalse(
            [thread for thread in threading.enumerate() if thread.name.startswith("RemoteShell-shell.sock-")]
        )

    def test_stop_does_not_wait_forever(self) -> None:
        """
        A command which never ends doesn't block the stop of the shell
        """
        release = threading.Event()
        self.addCleanup(release.set)
        started = threading.Event()

        class StuckCommand(ShellCommandsProvider):
            def get_namespace(self) -> str:
                return "test"

            def get_methods(self) -> list[tuple[str, ShellCommandMethod]]:
                return [("stuck", self.stuck)]

            def stuck(self, session: beans.ShellSession) -> None:
                started.set()
                release.wait(30)

        self.context.register_service(ShellCommandsProvider, StuckCommand(), {})
        path = self.folder / "shell.sock"
        self.start_shell({PROP_UNIX_PATH: str(path)})
        sock = self.connect(path)
        sock.sendall(to_bytes("test.stuck\n"))
        self.assertTrue(started.wait(5))

        begin = time.monotonic()
        with self.assertLogs("pelix.shell.remote", "WARNING") as logs, use_ipopo(self.context) as ipopo:
            ipopo.kill("remote-shell")

        self.assertLess(time.monotonic() - begin, STOP_TIMEOUT + 2)
        self.assertTrue(any("still running a command" in line for line in logs.output))


if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
