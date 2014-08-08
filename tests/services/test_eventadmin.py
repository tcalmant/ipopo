#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the EventAdmin service

:author: Thomas Calmant
"""

# Pelix
from pelix.ipopo.constants import use_ipopo
import pelix.framework
import pelix.services

# Standard library
import random
import threading
import time
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class DummyEventHandler(object):
    """
    Dummy event handler
    """
    def __init__(self):
        """
        Sets up members
        """
        # Topic of the last received event
        self.last_event = None
        self.last_props = {}
        self.__event = threading.Event()

        # Behavior
        self.change_props = False
        self.sleep = 0

    def handle_event(self, topic, properties):
        """
        Handles an event received from EventAdmin
        """
        # Add some behavior
        if self.change_props:
            properties['change'] = self.change_props

        if self.sleep:
            time.sleep(self.sleep)

        # Keep received values
        self.last_event = topic
        self.last_props = properties
        self.__event.set()

    def pop_event(self):
        """
        Pops the list of events
        """
        # Clear the event for next try
        self.__event.clear()

        # Reset last event
        event, self.last_event = self.last_event, None
        return event

    def wait(self, timeout):
        """
        Waits for the event to be received
        """
        self.__event.wait(timeout)

# ------------------------------------------------------------------------------


class EventAdminTest(unittest.TestCase):
    """
    Tests the EventAdmin service
    """
    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core',
             'pelix.services.eventadmin'))
        self.framework.start()

        # Instantiate the EventAdmin component
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            self.eventadmin = ipopo.instantiate(
                pelix.services.FACTORY_EVENT_ADMIN,
                "evtadmin", {})

    def _register_handler(self, topics, evt_filter=None):
        """
        Registers an event handler

        :param topics: Event topics
        :param evt_filter: Event filter
        """
        svc = DummyEventHandler()
        context = self.framework.get_bundle_context()
        svc_reg = context.register_service(
            pelix.services.SERVICE_EVENT_HANDLER, svc,
            {pelix.services.PROP_EVENT_TOPICS: topics,
             pelix.services.PROP_EVENT_FILTER: evt_filter})
        return svc, svc_reg

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.framework = None

    def testNoHandler(self):
        """
        Tests events when no event handler is registered
        """
        self.eventadmin.send('/titi/toto', {'some.value': 42})

    def testTopics(self):
        """
        Tests the topics filtering
        """
        # Prepare a handler
        handler, _ = self._register_handler('/titi/*')

        # Assert the handler is empty
        self.assertEqual(handler.pop_event(), None)

        # Send events, with a matching topic
        for topic in ('/titi/toto', '/titi/', '/titi/42', '/titi/toto/tata'):
            self.eventadmin.send(topic)
            self.assertEqual(handler.pop_event(), topic)

        # Send events, with a non-matching topic
        for topic in ('/toto/titi/42', '/titi', '/toto/42'):
            self.eventadmin.send(topic)
            self.assertEqual(handler.pop_event(), None)

    def testFilters(self):
        """
        Tests the events filtering
        """
        # Prepare a handler
        handler, _ = self._register_handler(None, '(answer=42)')

        # Assert the handler is empty
        self.assertEqual(handler.pop_event(), None)

        # Send event, with matching properties
        for topic in ('/titi/toto', '/toto/', '/titi/42', '/titi/toto/tata'):
            for value in (42, '42', [1, 2, 42, 20], set((42, 10)),
                          (10, 21, 42)):
                evt_props = {'answer': value}
                self.eventadmin.send(topic, evt_props)

                # Check properties
                self.assertDictContainsSubset(evt_props, handler.last_props)
                self.assertIsNot(handler.last_props, evt_props)

                # Check topic
                self.assertEqual(handler.pop_event(), topic)

            # Send events, with a non-matching properties
            for value in (' 42 ', 21, [1, 2, 3], (4, 5, 6), set((7, 8, 9))):
                self.eventadmin.send(topic, {'answer': value})
                self.assertEqual(handler.pop_event(), None)

    def testPost(self):
        """
        Tests the post event method
        """
        # Prepare a handler
        handler, _ = self._register_handler('/titi/*')

        # Post a message
        topic = '/titi/toto'
        self.eventadmin.post(topic)

        # Wait a little
        handler.wait(1)
        self.assertEqual(handler.pop_event(), topic)

        # Add a handler
        handler_2, svc_reg = self._register_handler('/titi/*')

        # Let the first handler sleep
        handler.sleep = 1

        # Post a message
        self.eventadmin.post(topic)

        # Wait a little (so that the list of handlers is prepared)
        time.sleep(.2)

        # Unregister the second handler
        svc_reg.unregister()

        # Register a new one
        handler_3, _ = self._register_handler('/titi/*')

        # Wait a little: only handlers present during the 'post' must be
        # notified
        handler.wait(2)
        handler_2.wait(2)
        self.assertEqual(handler.pop_event(), topic)
        self.assertEqual(handler_2.pop_event(), topic)
        self.assertEqual(handler_3.pop_event(), None)

    def testProperties(self):
        """
        Ensures that each handler get its own copy of the properties
        """
        # Prepare handlers
        handler_1, _ = self._register_handler('/titi/*')
        handler_2, _ = self._register_handler('/titi/*')
        handler_3, _ = self._register_handler('/titi/*')

        for handler in (handler_1, handler_2, handler_3):
            handler.change_props = random.randint(1, 10)

        # Send an event
        evt_props = {'answer': 42}
        self.eventadmin.send('/titi/toto', evt_props)

        for handler in (handler_1, handler_2, handler_3):
            # Check that the original properties are kept
            self.assertDictContainsSubset(evt_props, handler.last_props)

            # Check that the handler value has been stored
            self.assertEqual(
                handler.last_props['change'], handler.change_props)
