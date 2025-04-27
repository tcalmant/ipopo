#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the shell report module

:author: Thomas Calmant
"""

import json
import os
import unittest
from io import StringIO
from typing import Any, Tuple, cast

import pelix.shell.beans as beans
from pelix.framework import BundleContext, Framework, FrameworkFactory, create_framework
from pelix.shell import ShellReport, ShellService

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class ShellReportTest(unittest.TestCase):
    """
    Tests the shell report commands
    """

    framework: Framework
    context: BundleContext
    report: ShellReport
    shell: ShellService

    def setUp(self) -> None:
        """
        Starts a framework and install the shell bundle
        """
        # Start the framework
        self.framework = create_framework(["pelix.shell.core", "pelix.shell.report"])
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Shell service
        shell_ref = self.context.get_service_reference(ShellService)
        assert shell_ref is not None
        self.shell = self.context.get_service(shell_ref)

        # Report service
        report_ref = self.context.get_service_reference(ShellReport)
        assert report_ref is not None
        self.report = self.context.get_service(report_ref)

        # Output file
        self.out_file = "report_output.js"
        if os.path.exists(self.out_file):
            os.remove(self.out_file)

    def tearDown(self) -> None:
        """
        Cleans up the framework
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()

        # Remove the output file
        if os.path.exists(self.out_file):
            os.remove(self.out_file)

        self.report = None  # type: ignore
        self.shell = None  # type: ignore
        self.context = None  # type: ignore
        self.framework = None  # type: ignore

    def _make_session(self) -> Tuple[beans.ShellSession, StringIO]:
        """
        Prepares a ShellSession object for _run_command
        """
        # String output
        str_output = StringIO()

        # Session bean
        session = beans.ShellSession(beans.IOHandler(None, str_output))
        return session, str_output

    def _run_command(self, command: str, *args: Any, **kwargs: Any) -> str:
        """
        Runs the given command and returns the output stream. A keyword
        argument 'session' can be given to use a custom ShellSession.
        """
        # Format command
        if args:
            command = command.format(*args)

        try:
            # Get the given session
            session = kwargs["session"]
            str_output = kwargs["output"]
            str_output.truncate(0)
            str_output.seek(0)
        except KeyError:
            # No session given
            str_output = StringIO()
            session = beans.ShellSession(beans.IOHandler(None, str_output))

        # Run command
        self.shell.execute(command, session)
        return cast(str, str_output.getvalue())

    def test_levels(self) -> None:
        """
        Checks if the primordial levels are correctly listed
        """
        # Check if all levels are accessible
        all_levels = set(self.report.get_levels())
        self.assertTrue(all_levels.issuperset(("minimal", "standard", "debug", "full")))

        # Assert that all levels are shown in the 'levels' command
        output = self._run_command("report.levels")
        for level in all_levels:
            self.assertIn(level, output)

    def test_bad_levels(self) -> None:
        """
        Check what happens when using bad levels
        """
        for bad_level in (12, "bad level", "'<some unknown level>'"):
            for command in ("make", "show"):
                output = self._run_command("report.{0} {1}".format(command, bad_level))
                self.assertIn("Unknown report level", output)

    def test_report_info(self) -> None:
        """
        Check if the report description is stored for every level
        """
        for level in self.report.get_levels():
            # Run the 'show' command, to get the output
            output = self._run_command("report.show {0}".format(level))
            parsed = json.loads(output)

            # Check mandatory keys
            self.assertEqual(parsed["report"]["report.levels"], [level])
            for report_key in ("time.stamp", "time.local", "time.utc"):
                self.assertIn(report_key, parsed["report"])

    def test_full_report(self) -> None:
        """
        Simplest way to test all methods: run the full report
        """
        # Run the 'show' command, to get the output
        output = self._run_command("report.show full")
        parsed = json.loads(output)

        # Check if iPOPO entries are valid
        ipopo_keys = [key for key in parsed if key.startswith("ipopo")]
        for key in ipopo_keys:
            self.assertIsNone(parsed[key])

        # Rerun with iPOPO
        self.context.install_bundle("pelix.ipopo.core").start()

        # Run the 'show' command, to get the output
        output = self._run_command("report.show full")
        parsed = json.loads(output)
        for key in ipopo_keys:
            self.assertIsNotNone(parsed[key])

    def test_write(self) -> None:
        """
        Tests the 'write' command
        """
        self.assertFalse(os.path.exists(self.out_file))

        # Run the command without any report
        output = self._run_command("report.write {0}".format(self.out_file))
        self.assertIn("No report", output)
        self.assertFalse(os.path.exists(self.out_file))

        # Make a full report
        report_content = self._run_command("report.show full")

        # Write it down
        self._run_command("report.write {0}".format(self.out_file))
        self.assertTrue(os.path.exists(self.out_file))

        # Check content
        with open(self.out_file, "r") as report_file:
            self.assertEqual(report_content, report_file.read())

    def test_clear(self) -> None:
        """
        Tests the clear command
        """
        self.assertFalse(os.path.exists(self.out_file))

        # Make a report and write it down
        self._run_command("report.make minimal")
        self._run_command("report.write {0}".format(self.out_file))

        # Assert it's there
        self.assertTrue(os.path.exists(self.out_file))
        os.remove(self.out_file)

        # Clear report
        self._run_command("report.clear")

        # Run the command without any report
        output = self._run_command("report.write {0}".format(self.out_file))
        self.assertIn("No report", output)
        self.assertFalse(os.path.exists(self.out_file))

    def test_show_last(self) -> None:
        """
        Checks that the "show" command prints the previous report when given no
        argument
        """
        # Clear report (just in case)
        self._run_command("report.clear")

        # First try: no report to show
        output = self._run_command("report.show")
        self.assertIn("No report", output)

        # Make a report
        output = self._run_command("report.show full")

        # Next call without argument must have the exact same output
        output_2 = self._run_command("report.show")
        self.assertEqual(output, output_2)

    def test_default_report(self) -> None:
        """
        Checks that the 'full' report is generated by default
        """
        # Clear report (just in case)
        self._run_command("report.clear")

        # Make the default report
        self._run_command("report.make")

        # Show it
        output = self._run_command("report.show")

        # Check its level
        parsed = json.loads(output)
        self.assertEqual(parsed["report"]["report.levels"], ["full"])
