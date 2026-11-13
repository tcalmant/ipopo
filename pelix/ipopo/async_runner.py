#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Default IAsyncRunner service: an event loop in a daemon thread, used by iPOPO
to run the coroutine callbacks of the components.

iPOPO registers it as a plain service when it starts, with a ranking of -1, so
that a runner registered with the default ranking (e.g. one using the running
event loop of the environment) is preferred.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.3.0

..

    Copyright 2026 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

from pelix.services import IAsyncRunner

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["ThreadAsyncRunner"]

# ------------------------------------------------------------------------------

T = TypeVar("T")

_logger = logging.getLogger(__name__)

CANCEL_GRACE_DELAY = 1.0
""" Delay, in seconds, after the timeout before warning about a coroutine not cancelled yet """

CLOSE_TIMEOUT = 5.0
""" Maximum time, in seconds, ``close()`` waits for the loop thread to stop """

# ------------------------------------------------------------------------------


class ThreadAsyncRunner(IAsyncRunner):
    """
    Runs coroutines on an event loop owned by a daemon thread.

    The thread and its loop are created on the first call to ``run()`` or
    ``submit()``, never before. ``close()`` cancels the remaining tasks and
    stops the thread: the runner can't be used afterwards.
    """

    def __init__(self, name: str = "ipopo-async", close_timeout: float = CLOSE_TIMEOUT) -> None:
        """
        :param name: Name of the thread of the event loop
        :param close_timeout: Maximum time ``close()`` waits for the loop thread
        """
        self._name = name
        self._close_timeout = close_timeout
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._closed = False

    def is_started(self) -> bool:
        """
        Checks if the event loop thread has been started
        """
        with self._lock:
            return self._thread is not None

    def run(self, coroutine: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
        """
        Runs a coroutine on the event loop and waits for its result

        The timeout is applied in the event loop: this method returns only once
        the coroutine has ended, including its clean up after the cancellation.
        A coroutine blocking the loop with synchronous code can't be cancelled
        before that code returns: a warning is logged after the timeout and a
        grace delay, then the wait goes on.

        Called from the event loop thread itself (a coroutine calling synchronous
        code which ends up here), waiting for the loop would block it forever: the
        coroutine then runs on a temporary event loop, in another thread.

        :param coroutine: The coroutine to run
        :param timeout: Maximum duration of the coroutine, in seconds. None or
                        a value <= 0 waits as long as needed
        :return: The result of the coroutine
        :raise TimeoutError: The coroutine didn't end in time: it has been cancelled
        :raise RuntimeError: The runner has been closed
        """
        if timeout is not None and timeout <= 0:
            timeout = None

        if threading.current_thread() is self._thread:
            _logger.debug("Coroutine run from the event loop thread: using a temporary loop")
            with concurrent.futures.ThreadPoolExecutor(1, f"{self._name}-nested") as executor:
                return executor.submit(lambda: asyncio.run(_with_timeout(coroutine, timeout))).result()

        try:
            future = self.submit(_with_timeout(coroutine, timeout))
        except RuntimeError:
            coroutine.close()
            raise

        if timeout is not None:
            done, _ = concurrent.futures.wait((future,), timeout + CANCEL_GRACE_DELAY)
            if not done:
                _logger.warning(
                    "%r is still running %.1f seconds after its timeout: the event loop is "
                    "blocked by synchronous code. Waiting for it to end.",
                    coroutine,
                    CANCEL_GRACE_DELAY,
                )

        return future.result()

    def submit(self, coroutine: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """
        Schedules a coroutine on the event loop, without waiting for it

        :param coroutine: The coroutine to run
        :return: A future of its result. Cancelling it cancels the coroutine
        :raise RuntimeError: The runner has been closed
        """
        try:
            loop = self._get_loop()
        except RuntimeError:
            # Avoids the "never awaited" warning
            coroutine.close()
            raise
        return asyncio.run_coroutine_threadsafe(coroutine, loop)

    def close(self) -> None:
        """
        Cancels the pending tasks and stops the event loop thread, if started.

        Waits for the thread at most ``close_timeout`` seconds: a coroutine
        blocking the loop with synchronous code delays its stop. The thread
        being a daemon, it doesn't prevent the process from exiting.
        """
        with self._lock:
            self._closed = True
            loop, thread = self._loop, self._thread
            self._loop = None
            self._thread = None

        if loop is not None and thread is not None:
            loop.call_soon_threadsafe(loop.stop)
            if thread is not threading.current_thread():
                thread.join(self._close_timeout)
                if thread.is_alive():
                    _logger.warning(
                        "The event loop thread %s didn't stop within %s seconds: "
                        "a coroutine is blocking it with synchronous code",
                        thread.name,
                        self._close_timeout,
                    )

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """
        Returns the event loop, starting its thread on first call

        :raise RuntimeError: The runner has been closed
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("The asyncio runner has been closed")

            if self._loop is None:
                loop = asyncio.new_event_loop()
                thread = threading.Thread(target=_serve, args=(loop,), name=self._name, daemon=True)
                thread.start()
                self._loop = loop
                self._thread = thread

            return self._loop


async def _with_timeout(coroutine: Coroutine[Any, Any, T], timeout: float | None) -> T:
    """
    Awaits the coroutine, cancelled after the timeout (None to wait forever)

    :raise TimeoutError: The coroutine has been cancelled after the timeout
    """
    deadline = asyncio.timeout(timeout)
    try:
        async with deadline:
            return await coroutine
    except TimeoutError:
        if not deadline.expired():
            # Raised by the coroutine itself
            raise
        raise TimeoutError(f"{coroutine!r} didn't end within {timeout} seconds") from None


def _serve(loop: asyncio.AbstractEventLoop) -> None:
    """
    Runs the event loop until it is stopped, then cancels its remaining tasks
    """
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        loop.close()
