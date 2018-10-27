#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO remote shell

Provides a remote interface for the Pelix shell that can be accessed using
telnet or netcat.

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

from __future__ import print_function

# Standard library
from select import select
import argparse
import logging
import threading
import socket
import sys

try:
    # Some Python distributions don't support SSL
    import ssl
except ImportError:
    ssl = None

try:
    # Python 3
    # pylint: disable=F0401
    import socketserver
except ImportError:
    # Python 2
    # pylint: disable=F0401
    import SocketServer as socketserver

# iPOPO
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.decorators import (
    ComponentFactory,
    Requires,
    Property,
    Validate,
    Invalidate,
    Provides,
    HiddenProperty,
)

# Pelix
from pelix.shell.console import make_common_parser, handle_common_arguments
import pelix.framework
import pelix.ipv6utils
import pelix.shell
import pelix.shell.beans as beans
import pelix.utilities as utilities

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class SharedBoolean(object):
    """
    Shared boolean between objects / threads
    """

    def __init__(self, value=False):
        """
        Set up members
        """
        self._lock = threading.Lock()
        self._value = value

    def get_value(self):
        """
        Retrieves the boolean value
        """
        with self._lock:
            return self._value

    def set_value(self, value):
        """
        Sets the boolean value
        """
        with self._lock:
            self._value = value


# ------------------------------------------------------------------------------


class RemoteConsole(socketserver.StreamRequestHandler):
    """
    Handles incoming connections and redirect network stream to the Pelix shell
    """

    def __init__(self, shell_svc, active_flag, *args):
        """
        Sets up members

        :param shell_svc: The underlying Pelix shell service
        :param active_flag: Common flag for stopping the client communication
        """
        self._shell = shell_svc
        self._active = active_flag
        socketserver.StreamRequestHandler.__init__(self, *args)

    def send(self, data):
        """
        Tries to send data to the client.

        :param data: Data to be sent
        :return: True if the data was sent, False on error
        """
        if data is not None:
            data = data.encode("UTF-8")

        try:
            self.wfile.write(data)
            self.wfile.flush()
            return True

        except IOError:
            # An error occurred, mask it
            # -> This allows to handle the command even if the client has been
            # disconnect (i.e. "echo stop 0 | nc localhost 9000")
            return False

    def handle(self):
        """
        Handles a TCP client
        """
        _logger.info(
            "RemoteConsole client connected: [%s]:%d",
            self.client_address[0],
            self.client_address[1],
        )

        # Prepare the session
        session = beans.ShellSession(
            beans.IOHandler(self.rfile, self.wfile),
            {"remote_client_ip": self.client_address[0]},
        )

        # Print the banner
        def get_ps1():
            """
            Gets the prompt string from the session of the shell service

            :return: The prompt string
            """
            try:
                return session.get("PS1")
            except KeyError:
                return self._shell.get_ps1()

        self.send(self._shell.get_banner())
        self.send(get_ps1())

        try:
            while self._active.get_value():
                # Wait for data
                rlist = select([self.connection], [], [], .5)[0]
                if not rlist:
                    # Nothing to do (poll timed out)
                    continue

                data = self.rfile.readline()
                if not data:
                    # End of stream (client gone)
                    break

                # Strip the line
                line = data.strip()
                if not data:
                    # Empty line
                    continue

                # Execute it
                try:
                    self._shell.handle_line(line, session)
                except KeyboardInterrupt:
                    # Stop there on interruption
                    self.send("\nInterruption received.")
                    return
                except IOError as ex:
                    # I/O errors are fatal
                    _logger.exception(
                        "Error communicating with a client: %s", ex
                    )
                    break
                except Exception as ex:
                    # Other exceptions are not important
                    import traceback

                    self.send("\nError during last command: {0}\n".format(ex))
                    self.send(traceback.format_exc())

                # Print the prompt
                self.send(get_ps1())
        finally:
            _logger.info(
                "RemoteConsole client gone: [%s]:%d",
                self.client_address[0],
                self.client_address[1],
            )

            try:
                # Be polite
                self.send("\nSession closed. Good bye.\n")
                self.finish()
            except IOError as ex:
                _logger.warning("Error cleaning up connection: %s", ex)


# ------------------------------------------------------------------------------


class ThreadingTCPServerFamily(socketserver.ThreadingTCPServer):
    """
    Threaded TCP Server handling different address families
    """

    def __init__(
        self,
        server_address,
        request_handler_class,
        cert_file=None,
        key_file=None,
        key_password=None,
        ca_file=None,
    ):
        """
        Sets up the TCP server. Doesn't bind nor activate it.

        :param server_address: Server binding address
        :param request_handler_class: Class to instantiate for each client
        :param cert_file: Path to the server certificate
        :param key_file: Path to the server private key
        :param key_password: Password for the key file
        :param ca_file: Path to Certificate Authority to authenticate clients
        """
        # Determine the address family
        addr_info = socket.getaddrinfo(
            server_address[0], server_address[1], 0, 0, socket.SOL_TCP
        )

        # Change the address family before the socket is created
        # Get the family of the first possibility
        self.address_family = addr_info[0][0]

        # Keep track of SSL arguments
        self.cert_file = cert_file
        self.key_file = key_file
        self.key_password = key_password
        self.ca_file = ca_file

        # Call the super constructor
        socketserver.ThreadingTCPServer.__init__(
            self, server_address, request_handler_class, False
        )
        if self.address_family == socket.AF_INET6:
            # Explicitly ask to be accessible both by IPv4 and IPv6
            try:
                pelix.ipv6utils.set_double_stack(self.socket)
            except AttributeError as ex:
                _logger.exception("System misses IPv6 constant: %s", ex)
            except socket.error as ex:
                _logger.exception("Error setting up IPv6 double stack: %s", ex)

    def get_request(self):
        """
        Accepts a new client. Sets up SSL wrapping if necessary.

        :return: A tuple: (client socket, client address tuple)
        """
        # Accept the client
        client_socket, client_address = self.socket.accept()

        if ssl is not None and self.cert_file:
            # Setup an SSL context to accept clients with a certificate
            # signed by a known chain of authority.
            # Other clients will be rejected during handshake.
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
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

            try:
                # SSL handshake
                client_stream = context.wrap_socket(
                    client_socket, server_side=True
                )
            except ssl.SSLError as ex:
                # Explicitly log the exception before re-raising it
                _logger.warning(
                    "Error during SSL handshake with %s: %s", client_address, ex
                )
                raise
        else:
            # Nothing to do, use the raw socket
            client_stream = client_socket

        return client_stream, client_address

    def process_request(self, request, client_address):
        """
        Starts a new thread to process the request, adding the client address
        in its name.
        """
        thread = threading.Thread(
            name="RemoteShell-{0}-Client-{1}".format(
                self.server_address[1], client_address[:2]
            ),
            target=self.process_request_thread,
            args=(request, client_address),
        )
        thread.daemon = self.daemon_threads
        thread.start()


def _create_server(
    shell,
    server_address,
    port,
    cert_file=None,
    key_file=None,
    key_password=None,
    ca_file=None,
):
    """
    Creates the TCP console on the given address and port

    :param shell: The remote shell handler
    :param server_address: Server bound address
    :param port: Server port
    :param cert_file: Path to the server certificate
    :param key_file: Path to the server private key
    :param key_password: Password for the key file
    :param ca_file: Path to Certificate Authority to authenticate clients
    :return: A tuple: Server thread, TCP server object, Server active flag
    """
    # Set up the request handler creator
    active_flag = SharedBoolean(True)

    def request_handler(*rh_args):
        """
        Constructs a RemoteConsole as TCP request handler
        """
        return RemoteConsole(shell, active_flag, *rh_args)

    # Set up the server
    server = ThreadingTCPServerFamily(
        (server_address, port),
        request_handler,
        cert_file,
        key_file,
        key_password,
        ca_file,
    )

    # Set flags
    server.daemon_threads = True
    server.allow_reuse_address = True

    # Activate the server
    server.server_bind()
    server.server_activate()

    # Serve clients
    server_thread = threading.Thread(
        target=server.serve_forever, name="RemoteShell-{0}".format(port)
    )
    server_thread.daemon = True
    server_thread.start()

    return server_thread, server, active_flag


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.shell.FACTORY_REMOTE_SHELL)
@Provides(pelix.shell.SERVICE_SHELL_REMOTE)
@Requires("_shell", pelix.shell.SERVICE_SHELL)
@Property("_address", "pelix.shell.address", "localhost")
@Property("_port", "pelix.shell.port", 9000)
@Property("_ca_file", "pelix.shell.ssl.ca", None)
@Property("_cert_file", "pelix.shell.ssl.cert", None)
@Property("_key_file", "pelix.shell.ssl.key", None)
@HiddenProperty("_key_password", "pelix.shell.ssl.key_password", None)
class IPopoRemoteShell(object):
    """
    The iPOPO Remote Shell, based on the Pelix Shell
    """

    def __init__(self):
        """
        Sets up the component
        """
        # Component shell
        self._shell = None
        self._address = None
        self._port = 0

        # SSL configuration
        self._ca_file = None
        self._cert_file = None
        self._key_file = None
        self._key_password = None

        # Internals
        self._thread = None
        self._server = None
        self._server_flag = None

    def get_access(self):
        """
        Implementation of the remote shell specification

        :return: A (host, port) tuple
        """
        return self._address, self._port

    def get_banner(self):
        """
        Retrieves the shell banner

        :return: The shell banner
        """
        line = "-" * 72
        shell_banner = self._shell.get_banner()

        return "{lines}\n{shell_banner}\niPOPO Remote Shell\n{lines}\n".format(
            lines=line, shell_banner=shell_banner
        )

    def get_ps1(self):
        """
        Returns the shell prompt

        :return: The shell prompt
        """
        return self._shell.get_ps1()

    def handle_line(self, line, session):
        """
        Handles the command line.

        **Does not catch exceptions !**

        :param line: The command line
        :param session: The current shell session
        :return: The execution result (True on success, else False)
        """
        return self._shell.execute(line, session)

    @Validate
    def validate(self, _):
        """
        Component validation
        """
        if not self._address:
            # Local host by default
            self._address = "localhost"

        try:
            self._port = int(self._port)
            if self._port < 0 or self._port > 65535:
                # Invalid port value
                self._port = 0
        except (ValueError, TypeError):
            # Invalid port string: use a random port
            self._port = 0

        # Start the TCP server
        self._thread, self._server, self._server_flag = _create_server(
            self,
            self._address,
            self._port,
            self._cert_file,
            self._key_file,
            self._key_password,
            self._ca_file,
        )

        # Property update (if port was 0)
        self._port = self._server.socket.getsockname()[1]
        _logger.info("RemoteShell validated on port: %d", self._port)

    @Invalidate
    def invalidate(self, _):
        """
        Component invalidation
        """
        # Stop the clients loops
        if self._server is not None:
            self._server_flag.set_value(False)

            # Shutdown the server
            self._server.shutdown()
            self._thread.join(2)

            # Close the server socket (ignore errors)
            self._server.server_close()
            _logger.info("RemoteShell gone from port: %d", self._port)

        # Clean up
        self._thread = None
        self._server = None
        self._server_flag = None


# ------------------------------------------------------------------------------


def _run_interpreter(variables, banner):
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


def main(argv=None):
    """
    Script entry point

    :param argv: Script arguments (None for sys.argv)
    :return: An exit code or None
    """
    # Prepare arguments
    parser = argparse.ArgumentParser(
        prog="pelix.shell.remote",
        parents=[make_common_parser()],
        description="Pelix Remote Shell ({} SSL support)".format(
            "with" if ssl is not None else "without"
        ),
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

    if ssl is not None:
        # Remote Shell TLS options
        group = parser.add_argument_group("TLS Options")
        group.add_argument("--cert", help="Path to the server certificate file")
        group.add_argument(
            "--key",
            help="Path to the server key file "
            "(can be omitted if the key is in the certificate)",
        )
        group.add_argument(
            "--key-password",
            help="Password of the server key."
            "Set to '-' for a password request.",
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
    framework = pelix.framework.create_framework(
        utilities.remove_duplicates(bundles), init.properties
    )
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

            if ssl is not None:
                # Copy parsed arguments
                ca_chain = args.ca_chain
                cert = args.cert
                key = args.key

                # Normalize the TLS key file password argument
                if args.key_password == "-":
                    import getpass

                    key_password = getpass.getpass(
                        "Password for {}: ".format(args.key or args.cert)
                    )
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
            rshell = ipopo.instantiate(
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
            )

            # Avoid loose reference to the password
            del key_password
        else:
            logging.error(
                "A remote shell component (%s) is already "
                "configured. Abandon.",
                rshell_name,
            )
            return 1

    # Prepare a banner
    host, port = rshell.get_access()
    try:
        if args.no_input:
            # No input required: just print the access to the shell
            print("Remote shell bound to:", host, "- port:", port)

            try:
                while not framework.wait_for_stop(1):
                    # Awake from wait every second to let KeyboardInterrupt
                    # exception to raise
                    pass
            except KeyboardInterrupt:
                print("Got Ctrl+C: exiting.")
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

            banner = (
                "{lines}\nPython interpreter with Pelix Remote Shell\n"
                "Remote shell bound to: {host}:{port}\n{lines}\n"
                "Python version: {version}\n".format(
                    lines="-" * 80, version=sys.version, host=host, port=port
                )
            )

            # Run an interpreter
            _run_interpreter(variables, banner)
    finally:
        # Stop the framework
        framework.stop()


if __name__ == "__main__":
    # Run the entry point
    sys.exit(main() or 0)
