#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the remote shell with the TLS feature

:author: Thomas Calmant
"""

# Standard library
import os
import socket
import sys
import tempfile
import threading
import time

# Tests
try:
    import unittest2 as unittest
except ImportError:
    import unittest

try:
    import ssl
except ImportError:
    unittest.skip("SSL module not available")

# Pelix
from pelix.framework import FrameworkFactory, create_framework
from pelix.utilities import to_str, to_bytes
from pelix.ipopo.constants import use_ipopo

# Shell constants
from pelix.shell import SERVICE_SHELL, FACTORY_REMOTE_SHELL

# Certificate generation utilities
from tests.http.gen_cert import make_subj, call_openssl, write_conf

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

# Documentation strings format
__docformat__ = "restructuredtext en"

PASSWORD = "test_password"
TMP_DIR = tempfile.mkdtemp(prefix="ipopo-tests-shell-tls")

# ------------------------------------------------------------------------------


def make_certs(out_dir, key_password):
    """
    Generates a certificate chain and server and client certificates

    :param out_dir: Output directory
    :param key_password: Password for the protected key
    """
    # Write the configuration file
    config_file = write_conf(out_dir)

    # Make CA key and certificate
    print("--- Preparing CA key and certificate ---")
    call_openssl("req", "-new", "-x509",
                 "-days", 1,
                 "-subj", make_subj("iPOPO Test CA"),
                 "-keyout", os.path.join(out_dir, "ca.key"),
                 "-out", os.path.join(out_dir, "ca.crt"),
                 "-config", config_file,
                 "-nodes")

    # Second certificate used for CA mismatch test
    call_openssl("req", "-new", "-x509",
                 "-days", 1,
                 "-subj", make_subj("iPOPO Other CA"),
                 "-keyout", os.path.join(out_dir, "ca_2.key"),
                 "-out", os.path.join(out_dir, "ca_2.crt"),
                 "-config", config_file,
                 "-nodes")

    # Make server keys
    print("--- Preparing Server keys ---")
    call_openssl("genrsa", "-out", os.path.join(out_dir, "server.key"), 2048)

    if key_password:
        call_openssl("genrsa", "-out", os.path.join(out_dir, "server_enc.key"),
                     "-des3", "-passout", "pass:" + key_password, 2048)

    # Make signing requests
    print("--- Preparing Server certificate requests ---")
    call_openssl("req", "-subj", make_subj("localhost"),
                 "-out", os.path.join(out_dir, "server.csr"),
                 "-key", os.path.join(out_dir, "server.key"),
                 "-config", config_file,
                 "-new")

    if key_password:
        call_openssl("req", "-subj", make_subj("localhost", True),
                     "-out", os.path.join(out_dir, "server_enc.csr"),
                     "-key", os.path.join(out_dir, "server_enc.key"),
                     "-passin", "pass:" + key_password,
                     "-config", config_file,
                     "-new")

    # Sign server certificates
    print("--- Signing Server keys ---")
    call_openssl("x509", "-req",
                 "-in", os.path.join(out_dir, "server.csr"),
                 "-CA", os.path.join(out_dir, "ca.crt"),
                 "-CAkey", os.path.join(out_dir, "ca.key"),
                 "-CAcreateserial",
                 "-out", os.path.join(out_dir, "server.crt"),
                 "-days", 1)

    if key_password:
        call_openssl("x509", "-req",
                     "-in", os.path.join(out_dir, "server_enc.csr"),
                     "-CA", os.path.join(out_dir, "ca.crt"),
                     "-CAkey", os.path.join(out_dir, "ca.key"),
                     "-CAcreateserial",
                     "-out", os.path.join(out_dir, "server_enc.crt"),
                     "-days", 1)

    # Make client keys
    print("--- Preparing client keys ---")
    call_openssl("genrsa", "-out", os.path.join(out_dir, "client.key"), 2048)

    # Make signing requests
    print("--- Preparing client certificate requests ---")
    call_openssl("req", "-subj", make_subj("localhost"),
                 "-out", os.path.join(out_dir, "client.csr"),
                 "-key", os.path.join(out_dir, "client.key"),
                 "-config", config_file,
                 "-new")

    # Sign client certificates
    print("--- Signing client keys ---")
    call_openssl("x509", "-req",
                 "-in", os.path.join(out_dir, "client.csr"),
                 "-CA", os.path.join(out_dir, "ca.crt"),
                 "-CAkey", os.path.join(out_dir, "ca.key"),
                 "-CAcreateserial",
                 "-out", os.path.join(out_dir, "client.crt"),
                 "-days", 1)

    # Sign client certificates
    print("--- Signing client keys with another CA ---")
    call_openssl("x509", "-req",
                 "-in", os.path.join(out_dir, "client.csr"),
                 "-CA", os.path.join(out_dir, "ca_2.crt"),
                 "-CAkey", os.path.join(out_dir, "ca_2.key"),
                 "-CAcreateserial",
                 "-out", os.path.join(out_dir, "client_other.crt"),
                 "-days", 1)

# ------------------------------------------------------------------------------


class TLSShellClient(object):
    """
    Simple client of the TLS remote shell
    """
    def __init__(self, ps1, fail, client_cert, client_key):
        """
        Sets up the client
        """
        self._socket = None
        self._cert = client_cert
        self._key = client_key
        self._ps1 = ps1
        self.fail = fail
        self.__wait_prompt = True
        self.__prefix = ""

    def connect(self, access):
        """
        Connects to the remote shell
        """
        # Connect to the server
        sock = socket.create_connection(access)
        self._socket = ssl.wrap_socket(
            sock, server_side=False, certfile=self._cert, keyfile=self._key)

    def close(self):
        """
        Close the connection
        """
        if self._socket is not None:
            self._socket.close()

    def wait_prompt(self, raise_error=True):
        """
        Waits for the prompt to be read
        """
        data = ""
        # Wait for the prompt
        for _ in range(1, 10):
            spared = to_str(self._socket.recv(4096))
            if self._ps1 in spared:
                # Found it
                data += spared[:spared.index(self._ps1)]
                break

            else:
                # Prompt not yet found
                data += spared

        else:
            # Prompt not found
            if raise_error:
                self.fail("Didn't get the prompt")

        return data

    def run_command(self, command, disconnect=False):
        """
        Runs a command on the remote shell
        """
        # Wait for the first prompt
        if self.__wait_prompt:
            self.wait_prompt()
            self.__wait_prompt = False

        # Run the command
        self._socket.send(to_bytes(command + "\n"))

        # Disconnect if required
        if disconnect:
            self.close()
            return

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
        def test_remote_main(self):
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
            process = subprocess.Popen(
                [sys.executable, '-m', 'coverage', 'run', '-m',
                 'pelix.shell.remote', '-a', '127.0.0.1', '-p', str(port),
                 '--cert', srv_cert, '--key', srv_key,
                 '--ca-chain', ca_chain],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

            # Wait a little to ensure that the socket is here
            time.sleep(1)

            try:
                # Check if the remote shell port has been opened
                client = TLSShellClient(
                    ps1, self.fail, client_cert, client_key)

                client.connect(("127.0.0.1", port))

                test_string = "running"
                self.assertEqual(
                    client.run_command("echo {0}".format(test_string)),
                    test_string)

                # Good enough: stop there
                client.close()

                # Avoid being blocked...
                timer = threading.Timer(5, process.terminate)
                timer.start()

                # Stop the interpreter with a result code
                rc_code = 42
                stop_line = "import sys; sys.exit({0})".format(rc_code)
                process.communicate(to_bytes(stop_line))

                # We should be good
                timer.cancel()

                # Check result code
                self.assertEqual(process.returncode, rc_code)

                # The ShellClient must fail a new connection
                self.assertRaises(IOError, client.connect, ("localhost", port))
            finally:
                try:
                    # Kill it in any case
                    process.terminate()
                except OSError:
                    # Process was already stopped
                    pass

# ------------------------------------------------------------------------------


class TLSRemoteShellTest(unittest.TestCase):
    """
    Tests the client/server handshake of the TLS remote shell.
    """
    @classmethod
    def setUpClass(cls):
        """
        Setup the certificates
        """
        make_certs(TMP_DIR, PASSWORD)

    def setUp(self):
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = create_framework(
            ('pelix.ipopo.core', 'pelix.shell.core', 'pelix.shell.remote'))
        self.framework.start()
        context = self.framework.get_bundle_context()
        # Get the core shell service
        svc_ref = context.get_service_reference(SERVICE_SHELL)
        self.shell = context.get_service(svc_ref)

    def tearDown(self):
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()
        self.remote = None
        self.shell = None
        self.framework = None

    def test_basic_connect(self):
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
            self.remote = ipopo.instantiate(
                FACTORY_REMOTE_SHELL, "remoteShell",
                {'pelix.shell.address': '127.0.0.1',
                 'pelix.shell.port': 9000,
                 'pelix.shell.ssl.ca': ca_chain,
                 'pelix.shell.ssl.cert': srv_cert,
                 'pelix.shell.ssl.key': srv_key})

        # Wait a bit
        time.sleep(.1)

        # Create a client
        client = TLSShellClient(
            self.remote.get_ps1(), self.fail, client_cert, client_key)
        try:
            client.connect(self.remote.get_access())

            # Test a command
            test_str = "toto"
            remote_output = client.run_command("echo {0}".format(test_str))
            self.assertEqual(remote_output, test_str)
        finally:
            # Close the client in any case
            client.close()

    def test_unsigned_client(self):
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
            self.remote = ipopo.instantiate(
                FACTORY_REMOTE_SHELL, "remoteShell",
                {'pelix.shell.address': '127.0.0.1',
                 'pelix.shell.port': 9000,
                 'pelix.shell.ssl.ca': ca_chain,
                 'pelix.shell.ssl.cert': srv_cert,
                 'pelix.shell.ssl.key': srv_key})

        # Create a client
        client = TLSShellClient(
            self.remote.get_ps1(), self.fail, client_cert, client_key)

        try:
            self.assertRaises(
                ssl.SSLError, client.connect, self.remote.get_access())
        finally:
            client.close()

    def test_with_password(self):
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
            self.remote = ipopo.instantiate(
                FACTORY_REMOTE_SHELL, "remoteShell",
                {'pelix.shell.address': '127.0.0.1',
                 'pelix.shell.port': 9000,
                 'pelix.shell.ssl.ca': ca_chain,
                 'pelix.shell.ssl.cert': srv_cert,
                 'pelix.shell.ssl.key': srv_key,
                 'pelix.shell.ssl.key_password': PASSWORD})

        # Create a client
        client = TLSShellClient(
            self.remote.get_ps1(), self.fail, client_cert, client_key)

        try:
            client.connect(self.remote.get_access())

            # Test a command
            test_str = "toto"
            remote_output = client.run_command("echo {0}".format(test_str))
            self.assertEqual(remote_output, test_str)
        finally:
            # Close the client in any case
            client.close()
