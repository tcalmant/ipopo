#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the log shell commands

:author: Thomas Calmant
"""

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

# Pelix
import pelix.framework
import pelix.misc
import pelix.shell
import pelix.shell.beans as beans

# ------------------------------------------------------------------------------

__version_info__ = (1, 0, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class LogShellTest(unittest.TestCase):
    """
    Tests the log shell commands
    """
    def setUp(self):
        """
        Prepares a framework and a registers a service to export
        """
        # Create the framework
        self.framework = pelix.framework.create_framework(
            ('pelix.ipopo.core', 'pelix.shell.core',
             'pelix.misc.log', 'pelix.shell.log'))
        self.framework.start()

        # Get the Shell service
        context = self.framework.get_bundle_context()
        svc_ref = context.get_service_reference(pelix.shell.SERVICE_SHELL)
        self.shell = context.get_service(svc_ref)

        # Get the log reader service
        svc_ref = context.get_service_reference(pelix.misc.LOG_READER_SERVICE)
        self.reader = context.get_service(svc_ref)

    def tearDown(self):
        """
        Cleans up for next test
        """
        # Stop the framework
        pelix.framework.FrameworkFactory.delete_framework(self.framework)
        self.framework = None

    def _make_session(self):
        """
        Prepares a ShellSession object for _run_command
        """
        # String output
        str_output = StringIO()

        # Session bean
        session = beans.ShellSession(beans.IOHandler(None, str_output))
        return session, str_output

    def _run_command(self, command, *args, **kwargs):
        """
        Runs the given command and returns the output stream. A keyword
        argument 'session' can be given to use a custom ShellSession.
        """
        # Format command
        if args:
            command = command.format(*args)

        try:
            # Get the given session
            session = kwargs['session']
            str_output = kwargs['output']
            str_output.truncate(0)
            str_output.seek(0)
        except KeyError:
            # No session given
            str_output = StringIO()
            session = beans.ShellSession(beans.IOHandler(None, str_output))

        # Run command
        self.shell.execute(command, session)
        return str_output.getvalue()

    def test_log_levels(self):
        """
        Tests the log commands
        """
        for cmd, level in (("debug", logging.DEBUG), ("info", logging.INFO),
                           ("warn", logging.WARNING),
                           ("warning", logging.WARNING),
                           ("error", logging.ERROR)):
            self._run_command("log.{0} some text".format(cmd))

            latest = self.reader.get_log()[-1]
            self.assertEqual(latest.level, level, "Wrong log level")
            self.assertEqual(latest.message, "some text")

        # Remove the log service
        self.framework.get_bundle_by_name("pelix.misc.log").stop()

        # Check if the commands work
        for cmd in ("debug", "info", "warn", "warning", "error"):
            output = self._run_command("log.{0} some text".format(cmd))
            self.assertIn("No LogService".lower(), output.lower())
            self.assertIn("available", output.lower())

    def test_log_print(self):
        """
        Tests the "log" method
        """
        for cmd in ("debug", "info", "warn", "warning", "error"):
            # Log something
            self._run_command("log.{0} some text for {0}".format(cmd))

        # Get all logs
        logs = self.reader.get_log()

        # Basic filter: >= warning
        output = self._run_command("log.log")
        for entry in logs:
            if entry.level >= logging.WARNING:
                self.assertIn(entry.message, output)

        # Filter given
        for level in (logging.DEBUG, logging.INFO,
                      logging.WARNING, logging.ERROR):
            output = self._run_command(
                "log.log {0}".format(logging.getLevelName(level)))
            for entry in logs:
                if entry.level >= level:
                    self.assertIn(entry.message, output)

        # Test length filter, even when going beyond the log size
        for level in (logging.DEBUG, logging.INFO,
                      logging.WARNING, logging.ERROR):
            for i in range(1, len(logs) + 10):
                output = self._run_command(
                    "log.log {0} {1}".format(logging.getLevelName(level), i))
                for entry in logs[-i:]:
                    if entry.level >= level:
                        self.assertIn(entry.message, output)
