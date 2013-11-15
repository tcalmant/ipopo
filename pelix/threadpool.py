#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix Utilities: Task pool

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.5.5
:status: Beta

..

    Copyright 2013 isandlaTech

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

# Documentation strings format
__docformat__ = "restructuredtext en"

# Module version
__version_info__ = (0, 5, 5)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------

# Standard library
import logging
import threading

try:
    # Python 3
    import queue

except ImportError:
    # Python 2
    import Queue as queue

# ------------------------------------------------------------------------------

class FutureResult(object):
    """
    An object to wait for the result of a threaded execution
    """
    def __init__(self):
        """
        Sets up the FutureResult object
        """
        self._done_event = threading.Event()
        self._result = None


    def execute(self, method, args, kwargs):
        """
        Execute the given method and stores its result.
        The result is considered "done" even if the method raises an exception

        :param method: The method to execute
        :param args: Method positional arguments
        :param kwargs: Method keyword arguments
        :raise Exception: The exception raised by the method
        """
        # Normalize arguments
        if args is None:
            args = []

        if kwargs is None:
            kwargs = {}

        try:
            # Call the method
            self._result = method(*args, **kwargs)

        finally:
            # Mark the action as executed
            self._done_event.set()


    def done(self):
        """
        Returns True if the job has finished, else False
        """
        return self._done_event.is_set()


    def result(self, timeout=None):
        """
        Waits up to timeout for the result the threaded job.
        Returns immediately the result if the job has already been done.

        :param timeout: The maximum time to wait for a result (in seconds)
        :raise OSError: The timeout raised before the job finished
        """
        if self._done_event.wait(timeout) or self._done_event.is_set():
            return self._result

        raise OSError("Timeout raised")

# ------------------------------------------------------------------------------

class ThreadPool(object):
    """
    Executes the tasks stored in a FIFO in a thread pool
    """
    def __init__(self, nb_threads, queue_size=0, timeout=5, logname=None):
        """
        Sets up the task executor

        :param nb_threads: Size of the thread pool
        :param queue_size: Size of the task queue (0 for infinite)
        :param timeout: Queue timeout (in seconds)
        :param logname: Name of the logger
        :raise ValueError: Invalid number of threads
        """
        # Validate parameters
        if type(nb_threads) is not int or nb_threads < 1:
            raise ValueError("Invalid pool size: {0}".format(nb_threads))

        # The logger
        self.__name = logname or __name__
        self._logger = logging.getLogger(self.__name)

        # The loop control event
        self._done_event = threading.Event()
        self._done_event.set()

        # The task queue
        try:
            queue_size = int(queue_size)

        except (TypeError, ValueError):
            # Not a valid integer
            queue_size = 0

        self._queue = queue.Queue(queue_size)
        self._timeout = timeout
        self.__lock = threading.Lock()

        # The thread pool
        self._nb_threads = nb_threads
        self._threads = []


    def start(self):
        """
        Starts the thread pool. Does nothing if the pool is already started.
        """
        if not self._done_event.is_set():
            # Stop event not set: we're running
            return

        # Clear the stop event
        self._done_event.clear()

        # Create the threads
        i = 0
        while i < self._nb_threads:
            i += 1
            thread = threading.Thread(target=self.__run,
                                      name="{0}-{1}".format(self.__name, i))
            self._threads.append(thread)

        # Start'em
        for thread in self._threads:
            thread.start()


    def stop(self):
        """
        Stops the thread pool. Does nothing if the pool is already stopped.
        """
        if self._done_event.is_set():
            # Stop event set: we're stopped
            return

        # Set the stop event
        self._done_event.set()

        with self.__lock:
            # Add something in the queue (to unlock the join())
            try:
                for _ in self._threads:
                    self._queue.put(self._done_event, True, self._timeout)

            except queue.Full:
                # There is already something in the queue
                pass

            # Join threads
            for thread in self._threads:
                thread.join()

        # Clear storage
        del self._threads[:]
        self.clear()


    def enqueue(self, method, *args, **kwargs):
        """
        Enqueues a task in the pool

        :param method: Method to call
        :return: A FutureResult object, to get the result of the task
        :raise ValueError: Invalid method
        :raise Full: The task queue is full
        """
        if not hasattr(method, '__call__'):
            raise ValueError("{0} has no __call__ member." \
                             .format(method.__name__))

        # Prepare the future result object
        future = FutureResult()

        # Use a lock, as we might be "resetting" the queue
        with self.__lock:
            # Add the task to the queue
            self._queue.put((method, args, kwargs, future), True, self._timeout)

        return future


    def clear(self):
        """
        Empties the current queue content.
        Returns once the queue have been emptied.
        """
        with self.__lock:
            # Empty the current queue
            try:
                while True:
                    self._queue.get_nowait()
                    self._queue.task_done()

            except queue.Empty:
                # Queue is now empty
                pass

            # Wait for the tasks currently executed
            self.join()


    def join(self, timeout=None):
        """
        Waits for all the tasks to be executed

        :param timeout: Maximum time to wait (in seconds)
        :return: True if the queue has been emptied, else False
        """
        if self._queue.empty():
            # Nothing to wait for...
            return True

        elif timeout is None:
            # Use the original join
            self._queue.join()
            return True

        else:
            # Wait for the condition
            with self._queue.all_tasks_done:
                self._queue.all_tasks_done.wait(timeout)
                return self._queue.empty()


    def __run(self):
        """
        The main loop
        """
        while not self._done_event.is_set():
            try:
                # Wait for an action (blocking)
                task = self._queue.get(True, self._timeout)
                if task is self._done_event:
                    # Stop event in the queue: get out
                    return

            except queue.Empty:
                # Nothing to do
                pass

            else:
                # Extract elements
                method, args, kwargs, future = task
                try:
                    # Call the method
                    future.execute(method, args, kwargs)

                except Exception as ex:
                    self._logger.exception("Error executing %s: %s",
                                           method.__name__, ex)

                finally:
                    # Mark the action as executed
                    self._queue.task_done()
