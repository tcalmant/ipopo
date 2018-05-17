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

=================== ======= ====================================================
Name                Type    Description
=================== ======= ====================================================
``instance.name``   ``str`` The name of the iPOPO component instance
``service.id``      ``int`` The registration number of a service
``service.ranking`` ``int`` The rank (priority) of the services provided by this component
=================== ======= ====================================================

.. code-block:: python

    @ComponentFactory()
    @Property('_name', 'instance.name')    # Special property
    @Property('_value', 'my.value')        # Some property
    @Property('_answer', 'the.answer', 42) # Some property, with a default value
    class Foo(object):
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
.. autoclass:: RequiresMap
.. autoclass:: RequiresVarFilter


Instance definition
^^^^^^^^^^^^^^^^^^^

.. autoclass:: Instantiate


Life-cycle events
-----------------

Those decorators store behavioral information on component methods.
They must decorate methods in the component class.

Component state
^^^^^^^^^^^^^^^

.. autoclass:: ValidateComponent
.. autofunction:: Validate
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
