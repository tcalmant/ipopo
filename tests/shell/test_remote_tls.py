#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the remote shell with the TLS feature

:author: Thomas Calmant
"""

import ipaddress
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from typing import Callable, Optional, Tuple, cast

try:
    import ssl
except ImportError:
    unittest.skip("SSL module not available")
    raise

from pelix.framework import Framework, FrameworkFactory, create_framework
from pelix.ipopo.constants import use_ipopo
from pelix.shell import FACTORY_REMOTE_SHELL, RemoteShell, ShellService
from pelix.utilities import to_bytes, to_str
from tests.http.gen_cert import call_openssl, make_subj, write_conf

try:
    import coverage

    has_coverage = True
except ImportError:
    has_coverage = False

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

PASSWORD = "test_password"
TMP_DIR = tempfile.mkdtemp(prefix="ipopo-tests-shell-tls")

# ------------------------------------------------------------------------------


def make_certs(out_dir: str, key_password: str) -> None:
    """
    Generates a certificate chain and server and client certificates

    :param out_dir: Output directory
    :param key_password: Password for the protected key
    """
    # Write the configuration file
    config_file = write_conf(out_dir)

    # Make CA key and certificate
    print("--- Preparing CA key and certificate ---")
    call_openssl(
        "req",
        "-new",
        "-x509",
        "-days",
        1,
        "-subj",
        make_subj("iPOPO Test CA"),
        "-keyout",
        os.path.join(out_dir, "ca.key"),
        "-out",
        os.path.join(out_dir, "ca.crt"),
        "-config",
        config_file,
        "-nodes",
    )

    # Second certificate used for CA mismatch test
    call_openssl(
        "req",
        "-new",
        "-x509",
        "-days",
        1,
        "-subj",
        make_subj("iPOPO Other CA"),
        "-keyout",
        os.path.join(out_dir, "ca_2.key"),
        "-out",
        os.path.join(out_dir, "ca_2.crt"),
        "-config",
        config_file,
        "-nodes",
    )

    # Make server keys
    print("--- Preparing Server keys ---")
    call_openssl("genrsa", "-out", os.path.join(out_dir, "server.key"), 2048)

    if key_password:
        call_openssl(
            "genrsa",
            "-out",
            os.path.join(out_dir, "server_enc.key"),
            "-des3",
            "-passout",
            "pass:" + key_password,
            2048,
        )

    # Make signing requests
    print("--- Preparing Server certificate requests ---")
    call_openssl(
        "req",
        "-subj",
        make_subj("localhost"),
        "-out",
        os.path.join(out_dir, "server.csr"),
        "-key",
        os.path.join(out_dir, "server.key"),
        "-config",
        config_file,
        "-new",
    )

    if key_password:
        call_openssl(
            "req",
            "-subj",
            make_subj("localhost", True),
            "-out",
            os.path.join(out_dir, "server_enc.csr"),
            "-key",
            os.path.join(out_dir, "server_enc.key"),
            "-passin",
            "pass:" + key_password,
            "-config",
            config_file,
            "-new",
        )

    # Sign server certificates
    print("--- Signing Server keys ---")
    call_openssl(
        "x509",
        "-req",
        "-in",
        os.path.join(out_dir, "server.csr"),
        "-CA",
        os.path.join(out_dir, "ca.crt"),
        "-CAkey",
        os.path.join(out_dir, "ca.key"),
        "-CAcreateserial",
        "-out",
        os.path.join(out_dir, "server.crt"),
        "-days",
        1,
    )

    if key_password:
        call_openssl(
            "x509",
            "-req",
            "-in",
            os.path.join(out_dir, "server_enc.csr"),
            "-CA",
            os.path.join(out_dir, "ca.crt"),
            "-CAkey",
            os.path.join(out_dir, "ca.key"),
            "-CAcreateserial",
            "-out",
            os.path.join(out_dir, "server_enc.crt"),
            "-days",
            1,
        )

    # Make client keys
    print("--- Preparing client keys ---")
    call_openssl("genrsa", "-out", os.path.join(out_dir, "client.key"), 2048)

    # Make signing requests
    print("--- Preparing client certificate requests ---")
    call_openssl(
        "req",
        "-subj",
        make_subj("localhost"),
        "-out",
        os.path.join(out_dir, "client.csr"),
        "-key",
        os.path.join(out_dir, "client.key"),
        "-config",
        config_file,
        "-new",
    )

    # Sign client certificates
    print("--- Signing client keys ---")
    call_openssl(
        "x509",
        "-req",
        "-in",
        os.path.join(out_dir, "client.csr"),
        "-CA",
        os.path.join(out_dir, "ca.crt"),
        "-CAkey",
        os.path.join(out_dir, "ca.key"),
        "-CAcreateserial",
        "-out",
        os.path.join(out_dir, "client.crt"),
        "-days",
        1,
    )

    # Sign client certificates
    print("--- Signing client keys with another CA ---")
    call_openssl(
        "x509",
        "-req",
        "-in",
        os.path.join(out_dir, "client.csr"),
        "-CA",
        os.path.join(out_dir, "ca_2.crt"),
        "-CAkey",
        os.path.join(out_dir, "ca_2.key"),
        "-CAcreateserial",
        "-out",
        os.path.join(out_dir, "client_other.crt"),
        "-days",
        1,
    )


# ------------------------------------------------------------------------------


class TLSShellClient:
    """
    Simple client of the TLS remote shell
    """

    def __init__(
        self,
        ps1: str,
        fail: Callable[[str], None],
        client_cert: str,
        client_key: str,
        ca_chain: Optional[str] = None,
    ) -> None:
        """
        Sets up the client
        """
        self._socket: Optional[ssl.SSLSocket] = None
        self._ca_chain = ca_chain
        self._cert = client_cert
        self._key = client_key
        self._ps1 = ps1
        self.fail = fail
        self.__wait_prompt = True

    def connect(self, access: Tuple[str, int], server_hostname: Optional[str] = None) -> None:
        """
        Connects to the remote shell
        """
        # Connect to the server
        sock = socket.create_connection(access)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        if self._ca_chain is not None:
            context.load_verify_locations(self._ca_chain)
        else:
            context.load_default_certs(ssl.Purpose.SERVER_AUTH)

        # Check if we can require host verification
        if server_hostname:
            context.verify_mode = ssl.CERT_REQUIRED
        else:
            # Check if the access was a hostname
            try:
                ipaddress.ip_address(access[0])
                # We got an IP address and no host name, so don't check for it
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            except ValueError:
                # Not an IP address, then it should be a host name
                server_hostname = access[0]
                context.verify_mode = ssl.CERT_REQUIRED

        context.load_cert_chain(self._cert, self._key)

        self._socket = context.wrap_socket(
            sock=sock,
            server_side=False,
            do_handshake_on_connect=True,
            suppress_ragged_eofs=True,
            server_hostname=server_hostname,
        )

    def close(self) -> None:
        """
        Close the connection
        """
        if self._socket is not None:
            self._socket.close()

    def wait_prompt(self, raise_error: bool = True) -> str:
        """
        Waits for the prompt to be read
        """
        assert self._socket is not None

        data = ""
        # Wait for the prompt
        for _ in range(1, 10):
            spared = to_str(self._socket.recv(4096))
            if self._ps1 in spared:
                # Found it
                data += spared[: spared.index(self._ps1)]
                break

            else:
                # Prompt not yet found
                data += spared

        else:
            # Prompt not found
            if raise_error:
                self.fail("Didn't get the prompt")

        return data

    def run_command(self, command: str, disconnect: bool = False) -> Optional[str]:
        """
        Runs a command on the remote shell
        """
        assert self._socket is not None

        # Wait for the first prompt
        if self.__wait_prompt:
            self.wait_prompt()
            self.__wait_prompt = False

        # Run the command
        self._socket.send(to_bytes(command + "\n"))

        # Disconnect if required
        if disconnect:
            self.close()
            return None

        # Get its result
        data = self.wait_prompt(False)
        return data.strip()


# ------------------------------------------------------------------------------


try:
    import subprocess
except ImportError:
    # Can't run the test if we can't start another process
    pass
else:

    class TLSRemoteShellStandaloneTest(unittest.TestCase):
        """
        Tests the remote shell when started as a script
        """

        def test_remote_main(self) -> None:
            """
            Tests the remote shell 'main' method
            """
            # Prepare certificates
            certs_dir = tempfile.mkdtemp(prefix="ipopo-tests-shell-tls")
            make_certs(certs_dir, PASSWORD)
            ca_chain = os.path.join(certs_dir, "ca.crt")
            srv_cert = os.path.join(certs_dir, "server.crt")
            srv_key = os.path.join(certs_dir, "server.key")
            client_cert = os.path.join(certs_dir, "client.crt")
            client_key = os.path.join(certs_dir, "client.key")

            # Get shell PS1 (static method)
            import pelix.shell.core

            ps1 = pelix.shell.core._ShellService.get_ps1()

            # Start the remote shell process
            port = 9000
            args = [sys.executable, "-m"]
            if has_coverage:
                args += ["coverage", "run", "-m"]
            args += [
                "pelix.shell.remote",
                "-a",
                "127.0.0.1",
                "-p",
                str(port),
                "--cert",
                srv_cert,
                "--key",
                srv_key,
                "--ca-chain",
                ca_chain,
            ]
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait a little to ensure that the socket is here
            time.sleep(1)

            # Check if the remote shell port has been opened
            client = TLSShellClient(ps1, self.fail, client_cert, client_key, ca_chain)
            try:
                client.connect(("localhost", port), "localhost")

                test_string = "running"
                self.assertEqual(client.run_command(f"echo {test_string}"), test_string)

                # Good enough: stop there
                client.close()

                # Avoid being blocked...
                timer = threading.Timer(5, process.terminate)
                timer.start()

                # Stop the interpreter with a result code
                rc_code = 42
                stop_line = f"import sys; sys.exit({rc_code})"
                process.communicate(to_bytes(stop_line))

                # We should be good
                timer.cancel()

                # Check result code
                self.assertEqual(process.returncode, rc_code)

                # The ShellClient must fail a new connection
                self.assertRaises(IOError, client.connect, ("localhost", port))
            finally:
                client.close()
                try:
                    # Kill it in any case
                    process.terminate()
                    process.wait(1)
                except OSError:
                    # Process was already stopped
                    pass


# ------------------------------------------------------------------------------


class TLSRemoteShellTest(unittest.TestCase):
    """
    Tests the client/server handshake of the TLS remote shell.
    """

    framework: Framework
    shell: ShellService
    remote: RemoteShell

    @classmethod
    def setUpClass(cls) -> None:
        """
        Setup the certificates
        """
        make_certs(TMP_DIR, PASSWORD)

    def setUp(self) -> None:
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = create_framework(("pelix.ipopo.core", "pelix.shell.core", "pelix.shell.remote"))
        self.framework.start()
        context = self.framework.get_bundle_context()
        # Get the core shell service
        svc_ref = context.get_service_reference(ShellService)
        assert svc_ref is not None
        self.shell = context.get_service(svc_ref)

    def tearDown(self) -> None:
        """
        Cleans up the framework
        """
        try:
            self.framework.stop()
            self.remote = None  # type: ignore
            self.shell = None  # type: ignore
            self.framework = None  # type: ignore
        finally:
            FrameworkFactory.delete_framework()

    def test_basic_connect(self) -> None:
        """
        Tests a basic handshake between a client and the server
        """
        # Get the path of the server certificates
        ca_chain = os.path.join(TMP_DIR, "ca.crt")
        srv_cert = os.path.join(TMP_DIR, "server.crt")
        srv_key = os.path.join(TMP_DIR, "server.key")
        client_cert = os.path.join(TMP_DIR, "client.crt")
        client_key = os.path.join(TMP_DIR, "client.key")

        # Start the remote shell
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            self.remote = cast(
                RemoteShell,
                ipopo.instantiate(
                    FACTORY_REMOTE_SHELL,
                    "remoteShell",
                    {
                        "pelix.shell.address": "127.0.0.1",
                        "pelix.shell.port": 9000,
                        "pelix.shell.ssl.ca": ca_chain,
                        "pelix.shell.ssl.cert": srv_cert,
                        "pelix.shell.ssl.key": srv_key,
                    },
                ),
            )

        # Wait a bit
        time.sleep(0.1)

        # Create a client
        client = TLSShellClient(self.shell.get_ps1(), self.fail, client_cert, client_key, ca_chain)
        try:
            client.connect(self.remote.get_access())

            # Test a command
            test_str = "toto"
            remote_output = client.run_command(f"echo {test_str}")
            self.assertEqual(remote_output, test_str)
        finally:
            # Close the client in any case
            client.close()

    def test_unsigned_client(self) -> None:
        """
        Tests connection with an unsigned client
        """
        # Get the path of the server certificates
        ca_chain = os.path.join(TMP_DIR, "ca.crt")
        srv_cert = os.path.join(TMP_DIR, "server.crt")
        srv_key = os.path.join(TMP_DIR, "server.key")
        client_cert = os.path.join(TMP_DIR, "client_other.crt")
        client_key = os.path.join(TMP_DIR, "client.key")

        # Start the remote shell
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            self.remote = cast(
                RemoteShell,
                ipopo.instantiate(
                    FACTORY_REMOTE_SHELL,
                    "remoteShell",
                    {
                        "pelix.shell.address": "127.0.0.1",
                        "pelix.shell.port": 9000,
                        "pelix.shell.ssl.ca": ca_chain,
                        "pelix.shell.ssl.cert": srv_cert,
                        "pelix.shell.ssl.key": srv_key,
                    },
                ),
            )

        # Create a client
        client = TLSShellClient(self.shell.get_ps1(), self.fail, client_cert, client_key)
        try:
            # Give the host name so that the client accepts the server for the server to reject the client
            self.assertRaises(ssl.SSLError, client.connect, self.remote.get_access(), "localhost")
        finally:
            client.close()

    def test_with_password(self) -> None:
        """
        Tests connection with password-protected certificate on server side
        """
        # Get the path of the server certificates
        ca_chain = os.path.join(TMP_DIR, "ca.crt")
        srv_cert = os.path.join(TMP_DIR, "server_enc.crt")
        srv_key = os.path.join(TMP_DIR, "server_enc.key")
        client_cert = os.path.join(TMP_DIR, "client.crt")
        client_key = os.path.join(TMP_DIR, "client.key")

        # Start the remote shell
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            self.remote = cast(
                RemoteShell,
                ipopo.instantiate(
                    FACTORY_REMOTE_SHELL,
                    "remoteShell",
                    {
                        "pelix.shell.address": "127.0.0.1",
                        "pelix.shell.port": 9000,
                        "pelix.shell.ssl.ca": ca_chain,
                        "pelix.shell.ssl.cert": srv_cert,
                        "pelix.shell.ssl.key": srv_key,
                        "pelix.shell.ssl.key_password": PASSWORD,
                    },
                ),
            )

        # Create a client
        client = TLSShellClient(self.shell.get_ps1(), self.fail, client_cert, client_key, ca_chain)
        try:
            client.connect(self.remote.get_access())

            # Test a command
            test_str = "toto"
            remote_output = client.run_command("echo {0}".format(test_str))
            self.assertEqual(remote_output, test_str)
        finally:
            # Close the client in any case
            client.close()


if __name__ == "__main__":
    unittest.main()
