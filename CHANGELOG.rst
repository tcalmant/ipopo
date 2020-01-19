Release notes
#############

iPOPO 1.0.0
***********

Project
=======

* The Pelix/iPOPO is now split in two branches: iPOPO (``v1`` branch) and
  ipopo2 (``v2`` branch). The ``v2`` branch requires Python 3.7+, whereas ``v1``
  will keep compatibility with Python 2.7.

Pelix
=====

* Fixed an error when starting the framework after having loaded native modules,
  *e.g.* ``numpy``. These modules don't have a ``__path__`` set, which case was
  not handled when the framework normalizes the existing module paths.
* Fixed an invalid import of ``collections`` abstract classes for Python 3.3+
  in ``pelix.internal.hooks``.


iPOPO 0.8.1
***********

Pelix
=====

* Fixed a memory leak in the thread pool implementation. The patch comes from
  issue #35 of the `jsonrpclib-pelix <https://github.com/tcalmant/jsonrpclib/>`_
  project.

Remote Services
===============

* Fixed a deadlock in the Py4J provider (issue #100),
  contributed by Scott Lewis (@scottslewis).
  See `pull request #101 <https://github.com/tcalmant/ipopo/pull/101>`_
  for more details.
* Use a local ``etcd`` server in Travis-CI instead of a public one.


iPOPO 0.8.0
***********

Project
=======

* Version bump to 0.8 as the addition of Remote Service Admin is a big step
  forward.
* Fixed unit tests for ``pelix.threadpool``
* Added a word about Python 3.7 dataclasses in the iPOPO reference card
* All the source code has been reformatted with
  `black <https://github.com/ambv/black>`_ (``black -l 80 pelix``)

Remote Services
===============

* Added the implementation of Remote Service Admin OSGi specification,
  contributed by Scott Lewis (@scottslewis).
  This is a major feature which intends to be used instead of Pelix Remote
  Services. The latter will be kept for retro-compatibility reasons.


iPOPO 0.7.1
***********

Project
=======

* Added a CONTRIBUTING description file to describe the code style
* The ``zeroconf`` dependency is now forced to version 0.19, to stay compatible
  with Python 2.7
* Changed them in the documentation (back to standard ReadTheDocs theme)
* Added some reference cards in the documentation: initial configuration file,
  shell, shell report

Pelix
=====

* Added support for Event Listeners Hooks. See
  `pull request #88 <https://github.com/tcalmant/ipopo/pull/88>`_
  for more details.
* Fixed ``Framework.delete()`` when framework was already stopped.

iPOPO
=====

* Added ``@ValidateComponent`` and ``@InvalidateComponent`` decorators.
  They allow to define callback methods for component in/validation with access
  to component context and properties (read-only).
  ``@Validate`` and ``@Invalidate`` decorators are now simple aliases to those
  decorators.
* Checked behaviour with *data classes*, introduced in Python 3.7: all seems to
  work perfectly. See `issue 89 <https://github.com/tcalmant/ipopo/issues/89>`_
  for more details.

Shell
=====

* New shell completion system: completion is now extensible and can work with
  both commands and arguments. This system relies on ``readline``.
* Added a TLS version of the shell. Its usage and the generation of certificates
  are described in the Pelix Shell reference card in the documentation.
* ``ShellSession.write_line()`` can now be called without argument
  (prints an empty line)

Misc
====

* Fixed the access bug to the Python LogRecord message in the Log Service


iPOPO 0.7.0
***********

Project
=======

* Removed Python 2.6 compatibility code
* New version of the logo, with SVG sources in the repository
* Added some tests for ``install_package()``

Pelix
=====

* When a bundle is stopped, the framework now automatically releases the
  services it consumed. This was required to avoid stale references when using
  (prototype) service factories.
  **WARNING:** this can lead to issues if you were using stale references to
  pass information from one bundle version to another (which is bad).
* Added support for Prototype Service Factories, which were missing from issue
  `Service Factories (#75) <https://github.com/tcalmant/ipopo/issues/75>`_.
* Handle deprecation of the ``imp`` module (see #85)
* Added a ``delete()`` method to the ``Framework`` class.
  The ``FrameworkFactory`` class can now be fully avoided by developers.


iPOPO 0.6.5
***********

Project
=======

* Project documentation migrated to
  `Read The Docs <https://ipopo.readthedocs.io/>`_ as the previous documentation
  server crashed.
  All references to the previous server (``coderxpress.net``) have been removed.
* The documentation is being completely rewritten while it is converted from
  Dokuwiki to Sphinx.
* Removed Pypy 3 from Travis-CI/Tox tests, as it is not compatible with pip.
* Added tests to ensure that all services and utilities are used at least once
  in all tests environments. This will ease regression detection, especially
  when following updates of third-party libraries.
* Added ``mypy`` type hints in important places of the framework

Pelix
=====

* Added support for `Service Factories (#75) <https://github.com/tcalmant/ipopo/issues/75>`_.
  ``PrototypeServiceFactory`` are not supported.
* The Framework now adds the ``service.bundleid`` and ``service.scope``
  properties to services.
* The import path normalization now ensures that the full path of the initial
  working directory is stored in the path, and that the current working
  directory marker (empty string) is kept as the first entry of the Python path.
* Merged `pull request #65 <https://github.com/tcalmant/ipopo/pull/65>`_,
  to ignore import errors when normalizing the Python path.
* Merged `pull request #68 <https://github.com/tcalmant/ipopo/pull/68>`_,
  correcting the behaviour of the thread pool.
* Merged `pull request #77 <https://github.com/tcalmant/ipopo/pull/77>`_,
  which fixes the growing of ``sys.path`` in ``normalize_path()``.

iPOPO
=====

* The ``@Validate`` method of components is now always called after the bundle
  activator has returned. (`#66 <https://github.com/tcalmant/ipopo/issues/66>`_)
* Added a ``get_instance(name)`` method to access to the component instance
  object by its name. (`#74 <https://github.com/tcalmant/ipopo/issues/74>`_)
* Merged `pull request #79 <https://github.com/tcalmant/ipopo/pull/79>`_,
  which allows the use of ``__qualname__`` to automatically name the interface
  provided by a component according to its class name.

HTTP
====

* Added some utility methods to ``HttpServletRequest``:

  * ``get_command()``: get the HTTP command of the request
  * ``get_prefix_path()``: get the servlet prefix path
  * ``get_sub_path()``: get the part of the path corresponding to the servlet
    (*i.e.* without the prefix path)

* ``get_servlet()`` now returns the servlet prefix along with the servlet and
  the server parameters.
* Added a ``pelix.https`` service property and an ``is_https()`` service method
  to indicate that the server uses HTTPS.
* Added a utility module, ``pelix.http.routing``, which eases the routing of
  HTTP requests with decorators like ``@Http``, ``@HttpGet``...
* Merged `pull request #70 <https://github.com/tcalmant/ipopo/pull/70>`_,
  avoiding remote HTTP servlets to be used by the local HTTP server.
* Fixed the way servlet are found according to their path

Remote Services
===============

* JSON-RPC and XML-RPC transports providers now support HTTPS.
* Added a `Redis <https://redis.io/>`_-based discovery provider, working with
  all HTTP-based transport providers.
* Added a `ZooKeeper <https://zookeeper.apache.org/>`_-based discovery provider,
  working with all HTTP-based transport providers.
* Better detection of the loss of a framework with the mDNS discovery
* mDNS discovery is now based on the PyPI-available ``zeroconf`` package.

Shell
=====

* Added the *Configuration Handler*, which allows to give a JSON file to set
  the initial configuration of a framework: properties, bundles, instances, ...
* Console, Remote and XMPP shell now share some common arguments.
  This allows to use the *Configuration Handler* arguments in all these scripts.

Miscellaneous
=============

* The Log Service is now a Service Factory.

Utilities
=========

* Added a ``remove_duplicates()`` method, which allows to filter out duplicates
  from lists, keeping the original order.
* Added the ``is_bytes()`` method.

iPOPO 0.6.4
***********

iPOPO
=====

* Added support for the *hidden* properties. Those properties won't be seen
  in the shell nor in the components and factories description API.
  This is useful when giving password in component properties.

* Added the ``RequiresVariableFilter`` handler: it works like ``Requires`` but
  allows to use component properties in the LDAP filter. The filter is updated
  each time a component property is updated.

* iPOPO registers factories declared directly from a bundle, not those imported
  by the bundle. This avoids factory re-definitions when installing bundles
  which import each other.

HTTP
====

* Added support for HTTPS. Works for Python 2.7.9+, as it is based upon
  `SSLContext <https://docs.python.org/2/library/ssl.html#ssl-contexts>`_


Miscellaneous
=============

* Added a log service and its shell commands. It allows to look from the shell
  at what has been logged with its API or the ``logging`` module
* The MQTT client gives access to the underlying Paho client API and to its
  ``tls_set()`` method.


iPOPO 0.6.3
***********

Project
=======

* iPOPO now has a logo ! (thanks to @debbabi)
* README file has been rewritten
* Better PEP-8 compliance
* Updated *jsonrpclib* requirement version to 0.2.6


Pelix
=====

* Optimization of the service registry (less dictionaries, use of sets, ...)
* Added the ``hide_bundle_services()`` to the service registry.
  It is by the framework to hide the services of a stopping bundle from
  ``get_service_reference`` methods, and before those services will be
  unregistered.
* Removed the deprecated ``ServiceEvent.get_type()`` method


iPOPO
=====

* Optimization of StoredInstance (handlers, use of sets, ...)


HTTP
====

* Added a ``is_header_set()`` method to the HTTPServletResponse bean.
* Response headers are now sent on ``end_headers()``, not on ``set_header()``,
  to avoid duplicate headers.
* The request queue size of the basic HTTP server can now be set as a component
  property (``pelix.http.request_queue_size``)


Shell
=====

* The ``pelix.shell.console`` module can now be run as a main script
* Added the *report* shell command
* Added the name of *varargs* in the signature of commands
* Corrected the signature shown in the help description for static methods
* Corrected the *thread* and *threads* shell commands for *pypy*


Remote Services
===============

* Added support for keyword arguments in most of remote services transports
  (all except XML-RPC)
* Added support for ``pelix.remote.export.only`` and
  ``pelix.remote.export.none`` service properties. ``..only`` tells the
  exporter to export the given specifications only, while ``..none`` forbids
  the export of the service.


Utilities
=========

* Updated the MQTT client to follow the new API of Eclipse Paho MQTT Client


Tests
=====

* Travis-CI: Added Python 3.5 and Pypy3 targets
* Better configuration of coverage
* Added tests for the remote shell
* Added tests for the MQTT client and for *MQTT-RPC*


iPOPO 0.6.2
***********

iPOPO
=====

* The properties of a component can be updated when calling the
  ``retry_erroneous()`` method. This allows to modify the configuration of
  a component before trying to validate it again (HTTP port, ...).
* The ``get_instance_details()`` dictionary now always contains a *filter*
  entry for each of the component requirement description, even if not filter
  has been set.


Shell
=====

* The ``ipopo.retry`` shell command accepts properties to be reconfigure the
  instance before trying to validate it again.
* The bundle commands (*start*, *stop*, *update*, *uninstall*) now prints the
  name of the bundle along with its ID.
* The ``threads`` and ``threads`` shell commands now accept a stack depth limit
  argument.


HTTP
====

* Protect the ``ServletRequest.read_data()`` method against empty or invalid
  *Content-Length* headers


iPOPO 0.6.1
***********

iPOPO
=====

* The stack trace of the exception that caused a component to be in the
  ERRONEOUS state is now kept, as a string. It can be seen through the
  ``instance`` shell command.


Shell
=====

* The command parser has been separated from the shell core service. This
  allows to create custom shells without giving access to Pelix administration
  commands.
* Added ``cd`` and ``pwd`` shell commands, which allow changing the working
  directory of the framework and printing the current one.
* Corrected the encoding of the shell output string, to avoid exceptions when
  printing special characters.


Remote Services
===============

* Corrected a bug where an imported service with the same endpoint name as an
  exported service could be exported after the unregistration of the latter.


iPOPO 0.6.0
***********

Project
=======

* The support of Python 2.6 has been removed


Utilities
=========

* The XMPP bot class now supports anonymous connections using SSL or StartTLS.
  This is a workaround for
  `issue 351 <https://github.com/fritzy/SleekXMPP/issues/351>`_
  of SleekXMPP.


iPOPO 0.5.9
***********

Project
=======

* iPOPO now works with IronPython (tested inside Unity 3D)


iPOPO
=====

* Components raising an error during validation goes in the ERRONEOUS state,
  instead of going back to INVALID.
  This avoids trying to validate them automatically.
* The ``retry_erroneous()`` method of the iPOPO service and the ``retry`` shell
  command allows to retry the validation of an ERRONEOUS component.
* The ``@SingletonFactory`` decorator can replace the ``@ComponentFactory``
  one.
  It ensures that only one component of this factory can be instantiated at a
  time.
* The ``@Temporal`` requirement decorator allows to require a service and to
  wait a given amount of time for its replacement before invalidating the
  component or while using the requirement.
* ``@RequiresBest`` ensures that it is always the service with the best
  ranking that is injected in the component.
* The ``@PostRegistration`` and ``@PreUnregistration`` callbacks allows the
  component to be notified right after one of its services has been registered
  or will be unregistered.


HTTP
====

* The generated 404 page shows the list of registered servlets paths.
* The 404 and 500 error pages can be customized by a hook service.
* The default binding address is back to "0.0.0.0" instead of "localhost".
  (for those who used the development version)


Utilities
=========

* The ``ThreadPool`` class is now a cached thread pool. It now has a minimum
  and maximum number of threads: only the required threads are alive.
  A thread waits for a task during 60 seconds (by default) before stopping.


iPOPO 0.5.8
***********

Framework
=========

* ``FrameworkFactory.delete_framework()`` can be called with ``None`` or
  without argument. This simplifies the clean up afters tests, etc.
* The list returned by ``Framework.get_bundles()`` is always sorted by
  bundle ID.


iPOPO
=====

* Added the ``immediate_rebind`` option to the ``@Requires`` decorator.
  This indicates iPOPO to not invalidate then revalidate a component if a
  service can replace an unbound required one. This option inly applies to
  non-optional, non-aggregate requirements.


Shell
=====

* The I/O handler is now part of a ShellSession bean. The latter has the same
  API as the I/O handler so there is no need to update existing commands.
  I/O Handler write methods are now synchronized.
* The shell supports variables as arguments, e.g. ``echo $var``.
  See `string.Template <https://docs.python.org/3/library/string.html#template-strings>`_
  for more information. The Template used in Pelix Shell allows ``.`` (dot)
  in names.
* A special variable ``$?`` stores the result of the last command which
  returned a result, i.e. anything but None or False.
* Added *set* and *unset* commands to work with variables
* Added the *run* command to execute a script file.
* Added protection against ``AttributeError`` in *threads* and *thread*


iPOPO 0.5.7
***********

Project
=======

* Code review to be more PEP-8 compliant
* `jsonrpclib-pelix <https://pypi.python.org/pypi/jsonrpclib-pelix>`_ is now an
  install requirement (instead of an optional one)


Framework
=========

* Forget about previous global members when calling ``Bundle.update()``. This
  ensures to have a fresh dictionary of members after a bundle update
* Removed ``from pelix.constants import *`` in ``pelix.framework``:
  only use ``pelix.constants`` to access constants


Remote Services
===============

* Added support for endpoint name reuse
* Added support for synonyms: specifications that can be used on the remote
  side, or which describe a specification of another language
  (e.g. a Java interface)
* Added support for a *pelix.remote.export.reject* service property: the
  specifications it contains won't be exported, event if indicated in
  *service.exported.interfaces*.
* Jabsorb-RPC:

  * Use the common dispatch() method, like JSON-RPC

* MQTT(-RPC):

  * Explicitly stop the reading loop when the MQTT client is disconnecting
  * Handle unknown correlation ID


Shell
=====

* Added a ``loglevel`` shell command, to update the log level of any logger
* Added a ``--verbose`` argument to the shell console script
* Remote shell module can be ran as a script


HTTP
====

* Remove double-slashes when looking for a servlet


XMPP
====

* Added base classes to write a XMPP client based on
  `SleekXMPP <http://sleekxmpp.com/>`_
* Added a XMPP shell interface, to control Pelix/iPOPO from XMPP


Miscellaneous
=============

* Added an IPv6 utility module, to setup double-stack and to avoids missing
  constants bugs in Windows versions of Python
* Added a ``EventData`` class: it acts like ``Event``, but it allows to store
  a data when setting the event, or to raise an exception in all callers of
  ``wait()``
* Added a ``CountdownEvent`` class, an ``Event`` which is set until a given
   number of calls to ``step()`` is reached
* ``threading.Future`` class now supports a callback methods, to avoid to
  actively wait for a result.


iPOPO 0.5.6
***********

Project
=======

* Added samples to the project repository
* Removed the static website from the repository

* Added the project to `Coveralls <https://coveralls.io/>`_
* Increased code coverage


Framework
=========

* Added a ``@BundleActivator`` decorator, to define the bundle activator class.
  The ``activator`` module variable should be replaced by this decorator.
* Renamed specifications constants: from ``XXX_SPEC`` to ``SERVICE_XXX``


iPOPO
=====

* Added a *waiting list* service: instantiates components as soon as the iPOPO
  service and the component factory are registered
* Added ``@RequiresMap`` handler
* Added an ``if_valid`` parameter to binding callbacks decorators: ``@Bind``,
  ``@Update``, ``@Unbind``, ``@BindField``, ``@UpdateField``, ``@UnbindField``.
  The decorated method will be called if and only if the component valid.
* The ``get_factory_context()`` from ``decorators`` becomes public to ease
  the implementation of new decorators


Remote Services
===============

* Large rewriting of Remote Service core modules

  * Now using OSGi Remote Services properties
  * Added support for the OSGi EDEF file format (XML)

* Added an abstract class to easily write RPC implementations
* Added mDNS service discovery
* Added an MQTT discovery protocol
* Added an MQTT-RPC protocol, based on Node.js
  `MQTT-RPC module <https://github.com/wolfeidau/mqtt-rpc>`_
* Added a Jabsorb-RPC transport. Pelix can now use Java services and vice-versa,
  using:

  * `Cohorte Remote Services <https://github.com/isandlaTech/cohorte-remote-services>`_
  * `Eclipse ECF <http://wiki.eclipse.org/ECF>`_ and the
    `Jabsorb-RPC provider <https://github.com/isandlaTech/cohorte-remote-services/tree/master/org.cohorte.ecf.provider.jabsorb>`_


Shell
=====

* Enhanced completion with ``readline``
* Enhanced commands help generation
* Added arguments to filter the output of ``bl``, ``sl``, ``factories``
  and ``instances``
* Corrected ``prompt`` when using ``readline``
* Corrected ``write_lines()`` when not giving format arguments
* Added an ``echo`` command, to test string parsing


Services
========

* Added support for *managed service factories* in ConfigurationAdmin
* Added an EventAdmin-MQTT bridge: events from EventAdmin with an
  *event.propagate* property are published over MQTT
* Added an early version of an MQTT Client Factory service


Miscellaneous
=============

* Added a ``misc`` package, with utility modules and bundles:

  * ``eventadmin_printer``: an EventAdmin handler that prints or logs the
    events it receives
  * ``jabsorb``: converts dictionary from and to the Jabsorb-RPC format
  * ``mqtt_client``: a wrapper for the `Paho <http://www.eclipse.org/paho/>`_
    MQTT client, used in MQTT discovery and MQTT-RPC.


iPOPO 0.5.5
***********

Project
=======

The license of the iPOPO project is now an Apache License 2.0.


Framework
=========

* ``get_*_service_reference*()`` methods have a default LDAP filter set to
  ``None``. Only the service specification is required, event if set to
  ``None``.

* Added a context ``use_service(context, svc_ref)``, that allows to consume a
  service in a ``with`` block:

  .. code-block:: python

     from pelix.utilities import use_service
     with use_service(bundle_context, svc_ref) as svc:
        svc.foo()

  Service will be released automatically.


iPOPO
=====

* Added the *Handler Factory* pattern : all instance handlers are created by
  their factory, called by iPOPO according to the handler IDs found in the
  factory context.
  This will simplify the creation of new handlers.

* Added a context ``use_ipopo(context)``, that allows to use the iPOPO service
  in a ``with`` block:

  .. code-block:: python

     from pelix.ipopo.constants import use_ipopo
     with use_ipopo(bundle_context) as ipopo:
        ipopo.instantiate('my.factory', 'my.instance', {})

  The iPOPO service will be released automatically.


Services
========

* Added the ConfigurationAdmin service
* Added the FileInstall service


iPOPO 0.5.4
***********

Additions
=========

Global
------

* Global speedup replacing ``list.append()`` by ``bisect.insort()``.
* Optimizations in handling services, components and LDAP filters.
* Some classes of Pelix framework and iPOPO core modules extracted to new
  modules.

iPOPO
-----

* ``@Requires`` accepts only one specification
* Added a context ``use_ipopo(bundle_context)``, to simplify the usage of the
  iPOPO service, using the keyword ``with``.
* ``get_factory_details(name)`` method now also returns the ID of the bundle
  provided the component factory, and the component instance properties.

Shell
-----

* The help command now uses the *inspect* module to list the required and
  optional parameters.
* ``IOHandler`` now has a ``prompt()`` method to ask the user to enter a line.
  It replaces the ``read()`` method, which was to buggy.

Bugs fixed
==========

Global
------

* Fixed support of Python 2.6.
* Replaced Python 3 imports conditions by ``try-except`` blocks.

iPOPO
-----

* Protection of the unregistration of factories, as a component can kill
  another one of the factory during its invalidation.

Remote Services
---------------

* Protection of the unregistration loop during the invalidation of JSON-RPC and
  XML-RPC exporters.
* The *Dispatcher Servlet* now handles the *discovered* part of the discovery
  process. This simplifies the Multicast Discovery component and suppresses a
  socket bug/feature on BSD (including Mac OS).

Shell
-----

* The ``make_table()`` method now accepts generators as parameters.
* Remote commands handling removed: ``get_methods_names()`` is not used anymore.


iPOPO 0.5.3
***********

Additions
=========

iPOPO
-----

* New ``get_factory_details(name)`` method in the iPOPO service, acting like
  ``get_instance_details(name)`` but for factories.
  It returns a dictionary describing the given factory.

* New ``factory`` shell command, which describes a component factory:
  properties, requirements, provided services, ...

HTTP Service
------------

* Servlet exceptions are now both sent to the client and logged locally

Bugs fixed
==========

Remote Services
---------------

* Data read from the servlets or sockets are now properly converted from bytes
  to string before being parsed (Python 3 compatibility).

Shell
-----

* Exceptions are now printed using ``str(ex)`` instead of ``ex.message``
  (Python 3 compatibility).

* The shell output is now flushed, both by the shell I/O handler and the
  text console. The remote console was already flushing its output.
  This allows to run the Pelix shell correctly inside Eclipse.


iPOPO 0.5.2
***********

Additions
=========

iPOPO Decorators
----------------

* An error is now logged if a class is manipulated twice. Decorators executed
  after the first manipulation, i.e. upon ``@ComponentFactory()``, are ignored.


HTTP Service
------------

* New servlet binding parameters:

  * http.name : Name of HTTP service. The name of component instance in the case
    of the basic implementation.

  * http.extra : Extra properties of the HTTP service. In the basic
    implementation, this the content of the *http.extra* property of the
    HTTP server component

* New method ``accept_binding(path, params)`` in servlets.
  This allows to refuse the binding with a server before to test the
  availability of the registration path, thus to avoid raising a meaningless
  exception.


Remote Services
---------------

* End points are stored according to their framework

* Added a method ``lost_framework(uid)`` in the registry of imported services,
  which unregisters all the services provided by the given framework.


Shell
-----

* Shell *help* command now accepts a command name to print a specific
  documentation


Bugs fixed
==========

iPOPO Decorators
----------------

* Better handling of inherited and overridden methods: a decorated method can
  now be overridden in a child class, with the name, without warnings.

* Better error logs, with indication of the error source file and line


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
