.. _api:

API
===

This part of the documentation covers all the core classes and
services of iPOPO.

.. _api_bundlecontext:

BundleContext Object
--------------------

The bundle context is the link between a bundle and the framework.
It's by the context that you can register services, install other
bundles.

.. autoclass:: pelix.framework.BundleContext
   :members:
   :inherited-members:


Framework Object
----------------

The Framework object is a singleton and can be accessed using
:meth:`get_bundle(0) <pelix.framework.BundleContext.get_bundle>`.
This class inherits the methods from :class:`pelix.framework.Bundle`.

.. autoclass:: pelix.framework.Framework
   :members:


Service management
------------------

The lookup methods of the bundle context will return
:class:`~pelix.internals.registry.ServiceReference` objects that can be used
to check the metadata of a service before using it.

.. autoclass:: pelix.internals.registry.ServiceReference
   :members:

When registering a service, the bundle context will return a
:class:`~pelix.internals.registry.ServiceRegistration`.
That object must not be shared to others as it can be used to update service
properties and to unregister it.

.. autoclass:: pelix.internals.registry.ServiceRegistration
   :members:


Bundle Object
-------------

This object gives access to the description of an installed bundle.
It is useful to check the path of the source module, the version, etc.

.. autoclass:: pelix.framework.Bundle
   :members:
   :inherited-members:

Events Objects
--------------

Those objects are given to listeners when a bundle or a service event occurs.

.. autoclass:: pelix.internals.events.BundleEvent
   :members:

.. autoclass:: pelix.internals.events.ServiceEvent
   :members:

.. autoclass:: pelix.ipopo.constants.IPopoEvent
   :members:
