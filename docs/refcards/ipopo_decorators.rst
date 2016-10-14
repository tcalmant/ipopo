.. _refcard_decorators:
.. module:: pelix.ipopo.decorators

iPOPO Decorators
================

Component definition
--------------------

.. autoclass:: ComponentFactory
.. autoclass:: SingletonFactory
.. autoclass:: Property
.. autoclass:: HiddenProperty
.. autoclass:: Provides
.. autoclass:: Requires
.. autoclass:: Temporal
.. autoclass:: RequiresBest
.. autoclass:: RequiresMap
.. autoclass:: RequiresVarFilter
.. autoclass:: Instantiate

Life-cycle events
-----------------

.. autofunction:: Validate
.. autofunction:: Invalidate

.. autofunction:: Bind
.. autoclass:: BindField
.. autofunction:: Update
.. autoclass:: UpdateField
.. autofunction:: Unbind
.. autoclass:: UnbindField

.. autofunction:: PostRegistration
.. autofunction:: PostUnregistration
