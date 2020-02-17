#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Tests the utility module

:author: Thomas Calmant
"""

# Same version as the tested bundle
__version__ = (0, 5, 6)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Standard library
import random
import threading
import time
import pytest

# Tests
from tests.interfaces import IEchoService

# Pelix
import pelix.constants
import pelix.framework
import pelix.utilities as utilities


# ------------------------------------------------------------------------------


class TestSynchronizationUtilities:
    """
    Tests for utility module synchronization methods
    """
    lock = threading.Lock()
    def test_is_lock(self):
        """
        Tests the is_lock method
        """
        self.lock = threading.Lock()

        valid = (threading.Lock(), threading.RLock(), threading.Semaphore(),
                 threading.Condition())
        invalid = (None, "", 1234, object())

        for test in valid:
            assert utilities.is_lock(test), \
                            "Valid lock not detected: {0}" \
                            .format(type(test).__name__)

        for test in invalid:
            assert not utilities.is_lock(test), \
                             "Invalid lock not detected: {0}" \
                             .format(type(test).__name__)

    @utilities.SynchronizedClassMethod('lock')
    def test_synchronized_class_method(self):
        """
        Tests the @SynchronizedClassMethod decorator
        """
        # Just test if the lock is really locked
        assert not self.lock.acquire(False), "Method is not locked"

    def test_synchronized_method(self, no_lock=False):
        """
        Tests the @Synchronized decorator, with or without a given lock

        :param no_lock: If True, create the lock, else let the decorator do it
        """
        self.lock = threading.Lock()

        # Thread results: ID -> starting time
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
                assert not lock.acquire(False), "Lock not locked"

            result[sleep_id] = time.time()
            time.sleep(wait)

        # Get first call time
        start = time.time()

        # Launch first waiter
        thread1 = threading.Thread(target=sleeper, args=(.5, 1))
        thread1.start()

        # Wait a little before starting 2nd thread: on Windows, thread 2
        # can start before thread 1
        time.sleep(.1)

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
        assert result[1] >= start, "Thread 1 started too soon"

        # .. Thread 2 started at least 0.4 secs after thread 1
        # (due to the lock)
        # (0.4 instead of 0.5: some systems are not that precise)
        assert result[2] >= result[1] + .4, \
                                "Thread 2 started too soon (after {0}s)" \
                                .format(result[2] - result[1])

        # .. Thread 2 must not have blocked the main thread
        assert result[2] > interm, \
                           "Thread 2 blocked the main thread"

    def test_synchronized_method2(self):
        """
        Tests the @Synchronized decorator, without a given lock
        """
        self.lock = threading.Lock()
        self.test_synchronized_method(True)

    def test_nolock_exception(self):
        """
        Verifies that @SynchronizedClassMethod raises an error when no lock
        is given
        """
        self.lock = threading.Lock()
        try:
            @utilities.SynchronizedClassMethod()
            def dummy():
                pass

            pytest.fail("@SynchronizedClassMethod() should raise a ValueError")
        except ValueError:
            # We must be there to succeed
            pass

        try:
            @utilities.SynchronizedClassMethod(None)
            def dummy():
                pass

            pytest.fail("@SynchronizedClassMethod(None) should raise a "
                      "ValueError")
        except ValueError:
            # We must be there to succeed
            pass

    def test_none_lock_exception(self):
        """
        Verifies that @SynchronizedClassMethod raises an error when a None lock
        is used for locking
        """
        self.lock = None
        with pytest.raises(AttributeError):
            self.test_synchronized_class_method()

# ------------------------------------------------------------------------------


class TestUtilities:
    """
    Tests for utility module methods
    """
    def test_read_only_property(self):
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
        assert instance.inside == value_1, \
                         "Invalid initial value (in)"
        assert instance.outside == value_2, \
                         "Invalid initial value (out)"

        # Test set values
        try:
            instance.inside = random.random()
            pytest.fail("Instance value (in) must not be modified.")

        except AttributeError:
            # We must be there
            pass

        try:
            instance.outside = random.random()
            pytest.fail("Instance value (out) must not be modified.")

        except AttributeError:
            # We must be there
            pass

        # Test final values (just in case)
        assert instance.inside == value_1, \
                         "Invalid final value (in)"
        assert instance.outside == value_2, \
                         "Invalid final value (out)"

    def test_remove_all_occurrences(self):
        """
        Tests the remove_all_occurrences() method
        """
        try:
            # Must not raise an exception
            utilities.remove_all_occurrences(None, 12)

        except:
            pytest.fail("remove_all_occurrences(None) must not raise an "
                      "exception")

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
            assert list_copy.count(i) == count_base, \
                             "Copies doesn't have the same count of values"

            # Get the current length of the copy
            len_base = len(list_copy)

            # Remove the element
            utilities.remove_all_occurrences(list_copy, i)

            # The new count must be 0
            assert list_copy.count(i) == 0, "Some references remain"

            # The new length must be len_base - count_base
            assert len(list_copy) == len_base - count_base, \
                             "Incorrect new list size"

    def test_is_string(self):
        """
        Tests the is_string() method
        """
        valid = ["", "aaa", str(42)]
        invalid = [42, None, [], {}, tuple()]
        invalid.extend((b"", b"aaa"))


        for value in valid:
            assert isinstance(value, str), \
                            "'{0}' is a string".format(value)

        for value in invalid:
            assert not isinstance(value, str), \
                             "'{0}' is not a string".format(value)

    def test_add_remove_listener(self):
        """
        Tests add/remove listener methods
        """
        registry = []
        values = (42, "test", (1, 2, 3))

        # None value
        assert not utilities.add_listener(registry, None), \
                         "None value must not be accepted"

        assert not utilities.remove_listener(registry, None), \
                         "None value must not be accepted"

        for value in values:
            # Non-present value
            assert not utilities.remove_listener(registry, value), \
                             "Non-present value removed"

            # Add value
            assert utilities.add_listener(registry, value), \
                            "Value has been refused"
            assert registry.count(value) == 1, \
                             "Value not inserted in registry"

            # Second add
            assert not utilities.add_listener(registry, value), \
                             "Value has been added twice"
            assert registry.count(value) == 1, \
                             "Value has been added twice"

        for value in values:
            # Remove value
            assert utilities.remove_listener(registry, value), \
                            "Value has not been removed"
            # Ensure the value has been remove
            assert registry.count(value) == 0, \
                             "Value has not been removed"

            # Second removal
            assert not utilities.remove_listener(registry, value), \
                             "Value has been removed twice"

    @pytest.mark.asyncio
    async def test_use_service(self):
        """
        Tests utilities.use_service()
        """
        framework = await pelix.framework.create_framework([])
        await framework.start()
        context = framework.get_bundle_context()

        # Try without the service reference: TypeError
        with pytest.raises(TypeError):
            with utilities.use_service(context, None):
                pass

        # Start the service bundle
        bundle = await context.install_bundle("tests.framework.service_bundle")
        await bundle.start()

        # Get the service reference
        svc_ref = context.get_service_reference(IEchoService)

        # Use it
        with utilities.use_service(context, svc_ref) as service:
            # Test the usage information
            assert await context.get_bundle() in svc_ref.get_using_bundles(), "Bundles using the service not updated"

            # Get the service the Pelix way
            got_service = context.get_service(svc_ref)

            # Test the service object
            assert service is got_service, "Found a different service."

            # Clean up the test usage
            context.unget_service(svc_ref)
            got_service = None

            # Re-test the usage information
            assert await context.get_bundle() in svc_ref.get_using_bundles(), "Bundles using service not kept"

        # Test the usage information
        assert await context.get_bundle() not in svc_ref.get_using_bundles(), "Bundles using service kept after block"

        # Stop the iPOPO bundle
        await bundle.stop()

        # Ensure the service is not accessible anymore
        with pytest.raises(pelix.constants.BundleException):
            with utilities.use_service(context, svc_ref):
                pass

        # Uninstall the bundle
        await bundle.uninstall()

        # Ensure the service is not accessible anymore
        with pytest.raises(pelix.constants.BundleException):
            with utilities.use_service(context, svc_ref):
                pass

        await framework.delete()

    @pytest.mark.asyncio
    async def test_rlock(self):
        """
        Test asynchronous Rlock
        """
        lock = utilities.RLock()

        step_into_first = False
        step_into_second = False
        step_into_third = False
        async with lock:
            step_into_first = True
            async with lock:
                step_into_second = True
                async with lock:
                    step_into_third = True

        assert all([step_into_first, step_into_second, step_into_third])
        assert lock._depth == 0


    def test_to_iterable(self):
        """
        Tests the to_iterable() method
        """
        # None value
        assert utilities.to_iterable(None, True) is None, \
                          "None value refused"
        assert utilities.to_iterable(None, False) == [], \
                             "None value accepted"

        # Check iterable types
        for clazz in (list, tuple, set, frozenset):
            iterable = clazz()
            assert utilities.to_iterable(iterable) is iterable, \
                          "to_iterable() didn't returned the original object"

        # Check other types
        for value in ("hello", 123, {1: 2}, object()):
            assert utilities.to_iterable(value) == [value], \
                                 "to_iterable() didn't returned a list"

# ------------------------------------------------------------------------------


class TestCountdownEventTest:
    """
    Tests for the CountdownEvent class
    """
    def test_init_check(self):
        """
        Tests the value check when creating the event
        """
        for invalid in (-1, 0):
            with pytest.raises(ValueError):
                utilities.CountdownEvent(invalid)

    def test_steps(self):
        """
        Tests the count down event behavior
        """
        event = utilities.CountdownEvent(3)
        # Stepping...
        assert not event.step(), "Finished on first step..."
        assert not event.is_set(), "Set on first step..."
        assert not event.step(), "Finished on second step..."
        assert not event.is_set(), "Set on second step..."

        # Last one
        assert event.step(), "Not done on last step..."
        assert event.is_set(), "Not set on last step..."

        # No more
        with pytest.raises(ValueError):
            event.step()
        assert event.is_set(), "Not set after last step..."

    def test_wait(self):
        """
        Tests the wait() method
        """
        event = utilities.CountdownEvent(1)
        assert not event.wait(.1), "Timed out wait must return False"

        start = time.time()
        threading.Timer(1, event.step).start()
        assert not event.wait(.1), "Timed out wait must return False"
        assert event.wait(), "Wait should return true on set"
        assert time.time() - start <= 2, "Too long to wait"

        assert event.wait(.5), "Already set event shoudn't block wait()"
        assert event.wait(), "Already set event shoudn't block wait()"

# ------------------------------------------------------------------------------


class TestEventDataTest:
    """
    Tests for the EventData class
    """
    def test_set_clear(self):
        """
        Tests set() and clear() operations
        """
        # Initial condition
        event = utilities.EventData()
        assert not event.is_set(), "Event initially set"
        assert event.data is None, "Non-None data"
        assert event.exception is None, "Non-None exception"

        # No-data set
        event.set()
        assert event.is_set(), "Event not set"
        assert event.data is None, "Non-None data"
        assert event.exception is None, "Non-None exception"

        # Clear
        event.clear()
        assert not event.is_set(), "Event still set"
        assert event.data is None, "Non-None data"
        assert event.exception is None, "Non-None exception"

        # Set data
        data = object()
        event.set(data)
        assert event.is_set(), "Event not set"
        assert event.data is data, "Invalid event data"
        assert event.exception is None, "Non-None exception"

        # Clear
        event.clear()
        assert not event.is_set(), "Event still set"
        assert event.data is None, "Non-None data"
        assert event.exception is None, "Non-None exception"

    def test_exception(self):
        """
        Tests the exception storage
        """
        event = utilities.EventData()

        # "Raise" an exception
        exception = Exception("Some dummy exception")
        event.raise_exception(exception)

        # Check content
        assert event.is_set(), "Event has not been set"
        assert event.data is None, "Non-None data"
        assert event.exception is exception, "Invalid exception"

        # Check the behavior of "wait"
        try:
            event.wait()
        except Exception as ex:
            assert ex is exception, "Not the same exception"
            assert event.is_set(), "Event has been cleared"
        else:
            pytest.fail("Exception not raised")

        # Clear
        event.clear()
        assert not event.is_set(), "Event has been set"
        assert event.data is None, "Non-None data"
        assert event.exception is None, "Non-None exception"

    def test_wait(self):
        """
        Tests the wait() method
        """
        event = utilities.EventData()
        assert not event.wait(.1), "Timed out wait must return False"

        start = time.time()
        threading.Timer(1, event.set).start()
        assert not event.wait(.1), "Timed out wait must return False"
        assert event.wait(), "Wait should return true on set"
        assert time.time() - start <= 2, "Too long to wait"

        assert event.wait(.5), \
                        "Already set event shoudn't block wait()"
        assert event.wait(), \
                        "Already set event shoudn't block wait()"

    def test_wait_exception(self):
        """
        Tests the exception effect on wait()
        """
        event = utilities.EventData()
        exception = Exception("Some dummy exception")

        # "Raise" an exception
        threading.Timer(.5, event.raise_exception, [exception]).start()

        # Check the behavior of "wait"
        try:
            event.wait()
        except Exception as ex:
            assert ex is exception, "Not the same exception"
        else:
            pytest.fail("Exception not raised")

        # Check content
        assert event.is_set(), "Event has been cleared"
        assert event.data is None, "Non-None data"
        assert event.exception is exception, "Invalid exception"
