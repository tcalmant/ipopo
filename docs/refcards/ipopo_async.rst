.. _refcard_ipopo_async:

Coroutine callbacks
===================

The life-cycle and injection callbacks of a component can be coroutine
functions (``async def``).
iPOPO runs the coroutine until it ends before going on, so that the life-cycle
of the component is the same as with a synchronous callback: the component is
validated, and its services registered, once the coroutine of ``@Validate`` has
ended.
An exception raised by the coroutine is handled as if it was raised by a
synchronous callback: it makes the component ``ERRONEOUS`` in ``@Validate``,
and it is logged and ignored elsewhere.

.. code-block:: python

   from pelix.framework import BundleContext
   from pelix.ipopo.decorators import ComponentFactory, Invalidate, Validate


   @ComponentFactory("client-factory")
   class Client:
       @Validate
       async def validate(self, context: BundleContext) -> None:
           self._session = await open_session()

       @Invalidate
       async def invalidate(self, context: BundleContext) -> None:
           await self._session.close()

The decorators accepting a coroutine function are ``@Validate``,
``@ValidateComponent``, ``@Invalidate``, ``@InvalidateComponent``, ``@Bind``,
``@Update``, ``@Unbind``, ``@BindField``, ``@UpdateField``, ``@UnbindField``,
``@PostRegistration``, ``@PostUnregistration``, ``@Modified`` and
``@ErrorHandler``.
Synchronous callbacks are called as before.

Event loop
----------

iPOPO doesn't own an event loop: it runs the coroutines with the best
``pelix.services.IAsyncRunner`` service (specification
``pelix.services.async_runner``), *i.e.* the one with the highest ranking.
iPOPO keeps that service while the framework stops, so that the coroutine
``@Invalidate`` callbacks still run then.

When it starts, iPOPO registers the default runner, a plain service (not a
component) which runs the coroutines on an event loop in a daemon thread.
That thread is only started when a coroutine is run for the first time: a
framework without coroutine callbacks doesn't start it.
The default runner is registered with a ranking of ``-1``: a runner registered
with the default ranking, *e.g.* one using the event loop of an environment
which can't start threads, replaces it.
It is closed when iPOPO stops, after all the components have been killed.
Closing it waits at most 5 seconds for its thread, then logs a warning: a
coroutine blocking the loop doesn't prevent the framework from stopping.

Without an ``IAsyncRunner`` service, a coroutine callback fails with a
``RuntimeError``: a component whose ``@Validate`` is a coroutine becomes
``ERRONEOUS``.

Limitations
-----------

The callbacks are still run in a blocking way: the thread calling the
callback waits for the coroutine to end while it holds the locks of iPOPO and
of the component instance.

* **Don't call the iPOPO service from a coroutine callback** (``instantiate()``,
  ``kill()``, ``retry_erroneous()``, ``get_instances()``...), directly or from
  a thread it awaits (``asyncio.to_thread()``).
  It would wait for those locks, held by the thread waiting for the coroutine:
  iPOPO detects it and raises a ``RuntimeError`` in the coroutine at once,
  instead of a deadlock.
  With a ``@Validate``, the component becomes ``ERRONEOUS`` and nothing has
  been done by the call.
  Use a synchronous callback to do that, or a thread of your own which the
  coroutine doesn't wait for: its call to iPOPO waits for the end of the
  validation.
  The lock of the component is checked the same way: a service event the
  component itself must handle while its coroutine callback runs (*e.g.* a
  service registered by its coroutine ``@Validate`` and consumed by the
  component) fails with that error, logged by the framework, and the component
  misses that event.
  Other locks, such as the ones of the framework while it starts a bundle, or
  your own, aren't checked: a coroutine must not wait for another thread which
  needs them.
* **One loop for all the components**: with the default runner, all the
  coroutine callbacks share the same event loop. A coroutine calling blocking
  code (``time.sleep()``, a blocking driver...) blocks every other coroutine
  callback meanwhile, and can't be cancelled by the timeout before that code
  returns.
* **Nested callbacks run on a temporary loop**: when synchronous code called by
  a coroutine leads to another coroutine callback (for example, a coroutine
  registering a service consumed by a component with an ``async def``
  ``@Bind`` method), the latter runs on a temporary event loop in another
  thread, as the loop of iPOPO is busy.
  Objects bound to the main loop (an ``aiohttp`` session created in
  ``@Validate``, an ``asyncio.Lock``, a queue...) can't be used from such a
  nested callback.

A non-blocking validation, where iPOPO releases its locks while the coroutine
runs and completes the validation once it has ended, would lift the first
limitation: it is planned as a later step.

Timeout
-------

A coroutine callback can't run forever: it is cancelled after a timeout given
by a framework property.

=================================== ======= ====================================
Property                            Default Description
=================================== ======= ====================================
pelix.ipopo.async.callback_timeout  5       Maximum duration of a coroutine
                                            callback, in seconds. A value lesser
                                            than or equal to 0, or ``None``,
                                            disables the timeout
=================================== ======= ====================================

The property is read once, when iPOPO starts: changing it afterwards has no
effect until iPOPO is restarted.

When the timeout expires, the coroutine is cancelled and a ``TimeoutError`` is
raised in its place: a component whose ``@Validate`` timed out becomes
``ERRONEOUS``, and ``get_instance_error()`` returns that ``TimeoutError``.
The timeout is applied in the event loop, and iPOPO goes on only once the
cancelled coroutine has ended, including its ``finally`` blocks: it never runs
concurrently with what iPOPO does next.
A coroutine blocking the loop with synchronous code can only be cancelled once
that code returns: iPOPO logs a warning one second after the timeout, and keeps
waiting.

An ``@Invalidate`` or ``@Unbind`` coroutine which times out, or which is
cancelled, doesn't prevent the invalidation: the error is logged, the services
of the component are unregistered and the injected service is released as with
a synchronous callback which raised an exception.

Async runner service
--------------------

Components can also use the ``IAsyncRunner`` service to run their own
coroutines from synchronous code.
Getting the default runner service doesn't start its loop.

.. code-block:: python

   from pelix.ipopo.decorators import ComponentFactory, Requires
   from pelix.services import IAsyncRunner


   @ComponentFactory("poller-factory")
   @Requires("_runner", IAsyncRunner)
   class Poller:
       _runner: IAsyncRunner

       def poll(self) -> dict:
           # Waits for the result, at most 10 seconds
           return self._runner.run(fetch_status(), timeout=10)

       def poll_later(self) -> None:
           # Returns a concurrent.futures.Future
           self._runner.submit(fetch_status())

.. autoclass:: pelix.services.IAsyncRunner
   :members: run, submit
