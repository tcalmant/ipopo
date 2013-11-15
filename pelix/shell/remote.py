#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO remote shell

Provides a remote interface for the Pelix shell that can be accessed using
telnet or netcat.

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.1.2
:status: Beta

..

    Copyright 2013 isandlaTech

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

# Module version
__version_info__ = (0, 1, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Property, \
    Validate, Invalidate, Provides

# Shell constants
import pelix.shell

# Standard library
from select import select
import logging
import threading
import socket

try:
    # Python 3
    import socketserver

except ImportError:
    # Python 2
    import SocketServer as socketserver

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
        _logger.info("RemoteConsole client connected: [%s]:%d",
                     self.client_address[0], self.client_address[1])

        # Print the banner
        ps1 = self._shell.get_ps1()
        self.send(self._shell.get_banner())
        self.send(ps1)

        try:
            while self._active.get_value():
                # Wait for data
                rlist = select([self.rfile], [], [], .5)[0]
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
                    self._shell.handle_line(self.rfile, self.wfile, line)

                except KeyboardInterrupt:
                    # Stop there on interruption
                    self.send("\nInterruption received.")
                    return

                except IOError as ex:
                    # I/O errors are fatal
                    _logger.exception("Error communicating with a client: %s",
                                      ex)
                    break

                except Exception as ex:
                    # Other exceptions are not important
                    import traceback
                    self.send("\nError during last command: %s\n" % ex)
                    self.send(traceback.format_exc())

                # Print the prompt
                self.send(ps1)

        finally:
            _logger.info("RemoteConsole client gone: [%s]:%d",
                         self.client_address[0], self.client_address[1])

            # Be polite
            self.send("\nSession closed. Good bye.\n")
            self.finish()

# ------------------------------------------------------------------------------

class ThreadingTCPServerFamily(socketserver.ThreadingTCPServer):
    """
    Threaded TCP Server handling different address families
    """
    def __init__(self, server_address, request_handler_class):
        """
        Sets up the TCP server. Doesn't bind nor activate it.
        """
        # Determine the address family
        addr_info = socket.getaddrinfo(server_address[0], server_address[1],
                                       0, 0, socket.SOL_TCP)

        # Change the address family before the socket is created
        # Get the family of the first possibility
        self.address_family = addr_info[0][0]

        # Call the super constructor
        socketserver.ThreadingTCPServer.__init__(self, server_address,
                                                 request_handler_class,
                                                 False)

        if self.address_family == socket.AF_INET6:
            # Explicitly ask to be accessible both by IPv4 and IPv6
            # Some versions of Python don't have V6ONLY.
            # On Linux, IPC6_V6ONLY = 26
            opt_ipv6_only = getattr(socket, "IPV6_V6ONLY", 26)

            try:
                self.socket.setsockopt(socket.IPPROTO_IPV6, opt_ipv6_only, 0)

            except socket.error as ex:
                # Log the error
                _logger.exception("Couldn't set IP double stack flag: %s", ex)


def _create_server(shell, server_address, port):
    """
    Creates the TCP console on the given address and port

    :param shell: The remote shell handler
    :param server_address: Server bound address
    :param port: Server port
    :return: server thread, TCP server object
    """
    # Set up the request handler creator
    active_flag = SharedBoolean(True)
    request_handler = lambda *args: RemoteConsole(shell, active_flag, *args)

    # Set up the server
    server = ThreadingTCPServerFamily((server_address, port), request_handler)

    # Set flags
    server.daemon_threads = True
    server.allow_reuse_address = True

    # Activate the server
    server.server_bind()
    server.server_activate()

    # Serve clients
    server_thread = threading.Thread(target=server.serve_forever,
                                     name="RemoteShell-{0}".format(port))
    server_thread.daemon = True
    server_thread.start()

    return (server_thread, server, active_flag)

# ------------------------------------------------------------------------------

@ComponentFactory(pelix.shell.FACTORY_REMOTE_SHELL)
@Provides(pelix.shell.REMOTE_SHELL_SPEC)
@Property("_address", "pelix.shell.address", "localhost")
@Property("_port", "pelix.shell.port", 9000)
@Requires("_shell", pelix.shell.SHELL_SERVICE_SPEC)
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

        # Internals
        self._thread = None
        self._server = None
        self._server_flag = None


    def get_access(self):
        """
        Implementation of the remote shell specification

        :return: A (host, port) tuple
        """
        return (self._address, self._port)


    def get_banner(self):
        """
        Retrieves the shell banner

        :return: The shell banner
        """
        line = '-' * 72
        shell_banner = self._shell.get_banner()

        return "{lines}\n{shell_banner}\niPOPO Remote Shell\n{lines}\n" \
            .format(lines=line, shell_banner=shell_banner)


    def get_ps1(self):
        """
        Returns the shell prompt

        :return: The shell prompt
        """
        return self._shell.get_ps1()


    def handle_line(self, rfile, wfile, line):
        """
        Handles the command line.

        **Does not catch exceptions !**

        :param rfile: Input file-like object
        :param wfile: Output file-like object
        :param line: The command line
        :return: The execution result (True on success, else False)
        """
        return self._shell.execute(line, rfile, wfile)


    @Validate
    def validate(self, context):
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

        except ValueError:
            # Invalid port string: use a random port
            self._port = 0

        # Start the TCP server
        self._thread, self._server, self._server_flag = \
                                _create_server(self, self._address, self._port)

        # Property update (if port was 0)
        self._port = self._server.socket.getsockname()[1]

        _logger.info("RemoteShell validated on port: %d", self._port)


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidation
        """
        # Stop the clients loops
        self._server_flag.set_value(False)

        # Shutdown the server
        self._server.shutdown()
        self._thread.join(2)

        # Close the server socket (ignore errors)
        self._server.server_close()

        # Clean up
        self._thread = None
        self._server = None
        self._server_flag = None

        _logger.info("RemoteShell gone from port: %d", self._port)

