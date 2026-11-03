#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests BundleContext.wait_registered()

:author: Thomas Calmant
"""

import threading
import time
import unittest
from typing import Any

from pelix.constants import BundleException, Specification
from pelix.framework import FrameworkFactory

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------

SPEC_A = "test.wait.a"
SPEC_B = "test.wait.b"


@Specification(SPEC_B)
class SpecB:
    pass


class WaitRegisteredTest(unittest.TestCase):
    """
    Tests the wait for services registration
    """

    def setUp(self):
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        # Records the listeners of wait_registered() and tells when it listens
        self.listeners: list[Any] = []
        self.listening = threading.Event()
        add_service_listener = self.context.add_service_listener

        def add_listener(listener, *args, **kwargs):
            result = add_service_listener(listener, *args, **kwargs)
            self.listeners.append(listener)
            self.listening.set()
            return result

        self.context.add_service_listener = add_listener

        self.stop_listeners: list[Any] = []
        add_stop_listener = self.context.add_framework_stop_listener

        def add_framework_listener(listener):
            self.stop_listeners.append(listener)
            return add_stop_listener(listener)

        self.context.add_framework_stop_listener = add_framework_listener

    def tearDown(self):
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def _wait_in_thread(self, *args: Any, **kwargs: Any) -> tuple[threading.Thread, list[Any]]:
        """
        Calls wait_registered() in a thread and returns once it listens to
        the service events. The result holds the references or the exception.
        """
        context = self.context
        self.listening.clear()
        result: list[Any] = []

        def wait() -> None:
            try:
                result.append(context.wait_registered(*args, **kwargs))
            except (BundleException, TimeoutError) as ex:
                result.append(ex)

        thread = threading.Thread(target=wait, daemon=True)
        thread.start()
        self.assertTrue(self.listening.wait(5), "wait_registered() did not listen to service events")
        return thread, result

    def _join(self, thread: threading.Thread, result: list[Any]) -> Any:
        thread.join(5)
        self.assertFalse(thread.is_alive(), "wait_registered() did not return")
        return result[0]

    def test_already_registered(self):
        """
        Returns at once when the services are already there, even without delay
        """
        reg_a = self.context.register_service(SPEC_A, object(), {})
        reg_b = self.context.register_service(SPEC_B, object(), {})

        self.assertEqual(
            [reg_a.get_reference(), reg_b.get_reference()],
            self.context.wait_registered([SPEC_A, SPEC_B], timeout=0),
        )
        self.assertEqual([reg_a.get_reference()], self.context.wait_registered(SPEC_A))

    def test_registered_later(self):
        """
        Wakes up when the service is registered
        """
        thread, result = self._wait_in_thread(SPEC_A, timeout=5)
        self.assertTrue(thread.is_alive())

        reg = self.context.register_service(SPEC_A, object(), {})
        self.assertEqual([reg.get_reference()], self._join(thread, result))

    def test_multiple_specifications(self):
        """
        Waits for all the specifications, returns their references in order
        """
        thread, result = self._wait_in_thread([SPEC_B, SPEC_A], timeout=5)
        reg_a = self.context.register_service(SPEC_A, object(), {})
        thread.join(0.2)
        self.assertTrue(thread.is_alive(), "returned before all specifications were registered")

        reg_b = self.context.register_service(SPEC_B, object(), {})
        self.assertEqual([reg_b.get_reference(), reg_a.get_reference()], self._join(thread, result))

    def test_class_specification(self):
        """
        Accepts classes, which stand for their specifications
        """
        thread, result = self._wait_in_thread(SpecB, timeout=5)
        reg = self.context.register_service(SpecB, object(), {})
        self.assertEqual([reg.get_reference()], self._join(thread, result))

    def test_best_reference(self):
        """
        Returns the best ranked service of each specification
        """
        self.context.register_service(SPEC_A, object(), {"service.ranking": 1})
        best = self.context.register_service(SPEC_A, object(), {"service.ranking": 10})
        self.assertEqual([best.get_reference()], self.context.wait_registered(SPEC_A, timeout=0))

    def test_filter(self):
        """
        Only the services matching the filter count
        """
        self.context.register_service(SPEC_A, object(), {"answer": 1})
        thread, result = self._wait_in_thread(SPEC_A, "(answer=42)", timeout=5)

        self.context.register_service(SPEC_A, object(), {"answer": 2})
        thread.join(0.2)
        self.assertTrue(thread.is_alive(), "returned for a service not matching the filter")

        reg = self.context.register_service(SPEC_A, object(), {"answer": 42})
        self.assertEqual([reg.get_reference()], self._join(thread, result))

    def test_filter_modified(self):
        """
        A service whose properties change to match the filter counts
        """
        reg = self.context.register_service(SPEC_A, object(), {"answer": 1})
        thread, result = self._wait_in_thread(SPEC_A, "(answer=42)", timeout=5)

        reg.set_properties({"answer": 42})
        self.assertEqual([reg.get_reference()], self._join(thread, result))

    def test_timeout(self):
        """
        Raises a TimeoutError naming the missing specifications
        """
        self.context.register_service(SPEC_A, object(), {})
        start = time.monotonic()
        with self.assertRaises(TimeoutError) as ctx:
            self.context.wait_registered([SPEC_A, SPEC_B], timeout=0.2)

        self.assertGreaterEqual(time.monotonic() - start, 0.2)
        self.assertIn(SPEC_B, str(ctx.exception))
        self.assertNotIn(SPEC_A, str(ctx.exception))

    def test_unregistered_before_match(self):
        """
        A service unregistered before the others arrive no longer counts
        """
        thread, result = self._wait_in_thread([SPEC_A, SPEC_B], timeout=0.5)
        self.context.register_service(SPEC_A, object(), {}).unregister()
        self.context.register_service(SPEC_B, object(), {})

        error = self._join(thread, result)
        self.assertIsInstance(error, TimeoutError)
        self.assertIn(SPEC_A, str(error))
        self.assertNotIn(SPEC_B, str(error))

    def test_framework_stop(self):
        """
        Raises a BundleException when the framework stops while waiting
        """
        thread, result = self._wait_in_thread(SPEC_A)
        self.framework.stop()
        self.assertIsInstance(self._join(thread, result), BundleException)

    def test_listeners_removed(self):
        """
        The listeners are removed once the wait is over, whatever its result
        """
        thread, result = self._wait_in_thread(SPEC_A, timeout=5)
        self.context.register_service(SPEC_A, object(), {})
        self._join(thread, result)

        thread, result = self._wait_in_thread(SPEC_B, timeout=0.1)
        self.assertIsInstance(self._join(thread, result), TimeoutError)

        self.assertEqual(2, len(self.listeners))
        for listener in self.listeners:
            self.assertFalse(self.context.remove_service_listener(listener))
            self.assertFalse(self.context.remove_framework_stop_listener(listener))

    def test_invalid_arguments(self):
        """
        Refuses invalid or empty specifications
        """
        self.context.register_service(SPEC_A, object(), {})
        for specifications in ([], "", "bad(name)", [SPEC_A, " "], [SPEC_A, None]):
            with self.assertRaises(BundleException):
                self.context.wait_registered(specifications, timeout=0)

    def test_invalid_filter(self):
        """
        Refuses an invalid filter, without leaving its listeners behind
        """
        with self.assertRaises(BundleException):
            self.context.wait_registered(SPEC_A, "(invalid", timeout=0)

        self.assertEqual(1, len(self.stop_listeners))
        self.assertFalse(self.context.remove_framework_stop_listener(self.stop_listeners[0]))


if __name__ == "__main__":
    unittest.main()
