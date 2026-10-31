#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the authentication and authorization helpers of the remote services

:author: Thomas Calmant
"""

import json
import os
import tempfile
import time
import unittest
from collections.abc import Mapping
from typing import Any, Protocol

import pelix.framework
from pelix.constants import SERVICE_RANKING, Specification
from pelix.remote import security
from pelix.security import (
    ANONYMOUS,
    AccessDenied,
    AuthenticationRequired,
    Authorization,
    ClientCertificate,
    Credentials,
    Permission,
    Subject,
    UsernamePassword,
    run_as,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

ALICE = Subject("alice", authenticated=True)

# ------------------------------------------------------------------------------


class FakeAuthorization:
    """
    Grants a fixed set of permissions to every subject
    """

    def __init__(self, granted: set[str]) -> None:
        self.granted = granted

    def is_permitted(self, permission: Permission, subject: Subject | None = None) -> bool:
        return str(permission) in self.granted or permission.action in self.granted

    def check_permitted(self, permission: Permission, subject: Subject | None = None) -> None:
        if not self.is_permitted(permission, subject):
            raise AccessDenied(str(permission))


class FixedProvider:
    """
    Gives the same credentials for every peer
    """

    def __init__(self, credentials: Credentials | None) -> None:
        self.credentials = credentials

    def get_credentials(self, transport: str, url: str, endpoint: Mapping[str, Any]) -> Credentials | None:
        return self.credentials


@Specification("test.remote.hello")
class Hello(Protocol):
    def hello(self) -> str: ...


class HelloImpl(Hello):
    def hello(self) -> str:
        return "hello"

    def extra(self) -> str:
        return "extra"


class Untyped:
    def hello(self) -> str:
        return "hello"

    def extra(self) -> str:
        return "extra"


# ------------------------------------------------------------------------------


class RemoteSecurityTest(unittest.TestCase):
    """
    Tests the helpers which need a framework
    """

    def setUp(self) -> None:
        self.context = self._restart({})
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)

    @staticmethod
    def _restart(properties: dict[str, Any]) -> pelix.framework.BundleContext:
        """
        Starts a new framework: framework properties can't be updated
        """
        pelix.framework.FrameworkFactory.delete_framework()
        framework = pelix.framework.create_framework((), properties)
        framework.start()
        return framework.get_bundle_context()

    def test_check_call(self) -> None:
        """
        Exports allowed or refused depending on what they declare and where they listen
        """
        self.context.register_service(
            Authorization, FakeAuthorization({"pelix.remote.call:granted", "custom"}), {}
        )

        # declared permission, local only, subject, endpoint name, expected exception
        cases: list[tuple[str | None, bool, Subject, str, type[Exception] | None]] = [
            (None, True, ANONYMOUS, "any", None),
            (None, False, ANONYMOUS, "any", AuthenticationRequired),
            (None, False, ALICE, "any", AccessDenied),
            (None, False, ALICE, "granted", None),
            ("*", False, ANONYMOUS, "any", None),
            ("custom", True, ALICE, "any", None),
            ("other", True, ALICE, "any", AccessDenied),
            ("other", True, ANONYMOUS, "any", AuthenticationRequired),
        ]
        for declared, local_only, subject, name, expected in cases:
            with self.subTest(declared=declared, local_only=local_only, subject=subject.name, name=name):
                properties = {} if declared is None else {security.PROP_PERMISSION: declared}
                with run_as(subject):
                    if expected is None:
                        security.check_call(self.context, properties, name, local_only)
                    else:
                        self.assertRaises(
                            expected, security.check_call, self.context, properties, name, local_only
                        )

    def test_check_call_allowed_clients(self) -> None:
        """
        A client of an allowed network needs no permission, the others follow the usual rules
        """
        networks = security.parse_networks("10.0.0.0/24, fd00::/8")
        for client, declared, expected in (
            ("10.0.0.7", None, None),
            ("10.0.0.7", "other", None),
            ("fd00::7", None, None),
            ("10.0.1.7", None, AuthenticationRequired),
            ("10.0.1.7", "*", None),
            (None, None, AuthenticationRequired),
        ):
            with self.subTest(client=client, declared=declared):
                properties = {} if declared is None else {security.PROP_PERMISSION: declared}
                with run_as(Subject("anonymous", client_address=client)):
                    if expected is None:
                        security.check_call(self.context, properties, "any", False, networks)
                    else:
                        self.assertRaises(
                            expected, security.check_call, self.context, properties, "any", False, networks
                        )

    def test_check_call_without_authorization(self) -> None:
        """
        No authorization service: what needs a permission is refused
        """
        with run_as(ALICE):
            security.check_call(self.context, {}, "any", True)
            self.assertRaises(AccessDenied, security.check_call, self.context, {}, "any", False)

    def test_auth_headers(self) -> None:
        """
        Credentials only go to HTTPS or loopback peers
        """
        self.assertEqual(security.get_auth_headers(self.context, "test", "https://peer:8443/", {}), {})

        provider = FixedProvider(UsernamePassword("user", "pass"))
        registration = self.context.register_service(security.RemoteCredentialsProvider, provider, {})
        basic = {"Authorization": "Basic dXNlcjpwYXNz"}
        for url, expected in (
            ("https://peer.example:8443/JSON-RPC", basic),
            ("http://localhost:8080/JSON-RPC", basic),
            ("http://127.0.0.1:8080/JSON-RPC", basic),
            ("http://[::1]:8080/JSON-RPC", basic),
            ("http://peer.example:8080/JSON-RPC", {}),
            ("http://192.168.1.2:8080/JSON-RPC", {}),
        ):
            with self.subTest(url=url):
                self.assertEqual(security.get_auth_headers(self.context, "test", url, {}), expected)

        # Unsupported kind of credentials, or abstention
        for credentials in (ClientCertificate("a" * 64, "CN=test"), None):
            with self.subTest(credentials=credentials):
                provider.credentials = credentials
                self.assertEqual(security.get_auth_headers(self.context, "test", "https://peer/", {}), {})

        # The best ranked provider answers first
        provider.credentials = UsernamePassword("user", "pass")
        self.context.register_service(
            security.RemoteCredentialsProvider,
            FixedProvider(UsernamePassword("other", "x")),
            {SERVICE_RANKING: 10},
        )
        self.assertEqual(
            security.get_auth_headers(self.context, "test", "https://peer/", {}),
            {"Authorization": "Basic b3RoZXI6eA=="},
        )
        registration.unregister()

    def test_cap_ranking(self) -> None:
        """
        Imported services rank below the local ones by default
        """
        for ranking, cap, expected in (
            (None, None, -1),
            (100, None, -1),
            (-5, None, -5),
            ("100", None, -1),
            (100, 2**31 - 1, 100),
            (100, "invalid", -1),
        ):
            with self.subTest(ranking=ranking, cap=cap):
                context = self._restart({security.PROP_IMPORT_MAX_RANKING: cap})
                properties = {"a": 1} if ranking is None else {"a": 1, SERVICE_RANKING: ranking}
                self.assertEqual(
                    security.cap_ranking(context, properties), {"a": 1, SERVICE_RANKING: expected}
                )

    def test_accept_import(self) -> None:
        """
        The import filter selects the endpoints
        """
        properties = {"objectClass": ["sample.hello"], "endpoint.framework.uuid": "peer"}
        for ldap_filter, expected in (
            (None, True),
            ("(objectClass=sample.*)", True),
            ("(endpoint.framework.uuid=other)", False),
            ("(invalid", False),
        ):
            with self.subTest(ldap_filter=ldap_filter):
                context = self._restart({security.PROP_IMPORT_FILTER: ldap_filter})
                self.assertEqual(security.accept_import(context, properties), expected)


class RemoteSecurityHelpersTest(unittest.TestCase):
    """
    Tests the helpers which need no framework
    """

    def test_is_loopback_host(self) -> None:
        """
        Only names and addresses of the local host are loopback ones
        """
        for host, expected in (
            ("localhost", True),
            ("LOCALHOST", True),
            ("127.0.0.1", True),
            ("127.1.2.3", True),
            ("::1", True),
            ("[::1]", True),
            ("::ffff:127.0.0.1", True),
            ("0.0.0.0", False),
            ("::", False),
            ("192.168.1.2", False),
            ("localhost.evil.example", False),
            ("", False),
            (None, False),
        ):
            with self.subTest(host=host):
                self.assertEqual(security.is_loopback_host(host), expected)

    def test_parse_networks(self) -> None:
        """
        Addresses and CIDR networks, IPv4 and IPv6, as a string or a list
        """
        for value, expected in (
            (None, ()),
            ("", ()),
            ("10.0.0.5", ("10.0.0.5/32",)),
            ("172.14.0.0/16, 10.0.0.5 fd00::/8", ("172.14.0.0/16", "10.0.0.5/32", "fd00::/8")),
            (["192.168.1.0/24", "::1"], ("192.168.1.0/24", "::1/128")),
        ):
            with self.subTest(value=value):
                self.assertEqual(tuple(str(network) for network in security.parse_networks(value)), expected)

        for value in (
            "10.0.0.5/24",
            "10.0.0.0/33",
            "300.0.0.1",
            "example.com",
            "fd00::/8, nope",
            ["10.0.0.0/8", ""],
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError) as ctx:
                    security.parse_networks(value)
                self.assertIn(security.PROP_ALLOWED_CLIENTS, str(ctx.exception))

    def test_is_allowed_client(self) -> None:
        """
        The client address of the subject is looked for in the networks
        """
        networks = security.parse_networks("172.14.0.0/16, 10.0.0.5, fd00::/8")
        for client, expected in (
            ("172.14.3.4", True),
            ("172.15.0.1", False),
            ("10.0.0.5", True),
            ("10.0.0.6", False),
            ("::ffff:172.14.0.1", True),
            ("fd12::1", True),
            ("fd12::1%eth0", True),
            ("[fd12::1]", True),
            ("fe80::1", False),
            ("unix:uid=1000", False),
            (None, False),
        ):
            with self.subTest(client=client), run_as(Subject("x", client_address=client)):
                self.assertEqual(security.is_allowed_client(networks), expected)

        with run_as(Subject("x", client_address="10.0.0.5")):
            self.assertFalse(security.is_allowed_client(()))

    def test_get_remote_method(self) -> None:
        """
        Only the methods of the exported specification can be called, when it is a class
        """
        for service, specifications, name, allowed in (
            (HelloImpl(), ["test.remote.hello"], "hello", True),
            (HelloImpl(), ["test.remote.hello"], "extra", False),
            (HelloImpl(), ["test.remote.hello"], "_private", False),
            (HelloImpl(), ["other"], "extra", True),
            (Untyped(), ["test.remote.hello"], "extra", True),
            (Untyped(), ["test.remote.hello"], "missing", False),
        ):
            with self.subTest(service=type(service).__name__, specifications=specifications, name=name):
                method = security.get_remote_method(service, name, specifications)
                self.assertEqual(method is not None, allowed)

    def test_credentials_file(self) -> None:
        """
        Credentials are selected by the origin of the peer
        """
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as file:
            file.write(
                """
[[peer]]
origin = "https://peer.example"
username = "batch"
password = "secret"

[[peer]]
origin = "http://[::1]:8080"
username = "local"
password = "secret"

[[peer]]
origin = "not a url"
username = "ignored"
password = "x"
"""
            )
        self.addCleanup(os.remove, file.name)
        os.chmod(file.name, 0o600)

        store = security.CredentialsFile()
        store._path = file.name
        store._validate(None)

        for url, expected in (
            ("https://peer.example/JSON-RPC", "batch"),
            ("https://PEER.example:443/XML-RPC", "batch"),
            ("https://peer.example:8443/", None),
            ("http://peer.example/", None),
            ("http://[::1]:8080/", "local"),
            ("garbage", None),
        ):
            with self.subTest(url=url):
                credentials = store.get_credentials("test", url, {})
                self.assertEqual(
                    credentials.username if isinstance(credentials, UsernamePassword) else None, expected
                )

    def test_discovery_signer(self) -> None:
        """
        Signed announcements are accepted once, the others never
        """
        self.assertRaises(ValueError, security.DiscoverySigner, b"short")

        key = b"k" * 32
        signer = security.DiscoverySigner(key)
        payload = {"event": "add", "endpoints": [{"uid": "1", "ranking": 1.5}]}

        # Through JSON, as the discoveries send them
        signed = json.loads(json.dumps(signer.sign(payload)))
        self.assertEqual(signer.verify(signed), payload)

        tampered = json.loads(json.dumps(signed))
        tampered["event"] = "remove"
        expired = security.DiscoverySigner(key).sign(payload)
        expired_signer = security.DiscoverySigner(key, max_age=0.0)
        time.sleep(0.01)

        for name, verifier, message in (
            ("replayed", signer, signed),
            ("tampered", signer, tampered),
            ("other key", security.DiscoverySigner(b"o" * 32), signed),
            ("unsigned", signer, payload),
            ("bad signature", signer, {**payload, "pelix.remote.signature": "x"}),
            ("not a dict", signer, ["event"]),
            ("expired", expired_signer, expired),
        ):
            with self.subTest(name=name):
                self.assertIsNone(verifier.verify(message))

    def test_discovery_key_file(self) -> None:
        """
        The key is read from a file
        """
        with tempfile.NamedTemporaryFile("wb", delete=False) as file:
            file.write(b"  " + b"k" * 32 + b"\n")
        self.addCleanup(os.remove, file.name)

        signed = security.DiscoverySigner(b"k" * 32).sign({"a": 1})
        self.assertEqual(security.DiscoverySigner.from_file(file.name).verify(signed), {"a": 1})


if __name__ == "__main__":
    unittest.main()
