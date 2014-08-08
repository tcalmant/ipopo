#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the thread pool module

:author: Thomas Calmant
"""

__version__ = (1, 0, 0)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Tested module
import pelix.threadpool as threadpool

# Standard library
import threading
import time

# Tests
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------


def _slow_call(wait, result):
    """
    Method that returns after the given time (in seconds)
    """
    time.sleep(wait)
    return result

# ------------------------------------------------------------------------------


class FutureTest(unittest.TestCase):
    """
    Tests the Future utility class
    """
    def _simple_call(self, pos1, pos2, result):
        """
        Method that returns the 3 given arguments in a tuple
        """
        return (pos1, pos2, result)

    def _raise_call(self):
        """
        Method that raises a ValueError exception
        """
        raise ValueError("Buggy method")

    def testSimple(self):
        """
        Simple, error-less execution
        """
        # Create the future object
        future = threadpool.FutureResult()

        # Assert we have no result yet
        self.assertFalse(future.done(), "Execution flag up")
        self.assertRaises(OSError, future.result, 0)

        # Execute the method
        result1, result2, result3 = range(3)
        future.execute(self._simple_call,
                       (result1, result2), {"result": result3})

        # Assert it is done
        self.assertTrue(future.done(), "Execution flag not updated")
        self.assertEqual(future.result(), (result1, result2, result3),
                         "Invalid result")

    def testRaise(self):
        """
        Tests the traversal of an exception
        """
        # Let the method raise its exception
        future = threadpool.FutureResult()
        self.assertRaises(ValueError, future.execute,
                          self._raise_call, None, None)

        # The call must be considered as done
        self.assertTrue(future.done(), "Execution flag not updated")
        self.assertIsNone(future.result(), "A result has been set")

    def testTimeout(self):
        """
        Checks the timeout exit of result()
        """
        future = threadpool.FutureResult()
        result = object()

        # Call the method in a new thread
        thread = threading.Thread(target=future.execute,
                                  args=(_slow_call, (1, result), None))
        thread.daemon = True
        thread.start()

        # Check without wait
        self.assertRaises(OSError, future.result, 0)
        self.assertFalse(future.done(), "Execution flag up")

        # Check waiting a little
        self.assertRaises(OSError, future.result, .2)
        self.assertFalse(future.done(), "Execution flag up")

        # Check waiting longer
        self.assertIs(future.result(2), result, "Invalid result")
        self.assertTrue(future.done(), "Execution flag not updated")

# ------------------------------------------------------------------------------


class ThreadPoolTest(unittest.TestCase):
    """
    Tests the thread pool utility class
    """
    def setUp(self):
        """
        Sets up the test
        """
        # Pool member
        self.pool = None

    def tearDown(self):
        """
        Cleans up the test
        """
        # Clear pool, if any
        if self.pool is not None:
            self.pool.stop()

    def testInitParameters(self):
        """
        Tests the validity checks on thread pool creation
        """
        # Invalid number of threads
        for invalid_nb in (0, -1, 5.1):
            self.assertRaises(ValueError, threadpool.ThreadPool, invalid_nb)

    def testPreStartEnqueue(self):
        """
        Tests the late start of the poll
        """
        self.pool = threadpool.ThreadPool(1)
        result = object()

        # Add the call to the queue
        future = self.pool.enqueue(_slow_call, 0, result)
        self.assertFalse(future.done(), "Execution flag up")

        # Start the pool
        self.pool.start()

        # Wait for the result
        self.assertIs(future.result(1), result, "Invalid result")
        self.assertTrue(future.done(), "Execution flag not updated")

    def testPreRestartEnqueue(self):
        """
        Tests the restart of the poll
        """
        self.pool = threadpool.ThreadPool(1)
        result = object()

        # Start the pool
        self.pool.start()

        # Add the call to the queue
        future = self.pool.enqueue(_slow_call, 0, result)

        # Wait for the result
        self.assertIs(future.result(1), result, "Invalid result")
        self.assertTrue(future.done(), "Execution flag not updated")

        # Stop the pool
        self.pool.stop()

        # Add the call to the queue
        future = self.pool.enqueue(_slow_call, 0, result)
        self.assertFalse(future.done(), "Execution flag up")

        # Start the pool
        self.pool.start()

        # Wait for the result
        self.assertIs(future.result(1), result, "Invalid result")
        self.assertTrue(future.done(), "Execution flag not updated")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
