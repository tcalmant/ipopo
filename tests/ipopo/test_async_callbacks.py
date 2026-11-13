#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the coroutine (``async def``) callbacks of iPOPO components

:license: Apache License 2.0
"""

import asyncio
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from pelix.constants import SERVICE_RANKING
from pelix.framework import BundleContext, FrameworkFactory
from pelix.internals.registry import ServiceReference
from pelix.ipopo import async_runner, constants
from pelix.ipopo.async_runner import ThreadAsyncRunner
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.decorators import (
    Bind,
    BindField,
    ComponentFactory,
    ErrorHandler,
    Invalidate,
    Modified,
    PostRegistration,
    PostUnregistration,
    Property,
    Provides,
    Requires,
    Unbind,
    UnbindField,
    Update,
    Validate,
)
from pelix.ipopo.instance import StoredInstance
from pelix.services import SERVICE_ASYNC_RUNNER, IAsyncRunner
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

SPEC_TEST = "ipopo.tests.async.spec"
SPEC_PROVIDED = "ipopo.tests.async.provided"
RUNNER_THREAD = "ipopo-async"

# ------------------------------------------------------------------------------


def loop_threads() -> list[threading.Thread]:
    """
    Returns the event loop threads of iPOPO runners
    """
    return [thread for thread in threading.enumerate() if thread.name == RUNNER_THREAD]


class AsyncCallbacksTest(unittest.TestCase):
    """
    Tests the coroutine callbacks
    """

    def setUp(self) -> None:
        self.start_framework()

    def start_framework(self, properties: dict[str, Any] | None = None) -> None:
        """
        Starts a framework with iPOPO, with the given framework properties
        """
        if getattr(self, "framework", None) is not None:
            FrameworkFactory.delete_framework()
        self.framework = FrameworkFactory.get_framework(properties)
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.context = self.framework.get_bundle_context()

    def tearDown(self) -> None:
        FrameworkFactory.delete_framework()
        self.framework = None
        self.assertEqual([], loop_threads())

    def instantiate(self, factory: type, name: str = "component") -> Any:
        """
        Registers the factory and instantiates it
        """
        self.ipopo.register_factory(self.context, factory)
        return self.ipopo.instantiate(factory.__name__, name, {})

    def record_events(self) -> list[int]:
        """
        Records the kinds of the iPOPO events of the "component" instance
        """
        kinds: list[int] = []

        class Listener:
            def handle_ipopo_event(self, event: constants.IPopoEvent) -> None:
                if event.get_component_name() == "component":
                    kinds.append(event.get_kind())

        self.ipopo.add_listener(Listener())
        return kinds

    def state(self, name: str = "component") -> int:
        """
        Returns the state of a component
        """
        return self.ipopo.get_instance_details(name)["state"]

    def test_validate_invalidate(self) -> None:
        """
        Coroutine @Validate and @Invalidate run to completion on the loop thread
        """

        @ComponentFactory("Lifecycle")
        @Provides(SPEC_PROVIDED)
        class Lifecycle:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            @Validate
            async def validate(self, context: BundleContext) -> None:
                await asyncio.sleep(0.01)
                self.calls.append(("validate", threading.current_thread().name))

            @Invalidate
            async def invalidate(self, context: BundleContext) -> None:
                await asyncio.sleep(0.01)
                self.calls.append(("invalidate", threading.current_thread().name))

        component = self.instantiate(Lifecycle)
        # Validated once the coroutine ended, before the service registration
        self.assertEqual([("validate", RUNNER_THREAD)], component.calls)
        self.assertEqual(StoredInstance.VALID, self.state())
        self.assertIsNotNone(self.context.get_service_reference(SPEC_PROVIDED))

        self.ipopo.kill("component")
        self.assertEqual([("validate", RUNNER_THREAD), ("invalidate", RUNNER_THREAD)], component.calls)
        self.assertIsNone(self.context.get_service_reference(SPEC_PROVIDED))

    def test_bind_unbind(self) -> None:
        """
        Coroutine @Bind and @Unbind run to completion
        """

        @ComponentFactory("Consumer")
        @Requires("_svc", SPEC_TEST)
        class Consumer:
            def __init__(self) -> None:
                self._svc: Any = None
                self.calls: list[tuple[str, Any]] = []

            @Bind
            async def bind(self, svc: Any, ref: ServiceReference[Any]) -> None:
                await asyncio.sleep(0)
                self.calls.append(("bind", svc))

            @Unbind
            async def unbind(self, svc: Any, ref: ServiceReference[Any]) -> None:
                await asyncio.sleep(0)
                self.calls.append(("unbind", self._svc))

        component = self.instantiate(Consumer)
        self.assertEqual(StoredInstance.INVALID, self.state())

        service = object()
        registration = self.context.register_service(SPEC_TEST, service, {})
        self.assertEqual([("bind", service)], component.calls)
        self.assertEqual(StoredInstance.VALID, self.state())

        registration.unregister()
        # The field is still injected during the callback
        self.assertEqual([("bind", service), ("unbind", service)], component.calls)
        self.assertIsNone(component._svc)
        self.assertEqual(StoredInstance.INVALID, self.state())

    def test_other_callbacks(self) -> None:
        """
        Field, update, registration and @Modified callbacks can be coroutines
        """

        @ComponentFactory("Others")
        @Requires("_svc", SPEC_TEST)
        @Provides(SPEC_PROVIDED)
        @Property("_value", "value", 1)
        class Others:
            def __init__(self) -> None:
                self._svc: Any = None
                self._value = 1
                self.calls: list[str] = []

            @BindField("_svc")
            async def bind_field(self, field: str, svc: Any, ref: ServiceReference[Any]) -> None:
                await asyncio.sleep(0)
                self.calls.append("bind_field")

            @UnbindField("_svc")
            async def unbind_field(self, field: str, svc: Any, ref: ServiceReference[Any]) -> None:
                await asyncio.sleep(0)
                self.calls.append("unbind_field")

            @Update
            async def update(self, svc: Any, ref: ServiceReference[Any], old: dict[str, Any]) -> None:
                await asyncio.sleep(0)
                self.calls.append("update")

            @PostRegistration
            async def registered(self, ref: ServiceReference[Any]) -> None:
                await asyncio.sleep(0)
                self.calls.append("registered")

            @PostUnregistration
            async def unregistered(self, ref: ServiceReference[Any]) -> None:
                await asyncio.sleep(0)
                self.calls.append("unregistered")

            @Modified
            async def modified(self, changed: dict[str, Any], previous: dict[str, Any]) -> None:
                await asyncio.sleep(0)
                self.calls.append(f"modified {changed} {previous}")

        component = self.instantiate(Others)
        registration = self.context.register_service(SPEC_TEST, object(), {"x": 1})
        self.assertEqual(["bind_field", "registered"], component.calls)

        registration.set_properties({"x": 2})
        self.ipopo.reconfigure("component", {"value": 2})
        self.assertEqual(["update", "modified {'value': 2} {'value': 1}"], component.calls[2:])

        registration.unregister()
        # Invalidated (service unregistered) before the unbind
        self.assertEqual(["unregistered", "unbind_field"], component.calls[4:])

    def test_validate_error(self) -> None:
        """
        An exception raised by a coroutine @Validate makes the component ERRONEOUS
        """
        error = ValueError("failed after await")

        @ComponentFactory("Failing")
        class Failing:
            @Validate
            async def validate(self, context: BundleContext) -> None:
                await asyncio.sleep(0)
                raise error

        self.instantiate(Failing)
        self.assertEqual(StoredInstance.ERRONEOUS, self.state())
        self.assertIs(error, self.ipopo.get_instance_error("component"))

    def test_error_handler(self) -> None:
        """
        The @ErrorHandler can be a coroutine
        """
        handled: list[tuple[BaseException, str]] = []

        @ComponentFactory("Handled")
        class Handled:
            @Validate
            async def validate(self, context: BundleContext) -> None:
                raise ValueError("validation")

            @ErrorHandler
            async def on_error(self, error: BaseException, event: str) -> bool:
                await asyncio.sleep(0)
                handled.append((error, event))
                return True

        self.instantiate(Handled)
        self.assertEqual(StoredInstance.ERRONEOUS, self.state())
        self.assertEqual(1, len(handled))
        self.assertIsInstance(handled[0][0], ValueError)
        self.assertEqual(constants.IPOPO_CALLBACK_VALIDATE, handled[0][1])

    def test_validate_timeout(self) -> None:
        """
        A coroutine @Validate which doesn't end in time is cancelled and the
        component becomes ERRONEOUS
        """
        self.start_framework({constants.IPOPO_ASYNC_CALLBACK_TIMEOUT: 0.2})
        cancelled = threading.Event()

        @ComponentFactory("Slow")
        @Provides(SPEC_PROVIDED)
        class Slow:
            @Validate
            async def validate(self, context: BundleContext) -> None:
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        self.instantiate(Slow)
        self.assertEqual(StoredInstance.ERRONEOUS, self.state())
        self.assertIsInstance(self.ipopo.get_instance_error("component"), TimeoutError)
        self.assertTrue(cancelled.wait(5))
        self.assertIsNone(self.context.get_service_reference(SPEC_PROVIDED))

        # Can be retried
        self.assertEqual(StoredInstance.ERRONEOUS, self.ipopo.retry_erroneous("component"))

    def test_invalidate_timeout(self) -> None:
        """
        A coroutine @Invalidate which doesn't end in time is cancelled, and the
        component is still invalidated and killed
        """
        self.start_framework({constants.IPOPO_ASYNC_CALLBACK_TIMEOUT: "0.2"})
        cancelled = threading.Event()

        @ComponentFactory("SlowStop")
        @Provides(SPEC_PROVIDED)
        class SlowStop:
            @Invalidate
            async def invalidate(self, context: BundleContext) -> None:
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        self.instantiate(SlowStop)
        self.assertEqual(StoredInstance.VALID, self.state())
        events = self.record_events()

        self.ipopo.kill("component")
        self.assertTrue(cancelled.wait(5))
        self.assertEqual([constants.IPopoEvent.INVALIDATED, constants.IPopoEvent.KILLED], events)
        self.assertFalse(self.ipopo.is_registered_instance("component"))
        self.assertIsNone(self.context.get_service_reference(SPEC_PROVIDED))

    def test_invalidate_cancelled(self) -> None:
        """
        A cancelled coroutine @Invalidate doesn't prevent the invalidation
        """

        @ComponentFactory("Cancelled")
        @Provides(SPEC_PROVIDED)
        @Requires("_svc", SPEC_TEST)
        class Cancelled:
            def __init__(self) -> None:
                self._svc: Any = None

            @Invalidate
            async def invalidate(self, context: BundleContext) -> None:
                task = asyncio.current_task()
                assert task is not None
                task.cancel()
                await asyncio.sleep(0)

        self.instantiate(Cancelled)
        registration = self.context.register_service(SPEC_TEST, object(), {})
        self.assertEqual(StoredInstance.VALID, self.state())
        events = self.record_events()

        registration.unregister()
        self.assertEqual(StoredInstance.INVALID, self.state())
        self.assertIsNone(self.context.get_service_reference(SPEC_PROVIDED))
        self.assertIn(constants.IPopoEvent.INVALIDATED, events)

    def test_unbind_timeout(self) -> None:
        """
        A coroutine @Unbind which doesn't end in time is cancelled, and the
        service is still unbound
        """
        self.start_framework({constants.IPOPO_ASYNC_CALLBACK_TIMEOUT: 0.2})
        cancelled = threading.Event()

        @ComponentFactory("SlowUnbind")
        @Requires("_svc", SPEC_TEST)
        class SlowUnbind:
            def __init__(self) -> None:
                self._svc: Any = None

            @Unbind
            async def unbind(self, svc: Any, ref: ServiceReference[Any]) -> None:
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise

        component = self.instantiate(SlowUnbind)
        registration = self.context.register_service(SPEC_TEST, object(), {})
        reference = registration.get_reference()
        self.assertEqual(StoredInstance.VALID, self.state())

        registration.unregister()
        self.assertTrue(cancelled.wait(5))
        self.assertIsNone(component._svc)
        self.assertEqual(StoredInstance.INVALID, self.state())
        self.assertEqual([], reference.get_using_bundles())

    def test_timeout_property(self) -> None:
        """
        Values of the timeout framework property
        """
        for value, expected in (
            (None, None),
            (0, None),
            (-1, None),
            ("0", None),
            (0.5, 0.5),
            ("2", 2.0),
            ("invalid", constants.IPOPO_ASYNC_CALLBACK_TIMEOUT_DEFAULT),
        ):
            with self.subTest(value=value):
                self.start_framework({constants.IPOPO_ASYNC_CALLBACK_TIMEOUT: value})
                self.assertEqual(expected, self.ipopo._async_timeout)

        # Default value
        self.start_framework()
        self.assertEqual(5.0, self.ipopo._async_timeout)

    def test_custom_runner(self) -> None:
        """
        The best IAsyncRunner service runs the coroutine callbacks, with the
        configured timeout (here, disabled)
        """
        self.start_framework({constants.IPOPO_ASYNC_CALLBACK_TIMEOUT: 0})
        timeouts: list[float | None] = []

        class Runner:
            def run(self, coroutine: Any, timeout: float | None = None) -> Any:
                timeouts.append(timeout)
                return asyncio.run(coroutine)

            def submit(self, coroutine: Any) -> Any:
                raise NotImplementedError

        registration = self.context.register_service(IAsyncRunner, Runner(), {SERVICE_RANKING: 10})

        @ComponentFactory("Waiting")
        class Waiting:
            def __init__(self) -> None:
                self.thread = ""

            @Validate
            async def validate(self, context: BundleContext) -> None:
                await asyncio.sleep(0.3)
                self.thread = threading.current_thread().name

            @Invalidate
            async def invalidate(self, context: BundleContext) -> None:
                pass

        component = self.instantiate(Waiting)
        self.assertEqual(StoredInstance.VALID, self.state())
        self.assertEqual([None], timeouts)
        self.assertEqual(threading.current_thread().name, component.thread)

        # Back to the default runner
        registration.unregister()
        self.ipopo.kill("component")
        self.assertEqual([None], timeouts)
        self.assertEqual(1, len(loop_threads()))

    def test_no_runner(self) -> None:
        """
        Without an IAsyncRunner service, a coroutine @Validate fails
        """
        # Stops tracking the default runner
        self.ipopo._async_runner.close()

        @ComponentFactory("NoRunner")
        class NoRunner:
            @Validate
            async def validate(self, context: BundleContext) -> None:
                pass

        self.instantiate(NoRunner)
        self.assertEqual(StoredInstance.ERRONEOUS, self.state())
        error = self.ipopo.get_instance_error("component")
        self.assertIsInstance(error, RuntimeError)
        self.assertIn("IAsyncRunner", str(error))

    def test_framework_stop(self) -> None:
        """
        Coroutine @Invalidate callbacks run while the framework stops, when the
        services are hidden from lookups
        """
        module = install_bundle(self.framework, "tests.ipopo.async_bundle")
        module.INVALIDATED.clear()

        @ComponentFactory("Stopped")
        class Stopped:
            @Invalidate
            async def invalidate(self, context: BundleContext) -> None:
                await asyncio.sleep(0)
                module.INVALIDATED.append("framework bundle")

        self.instantiate(Stopped)
        self.framework.stop()
        self.assertEqual([RUNNER_THREAD, "framework bundle"], module.INVALIDATED)
        self.assertEqual([], loop_threads())

    def test_lazy_runner(self) -> None:
        """
        No event loop thread is started while no coroutine callback is used
        """

        @ComponentFactory("Sync")
        @Provides(SPEC_PROVIDED)
        @Requires("_svc", SPEC_TEST, optional=True)
        class Sync:
            def __init__(self) -> None:
                self._svc: Any = None

            @Validate
            def validate(self, context: BundleContext) -> None:
                pass

            @Bind
            def bind(self, svc: Any, ref: ServiceReference[Any]) -> None:
                pass

            @Invalidate
            def invalidate(self, context: BundleContext) -> None:
                pass

        self.instantiate(Sync)
        registration = self.context.register_service(SPEC_TEST, object(), {})
        registration.unregister()
        self.ipopo.kill("component")
        self.assertEqual([], loop_threads())

        @ComponentFactory("Async")
        class Async:
            @Validate
            async def validate(self, context: BundleContext) -> None:
                pass

        self.instantiate(Async, "async")
        self.assertEqual(1, len(loop_threads()))

        # Stopping iPOPO stops the loop
        self.framework.stop()
        self.assertEqual([], loop_threads())

    def test_runner_service(self) -> None:
        """
        The default runner is a plain service registered by iPOPO, not a
        component, which doesn't start its loop
        """
        self.assertEqual([], self.ipopo.get_factories())
        self.assertEqual([], self.ipopo.get_instances())
        reference = self.context.get_service_reference(IAsyncRunner)
        self.assertIsNotNone(reference)
        assert reference is not None
        self.assertIn(SERVICE_ASYNC_RUNNER, reference.get_property("objectClass"))
        self.assertEqual(-1, reference.get_property(SERVICE_RANKING))
        runner = self.context.get_service(reference)
        self.assertEqual([], loop_threads())

        async def compute(value: int) -> tuple[int, str]:
            await asyncio.sleep(0)
            return value * 2, threading.current_thread().name

        self.assertEqual((42, RUNNER_THREAD), runner.run(compute(21)))
        self.assertEqual((4, RUNNER_THREAD), runner.submit(compute(2)).result(5))

        with self.assertRaises(TimeoutError):
            runner.run(asyncio.sleep(30), 0.1)

        with self.assertRaises(ZeroDivisionError):
            runner.run(_divide())

        # Unregistered with iPOPO, and closed
        self.context.unget_service(reference)
        self.framework.stop()
        self.assertEqual([], loop_threads())
        coroutine = compute(1)
        with self.assertRaises(RuntimeError):
            runner.run(coroutine)

    def test_nested_callbacks(self) -> None:
        """
        A coroutine callback registering a service consumed by another
        component with a coroutine @Bind doesn't block the loop
        """

        @ComponentFactory("Consumer")
        @Requires("_svc", SPEC_TEST)
        class Consumer:
            def __init__(self) -> None:
                self._svc: Any = None
                self.bound = False

            @Bind
            async def bind(self, svc: Any, ref: ServiceReference[Any]) -> None:
                await asyncio.sleep(0)
                self.bound = True

        @ComponentFactory("Registering")
        class Registering:
            @Validate
            async def validate(self, context: BundleContext) -> None:
                await asyncio.sleep(0)
                context.register_service(SPEC_TEST, object(), {})

        consumer = self.instantiate(Consumer, "consumer")
        self.instantiate(Registering)
        self.assertEqual(StoredInstance.VALID, self.state())
        self.assertTrue(consumer.bound)
        self.assertEqual(StoredInstance.VALID, self.state("consumer"))

    def test_validate_calls_ipopo(self) -> None:
        """
        A coroutine @Validate calling the iPOPO service fails at once with a
        RuntimeError instead of a deadlock, without side effects afterwards
        """

        @ComponentFactory("plain")
        class Plain:
            pass

        self.ipopo.register_factory(self.context, Plain)

        for timeout in (2, 0):
            with self.subTest(timeout=timeout):
                self.start_framework({constants.IPOPO_ASYNC_CALLBACK_TIMEOUT: timeout})
                self.ipopo.register_factory(self.context, Plain)

                @ComponentFactory("Caller")
                class Caller:
                    @Validate
                    async def validate(self, context: BundleContext) -> None:
                        with use_ipopo(context) as ipopo:
                            ipopo.instantiate("plain", "inner")

                start = time.monotonic()
                self.instantiate(Caller)
                self.assertLess(time.monotonic() - start, 1)
                self.assertEqual(StoredInstance.ERRONEOUS, self.state())
                error = self.ipopo.get_instance_error("component")
                self.assertIsInstance(error, RuntimeError)
                self.assertIn("Deadlock avoided", str(error))

                time.sleep(0.2)
                self.assertFalse(self.ipopo.is_registered_instance("inner"))

    def test_validate_calls_ipopo_in_thread(self) -> None:
        """
        A coroutine @Validate awaiting a thread which calls the iPOPO service
        fails the same way
        """

        @ComponentFactory("ThreadCaller")
        class ThreadCaller:
            @Validate
            async def validate(self, context: BundleContext) -> None:
                with use_ipopo(context) as ipopo:
                    await asyncio.to_thread(ipopo.get_instances)

        self.instantiate(ThreadCaller)
        self.assertEqual(StoredInstance.ERRONEOUS, self.state())
        self.assertIsInstance(self.ipopo.get_instance_error("component"), RuntimeError)

    def test_loop_blocked_by_other_task(self) -> None:
        """
        Another task of the loop waiting for a lock held by a thread which
        waits for a coroutine callback on that loop fails instead of a deadlock
        """
        started = threading.Event()

        @ComponentFactory("Waiting")
        class Waiting:
            @Validate
            async def validate(self, context: BundleContext) -> None:
                started.set()
                await asyncio.sleep(0.5)

        thread = threading.Thread(target=self.instantiate, args=(Waiting,))
        thread.start()
        self.assertTrue(started.wait(5))

        ipopo = self.ipopo

        async def list_instances() -> Any:
            return ipopo.get_instances()

        reference = self.context.get_service_reference(IAsyncRunner)
        assert reference is not None
        runner = self.context.get_service(reference)
        with self.assertRaises(RuntimeError):
            runner.submit(list_instances()).result(5)

        thread.join(5)
        self.assertEqual(StoredInstance.VALID, self.state())

    def test_ipopo_from_own_thread(self) -> None:
        """
        A thread of the coroutine, not awaited by it, calls the iPOPO service
        once the validation is over
        """
        done = threading.Event()

        @ComponentFactory("plain")
        class Plain:
            pass

        @ComponentFactory("Starter")
        class Starter:
            @Validate
            async def validate(self, context: BundleContext) -> None:
                def instantiate() -> None:
                    with use_ipopo(context) as ipopo:
                        ipopo.instantiate("plain", "inner")
                    done.set()

                threading.Thread(target=instantiate).start()

        self.ipopo.register_factory(self.context, Plain)
        self.instantiate(Starter)
        self.assertTrue(done.wait(5))
        self.assertEqual(StoredInstance.VALID, self.state())
        self.assertEqual(StoredInstance.VALID, self.state("inner"))

    def test_timeout_waits_for_cleanup(self) -> None:
        """
        On timeout, iPOPO goes on only once the cancelled coroutine has ended,
        including its clean up
        """
        self.start_framework({constants.IPOPO_ASYNC_CALLBACK_TIMEOUT: 0.2})
        cleaned = threading.Event()

        @ComponentFactory("SlowCleanup")
        class SlowCleanup:
            @Validate
            async def validate(self, context: BundleContext) -> None:
                try:
                    await asyncio.sleep(30)
                finally:
                    await asyncio.sleep(0.3)
                    cleaned.set()

        self.instantiate(SlowCleanup)
        self.assertTrue(cleaned.is_set())
        self.assertEqual(StoredInstance.ERRONEOUS, self.state())
        self.assertIsInstance(self.ipopo.get_instance_error("component"), TimeoutError)

    def test_own_timeout_error(self) -> None:
        """
        A TimeoutError raised by the coroutine itself is kept as is
        """
        runner = ThreadAsyncRunner("test-own-timeout")
        self.addCleanup(runner.close)

        async def fail() -> None:
            raise TimeoutError("own")

        with self.assertRaises(TimeoutError) as ctx:
            runner.run(fail(), 5)
        self.assertEqual("own", str(ctx.exception))

    def test_blocked_loop(self) -> None:
        """
        A coroutine blocking the loop past its timeout is waited for, with a
        warning
        """
        runner = ThreadAsyncRunner("test-blocked-run")
        self.addCleanup(runner.close)

        async def blocking() -> str:
            # Blocks the loop on purpose
            time.sleep(0.5)  # noqa: ASYNC251
            return "ended"

        with (
            mock.patch.object(async_runner, "CANCEL_GRACE_DELAY", 0.1),
            self.assertLogs(async_runner.__name__, "WARNING"),
        ):
            self.assertEqual("ended", runner.run(blocking(), 0.1))

    def test_close_timeout(self) -> None:
        """
        Closing the runner doesn't wait forever for a loop blocked by
        synchronous code
        """
        runner = ThreadAsyncRunner("test-blocked-close", close_timeout=0.2)
        started = threading.Event()

        async def blocking() -> None:
            started.set()
            # Blocks the loop on purpose
            time.sleep(1)  # noqa: ASYNC251

        runner.submit(blocking())
        self.assertTrue(started.wait(5))
        threads = [thread for thread in threading.enumerate() if thread.name == "test-blocked-close"]
        self.assertEqual(1, len(threads))

        start = time.monotonic()
        with self.assertLogs(async_runner.__name__, "WARNING"):
            runner.close()
        self.assertLess(time.monotonic() - start, 0.8)
        self.assertTrue(threads[0].daemon)
        threads[0].join(5)

    def test_type_checker_accepts_coroutines(self) -> None:
        """
        ty accepts coroutine functions decorated with the callback decorators
        """
        ty = shutil.which("ty", path=str(Path(sys.executable).parent))
        if ty is None:
            self.skipTest("ty is not installed")

        source = (
            "from typing import Any\n"
            "from pelix.framework import BundleContext\n"
            "from pelix.internals.registry import ServiceReference\n"
            "from pelix.ipopo.decorators import Bind, ComponentFactory, Invalidate, Validate\n\n"
            '@ComponentFactory("x")\n'
            "class X:\n"
            "    @Validate\n"
            "    async def validate(self, context: BundleContext) -> None: ...\n\n"
            "    @Invalidate\n"
            "    async def invalidate(self, context: BundleContext) -> None: ...\n\n"
            "    @Bind\n"
            "    async def bind(self, svc: Any, ref: ServiceReference[Any]) -> None: ...\n"
        )
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case.py"
            case.write_text(source)
            done = subprocess.run(
                [ty, "check", "--python", sys.prefix, "--extra-search-path", str(root), str(case)],
                capture_output=True,
                text=True,
                cwd=tmp,
                check=False,
            )
        self.assertEqual(0, done.returncode, done.stdout)


async def _divide() -> float:
    """
    Raises a ZeroDivisionError after an await
    """
    await asyncio.sleep(0)
    return 1 / 0


if __name__ == "__main__":
    unittest.main()
