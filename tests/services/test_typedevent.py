#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Typed Event bus

:author: Thomas Calmant
"""

import dataclasses
import threading
import time
import unittest
from collections.abc import Mapping
from typing import Any

import pelix.framework
import pelix.services
from pelix.ipopo.constants import use_ipopo
from pelix.services.eventdelivery import (
    EventDeliveryError,
    EventProperties,
    is_valid_topic,
    is_valid_topic_scope,
    topic_matches,
)
from pelix.services.typedevent import default_topic, event_to_map, map_to_event

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ChunkChanged:
    chunk_id: int
    kind: str = "update"


def _local() -> type:
    @dataclasses.dataclass
    class Local:
        a: int

    return Local


# A class without a default topic
Local = _local()


@dataclasses.dataclass(frozen=True)
class Rejected:
    chunk_id: int
    reason: str


class TypedRecorder:
    """
    A typed handler, typed by the annotation of notify()
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, ChunkChanged]] = []
        self.fail = False

    def notify(self, topic: str, event: ChunkChanged) -> None:
        self.calls.append((topic, event))
        if self.fail:
            raise RuntimeError("refused")


class UntypedRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def notify_untyped(self, topic: str, data: Mapping[str, Any]) -> None:
        self.calls.append((topic, data))


class UnhandledRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def notify_unhandled(self, topic: str, data: Mapping[str, Any]) -> None:
        self.calls.append((topic, data))


def _wait(condition: Any, timeout: float = 5) -> bool:
    deadline = time.time() + timeout
    while not condition() and time.time() < deadline:
        time.sleep(0.01)
    return bool(condition())


class TypedEventTest(unittest.TestCase):
    """
    Tests the Typed Event bus
    """

    def setUp(self) -> None:
        self.framework = pelix.framework.create_framework(("pelix.ipopo.core", "pelix.services.typedevent"))
        self.framework.start()
        self.context = self.framework.get_bundle_context()
        with use_ipopo(self.context) as ipopo:
            ipopo.instantiate(pelix.services.FACTORY_TYPED_EVENT_BUS, "bus", {"history.size": 3})

        ref = self.context.get_service_reference(pelix.services.TypedEventBus)
        assert ref is not None
        self.bus = self.context.get_service(ref)

    def tearDown(self) -> None:
        pelix.framework.FrameworkFactory.delete_framework(self.framework)

    def _register(self, spec: Any, handler: Any, **props: Any) -> Any:
        return self.context.register_service(spec, handler, props)

    def test_topics_and_conversions(self) -> None:
        self.assertEqual(default_topic(ChunkChanged), "tests/services/test_typedevent/ChunkChanged")
        self.assertEqual(event_to_map(ChunkChanged(1)), {"chunk_id": 1, "kind": "update"})
        # Extra keys are ignored, missing fields take their default
        self.assertEqual(map_to_event(ChunkChanged, {"chunk_id": 2, "other": 1}), ChunkChanged(2))

        # Counter-examples: not a dataclass instance, local class, missing field
        with self.assertRaises(TypeError):
            event_to_map({"chunk_id": 1})
        with self.assertRaises(TypeError):
            event_to_map(ChunkChanged)
        with self.assertRaises(TypeError):
            map_to_event(Rejected, {"chunk_id": 2})
        with self.assertRaises(ValueError):
            default_topic(Local)

        # OSGi matching rules
        self.assertTrue(topic_matches("a/b/*", "a/b/c"))
        self.assertTrue(topic_matches("a/b/*", "a/b/c/d"))
        self.assertTrue(topic_matches("*", "a"))
        self.assertTrue(topic_matches("a/b", "a/b"))
        # Counter-examples: wildcard needs a sub-topic, case matters, no prefix match
        self.assertFalse(topic_matches("a/b/*", "a/b"))
        self.assertFalse(topic_matches("a/b/*", "a/bc"))
        self.assertFalse(topic_matches("a/b", "A/b"))
        self.assertFalse(topic_matches("a/b", "a/b/c"))

        self.assertTrue(is_valid_topic_scope("a/*"))
        self.assertFalse(is_valid_topic_scope("a*"))
        self.assertFalse(is_valid_topic_scope("a/*/b"))
        self.assertFalse(is_valid_topic("a/*"))

    def test_typed_handlers(self) -> None:
        handler = TypedRecorder()
        self._register(pelix.services.TypedEventHandler, handler)

        event = ChunkChanged(7)
        self.bus.deliver(event, sync=True)

        # Delivered in this call, on the default topic, identity kept
        self.assertEqual(len(handler.calls), 1)
        self.assertEqual(handler.calls[0][0], default_topic(ChunkChanged))
        self.assertIs(handler.calls[0][1], event)

        # Counter-example: another type, on another topic
        self.bus.deliver(Rejected(1, "x"), sync=True)
        self.assertEqual(len(handler.calls), 1)

        # Typed by property, from untyped data
        handler = TypedRecorder()
        self._register(
            pelix.services.TypedEventHandler,
            handler,
            **{
                pelix.services.PROP_EVENT_TOPICS: "chunks/*",
                pelix.services.PROP_EVENT_TYPE: f"{__name__}.ChunkChanged",
            },
        )
        self.bus.deliver_untyped("chunks/changed", {"chunk_id": 3}, sync=True)
        self.assertEqual(handler.calls, [("chunks/changed", ChunkChanged(3))])

        # Counter-example: the scope "chunks/*" does not match "chunks" nor "other/x"
        self.bus.deliver_untyped("chunks", {"chunk_id": 4}, sync=True)
        self.bus.deliver_untyped("other/x", {"chunk_id": 4}, sync=True)
        self.assertEqual(len(handler.calls), 1)

    def test_filter_and_untyped_handler(self) -> None:
        handler = UntypedRecorder()
        self._register(
            pelix.services.UntypedEventHandler,
            handler,
            **{pelix.services.PROP_EVENT_TOPICS: "a/b", pelix.services.PROP_EVENT_FILTER: "(chunk_id=1)"},
        )
        self.bus.deliver_untyped("a/b", {"chunk_id": 1}, sync=True)
        self.assertEqual(len(handler.calls), 1)
        self.assertIsInstance(handler.calls[0][1], EventProperties)

        # Counter-example: filter does not match
        self.bus.deliver_untyped("a/b", {"chunk_id": 2}, sync=True)
        self.assertEqual(len(handler.calls), 1)

    def test_unhandled(self) -> None:
        unhandled = UnhandledRecorder()
        self._register(pelix.services.UnhandledEventHandler, unhandled)
        # An untyped handler without topics receives nothing
        self._register(pelix.services.UntypedEventHandler, UntypedRecorder())
        self.bus.deliver(ChunkChanged(1), sync=True)
        self.assertEqual(len(unhandled.calls), 1)
        self.assertEqual(unhandled.calls[0][1]["chunk_id"], 1)

        # Counter-example: once a handler listens, the event is handled
        self._register(pelix.services.TypedEventHandler, TypedRecorder())
        self.bus.deliver(ChunkChanged(2), sync=True)
        self.assertEqual(len(unhandled.calls), 1)

    def test_invalid_topics_and_handlers(self) -> None:
        for topic in ("", "a//b", "a b", "a/*", "/a"):
            with self.assertRaises(ValueError, msg=topic):
                self.bus.deliver_untyped(topic, {})

        # An invalid scope on a handler is ignored, the valid one stays
        handler = UntypedRecorder()
        self._register(
            pelix.services.UntypedEventHandler,
            handler,
            **{pelix.services.PROP_EVENT_TOPICS: ["a/*/b", "a/b"]},
        )
        self.bus.deliver_untyped("a/x/b", {}, sync=True)
        self.assertEqual(handler.calls, [])
        self.bus.deliver_untyped("a/b", {}, sync=True)
        self.assertEqual(len(handler.calls), 1)

        # Handlers without a usable type are ignored, without breaking the delivery
        class Untyped:
            def notify(self, topic, event):
                raise AssertionError("must not be called")

        class LocalTyped:
            def notify(self, topic: str, event: Local) -> None:
                raise AssertionError("must not be called")

        self._register(
            pelix.services.TypedEventHandler, Untyped(), **{pelix.services.PROP_EVENT_TOPICS: "a/b"}
        )
        self._register(pelix.services.TypedEventHandler, LocalTyped())
        self.bus.deliver_untyped("a/b", {}, sync=True)
        self.assertEqual(len(handler.calls), 2)

    def test_sync_errors(self) -> None:
        bad, good = TypedRecorder(), TypedRecorder()
        bad.fail = True
        self._register(pelix.services.TypedEventHandler, bad)
        self._register(pelix.services.TypedEventHandler, good)

        # Default: logged only
        self.bus.deliver(ChunkChanged(1), sync=True)
        self.assertEqual(len(good.calls), 1)

        with self.assertRaises(EventDeliveryError) as ctx:
            self.bus.deliver(ChunkChanged(2), sync=True, raise_errors=True)
        self.assertIsInstance(ctx.exception.exceptions[0], RuntimeError)
        self.assertEqual(len(good.calls), 2)

    def test_async(self) -> None:
        received: list[int] = []
        threads: set[str] = set()

        class Slow:
            def notify(self, topic: str, event: ChunkChanged) -> None:
                if event.chunk_id % 4 == 0:
                    time.sleep(0.01)
                threads.add(threading.current_thread().name)
                received.append(event.chunk_id)

        # Delivered in order, by another thread
        self._register(pelix.services.TypedEventHandler, Slow())
        for number in range(40):
            self.bus.deliver(ChunkChanged(number))

        self.assertTrue(_wait(lambda: len(received) == 40))
        self.assertEqual(received, list(range(40)))
        self.assertNotIn(threading.current_thread().name, threads)

    def test_history(self) -> None:
        monitor_ref = self.context.get_service_reference(pelix.services.TypedEventMonitor)
        assert monitor_ref is not None
        monitor = self.context.get_service(monitor_ref)

        for number in range(5):
            self.bus.deliver(ChunkChanged(number), sync=True)

        # history.size is 3: the oldest ones are gone
        events = monitor.history()
        self.assertEqual([e.data["chunk_id"] for e in events], [2, 3, 4])
        self.assertEqual([e.data["chunk_id"] for e in monitor.history(2)], [3, 4])
        self.assertEqual(monitor.history(0), [])
