.. iPOPO Release notes

Release Notes
#############

.. _release_0.5:

iPOPO 0.5
*********

API Changes
===========

Framework
---------

* ``BundleContext.install_bundle()`` now returns the ``Bundle`` object instead
  of the bundle ID.
  ``BundleContext.get_bundle()`` has been updated to accept both IDs and
  ``Bundle`` objects in order to keep a bit of compatibility

* ``Framework.get_symbolic_name()`` now returns *pelix.framework* instead of
  *org.psem2m.pelix*

* ``ServiceEvent.get_type()`` is renamed ``get_kind()``. The other name is
  still available but is declared deprecated (a warning is logged on its first
  use).


Shell
-----

* Shell command methods now take an ``IOHandler`` object in parameter instead
  of input and output file-like streams.
  This hides the compatibility tricks between Python 2 and 3 and simplifies the
  output formatting.


Additions
=========

Project
-------

* First version with release notes

Framework
---------

* ``BundleContext.install_visiting(path, visitor)``:

  * Visits the given path and installs the found modules if the visitor accepts
    them

* ``BundleContext.install_package(path)`` (*experimental*):

  * Installs all the modules found in the package at the given path
  * Based on ``install_visiting()``


iPOPO
-----

* Components with a ``pelix.ipopo.auto_restart`` property set to *True* are
  automatically re-instantiated after their bundle has been updated.


Services
--------

* Remote Services: use services of a distant Pelix instance

  * Multicast discovery
  * XML-RPC transport (not fully usable)
  * JSON-RPC transport (based on a patched version of jsonrpclib)

* EventAdmin: send events (a)synchronously
