.. iPOPO Release notes

Release Notes
#############

.. _release_0.5.1:

iPOPO 0.5.1
***********

Additions
=========

Shell
-----

* The remote shell now provides a service, ``pelix.shell.remote``, with a
  ``get_access()`` method that returns the *(host, port)* tuple where the
  remote shell is waiting for clients.


HTTP Service
------------

* The HTTP service now supports the update of servlet services properties.
  A servlet service can now update its registration path property after having
  been bound to a HTTP service.
* A *500 server error* page containing an exception trace is now generated when
  a servlet fails.


Bugs fixed
==========

Framework
---------

* Bundle.update() now logs the SyntaxError exception that be raised in Python 3.

Shell
-----

* Fixed the ``threads`` command that wasn't working on Python 3.


HTTP Service
------------

* The ``bound_to()`` method of a servlet is called only after the HTTP service
  is ready to accept clients.


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

* Added this "release notes" page to the web site

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

iPOPO 0.4
*********

Version 0.4 fixes many bugs and provides new features:

Pelix
=====

* ``create_framework()`` utility method
* The framework has been refactored, allowing more efficient services and
  events handling

iPOPO
=====

* A component can provide multiple services
* A service controller can be injected for each provided service, to
  activate or deactivate its registration
* Dependency injection and service providing mechanisms have been refactored,
  using a basic handler concept.

Services
========

* Added a HTTP service component, using the concept of *servlet*
* Added an extensible shell, interactive and remote, simplifying the usage
  of a framework instance

iPOPO 0.3
*********

Packages have been renamed. As the project goes public, it may not have
relations to isandlaTech projects anymore.

+------------------------+------------------+
| Previous name          | New name         |
+========================+==================+
| psem2m                 | pelix            |
+------------------------+------------------+
| psem2m.service.pelix   | pelix.framework  |
+------------------------+------------------+
| psem2m.component       | pelix.ipopo      |
+------------------------+------------------+
| psem2m.component.ipopo | pelix.ipopo.core |
+------------------------+------------------+

iPOPO 0.2
*********

Version 0.2 is the first public release, under GPLv3 license (see LICENSE).