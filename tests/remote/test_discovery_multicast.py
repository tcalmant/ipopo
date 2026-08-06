#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Unit tests for the multicast discovery helpers (no network setup required,
except local multicast sockets)

:author: Thomas Calmant
"""

import json
import socket
import unittest
from typing import Any

from pelix.remote.discovery.multicast import (
    MulticastDiscovery,
    close_multicast_socket,
    create_multicast_socket,
    make_mreq,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

IPV4_GROUP = "239.0.0.1"
IPV6_GROUP = "ff02::1"

# ------------------------------------------------------------------------------


class MreqTest(unittest.TestCase):
    """
    Tests the multicast request structure creation
    """

    def test_ipv4(self) -> None:
        mreq = make_mreq(socket.AF_INET, IPV4_GROUP)
        # struct ip_mreq: 4 bytes group + 4 bytes interface
        self.assertEqual(len(mreq), 8)
        self.assertEqual(mreq[:4], socket.inet_aton(IPV4_GROUP))

    def test_ipv6(self) -> None:
        mreq = make_mreq(socket.AF_INET6, IPV6_GROUP)
        # struct ipv6_mreq: 16 bytes group + interface index
        self.assertGreaterEqual(len(mreq), 20)
        self.assertEqual(mreq[:16], socket.inet_pton(socket.AF_INET6, IPV6_GROUP))

    def test_errors(self) -> None:
        self.assertRaises(ValueError, make_mreq, socket.AF_INET, "")
        self.assertRaises((ValueError, OSError), make_mreq, socket.AF_UNIX, "/some/path")


class MulticastSocketTest(unittest.TestCase):
    """
    Tests the creation and cleanup of multicast sockets
    """

    def test_ipv4(self) -> None:
        sock, address = create_multicast_socket(IPV4_GROUP, 24680)
        try:
            self.assertEqual(address, IPV4_GROUP)
            self.assertEqual(sock.family, socket.AF_INET)
        finally:
            close_multicast_socket(sock, address)

    def test_ipv6(self) -> None:
        try:
            sock, address = create_multicast_socket(IPV6_GROUP, 24680)
        except OSError as ex:
            self.skipTest(f"IPv6 multicast not available: {ex}")

        try:
            self.assertEqual(address, IPV6_GROUP)
            self.assertEqual(sock.family, socket.AF_INET6)
        finally:
            close_multicast_socket(sock, address)


# ------------------------------------------------------------------------------


class RecordingAccess:
    """
    Mimics the dispatcher servlet for the discovery component
    """

    def __init__(self) -> None:
        self.access: tuple[int, str] | None = (8080, "/pelix-dispatcher")
        self.discovered: list[tuple[str, int, str]] = []
        self.endpoints: dict[str, Any] = {}

    def get_access(self) -> tuple[int, str] | None:
        return self.access

    def send_discovered(self, host: str, port: int, path: str) -> None:
        self.discovered.append((host, port, path))

    def grab_endpoint(self, host: str, port: int, path: str, uid: str) -> Any:
        return self.endpoints.get(uid)


class RecordingRegistry:
    """
    Mimics the imported endpoints registry
    """

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.removed: list[str] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []

    def add(self, endpoint: Any) -> None:
        self.added.append(endpoint)

    def remove(self, uid: str) -> None:
        self.removed.append(uid)

    def update(self, uid: str, new_properties: dict[str, Any]) -> None:
        self.updated.append((uid, new_properties))


class FakeExportEndpoint:
    """
    Mimics an ExportEndpoint bean
    """

    def __init__(self, uid: str) -> None:
        self.uid = uid

    def make_import_properties(self) -> dict[str, Any]:
        return {"fake": True}


class PacketHandlingTest(unittest.TestCase):
    """
    Tests the handling and creation of discovery packets
    """

    SENDER = ("192.168.1.100", 12345)

    def setUp(self) -> None:
        self.discovery = MulticastDiscovery()
        self.discovery._fw_uid = "local-fw-uid"
        self.access = RecordingAccess()
        self.registry = RecordingRegistry()
        self.discovery._access = self.access  # type: ignore
        self.discovery._registry = self.registry  # type: ignore

    def _handle(self, data: dict[str, Any]) -> None:
        self.discovery._handle_packet(self.SENDER, json.dumps(data))

    def test_own_packet_ignored(self) -> None:
        """
        Packets sent by the local framework must be ignored
        """
        self._handle({"sender": "local-fw-uid", "event": "discovery"})
        self.assertListEqual(self.access.discovered, [])

    def test_discovery_event(self) -> None:
        """
        A discovery request must be answered with the local access
        """
        self._handle(
            {"sender": "other-fw", "event": "discovery", "access": {"port": 9000, "path": "/other"}}
        )
        self.assertListEqual(self.access.discovered, [(self.SENDER[0], 9000, "/other")])

    def test_add_event(self) -> None:
        """
        Endpoints from an "add" event are grabbed and registered
        """
        endpoint = object()
        self.access.endpoints["uid-1"] = endpoint

        # "uid-2" is unknown to the dispatcher: it must be skipped
        self._handle(
            {
                "sender": "other-fw",
                "event": "add",
                "access": {"port": 9000, "path": "/other"},
                "uids": ["uid-1", "uid-2"],
            }
        )
        self.assertListEqual(self.registry.added, [endpoint])

    def test_remove_event(self) -> None:
        self._handle({"sender": "other-fw", "event": "remove", "uid": "uid-1"})
        self.assertListEqual(self.registry.removed, ["uid-1"])

    def test_update_event(self) -> None:
        self._handle(
            {"sender": "other-fw", "event": "update", "uid": "uid-1", "new_properties": {"a": 1}}
        )
        self.assertListEqual(self.registry.updated, [("uid-1", {"a": 1})])

    def test_unknown_event(self) -> None:
        with self.assertLogs("pelix.remote.discovery.multicast", "WARNING") as log_ctx:
            self._handle({"sender": "other-fw", "event": "shrubbery"})
        self.assertTrue(any("Unknown event" in line for line in log_ctx.output))

    def test_make_packets(self) -> None:
        """
        Tests the creation of event packets
        """
        endpoint = FakeExportEndpoint("uid-1")

        packet = self.discovery._make_endpoint_dict("remove", endpoint)  # type: ignore
        self.assertEqual(packet["sender"], "local-fw-uid")
        self.assertEqual(packet["event"], "remove")
        self.assertEqual(packet["uid"], "uid-1")
        self.assertEqual(packet["access"], {"port": 8080, "path": "/pelix-dispatcher"})
        self.assertNotIn("new_properties", packet)

        packet = self.discovery._make_endpoint_dict("update", endpoint)  # type: ignore
        self.assertEqual(packet["new_properties"], {"fake": True})

        packet = self.discovery._make_endpoints_dict("add", [endpoint, FakeExportEndpoint("uid-2")])  # type: ignore
        self.assertListEqual(packet["uids"], ["uid-1", "uid-2"])

        # No dispatcher servlet access available: error
        self.access.access = None
        self.assertRaises(ValueError, self.discovery._make_endpoint_dict, "remove", endpoint)  # type: ignore


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
