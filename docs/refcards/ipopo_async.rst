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

The coroutines run on a single event loop owned by iPOPO, in a dedicated
daemon thread.
The thread is only started when a coroutine is run for the first time: a
framework without coroutine callbacks doesn't start it.
It is stopped with the iPOPO bundle.

The thread calling the callback, which holds the lock of the component
instance, waits for the coroutine to end.
The coroutine must therefore not wait for another thread which needs that same
component, *e.g.* to bind it to a service.
When synchronous code called by a coroutine leads to another coroutine
callback (for example, a coroutine registering a service consumed by a
component with an ``async def`` ``@Bind`` method), the latter runs on a
temporary event loop in another thread, as the loop of iPOPO is busy.

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

When the timeout expires, the coroutine is cancelled and a ``TimeoutError`` is
raised in its place: a component whose ``@Validate`` timed out becomes
``ERRONEOUS``, and ``get_instance_error()`` returns that ``TimeoutError``.

An ``@Invalidate`` or ``@Unbind`` coroutine which times out, or which is
cancelled, doesn't prevent the invalidation: the error is logged, the services
of the component are unregistered and the injected service is released as with
a synchronous callback which raised an exception.

Async runner service
--------------------

The event loop of iPOPO is available to the components as the
``pelix.services.IAsyncRunner`` service (specification
``pelix.services.async_runner``), to run their own coroutines from synchronous
code.
Getting the service doesn't start the loop.

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
