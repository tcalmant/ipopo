#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the EventAdmin service

:author: Thomas Calmant
"""

import random
import threading
import time
import unittest
from typing import Any, cast

import pelix.framework
import pelix.services
from pelix.internals.registry import ServiceRegistration
from pelix.ipopo.constants import use_ipopo
from pelix.services.eventdelivery import EventDeliveryError, EventProperties

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class DummyEventHandler:
    """
    Dummy event handler
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        # Topic of the last received event
        self.last_event: str | None = None
        self.last_props: dict[str, Any] = {}
        self.__event = threading.Event()

        # Behavior
        self.change_props: Any = False
        self.sleep = 0

    def handle_event(self, topic: str, properties: dict[str, Any]) -> None:
        """
        Handles an event received from EventAdmin
        """
        # Add some behavior
        if self.change_props:
            properties["change"] = self.change_props

        if self.sleep:
            time.sleep(self.sleep)

        # Keep received values
        self.last_event = topic
        self.last_props = properties
        self.__event.set()

    def pop_event(self) -> str | None:
        """
        Pops the list of events
        """
        # Clear the event for next try
        self.__event.clear()

        # Reset last event
        event, self.last_event = self.last_event, None
        return event

    def wait(self, timeout: float) -> None:
        """
        Waits for the event to be received
        """
        self.__event.wait(timeout)


# ------------------------------------------------------------------------------


class EventAdminTest(unittest.TestCase):
    """
    Tests the EventAdmin service
    """

    framework: pelix.framework.Framework

    def setUp(self) -> None:
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(("pelix.ipopo.core", "pelix.services.eventadmin"))
        self.framework.start()

        # Instantiate the EventAdmin component
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            self.eventadmin = ipopo.instantiate(pelix.services.FACTORY_EVENT_ADMIN, "evtadmin", {})

    def _register_handler(
        self, topics: None | str | list[str], evt_filter: str | None = None
    ) -> tuple[DummyEventHandler, ServiceRegistration[pelix.services.ServiceEventHandler]]:
        """
        Registers an event handler

        :param topics: Event topics
        :param evt_filter: Event filter
        """
        svc = DummyEventHandler()
        context = self.framework.get_bundle_context()
        svc_reg = context.register_service(
            pelix.services.ServiceEventHandler,
            cast(pelix.services.ServiceEventHandler, svc),
            {pelix.services.PROP_EVENT_TOPICS: topics, pelix.services.PROP_EVENT_FILTER: evt_filter},
        )
        return svc, svc_reg

    def tearDown(self) -> None:
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.framework = None  # type: ignore

    def assertDictContains(
        self, subset: dict[str, Any], tested: dict[str, Any] | None, msg: Any = None
    ) -> None:
        assert tested is not None
        self.assertEqual(tested, tested | subset, msg)

    def testNoHandler(self) -> None:
        """
        Tests events when no event handler is registered
        """
        self.eventadmin.send("/titi/toto", {"some.value": 42})

    def testTopics(self) -> None:
        """
        Tests the topics filtering
        """
        # Prepare a handler
        handler, _ = self._register_handler("/titi/*")

        # Assert the handler is empty
        self.assertEqual(handler.pop_event(), None)

        # Send events, with a matching topic
        for topic in ("/titi/toto", "/titi/", "/titi/42", "/titi/toto/tata"):
            self.eventadmin.send(topic)
            self.assertEqual(handler.pop_event(), topic)

        # Send events, with a non-matching topic
        for topic in ("/toto/titi/42", "/titi", "/toto/42"):
            self.eventadmin.send(topic)
            self.assertEqual(handler.pop_event(), None)

    def testFilters(self) -> None:
        """
        Tests the events filtering
        """
        # Prepare a handler
        handler, _ = self._register_handler(None, "(answer=42)")

        # Assert the handler is empty
        self.assertEqual(handler.pop_event(), None)

        # Send event, with matching properties
        for topic in ("/titi/toto", "/toto/", "/titi/42", "/titi/toto/tata"):
            for value in (42, "42", [1, 2, 42, 20], {42, 10}, (10, 21, 42)):
                evt_props = {"answer": value}
                self.eventadmin.send(topic, evt_props)

                # Check properties
                self.assertDictContains(evt_props, handler.last_props)
                self.assertIsNot(handler.last_props, evt_props)

                # Check topic
                self.assertEqual(handler.pop_event(), topic)

            # Send events, with a non-matching properties
            for value in (" 42 ", 21, [1, 2, 3], (4, 5, 6), {7, 8, 9}):
                self.eventadmin.send(topic, {"answer": value})
                self.assertEqual(handler.pop_event(), None)

    def testPost(self) -> None:
        """
        Tests the post event method
        """
        # Prepare a handler
        handler, _ = self._register_handler("/titi/*")

        # Post a message
        topic = "/titi/toto"
        self.eventadmin.post(topic)

        # Wait a little
        handler.wait(1)
        self.assertEqual(handler.pop_event(), topic)

        # Add a handler
        handler_2, handler_2_reg = self._register_handler("/titi/*")
        handler_3, _ = self._register_handler("/titi/*")

        # Let the first two handlers sleep
        handler.sleep = 1
        handler_2.sleep = 1

        # Post two messages: the second one waits behind the first one, for each handler
        self.eventadmin.post(topic)
        self.eventadmin.post(topic + "/2")

        # Wait a little (so that the first event is being handled)
        time.sleep(0.2)

        # Unregister the second handler
        handler_2_reg.unregister()

        # Register a new one
        handler_4, _ = self._register_handler("/titi/*")

        # Wait a little: only handlers present during the call to 'post'
        # and still present when their turn comes must be notified
        time.sleep(2.5)
        self.assertEqual(handler.pop_event(), topic + "/2")
        self.assertEqual(handler_2.pop_event(), topic)
        self.assertEqual(handler_3.pop_event(), topic + "/2")
        self.assertEqual(handler_4.pop_event(), None)

    def testProperties(self) -> None:
        """
        Ensures that each handler get its own copy of the properties
        """
        # Prepare handlers
        handler_1, _ = self._register_handler("/titi/*")
        handler_2, _ = self._register_handler("/titi/*")
        handler_3, _ = self._register_handler("/titi/*")

        for handler in (handler_1, handler_2, handler_3):
            handler.change_props = random.randint(1, 10)

        # Send an event
        evt_props = {"answer": 42}
        self.eventadmin.send("/titi/toto", evt_props)

        for handler in (handler_1, handler_2, handler_3):
            # Check that the original properties are kept
            self.assertDictContains(evt_props, handler.last_props)

            # Check that the handler value has been stored
            self.assertEqual(handler.last_props["change"], handler.change_props)

    def testPostOrdering(self) -> None:
        """
        Posted events reach a handler in posting order (OSGi 113.7.3), even when
        the handler is slow for some of them, unless it asked for unordered delivery
        """
        received: list[int] = []

        class SlowHandler:
            def handle_event(self, topic: str, properties: dict[str, Any]) -> None:
                number = properties["n"]
                if number % 3 == 0:
                    time.sleep(0.01)
                received.append(number)

        context = self.framework.get_bundle_context()
        context.register_service(
            pelix.services.ServiceEventHandler,
            cast(pelix.services.ServiceEventHandler, SlowHandler()),
            {pelix.services.PROP_EVENT_TOPICS: "order/*"},
        )

        count = 60
        for number in range(count):
            self.eventadmin.post("order/event", {"n": number})

        deadline = time.time() + 10
        while len(received) < count and time.time() < deadline:
            time.sleep(0.01)

        self.assertEqual(received, list(range(count)))

        # A handler asking for async.unordered delivery is still notified of every event
        received = []
        context.register_service(
            pelix.services.ServiceEventHandler,
            cast(
                pelix.services.ServiceEventHandler,
                type("H", (), {"handle_event": lambda self, topic, props: received.append(props["n"])})(),
            ),
            {
                pelix.services.PROP_EVENT_TOPICS: "/titi/*",
                pelix.services.PROP_EVENT_DELIVERY: pelix.services.DELIVERY_ASYNC_UNORDERED,
            },
        )
        for number in range(20):
            self.eventadmin.post("/titi/x", {"n": number})

        deadline = time.time() + 5
        while len(received) < 20 and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(sorted(received), list(range(20)))

    def testInvalidFilterAndTopic(self) -> None:
        """
        An invalid event.filter disables its handler only (OSGi 113.4), send() doesn't
        fail; the topic is a property filters can test
        """
        broken, _ = self._register_handler("/titi/*", "(answer=")
        good, _ = self._register_handler("/titi/*", "(answer=42)")

        self.eventadmin.send("/titi/x", {"answer": 42})
        self.assertEqual(broken.pop_event(), None)
        self.assertEqual(good.pop_event(), "/titi/x")

        # The topic can be tested as the event.topics property (OSGi 113.3.2)
        handler, _ = self._register_handler(None, "(event.topics=/titi/x)")
        self.eventadmin.send("/titi/x")
        self.assertEqual(handler.pop_event(), "/titi/x")

        # Counter-example: another topic
        self.eventadmin.send("/titi/y")
        self.assertEqual(handler.pop_event(), None)

    def testRaiseErrors(self) -> None:
        """
        send(raise_errors=True) reports failures once every handler was notified
        """

        class Failing:
            def handle_event(self, topic: str, properties: dict[str, Any]) -> None:
                raise RuntimeError("refused")

        context = self.framework.get_bundle_context()
        context.register_service(
            pelix.services.ServiceEventHandler,
            cast(pelix.services.ServiceEventHandler, Failing()),
            {pelix.services.PROP_EVENT_TOPICS: "/titi/*"},
        )
        good, _ = self._register_handler("/titi/*")

        # Default: swallowed
        self.eventadmin.send("/titi/x")
        self.assertEqual(good.pop_event(), "/titi/x")

        with self.assertRaises(EventDeliveryError) as ctx:
            self.eventadmin.send("/titi/x", raise_errors=True)

        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)
        self.assertEqual(len(ctx.exception.errors), 1)
        # The other handler was notified
        self.assertEqual(good.pop_event(), "/titi/x")

        # Counter-example: no failure, no exception
        self.eventadmin.send("/other/x", raise_errors=True)

    def testCopy(self) -> None:
        """
        A value that can't be copied is reported with raise_errors, and can travel
        with copy=False, as the same object in one immutable mapping
        """
        lock = threading.Lock()
        handler, _ = self._register_handler("/titi/*")

        with self.assertRaises(EventDeliveryError):
            self.eventadmin.send("/titi/x", {"lock": lock}, raise_errors=True)
        self.assertEqual(handler.pop_event(), None)

        self.eventadmin.send("/titi/x", {"lock": lock}, copy=False, raise_errors=True)
        self.assertEqual(handler.pop_event(), "/titi/x")
        self.assertIs(handler.last_props["lock"], lock)

        # Handlers share one immutable mapping
        first = handler
        second, _ = self._register_handler("/titi/*")
        self.eventadmin.send("/titi/x", {"answer": 42}, copy=False)

        self.assertIsInstance(first.last_props, EventProperties)
        self.assertIs(first.last_props, second.last_props)
        self.assertEqual(first.last_props["answer"], 42)
        with self.assertRaises(TypeError):
            first.last_props["answer"] = 0  # type: ignore[index]
