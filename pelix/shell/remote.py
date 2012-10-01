#!/usr/bin/env python
#-- Content-Encoding: UTF-8 --
"""
iPOPO remote shell

Provides a remote interface for the Pelix shell that can be accessed using
telnet or netcat.

:author: Thomas Calmant
:copyright: Copyright 2012, isandlaTech
:license: GPLv3
:version: 0.1
:status: Alpha

..

    This file is part of iPOPO.

    iPOPO is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    iPOPO is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with iPOPO. If not, see <http://www.gnu.org/licenses/>.
"""

__version__ = (0, 1, 0)

# ------------------------------------------------------------------------------

from pelix.ipopo.decorators import ComponentFactory, Requires, Property, \
    Validate, Invalidate, Bind, Unbind, Instantiate
import pelix.framework as pelix

# ------------------------------------------------------------------------------

from select import select

import logging
import sys
import threading
import socket

if sys.version_info[0] >= 3:
    import socketserver
else:
    import SocketServer as socketserver

# ------------------------------------------------------------------------------

SHELL_SERVICE_SPEC = "pelix.shell"
SHELL_COMMAND_SPEC = "ipopo.shell.command"

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
        Send data to the client
        
        :param data: Data to be sent
        """
        if data is not None:
            data = data.encode("UTF-8")

        self.wfile.write(data)
        self.wfile.flush()


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

            try:
                # Be polite, if possible
                self.send("\nSession closed. Good bye.\n")
            except:
                # Can't send data anymore
                pass

# ------------------------------------------------------------------------------

class ThreadingTCPServerFamily(socketserver.ThreadingTCPServer):
    """
    Threaded TCP Server handling different address families
    """
    def __init__(self, server_address, request_handler_class,
                 bind_and_activate=True, address_family=socket.AF_INET):
        """
        Sets up the server
        """
        # Set the family
        self.address_family = address_family

        # Call the super constructor
        socketserver.ThreadingTCPServer.__init__(self, server_address,
                                                 request_handler_class,
                                                 bind_and_activate)


def _create_server(shell, server_address, port, address_family=None):
    """
    Creates the TCP console on the given address and port
    
    :param shell: The remote shell handler
    :param server_address: Server bound address
    :param port: Server port
    :param address_family: The IP address family
    :return: server thread, TCP server object
    """
    # Set up the request handler creator
    active_flag = SharedBoolean(True)
    request_handler = lambda *args: RemoteConsole(shell, active_flag, *args)

    # Set up the server
    server = ThreadingTCPServerFamily((server_address, port), request_handler,
                                      False, address_family)

    # Set flags
    server.daemon_threads = True
    server.allow_reuse_address = True

    # Activate the server
    server.server_bind()
    server.server_activate()

    # Serve clients
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    return (server_thread, server, active_flag)

# ------------------------------------------------------------------------------

@ComponentFactory("ipopo-remote-shell-factory")
@Property("_port", "shell.port", 9000)
@Requires("_shell", SHELL_SERVICE_SPEC)
@Requires("_handlers", SHELL_COMMAND_SPEC, aggregate=True, optional=True)
@Instantiate("ipopo-remote-shell")
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
        self._handlers = None
        self._port = 0

        # Internals
        self._thread = None
        self._server = None
        self._server_flag = None
        self._remote_handlers = {}


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


    def __register_handler(self, handler):
        """
        Registers the given command handler to the shell
        """
        # Shell command bound, and shell active
        namespace = handler.get_namespace()
        if handler not in self._remote_handlers:
            # Local service
            for command, method in handler.get_methods():
                self._shell.register_command(namespace, command, method)

        else:
            # Imported service
            host = self._remote_handlers[handler]
            _logger.info("Bound to a remote command handler from %s", host)

            namespace = ".".join((host, namespace))
            for command, method_name in handler.get_methods_names():
                def proxy(*args, **kwargs):
                    """
                    Remote command proxy
                    """
                    return getattr(handler, method_name)(*args, **kwargs)

                self._shell.register_command(namespace, command, proxy)


    @Bind
    def bind(self, svc, svc_ref):
        """
        Called by iPOPO when a service is bound
        
        :param svc: The bound service
        :param svc_ref: The reference of the bound service
        """
        specs = svc_ref.get_property(pelix.OBJECTCLASS)
        if SHELL_COMMAND_SPEC in specs:
            # Command handler bound
            if svc_ref.get_property("service.imported"):
                # Imported command
                self._remote_handlers[svc] = \
                                svc_ref.get_property("service.imported.from")

            if self._shell is not None:
                # The shell is active, register the command handler immediately
                self.__register_handler(svc)

        elif self._handlers and SHELL_SERVICE_SPEC in specs:
            # Bound to the shell, register bound commands if any
            for handler in self._handlers:
                self.__register_handler(handler)


    @Unbind
    def unbind(self, svc, svc_ref):
        """
        Called by iPOPO when a service is bound
        
        :param svc: The bound service
        :param svc_ref: The reference of the bound service
        """
        specs = svc_ref.get_property(pelix.OBJECTCLASS)
        if SHELL_COMMAND_SPEC in specs:
            # Shell command unbound
            namespace = svc.get_namespace()
            self._shell.unregister(namespace)

            # Clean up the references
            if svc in self._remote_handlers:
                del self._remote_handlers[svc]


    @Validate
    def validate(self, context):
        """
        Component validation
        """
        # Start the TCP server
        port = int(self._port)
        self._thread, self._server, \
            self._server_flag = _create_server(self, "::", port,
                                               socket.AF_INET6)

        _logger.info("RemoteShell validated on port: %d", port)


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidation
        """
        # Stop the clients loops
        self._server_flag.set_value(False)

        # Clear data
        self._remote_handlers.clear()

        # Shutdown the server
        self._server.shutdown()
        self._thread.join(2)

        # Close the server socket (ignore errors)
        self._server.server_close()

