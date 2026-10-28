#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the authentication and the authorization of the remote shell, based on pelix.security

:author: Thomas Calmant
"""

import hashlib
import io
import os
import pathlib
import shutil
import socket
import tempfile
import unittest
from typing import Any, cast
from unittest import mock

try:
    import ssl
except ImportError:
    raise unittest.SkipTest("SSL module not available") from None

from pelix.framework import Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.instance import StoredInstance
from pelix.security import (
    ANONYMOUS,
    FACTORY_HTPASSWD,
    FACTORY_POLICY_FILE,
    PROP_HTPASSWD_FILE,
    PROP_HTPASSWD_GROUPS,
    PROP_POLICY_FILE,
    Subject,
    run_as,
)
from pelix.security.decorators import AllowRole
from pelix.shell import FACTORY_REMOTE_SHELL, PERMISSION_READ, CommandPermission, ShellService, beans
from pelix.shell.remote import PROP_CLIENT_AUTH, IPopoRemoteShell, _is_loopback
from pelix.utilities import to_bytes, to_str
from tests.shell.test_remote import GOOD_SHA512
from tests.shell.test_remote_tls import make_certs

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

PS1 = "$ "
LOGGER = "pelix.shell.remote"

# ------------------------------------------------------------------------------


class Client:
    """
    A remote shell client, over plain TCP or TLS
    """

    def __init__(
        self, access: tuple[str, int], certs: pathlib.Path | None = None, client_cert: bool = True
    ) -> None:
        """
        :param access: Address and port of the remote shell
        :param certs: Folder of the test certificates, to connect over TLS
        :param client_cert: Present the client certificate of that folder
        """
        sock = socket.create_connection(access, timeout=10)
        if certs is not None:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(str(certs / "ca.crt"))
            if client_cert:
                context.load_cert_chain(str(certs / "client.crt"), str(certs / "client.key"))
            sock = context.wrap_socket(sock, server_hostname="localhost")

        self._socket = sock
        self._buffer = ""

    def close(self) -> None:
        self._socket.close()

    def read_until(self, marker: str) -> str:
        """
        Reads until the given marker, which is consumed

        :return: What came before the marker
        :raise AssertionError: The connection was closed first
        """
        while marker not in self._buffer:
            data = self._socket.recv(4096)
            if not data:
                raise AssertionError(f"Connection closed before {marker!r}. Got: {self._buffer!r}")

            self._buffer += to_str(data)

        before, _, self._buffer = self._buffer.partition(marker)
        return before

    def read_all(self) -> str:
        """
        Reads until the server closes the connection
        """
        while True:
            data = self._socket.recv(4096)
            if not data:
                break

            self._buffer += to_str(data)

        content, self._buffer = self._buffer, ""
        return content

    def send_line(self, line: str) -> None:
        self._socket.sendall(to_bytes(line + "\n"))

    def login(self, username: str, password: str) -> str:
        """
        Answers the login prompt, which must come next

        :return: What the server wrote after the password
        """
        self.read_until("Login: ")
        self.send_line(username)
        self.read_until("Password: ")
        self.send_line(password)
        return self._read_answer()

    def _read_answer(self) -> str:
        """
        Reads up to the next prompt of any kind
        """
        while True:
            for marker in (PS1, "Login: "):
                if marker in self._buffer:
                    return self.read_until(marker) + marker

            data = self._socket.recv(4096)
            if not data:
                content, self._buffer = self._buffer, ""
                return content

            self._buffer += to_str(data)

    def command(self, line: str) -> str:
        """
        Runs a command, once the shell prompt was read

        :return: Its output
        """
        self.send_line(line)
        return self.read_until(PS1).strip()


def whoami(output: str) -> dict[str, str]:
    """
    Parses the output of the whoami command
    """
    return {
        key.strip(): value.strip() for key, _, value in (line.partition(":") for line in output.splitlines())
    }


# ------------------------------------------------------------------------------


class RemoteShellAuthTest(unittest.TestCase):
    """
    Tests the remote shell with the security bundles
    """

    certs: pathlib.Path
    fingerprint: str
    framework: Framework

    @classmethod
    def setUpClass(cls) -> None:
        cls.certs = pathlib.Path(tempfile.mkdtemp(prefix="ipopo-tests-shell-auth"))
        make_certs(cls.certs, "")

        der = ssl.PEM_cert_to_DER_cert((cls.certs / "client.crt").read_text())
        cls.fingerprint = hashlib.sha256(der).hexdigest()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.certs, ignore_errors=True)

    def setUp(self) -> None:
        self.folder = pathlib.Path(tempfile.mkdtemp(prefix="ipopo-tests-shell-auth-conf"))
        (self.folder / ".htpasswd").write_text(f"thomas:{GOOD_SHA512}\ncertuser:{GOOD_SHA512}\n")
        (self.folder / ".htpasswd").chmod(0o600)
        (self.folder / ".htgroup").write_text("ops: thomas\n")

        self.framework = create_framework(
            (
                "pelix.ipopo.core",
                "pelix.shell.core",
                "pelix.shell.ipopo",
                "pelix.shell.remote",
                "pelix.security.core",
                "pelix.security.htpasswd",
                "pelix.security.policy",
            ),
            {"secret_prop": "s3cr3t"},
        )
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        reference = self.context.get_service_reference(ShellService)
        assert reference is not None
        self.shell: ShellService = self.context.get_service(reference)

        # Open to the read level of the shell, then guarded by the security decorator
        @CommandPermission(PERMISSION_READ)
        @AllowRole("admin")
        def admin_only(session: beans.ShellSession) -> None:
            """
            A command only admins may run
            """
            session.write_line("granted")

        @CommandPermission(PERMISSION_READ)
        def fail(session: beans.ShellSession) -> None:
            """
            A command which fails
            """
            raise RuntimeError("b00m")

        @CommandPermission(PERMISSION_READ)
        def fail_type(session: beans.ShellSession) -> None:
            """
            A command which fails like a call with wrong arguments
            """
            raise TypeError("b00m")

        self.shell.register_command("test", "admin_only", admin_only)
        self.shell.register_command("test", "fail", fail)
        self.shell.register_command("test", "fail_type", fail_type)

    def tearDown(self) -> None:
        try:
            self.framework.stop()
        finally:
            FrameworkFactory.delete_framework()
            shutil.rmtree(self.folder, ignore_errors=True)

    def start_security(self, map_certificate: bool = True, extra_policy: str = "") -> Any:
        """
        Instantiates the password store and the policy

        :return: The password store component
        """
        policy = """
[roles.admin]
groups = ["ops"]

[roles.operator]
users = ["certuser"]

[permissions]
admin = ["pelix.shell.admin", "pelix.shell.debug"]
operator = ["pelix.shell.read", "jobs.read"]
"""
        if map_certificate:
            policy += f'\n[certificates.fingerprints]\n"{self.fingerprint}" = "certuser"\n'
        policy += extra_policy

        (self.folder / "policy.toml").write_text(policy)

        with use_ipopo(self.context) as ipopo:
            users = ipopo.instantiate(
                FACTORY_HTPASSWD,
                "users",
                {
                    PROP_HTPASSWD_FILE: str(self.folder / ".htpasswd"),
                    PROP_HTPASSWD_GROUPS: str(self.folder / ".htgroup"),
                },
            )
            ipopo.instantiate(
                FACTORY_POLICY_FILE, "policy", {PROP_POLICY_FILE: str(self.folder / "policy.toml")}
            )

        return users

    def start_shell(self, tls: bool, **properties: Any) -> IPopoRemoteShell:
        """
        Instantiates the remote shell
        """
        props: dict[str, Any] = {"pelix.shell.address": "127.0.0.1", "pelix.shell.port": 0}
        if tls:
            props.update(
                {
                    "pelix.shell.ssl.ca": str(self.certs / "ca.crt"),
                    "pelix.shell.ssl.cert": str(self.certs / "server.crt"),
                    "pelix.shell.ssl.key": str(self.certs / "server.key"),
                }
            )
        props.update(properties)

        with use_ipopo(self.context) as ipopo:
            return cast(IPopoRemoteShell, ipopo.instantiate(FACTORY_REMOTE_SHELL, "remote-shell", props))

    def connect(self, remote: IPopoRemoteShell, tls: bool, client_cert: bool = True) -> Client:
        host, port = remote.get_access()
        assert host is not None and port is not None
        client = Client((host, port), self.certs if tls else None, client_cert)
        self.addCleanup(client.close)
        return client

    # --------------------------------------------------------------------------

    def test_tcp_requires_a_login(self) -> None:
        """
        No anonymous session over TCP: without a password store, nobody can log in
        """
        remote = self.start_shell(tls=False)
        client = self.connect(remote, tls=False)
        with self.assertLogs(LOGGER, "WARNING"):
            self.assertIn("Login incorrect", client.login("thomas", "good"))

        self.start_security()
        client = self.connect(remote, tls=False)
        self.assertTrue(client.login("thomas", "good").endswith(PS1))
        self.assertEqual(whoami(client.command("whoami"))["User"], "thomas")

    def test_plain_tcp_only_on_loopback(self) -> None:
        """
        Passwords never cross the network in clear text: checked on the bound address
        """
        for address, tls, state in (
            ("0.0.0.0", False, StoredInstance.ERRONEOUS),
            ("0.0.0.0", True, StoredInstance.VALID),
            ("127.0.0.1", False, StoredInstance.VALID),
        ):
            with self.subTest(address=address, tls=tls):
                self.start_shell(tls=tls, **{"pelix.shell.address": address})
                with use_ipopo(self.context) as ipopo:
                    self.assertEqual(ipopo.get_instance_details("remote-shell")["state"], state)
                    ipopo.kill("remote-shell")

        for address, loopback in (
            ("127.0.0.1", True),
            ("127.1.2.3", True),
            ("::1", True),
            ("::ffff:127.0.0.1", True),
            ("0.0.0.0", False),
            ("::", False),
            ("10.0.0.1", False),
            ("::ffff:10.0.0.1", False),
            ("fe80::1%eth0", False),
        ):
            with self.subTest(address=address):
                self.assertEqual(_is_loopback(address), loopback)

    def test_client_auth_modes(self) -> None:
        """
        A client certificate is required, optional or never asked, and a certificate
        authority must be given exactly when a certificate can be presented
        """
        self.start_security()
        for mode, ca, client_cert, prompt in (
            ("required", False, True, None),
            ("required", True, True, PS1),
            ("optional", False, True, None),
            ("optional", True, True, PS1),
            ("optional", True, False, "Login: "),
            ("none", True, True, None),
            ("none", False, False, "Login: "),
            ("none", False, True, "Login: "),
            ("bad", True, True, None),
        ):
            with self.subTest(mode=mode, ca=ca, client_cert=client_cert):
                ca_file = str(self.certs / "ca.crt") if ca else None
                remote = self.start_shell(tls=True, **{PROP_CLIENT_AUTH: mode, "pelix.shell.ssl.ca": ca_file})
                try:
                    if prompt is None:
                        with use_ipopo(self.context) as ipopo:
                            state = ipopo.get_instance_details("remote-shell")["state"]
                        self.assertEqual(state, StoredInstance.ERRONEOUS)
                    else:
                        # The mapped certificate logs in, else the client gets a login prompt
                        client = self.connect(remote, tls=True, client_cert=client_cert)
                        self.assertNotIn("Login: ", client.read_until(prompt))
                finally:
                    with use_ipopo(self.context) as ipopo:
                        ipopo.kill("remote-shell")

    def test_a_mapped_certificate_logs_in(self) -> None:
        self.start_security()
        remote = self.start_shell(tls=True)
        client = self.connect(remote, tls=True)

        # No password prompt: straight to the shell
        self.assertNotIn("Login", client.read_until(PS1))

        identity = whoami(client.command("whoami"))
        self.assertEqual(identity["User"], "certuser")
        self.assertEqual(identity["Authenticated"], "yes")
        self.assertEqual(identity["Method"], "certificate")
        self.assertEqual(identity["Transport"], "shell")
        self.assertEqual(identity["Roles"], "operator")

    def test_a_certificate_mapped_by_subject(self) -> None:
        """
        The subject the ssl module decoded, written the RFC 4514 way
        """
        self.start_security(
            map_certificate=False,
            extra_policy=(
                "\n[certificates.subjects]\n"
                '"CN=localhost,O=iPOPO Tests (plain),L=Grenoble,ST=Auvergne-Rhone-Alpes,C=FR" = "certuser"\n'
            ),
        )
        remote = self.start_shell(tls=True)
        client = self.connect(remote, tls=True)
        client.read_until(PS1)

        self.assertEqual(whoami(client.command("whoami"))["User"], "certuser")

    def test_a_login_sent_in_one_packet(self) -> None:
        """
        A client may send its login, its password and a command at once: none of them
        must be left waiting in a buffer select() cannot see
        """
        self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)
        client = self.connect(remote, tls=True)
        client.read_until("Login: ")

        client.send_line("thomas\ngood\nwhoami")
        client.read_until(PS1)
        self.assertEqual(whoami(client.read_until(PS1).strip())["User"], "thomas")

    def test_an_unmapped_certificate_falls_back_to_a_password(self) -> None:
        self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)
        client = self.connect(remote, tls=True)

        self.assertTrue(client.login("thomas", "good").endswith(PS1))

        identity = whoami(client.command("whoami"))
        self.assertEqual(identity["User"], "thomas")
        self.assertEqual(identity["Method"], "password")
        self.assertEqual(identity["Groups"], "ops")
        self.assertEqual(identity["Roles"], "admin")

    def test_an_unmapped_certificate_does_not_lock_out_its_address(self) -> None:
        """
        The TLS layer verified the certificate: its rejection is no guess, and must not
        count against the address where the password comes next
        """
        self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)
        # More connections than the failures which lock out a source (5 by default)
        for attempt in range(7):
            with self.subTest(attempt=attempt):
                client = self.connect(remote, tls=True)
                self.assertTrue(client.login("thomas", "good").endswith(PS1))

    def test_a_wrong_password_then_a_good_one(self) -> None:
        self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)
        client = self.connect(remote, tls=True)

        with self.assertLogs(LOGGER, "WARNING"):
            self.assertIn("Login incorrect", client.login("thomas", "bad"))

        # The answer to the first attempt ended on the next login prompt
        client.send_line("thomas")
        client.read_until("Password: ")
        client.send_line("good")
        client.read_until(PS1)
        self.assertEqual(whoami(client.command("whoami"))["User"], "thomas")

    def test_three_failures_close_the_connection(self) -> None:
        self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)
        client = self.connect(remote, tls=True)

        with self.assertLogs(LOGGER, "WARNING") as logs:
            client.read_until("Login: ")
            for attempt in range(3):
                if attempt:
                    client.read_until("Login: ")

                client.send_line("thomas")
                client.read_until("Password: ")
                client.send_line("bad")

            rest = client.read_all()

        self.assertIn("Too many failed login attempts", rest)
        self.assertNotIn("Login: ", rest)
        self.assertTrue(any("Too many failed logins" in line for line in logs.output))

    def test_no_command_before_login(self) -> None:
        self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)
        client = self.connect(remote, tls=True)

        # Whatever is written at the login prompt is a user name, never a command
        with self.assertLogs(LOGGER, "WARNING"):
            answer = client.login("echo leaked", "help")

        self.assertNotIn("leaked", answer)
        self.assertNotIn(PS1, answer)
        self.assertTrue(answer.endswith("Login: "))

    def test_commands_run_as_the_session_subject(self) -> None:
        self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)

        client = self.connect(remote, tls=True)
        client.login("thomas", "good")
        self.assertEqual(client.command("test.admin_only"), "granted")

        client = self.connect(remote, tls=True)
        client.login("certuser", "good")
        self.assertIn("AccessDenied", client.command("test.admin_only"))

    def test_permissions(self) -> None:
        """
        The read level runs the listings, the admin level runs everything. A refused
        command looks unknown, and the help doesn't list it
        """
        self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)
        for user, command, allowed in (
            ("certuser", "bl", True),
            ("certuser", "ipopo.instances", True),
            ("certuser", "install pelix.shell.log", False),
            ("certuser", "ipopo.instantiate x y", False),
            ("certuser", "properties", False),
            ("thomas", "install pelix.shell.log", True),
            ("thomas", "properties", True),
        ):
            with self.subTest(user=user, command=command):
                client = self.connect(remote, tls=True)
                client.login(user, "good")
                if allowed:
                    self.assertNotIn("Unknown command", client.command(command))
                else:
                    with self.assertLogs("pelix.shell", "WARNING"):
                        self.assertEqual(client.command(command), f"Unknown command {command.split()[0]}")

        client = self.connect(remote, tls=True)
        client.login("certuser", "good")
        listing = client.command("help")
        self.assertIn("- bl", listing)
        self.assertNotIn("- install", listing)
        self.assertNotIn("- properties", listing)
        self.assertEqual(client.command("help install"), "Unknown command install")

    def test_restricted_sessions(self) -> None:
        """
        A remote session never expands the framework properties, and only shows the
        details of an error with the debug permission
        """
        self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)
        for user, command, details in (
            ("certuser", "test.fail", False),
            ("certuser", "test.fail_type", False),
            ("thomas", "test.fail", True),
            ("thomas", "test.fail_type", True),
        ):
            with self.subTest(user=user, command=command):
                client = self.connect(remote, tls=True)
                client.login(user, "good")
                self.assertEqual(client.command("echo $secret_prop"), "")
                with self.assertLogs("pelix.shell", "ERROR") as logs:
                    output = client.command(command)

                self.assertEqual("b00m" in output, details)
                self.assertIn("b00m", logs.output[0])

    def test_the_subject_is_refreshed(self) -> None:
        """
        A user removed from a group loses its permissions at its next command
        """
        users = self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)
        client = self.connect(remote, tls=True)
        client.login("thomas", "good")
        self.assertNotIn("Unknown command", client.command("properties"))

        (self.folder / ".htgroup").write_text("ops: someone\n")
        users.reload()
        with self.assertLogs("pelix.shell", "WARNING"):
            self.assertIn("Unknown command", client.command("properties"))

    def test_the_audit_log(self) -> None:
        self.start_security()
        remote = self.start_shell(tls=True)
        client = self.connect(remote, tls=True)
        client.read_until(PS1)

        with self.assertLogs(LOGGER, "DEBUG") as logs:
            self.assertEqual(client.command("echo s3cr3t"), "s3cr3t")
            client.command("no_such_command s3cr3t")

        info = [record.getMessage() for record in logs.records if record.levelname == "INFO"]
        debug = [record.getMessage() for record in logs.records if record.levelname == "DEBUG"]

        self.assertIn("User certuser from 127.0.0.1 requested default.echo", info)
        self.assertIn("User certuser from 127.0.0.1 requested an unknown command", info)
        self.assertFalse([message for message in info if "s3cr3t" in message])
        self.assertIn("User certuser from 127.0.0.1 requested: echo s3cr3t", debug)

    def __break(self, remote: IPopoRemoteShell) -> None:
        """
        Makes the "boom" line fail outside of any command
        """
        original = remote.handle_line

        def handle_line(line: str, session: beans.ShellSession) -> bool:
            if line == "boom":
                raise RuntimeError("boom")

            return original(line, session)

        cast(Any, remote).handle_line = handle_line

    def test_a_trace_is_shown_with_the_debug_permission(self) -> None:
        self.start_security(map_certificate=False)
        remote = self.start_shell(tls=True)
        self.__break(remote)
        client = self.connect(remote, tls=True)
        client.login("thomas", "good")

        with self.assertLogs(LOGGER, "ERROR"):
            output = client.command("boom")

        self.assertIn("Traceback", output)
        self.assertIn("RuntimeError: boom", output)

    def test_a_trace_is_hidden_without_the_debug_permission(self) -> None:
        self.start_security()
        remote = self.start_shell(tls=True)
        self.__break(remote)
        client = self.connect(remote, tls=True)
        client.read_until(PS1)

        with self.assertLogs(LOGGER, "ERROR") as logs:
            output = client.command("boom")

        self.assertNotIn("Traceback", output)
        self.assertNotIn("boom", output)
        error_id = output.rpartition("Error ID: ")[2].strip()
        self.assertEqual(len(error_id), 32)

        # The trace is in the log, with the ID the client got
        self.assertIn(error_id, logs.output[0])
        self.assertIn("RuntimeError: boom", logs.output[0])


# ------------------------------------------------------------------------------


class SessionSubjectTest(unittest.TestCase):
    """
    Tests the subject of a shell session and the whoami command, with no remote shell
    """

    framework: Framework

    def setUp(self) -> None:
        self.framework = create_framework(("pelix.shell.core",), {"secret_prop": "s3cr3t"})
        self.framework.start()
        context = self.framework.get_bundle_context()
        reference = context.get_service_reference(ShellService)
        assert reference is not None
        self.shell: ShellService = context.get_service(reference)

    def tearDown(self) -> None:
        try:
            self.framework.stop()
        finally:
            FrameworkFactory.delete_framework()

    def test_a_session_is_anonymous_and_untrusted_by_default(self) -> None:
        session = beans.ShellSession(beans.IOHandler(None, io.StringIO()))
        self.assertIs(session.subject, ANONYMOUS)
        self.assertFalse(session.trusted)

    def test_the_session_subject_is_kept(self) -> None:
        subject = Subject("thomas", authenticated=True)
        session = beans.ShellSession(beans.IOHandler(None, io.StringIO()), {}, subject)
        self.assertIs(session.subject, subject)

    def test_whoami_prints_the_session_subject(self) -> None:
        """
        Commands run as the subject of their session, which is what a decorator checks
        """
        output = io.StringIO()
        subject = Subject(
            "batch", frozenset({"ops"}), frozenset({"operator"}), authenticated=True, method="test"
        )
        session = beans.ShellSession(beans.IOHandler(None, output), {}, subject, trusted=True)

        with run_as(ANONYMOUS):
            self.assertTrue(self.shell.execute("whoami", session))

        self.assertEqual(
            whoami(output.getvalue()),
            {
                "User": "batch",
                "Authenticated": "yes",
                "Method": "test",
                "Transport": "-",
                "Groups": "ops",
                "Roles": "operator",
            },
        )

    def test_only_trusted_sessions_without_security(self) -> None:
        """
        Without the security core, nothing is permitted but in a trusted session, which
        also is the only one to see the framework properties
        """
        for trusted, expected in ((True, "s3cr3t"), (False, "Unknown command echo")):
            with self.subTest(trusted=trusted):
                output = io.StringIO()
                session = beans.ShellSession(beans.IOHandler(None, output), trusted=trusted)
                self.assertEqual(self.shell.execute("echo $secret_prop", session), trusted)
                self.assertEqual(output.getvalue().strip(), expected)

        # Without a session: anything could have sent the line
        self.assertFalse(self.shell.execute("echo"))

    def test_local_subject(self) -> None:
        """
        The user of the process comes from the account database, not from the environment
        """
        try:
            import pwd
        except ImportError:
            self.skipTest("No account database")

        with mock.patch.dict(os.environ, {"USER": "root", "LOGNAME": "root"}):
            subject = beans.make_local_subject("console")

        self.assertEqual(subject.name, pwd.getpwuid(os.geteuid()).pw_name)
        self.assertTrue(subject.authenticated)
        self.assertEqual((subject.method, subject.transport), ("local", "console"))
        self.assertEqual(beans.make_local_subject("x", 2**31 - 2).name, "uid:2147483646")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
