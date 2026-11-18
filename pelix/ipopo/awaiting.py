#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Deadlock guard of the coroutine callbacks.

The thread calling a coroutine callback holds the iPOPO and instance locks
while it waits for the coroutine to end. If that coroutine, or the event loop
running it, then waits for one of those locks (e.g. an ``async def @Validate``
calling ``ipopo.instantiate()``), neither can go on. The locks of iPOPO raise a
``RuntimeError`` in that case instead of blocking forever.

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
import contextlib
import contextvars
import threading
from collections.abc import Coroutine, Generator
from types import TracebackType
from typing import Any, TypeVar

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["CallbackLock", "awaiting_callback"]

# ------------------------------------------------------------------------------

T = TypeVar("T")

CHECK_DELAY = 0.05
""" Interval, in seconds, between two deadlock checks while waiting for a lock """


class _AwaitedCallback:
    """
    A coroutine callback, the thread waiting for it and its event loop
    """

    __slots__ = ("loop", "thread")

    def __init__(self) -> None:
        self.thread = threading.get_ident()
        # Known once the coroutine has started
        self.loop: asyncio.AbstractEventLoop | None = None


# Thread ident -> coroutine callbacks it waits for
_AWAITED: dict[int, list[_AwaitedCallback]] = {}
_AWAITED_LOCK = threading.Lock()

# The coroutine callback the current task (or a thread it started with
# asyncio.to_thread()) belongs to
_CURRENT: contextvars.ContextVar[_AwaitedCallback | None] = contextvars.ContextVar(
    "ipopo_awaited_callback", default=None
)


@contextlib.contextmanager
def awaiting_callback(
    coroutine: Coroutine[Any, Any, T],
) -> Generator[Coroutine[Any, Any, T], None, None]:
    """
    Declares that the current thread waits for the given coroutine callback
    while the context is active

    :param coroutine: The coroutine returned by a component callback
    :return: The coroutine to run in place of the given one
    """
    awaited = _AwaitedCallback()
    with _AWAITED_LOCK:
        _AWAITED.setdefault(awaited.thread, []).append(awaited)
    try:
        yield _track(awaited, coroutine)
    finally:
        if awaited.loop is None:
            # Never started (e.g. the runner is closed): avoids the "never awaited" warning
            coroutine.close()

        with _AWAITED_LOCK:
            waits = _AWAITED[awaited.thread]
            waits.remove(awaited)
            if not waits:
                del _AWAITED[awaited.thread]


async def _track(awaited: _AwaitedCallback, coroutine: Coroutine[Any, Any, T]) -> T:
    """
    Runs the coroutine, knowing its event loop
    """
    awaited.loop = asyncio.get_running_loop()
    _CURRENT.set(awaited)
    return await coroutine


def _would_deadlock(owner: int) -> bool:
    """
    Checks if the current thread waiting for a lock held by the given thread
    would wait forever: the owner waits for the coroutine callback the current
    thread works for, or for a coroutine callback on the event loop the current
    thread runs
    """
    with _AWAITED_LOCK:
        waits = list(_AWAITED.get(owner, ()))
    if not waits:
        return False

    if _CURRENT.get() in waits:
        return True

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    return any(awaited.loop is loop for awaited in waits)


class CallbackLock:
    """
    A reentrant lock which raises a ``RuntimeError`` instead of waiting for
    a thread which itself waits for the coroutine callback asking for the lock
    """

    __slots__ = ("_count", "_lock", "_name", "_owner")

    def __init__(self, name: str) -> None:
        """
        :param name: Name of the lock, for the error message
        """
        self._name = name
        self._lock = threading.RLock()
        self._owner: int | None = None
        self._count = 0

    def acquire(self) -> bool:
        """
        Acquires the lock

        :raise RuntimeError: Waiting for the lock would never end
        """
        current = threading.get_ident()
        if self._owner != current and not self._lock.acquire(blocking=False):
            while not self._lock.acquire(timeout=CHECK_DELAY):
                owner = self._owner
                if owner is not None and _would_deadlock(owner):
                    raise RuntimeError(
                        f"Deadlock avoided: a coroutine callback, or its event loop, can't wait for the "
                        f"{self._name} lock, held by the thread waiting for that callback. Don't call the "
                        "iPOPO service, or code needing that component, from a coroutine callback"
                    )
        elif self._owner == current:
            self._lock.acquire()

        self._owner = current
        self._count += 1
        return True

    def release(self) -> None:
        """
        Releases the lock
        """
        self._count -= 1
        if not self._count:
            self._owner = None
        self._lock.release()

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
