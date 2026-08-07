#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Unit tests for the mDNS/Zeroconf discovery property (de)serialization
(no network setup required)

:author: Thomas Calmant
"""

import importlib.util
import os
import shutil
import tempfile
import unittest
from typing import Any

if importlib.util.find_spec("zeroconf") is None:
    raise unittest.SkipTest("zeroconf is missing: can't test mDNS discovery")

import pelix.constants
import pelix.remote
from pelix.remote.discovery.mdns import PELIX_TYPE_PREFIX, ZeroconfDiscovery

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
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


if __name__ == "__main__":
    unittest.main()
