#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Multicast discovery and event notification

A discovery packet contains the access to the dispatcher servlet, which
can be used to get the end points descriptions.
An event notification packet contain an end point UID, a kind of event and the
previous service properties (if the event is an update).

**WARNING:** Do not forget to open the UDP ports used for the multicast, even
when using remote services on the local host only.

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

# Standard library
import logging
import json
import os
import select
import socket
import struct
import threading

# iPOPO decorators
from pelix.ipopo.decorators import (
    ComponentFactory,
    Requires,
    Provides,
    Invalidate,
    Validate,
    Property,
)

# Pelix utilities
import pelix.constants
from pelix.ipv6utils import ipproto_ipv6
from pelix.utilities import to_bytes, to_str

# Remote services
import pelix.remote

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

if os.name == "nt":
    # Windows Specific code
    def pton(family, address):
        """
        Calls inet_pton

        :param family: Socket family
        :param address: A string address
        :return: The binary form of the given address
        """
        if family == socket.AF_INET:
            return socket.inet_aton(address)

        elif family == socket.AF_INET6:
            # Do it using WinSocks
            import ctypes

            winsock = ctypes.windll.ws2_32

            # Prepare structure
            class sockaddr_in6(ctypes.Structure):
                # pylint: disable=C0103, R0903
                """
                Definition of the C structure 'sockaddr_in6'
                """

                _fields_ = [
                    ("sin6_family", ctypes.c_short),
                    ("sin6_port", ctypes.c_ushort),
                    ("sin6_flowinfo", ctypes.c_ulong),
                    ("sin6_addr", ctypes.c_ubyte * 16),
                    ("sin6_scope_id", ctypes.c_ulong),
                ]

            # Prepare pointers
            addr_ptr = ctypes.c_char_p(to_bytes(address))

            out_address = sockaddr_in6()
            size = len(sockaddr_in6)
            size_ptr = ctypes.pointer(size)

            # Second call
            winsock.WSAStringToAddressA(
                addr_ptr, family, 0, out_address, size_ptr
            )

            # Convert the array...
            bin_addr = 0
            for part in out_address.sin6_addr:
                bin_addr = bin_addr * 16 + part

            return bin_addr

        else:
            raise ValueError("Unhandled socket family: {0}".format(family))


else:
    # Other systems
    def pton(family, address):
        """
        Calls inet_pton

        :param family: Socket family
        :param address: A string address
        :return: The binary form of the given address
        """
        return socket.inet_pton(family, address)


# ------------------------------------------------------------------------------


def make_mreq(family, address):
    """
    Makes a mreq structure object for the given address and socket family.

    :param family: A socket family (AF_INET or AF_INET6)
    :param address: A multicast address (group)
    :raise ValueError: Invalid family or address
    """
    if not address:
        raise ValueError("Empty address")

    # Convert the address to a binary form
    group_bin = pton(family, address)

    if family == socket.AF_INET:
        # IPv4
        # struct ip_mreq
        # {
        #     struct in_addr imr_multiaddr; /* IP multicast address of group */
        #     struct in_addr imr_interface; /* local IP address of interface */
        # };
        # "=I" : Native order, standard size unsigned int
        return group_bin + struct.pack("=I", socket.INADDR_ANY)

    elif family == socket.AF_INET6:
        # IPv6
        # struct ipv6_mreq {
        #    struct in6_addr ipv6mr_multiaddr;
        #    unsigned int    ipv6mr_interface;
        # };
        # "@I" : Native order, native size unsigned int
        return group_bin + struct.pack("@I", 0)

    raise ValueError("Unknown family {0}".format(family))


# ------------------------------------------------------------------------------


def create_multicast_socket(address, port):
    """
    Creates a multicast socket according to the given address and port.
    Handles both IPv4 and IPv6 addresses.

    :param address: Multicast address/group
    :param port: Socket port
    :return: A tuple (socket, listening address)
    :raise ValueError: Invalid address or port
    """
    # Get the information about a datagram (UDP) socket, of any family
    try:
        addrs_info = socket.getaddrinfo(
            address, port, socket.AF_UNSPEC, socket.SOCK_DGRAM
        )
    except socket.gaierror:
        raise ValueError(
            "Error retrieving address informations ({0}, {1})".format(
                address, port
            )
        )

    if len(addrs_info) > 1:
        _logger.debug(
            "More than one address information found. Using the first one."
        )

    # Get the first entry : (family, socktype, proto, canonname, sockaddr)
    addr_info = addrs_info[0]

    # Only accept IPv4/v6 addresses
    if addr_info[0] not in (socket.AF_INET, socket.AF_INET6):
        # Unhandled address family
        raise ValueError("Unhandled socket family : %d" % (addr_info[0]))

    # Prepare the socket
    sock = socket.socket(addr_info[0], socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    # Reuse address
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        # Special for MacOS
        # pylint: disable=E1101
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    # Bind the socket
    if sock.family == socket.AF_INET:
        # IPv4 binding
        sock.bind(("0.0.0.0", port))

    else:
        # IPv6 Binding
        sock.bind(("::", port))

    # Prepare the mreq structure to join the group
    # addrinfo[4] = (addr,port)
    mreq = make_mreq(sock.family, addr_info[4][0])

    # Join the group
    if sock.family == socket.AF_INET:
        # IPv4
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # Allow multicast packets to get back on this host
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)

    elif sock.family == socket.AF_INET6:
        # IPv6
        sock.setsockopt(ipproto_ipv6(), socket.IPV6_JOIN_GROUP, mreq)

        # Allow multicast packets to get back on this host
        sock.setsockopt(ipproto_ipv6(), socket.IPV6_MULTICAST_LOOP, 1)

    return sock, addr_info[4][0]


def close_multicast_socket(sock, address):
    """
    Cleans up the given multicast socket.
    Unregisters it of the multicast group.

    Parameters should be the result of create_multicast_socket

    :param sock: A multicast socket
    :param address: The multicast address used by the socket
    """
    if sock is None:
        return

    if address:
        # Prepare the mreq structure to join the group
        mreq = make_mreq(sock.family, address)

        # Quit group
        if sock.family == socket.AF_INET:
            # IPv4
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)

        elif sock.family == socket.AF_INET6:
            # IPv6
            sock.setsockopt(ipproto_ipv6(), socket.IPV6_LEAVE_GROUP, mreq)

    # Close the socket
    sock.close()


# ------------------------------------------------------------------------------


@ComponentFactory(pelix.remote.FACTORY_DISCOVERY_MULTICAST)
@Provides(pelix.remote.SERVICE_EXPORT_ENDPOINT_LISTENER)
@Requires("_access", pelix.remote.SERVICE_DISPATCHER_SERVLET)
@Requires("_registry", pelix.remote.SERVICE_REGISTRY)
@Property("_group", "multicast.group", "239.0.0.1")
@Property("_port", "multicast.port", 42000)
class MulticastDiscovery(object):
    """
    Remote services discovery and notification using multicast packets
    """

    def __init__(self):
        """
        Sets up the component
        """
        # End points registry
        self._registry = None

        # Dispatcher access
        self._access = None

        # Framework UID
        self._fw_uid = None

        # Socket
        self._group = "239.0.0.1"
        self._port = 42000
        self._socket = None
        self._target = None

        # Reception loop
        self._stop_event = threading.Event()
        self._thread = None

    def __make_basic_dict(self, event):
        """
        Prepares basic common information contained into an event packet
        (access, framework UID, event type)

        :param event: The kind of event
        :return: A dictionary
        """
        # Get the dispatcher servlet access
        access = self._access.get_access()

        # Make the event packet content
        return {
            "sender": self._fw_uid,
            "event": event,  # Kind of event
            "access": {
                "port": access[0],  # Access to the dispatcher
                "path": access[1],
            },
        }  # servlet

    def _make_endpoint_dict(self, event, endpoint):
        """
        Prepares an event packet containing a single endpoint

        :param event: The kind of event (update, remove)
        :param endpoint: An ExportEndpoint bean
        :return: A dictionary
        """
        # Basic packet information
        packet = self.__make_basic_dict(event)

        # Add endpoint information
        packet["uid"] = endpoint.uid
        if event == "update":
            # Give the new end point properties
            packet["new_properties"] = endpoint.make_import_properties()

        return packet

    def _make_endpoints_dict(self, event, endpoints):
        """
        Prepares an event packet containing multiple endpoints

        :param event: The kind of event (add)
        :param endpoints: A list of ExportEndpoint beans
        :return: A dictionary
        """
        # Basic packet information
        packet = self.__make_basic_dict(event)

        # Add endpoints information
        packet["uids"] = [endpoint.uid for endpoint in endpoints]

        return packet

    def __send_packet(self, data, target=None):
        """
        Sends a UDP datagram to the given target, if given, or to the multicast
        group.

        :param data: The content of the datagram
        :param target: The packet target (can be None)
        """
        if target is None:
            # Use the multicast target by default
            target = self._target

        # Converts data to bytes
        data = to_bytes(data)

        # Send the data
        self._socket.sendto(data, 0, target)

    def _send_discovery(self):
        """
        Sends a discovery packet, requesting others to indicate their services
        """
        # Send a JSON request
        data = json.dumps(self.__make_basic_dict("discovery"))
        self.__send_packet(data)

    def endpoints_added(self, endpoints):
        """
        Multiple endpoints have been created
        """
        # Send a JSON event
        data = json.dumps(self._make_endpoints_dict("add", endpoints))
        self.__send_packet(data)

    def endpoint_updated(self, endpoint, old_properties):
        # pylint: disable=W0613
        """
        An end point is updated
        """
        # Send a JSON event
        data = json.dumps(self._make_endpoint_dict("update", endpoint))
        self.__send_packet(data)

    def endpoint_removed(self, endpoint):
        """
        An end point is removed
        """
        # Send a JSON event
        data = json.dumps(self._make_endpoint_dict("remove", endpoint))
        self.__send_packet(data)

    def _handle_packet(self, sender, raw_data):
        """
        Calls the method associated to the kind of event indicated in the given
        packet.

        :param sender: The (address, port) tuple of the client
        :param raw_data: Raw packet content
        """
        # Decode content
        data = json.loads(raw_data)

        # Avoid handling our own packets
        sender_uid = data["sender"]
        if sender_uid == self._fw_uid:
            return

        # Dispatch the event
        event = data["event"]
        if event == "discovery":
            # Discovery request
            access = data["access"]
            self._access.send_discovered(
                sender[0], access["port"], access["path"]
            )

        elif event in ("add", "update", "remove"):
            # End point event
            self._handle_event_packet(sender, data)

        else:
            _logger.warning("Unknown event '%s' from %s", event, sender)

    def _handle_event_packet(self, sender, data):
        """
        Handles an end point event packet

        :param sender: The (address, port) tuple of the client
        :param data: Decoded packet content
        """
        # Get the event
        event = data["event"]

        if event == "add":
            # Store it
            port = data["access"]["port"]
            path = data["access"]["path"]

            for uid in data["uids"]:
                # Get the description of the endpoint
                endpoint = self._access.grab_endpoint(
                    sender[0], port, path, uid
                )
                if endpoint is not None:
                    # Register the endpoint
                    self._registry.add(endpoint)

        elif event == "remove":
            # Remove it
            self._registry.remove(data["uid"])

        elif event == "update":
            # Update it
            endpoint_uid = data["uid"]
            new_properties = data["new_properties"]
            self._registry.update(endpoint_uid, new_properties)

    def _read_loop(self):
        """
        Reads packets from the socket
        """
        while not self._stop_event.is_set():
            # Watch for content
            ready = select.select([self._socket], [], [], 1)
            if ready[0]:
                # Socket is ready
                data, sender = self._socket.recvfrom(1024)
                try:
                    data = to_str(data)
                    self._handle_packet(sender, data)

                except Exception as ex:
                    _logger.exception("Error handling the packet: %s", ex)

    @Invalidate
    def invalidate(self, _):
        """
        Component invalidated
        """
        # Stop the loop
        self._stop_event.set()

        # Join the thread
        self._thread.join()

        # Close the socket
        close_multicast_socket(self._socket, self._target[0])

        # Clean up
        self._thread = None
        self._socket = None
        self._target = None
        self._fw_uid = None

        _logger.debug("Multicast discovery invalidated")

    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Ensure we have a valid port
        self._port = int(self._port)

        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Create the socket
        self._socket, address = create_multicast_socket(self._group, self._port)

        # Store group access information
        self._target = (address, self._port)

        # Start the listening thread
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._read_loop)
        self._thread.start()

        # Send a discovery request
        self._send_discovery()

        _logger.debug(
            "Multicast discovery validated: group=%s port=%d",
            self._group,
            self._port,
        )
