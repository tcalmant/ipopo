#!/usr/bin/python3
# -- Content-Encoding: UTF-8 --
"""
Cached thread pool tests

:license: Apache License 2.0
"""

# ------------------------------------------------------------------------------

# Standard library
import threading
import time

# Tests
import pytest

# Tested module
import pelix.threadpool as threadpool


# ------------------------------------------------------------------------------


def _slow_call(wait, result=None, event=None):
    """
    Method that returns after the given time (in seconds)
    """
    if event is not None:
        event.wait(wait)
    else:
        time.sleep(wait)
    return result


def _trace_call(result_list, result):
    """
    Methods stores the result in the result list
    """
    result_list.append(result)

# ------------------------------------------------------------------------------


class TestFuture:
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

    def test_simple(self):
        """
        Simple, error-less execution
        """
        # Create the future object
        future = threadpool.FutureResult()

        # Assert we have no result yet
        assert not future.done(), "Execution flag up"
        with pytest.raises(OSError):
            future.result(0)

        # Execute the method
        result1, result2, result3 = range(3)
        future.execute(self._simple_call,
                       (result1, result2), {"result": result3})

        # Assert it is done
        assert future.done(), "Execution flag not updated"
        assert future.result() == (result1, result2, result3), \
                         "Invalid result"

    def test_raise(self):
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
            pytest.fail("Execute didn't propagate the error")

        # The call must be considered as done
        assert future.done(), "Execution flag not updated"
        try:
            future.result()
        except ValueError as ex:
            assert ex is exception, "Result exception changed"
        else:
            pytest.fail("Result didn't propagate the error")

    def test_timeout(self):
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
        with pytest.raises(OSError):
            future.result(0)
        assert not future.done(), "Execution flag up"

        # Check waiting a little
        with pytest.raises(OSError):
            future.result(.2)
        assert not future.done(), "Execution flag up"

        # Check waiting longer
        assert future.result(2) is result, "Invalid result"
        assert future.done(), "Execution flag not updated"

    def test_callback(self):
        """
        Tests the callback method
        """
        # Set the callback before calling the method
        flag = threadpool.EventData()
        future = threadpool.FutureResult()
        future.set_callback(self._callback, flag)
        assert not flag.is_set(), "Flag already set"

        # Execute
        args = (1, 2, 3)
        future.execute(self._simple_call, args, None)

        # Check event content
        assert flag.is_set(), "Callback method not called"
        assert flag.exception is None, "Exception set"
        assert flag.data == args, "Data not set"

        # ... Re-set the callback (should be re-called)
        flag.clear()
        assert not flag.is_set(), "Flag already set"
        future.set_callback(self._callback, flag)

        # Check event content
        assert flag.is_set(), "Callback method not called"
        assert flag.exception is None, "Exception set"
        assert flag.data == args, "Data not set"

    def test_callback_exception(self):
        """
        Tests the callback method in case of exception
        """
        # Set the callback before calling the method
        flag = threadpool.EventData()
        future = threadpool.FutureResult()
        future.set_callback(self._callback, flag)
        assert not flag.is_set(), "Flag already set"

        # Execute
        try:
            future.execute(self._raise_call, None, None)
        except Exception as ex:
            # Store it
            exception = ex
        else:
            pytest.fail("Exception wasn't propagated")

        # Check event content
        assert flag.is_set(), "Callback method not called"
        assert flag.exception is exception, "Exception not set"
        assert flag.data is None, "Data set"

        # ... Re-set the callback (should be re-called)
        flag.clear()
        assert not flag.is_set(), "Flag already set"
        future.set_callback(self._callback, flag)

        # Check event content
        assert flag.is_set(), "Callback method not called"
        assert flag.exception is exception, "Exception not set"
        assert flag.data is None, "Data set"

    def test_bad_callback(self):
        """
        Tests behavior on callback error
        """
        future = threadpool.FutureResult()
        args = (1, 2, 3)
        flag = threadpool.EventData()

        def dummy():
            """
            Callback without arguments
            """
            flag.set()

        # Bad number of arguments: no exception must be raised
        future.set_callback(dummy)
        future.execute(self._simple_call, args, None)
        assert not flag.is_set(), "Flag shouldn't be set..."

        def raising(data, exception, ex):
            """
            Callback raising an exception
            """
            flag.set()
            raise ex

        exception = ValueError("Dummy error")
        future.set_callback(raising, exception)
        assert flag.is_set(), "Callback not called"

# ------------------------------------------------------------------------------


class TestThreadPool:
    """
    Tests the thread pool utility class
    """
    pool = None
    def test_init_parameters(self):
        """
        Tests the validity checks on thread pool creation
        """
        self.pool = None

        # Invalid maximum number of threads
        for invalid_nb in (0, -1, 0.1, "abc"):
            # Invalid max threads
            with pytest.raises(ValueError):
                threadpool.ThreadPool(invalid_nb)

        # Invalid minimum threads
        with pytest.raises(ValueError):
            threadpool.ThreadPool(10, "abc")

        # Normalization of the minimum number of thread
        # ... < 0 => 0
        pool = threadpool.ThreadPool(10, -1)
        assert pool._min_threads == 0

        # ... > max => max
        pool = threadpool.ThreadPool(10, 100)
        assert pool._min_threads == 10

        # Check queue size
        for queue_size in (-1, 0, 0.1, "abc"):
            pool = threadpool.ThreadPool(10, queue_size=queue_size)
            assert pool._queue.maxsize <= 0

        if self.pool is not None:
            self.pool.stop()

    def test_double_start_stop(self):
        """
        Check double call to start() and stop()
        """
        self.pool = threadpool.ThreadPool(1)
        result_list = []

        # Enqueue the call
        future = self.pool.enqueue(_trace_call, result_list, None)

        # Double start
        self.pool.start()
        self.pool.start()

        # Wait for the result
        future.result()

        # Ensure the method has been called only once
        assert len(result_list) == 1

        # Double stop: shouldn't raise any error
        self.pool.stop()
        self.pool.stop()

    def test_pre_start_enqueue(self):
        """
        Tests the late start of the poll
        """
        self.pool = threadpool.ThreadPool(1)
        result = object()

        # Add the call to the queue
        future = self.pool.enqueue(_slow_call, 0, result)
        assert not future.done(), "Execution flag up"

        # Start the pool
        self.pool.start()

        # Wait for the result
        assert future.result(1) is result, "Invalid result"
        assert future.done(), "Execution flag not updated"

        # Stop the pool
        self.pool.stop()

        # Create a new pool
        max_threads = 5
        futures = []

        # Prepare the pool
        self.pool = threadpool.ThreadPool(max_threads)

        # Enqueue more tasks than the maximum threads for the pool
        for i in range(max_threads * 2):
            futures.append(self.pool.enqueue(_slow_call, 0, result))

        # Start the pool
        self.pool.start()

        # Ensure all methods are called
        for future in futures:
            future.result(2)

        # Stop the pool
        self.pool.stop()

    def test_pre_restart_enqueue(self):
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
        assert future.result(1) is result, "Invalid result"
        assert future.done(), "Execution flag not updated"

        # Stop the pool
        self.pool.stop()

        # Add the call to the queue
        future = self.pool.enqueue(_slow_call, 0, result)
        assert not future.done(), "Execution flag up"

        # Start the pool
        self.pool.start()

        # Wait for the result
        assert future.result(5) is result, "Invalid result"
        assert future.done(), "Execution flag not updated"

        # Clear pool, if any
        if self.pool is not None:
            self.pool.stop()

    def test_exception(self):
        """
        Tests if an exception is correctly hidden
        """
        # Define the exception
        def thrower(ex):
            raise ex

        exception = ValueError("Some error")

        # Start the pool
        self.pool = threadpool.ThreadPool(1)
        self.pool.start()

        # Enqueue the method
        future = self.pool.enqueue(thrower, exception)

        # Wait for the method to be executed
        self.pool.join()

        # Method has been called
        assert future.done()

        try:
            future.result()
        except ValueError as catched_ex:
            # result() must raise the exact exception
            assert catched_ex is exception

        # Clear pool, if any
        if self.pool is not None:
            self.pool.stop()

    def test_join(self):
        """
        Tests the join() method
        """
        # Start the pool
        self.pool = threadpool.ThreadPool(1)
        self.pool.start()

        # Empty, with or without timeout
        assert self.pool.join()

        start = time.time()
        assert self.pool.join(5)
        end = time.time()
        assert end - start < 1

        # Not empty, without timeout
        self.pool.enqueue(_slow_call, 2)
        start = time.time()
        assert self.pool.join()
        end = time.time()
        assert end - start < 3

        # Really join
        self.pool.join()

        # Not empty, with timeout not reached
        self.pool.enqueue(_slow_call, 1)
        start = time.time()
        assert self.pool.join(5)
        end = time.time()
        assert end - start < 3

        # Really join
        self.pool.join()

        # Not empty, with timeout reached
        # Use an event to ensure that the thread stays alive
        event = threading.Event()
        self.pool.enqueue(_slow_call, 10, event=event)
        start = time.time()
        assert not self.pool.join(1)
        end = time.time()
        event.set()
        assert end - start < 2

        # Really join
        self.pool.join()

        # Clear pool, if any
        if self.pool is not None:
            self.pool.stop()

    def test_max_thread(self):
        """
        Checks if the maximum number of threads is respected
        """
        # Start the pool
        self.pool = threadpool.ThreadPool(3)
        self.pool.start()

        # Enqueue & check
        for _ in range(10):
            time.sleep(.1)
            self.pool.enqueue(_slow_call, .8, None)
            assert self.pool._ThreadPool__nb_threads <= \
                                 self.pool._max_threads

        self.pool.join()

        # Clear pool, if any
        if self.pool is not None:
            self.pool.stop()
