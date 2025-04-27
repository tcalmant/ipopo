#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the shell console

:author: Thomas Calmant
"""

import random
import string
import sys
import threading
import time
import unittest

from pelix.utilities import to_bytes, to_str

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


try:
    import subprocess
except ImportError:
    # Can't run the test if we can't start another process
    pass
else:

    class ShellStandaloneTest(unittest.TestCase):
        """
        Tests the console shell when started as a script
        """

        @staticmethod
        def random_str():
            """
            Generates a random string

            :return: A random string
            """
            data = list(string.ascii_letters)
            random.shuffle(data)
            return "".join(data)

        def test_echo(self):
            """
            Tests the console shell 'echo' method
            """
            # Get shell PS1 (static method)
            import pelix.shell.core

            ps1 = pelix.shell.core._ShellService.get_ps1()

            # Start the shell process
            process = subprocess.Popen(
                [sys.executable, "-m", "pelix.shell"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            # Avoid being blocked...
            timer = threading.Timer(5, process.terminate)
            timer.start()

            # Wait for prompt
            got = ""
            while ps1 not in got:
                char = to_str(process.stdout.read(1))
                if not char:
                    if sys.version_info[0] == 2:
                        self.skipTest("Shell console test doesn't work on " "Python 2.7 with Travis")
                    else:
                        if process.poll():
                            output = to_str(process.stdout.read())
                        else:
                            output = "<no output>"

                        self.fail("Can't read from stdout (rc={})\n{}".format(process.returncode, output))
                else:
                    got += char

            # We should be good
            timer.cancel()

            try:
                # Try echoing
                data = self.random_str()

                # Write command
                process.stdin.write(to_bytes("echo {}\n".format(data)))
                process.stdin.flush()

                # Read result
                last_line = to_str(process.stdout.readline()).rstrip()
                self.assertEqual(last_line, data, "Wrong output")

                # Stop the process
                process.stdin.write(to_bytes("exit\n"))
                process.stdin.flush()

                # Wait for the process to stop (1 second max)
                delta = 0
                start = time.time()
                while delta <= 1:
                    delta = time.time() - start
                    if process.poll() is not None:
                        break
                    time.sleep(0.1)
                else:
                    self.fail("Process took too long to stop")
            finally:
                try:
                    # Kill it in any case
                    process.terminate()
                    process.wait(1)
                except OSError:
                    # Process was already stopped
                    pass

        def test_properties(self):
            """
            Tests the console shell properties parameter
            """
            # Prepare some properties
            key1 = self.random_str()[:5]
            key2 = self.random_str()[:5]

            val1 = self.random_str()
            val2 = self.random_str()

            # Start the shell process
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "pelix.shell",
                    "-D",
                    "{}={}".format(key1, val1),
                    "{}={}".format(key2, val2),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )

            try:
                # List properties, stop and get output
                output = to_str(process.communicate(to_bytes("properties"))[0])

                found = 0
                for line in output.splitlines(False):
                    if key1 in line:
                        self.assertIn(val1, line)
                        found += 1
                    elif key2 in line:
                        self.assertIn(val2, line)
                        found += 1

                self.assertEqual(found, 2, "Wrong number of properties")
            finally:
                try:
                    # Kill it in any case
                    process.terminate()
                    process.wait(1)
                except OSError:
                    # Process was already stopped
                    pass
