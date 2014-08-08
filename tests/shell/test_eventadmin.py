#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the EventAdmin shell commands

:author: Thomas Calmant
"""

# Pelix
from pelix.ipopo.constants import use_ipopo
import pelix.framework
import pelix.services
import pelix.shell

# Standard library
import threading
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

    def handle_event(self, topic, properties):
        """
        Handles an event received from EventAdmin
        """
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


class EventAdminShellTest(unittest.TestCase):

    """
    Tests the EventAdmin shell commands
    """

    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core',
             'pelix.shell.core',
             'pelix.services.eventadmin',
             'pelix.shell.eventadmin'))
        self.framework.start()

        # Get the Shell service
        context = self.framework.get_bundle_context()
        svc_ref = context.get_service_reference(pelix.shell.SERVICE_SHELL)
        self.shell = context.get_service(svc_ref)

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

    def _run_command(self, command, *args):
        """
        Runs the given shell command
        """
        # Format command
        if args:
            command = command.format(*args)

        # Run command
        self.shell.execute(command)

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.framework = None

    def testTopics(self):
        """
        Tests sending topics
        """
        # Prepare a handler
        handler, _ = self._register_handler('/titi/*')

        # Send events, with a matching topic
        for topic in ('/titi/toto', '/titi/', '/titi/42', '/titi/toto/tata'):
            self._run_command("send {0}", topic)
            self.assertEqual(handler.pop_event(), topic)

        # Send events, with a non-matching topic
        for topic in ('/toto/titi/42', '/titi', '/toto/42'):
            self._run_command("send {0}", topic)
            self.assertEqual(handler.pop_event(), None)

    def testFilters(self):
        """
        Tests the sending events with properties
        """
        # Prepare a handler
        key = "some.key"
        handler, _ = self._register_handler(None, '({0}=42)'.format(key))

        # Assert the handler is empty
        self.assertEqual(handler.pop_event(), None)

        # Send event, with matching properties
        for topic in ('/titi/toto', '/toto/', '/titi/42', '/titi/toto/tata'):
            value = 42
            evt_props = {key: value}
            self._run_command("send {0} {1}=42", topic, key, value)

            # Check properties
            self.assertIn(key, handler.last_props)
            self.assertEqual(str(handler.last_props[key]), str(value))
            self.assertIsNot(handler.last_props, evt_props)

            # Check topic
            self.assertEqual(handler.pop_event(), topic)

            # Send events, with a non-matching properties
            self._run_command("send {0} {1}=21", topic, key)
            self.assertEqual(handler.pop_event(), None)

    def testPost(self):
        """
        Tests the post event method
        """
        # Prepare a handler
        handler, _ = self._register_handler('/titi/*')

        # Post a message
        topic = '/titi/toto'
        self._run_command("post {0}", topic)

        # Wait a little
        handler.wait(1)
        self.assertEqual(handler.pop_event(), topic)
