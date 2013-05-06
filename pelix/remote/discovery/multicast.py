#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Multicast discovery

**WARNING:** Do not forget to open the UDP ports used for the multicast, even
when using remote services on the local host only.

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
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

# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(map(str, __version_info__))

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix utilities
from pelix.utilities import to_bytes, to_str

# Remote Services constants
import pelix.remote

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Provides, \
    Invalidate, Validate, Property

# Standard library
import logging
import json
import os
import select
import socket
import struct
import threading

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
                _fields_ = [("sin6_family", ctypes.c_short),
                            ("sin6_port", ctypes.c_ushort),
                            ("sin6_flowinfo", ctypes.c_ulong),
                            ("sin6_addr", ctypes.c_ubyte * 16),
                            ("sin6_scope_id", ctypes.c_ulong)]

            # Prepare pointers
            addr_ptr = ctypes.c_char_p(to_bytes(address))

            out_address = sockaddr_in6()
            size = len(sockaddr_in6)
            size_ptr = ctypes.pointer(size)

            # Second call
            winsock.WSAStringToAddressA(addr_ptr, family, 0,
                                        out_address, size_ptr)

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
        addrs_info = socket.getaddrinfo(address, port, socket.AF_UNSPEC,
                                       socket.SOCK_DGRAM)
    except socket.gaierror:
        raise ValueError("Error retrieving address informations ({0}, {1})" \
                         .format(address, port))

    if len(addrs_info) > 1:
        _logger.debug("More than one address information found. "
                      "Using the first one.")

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
    if hasattr(socket, 'SO_REUSEPORT'):
        # Special for MacOS
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    # Bind the socket
    if sock.family == socket.AF_INET:
        # IPv4 binding
        sock.bind(('0.0.0.0', port))

    else:
        # IPv6 Binding
        sock.bind(('::', port))

    # Prepare the mreq structure to join the group
    # addrinfo[4] = (addr,port)
    mreq = make_mreq(sock.family, addr_info[4][0])

    # Join the group
    if sock.family == socket.AF_INET:
        # IPv4
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # Allow multicast packets to get back on this host
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)

    else:
        # IPv6
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP, mreq)

        # Allow multicast packets to get back on this host
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_LOOP, 1)

    return (sock, addr_info[4][0])


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
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_LEAVE_GROUP, mreq)

    # Close the socket
    sock.close()

# ------------------------------------------------------------------------------

@ComponentFactory("pelix-remote-discovery-multicast-factory")
@Provides(pelix.remote.SERVICE_ENDPOINT_LISTENER)
@Requires("_dispatcher", pelix.remote.SERVICE_DISPATCHER)
@Requires("_registry", pelix.remote.SERVICE_REGISTRY)
@Property("_group", "multicast.group", "239.0.0.1")
@Property("_port", "multicast.port", 42000)
@Property("_listener_flag", pelix.remote.PROP_LISTEN_EXPORTED, True)
class MulticastDiscovery(object):
    """
    Remote services discovery and notification using multicast packets
    """
    def __init__(self):
        """
        Sets up the component
        """
        # End point listener flag
        self._listener_flag = True

        # End points registry
        self._dispatcher = None
        self._registry = None

        # Socket
        self._group = "239.0.0.1"
        self._port = 42000
        self._socket = None
        self._target = None

        # Reception loop
        self._stop_event = threading.Event()
        self._thread = None


    def _make_endpoint_dict(self, event, endpoint):
        """
        Converts the end point into a dictionary
        """
        specs = endpoint.reference.get_property(pelix.framework.OBJECTCLASS)

        return {"sender": self._dispatcher.uid,
                "event": event,
                "uid": endpoint.uid,
                "kind": endpoint.kind,
                "name": endpoint.name,
                "url": endpoint.url,
                "properties": endpoint.reference.get_properties(),
                "specifications": specs}


    def _send_discovery(self):
        """
        Sends a discovery packet, requesting others to indicate their services
        """
        # Send a JSON request
        data = json.dumps({"event": "discovery",
                           "sender": self._dispatcher.uid})
        data = to_bytes(data)
        self._socket.sendto(data, 0, self._target)


    def endpoint_added(self, endpoint):
        """
        A new service is exported
        """
        # Send a JSON event
        data = json.dumps(self._make_endpoint_dict("add", endpoint))
        data = to_bytes(data)
        self._socket.sendto(data, 0, self._target)


    def endpoint_updated(self, endpoint, old_properties):
        """
        An end point is updated
        """
        # Prepare the end point dictionary
        endpoint_dict = self._make_endpoint_dict("update", endpoint)
        endpoint_dict['old_properties'] = old_properties

        # Send a JSON event
        data = json.dumps(endpoint_dict)
        data = to_bytes(data)
        self._socket.sendto(data, 0, self._target)


    def endpoint_removed(self, endpoint):
        """
        An end point is removed
        """
        # Send a JSON event
        data = json.dumps(self._make_endpoint_dict("remove", endpoint))
        data = to_bytes(data)
        self._socket.sendto(data, 0, self._target)


    def _handle_packet(self, sender, raw_data):
        """
        Calls the method associated to the kind of event indicated in the given
        packet.
        
        :param sender: The (address, port) tuple of the client
        :param raw_data: Raw packet content
        """
        # Decode content
        data = json.loads(raw_data)

        # Avoid handling our own requests
        sender_uid = data['sender']
        if sender_uid == self._dispatcher.uid:
            return

        # Dispatch the event
        event = data['event']
        if event == "discovery":
            # Discovery request
            self._handle_discovery(sender)

        elif event == "discovered":
            # Answer to a discovery request
            for endpoint in data['endpoints']:
                self._handle_endpoint_packet(sender, 'add', endpoint)

        elif event in ('add', 'update', 'remove'):
            # End point event
            self._handle_endpoint_packet(sender, event, data)

        else:
            _logger.warning("Unhandled event '%s' from %s", event, sender)


    def _handle_discovery(self, sender):
        """
        Responds to a discovery request
        
        :param sender: The (address, port) tuple of the client
        """
        # Compute the list of end points
        endpoints = [self._make_endpoint_dict('add', endpoint)
                     for endpoint in self._dispatcher.get_endpoints()]
        if endpoints:
            # Only send a packet if necessary
            data = json.dumps({"event": "discovered",
                               "sender": self._dispatcher.uid,
                               "endpoints": endpoints})
            data = to_bytes(data)

            # Send the packet to the sender only
            self._socket.sendto(data, 0, sender)


    def _handle_endpoint_packet(self, sender, event, data):
        """
        Handles an end point event packet
        
        :param sender: The (address, port) tuple of the client
        :param data: Decoded packet content
        """
        # Update properties
        properties = data['properties']
        properties[pelix.remote.PROP_IMPORTED] = True
        if pelix.remote.PROP_EXPORTED_CONFIGS in properties:
            properties[pelix.remote.PROP_IMPORTED_CONFIGS] = \
                                properties[pelix.remote.PROP_EXPORTED_CONFIGS]

        # Add the dispatcher UID to the properties
        properties[pelix.remote.PROP_DISPATCHER_UID] = data['sender']

        # Clear export properties
        for name in (pelix.remote.PROP_EXPORTED_CONFIGS,
                     pelix.remote.PROP_EXPORTED_INTERFACES):
            if name in properties:
                del properties[name]

        # Create the endpoint
        endpoint = pelix.remote.ImportEndpoint(data['uid'],
                                               data['kind'],
                                               data['name'],
                                               data['url'],
                                               data['specifications'],
                                               properties)

        if event == 'add':
            # Store it
            self._registry.add(endpoint)

        elif event == 'remove':
            # Remove it
            self._registry.remove(endpoint)

        elif event == 'update':
            # Update it
            self._registry.update(endpoint, data['old_properties'])


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
    def invalidate(self, context):
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

        _logger.debug("Multicast discovery invalidated")


    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Ensure we have a valid port
        self._port = int(self._port)

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

        _logger.debug("Multicast discovery validated: group=%s port=%d",
                      self._group, self._port)
