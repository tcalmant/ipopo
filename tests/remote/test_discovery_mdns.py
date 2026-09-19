#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Unit tests for the mDNS/Zeroconf discovery property (de)serialization and
records handling (no network setup required)

:author: Thomas Calmant
"""

import importlib.util
import json
import os
import shutil
import socket
import tempfile
import types
import unittest
from typing import Any, cast

if importlib.util.find_spec("zeroconf") is None:
    raise unittest.SkipTest("zeroconf is missing: can't test mDNS discovery")

import pelix.constants
import pelix.remote
from pelix.remote.beans import ExportEndpoint, ImportEndpoint
from pelix.remote.discovery.mdns import DEFAULT_ZEROCONF_TYPE, PELIX_TYPE_PREFIX, ZeroconfDiscovery

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

LOGGER_NAME = "pelix.remote.discovery.mdns"

# ------------------------------------------------------------------------------


def deserialize(value: bytes | None, key: bytes = b"test.property") -> Any:
    """
    Deserializes a single property value

    :param value: The raw value of the property
    :param key: The name of the property
    :return: The deserialized value
    """
    return ZeroconfDiscovery._deserialize_properties({key: value})[key.decode("utf-8")]


class PseudoSerializationSecurityTest(unittest.TestCase):
    """
    Ensures that values read from mDNS records are never executed.

    Records are sent over unauthenticated multicast: any host on the local link
    can craft them. A previous implementation passed them to eval().
    """

    def setUp(self) -> None:
        # Marker file: it must never be created by a payload
        self.temp_dir = tempfile.mkdtemp(prefix="ipopo-mdns-test-")
        self.marker = os.path.join(self.temp_dir, "payload-was-executed")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def assertNotExecuted(self, payload: str) -> Any:
        """
        Deserializes a payload and ensures it has not been executed

        :param payload: The property value to deserialize
        :return: The deserialized value
        """
        value = deserialize(payload.encode("utf-8"))
        self.assertFalse(
            os.path.exists(self.marker),
            f"Payload has been executed: {payload}",
        )
        return value

    def test_unknown_type_is_not_executed(self) -> None:
        """
        A payload with an unknown type name must be kept as a string.

        This is the shape that used to reach eval(): the old parser dropped the
        type name, so anything after the third colon was executed.
        """
        code = f"__import__('pathlib').Path({self.marker!r}).touch()"
        value = self.assertNotExecuted(f"{PELIX_TYPE_PREFIX}x:y:{code}")
        self.assertIsInstance(value, str)
        self.assertEqual(value, f"y:{code}")

    def test_known_type_is_not_executed(self) -> None:
        """
        A payload using an allowed type name must not be executed either:
        the converter is applied to the raw text, it never interprets it
        """
        code = f"__import__('pathlib').Path({self.marker!r}).touch()"
        for type_name in ("int", "float", "bool", "str"):
            with self.subTest(type_name=type_name):
                value = self.assertNotExecuted(f"{PELIX_TYPE_PREFIX}{type_name}:{code}")
                self.assertIsInstance(value, (str, bool))

    def test_dunder_payloads_are_not_executed(self) -> None:
        """
        Various payloads that would have been valid Python expressions
        """
        payloads = [
            f"{PELIX_TYPE_PREFIX}a:b:__import__('os').system('touch {self.marker}')",
            f"{PELIX_TYPE_PREFIX}a:b:open({self.marker!r}, 'w').close()",
            f"{PELIX_TYPE_PREFIX}a:b:[].__class__.__mro__[1].__subclasses__()",
            f"{PELIX_TYPE_PREFIX}int:0:__import__('pathlib').Path({self.marker!r}).touch()",
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertNotExecuted(payload)

    def test_no_execution_through_json(self) -> None:
        """
        The JSON branch must not interpret Python expressions either
        """
        self.assertNotExecuted(f"__import__('pathlib').Path({self.marker!r}).touch()")


class PseudoSerializationParsingTest(unittest.TestCase):
    """
    Tests the parsing of the "pelix-type:" pseudo-serialization format
    """

    def test_allowed_types(self) -> None:
        """
        Values of an allowed type are converted
        """
        for raw, expected in (
            ("int:42", 42),
            ("int:-7", -7),
            ("float:3.5", 3.5),
            ("float:-0.25", -0.25),
            ("str:hello", "hello"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(deserialize(f"{PELIX_TYPE_PREFIX}{raw}".encode()), expected)

    def test_boolean_values(self) -> None:
        """
        Booleans are parsed with str2bool
        """
        for raw, expected in (
            ("true", True),
            ("True", True),
            ("yes", True),
            ("1", True),
            ("on", True),
            ("false", False),
            ("no", False),
            ("0", False),
            ("whatever", False),
        ):
            with self.subTest(raw=raw):
                value = deserialize(f"{PELIX_TYPE_PREFIX}bool:{raw}".encode())
                self.assertIs(value, expected)

    def test_value_containing_colons(self) -> None:
        """
        Only the first two colons are separators: the value keeps its own
        """
        self.assertEqual(
            deserialize(f"{PELIX_TYPE_PREFIX}str:hello:world".encode()),
            "hello:world",
        )
        self.assertEqual(
            deserialize(f"{PELIX_TYPE_PREFIX}str:http://localhost:9000/path".encode()),
            "http://localhost:9000/path",
        )

    def test_unsupported_type_keeps_string(self) -> None:
        """
        An unsupported type is logged and its value kept as a string
        """
        for raw in ("set:{1, 2}", "dict:{'a': 1}", "complex:1j", "SomeClass:<object>"):
            with self.subTest(raw=raw):
                with self.assertLogs(LOGGER_NAME, "WARNING"):
                    value = deserialize(f"{PELIX_TYPE_PREFIX}{raw}".encode())

                self.assertIsInstance(value, str)
                self.assertEqual(value, raw.split(":", 1)[1])

    def test_invalid_value_keeps_string(self) -> None:
        """
        A value that doesn't match its announced type is kept as a string
        """
        for raw in ("int:not-a-number", "float:not-a-number", "int:", "float:1.2.3"):
            with self.subTest(raw=raw):
                with self.assertLogs(LOGGER_NAME, "WARNING"):
                    value = deserialize(f"{PELIX_TYPE_PREFIX}{raw}".encode())

                self.assertIsInstance(value, str)
                self.assertEqual(value, raw.split(":", 1)[1])

    def test_malformed_values(self) -> None:
        """
        Malformed pseudo-serialized values don't raise and are kept as strings
        """
        for raw in (PELIX_TYPE_PREFIX, "pelix-type", f"{PELIX_TYPE_PREFIX}int"):
            with self.subTest(raw=raw):
                value = deserialize(raw.encode("utf-8"))
                self.assertIsInstance(value, str)


class DeserializationTest(unittest.TestCase):
    """
    Tests the standard (JSON) deserialization path
    """

    def test_json_values(self) -> None:
        """
        JSON values are parsed as usual
        """
        for raw, expected in (
            (b"42", 42),
            (b"-1", -1),
            (b"3.5", 3.5),
            (b"true", True),
            (b"false", False),
            (b"null", None),
            (b"[1, 2, 3]", [1, 2, 3]),
            (b'["a", "b"]', ["a", "b"]),
            (b'{"a": 1}', {"a": 1}),
            (b'"a string"', "a string"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(deserialize(raw), expected)

    def test_plain_strings(self) -> None:
        """
        Values that are neither JSON nor pseudo-serialized are kept as strings
        """
        for raw in (b"hello", b"a.b.c.Service", b"", b"{not json}"):
            with self.subTest(raw=raw):
                self.assertEqual(deserialize(raw), raw.decode("utf-8"))

    def test_none_value(self) -> None:
        """
        A TXT record entry without a value gives None
        """
        self.assertIsNone(deserialize(None))

    def test_keys_and_values_are_decoded(self) -> None:
        """
        Zeroconf gives bytes for both keys and values
        """
        props = ZeroconfDiscovery._deserialize_properties({b"some.key": b"some value"})
        self.assertEqual(props, {"some.key": "some value"})
        for key in props:
            self.assertIsInstance(key, str)

    def test_string_values_are_accepted(self) -> None:
        """
        Values are also accepted as strings, not only as bytes
        """
        props = ZeroconfDiscovery._deserialize_properties({b"some.key": "42"})  # type: ignore
        self.assertEqual(props, {"some.key": 42})


class SerializationTest(unittest.TestCase):
    """
    Tests the serialization of properties
    """

    def test_json_serializable_values(self) -> None:
        """
        Standard values go through JSON
        """
        props: dict[str, Any] = {
            "an.int": 42,
            "a.float": 3.5,
            "a.bool": True,
            "a.none": None,
            "a.list": ["a", "b"],
        }
        serialized = ZeroconfDiscovery._serialize_properties(props)
        for value in serialized.values():
            self.assertIsInstance(value, str)

        self.assertEqual(ZeroconfDiscovery._deserialize_properties(serialized), props)  # type: ignore

    def test_strings_are_kept(self) -> None:
        """
        String values are sent as-is
        """
        serialized = ZeroconfDiscovery._serialize_properties({"a.string": "hello"})
        self.assertEqual(serialized["a.string"], "hello")

    def test_unserializable_value_does_not_raise(self) -> None:
        """
        A value that JSON can't handle must not abort the export.

        json.dumps() raises TypeError for those, which used to propagate out of
        _serialize_properties and break the whole endpoint registration.
        """

        class Custom:
            def __str__(self) -> str:
                return "custom-value"

        for value in ({1, 2}, Custom(), object()):
            with self.subTest(value=type(value).__name__):
                with self.assertLogs(LOGGER_NAME, "WARNING"):
                    serialized = ZeroconfDiscovery._serialize_properties({"a.key": value})

                self.assertIsInstance(serialized["a.key"], str)
                self.assertTrue(serialized["a.key"].startswith(PELIX_TYPE_PREFIX))

    def test_circular_reference_does_not_raise(self) -> None:
        """
        Circular references make json.dumps() raise a ValueError
        """
        circular: list = []
        circular.append(circular)

        with self.assertLogs(LOGGER_NAME, "WARNING"):
            serialized = ZeroconfDiscovery._serialize_properties({"a.key": circular})

        self.assertIsInstance(serialized["a.key"], str)

    def test_unserializable_value_is_read_back_as_string(self) -> None:
        """
        An unsupported type is sent as a string and read back as a string,
        instead of being interpreted by the reader
        """
        with self.assertLogs(LOGGER_NAME, "WARNING"):
            serialized = ZeroconfDiscovery._serialize_properties({"a.key": {1, 2}})

        with self.assertLogs(LOGGER_NAME, "WARNING"):
            value = deserialize(serialized["a.key"].encode("utf-8"), b"a.key")

        self.assertIsInstance(value, str)

    def test_ecf_compatibility_single_values(self) -> None:
        """
        objectClass and imported configs are sent as single strings (for ECF)
        """
        serialized = ZeroconfDiscovery._serialize_properties(
            {
                pelix.constants.OBJECTCLASS: ["spec.one", "spec.two"],
                pelix.remote.PROP_IMPORTED_CONFIGS: ["jsonrpc"],
            }
        )
        self.assertEqual(serialized[pelix.constants.OBJECTCLASS], "spec.one")
        self.assertEqual(serialized[pelix.remote.PROP_IMPORTED_CONFIGS], "jsonrpc")

    def test_endpoint_properties_round_trip(self) -> None:
        """
        A realistic set of endpoint properties survives the round trip
        """
        props: dict[str, Any] = {
            pelix.remote.PROP_ENDPOINT_ID: "endpoint-uid",
            pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID: "framework-uid",
            pelix.remote.PROP_ENDPOINT_SERVICE_ID: 21,
            pelix.remote.PROP_IMPORTED: True,
            "service.ranking": 0,
            "pelix.access.port": 9000,
            "pelix.access.path": "/pelix-dispatcher",
            "pelix.version": "3.2.2",
        }
        serialized = ZeroconfDiscovery._serialize_properties(props)
        self.assertEqual(ZeroconfDiscovery._deserialize_properties(serialized), props)  # type: ignore


# ------------------------------------------------------------------------------

LOCAL_FW = "local-framework"
REMOTE_FW = "remote-framework"
RS_NAME = f"remote-endpoint.{DEFAULT_ZEROCONF_TYPE}"
DISPATCHER_NAME = f"{REMOTE_FW}.{ZeroconfDiscovery.DNS_DISPATCHER_TYPE}"


class FakeZeroconf:
    """
    Zeroconf stand-in: returns the service information given by the test
    """

    def __init__(self) -> None:
        self.infos: dict[str, Any] = {}
        self.unregistered: list[Any] = []

    def get_service_info(self, svc_type: str, name: str) -> Any:
        return self.infos.get(name)

    def unregister_service(self, info: Any) -> None:
        self.unregistered.append(info)


class FakeRegistry:
    """
    Imported endpoints registry stand-in
    """

    def __init__(self) -> None:
        self.accept = True
        self.added: list[ImportEndpoint] = []
        self.updated: list[tuple[str, dict[str, Any]]] = []
        self.removed: list[str] = []
        self.lost: list[str] = []

    def add(self, endpoint: ImportEndpoint) -> bool:
        self.added.append(endpoint)
        return self.accept

    def update(self, uid: str, properties: dict[str, Any]) -> None:
        self.updated.append((uid, properties))

    def remove(self, uid: str) -> None:
        self.removed.append(uid)

    def lost_framework(self, uid: str) -> None:
        self.lost.append(uid)


class FakeAccess:
    """
    Dispatcher servlet stand-in
    """

    def __init__(self) -> None:
        self.discovered: list[tuple[str, int, str]] = []

    def get_access(self) -> tuple[int, str] | None:
        return None

    def send_discovered(self, host: str, port: int, path: str) -> None:
        self.discovered.append((host, port, path))


def make_info(properties: dict[str, Any], **kwargs: Any) -> Any:
    """
    Prepares a service information bean with JSON-encoded properties
    """
    kwargs.setdefault("port", 8080)
    kwargs.setdefault("addresses", [socket.inet_aton("192.168.1.2")])
    kwargs.setdefault("server", None)
    raw_props = {key.encode(): json.dumps(value).encode() for key, value in properties.items()}
    return types.SimpleNamespace(properties=raw_props, **kwargs)


def endpoint_props(framework: str = REMOTE_FW, **extra: Any) -> dict[str, Any]:
    """
    Prepares the properties of a remote service record
    """
    props: dict[str, Any] = {
        pelix.remote.PROP_ENDPOINT_ID: "endpoint-uid",
        pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID: framework,
        pelix.remote.PROP_IMPORTED_CONFIGS: ["jsonrpc", "xmlrpc"],
        pelix.constants.OBJECTCLASS: "sample.spec",
    }
    props.update(extra)
    return props


class ZeroconfRecordsTest(unittest.TestCase):
    """
    Tests the handling of the mDNS records notified by Zeroconf
    """

    def setUp(self) -> None:
        self.zeroconf = FakeZeroconf()
        self.registry = FakeRegistry()
        self.access = FakeAccess()

        self.discovery = ZeroconfDiscovery()
        self.discovery._fw_uid = LOCAL_FW
        self.discovery._zeroconf = cast(Any, self.zeroconf)
        self.discovery._registry = cast(Any, self.registry)
        self.discovery._access = cast(Any, self.access)
        self.zc = cast(Any, self.zeroconf)

    def add_service(self, name: str = RS_NAME, type_: str = DEFAULT_ZEROCONF_TYPE) -> None:
        """
        Notifies the discovery of a new record
        """
        self.discovery.add_service(self.zc, type_, name)

    def test_ignored_records(self) -> None:
        """
        Unreadable, local and non-Pelix records are ignored
        """
        with self.assertLogs(LOGGER_NAME, "WARNING"):
            self.add_service()

        self.zeroconf.infos[RS_NAME] = make_info(endpoint_props(LOCAL_FW))
        self.add_service()

        self.zeroconf.infos[RS_NAME] = make_info({"some": "property"})
        with self.assertLogs(LOGGER_NAME, "WARNING"):
            self.add_service()

        self.assertEqual([], self.registry.added)
        self.assertEqual([], self.access.discovered)

    def test_dispatcher_record(self) -> None:
        """
        The access to a remote dispatcher is given to the dispatcher servlet
        """
        props = {pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID: REMOTE_FW, "pelix.access.path": "/dispatcher"}
        dispatcher_type = ZeroconfDiscovery.DNS_DISPATCHER_TYPE
        self.zeroconf.infos[DISPATCHER_NAME] = make_info(props)
        self.add_service(DISPATCHER_NAME, dispatcher_type)
        self.assertEqual([("192.168.1.2", 8080, "/dispatcher")], self.access.discovered)

        # Without address, the server name is used
        self.zeroconf.infos[DISPATCHER_NAME] = make_info(props, addresses=[], server="remote.local.")
        self.add_service(DISPATCHER_NAME, dispatcher_type)
        self.assertEqual(("remote.local.", 8080, "/dispatcher"), self.access.discovered[-1])

        # Incomplete records are ignored
        for kwargs in ({"port": None}, {"addresses": [], "server": None}):
            self.zeroconf.infos[DISPATCHER_NAME] = make_info(props, **kwargs)
            with self.assertLogs(LOGGER_NAME, "WARNING"):
                self.add_service(DISPATCHER_NAME, dispatcher_type)
        self.assertEqual(2, len(self.access.discovered))

    def test_dispatcher_lost(self) -> None:
        """
        The loss of a remote dispatcher means the loss of its framework
        """
        dispatcher_type = ZeroconfDiscovery.DNS_DISPATCHER_TYPE
        self.discovery.remove_service(self.zc, dispatcher_type, f"{LOCAL_FW}.{dispatcher_type}")
        self.assertEqual([], self.registry.lost)

        self.discovery.remove_service(self.zc, dispatcher_type, DISPATCHER_NAME)
        self.assertEqual([REMOTE_FW], self.registry.lost)

    def test_dispatcher_update(self) -> None:
        """
        A remote dispatcher update is handled as a removal then an addition
        """
        dispatcher_type = ZeroconfDiscovery.DNS_DISPATCHER_TYPE
        self.discovery.update_service(self.zc, dispatcher_type, f"{LOCAL_FW}.{dispatcher_type}")
        self.assertEqual([], self.registry.lost)

        self.zeroconf.infos[DISPATCHER_NAME] = make_info(
            {pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID: REMOTE_FW, "pelix.access.path": "/dispatcher"}
        )
        self.discovery.update_service(self.zc, dispatcher_type, DISPATCHER_NAME)
        self.assertEqual([REMOTE_FW], self.registry.lost)
        self.assertEqual([("192.168.1.2", 8080, "/dispatcher")], self.access.discovered)

    def test_remote_service(self) -> None:
        """
        A remote service record is converted to an import endpoint
        """
        self.zeroconf.infos[RS_NAME] = make_info(endpoint_props())
        self.add_service()

        self.assertEqual(1, len(self.registry.added))
        endpoint = self.registry.added[0]
        self.assertEqual("endpoint-uid", endpoint.uid)
        self.assertEqual(REMOTE_FW, endpoint.framework)
        self.assertEqual(["jsonrpc"], list(endpoint.configurations))
        self.assertEqual(["sample.spec"], list(endpoint.specifications))

        # Removal of unknown services is ignored
        self.discovery.remove_service(self.zc, DEFAULT_ZEROCONF_TYPE, "unknown")
        self.assertEqual([], self.registry.removed)

        self.discovery.remove_service(self.zc, DEFAULT_ZEROCONF_TYPE, RS_NAME)
        self.assertEqual(["endpoint-uid"], self.registry.removed)

        # Already removed
        self.discovery.remove_service(self.zc, DEFAULT_ZEROCONF_TYPE, RS_NAME)
        self.assertEqual(["endpoint-uid"], self.registry.removed)

    def test_refused_remote_service(self) -> None:
        """
        An endpoint refused by the registry isn't associated to its record
        """
        self.registry.accept = False
        self.zeroconf.infos[RS_NAME] = make_info(
            endpoint_props(**{pelix.remote.PROP_IMPORTED_CONFIGS: "xmlrpc"})
        )
        self.add_service()
        self.assertEqual(["xmlrpc"], list(self.registry.added[0].configurations))

        self.discovery.remove_service(self.zc, DEFAULT_ZEROCONF_TYPE, RS_NAME)
        self.assertEqual([], self.registry.removed)

    def test_incomplete_remote_service(self) -> None:
        """
        A remote service record without endpoint ID is ignored
        """
        props = endpoint_props()
        del props[pelix.remote.PROP_ENDPOINT_ID]
        self.zeroconf.infos[RS_NAME] = make_info(props)
        with self.assertLogs(LOGGER_NAME, "WARNING"):
            self.add_service()
        self.assertEqual([], self.registry.added)

    def test_record_without_specification(self) -> None:
        """
        A remote service record without specification or imported
        configuration is ignored with a warning, like records without
        endpoint ID
        """
        for key in (pelix.constants.OBJECTCLASS, pelix.remote.PROP_IMPORTED_CONFIGS):
            props = endpoint_props()
            del props[key]
            self.zeroconf.infos[RS_NAME] = make_info(props)
            with self.assertLogs(LOGGER_NAME, "WARNING"):
                self.add_service()
            self.assertEqual([], self.registry.added)

    def test_remote_service_update(self) -> None:
        """
        A remote service update updates the imported endpoint, or imports it
        if it is unknown
        """
        self.zeroconf.infos[RS_NAME] = make_info(endpoint_props())
        self.discovery.update_service(self.zc, DEFAULT_ZEROCONF_TYPE, RS_NAME)
        self.assertEqual(1, len(self.registry.added))

        self.zeroconf.infos[RS_NAME] = make_info(endpoint_props(answer=42))
        self.discovery.update_service(self.zc, DEFAULT_ZEROCONF_TYPE, RS_NAME)
        self.assertEqual(1, len(self.registry.added))
        self.assertEqual(1, len(self.registry.updated))
        uid, properties = self.registry.updated[0]
        self.assertEqual("endpoint-uid", uid)
        self.assertEqual(42, properties["answer"])

    def test_remote_service_update_timeout(self) -> None:
        """
        An update without readable information is ignored
        """
        self.zeroconf.infos[RS_NAME] = make_info(endpoint_props())
        self.add_service()

        del self.zeroconf.infos[RS_NAME]
        with self.assertLogs(LOGGER_NAME, "WARNING"):
            self.discovery.update_service(self.zc, DEFAULT_ZEROCONF_TYPE, RS_NAME)
        self.assertEqual([], self.registry.updated)

    def test_remove_after_update(self) -> None:
        """
        A remote service removed after an update is removed from the registry:
        the update keeps the record name -> endpoint UID association
        """
        self.zeroconf.infos[RS_NAME] = make_info(endpoint_props())
        self.add_service()
        self.discovery.update_service(self.zc, DEFAULT_ZEROCONF_TYPE, RS_NAME)

        self.discovery.remove_service(self.zc, DEFAULT_ZEROCONF_TYPE, RS_NAME)
        self.assertEqual(["endpoint-uid"], self.registry.removed)

    def test_exported_endpoints(self) -> None:
        """
        Exported endpoints are only handled when Zeroconf and the dispatcher
        are ready
        """
        # Only the UID of the endpoint is used before Zeroconf registration
        exp_endpoint = cast(ExportEndpoint, types.SimpleNamespace(uid="uid"))
        with self.assertLogs(LOGGER_NAME, "ERROR"):
            self.discovery.endpoints_added([exp_endpoint])

        # Unknown endpoint: nothing to unregister
        self.discovery.endpoint_removed(exp_endpoint)
        self.assertEqual([], self.zeroconf.unregistered)

        info = object()
        self.discovery._export_infos["uid"] = cast(Any, info)
        self.discovery.endpoint_updated(exp_endpoint, {})
        self.discovery.endpoint_removed(exp_endpoint)
        self.assertEqual([info], self.zeroconf.unregistered)
        self.assertEqual({}, self.discovery._export_infos)

        # Zeroconf not ready
        self.discovery._zeroconf = None
        with self.assertLogs(LOGGER_NAME, "ERROR"):
            self.discovery.endpoints_added([exp_endpoint])
        with self.assertLogs(LOGGER_NAME, "ERROR"):
            self.discovery.endpoint_removed(exp_endpoint)


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
