#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the utility module

:author: Thomas Calmant
"""

import pelix.utilities as utilities

import random
import sys
import threading
import time

try:
    import unittest2 as unittest

except ImportError:
    import unittest
    import tests
    tests.inject_unittest_methods()

# ------------------------------------------------------------------------------

__version__ = (1, 1, 0)

# ------------------------------------------------------------------------------

class SynchronizationUtilitiesTest(unittest.TestCase):
    """
    Tests for utility module synchronization methods
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


    def testNoLockException(self):
        """
        Verifies that @SynchronizedClassMethod raises an error when no lock
        is given
        """
        try:
            @utilities.SynchronizedClassMethod()
            def dummy():
                pass

            self.fail("@SynchronizedClassMethod() should raise a ValueError")

        except ValueError:
            # We must be there to succeed
            pass

        try:
            @utilities.SynchronizedClassMethod(None)
            def dummy():
                pass

            self.fail("@SynchronizedClassMethod(None) should raise a ValueError")

        except ValueError:
            # We must be there to succeed
            pass


    def testNoneLockException(self):
        """
        Verifies that @SynchronizedClassMethod raises an error when a None lock
        is used for locking
        """
        self.lock = None
        self.assertRaises(AttributeError, self.testSynchronizedClassMethod)


# ------------------------------------------------------------------------------

class UtilitiesTest(unittest.TestCase):
    """
    Tests for utility module methods
    """
    def testReadOnlyProperty(self):
        """
        Tests the read only property generator
        """
        value_1 = 42
        value_2 = random.random()

        # Prepare the class members
        class Dummy(object):
            inside = utilities.read_only_property(value_1)

        Dummy.outside = utilities.read_only_property(value_2)

        # Work on an instance
        instance = Dummy()

        # Test read values
        self.assertEqual(instance.inside, value_1,
                         "Invalid initial value (in)")
        self.assertEqual(instance.outside, value_2,
                         "Invalid initial value (out)")

        # Test set values
        try:
            instance.inside = random.random()
            self.fail("Instance value (in) must not be modified.")

        except AttributeError:
            # We must be there
            pass

        try:
            instance.outside = random.random()
            self.fail("Instance value (out) must not be modified.")

        except AttributeError:
            # We must be there
            pass

        # Test final values (just in case)
        self.assertEqual(instance.inside, value_1,
                         "Invalid final value (in)")
        self.assertEqual(instance.outside, value_2,
                         "Invalid final value (out)")


    def testRemoveAllOccurrences(self):
        """
        Tests the remove_all_occurrences() method
        """
        try:
            # Must not raise an exception
            utilities.remove_all_occurrences(None, 12)

        except:
            self.fail("remove_all_occurrences(None) must not raise an exception")

        min_value = -1
        max_value = 4

        # Create a random list
        list_org = []
        for i in range(0, random.randint(10, 20)):
            list_org.append(random.randint(min_value, max_value))

        # Create a copy
        list_copy = list_org[:]

        # Pick a random element
        for i in range(min_value, max_value + 1):
            # Get the original count
            count_base = list_org.count(i)
            self.assertEqual(list_copy.count(i), count_base,
                             "Copies doesn't have the same count of values")

            # Get the current length of the copy
            len_base = len(list_copy)

            # Remove the element
            utilities.remove_all_occurrences(list_copy, i)

            # The new count must be 0
            self.assertEqual(list_copy.count(i), 0, "Some references remain")

            # The new length must be len_base - count_base
            self.assertEqual(len(list_copy), len_base - count_base,
                             "Incorrect new list size")


    def testIsString(self):
        """
        Tests the is_string() method
        """
        valid = ["", "aaa", str(42)]
        invalid = [42, None, [], {}, tuple()]

        if sys.version_info[0] >= 3:
            invalid.extend((b"", b"aaa"))

        else:
            valid.extend((unicode(""), unicode("aaa"), unicode(42)))
            invalid.extend((42, None, [], {}))

        for value in valid:
            self.assertTrue(utilities.is_string(value),
                            "'%s' is a string".format(value))

        for value in invalid:
            self.assertFalse(utilities.is_string(value),
                             "'%s' is not a string".format(value))


    def testAddRemoveListener(self):
        """
        Tests add/remove listener methods
        """
        registry = []
        values = (42, "test", (1, 2, 3))

        # None value
        self.assertFalse(utilities.add_listener(registry, None),
                         "None value must not be accepted")

        self.assertFalse(utilities.remove_listener(registry, None),
                         "None value must not be accepted")

        for value in values:
            # Non-present value
            self.assertFalse(utilities.remove_listener(registry, value),
                             "Non-present value removed")

            # Add value
            self.assertTrue(utilities.add_listener(registry, value),
                            "Value has been refused")
            self.assertEqual(registry.count(value), 1,
                             "Value not inserted in registry")

            # Second add
            self.assertFalse(utilities.add_listener(registry, value),
                             "Value has been added twice")
            self.assertEqual(registry.count(value), 1,
                             "Value has been added twice")

        for value in values:
            # Remove value
            self.assertTrue(utilities.remove_listener(registry, value),
                            "Value has not been removed")
            # Ensure the value has been remove
            self.assertEqual(registry.count(value), 0,
                             "Value has not been removed")

            # Second removal
            self.assertFalse(utilities.remove_listener(registry, value),
                             "Value has been removed twice")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
