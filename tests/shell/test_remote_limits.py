#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the resource limits of the remote shell

:author: Thomas Calmant
"""

import pathlib
import shutil
import socket
import tempfile
import time
import unittest
from typing import Any, cast

try:
    import ssl  # noqa: F401
except ImportError:
    raise unittest.SkipTest("SSL module not available") from None

from pelix.framework import Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import use_ipopo
from pelix.shell import FACTORY_REMOTE_SHELL, ShellService, beans
from pelix.shell.remote import (
    PROP_IDLE_TIMEOUT,
    PROP_LOGIN_TIMEOUT,
    PROP_MAX_CLIENTS,
    PROP_MAX_LINE_LENGTH,
    IPopoRemoteShell,
)
from tests.shell.test_remote_auth import PS1, Client
from tests.shell.test_remote_tls import make_certs

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


def wait_closed(sock: socket.socket, timeout: float = 10) -> bytes:
    """
    Reads until the server closes the connection

    :return: Everything received
    :raise AssertionError: The connection is still open after the timeout
    """
    sock.settimeout(timeout)
    received = b""
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                return received
            received += data
    except ConnectionResetError:
        return received
    except TimeoutError:
        raise AssertionError(f"Connection still open after {timeout}s. Got: {received!r}") from None


class RemoteShellLimitsTest(unittest.TestCase):
    """
    Tests the limits protecting the remote shell from its clients
    """

    certs: pathlib.Path
    framework: Framework

    @classmethod
    def setUpClass(cls) -> None:
        cls.certs = pathlib.Path(tempfile.mkdtemp(prefix="ipopo-tests-shell-limits"))
        make_certs(cls.certs, "")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.certs, ignore_errors=True)

    def setUp(self) -> None:
        self.framework = create_framework(("pelix.ipopo.core", "pelix.shell.core", "pelix.shell.remote"))
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        reference = self.context.get_service_reference(ShellService)
        assert reference is not None
        shell: ShellService = self.context.get_service(reference)

        def ask(session: beans.ShellSession) -> None:
            """
            A command reading its own input
            """
            session.write_line("Got: {0}", session.prompt("Value: ").strip())

        shell.register_command("test", "ask", ask)

    def tearDown(self) -> None:
        try:
            self.framework.stop()
        finally:
            FrameworkFactory.delete_framework()

    def start_shell(self, properties: dict[str, Any] | None = None, tls: bool = False) -> tuple[str, int]:
        """
        Instantiates the remote shell

        :return: Its address and port
        """
        props: dict[str, Any] = {
            "pelix.shell.address": "127.0.0.1",
            "pelix.shell.port": 0,
            **(properties or {}),
        }
        if tls:
            props.update(
                {
                    "pelix.shell.ssl.ca": str(self.certs / "ca.crt"),
                    "pelix.shell.ssl.cert": str(self.certs / "server.crt"),
                    "pelix.shell.ssl.key": str(self.certs / "server.key"),
                }
            )

        with use_ipopo(self.context) as ipopo:
            remote = cast(IPopoRemoteShell, ipopo.instantiate(FACTORY_REMOTE_SHELL, "remote-shell", props))

        host, port = remote.get_access()
        assert host is not None and port is not None
        return host, port

    def connect(self, access: tuple[str, int], tls: bool = False) -> Client:
        client = Client(access, self.certs if tls else None)
        self.addCleanup(client.close)
        client.read_until(PS1)
        return client

    def raw_socket(self, access: tuple[str, int]) -> socket.socket:
        sock = socket.create_connection(access, timeout=10)
        self.addCleanup(sock.close)
        return sock

    # --------------------------------------------------------------------------

    def test_defaults(self) -> None:
        """
        The limits are on by default, with generous values
        """
        with use_ipopo(self.context) as ipopo:
            remote = cast(
                IPopoRemoteShell,
                ipopo.instantiate(
                    FACTORY_REMOTE_SHELL,
                    "remote-shell",
                    {"pelix.shell.address": "127.0.0.1", "pelix.shell.port": 0},
                ),
            )

        self.assertEqual(remote.get_max_line_length(), 64 * 1024)
        self.assertEqual(remote.get_idle_timeout(), 3600)
        self.assertEqual(remote.get_login_timeout(), 60)

    def test_line_too_long(self) -> None:
        """
        A line longer than the limit closes the session
        """
        access = self.start_shell({PROP_MAX_LINE_LENGTH: 100})
        client = self.connect(access)
        self.assertEqual(client.command("echo " + "a" * 90), "a" * 90)

        with self.assertLogs("pelix.shell.remote", "WARNING"):
            client.send_line("echo " + "b" * 200)
            output = client.read_all()
        self.assertIn("Line too long", output)
        self.assertNotIn("b" * 200, output)

    def test_partial_line_too_long(self) -> None:
        """
        Data without end of line is limited too: it would otherwise grow forever
        """
        access = self.start_shell({PROP_MAX_LINE_LENGTH: 100})
        sock = self.raw_socket(access)
        sock.sendall(b"x" * 500)

        self.assertIn(b"Line too long", wait_closed(sock))

    def test_idle_timeout(self) -> None:
        """
        An idle session is closed, even in the middle of a line
        """
        access = self.start_shell({PROP_IDLE_TIMEOUT: 1})
        client = self.connect(access)
        self.assertEqual(client.command("echo alive"), "alive")

        start = time.monotonic()
        self.assertIn("Timeout", client.read_all())
        self.assertLess(time.monotonic() - start, 5)

        # Half a line doesn't keep the session alive
        sock = self.raw_socket(access)
        sock.sendall(b"echo no end of line")
        self.assertIn(b"Timeout", wait_closed(sock))

    def test_login_timeout(self) -> None:
        """
        A client which doesn't log in is disconnected
        """
        access = self.start_shell({"pelix.shell.auth.required": True, PROP_LOGIN_TIMEOUT: 1})
        sock = self.raw_socket(access)
        self.assertIn(b"Timeout", wait_closed(sock))

    def test_stalled_tls_handshake(self) -> None:
        """
        A client which never finishes its TLS handshake doesn't block the others, and is
        disconnected after the login timeout
        """
        access = self.start_shell({PROP_LOGIN_TIMEOUT: 2}, tls=True)

        # Connected, but no handshake
        stalled = self.raw_socket(access)

        start = time.monotonic()
        client = self.connect(access, tls=True)
        self.assertEqual(client.command("echo served"), "served")
        self.assertLess(time.monotonic() - start, 2, "The stalled handshake blocked the server")

        wait_closed(stalled)

    def test_max_clients(self) -> None:
        """
        Clients past the limit are refused, and the slots are released
        """
        access = self.start_shell({PROP_MAX_CLIENTS: 2})
        first = self.connect(access)
        self.connect(access)

        with self.assertLogs("pelix.shell.remote", "WARNING"):
            refused = self.raw_socket(access)
            self.assertEqual(wait_closed(refused), b"")

        # A slot is freed when a client leaves
        first.send_line("exit")
        first.read_all()
        for _ in range(50):
            try:
                client = self.connect(access)
            except AssertionError:
                time.sleep(0.1)
            else:
                self.assertEqual(client.command("echo back"), "back")
                break
        else:
            self.fail("The slot of the first client was never released")

    def test_command_input_shares_the_reader(self) -> None:
        """
        A command reading its input gets the next line, even sent with the command
        """
        access = self.start_shell()
        client = self.connect(access)
        client.send_line("test.ask\n42")
        self.assertIn("Got: 42", client.read_until(PS1))

    def test_disabled_limits(self) -> None:
        """
        A limit lesser than or equal to 0 is disabled
        """
        access = self.start_shell({PROP_MAX_LINE_LENGTH: 0, PROP_IDLE_TIMEOUT: -1, PROP_MAX_CLIENTS: 0})
        client = self.connect(access)
        long_value = "c" * (128 * 1024)
        self.assertEqual(client.command("echo " + long_value), long_value)


if __name__ == "__main__":
    unittest.main()
