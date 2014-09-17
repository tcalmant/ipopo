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
import pelix.utilities as utilities

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
        return pos1, pos2, result

    def _raise_call(self):
        """
        Method that raises a ValueError exception
        """
        raise ValueError("Buggy method")

    def _callback(self, data, exception, event):
        """
        Sets up an EventData
        """
        if exception is not None:
            event.raise_exception(exception)
        else:
            event.set(data)

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

        try:
            future.execute(self._raise_call, None, None)
        except ValueError as ex:
            exception = ex
        else:
            self.fail("Execute didn't propagate the error")

        # The call must be considered as done
        self.assertTrue(future.done(), "Execution flag not updated")
        try:
            future.result()
        except ValueError as ex:
            self.assertIs(ex, exception, "Result exception changed")
        else:
            self.fail("Result didn't propagate the error")

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

    def testCallback(self):
        """
        Tests the callback method
        """
        # Set the callback before calling the method
        flag = utilities.EventData()
        future = threadpool.FutureResult()
        future.set_callback(self._callback, flag)
        self.assertFalse(flag.is_set(), "Flag already set")

        # Execute
        args = (1, 2, 3)
        future.execute(self._simple_call, args, None)

        # Check event content
        self.assertTrue(flag.is_set(), "Callback method not called")
        self.assertIsNone(flag.exception, "Exception set")
        self.assertEqual(flag.data, args, "Data not set")

        # ... Re-set the callback (should be re-called)
        flag.clear()
        self.assertFalse(flag.is_set(), "Flag already set")
        future.set_callback(self._callback, flag)

        # Check event content
        self.assertTrue(flag.is_set(), "Callback method not called")
        self.assertIsNone(flag.exception, "Exception set")
        self.assertEqual(flag.data, args, "Data not set")

    def testCallbackException(self):
        """
        Tests the callback method in case of exception
        """
        # Set the callback before calling the method
        flag = utilities.EventData()
        future = threadpool.FutureResult()
        future.set_callback(self._callback, flag)
        self.assertFalse(flag.is_set(), "Flag already set")

        # Execute
        try:
            future.execute(self._raise_call, None, None)
        except Exception as ex:
            # Store it
            exception = ex
        else:
            self.fail("Exception wasn't propagated")

        # Check event content
        self.assertTrue(flag.is_set(), "Callback method not called")
        self.assertIs(flag.exception, exception, "Exception not set")
        self.assertIsNone(flag.data, "Data set")

        # ... Re-set the callback (should be re-called)
        flag.clear()
        self.assertFalse(flag.is_set(), "Flag already set")
        future.set_callback(self._callback, flag)

        # Check event content
        self.assertTrue(flag.is_set(), "Callback method not called")
        self.assertIs(flag.exception, exception, "Exception not set")
        self.assertIsNone(flag.data, "Data set")

    def testBadCallback(self):
        """
        Tests behavior on callback error
        """
        future = threadpool.FutureResult()
        args = (1, 2, 3)
        flag = utilities.EventData()

        def dummy():
            """
            Callback without arguments
            """
            flag.set()

        # Bad number of arguments: no exception must be raised
        future.set_callback(dummy)
        future.execute(self._simple_call, args, None)
        self.assertFalse(flag.is_set(), "Flag shouldn't be set...")

        def raising(data, exception, ex):
            """
            Callback raising an exception
            """
            flag.set()
            raise ex

        exception = ValueError("Dummy error")
        future.set_callback(raising, exception)
        self.assertTrue(flag.is_set(), "Callback not called")

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
        for invalid_nb in (0, -1, 0.1):
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
