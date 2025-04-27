#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the utility module

:author: Thomas Calmant
"""

# Same version as the tested bundle
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

import random
import threading
import time
import unittest
from typing import Any, Dict, List

import pelix.constants
import pelix.framework
import pelix.utilities as utilities
from tests.interfaces import IEchoService

# ------------------------------------------------------------------------------


class SynchronizationUtilitiesTest(unittest.TestCase):
    """
    Tests for utility module synchronization methods
    """

    lock: threading.Lock

    def setUp(self) -> None:
        """
        Sets up the test
        """
        self.lock = threading.Lock()

    def testIsLock(self) -> None:
        """
        Tests the is_lock method
        """
        valid = (threading.Lock(), threading.RLock(), threading.Semaphore(), threading.Condition())
        invalid = (None, "", 1234, object())

        for test in valid:
            self.assertTrue(
                utilities.is_lock(test), "Valid lock not detected: {0}".format(type(test).__name__)
            )

        for test in invalid:
            self.assertFalse(
                utilities.is_lock(test), "Invalid lock not detected: {0}".format(type(test).__name__)
            )

    @utilities.SynchronizedClassMethod("lock")
    def testSynchronizedClassMethod(self) -> None:
        """
        Tests the @SynchronizedClassMethod decorator
        """
        # Just test if the lock is really locked
        self.assertFalse(self.lock.acquire(False), "Method is not locked")

    def testSynchronizedMethod(self, no_lock: bool = False) -> None:
        """
        Tests the @Synchronized decorator, with or without a given lock

        :param no_lock: If True, create the lock, else let the decorator do it
        """
        # Thread results: ID -> starting time
        result: Dict[int, float] = {}

        # Synchronization lock
        if no_lock:
            lock = None
        else:
            lock = threading.Lock()

        @utilities.Synchronized(lock)
        def sleeper(wait: float, sleep_id: int) -> None:
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
        thread1 = threading.Thread(target=sleeper, args=(0.5, 1))
        thread1.start()

        # Wait a little before starting 2nd thread: on Windows, thread 2
        # can start before thread 1
        time.sleep(0.1)

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
        self.assertGreaterEqual(result[1], start, "Thread 1 started too soon")

        # .. Thread 2 started at least 0.4 secs after thread 1
        # (due to the lock)
        # (0.4 instead of 0.5: some systems are not that precise)
        self.assertGreaterEqual(
            result[2], result[1] + 0.4, "Thread 2 started too soon (after {0}s)".format(result[2] - result[1])
        )

        # .. Thread 2 must not have blocked the main thread
        self.assertGreater(result[2], interm, "Thread 2 blocked the main thread")

    def testSynchronizedMethod2(self) -> None:
        """
        Tests the @Synchronized decorator, without a given lock
        """
        self.testSynchronizedMethod(True)

    def testNoLockException(self) -> None:
        """
        Verifies that @SynchronizedClassMethod raises an error when no lock
        is given
        """
        try:

            @utilities.SynchronizedClassMethod()
            def dummy() -> None:
                pass

            self.fail("@SynchronizedClassMethod() should raise a ValueError")
        except ValueError:
            # We must be there to succeed
            pass

        try:

            @utilities.SynchronizedClassMethod(None)  # type: ignore
            def dummy() -> None:
                pass

            self.fail("@SynchronizedClassMethod(None) should raise a " "ValueError")
        except ValueError:
            # We must be there to succeed
            pass

    def testNoneLockException(self) -> None:
        """
        Verifies that @SynchronizedClassMethod raises an error when a None lock
        is used for locking
        """
        self.lock = None  # type: ignore
        self.assertRaises(AttributeError, self.testSynchronizedClassMethod)


# ------------------------------------------------------------------------------


class UtilitiesTest(unittest.TestCase):
    """
    Tests for utility module methods
    """

    def testReadOnlyProperty(self) -> None:
        """
        Tests the read only property generator
        """
        value_1 = 42
        value_2 = random.random()

        # Prepare the class members
        class Dummy(object):
            inside = utilities.read_only_property(value_1)

        Dummy.outside = utilities.read_only_property(value_2)  # type: ignore

        # Work on an instance
        instance = Dummy()

        # Test read values
        self.assertEqual(instance.inside, value_1, "Invalid initial value (in)")
        self.assertEqual(instance.outside, value_2, "Invalid initial value (out)")  # type: ignore

        # Test set values
        try:
            instance.inside = random.random()
            self.fail("Instance value (in) must not be modified.")
        except AttributeError:
            # We must be there
            pass

        try:
            instance.outside = random.random()  # type: ignore
            self.fail("Instance value (out) must not be modified.")
        except AttributeError:
            # We must be there
            pass

        # Test final values (just in case)
        self.assertEqual(instance.inside, value_1, "Invalid final value (in)")
        self.assertEqual(instance.outside, value_2, "Invalid final value (out)")  # type: ignore

    def testRemoveAllOccurrences(self) -> None:
        """
        Tests the remove_all_occurrences() method
        """
        try:
            # Must not raise an exception
            utilities.remove_all_occurrences(None, 12)  # type: ignore
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
            self.assertEqual(list_copy.count(i), count_base, "Copies doesn't have the same count of values")

            # Get the current length of the copy
            len_base = len(list_copy)

            # Remove the element
            utilities.remove_all_occurrences(list_copy, i)

            # The new count must be 0
            self.assertEqual(list_copy.count(i), 0, "Some references remain")

            # The new length must be len_base - count_base
            self.assertEqual(len(list_copy), len_base - count_base, "Incorrect new list size")

    def testIsString(self) -> None:
        """
        Tests the is_string() method
        """
        valid = ["", "aaa", str(42)]
        invalid = [42, None, [], {}, tuple(), b"", b"aaa"]  # type: ignore

        for value in valid:
            self.assertTrue(utilities.is_string(value), f"'{value}' is a string")

        for value in invalid:  # type: ignore
            self.assertFalse(utilities.is_string(value), f"'{value}' is not a string")

    def testAddRemoveListener(self) -> None:
        """
        Tests add/remove listener methods
        """
        registry: List[Any] = []
        values = (42, "test", (1, 2, 3))

        # None value
        self.assertFalse(utilities.add_listener(registry, None), "None value must not be accepted")

        self.assertFalse(utilities.remove_listener(registry, None), "None value must not be accepted")

        for value in values:
            # Non-present value
            self.assertFalse(utilities.remove_listener(registry, value), "Non-present value removed")

            # Add value
            self.assertTrue(utilities.add_listener(registry, value), "Value has been refused")
            self.assertEqual(registry.count(value), 1, "Value not inserted in registry")

            # Second add
            self.assertFalse(utilities.add_listener(registry, value), "Value has been added twice")
            self.assertEqual(registry.count(value), 1, "Value has been added twice")

        for value in values:
            # Remove value
            self.assertTrue(utilities.remove_listener(registry, value), "Value has not been removed")
            # Ensure the value has been remove
            self.assertEqual(registry.count(value), 0, "Value has not been removed")

            # Second removal
            self.assertFalse(utilities.remove_listener(registry, value), "Value has been removed twice")

    def testUseService(self) -> None:
        """
        Tests utilities.use_service()
        """
        framework = pelix.framework.create_framework([])
        try:
            framework.start()
            context = framework.get_bundle_context()

            # Try without the service reference: TypeError
            self.assertRaises(TypeError, utilities.use_service(context, None).__enter__)  # type: ignore

            # Start the service bundle
            bundle = context.install_bundle("tests.framework.service_bundle")
            bundle.start()

            # Get the service reference
            svc_ref = context.get_service_reference(IEchoService)
            assert svc_ref is not None

            # Use it
            with utilities.use_service(context, svc_ref) as service:
                # Test the usage information
                self.assertIn(
                    context.get_bundle(), svc_ref.get_using_bundles(), "Bundles using the service not updated"
                )

                # Get the service the Pelix way
                got_service = context.get_service(svc_ref)

                # Test the service object
                self.assertIs(service, got_service, "Found a different service.")

                # Clean up the test usage
                context.unget_service(svc_ref)
                got_service = None  # type: ignore

                # Re-test the usage information
                self.assertIn(
                    context.get_bundle(), svc_ref.get_using_bundles(), "Bundles using service not kept"
                )

            # Test the usage information
            self.assertNotIn(
                context.get_bundle(), svc_ref.get_using_bundles(), "Bundles using service kept after block"
            )

            # Stop the iPOPO bundle
            bundle.stop()

            # Ensure the service is not accessible anymore
            self.assertRaises(
                pelix.constants.BundleException, utilities.use_service(context, svc_ref).__enter__
            )

            # Uninstall the bundle
            bundle.uninstall()

            # Ensure the service is not accessible anymore
            self.assertRaises(
                pelix.constants.BundleException, utilities.use_service(context, svc_ref).__enter__
            )
        finally:
            framework.stop()
            framework.delete(True)

    def testToIterable(self) -> None:
        """
        Tests the to_iterable() method
        """
        # None value
        self.assertIsNone(utilities.to_iterable(None, True), "None value refused")
        self.assertListEqual(utilities.to_iterable(None, False), [], "None value accepted")  # type: ignore

        # Check iterable types
        for clazz in (list, tuple, set, frozenset):
            iterable = clazz()
            self.assertIs(
                utilities.to_iterable(iterable), iterable, "to_iterable() didn't returned the original object"
            )

        # Check other types
        for value in ("hello", 123, {1: 2}, object()):
            self.assertListEqual(
                utilities.to_iterable(value), [value], "to_iterable() didn't returned a list"  # type: ignore
            )


# ------------------------------------------------------------------------------


class CountdownEventTest(unittest.TestCase):
    """
    Tests for the CountdownEvent class
    """

    def testInitCheck(self) -> None:
        """
        Tests the value check when creating the event
        """
        for invalid in (-1, 0):
            self.assertRaises(ValueError, utilities.CountdownEvent, invalid)

    def testSteps(self) -> None:
        """
        Tests the count down event behavior
        """
        event = utilities.CountdownEvent(3)
        # Stepping...
        self.assertFalse(event.step(), "Finished on first step...")
        self.assertFalse(event.is_set(), "Set on first step...")
        self.assertFalse(event.step(), "Finished on second step...")
        self.assertFalse(event.is_set(), "Set on second step...")

        # Last one
        self.assertTrue(event.step(), "Not done on last step...")
        self.assertTrue(event.is_set(), "Not set on last step...")

        # No more
        self.assertRaises(ValueError, event.step)
        self.assertTrue(event.is_set(), "Not set after last step...")

    def testWait(self) -> None:
        """
        Tests the wait() method
        """
        event = utilities.CountdownEvent(1)
        self.assertFalse(event.wait(0.1), "Timed out wait must return False")

        start = time.time()
        threading.Timer(1, event.step).start()
        self.assertFalse(event.wait(0.1), "Timed out wait must return False")
        self.assertTrue(event.wait(), "Wait should return true on set")
        self.assertLessEqual(time.time() - start, 2, "Too long to wait")

        self.assertTrue(event.wait(0.5), "Already set event shoudn't block wait()")
        self.assertTrue(event.wait(), "Already set event shoudn't block wait()")


# ------------------------------------------------------------------------------


class EventDataTest(unittest.TestCase):
    """
    Tests for the EventData class
    """

    def testSetClear(self) -> None:
        """
        Tests set() and clear() operations
        """
        # Initial condition
        event = utilities.EventData[Any]()
        self.assertFalse(event.is_set(), "Event initially set")
        self.assertIsNone(event.data, "Non-None data")
        self.assertIsNone(event.exception, "Non-None exception")

        # No-data set
        event.set()
        self.assertTrue(event.is_set(), "Event not set")
        self.assertIsNone(event.data, "Non-None data")
        self.assertIsNone(event.exception, "Non-None exception")

        # Clear
        event.clear()
        self.assertFalse(event.is_set(), "Event still set")
        self.assertIsNone(event.data, "Non-None data")
        self.assertIsNone(event.exception, "Non-None exception")

        # Set data
        data = object()
        event.set(data)
        self.assertTrue(event.is_set(), "Event not set")
        self.assertIs(event.data, data, "Invalid event data")
        self.assertIsNone(event.exception, "Non-None exception")

        # Clear
        event.clear()
        self.assertFalse(event.is_set(), "Event still set")
        self.assertIsNone(event.data, "Non-None data")
        self.assertIsNone(event.exception, "Non-None exception")

    def testException(self) -> None:
        """
        Tests the exception storage
        """
        event = utilities.EventData[Any]()

        # "Raise" an exception
        exception = Exception("Some dummy exception")
        event.raise_exception(exception)

        # Check content
        self.assertTrue(event.is_set(), "Event has not been set")
        self.assertIsNone(event.data, "Non-None data")
        self.assertIs(event.exception, exception, "Invalid exception")

        # Check the behavior of "wait"
        try:
            event.wait()
        except Exception as ex:
            self.assertIs(ex, exception, "Not the same exception")
            self.assertTrue(event.is_set(), "Event has been cleared")
        else:
            self.fail("Exception not raised")

        # Clear
        event.clear()
        self.assertFalse(event.is_set(), "Event has been set")
        self.assertIsNone(event.data, "Non-None data")
        self.assertIsNone(event.exception, "Non-None exception")

    def testWait(self) -> None:
        """
        Tests the wait() method
        """
        event = utilities.EventData[Any]()
        self.assertFalse(event.wait(0.1), "Timed out wait must return False")

        start = time.time()
        threading.Timer(1, event.set).start()
        self.assertFalse(event.wait(0.1), "Timed out wait must return False")
        self.assertTrue(event.wait(), "Wait should return true on set")
        self.assertLessEqual(time.time() - start, 2, "Too long to wait")

        self.assertTrue(event.wait(0.5), "Already set event shoudn't block wait()")
        self.assertTrue(event.wait(), "Already set event shoudn't block wait()")

    def testWaitException(self) -> None:
        """
        Tests the exception effect on wait()
        """
        event = utilities.EventData[Any]()
        exception = Exception("Some dummy exception")

        # "Raise" an exception
        threading.Timer(0.5, event.raise_exception, [exception]).start()

        # Check the behavior of "wait"
        try:
            event.wait()
        except Exception as ex:
            self.assertIs(ex, exception, "Not the same exception")
        else:
            self.fail("Exception not raised")

        # Check content
        self.assertTrue(event.is_set(), "Event has been cleared")
        self.assertIsNone(event.data, "Non-None data")
        self.assertIs(event.exception, exception, "Invalid exception")


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
