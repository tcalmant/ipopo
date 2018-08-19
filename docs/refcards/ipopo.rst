.. _refcard_component:
.. module:: pelix.framework

iPOPO Components
================

A component is an object with a life-cycle, requiring services and providing
ones, and associated to properties.
The code of a component is reduced to its functional purpose:
its life-cycle, dependencies, etc. are handled by iPOPO.
In iPOPO, a component is an instance of component factory, *i.e.* a Python
class manipulated with the iPOPO decorators.

.. note::

   Due to the use of Python properties, all component factories must be
   new-style classes. It is the case of all Python 3 classes, but Python 2.x
   classes must explicitly inherit from the ``object`` class.

Life-cycle
----------

The component life cycle is handled by an instance manager created by the
iPOPO service.
This instance manager will inject control methods, run-time dependencies,
and will register the component services.
All changes will be notified to the component using the callback methods it
decorated.

.. image:: ../_static/component_lifecycle.png
   :alt: iPOPO component life-cycle graph
   :width: 30%
   :align: right

============ ==================================================================
State        Description
============ ==================================================================
INSTANTIATED The component has been instantiated. Its constructor has been called and the control methods have been injected
VALIDATED    All required dependencies have been injected. All services provided by the component will be registered right after this method returned
KILLED       The component has been invalidated and won't be usable again
ERRONEOUS    The component raised an error during its validation. It is not destroyed and a validation can be retried manually
============ ==================================================================

API
---

iPOPO components are handled through the iPOPO core service, which can itself
be accessed through the Pelix API or the utility context manager
:meth:`~pelix.ipopo.constants.use_ipopo`.
The core service provides the ``pelix.ipopo.core`` specification.

.. autofunction:: pelix.ipopo.constants.use_ipopo

   The following snippet shows how to use this method::

      from pelix.ipopo.constants import use_ipopo

      # ... considering "context" being a BundleContext object
      with use_ipopo(context) as ipopo:
          # use the iPOPO core service with the "ipopo" variable
          ipopo.instantiate("my.factory", "my.component",
                            {"some.property": [1, 2, 3], "answer": 42})

      # ... out of the "with" context, the iPOPO service has been released
      # and shouldn't be used


Here are the most commonly used methods from the iPOPO core service to handle
components and factories:

.. autoclass:: pelix.ipopo.core._IPopoService
   :members: add_listener, remove_listener, get_instances, get_instance_details,
             get_factories, get_factory_details, instantiate, kill,
             retry_erroneous

A word on Python 3.7 Data classes
=================================

These indications have to be taken into account when using iPOPO decorators on
`data classes <https://www.python.org/dev/peps/pep-0557/>`_.
They are also valid when using the
`dataclasses <https://pypi.org/project/dataclasses/>`_ package for Python 3.6.

Important notes
---------------

* **All** fields of the Data Class **must** have a default value.
  This will let the ``@dataclass`` decorator generate an ``__init__`` method
  without explicit arguments, which is a requirement for iPOPO.

* If the ``init=False`` argument is given to ``@dataclass``, it is necessary to
  implement your own ``__init__``, defining all fields, otherwise generated
  methods like ``__repr__`` won't work.

Good to know
------------

* Injected fields (``@Property``, ``@Requires``, ...) will lose the default
  value given in the class definition, in favor to the ones given to the iPOPO
  decorators. This is due to the redefinition of the fields by those decorators.
  Other fields are not touched at all.
* The ``@dataclass`` decorator can be used before or after the iPOPO decorators
