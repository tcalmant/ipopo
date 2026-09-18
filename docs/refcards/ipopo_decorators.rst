.. _refcard_decorators:
.. module:: pelix.ipopo.decorators

iPOPO Decorators
================

Component definition
--------------------

Those decorators describe the component.
They must decorate the factory class itself.


Factory definition
^^^^^^^^^^^^^^^^^^

The factory definition decorator must be unique per class and must always be
the last one executed, *i.e.* the top one in the source code.

.. autoclass:: ComponentFactory
.. autoclass:: SingletonFactory


Component properties
^^^^^^^^^^^^^^^^^^^^

.. autoclass:: Property
.. autoclass:: HiddenProperty

Special properties
__________________

Note that some properties have a special meaning for iPOPO and Pelix.

=================== ======= ===================================================
Name                Type    Description
=================== ======= ===================================================
``instance.name``   ``str`` The name of the iPOPO component instance (read only)
``service.id``      ``int`` The registration number of a service (read only)
``service.ranking`` ``int`` The rank (priority) of the services provided by this component
=================== ======= ===================================================

.. code-block:: python

    @ComponentFactory()
    @Property('_name', 'instance.name')    # Special property
    @Property('_value', 'my.value')        # Some property
    @Property('_answer', 'the.answer', 42) # Some property, with a default value
    class Foo:
       def __init__(self):
           self._name = None    # This will overwritten by iPOPO
           self._value = 12     # 12 will be used if this property is not configured
           self._answer = None  # 42 will be used by default


Provided Services
^^^^^^^^^^^^^^^^^

.. autoclass:: Provides


Requirements
^^^^^^^^^^^^

.. autoclass:: Requires
.. autoclass:: Temporal
.. autoclass:: RequiresBest
.. autoclass:: RequiresBroadcast
.. autoclass:: RequiresMap
.. autoclass:: RequiresVarFilter
.. autoclass:: RequiresConfiguration

Requiring several specifications
________________________________

:class:`Requires`, :class:`Temporal`, :class:`RequiresBest`,
:class:`RequiresBroadcast`, :class:`RequiresMap` and :class:`RequiresVarFilter`
accept a list of specifications (names or types) instead of a single one.

By default, the injected services must provide *all* of the given
specifications. With the ``match_any=True`` keyword argument, a service
providing *at least one* of them is enough.
The properties filter (``spec_filter``) applies in both cases.

.. code-block:: python

   @ComponentFactory()
   # Services providing both specifications
   @Requires("_storage", ["storage.reader", "storage.writer"])
   # Services providing any of them, e.g. to inject every storage service
   @Requires("_all_storages", ["storage.reader", "storage.writer"],
             aggregate=True, match_any=True)
   class Consumer:
       pass

The ``specification`` entry of the dictionaries returned by the
``get_factory_details()`` and ``get_instance_details()`` methods of the iPOPO
service still holds the first specification of the requirement, while the
``specifications`` entry holds all of them and ``match_any`` tells how they are
combined.

.. note::

   A requirement on all of the specifications costs the same as a
   single-specification one: the service registry only considers the services
   providing its first specification, then checks the other ones with an LDAP
   filter.

   A requirement with ``match_any=True`` can't rely on this index: it uses a
   service listener without specification, whose filter is evaluated on every
   service event of the framework, and its service lookups scan the whole
   registry. Prefer the default behavior when it fits.

Comparison with OSGi Declarative Services
__________________________________________

OSGi Declarative Services exposes a single reference type, configured by a
``policy`` (static or dynamic) and a ``policy-option`` (greedy or reluctant)
attribute. iPOPO spreads those same binding behaviors across several
specialized decorators instead of unifying them as attributes:

.. list-table::
   :header-rows: 1
   :widths: 20 45 35

   * - Decorator
     - Rebinds when...
     - Closest DS analogue
   * - :class:`Requires`
     - a bound service is lost (keeps ties, doesn't rebind on a better match
       becoming available)
     - ``policy-option="reluctant"`` (default)
   * - :class:`RequiresBest`
     - a higher-ranked match appears, even replacing an already bound
       service
     - ``policy-option="greedy"``
   * - :class:`RequiresVarFilter`
     - a referenced component property used by its filter changes
     - ConfigAdmin-driven ``target`` reference property
   * - :class:`Temporal`
     - (no DS equivalent: adds a grace period before a lost dependency
       actually invalidates the component)
     - *(iPOPO-only extension)*


Instance definition
^^^^^^^^^^^^^^^^^^^

.. autoclass:: Instantiate


Life-cycle events
-----------------

Those decorators store behavioural information on component methods.
They must decorate methods in the component class.

Component state
^^^^^^^^^^^^^^^

When all its requirements are fulfilled, the component goes into the
*VALID* state.
During the transition, it is in *VALIDATING* state and the following decorators
indicate which method must be called at that time.
If the decorated method raises an exception, the component goes into the
*ERRONEOUS* state.

.. autoclass:: ValidateComponent
.. autofunction:: Validate


When one of its requirements is missing, or when it is killed, the component
goes into the *INVALID* state.
During the transition, it is in *INVALIDATING* state and the following
decorators indicate which method must be called at that time.

Exceptions raised by the decorated method are ignored.

.. autofunction:: InvalidateComponent
.. autofunction:: Invalidate

Injections
^^^^^^^^^^

.. autofunction:: Bind
.. autoclass:: BindField
.. autofunction:: Update
.. autoclass:: UpdateField
.. autofunction:: Unbind
.. autoclass:: UnbindField

Service state
^^^^^^^^^^^^^

.. autofunction:: PostRegistration
.. autofunction:: PostUnregistration
