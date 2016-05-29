#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the log service

:author: Thomas Calmant
"""

# Pelix
import pelix.framework
import pelix.misc
from pelix.ipopo.constants import use_ipopo
from pelix.misc.log import LOG_DEBUG, LOG_INFO, LOG_WARNING, LOG_ERROR

# Standard library
import logging
import sys
import time

try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"


# ------------------------------------------------------------------------------


class LogServiceTest(unittest.TestCase):
    """
    Tests the log service
    """

    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core', 'pelix.misc.log'))
        self.framework.start()

        # Get the service
        self.service = self._get_service()

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.service = None
        self.framework = None

    def _get_service(self):
        """
        Returns the log service
        """
        context = self.framework.get_bundle_context()
        ref = context.get_service_reference(pelix.misc.LOG_SERVICE)
        return context.get_service(ref)

    def test_log(self):
        """
        Basic tests for the log service
        """
        # Try to log at various log levels
        prev_logs = []
        for level, osgi_level in (
                (logging.DEBUG, LOG_DEBUG), (logging.INFO, LOG_INFO),
                (logging.WARNING, LOG_WARNING), (logging.ERROR, LOG_ERROR),
                (logging.CRITICAL, LOG_ERROR)):
            # Log at the expected level
            self.service.log(level, logging.getLevelName(level))

            # Get new logs
            new_logs = self.service.get_log()
            latest = new_logs[-1]

            # Check time stamp
            self.assertLessEqual(
                latest.time, time.time() + .5, "Log in future")
            self.assertGreaterEqual(
                latest.time, time.time() - 10, "Log too far in past")

            # Check stored info
            self.assertEqual(latest.level, level, "Wrong log level")
            self.assertEqual(latest.osgi_level, osgi_level,
                             "Wrong OSGi log level")
            self.assertEqual(latest.message, logging.getLevelName(level),
                             "Wrong log message")
            self.assertIsNone(latest.bundle, "Unexpected bundle info")
            self.assertIsNone(latest.exception, "Unexpected exception data")
            self.assertIsNone(latest.reference, "Unexpected reference data")

            # Compare list (not tuples)
            new_logs = list(new_logs)
            self.assertListEqual(new_logs, prev_logs + [latest],
                                 "Logs list changed")
            prev_logs = new_logs

    def test_logging(self):
        """
        Tests if logs made with the logging are handled
        """
        # Debug logs aren't taken into account
        logging.debug("Some log message at %s",
                      logging.getLevelName(logging.DEBUG))
        self.assertListEqual(
            list(self.service.get_log()), [], "Debug message logged")

        # Try to log at various log levels
        prev_logs = []
        for level, osgi_level in (
                (logging.INFO, LOG_INFO), (logging.WARNING, LOG_WARNING),
                (logging.ERROR, LOG_ERROR), (logging.CRITICAL, LOG_ERROR)):
            # Log at the expected level
            logging.log(level, "Some log message at %s",
                        logging.getLevelName(level))

            # Get new logs
            new_logs = self.service.get_log()
            latest = new_logs[-1]

            # Check time stamp
            self.assertLessEqual(
                latest.time, time.time() + .5, "Log in future")
            self.assertGreaterEqual(
                latest.time, time.time() - 10, "Log too far in past")

            # Check stored info
            self.assertEqual(latest.level, level, "Wrong log level")
            self.assertEqual(latest.osgi_level, osgi_level,
                             "Wrong OSGi log level")
            self.assertIn(logging.getLevelName(level), latest.message,
                          "Wrong log message")
            self.assertIsNone(latest.bundle, "Unexpected bundle info")
            self.assertIsNone(latest.exception, "Unexpected exception data")
            self.assertIsNone(latest.reference, "Unexpected reference data")

            # Check string representation
            self.assertIn(logging.getLevelName(level), str(latest))

            # Compare list (not tuples)
            new_logs = list(new_logs)
            self.assertListEqual(new_logs, prev_logs + [latest],
                                 "Logs list changed")
            prev_logs = new_logs

    def test_logging_filter_level(self):
        """
        Tests the change of filter for the logging handler
        """
        for filter_level in (logging.DEBUG, logging.INFO, logging.WARNING,
                             logging.ERROR):
            for int_level in (True, False):
                # Restart the framework
                self.tearDown()
                self.setUp()

                # Change the framework property and reload the log service
                if int_level:
                    self.framework.add_property(
                        pelix.misc.PROPERTY_LOG_LEVEL, filter_level)
                else:
                    self.framework.add_property(
                        pelix.misc.PROPERTY_LOG_LEVEL,
                        logging.getLevelName(filter_level))

                self.framework.get_bundle_by_name("pelix.misc.log").update()
                self.service = self._get_service()

                # Log for each level
                for level in (logging.DEBUG, logging.INFO, logging.WARNING,
                              logging.ERROR):
                    # Log something
                    logging.log(level, "Some log at %s",
                                logging.getLevelName(level))

                    try:
                        latest = self.service.get_log()[-1]
                        if level >= filter_level:
                            self.assertIn(logging.getLevelName(level),
                                          latest.message)
                    except IndexError:
                        if level >= filter_level:
                            self.fail("Missing a log matching the filter")

        # Try with invalid levels, default level is INFO
        filter_level = logging.INFO
        for invalid in (None, "", "deb", "ug", "foobar", {1: 2}, [1, 2]):
            # Restart the framework
            self.tearDown()
            self.setUp()

            # Change the framework property and reload the log service
            self.framework.add_property(pelix.misc.PROPERTY_LOG_LEVEL, invalid)

            self.framework.get_bundle_by_name("pelix.misc.log").update()
            self.service = self._get_service()

            # Log for each level
            for level in (logging.DEBUG, logging.INFO, logging.WARNING,
                          logging.ERROR):
                # Log something
                logging.log(level, "Some log at %s",
                            logging.getLevelName(level))

                try:
                    latest = self.service.get_log()[-1]
                    if level >= filter_level:
                        self.assertIn(logging.getLevelName(level),
                                      latest.message)
                except IndexError:
                    if level >= filter_level:
                        self.fail("Missing a log matching the filter")

    def test_listener(self):
        """
        Tests when log listeners are notified
        """
        entries = []

        # Prepare the listener
        class Listener:
            @staticmethod
            def logged(entry):
                entries.append(entry)

        listener = Listener()

        # Register it twice
        self.service.add_log_listener(listener)
        self.service.add_log_listener(listener)

        # Also, check with a null log listener
        self.service.add_log_listener(None)

        # Log something
        self.service.log(logging.WARNING, "Some log")

        # Get the log entry through the service
        latest = self.service.get_log()[-1]

        # Compare with what we stored
        self.assertListEqual(entries, [latest], "Bad content for the listener")

        # Clean up
        del entries[:]

        # Unregister the listener once
        self.service.remove_log_listener(listener)

        # Log something
        self.service.log(logging.WARNING, "Some log")

        # Nothing must have been logged
        self.assertListEqual(entries, [], "Something has been logged")

        # Nothing must happen if we unregister the listener twice
        self.service.remove_log_listener(listener)
        self.service.remove_log_listener(None)

    def test_bad_listener(self):
        """
        Tests a listener raising an exception
        """

        # Prepare the listener
        class GoodListener:
            def __init__(self):
                self.entries = []

            def logged(self, entry):
                self.entries.append(entry)
                raise OSError("Something went wrong")

        class BadListener(GoodListener):
            def logged(self, entry):
                super(BadListener, self).logged(entry)
                raise OSError("Something went wrong")

        good1 = GoodListener()
        bad = GoodListener()
        good2 = GoodListener()

        # Register listeners
        self.service.add_log_listener(good1)
        self.service.add_log_listener(bad)
        self.service.add_log_listener(good2)

        # Log something
        self.service.log(logging.WARNING, "Some log")

        # Get the log entry through the service
        latest = self.service.get_log()[-1]

        self.assertEqual(latest.level, logging.WARNING)
        for listener in (good1, bad, good2):
            self.assertIs(latest, listener.entries[-1], "Entry not kept")

    def test_reference(self):
        """
        Tests the service reference handling in logs
        """
        # Register a service, with the Framework context
        context = self.framework.get_bundle_context()
        svc_reg = context.register_service("test.svc", object(), {})
        svc_ref = svc_reg.get_reference()

        # Log something
        self.service.log(logging.WARNING, "Some text", reference=svc_ref)

        # Check what has been stored
        latest = self.service.get_log()[-1]
        self.assertIs(latest.reference, svc_ref, "Wrong service reference")
        self.assertIs(latest.bundle, self.framework, "Wrong bundle found")

        # Log with wrong references
        for wrong_ref in (None, object(), svc_reg):
            self.service.log(logging.WARNING, "Some text", reference=wrong_ref)

            latest = self.service.get_log()[-1]
            self.assertIsNone(latest.reference, "Non-None service reference")
            self.assertIsNone(latest.bundle, "Non-None bundle found")

    def test_bundle(self):
        """
        Tests the detection of the calling bundle
        """
        # Install a test bundle
        context = self.framework.get_bundle_context()
        bnd = context.install_bundle("tests.misc.log_bundle")
        module = bnd.get_module()
        bnd.start()

        # Instantiate a test component
        with use_ipopo(context) as ipopo:
            comp = ipopo.instantiate(module.SIMPLE_FACTORY, "test.log", {})

        # Log something
        comp.log(logging.WARNING, "Some log")

        # Check the bundle
        latest = self.service.get_log()[-1]
        self.assertIs(latest.bundle, bnd, "Wrong bundle found")

        # Check if the bundle in the string representation
        self.assertIn(bnd.get_symbolic_name(), str(latest))

        # Remove the name of the module
        comp.remove_name()

        # Log something
        comp.log(logging.WARNING, "Some log")

        # Check the bundle
        latest = self.service.get_log()[-1]
        self.assertIsNone(latest.bundle, "Wrong bundle found")

    def test_exception(self):
        """
        Tests the exception information
        """
        try:
            raise ValueError("Some error")
        except ValueError:
            self.service.log(logging.ERROR, "Error !", sys.exc_info())

        latest = self.service.get_log()[-1]
        self.assertTrue(isinstance(latest.exception, str),
                        "Exception info must be a string")
        self.assertIn(__file__, latest.exception, "Incomplete exception info")

        # Check if the exception in the string representation
        self.assertIn(latest.exception, str(latest))

        # Check invalid exception info
        for invalid in ([], [1, 2], (4, 5, 6)):
            self.service.log(logging.ERROR, "Error !", invalid)
            latest = self.service.get_log()[-1]
            self.assertEqual(latest.exception, '<Invalid exc_info>')
