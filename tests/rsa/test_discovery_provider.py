#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the RSA discovery provider API: endpoint advertisers, endpoint
subscribers and the dispatch of endpoint events

:author: Thomas Calmant
"""

import unittest
from typing import Any, cast

import pelix.framework
from pelix.internals.registry import ServiceReference
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.decorators import ComponentFactory
from pelix.rsa import get_current_time_millis, get_edef_props
from pelix.rsa.endpointdescription import EndpointDescription
from pelix.rsa.providers.discovery import (
    EndpointAdvertiser,
    EndpointEvent,
    EndpointEventListener,
    EndpointSubscriber,
)

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

SCOPE: str = EndpointEventListener.ENDPOINT_LISTENER_SCOPE  # ty: ignore[unresolved-attribute]

# ------------------------------------------------------------------------------


def make_ed(service_id: int = 1, extra: dict[str, Any] | None = None) -> EndpointDescription:
    """
    Prepares an endpoint description
    """
    props = get_edef_props(
        ["test.discovery.spec"],
        ["test.config"],
        "test.namespace",
        "unused",
        "test-container",
        service_id,
        get_current_time_millis(),
        fw_id="test-framework",
    )
    props.update(extra or {})
    return EndpointDescription.fromprops(props)


class RecordingAdvertiser(EndpointAdvertiser):
    """
    Advertiser recording the calls to its protocol-specific methods
    """

    def __init__(self) -> None:
        super().__init__()
        self.result: Any = "advertised"
        self.calls: list[tuple[str, Any]] = []

    def _advertise(self, endpoint_description: EndpointDescription) -> Any:
        self.calls.append(("advertise", endpoint_description))
        return self.result

    def _update(self, endpoint_description: EndpointDescription) -> Any:
        self.calls.append(("update", endpoint_description))
        return self.result

    def _unadvertise(self, advertised: tuple[EndpointDescription, Any]) -> Any:
        self.calls.append(("unadvertise", advertised))
        return self.result


class RecordingListener:
    """
    Endpoint event listener keeping track of its notifications
    """

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[tuple[EndpointEvent, str | None]] = []

    def endpoint_changed(self, endpoint_event: EndpointEvent, matched_filter: str | None) -> None:
        self.events.append((endpoint_event, matched_filter))
        if self.fail:
            raise ValueError("Listener failure")


class FakeReference:
    """
    Service reference stand-in: the subscriber only reads the scope property
    """

    def __init__(self, scope: Any) -> None:
        self._scope = scope

    def get_property(self, name: str) -> Any:
        return self._scope if name == SCOPE else None


@ComponentFactory("test-rsa-endpoint-subscriber-factory")
class SubscriberComponent(EndpointSubscriber):
    """
    Component relying on the listener injection inherited from
    EndpointSubscriber
    """


# ------------------------------------------------------------------------------


class EndpointAdvertiserTest(unittest.TestCase):
    """
    Tests the bookkeeping done by EndpointAdvertiser
    """

    def setUp(self) -> None:
        self.advertiser = RecordingAdvertiser()
        self.ed = make_ed()

    def test_advertise(self) -> None:
        """
        An endpoint is advertised only once
        """
        ed_id = self.ed.get_id()
        self.assertFalse(self.advertiser.is_advertised(ed_id))
        self.assertIsNone(self.advertiser.get_advertised_endpoint(ed_id))

        self.assertTrue(self.advertiser.advertise_endpoint(self.ed))
        self.assertTrue(self.advertiser.is_advertised(ed_id))
        self.assertEqual((self.ed, "advertised"), self.advertiser.get_advertised_endpoint(ed_id))

        # Already advertised: the protocol isn't called again
        self.assertFalse(self.advertiser.advertise_endpoint(self.ed))
        self.assertEqual([("advertise", self.ed)], self.advertiser.calls)

        # The advertised endpoints are returned as a copy
        endpoints = self.advertiser.get_advertised_endpoints()
        self.assertEqual({ed_id: (self.ed, "advertised")}, endpoints)
        endpoints.clear()
        self.assertTrue(self.advertiser.is_advertised(ed_id))

    def test_advertise_failure(self) -> None:
        """
        An endpoint the protocol failed to advertise isn't kept
        """
        self.advertiser.result = None
        self.assertFalse(self.advertiser.advertise_endpoint(self.ed))
        self.assertFalse(self.advertiser.is_advertised(self.ed.get_id()))
        self.assertEqual({}, self.advertiser.get_advertised_endpoints())

    def test_update(self) -> None:
        """
        Only advertised endpoints can be updated
        """
        self.assertFalse(self.advertiser.update_endpoint(self.ed))
        self.assertEqual([], self.advertiser.calls)

        self.advertiser.advertise_endpoint(self.ed)
        updated = make_ed(extra={"foo": "bar", "endpoint.id": self.ed.get_id()})
        self.advertiser.result = "updated"
        self.assertTrue(self.advertiser.update_endpoint(updated))

        advertised = self.advertiser.get_advertised_endpoint(self.ed.get_id())
        assert advertised is not None
        self.assertIs(updated, advertised[0])
        self.assertEqual("updated", advertised[1])

        # A failed update keeps the previous state
        self.advertiser.result = None
        self.assertFalse(self.advertiser.update_endpoint(make_ed(extra={"endpoint.id": self.ed.get_id()})))
        self.assertEqual((updated, "updated"), self.advertiser.get_advertised_endpoint(self.ed.get_id()))

    def test_unadvertise(self) -> None:
        """
        Unadvertising forgets the endpoint, unless the protocol failed
        """
        self.assertFalse(self.advertiser.unadvertise_endpoint(self.ed.get_id()))
        self.assertEqual([], self.advertiser.calls)

        self.advertiser.advertise_endpoint(self.ed)
        self.assertTrue(self.advertiser.unadvertise_endpoint(self.ed.get_id()))
        self.assertEqual(("unadvertise", (self.ed, "advertised")), self.advertiser.calls[-1])
        self.assertFalse(self.advertiser.is_advertised(self.ed.get_id()))

        # Protocol failure: the endpoint is still considered as advertised
        self.advertiser.advertise_endpoint(self.ed)
        self.advertiser.result = None
        self.advertiser.unadvertise_endpoint(self.ed.get_id())
        self.assertTrue(self.advertiser.is_advertised(self.ed.get_id()))


class EndpointEventTest(unittest.TestCase):
    """
    Tests the endpoint event bean
    """

    def test_bean(self) -> None:
        """
        Checks the event getters
        """
        ed = make_ed()
        event = EndpointEvent(EndpointEvent.MODIFIED, ed)
        self.assertEqual(EndpointEvent.MODIFIED, event.get_type())
        self.assertIs(ed, event.get_endpoint_description())
        self.assertIn("type=4", str(event))
        self.assertIn(str(ed), str(event))


class EndpointSubscriberTest(unittest.TestCase):
    """
    Tests the EndpointSubscriber utility methods
    """

    def setUp(self) -> None:
        self.subscriber = EndpointSubscriber()

    def add_listener(self, scope: Any, fail: bool = False) -> RecordingListener:
        """
        Binds a listener with the given scope
        """
        listener = RecordingListener(fail)
        self.subscriber._add_endpoint_event_listener(
            "_event_listeners", cast(Any, listener), cast(ServiceReference[Any], FakeReference(scope))
        )
        return listener

    def test_matching_listeners(self) -> None:
        """
        Listeners are selected according to their scope filters
        """
        ed = make_ed(extra={"color": "blue"})
        no_scope = self.add_listener(None)
        other = self.add_listener("(color=red)")
        blue = self.add_listener("(color=blue)")
        multi = self.add_listener(["(color=green)", "(color=*)", "(objectClass=*)"])

        matching = self.subscriber._get_matching_endpoint_event_listeners(ed)
        self.assertEqual([(blue, "(color=blue)"), (multi, "(color=*)")], matching)
        self.assertNotIn(no_scope, [item[0] for item in matching])
        self.assertNotIn(other, [item[0] for item in matching])

    def test_fire_event(self) -> None:
        """
        Events are given to matching listeners, even if one of them fails
        """
        ed = make_ed()
        failing = self.add_listener("(objectClass=*)", fail=True)
        listener = self.add_listener("(endpoint.id=*)")
        ignored = self.add_listener("(unknown=*)")

        self.subscriber._fire_endpoint_event(EndpointEvent.ADDED, ed)
        self.assertEqual(1, len(failing.events))
        self.assertEqual([], ignored.events)

        self.assertEqual(1, len(listener.events))
        event, matched_filter = listener.events[0]
        self.assertEqual(EndpointEvent.ADDED, event.get_type())
        self.assertIs(ed, event.get_endpoint_description())
        self.assertEqual("(endpoint.id=*)", matched_filter)

    def test_fire_event_no_listener(self) -> None:
        """
        No matching listener: the event is dropped
        """
        listener = self.add_listener("(unknown=*)")
        with self.assertLogs("pelix.rsa.providers.discovery", "ERROR"):
            self.subscriber._fire_endpoint_event(EndpointEvent.REMOVED, make_ed())
        self.assertEqual([], listener.events)

    def test_remove_listener(self) -> None:
        """
        Unbound listeners aren't notified anymore; unbinding an unknown
        listener is only logged
        """
        ref = cast(ServiceReference[Any], FakeReference("(objectClass=*)"))
        listener = RecordingListener()
        self.subscriber._add_endpoint_event_listener("_event_listeners", cast(Any, listener), ref)
        self.subscriber._remove_endpoint_event_listener("_event_listeners", cast(Any, listener), ref)

        with self.assertLogs("pelix.rsa.providers.discovery", "ERROR"):
            self.subscriber._remove_endpoint_event_listener("_event_listeners", cast(Any, listener), ref)

        with self.assertLogs("pelix.rsa.providers.discovery", "ERROR"):
            self.subscriber._fire_endpoint_event(EndpointEvent.ADDED, make_ed())
        self.assertEqual([], listener.events)

    def test_discovered_endpoints(self) -> None:
        """
        Discovered endpoints are kept per session
        """
        ed_1 = make_ed(1)
        ed_2 = make_ed(2)
        ed_3 = make_ed(3)
        self.subscriber._add_discovered_endpoint("session-1", ed_1)
        self.subscriber._add_discovered_endpoint("session-1", ed_2)
        self.subscriber._add_discovered_endpoint("session-2", ed_3)

        self.assertIs(ed_1, self.subscriber._has_discovered_endpoint(ed_1.get_id()))
        self.assertIsNone(self.subscriber._has_discovered_endpoint("unknown"))
        self.assertEqual(
            {ed_1.get_id(), ed_2.get_id()}, set(self.subscriber._get_endpointids_for_sessionid("session-1"))
        )
        self.assertEqual([ed_3.get_id()], self.subscriber._get_endpointids_for_sessionid("session-2"))
        self.assertEqual([], self.subscriber._get_endpointids_for_sessionid("unknown"))

        self.assertIs(ed_1, self.subscriber._remove_discovered_endpoint(ed_1.get_id()))
        self.assertIsNone(self.subscriber._remove_discovered_endpoint(ed_1.get_id()))
        self.assertIsNone(self.subscriber._has_discovered_endpoint(ed_1.get_id()))
        self.assertEqual([ed_2.get_id()], self.subscriber._get_endpointids_for_sessionid("session-1"))


class EndpointSubscriberComponentTest(unittest.TestCase):
    """
    Tests the listener injection in an EndpointSubscriber component
    """

    def setUp(self) -> None:
        self.framework = pelix.framework.create_framework(["pelix.ipopo.core"])
        self.addCleanup(pelix.framework.FrameworkFactory.delete_framework)
        self.framework.start()

    def tearDown(self) -> None:
        self.framework.delete(True)

    def test_injection(self) -> None:
        """
        Listener services are bound and unbound by iPOPO
        """
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            ipopo.register_factory(context, SubscriberComponent)
            subscriber = cast(
                SubscriberComponent,
                ipopo.instantiate("test-rsa-endpoint-subscriber-factory", "subscriber", {}),
            )

        listener = RecordingListener()
        svc_reg = context.register_service(EndpointEventListener, listener, {SCOPE: "(objectClass=*)"})

        ed = make_ed()
        subscriber._fire_endpoint_event(EndpointEvent.ADDED, ed)
        self.assertEqual(1, len(listener.events))
        self.assertEqual("(objectClass=*)", listener.events[0][1])

        svc_reg.unregister()
        with self.assertLogs("pelix.rsa.providers.discovery", "ERROR"):
            subscriber._fire_endpoint_event(EndpointEvent.REMOVED, ed)
        self.assertEqual(1, len(listener.events))


if __name__ == "__main__":
    unittest.main()
