#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO remote shell

Provides a remote interface for the Pelix shell that can be accessed using
telnet or netcat.

Authentication is optional and based on :mod:`pelix.security`: a TLS client
certificate the security layer maps to a user, or a login and password prompt when
``pelix.shell.auth.required`` is set. Every command then runs as the authenticated
subject, or as the anonymous one when authentication is not required.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.2.2

..

    Copyright 2026 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import argparse
import importlib
import logging
import shlex
import socket
import socketserver
import sys
import threading
import time
import traceback
import uuid
from select import select
from typing import TYPE_CHECKING, Any, cast

import pelix.framework
import pelix.ipv6utils
import pelix.shell
from pelix import utilities
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.decorators import (
    ComponentFactory,
    HiddenProperty,
    Invalidate,
    Property,
    Provides,
    Requires,
    Validate,
)
from pelix.security import (
    ANONYMOUS,
    AuthenticationFailed,
    Authorization,
    ClientCertificate,
    Credentials,
    Permission,
    Subject,
    UsernamePassword,
    run_as,
)
from pelix.shell import beans
from pelix.shell.console import handle_common_arguments, make_common_parser

if TYPE_CHECKING:
    # Type checkers must always see "ssl" as the module and never as None, so
    # that annotations like "ssl.SSLContext" stay valid. Whether SSL is really
    # available is a run-time question, answered by HAS_SSL.
    import ssl

    HAS_SSL: bool = True
else:
    try:
        # Some Python distributions don't support SSL
        import ssl

        HAS_SSL = True
    except ImportError:
        HAS_SSL = False
        ssl = None

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "DEFAULT_IDLE_TIMEOUT",
    "DEFAULT_LOGIN_TIMEOUT",
    "DEFAULT_MAX_CLIENTS",
    "DEFAULT_MAX_LINE_LENGTH",
    "MAX_LOGIN_ATTEMPTS",
    "METHOD_CERTIFICATE",
    "METHOD_PASSWORD",
    "POLL_INTERVAL",
    "PROP_AUTH_REQUIRED",
    "PROP_IDLE_TIMEOUT",
    "PROP_LOGIN_TIMEOUT",
    "PROP_MAX_CLIENTS",
    "PROP_MAX_LINE_LENGTH",
    "TRANSPORT",
    "RemoteConsole",
    "SharedBoolean",
    "ThreadingTCPServerFamily",
    "main",
]

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

PROP_AUTH_REQUIRED = "pelix.shell.auth.required"
""" Component property: refuse every command until the client authenticated. Default: False """

PERMISSION_DEBUG = Permission("pelix.shell.debug")
""" Permission to see the stack trace of an error outside a command """

METHOD_CERTIFICATE = "certificate"
""" Authentication method of a session opened with a TLS client certificate """

METHOD_PASSWORD = "password"
""" Authentication method of a session opened with a login and a password """

TRANSPORT = "shell"
""" Transport name given to the security layer, telling shell logins from others in audits """

MAX_LOGIN_ATTEMPTS = 3
""" Password attempts a connection gets before it is closed """

PROP_MAX_LINE_LENGTH = "pelix.shell.max_line_length"
""" Component property: longest line, in bytes, a client can send. Default: 65536. 0: no limit """

PROP_IDLE_TIMEOUT = "pelix.shell.idle_timeout"
""" Component property: seconds without input before a session is closed. Default: 3600. 0: never """

PROP_LOGIN_TIMEOUT = "pelix.shell.login_timeout"
"""
Component property: seconds a client gets to finish the TLS handshake and to log in.
Default: 60. 0: no limit
"""

PROP_MAX_CLIENTS = "pelix.shell.max_clients"
""" Component property: maximum number of simultaneous clients. Default: 32. 0: no limit """

DEFAULT_MAX_LINE_LENGTH = 64 * 1024
DEFAULT_IDLE_TIMEOUT = 3600.0
DEFAULT_LOGIN_TIMEOUT = 60.0
DEFAULT_MAX_CLIENTS = 32

POLL_INTERVAL = 0.5
""" Seconds between two checks of the server state while waiting for a client """

# ------------------------------------------------------------------------------


def _to_limit(value: Any, default: float) -> float | None:
    """
    Normalizes a limit given as a component property

    :param value: The raw property value
    :param default: The value to use if the property is invalid
    :return: The limit, or None if it is disabled (lesser than or equal to 0)
    """
    try:
        limit = float(value)
    except (TypeError, ValueError):
        _logger.error("Invalid remote shell limit %r: using %s", value, default)
        limit = default

    return limit if limit > 0 else None


def _to_bool(value: Any) -> bool:
    """
    Reads a boolean component property, which a configuration file may give as a string

    :param value: The property value
    :return: The boolean it means
    """
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")

    return bool(value)


class SharedBoolean:
    """
    Shared boolean between objects / threads
    """

    def __init__(self, value: bool = False) -> None:
        """
        Set up members
        """
        self._lock = threading.Lock()
        self._value = value

    def get_value(self) -> bool:
        """
        Retrieves the boolean value
        """
        with self._lock:
            return self._value

    def set_value(self, value: bool) -> None:
        """
        Sets the boolean value
        """
        with self._lock:
            self._value = value


# ------------------------------------------------------------------------------


class _SessionClosed(Exception):
    """
    The session must be closed: the client broke one of the limits of the shell
    """

    def __init__(self, reason: str) -> None:
        """
        :param reason: The message sent to the client
        """
        super().__init__(reason)
        self.reason = reason


class _LineReader:
    """
    Reads lines from a client socket, enforcing the limits of the shell.

    The socket is read in chunks rather than through a buffered file: a file would
    block until the end of a line, so that a client sending half a line would keep a
    thread forever, whatever the timeouts.
    """

    def __init__(self, connection: socket.socket, active: SharedBoolean, max_line_length: int | None) -> None:
        """
        :param connection: The client socket (TLS handshake already done)
        :param active: The flag telling if the server is still running
        :param max_line_length: The longest accepted line, in bytes, or None
        """
        self._connection = connection
        self._active = active
        self._max_line_length = max_line_length
        self._buffer = bytearray()
        self._eof = False

        # Once a limit is broken, every read fails: a command reading its own input
        # (prompt) must not let the session go on
        self._failure: _SessionClosed | None = None

    def _wait_readable(self, deadline: float | None) -> bool:
        """
        Waits for data to read, for at most one poll interval

        :param deadline: Monotonic time after which to give up, or None
        :return: True if data can be read
        """
        if HAS_SSL and isinstance(self._connection, ssl.SSLSocket) and self._connection.pending():
            # Already decrypted by the TLS layer: the socket itself may have nothing left
            return True

        wait = POLL_INTERVAL
        if deadline is not None:
            wait = max(0.0, min(wait, deadline - time.monotonic()))

        return bool(select([self._connection], [], [], wait)[0])

    def readline(self, timeout: float | None) -> bytes | None:
        """
        Reads a line, with its end of line

        :param timeout: Seconds to wait for the complete line, or None
        :return: The line, or None if the client is gone or the server is stopping
        :raise _SessionClosed: The line is too long, or took too long to come
        """
        if self._failure is not None:
            raise self._failure

        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            end = self._buffer.find(b"\n")
            limit = self._max_line_length
            if end >= 0 and (limit is None or end <= limit):
                line = bytes(self._buffer[: end + 1])
                del self._buffer[: end + 1]
                return line

            if limit is not None and (end > limit or len(self._buffer) > limit):
                self._failure = _SessionClosed(f"Line too long: the limit is {limit} bytes.")
                raise self._failure

            if self._eof:
                if self._buffer:
                    # Last line, without its end of line
                    line = bytes(self._buffer)
                    self._buffer.clear()
                    return line
                return None

            if not self._active.get_value():
                return None

            if deadline is not None and time.monotonic() >= deadline:
                self._failure = _SessionClosed("Timeout: closing the session.")
                raise self._failure

            if not self._wait_readable(deadline):
                continue

            try:
                chunk = self._connection.recv(4096)
            except BlockingIOError:
                # Readable socket, but not a full TLS record yet
                continue
            except OSError:
                chunk = b""

            if chunk:
                self._buffer.extend(chunk)
            else:
                self._eof = True


class _ReaderInput:
    """
    File-like input given to the shell session, for the commands reading their own
    input: it shares the buffer and the limits of the session reader
    """

    def __init__(self, reader: _LineReader, timeout: float | None) -> None:
        """
        :param reader: The line reader of the session
        :param timeout: Seconds a command waits for its input, or None
        """
        self._reader = reader
        self._timeout = timeout

    def readline(self, size: int = -1) -> bytes:
        """
        Reads a line. Returns an empty line when the session is over: the reader then
        fails again on the next read of the session loop, which closes it.
        """
        try:
            return self._reader.readline(self._timeout) or b""
        except _SessionClosed:
            return b""


class RemoteConsole(socketserver.StreamRequestHandler):
    """
    Handles incoming connections and redirect network stream to the Pelix shell
    """

    # Unbuffered: the input is read by a _LineReader, directly on the socket
    rbufsize = 0

    def __init__(self, shell_svc: "IPopoRemoteShell", active_flag: SharedBoolean, *args: Any) -> None:
        """
        Sets up members

        :param shell_svc: The underlying Pelix shell service
        :param active_flag: Common flag for stopping the client communication
        """
        self._shell = shell_svc
        self._active = active_flag
        self._connected_at = time.monotonic()
        self._handshake_done = False
        self._reader: _LineReader | None = None
        socketserver.StreamRequestHandler.__init__(self, *args)

    def setup(self) -> None:
        """
        Prepares the connection, in the thread of the client.

        The TLS handshake happens here rather than when the connection is accepted: a
        client which never finishes it would otherwise block every other client.
        """
        super().setup()

        connection = self.connection
        if HAS_SSL and isinstance(connection, ssl.SSLSocket):
            try:
                connection.settimeout(self._shell.get_login_timeout())
                connection.do_handshake()
                connection.settimeout(None)
            except (OSError, ssl.SSLError) as ex:
                _logger.warning("TLS handshake failed with %s: %s", self.client_address, ex)
                return

        self._handshake_done = True
        self._reader = _LineReader(connection, self._active, self._shell.get_max_line_length())

    def _login_remaining(self) -> float | None:
        """
        Returns the seconds left to log in, or None if there is no limit
        """
        timeout = self._shell.get_login_timeout()
        if timeout is None:
            return None

        return max(0.0, self._connected_at + timeout - time.monotonic())

    def send(self, data: str) -> bool:
        """
        Tries to send data to the client.

        :param data: Data to be sent
        :return: True if the data was sent, False on error
        """
        if data is None:
            # Don't send None
            return False

        try:
            self.wfile.write(data.encode("UTF-8"))
            self.wfile.flush()
            return True
        except OSError:
            # An error occurred, mask it
            # -> This allows to handle the command even if the client has been
            # disconnect (i.e. "echo stop 0 | nc localhost 9000")
            return False

    def _is_tls(self) -> bool:
        """
        Tells whether the client is connected over TLS
        """
        return HAS_SSL and isinstance(self.connection, ssl.SSLSocket)

    def read_line(self, timeout: float | None = None) -> str | None:
        """
        Waits for a line from the client, as long as the server is active.

        :param timeout: Seconds to wait for the line; the idle timeout if None
        :return: The line, with its end of line, or None if the client is gone or the
                 server is stopping
        :raise _SessionClosed: The client broke a limit of the shell
        """
        assert self._reader is not None
        data = self._reader.readline(timeout if timeout is not None else self._shell.get_idle_timeout())
        if data is None:
            return None

        return data.decode(self._shell.get_encoding(), errors="replace")

    def _login(self, client_ip: str) -> Subject | None:
        """
        Authenticates the client: first with its TLS certificate, then with a login and
        a password if authentication is required.

        :param client_ip: The address of the client
        :return: The subject of the session, or None to close the connection
        """
        # Without the security core, a shell which does not require authentication
        # behaves as it always did, without even a warning about missing authenticators
        if self._is_tls() and self._shell.is_security_active():
            certificate = ClientCertificate.from_socket(cast(ssl.SSLSocket, self.connection))
            if certificate is not None:
                try:
                    subject = self._shell.authenticate(certificate, client_ip, METHOD_CERTIFICATE)
                except AuthenticationFailed:
                    # The TLS layer verified it: it is simply not mapped to any user
                    _logger.info(
                        "Client certificate %s (%s) from %s is not mapped to a user",
                        certificate.fingerprint,
                        certificate.subject,
                        client_ip,
                    )
                else:
                    _logger.info("User %s from %s authenticated by certificate", subject.name, client_ip)
                    return subject

        if not self._shell.is_auth_required():
            return ANONYMOUS

        if not self._is_tls():
            _logger.warning(
                "Password login prompted to %s over a clear-text connection: "
                "the password will travel unencrypted",
                client_ip,
            )

        for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
            self.send("Login: ")
            username = self.read_line(self._login_remaining())
            if username is None:
                return None

            self.send("Password: ")
            password = self.read_line(self._login_remaining())
            if password is None:
                return None

            try:
                # Only the end of line is removed: a password may start or end with a space
                subject = self._shell.authenticate(
                    UsernamePassword(username.strip(), password.rstrip("\r\n")), client_ip, METHOD_PASSWORD
                )
            except AuthenticationFailed:
                # The attempted name is not logged: it is sometimes a password typed too early
                _logger.warning("Failed login %d/%d from %s", attempt, MAX_LOGIN_ATTEMPTS, client_ip)
                self.send("Login incorrect\n")
            else:
                _logger.info("User %s from %s authenticated by password", subject.name, client_ip)
                return subject

        _logger.warning("Too many failed logins from %s: closing the connection", client_ip)
        self.send("Too many failed login attempts.\n")
        return None

    def _report_error(self, session: beans.ShellSession, client_ip: str, ex: Exception) -> None:
        """
        Reports an error which happened outside of a command.

        A stack trace describes the server and the data it handles, so it is only sent
        to a subject granted the debug permission. It is always logged, with the error ID
        the client gets instead.

        :param session: The session of the client
        :param client_ip: The address of the client
        :param ex: The error
        """
        error_id = uuid.uuid4().hex
        stack = traceback.format_exc()
        _logger.error(
            "Error %s in the session of %s from %s:\n%s", error_id, session.subject.name, client_ip, stack
        )

        if self._shell.is_debug_allowed(session.subject):
            self.send(f"\nError during last command: {ex}\n")
            self.send(stack)
        else:
            self.send(f"\nError during last command. Error ID: {error_id}\n")

    def _audit(self, session: beans.ShellSession, client_ip: str, line: str) -> None:
        """
        Logs a command line about to be executed.

        Only the command name goes to the INFO level: its arguments may be secrets, like
        the password of a configuration entry.

        :param session: The session of the client
        :param client_ip: The address of the client
        :param line: The command line
        """
        _logger.info(
            "User %s from %s ran %s",
            session.subject.name,
            client_ip,
            self._shell.get_command_name(line) or "an unknown command",
        )
        _logger.debug("User %s from %s ran: %s", session.subject.name, client_ip, line)

    def handle(self) -> None:
        """
        Handles a TCP client
        """
        client_ip = self.client_address[0]
        if not self._handshake_done or self._reader is None:
            # Already logged by setup()
            return

        _logger.info("RemoteConsole client connected: [%s]:%d", client_ip, self.client_address[1])

        try:
            # Print the banner
            self.send(self._shell.get_banner())

            # No command at all, not even "help", before the client is authenticated
            subject = self._login(client_ip)
            if subject is None:
                return

            # Prepare the session: commands reading their own input share the reader
            # and its limits
            session = beans.ShellSession(
                beans.IOHandler(
                    cast(Any, _ReaderInput(self._reader, self._shell.get_idle_timeout())), self.wfile
                ),
                {"remote_client_ip": client_ip},
                subject,
            )

            def get_ps1() -> str:
                """
                Gets the prompt string from the session of the shell service

                :return: The prompt string
                """
                try:
                    ps1_var = session.get("PS1")
                    return str(ps1_var) if ps1_var else ""
                except KeyError:
                    return self._shell.get_ps1()

            self.send(get_ps1())

            while True:
                line = self.read_line()
                if line is None:
                    break

                # Strip the line
                line = line.strip()
                if line:
                    self._audit(session, client_ip, line)

                    # Execute it
                    try:
                        # Every command, so that the security decorators see who runs it
                        with run_as(session.subject):
                            self._shell.handle_line(line, session)
                    except KeyboardInterrupt:
                        # Stop there on interruption
                        self.send("\nInterruption received.")
                        return
                    except OSError:
                        # I/O errors are fatal
                        _logger.exception("Error communicating with a client")
                        break
                    except Exception as ex:  # noqa: BLE001
                        # Other exceptions are not important
                        self._report_error(session, client_ip, ex)

                # Print the prompt
                self.send(get_ps1())
        except _SessionClosed as ex:
            _logger.warning("Closing the session of %s: %s", client_ip, ex.reason)
            self.send(f"\n{ex.reason}\n")
        finally:
            _logger.info("RemoteConsole client gone: [%s]:%d", client_ip, self.client_address[1])

            try:
                # Be polite
                self.send("\nSession closed. Good bye.\n")
                self.finish()
            except OSError as ex:
                _logger.warning("Error cleaning up connection: %s", ex)


# ------------------------------------------------------------------------------


class ThreadingTCPServerFamily(socketserver.ThreadingTCPServer):
    """
    Threaded TCP Server handling different address families
    """

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[socketserver.BaseRequestHandler],
        cert_file: str | None = None,
        key_file: str | None = None,
        key_password: str | None = None,
        ca_file: str | None = None,
        max_clients: int | None = None,
    ):
        """
        Sets up the TCP server. Doesn't bind nor activate it.

        :param server_address: Server binding address
        :param request_handler_class: Class to instantiate for each client
        :param cert_file: Path to the server certificate
        :param key_file: Path to the server private key
        :param key_password: Password for the key file
        :param ca_file: Path to Certificate Authority to authenticate clients
        :param max_clients: Maximum number of simultaneous clients, or None
        """
        # Clients being handled, to refuse new ones past the limit
        self.max_clients = max_clients
        self._clients = 0
        self._clients_lock = threading.Lock()

        # Determine the address family
        addr_info = socket.getaddrinfo(server_address[0], server_address[1], 0, 0, socket.SOL_TCP)

        # Change the address family before the socket is created
        # Get the family of the first possibility
        self.address_family = addr_info[0][0]

        # Keep track of SSL arguments
        self.cert_file = cert_file
        self.key_file = key_file
        self.key_password = key_password
        self.ca_file = ca_file

        # Prepare the SSL context once: the certificate and key files must not
        # be re-read and re-parsed for each incoming connection
        self.ssl_context: ssl.SSLContext | None = self.__make_ssl_context()

        # Call the super constructor
        socketserver.ThreadingTCPServer.__init__(self, server_address, request_handler_class, False)
        if self.address_family == socket.AF_INET6:
            # Explicitly ask to be accessible both by IPv4 and IPv6
            try:
                pelix.ipv6utils.set_double_stack(self.socket)
            except AttributeError:
                _logger.exception("System lacks IPv6 constant")
            except OSError:
                _logger.exception("Error setting up IPv6 double stack")

    def __make_ssl_context(self) -> "ssl.SSLContext | None":
        """
        Prepares the SSL context to accept clients with a certificate signed by
        a known chain of authority. Other clients will be rejected during the
        handshake.

        :return: The SSL context, or None if TLS is not configured
        """
        if not HAS_SSL or not self.cert_file:
            # Nothing to do
            return None

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            # Force a valid/signed client-side certificate
            context.verify_mode = ssl.CERT_REQUIRED

            # Load the server certificate
            context.load_cert_chain(
                certfile=self.cert_file,
                keyfile=self.key_file,
                password=self.key_password,
            )

            if self.ca_file:
                # Load the given authority chain
                context.load_verify_locations(self.ca_file)
            else:
                # Load the default chain if none given
                context.load_default_certs(ssl.Purpose.CLIENT_AUTH)
        except Exception as ex:
            # Explicitly log the error as the default behaviour hides it
            _logger.error("Error setting up the SSL context: %s", ex)
            raise

        return context

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        """
        Accepts a new client. Sets up SSL wrapping if necessary.

        :return: A tuple: (client socket, client address tuple)
        """
        # Accept the client
        client_socket, client_address = self.socket.accept()

        if self.ssl_context is not None:
            try:
                # The handshake is done by the thread of the client (see RemoteConsole.setup):
                # done here, a client which never finishes it would block the whole server
                client_stream = cast(
                    socket.socket,
                    self.ssl_context.wrap_socket(
                        client_socket, server_side=True, do_handshake_on_connect=False
                    ),
                )
            except ssl.SSLError as ex:
                # Explicitly log the exception before re-raising it
                _logger.warning("Error during SSL handshake with %s: %s", client_address, ex)
                client_socket.close()
                raise
        else:
            # Nothing to do, use the raw socket
            client_stream = client_socket

        return client_stream, client_address

    def process_request_thread(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: tuple[str, int]
    ) -> None:
        """
        Handles the request in its own thread, named after the client address.

        The thread itself is started by ``ThreadingMixIn.process_request()``.
        Overriding that method to name the thread would bypass this
        bookkeeping.
        """
        threading.current_thread().name = f"RemoteShell-{self.server_address[1]}-Client-{client_address[:2]}"
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._release_client()

    def verify_request(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: Any
    ) -> bool:
        """
        Refuses a new client when the maximum number of clients is reached.

        The slot is reserved here, in the thread accepting the connections, and
        released when the thread of the client ends.
        """
        with self._clients_lock:
            if self.max_clients is not None and self._clients >= self.max_clients:
                _logger.warning(
                    "Refusing the connection of %s: already %d clients", client_address, self._clients
                )
                return False

            self._clients += 1
            return True

    def process_request(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: Any
    ) -> None:
        """
        Starts the thread of a client, releasing its slot if that fails
        """
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._release_client()
            raise

    def _release_client(self) -> None:
        """
        Frees the slot of a client which is gone
        """
        with self._clients_lock:
            self._clients = max(0, self._clients - 1)


def _create_server(
    shell: "IPopoRemoteShell",
    server_address: str,
    port: int,
    cert_file: str | None = None,
    key_file: str | None = None,
    key_password: str | None = None,
    ca_file: str | None = None,
    max_clients: int | None = None,
) -> tuple[threading.Thread, socketserver.TCPServer, SharedBoolean]:
    """
    Creates the TCP console on the given address and port

    :param shell: The remote shell handler
    :param server_address: Server bound address
    :param port: Server port
    :param cert_file: Path to the server certificate
    :param key_file: Path to the server private key
    :param key_password: Password for the key file
    :param ca_file: Path to Certificate Authority to authenticate clients
    :param max_clients: Maximum number of simultaneous clients, or None
    :return: A tuple: Server thread, TCP server object, Server active flag
    """
    # Set up the request handler creator
    active_flag = SharedBoolean(True)

    def request_handler(*rh_args: Any) -> RemoteConsole:
        """
        Constructs a RemoteConsole as TCP request handler
        """
        return RemoteConsole(shell, active_flag, *rh_args)

    # Set up the server
    server = ThreadingTCPServerFamily(
        (server_address, port),
        cast(type[socketserver.BaseRequestHandler], request_handler),
        cert_file,
        key_file,
        key_password,
        ca_file,
        max_clients,
    )

    # Set flags
    server.daemon_threads = True
    server.allow_reuse_address = True

    # Activate the server
    server.server_bind()
    server.server_activate()

    # Serve clients
    server_thread = threading.Thread(target=server.serve_forever, name=f"RemoteShell-{port}")
    server_thread.daemon = True
    server_thread.start()

    return server_thread, server, active_flag


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.shell.FACTORY_REMOTE_SHELL)
@Provides(pelix.shell.RemoteShell)
@Requires("_shell", pelix.shell.ShellService)
@Requires("_authorization", Authorization, optional=True)
@Property("_auth_required", PROP_AUTH_REQUIRED, False)
@Property("_max_line_length", PROP_MAX_LINE_LENGTH, DEFAULT_MAX_LINE_LENGTH)
@Property("_idle_timeout", PROP_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)
@Property("_login_timeout", PROP_LOGIN_TIMEOUT, DEFAULT_LOGIN_TIMEOUT)
@Property("_max_clients", PROP_MAX_CLIENTS, DEFAULT_MAX_CLIENTS)
@Property("_address", "pelix.shell.address", "localhost")
@Property("_port", "pelix.shell.port", 9000)
@Property("_encoding", "pelix.shell.encoding", "utf-8")
@Property("_ca_file", "pelix.shell.ssl.ca", None)
@Property("_cert_file", "pelix.shell.ssl.cert", None)
@Property("_key_file", "pelix.shell.ssl.key", None)
@HiddenProperty("_key_password", "pelix.shell.ssl.key_password", None)
class IPopoRemoteShell(pelix.shell.RemoteShell):
    """
    The iPOPO Remote Shell, based on the Pelix Shell
    """

    _shell: pelix.shell.ShellService
    _authorization: Authorization | None

    def __init__(self) -> None:
        """
        Sets up the component
        """
        # Security configuration
        self._auth_required: bool = False
        self._authorization = None

        # Limits (None: no limit)
        self._max_line_length: Any = DEFAULT_MAX_LINE_LENGTH
        self._idle_timeout: Any = DEFAULT_IDLE_TIMEOUT
        self._login_timeout: Any = DEFAULT_LOGIN_TIMEOUT
        self._max_clients: Any = DEFAULT_MAX_CLIENTS
        self.__max_line_length: int | None = DEFAULT_MAX_LINE_LENGTH
        self.__idle_timeout: float | None = DEFAULT_IDLE_TIMEOUT
        self.__login_timeout: float | None = DEFAULT_LOGIN_TIMEOUT
        self.__max_clients: int | None = DEFAULT_MAX_CLIENTS

        # Server configuration
        self._address: str | None = None
        self._port: int | None = 0
        self._encoding: str = "utf-8"

        # SSL configuration
        self._ca_file: str | None = None
        self._cert_file: str | None = None
        self._key_file: str | None = None
        self._key_password: str | None = None

        # Internals
        self._thread: threading.Thread | None = None
        self._server: socketserver.TCPServer | None = None
        self._server_flag: SharedBoolean = SharedBoolean()

    def get_access(self) -> tuple[str | None, int | None]:
        """
        Returns the access to this remote shell

        :return: A (host, port) tuple
        """
        return self._address, self._port

    def get_encoding(self) -> str:
        """
        Returns the stream encoding
        """
        return self._encoding

    def get_banner(self) -> str:
        """
        Retrieves the shell banner

        :return: The shell banner
        """
        line = "-" * 72
        shell_banner = self._shell.get_banner()
        return f"{line}\n{shell_banner}\niPOPO Remote Shell\n{line}\n"

    def get_ps1(self) -> str:
        """
        Returns the shell prompt

        :return: The shell prompt
        """
        return self._shell.get_ps1()

    def get_max_line_length(self) -> int | None:
        """
        Returns the longest line, in bytes, a client can send, or None
        """
        return self.__max_line_length

    def get_idle_timeout(self) -> float | None:
        """
        Returns the seconds without input before a session is closed, or None
        """
        return self.__idle_timeout

    def get_login_timeout(self) -> float | None:
        """
        Returns the seconds a client gets to finish the TLS handshake and log in, or None
        """
        return self.__login_timeout

    def is_auth_required(self) -> bool:
        """
        Tells whether a client must authenticate before running any command
        """
        return self._auth_required

    def is_security_active(self) -> bool:
        """
        Tells whether the security core is active, which its authorization service shows
        """
        return self._authorization is not None

    def authenticate(self, credentials: Credentials, client_ip: str, method: str) -> Subject:
        """
        Authenticates a client through the security layer.

        :param credentials: What the client presented
        :param client_ip: The address of the client, for the brute-force throttle
        :param method: Name of the authentication mechanism
        :return: The authenticated subject
        :raise AuthenticationFailed: The credentials are wrong, unknown, or locked out
        """
        if not self.is_security_active():
            _logger.error(
                "Cannot authenticate a remote shell client: the pelix.security.core bundle is not active"
            )
            raise AuthenticationFailed("No security core")

        # Looked up at each call: when its bundle is reinstalled, the module is reloaded,
        # and a reference taken at import time would point to a stopped copy
        core = importlib.import_module("pelix.security.core")
        return core.authenticate(credentials, client_ip, method=method, transport=TRANSPORT)

    def is_debug_allowed(self, subject: Subject) -> bool:
        """
        Tells whether a subject may see the stack trace of an error

        :param subject: The subject of a session
        :return: True if it is granted the debug permission
        """
        authorization = self._authorization
        if authorization is None:
            return False

        try:
            return authorization.is_permitted(PERMISSION_DEBUG, subject)
        except Exception:
            # Denying is the only safe answer of a policy which cannot answer
            _logger.exception("Error checking the %s permission", PERMISSION_DEBUG)
            return False

    def get_command_name(self, line: str) -> str | None:
        """
        Resolves the command a line would run, without its arguments.

        :param line: A command line
        :return: The command, as ``namespace.command``, or None if it is unknown
        """
        try:
            tokens = shlex.split(line, True, True)
            if not tokens:
                return None

            namespace, command = self._shell.get_ns_command(tokens[0])
        except ValueError:
            return None

        return f"{namespace}.{command}"

    def handle_line(self, line: str, session: beans.ShellSession) -> bool:
        """
        Handles the command line.

        **Does not catch exceptions !**

        :param line: The command line
        :param session: The current shell session
        :return: The execution result (True on success, else False)
        """
        return self._shell.execute(line, session)

    @Validate
    def validate(self, _: pelix.framework.BundleContext) -> None:
        """
        Component validation
        """
        if not self._address:
            # Local host by default
            self._address = "localhost"

        try:
            self._port = int(self._port or 0)
            if self._port < 0 or self._port > 65535:
                # Invalid port value
                self._port = 0
        except (ValueError, TypeError):
            # Invalid port string: use a random port
            self._port = 0

        if not self._encoding:
            self._encoding = "utf-8"

        # Normalized into private copies: the property fields keep what was configured
        max_line_length = _to_limit(self._max_line_length, DEFAULT_MAX_LINE_LENGTH)
        self.__max_line_length = int(max_line_length) if max_line_length is not None else None
        self.__idle_timeout = _to_limit(self._idle_timeout, DEFAULT_IDLE_TIMEOUT)
        self.__login_timeout = _to_limit(self._login_timeout, DEFAULT_LOGIN_TIMEOUT)
        max_clients = _to_limit(self._max_clients, DEFAULT_MAX_CLIENTS)
        self.__max_clients = int(max_clients) if max_clients is not None else None

        self._auth_required = _to_bool(self._auth_required)
        if self._auth_required and not self._cert_file:
            _logger.warning(
                "The remote shell requires authentication without TLS: passwords will travel "
                "in clear text. Set pelix.shell.ssl.cert and pelix.shell.ssl.ca"
            )

        if self._cert_file and not self._ca_file:
            # Without an explicit authority chain, any client certificate signed
            # by any CA of the system trust store would be accepted
            _logger.error(
                "pelix.shell.ssl.cert is set without pelix.shell.ssl.ca: ANY client certificate "
                "signed by ANY CA in the system trust store will be accepted by a shell which can "
                "install and start arbitrary bundles. Set pelix.shell.ssl.ca. "
                "This configuration will be refused in iPOPO 3.3.0."
            )

        # Start the TCP server
        self._thread, self._server, self._server_flag = _create_server(
            self,
            self._address,
            self._port,
            self._cert_file,
            self._key_file,
            self._key_password,
            self._ca_file,
            self.__max_clients,
        )

        # Property update (if port was 0)
        self._port = self._server.socket.getsockname()[1]
        _logger.info("RemoteShell validated on port: %d", self._port)

    @Invalidate
    def invalidate(self, _: pelix.framework.BundleContext) -> None:
        """
        Component invalidation
        """
        # Stop the clients loops
        if self._server is not None:
            self._server_flag.set_value(False)

            # Shutdown the server
            self._server.shutdown()

            if self._thread is not None:
                self._thread.join(2)

            # Close the server socket (ignore errors)
            self._server.server_close()
            _logger.info("RemoteShell gone from port: %d", self._port)

        # Clean up
        self._thread = None
        self._server = None


# ------------------------------------------------------------------------------


def _run_interpreter(variables: dict[str, Any], banner: str) -> None:
    """
    Runs a Python interpreter console and blocks until the user exits it.

    :param variables: Interpreters variables (locals)
    :param banner: Start-up banners
    """
    # Script-only imports
    import code

    try:
        import readline
        import rlcompleter

        readline.set_completer(rlcompleter.Completer(variables).complete)
        readline.parse_and_bind("tab: complete")
    except ImportError:
        # readline is not available: ignore
        pass

    # Start the console
    shell = code.InteractiveConsole(variables)
    shell.interact(banner)


def main(argv: list[str] | None = None) -> int:
    """
    Script entry point

    :param argv: Script arguments (None for sys.argv)
    :return: An exit code or None
    """
    # Prepare arguments
    parser = argparse.ArgumentParser(
        prog="pelix.shell.remote",
        parents=[make_common_parser()],
        description=f"Pelix Remote Shell ({'with' if HAS_SSL else 'without'} SSL support)",
    )

    # Remote shell options
    group = parser.add_argument_group("Remote Shell options")
    group.add_argument(
        "-a",
        "--address",
        default="localhost",
        help="The remote shell binding address",
    )
    group.add_argument(
        "-p",
        "--port",
        type=int,
        default=9000,
        help="The remote shell binding port",
    )

    if HAS_SSL:
        # Remote Shell TLS options
        group = parser.add_argument_group("TLS Options")
        group.add_argument("--cert", help="Path to the server certificate file")
        group.add_argument(
            "--key",
            help="Path to the server key file (can be omitted if the key is in the certificate)",
        )
        group.add_argument(
            "--key-password",
            help="Password of the server key.Set to '-' for a password request.",
        )
        group.add_argument(
            "--ca-chain",
            help="Path to the CA chain file to authenticate clients",
        )

    # Local options
    group = parser.add_argument_group("Local options")
    group.add_argument(
        "--no-input",
        action="store_true",
        help="Run without input (for daemon mode)",
    )

    # Parse them
    args = parser.parse_args(argv)

    # Handle arguments
    init = handle_common_arguments(args)

    # Set the initial bundles
    bundles = [
        "pelix.ipopo.core",
        "pelix.shell.core",
        "pelix.shell.ipopo",
        "pelix.shell.remote",
    ]
    bundles.extend(init.bundles)

    # Start a Pelix framework
    framework = pelix.framework.create_framework(utilities.remove_duplicates(bundles), init.properties)
    framework.start()
    context = framework.get_bundle_context()

    # Instantiate configured components
    init.instantiate_components(framework.get_bundle_context())

    # Instantiate a Remote Shell, if necessary
    with use_ipopo(context) as ipopo:
        rshell_name = "remote-shell"
        try:
            ipopo.get_instance_details(rshell_name)
        except ValueError:
            # Component doesn't exist, we can instantiate it.
            if HAS_SSL:
                # Copy parsed arguments
                ca_chain = args.ca_chain
                cert = args.cert
                key = args.key

                # Normalize the TLS key file password argument
                if args.key_password == "-":
                    import getpass

                    key_password = getpass.getpass(f"Password for {args.key or args.cert}: ")
                else:
                    key_password = args.key_password
            else:
                # SSL support is missing:
                # Ensure the SSL arguments are defined but set to None
                ca_chain = None
                cert = None
                key = None
                key_password = None

            # Setup the component
            rshell = cast(
                IPopoRemoteShell,
                ipopo.instantiate(
                    pelix.shell.FACTORY_REMOTE_SHELL,
                    rshell_name,
                    {
                        "pelix.shell.address": args.address,
                        "pelix.shell.port": args.port,
                        "pelix.shell.ssl.ca": ca_chain,
                        "pelix.shell.ssl.cert": cert,
                        "pelix.shell.ssl.key": key,
                        "pelix.shell.ssl.key_password": key_password,
                    },
                ),
            )

            # Avoid loose reference to the password
            del key_password
        else:
            _logger.error(
                "A remote shell component (%s) is already configured. Abandon.",
                rshell_name,
            )
            return 1

    # Prepare a banner
    host, port = rshell.get_access()
    try:
        if args.no_input:
            # No input required: just print the access to the shell
            print("Remote shell bound to:", host, "- port:", port, file=sys.stderr)

            try:
                while not framework.wait_for_stop(1):
                    # Awake from wait every second to let KeyboardInterrupt
                    # exception to raise
                    pass
            except KeyboardInterrupt:
                print("Got Ctrl+C: exiting.", file=sys.stderr)
                return 127
        else:
            # Prepare interpreter variables
            variables = {
                "__name__": "__console__",
                "__doc__": None,
                "__package__": None,
                "framework": framework,
                "context": context,
                "use_ipopo": use_ipopo,
            }

            lines = "-" * 80
            banner = (
                f"{lines}\nPython interpreter with Pelix Remote Shell\n"
                f"Remote shell bound to: {host}:{port}\n{lines}\n"
                f"Python version: {sys.version}\n"
            )

            # Run an interpreter
            _run_interpreter(variables, banner)
    finally:
        # Stop the framework
        framework.stop()

    return 0


if __name__ == "__main__":
    # Run the entry point
    sys.exit(main())
