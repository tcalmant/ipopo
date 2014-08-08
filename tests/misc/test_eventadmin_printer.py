#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the EventAdmin printer

:author: Thomas Calmant
"""

# Pelix
from pelix.ipopo.constants import use_ipopo
import pelix.framework
import pelix.misc
import pelix.services

# Standard library
import logging

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class EventAdminPrinterTest(unittest.TestCase):
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
             'pelix.services.eventadmin',
             'pelix.misc.eventadmin_printer'))
        self.framework.start()

        # Add a log handler
        self.log_io = StringIO()
        self._log_handler = logging.StreamHandler(self.log_io)
        logger = logging.getLogger('pelix.misc.eventadmin_printer')
        logger.setLevel(logging.INFO)
        logger.addHandler(self._log_handler)

        # Instantiate the EventAdmin component
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            self.eventadmin = ipopo.instantiate(
                pelix.services.FACTORY_EVENT_ADMIN,
                "evtadmin", {})

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Remove the log handler
        logger = logging.getLogger('pelix.misc.eventadmin_printer')
        logger.removeHandler(self._log_handler)

        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.framework = None

    def testPrinter(self):
        """
        Tests the topics filtering
        """
        # Start the printer
        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            ipopo.instantiate(pelix.misc.FACTORY_EVENT_ADMIN_PRINTER,
                              "evtPrinter",
                              {pelix.services.PROP_EVENT_TOPICS: '/titi/*',
                               'evt.log': True, 'evt.print': True})

        # Send events, with a matching topic
        for topic in ('/titi/toto', '/titi/', '/titi/toto/tata'):
            # Clear the log I/O
            self.log_io.truncate(0)

            # Send the event
            self.eventadmin.send(topic)

            # Check the log
            output = self.log_io.getvalue()
            self.assertIn(topic, output)

        # Send events, with a non-matching topic
        for topic in ('/toto/titi/42', '/titi', '/toto/42'):
            # Clear the log I/O
            self.log_io.truncate(0)

            # Send the event
            self.eventadmin.send(topic)

            # Check the log
            output = self.log_io.getvalue()
            self.assertNotIn(topic, output)

    def testParseBoolean(self):
        """
        Tests the parse boolean method of the printer module
        """
        # Get the module
        bundle = self.framework.get_bundle_by_name(
            'pelix.misc.eventadmin_printer')
        module = bundle.get_module()

        # Test false values
        for not_true in (None, "None", "none", False, "False", "fAlse", "0",
                         0, "no", "NO"):
            self.assertFalse(module._parse_boolean(not_true))

        # Test true values
        for not_false in (True, 1, '1', 'true', 'yes'):
            self.assertTrue(module._parse_boolean(not_false))
