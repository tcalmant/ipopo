#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the dispatch of calls to services exported by RSA

:author: Thomas Calmant
"""

import unittest
from typing import Any

# Imported first: pelix.rsa.providers.distribution can't be loaded on its own
import pelix.rsa.remoteserviceadmin  # noqa: F401
from pelix.rsa import RemoteServiceError
from pelix.rsa.providers.distribution import ExportContainer

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

RS_ID = 42

SERVICE_SECRET = "s3cr3t-value"

# ------------------------------------------------------------------------------


class DummyService:
    """
    Dummy exported service
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.calls: list[str] = []
        self._secret = SERVICE_SECRET

    def echo(self, value: Any) -> Any:
        """
        Returns the given value
        """
        self.calls.append("echo")
        return value

    def _private_method(self) -> str:
        """
        Private method: it must not be callable by a remote caller
        """
        self.calls.append("_private_method")
        return self._secret


class FakeEndpointDescription:
    """
    Minimal stand-in for an EndpointDescription: the dispatch only looks for
    the remote service ID
    """

    def __init__(self, rs_id: int) -> None:
        self._rs_id = rs_id

    def get_remoteservice_id(self) -> tuple[tuple[str, str], int]:
        """
        Returns the ID of the remote service
        """
        return ("namespace", "container"), self._rs_id


# ------------------------------------------------------------------------------


class ExportContainerDispatchTest(unittest.TestCase):
    """
    Tests the restrictions applied when calling an exported service
    """

    def setUp(self) -> None:
        """
        Prepares a container with a single exported service
        """
        self.service = DummyService()
        self.container = ExportContainer()
        exported: dict[str, tuple[Any, Any]] = {
            "endpoint-id": (self.service, FakeEndpointDescription(RS_ID)),
        }
        self.container._exported_services = exported

    def dispatch(self, method_name: str, params: Any = None) -> Any:
        """
        Calls a method of the exported service
        """
        return self.container._dispatch_exported(RS_ID, method_name, params if params is not None else [])

    def test_public_method(self) -> None:
        """
        The public API of the service must be callable
        """
        self.assertEqual(self.dispatch("echo", ["hello"]), "hello")
        self.assertListEqual(self.service.calls, ["echo"])

    def test_unknown_method(self) -> None:
        """
        An unknown method must be refused
        """
        self.assertRaises(RemoteServiceError, self.dispatch, "unknown")

    def test_unknown_service(self) -> None:
        """
        A call to an unknown service must be refused
        """
        self.assertRaises(RemoteServiceError, self.container._dispatch_exported, RS_ID + 1, "echo", [])

    def test_special_methods_are_refused(self) -> None:
        """
        Special methods must not be callable by a remote caller
        """
        for method_name in (
            "__init__",
            "__class__",
            "__dict__",
            "__str__",
            "__repr__",
            "__getattribute__",
            "__setattr__",
            "__reduce__",
        ):
            with self.subTest(method_name=method_name):
                self.assertRaises(RemoteServiceError, self.dispatch, method_name)

        self.assertListEqual(self.service.calls, [], "Service called by a refused method")

    def test_private_members_are_refused(self) -> None:
        """
        Private methods and attributes must not be callable by a remote caller
        """
        for method_name in ("_private_method", "_secret"):
            with self.subTest(method_name=method_name):
                self.assertRaises(RemoteServiceError, self.dispatch, method_name)

        self.assertListEqual(self.service.calls, [], "Service called by a refused method")

    def test_non_callable_members_are_refused(self) -> None:
        """
        Public but non-callable attributes must not be callable
        """
        self.assertRaises(RemoteServiceError, self.dispatch, "calls")

    def test_private_state_is_not_readable(self) -> None:
        """
        The internal state of the service must not be readable through a
        special method
        """
        self.assertRaises(RemoteServiceError, self.dispatch, "__getattribute__", ["_secret"])
        self.assertEqual(self.service._secret, SERVICE_SECRET)

    def test_service_is_not_altered(self) -> None:
        """
        A refused call must not modify the service
        """
        self.assertRaises(RemoteServiceError, self.dispatch, "__init__")
        self.assertRaises(RemoteServiceError, self.dispatch, "__setattr__", ["_secret", "altered"])

        self.assertEqual(self.service._secret, SERVICE_SECRET)
        self.assertEqual(self.dispatch("echo", ["still alive"]), "still alive")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
