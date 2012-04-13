#!/usr/bin/env python
#-- Content-Encoding: UTF-8 --
"""
Tests the utility module

:author: Thomas Calmant
"""

import pelix.utilities as utilities

import threading
import time
import unittest

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

# ------------------------------------------------------------------------------

class UtilitiesTest(unittest.TestCase):
    """
    Tests for utility module methods
    """
    def setUp(self):
        """
        Sets up the test
        """
        self.lock = threading.Lock()


    def testIsLock(self):
        """
        Tests the is_lock method
        """
        valid = (threading.Lock(), threading.RLock(), threading.Semaphore(),
                 threading.Condition())
        invalid = (None, "", 1234, object())

        for test in valid:
            self.assertTrue(utilities.is_lock(test),
                            "Valid lock not detected : %s"
                            % type(test).__name__)

        for test in invalid:
            self.assertFalse(utilities.is_lock(test),
                            "Invalid lock not detected : %s"
                            % type(test).__name__)


    @utilities.SynchronizedClassMethod('lock')
    def testSynchronizedClassMethod(self):
        """
        Tests the @SynchronizedClassMethod decorator
        """
        # Just test if the lock is really locked
        self.assertFalse(self.lock.acquire(False), "Method is not locked")


    def testSynchronizedMethod(self, no_lock=False):
        """
        Tests the @Synchronized decorator, with or without a given lock

        :param no_lock: If True, create the lock, else let the decorator do it
        """
        # Thread results : ID -> starting time
        result = {}

        # Synchronization lock
        if no_lock:
            lock = None
        else:
            lock = threading.Lock()

        @utilities.Synchronized(lock)
        def sleeper(wait, sleep_id):
            """
            Sleeps during *wait* seconds
            """
            if lock is not None:
                self.assertFalse(lock.acquire(False), "Lock not locked")

            result[sleep_id] = time.time()
            time.sleep(wait)

        # Get first call time
        start = time.time()

        # Launch first waiter
        thread1 = threading.Thread(target=sleeper, args=(.5, 1))
        thread1.start()

        # Launch second waiter
        thread2 = threading.Thread(target=sleeper, args=(0, 2))
        thread2.start()

        # Get intermediate time
        interm = time.time()

        # Wait for threads
        for thread in (thread1, thread2):
            thread.join()

        # Validate conditions :
        # .. Thread 1 started after start (obvious)
        self.assertGreater(result[1], start, "Thread 1 started too soon")

        # .. Thread 2 started at least 0.5 secs after thread 1 (due to the lock)
        self.assertGreaterEqual(result[2], result[1] + .5,
                                "Thread 2 started too soon")

        # .. Thread 2 must not have blocked the main thread
        self.assertGreater(result[2], interm,
                           "Thread 2 blocked the main thread")


    def testSynchronizedMethod2(self):
        """
        Tests the @Synchronized decorator, without a given lock
        """
        self.testSynchronizedMethod(True)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
