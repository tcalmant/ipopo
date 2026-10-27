.. _refcard_typedevent:

Typed Event service
###################

Description
===========

The Typed Event bus is a publish/subscribe service inspired by the OSGi Typed
Event specification (chapter 157). Where :ref:`EventAdmin <refcard_eventadmin>`
carries a topic and a dictionary, the Typed Event bus carries a *typed* event: a
dataclass instance. Handlers declare the type they want and receive it.

It lives in the ``pelix.services.typedevent`` bundle, as a single iPOPO component
(factory ``pelix-services-typedevent-factory``), which provides two services:

* ``TypedEventBus`` (``pelix.services.typedevent``) to deliver events
* ``TypedEventMonitor`` (``pelix.services.typedevent.monitor``) to read the history

.. code-block:: python

    import pelix.framework
    import pelix.services
    from pelix.ipopo.constants import use_ipopo

    framework = pelix.framework.create_framework(
        ["pelix.ipopo.core", "pelix.services.typedevent"]
    )
    framework.start()
    with use_ipopo(framework.get_bundle_context()) as ipopo:
        ipopo.instantiate(pelix.services.FACTORY_TYPED_EVENT_BUS, "typed-events", {})

The component accepts the following properties:

============ ============= ====================================================
Property     Default value Description
============ ============= ====================================================
pool.threads 10            Number of threads of the pool used for asynchronous delivery
history.size 0             Number of events kept for the monitor (0: no history)
============ ============= ====================================================

Delivering events
=================

.. code-block:: python

    import dataclasses

    @dataclasses.dataclass(frozen=True)
    class ChunkChanged:
        chunk_id: int
        kind: str = "update"

    bus.deliver(ChunkChanged(7))               # asynchronous
    bus.deliver(ChunkChanged(7), sync=True)    # handlers called before returning
    bus.deliver(ChunkChanged(7), topic="chunks/changed")
    bus.deliver_untyped("chunks/changed", {"chunk_id": 7})

The topic is the one given, else the fully qualified name of the class with ``.``
replaced by ``/`` (``mypackage/events/ChunkChanged``, OSGi 157.3.2). A class
defined inside a function has no such name: give a topic. Topics follow the OSGi
grammar ``token ( '/' token )*`` where a token has letters, digits, ``_`` and ``-``;
``deliver()`` raises ``ValueError`` otherwise.

Asynchronous delivery runs on the thread pool. The events delivered by a thread
reach a given handler in delivery order; different handlers work concurrently.
With ``sync=True``, the handlers are called in the calling thread, in the
context of the caller (context variables, open transaction, ...) and the event
is delivered even if no thread is available. ``raise_errors=True`` (with
``sync``) raises an :class:`~pelix.services.eventdelivery.EventDeliveryError`
after all the handlers were notified if some failed; otherwise failures are only
logged.

.. note:: Synchronous delivery and ``raise_errors`` are extensions: in OSGi,
   delivery is always asynchronous.

Handlers
========

All handlers are services found at each delivery (whiteboard pattern).

Typed handlers
--------------

A service of ``pelix.services.TypedEventHandler``, with a ``notify(topic, event)``
method. The type it wants is, in this order:

* its ``event.type`` property: a class or its fully qualified name
* the annotation of the ``event`` parameter of ``notify()``

A handler for which no type can be found is ignored and a warning is logged.

.. code-block:: python

    @ComponentFactory()
    @Provides(pelix.services.SERVICE_TYPED_EVENT_HANDLER)
    class ChunkView:
        def notify(self, topic: str, event: ChunkChanged) -> None:
            ...

Without an ``event.topics`` property, the handler gets the events on the default
topic of its type. When the event is an instance of the handler's type, the
handler gets *the same object* (so an identity, like a handle, crosses the bus;
make events immutable, as all handlers share the object). Otherwise (event delivered
by ``deliver_untyped()``, or of another class), the handler type is built from the
fields it declares, ignoring extra keys; a handler whose event cannot be built
fails like any failing handler.

Untyped handlers
----------------

A service of ``pelix.services.UntypedEventHandler``, with a
``notify_untyped(topic, data)`` method, where ``data`` is an immutable mapping
(:class:`~pelix.services.eventdelivery.EventProperties`). It must declare
``event.topics``, else it receives nothing.

Unhandled event handlers
------------------------

A service of ``pelix.services.UnhandledEventHandler``, with a
``notify_unhandled(topic, data)`` method, called when no typed or untyped handler
matched the event (topic and filter).

Selecting events
----------------

============ =========== ======================================================
Property     Type        Description
============ =========== ======================================================
event.topics List of str Topic scopes: a topic (``a/b``), a prefix (``a/b/*``, which does not match ``a/b``) or ``*``. Invalid scopes are ignored with a warning
event.filter str         LDAP filter tested on the fields of the event and on its topic (``event.topics`` property)
event.type   str / type  Type of a typed handler
============ =========== ======================================================

Matching is case-sensitive. A filter cannot reach inside a nested value.

History
=======

With ``history.size`` above 0, the ``TypedEventMonitor`` service returns the last
events, oldest first, as :class:`pelix.services.MonitorEvent` (topic, immutable
data, time). It is a snapshot, not a push stream as in OSGi.

.. code-block:: python

    for evt in monitor.history(10):
        print(evt.time, evt.topic, evt.data)

Differences with the OSGi Typed Event
=====================================

* Event types are dataclasses; the OSGi converter (beans, DTO, maps) is not
  implemented, only the dataclass-to-mapping and mapping-to-dataclass conversions.
* Events are not forwarded to EventAdmin handlers, nor the reverse.
* No deny-listing of failing handlers, no ``TopicPermission`` checks, no
  ``PushStream`` monitor.
