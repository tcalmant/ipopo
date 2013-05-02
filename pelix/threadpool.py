#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix Utilities: Task pool

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.5.0
:status: Alpha

    This file is part of iPOPO.

    iPOPO is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    iPOPO is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with iPOPO. If not, see <http://www.gnu.org/licenses/>.
"""

# Documentation strings format
__docformat__ = "restructuredtext en"

# Module version
__version_info__ = (0, 5, 0)
__version__ = ".".join(map(str, __version_info__))

# ------------------------------------------------------------------------------

# Standard library
import logging
import threading
import sys

if sys.version_info[0] == 3:
    # Python 3
    import queue

else:
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
        if self._done_event.wait(timeout):
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
        self._logger = logging.getLogger(logname or __name__)

        # The loop control event
        self._done_event = threading.Event()
        self._done_event.set()

        # The task queue
        self._queue = queue.Queue(queue_size)
        self._queue_size = queue_size
        self._timeout = timeout

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
            thread = threading.Thread(target=self.__run)
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
        self.reset_queue()


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

        # Add the task to the queue
        self._queue.put((method, args, kwargs, future), True, self._timeout)
        return future


    def reset_queue(self):
        """
        Creates a new queue (deletes references to the old one)
        """
        self._queue = queue.Queue(self._queue_size)


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
                    future._result = method(*args, **kwargs)

                except Exception as ex:
                    logging.exception("Error executing %s: %s",
                                      method.__name__, ex)

                finally:
                    # Mark the action as executed
                    future._done_event.set()
                    self._queue.task_done()
