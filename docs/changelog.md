# Release Notes

## iPOPO 3.1.0

:::{admonition} Release Date
:class: info

2025-04-27
:::

### Project

* Addition of the `pyproject.toml` file

### Dependencies

* Updated and fixed [SliXMPP](https://pypi.org/project/slixmpp/) to 1.10
* Updated `osgiservicebridge` to 1.5.8
* Removed `etcd3` dependency

### Remote Services Admin

* Scott Lewis (@scottslewis) replaced the etcd3 implementation by a custom one
  (see issue [#143](https://github.com/tcalmant/ipopo/issues/143)
  and pull request [#145](https://github.com/tcalmant/ipopo/pull/145))
* The etcd2 endpoint discovery is now **deprecated**.
  Removal is expected in next minor version (3.2) or when it breaks.


### XMPP client

* `pelix.misc.xmpp.BasicBot` doesn't inherit `slixmpp.ClientXMPP` anymore,
  but is the class to call to create an XMPP client.
  This ensures that the client will run in a specific thread with a valid
  asyncio loop and will forward common methods to that thread.
  Its main purpose is to provide a non-async API toward the underlying bot.

* XMPP bots should now inherit `pelix.misc.xmpp.XMPPBotClient` which behaves
  like the previous `BasicBot` class (without asyncio loop handling)
  and inherits `slixmpp.ClientXMPP`.


## iPOPO 3.0.0

:::{admonition} Release Date
:class: info

2024-08-26
:::

### Project

* Dropped support for Python 2.7 and versions earlier than 3.10
* Kept compability with iPOPO 1.0 on API level
* Moved from Travis-CI to GitHub actions to test project against Python 3.10, 3.11 and 3.12
* Added type hints where possible
* Support types in specifications
* Documentation updates
* Fixed most deprecation warnings from Python 3.12

### Dependencies

* Upgraded Eclipse Paho to 2.1
* Replaced [SleekXMPP](https://github.com/fritzy/SleekXMPP)
  by [SliXMPP](https://pypi.org/project/slixmpp/)

### Remote Services Admin

* Added an etcd3 discovery provider
* Updated `osgiservicebridge` to 1.5.7 because of `protobuf` version issues

### Tests

* Fixed link to Karaf

## iPOPO 1.0.2

:::{admonition} Release Date
:class: info

2023-10-28
:::

### iPOPO

* Fixed component not being validated correctly on filter update in the
  `@RequiresVarFilter` handler.
  See [#119](https://github.com/tcalmant/ipopo/issues/113) for more details.

## iPOPO 1.0.1

:::{admonition} Release Date
:class: info

2020-11-10
:::

### iPOPO

* Added a `RequiresBroadcast` decorator, which injects a proxy that
  broadcasts calls to all services matched by the requirement. It also
  transparently ignores calls when no service matches the requirement.

### Misc

* `ConfigurationAdmin` default persistence can now be disabled by
  setting the `pelix.configadmin.persistence.default.disable`
  framework property to any non-empty value.
  See [#113](https://github.com/tcalmant/ipopo/issues/113) for more details.
* Added a `to_record()` method in `LogEntry` objects. This converts
  the Pelix entry to a `logging.LogRecord` object, which can then be
  formatted using standard formatters. Note that some information is
  missing, like the place the log record is from (file path and line).

## iPOPO 1.0.0

:::{admonition} Release Date
:class: info

2020-01-19
:::

### Project

* The Pelix/iPOPO is now split in two branches: iPOPO (`v1` branch)
  and ipopo2 (`v2` branch). The `v2` branch requires Python 3.7+,
  whereas `v1` will keep compatibility with Python 2.7.

### Pelix

* Fixed an error when starting the framework after having loaded
  native modules, *e.g.* `numpy`. These modules don't have a
  `__path__` set, which case was not handled when the framework
  normalizes the existing module paths.
* Fixed an invalid import of `collections` abstract classes for Python
  3.3+ in `pelix.internal.hooks`.

## iPOPO 0.8.1

:::{admonition} Release Date
:class: info

2018-11-17
:::

### Pelix

* Fixed a memory leak in the thread pool implementation. The patch comes from
  issue #35 of the [jsonrpclib-pelix](https://github.com/tcalmant/jsonrpclib/)
  project.

### Remote Services

* Fixed a deadlock in the Py4J provider (issue #100), contributed by
  Scott Lewis (@scottslewis).
  See [#101](https://github.com/tcalmant/ipopo/pull/101) for more details.
* Use a local `etcd` server in Travis-CI instead of a public one.

## iPOPO 1.0.0

:::{admonition} Release Date
:class: info

2018-08-19
:::

### Project

* Version bump to 0.8 as the addition of Remote Service Admin is a big step forward.
* Fixed unit tests for `pelix.threadpool`
* Added a word about Python 3.7 dataclasses in the iPOPO reference card
* All the source code has been reformatted with
  [black](https://github.com/psf/black) (`black -l 80 pelix`)

### Remote Services

* Added the implementation of Remote Service Admin OSGi specification,
  contributed by Scott Lewis (@scottslewis). This is a major feature
  which intends to be used instead of Pelix Remote Services. The
  latter will be kept for retro-compatibility reasons.

## iPOPO 0.7.1

:::{admonition} Release Date
:class: info

2018-06-16
:::

### Project

* Added a CONTRIBUTING description file to describe the code style
* The `zeroconf` dependency is now forced to version 0.19, to stay
  compatible with Python 2.7
* Changed them in the documentation (back to standard ReadTheDocs theme)
* Added some reference cards in the documentation:
  initial configuration file, shell, shell report

### Pelix

* Aded support for Event Listeners Hooks.
  See [#88](https://github.com/tcalmant/ipopo/pull/88) for more details.
* Fixed `Framework.delete()` when framework was already stopped.

### iPOPO

* Added `@ValidateComponent` and `@InvalidateComponent` decorators.
  They allow to define callback methods for component in/validation
  with access to component context and properties (read-only).
  `@Validate` and `@Invalidate` decorators are now simple aliases to
  those decorators.
* Checked behaviour with *data classes*, introduced in Python 3.7: all
  seems to work perfectly. See [#89](https://github.com/tcalmant/ipopo/issues/89)
  for more details.

### Shell

* New shell completion system: completion is now extensible and can
  work with both commands and arguments. This system relies on `readline`.
* Added a TLS version of the shell. Its usage and the generation of
  certificates are described in the Pelix Shell reference card in the
  documentation.
* `ShellSession.write_line()` can now be called without argument
  (prints an empty line)

### Misc

* Fixed the access bug to the Python LogRecord message in the Log Service

## iPOPO 0.7.0

:::{admonition} Release Date
:class: info

2017-12-30
:::

### Project

* Removed Python 2.6 compatibility code
* New version of the logo, with SVG sources in the repository
* Added some tests for `install_package()`

### Pelix

* When a bundle is stopped, the framework now automatically releases
  the services it consumed. This was required to avoid stale
  references when using (prototype) service factories.

  **WARNING:** this can lead to issues if you were using stale references to
  pass information from one bundle version to another (which is bad).
* Added support for Prototype Service Factories, which were missing
  from issue [Service Factories (#75)](https://github.com/tcalmant/ipopo/issues/75).
* Handle deprecation of the `imp` module (see #85)
* Added a `delete()` method to the `Framework` class.
  The `FrameworkFactory` class can now be fully avoided by developers.

## iPOPO 0.6.5

:::{admonition} Release Date
:class: info

2017-09-17
:::

### Project

* Project documentation migrated to [Read The Docs](https://ipopo.readthedocs.io/)
  as the previous documentation server crashed.
  All references to the previous server (`coderxpress.net`) have been removed.
* The documentation is being completely rewritten while it is converted from
  Dokuwiki to Sphinx.
* Removed Pypy 3 from Travis-CI/Tox tests, as it is not compatible with pip.

### Pelix

* The import path normalization now ensures that the full path of the
  initial working directory is stored in the path, and that the
  current working directory marker (empty string) is kept as the first
  entry of the Python path.
* Merged [#65](https://github.com/tcalmant/ipopo/pull/65), to ignore import
  errors when normalizing the Python path.
* Merged [#68](https://github.com/tcalmant/ipopo/pull/68), correcting the
  behaviour of the thread pool.

### iPOPO

* The `@Validate` method of components is now always called after the
  bundle activator has returned.
  ([#66](https://github.com/tcalmant/ipopo/issues/66))
* Added a `get_instance(name)` method to access to the component
  instance object by its name.
  ([#74](https://github.com/tcalmant/ipopo/issues/74))

### HTTP

* Added some utility methods to `HttpServletRequest`:
  * `get_command()`: get the HTTP command of the request
  * `get_prefix_path()`: get the servlet prefix path
  * `get_sub_path()`: get the part of the path corresponding to the servlet
    (*i.e.* without the prefix path)
* `get_servlet()` now returns the servlet prefix along with the
  servlet and the server parameters.
* Added a `pelix.https` service property and an `is_https()` service
  method to indicate that the server uses HTTPS.
* Added a utility module, `pelix.http.routing`, which eases the
  routing of HTTP requests with decorators like `@Http`, `@HttpGet`, ...
* Merged [#70](https://github.com/tcalmant/ipopo/pull/70), avoiding remote
  HTTP servlets to be used by the local HTTP server.

### Remote Services

* JSON-RPC and XML-RPC transports providers now support HTTPS.
* Added a [Redis](https://redis.io/)-based discovery provider, working
  with all HTTP-based transport providers.

### Shell

* Added the *Configuration Handler*, which allows to give a JSON file
  to set the initial configuration of a framework: properties,
  bundles, instances, ...

## iPOPO 0.6.4

:::{admonition} Release Date
:class: info

2016-06-12
:::

### iPOPO

* Added `@RequiresVariableFilter`, which works like `@Requires` but
  also supports the use of component properties as variables in LDAP
  filter.
* Added `@HiddenProperty`, which extends `@Property`, but ensures that
  the property key and value won't be seen in the description API nor
  in the shell. (it will stay visible using the standard reflection
  API of Python)

### HTTP Service

* The HTTP basic component now support HTTPS. It is activated when
  given two files (a certificate and a key) in its component
  properties. A password can also be given if the key file is
  encrypted. This is a prototype feature and should be used carefully.
  Also, it should not be used with remote services.

### Services

* A new *log service* has been added to this version, though the
  `pelix.misc.log` bundle. It provides the OSGi API to log traces, but
  also keeps track of the traces written with the `logging` module.
  The log entries can be accessed locally (but not through remote
  services). They can be printed in the shell using commands provided
  by pelix.shell.log.

## iPOPO 0.6.3

:::{admonition} Release Date
:class: info

2015-10-23
:::

### Project

* iPOPO now has a logo ! (thanks to @debbabi)
* README file has been rewritten
* Better PEP-8 compliance
* Updated `jsonrpclib-pelix` requirement version to 0.2.6

### Framework

* Optimization of the service registry (less dictionaries, use of sets, ...)
* Added the `hide_bundle_services()` to the service registry. It is by
  the framework to hide the services of a stopping bundle from
  `get_service_reference` methods, and before those services will be
  unregistered.
* Removed the deprecated `ServiceEvent.get_type()` method

### iPOPO

* Optimization of StoredInstance (handlers, use of sets, ...)

### HTTP Service

* Added a `is_header_set()` method to the HTTPServletResponse bean.
* Response headers are now sent on `end_headers()`, not on
  `set_header()`, to avoid duplicate headers.
* The request queue size of the basic HTTP server can now be set as a
  component property (`pelix.http.request_queue_size`)

### Remote Services

* Added support for keyword arguments in most of remote services
  transports (all except XML-RPC)
* Added support for `pelix.remote.export.only` and
  `pelix.remote.export.none` service properties.
  `pelix.remote.export.only` tells the exporter to export the given
  specifications only, while `pelix.remote.export.none` forbids the
  export of the service.

### Shell

* The `pelix.shell.console` module can now be run as a main script
* Added the *report* shell command
* Added the name of *varargs* in the signature of commands
* Corrected the signature shown in the help description for static methods
* Corrected the *thread* and *threads* shell commands for Pypy

### Utilities

* Updated the MQTT client to follow the new API of Eclipse Paho MQTT Client

### Tests

* Travis-CI: Added Python 3.5 and Pypy3 targets
* Better configuration of coverage
* Added tests for the remote shell
* Added tests for the MQTT client and for MQTT-RPC

## iPOPO 0.6.2

:::{admonition} Release Date
:class: info

2015-06-17
:::

### iPOPO

* The properties of a component can be updated when calling the
  `retry_erroneous()` method. This allows to modify the configuration
  of a component before trying to validate it again (HTTP port, ...).
* The `get_instance_details()` dictionary now always contains a
  *filter* entry for each of the component requirement description,
  even if not filter has been set.

### HTTP Service

* Protection of the `ServletRequest.read_data()` method against empty
  or invalid `Content-Length` headers

### Shell

* The `ipopo.retry` shell command accepts properties to be reconfigure
  the instance before trying to validate it again.
* The bundle commands (*start*, *stop*, *update*, *uninstall*) now
  print the name of the bundle along with its ID.
* The `threads` and `threads` shell commands now accept a stack depth
  limit argument.

## iPOPO 0.6.1

:::{admonition} Release Date
:class: info

2015-04-20
:::

### iPOPO

* The stack trace of the exception that caused a component to be in
  the `ERRONEOUS` state is now kept, as a string. It can be seen
  through the `instance` shell command.

### Shell

* The command parser has been separated from the shell core service.
  This allows to create custom shells without giving access to Pelix
  administration commands.
* Added `cd` and `pwd` shell commands, which allow changing the
  working directory of the framework and printing the current one.
* Corrected the encoding of the shell output string, to avoid
  exceptions when printing special characters.

### Remote Services

* Corrected a bug where an imported service with the same endpoint
  name as an exported service could be exported after the
  unregistration of the latter.

## iPOPO 0.6.0

:::{admonition} Release Date
:class: info

2015-03-12
:::

### Project

* The support of Python 2.6 has been removed

### Utilities

* The XMPP bot class now supports anonymous connections using SSL or
  StartTLS. This is a workaround for
  [#351](https://github.com/fritzy/SleekXMPP/issues/351) of
  [SleekXMPP](https://github.com/fritzy/SleekXMPP).

## iPOPO 0.5.9

:::{admonition} Release Date
:class: info

2015-02-18
:::

### Project

* iPOPO now works with IronPython (tested inside Unity 3D)

### iPOPO

* Components raising an error during validation goes in the
  `ERRONEOUS` state, instead of going back to `INVALID`. This avoids
  trying to validate them automatically.
* The `retry_erroneous()` method of the iPOPO service and the `retry`
  shell command allows to retry the validation of an `ERRONEOUS` component.
* The `@SingletonFactory` decorator can replace the
  `@ComponentFactory` one. It ensures that only one component of this
  factory can be instantiated at a time.
* The `@Temporal` requirement decorator allows to require a service
  and to wait a given amount of time for its replacement before
  invalidating the component or while using the requirement.
* `@RequiresBest` ensures that it is always the service with the best
  ranking that is injected in the component.
* The `@PostRegistration` and `@PreUnregistration` callbacks allows
  the component to be notified right after one of its services has
  been registered or will be unregistered.

### HTTP Service

* The generated 404 page shows the list of registered servlets paths.
* The 404 and 500 error pages can be customized by a hook service.
* The default binding address is back to `0.0.0.0` instead of
  `localhost` (for those who used the development version).

### Utilities

* The `ThreadPool` class is now a cached thread pool. It now has a
  minimum and maximum number of threads: only the required threads are
  alive. A thread waits for a task during 60 seconds (by default)
  before stopping.

## iPOPO 0.5.8

:::{admonition} Release Date
:class: info

2014-10-13
:::

### Framework

* `FrameworkFactory.delete_framework()` can be called with `None` or
  without argument. This simplifies the clean up afters tests, etc.
* The list returned by `Framework.get_bundles()` is always sorted by bundle ID.

### iPOPO

* Added the `immediate_rebind` option to the `@Requires` decorator.
  This indicates iPOPO to not invalidate then re-validate a component
  if a service can replace an unbound required one. This option only
  applies to non-optional, non-aggregate requirements.

### Shell

* The I/O handler is now part of a `ShellSession` bean. The latter has
  the same API as the I/O handler so there is no need to update
  existing commands. I/O Handler write methods are now synchronized.
* The shell supports variables as arguments, *e.g.* `echo $var`. See
  [string.Template](https://docs.python.org/3/library/string.html#template-strings)
  for more information. The Template used in Pelix Shell allows `.` (dot) in names.
* A special variable `$?` stores the result of the last command which
  returned a result, *i.e.* anything but `None` or `False`.
* Added *set* and *unset* commands to work with variables
* Added the *run* command to execute a script file.
* Added protection against `AttributeError` in *threads* and *thread*

## iPOPO 0.5.7

:::{admonition} Release Date
:class: info

2014-09-18
:::

### Project

* Code review to be more PEP-8 compliant
* [jsonrpclib-pelix](https://pypi.org/project/jsonrpclib-pelix/) is
  now an install requirement (instead of an optional one)

### Framework

* Forget about previous global members when calling `Bundle.update()`.
  This ensures to have a fresh dictionary of members after a bundle update
* Removed `from pelix.constants import *` in `pelix.framework`: only
  use `pelix.constants` to access constants

### Remote Services

* Added support for endpoint name reuse
* Added support for synonyms: specifications that can be used on the
  remote side, or which describe a specification of another language
  (*e.g.* a Java interface)
* Added support for a `pelix.remote.export.reject` service property:
  the specifications it contains won't be exported, event if
  indicated in `service.exported.interfaces`.
* JABSORB-RPC:
  * Use the common `dispatch()` method, like JSON-RPC
* MQTT(-RPC):
  * Explicitly stop the reading loop when the MQTT client is disconnecting
  * Handle unknown correlation ID

### Shell

* Added a `loglevel` shell command, to update the log level of any logger
* Added a `--verbose` argument to the shell console script
* Remote shell module can be ran as a script

### HTTP Service

* Remove double-slashes when looking for a servlet

### XMPP

* Added base classes to write a XMPP client based on
  [SleekXMPP](https://github.com/fritzy/SleekXMPP)
* Added a XMPP shell interface, to control Pelix/iPOPO from XMPP

### Miscellaneous

* Added an IPv6 utility module, to setup double-stack and to avoids
  missing constants bugs in Windows versions of Python
* Added a `EventData` class: it acts like `Event`, but it allows to
  store a data when setting the event, or to raise an exception in all
  callers of `wait()`
* Added a `CountdownEvent` class, an `Event` which is set until a
  given number of calls to `step()` is reached
* `threading.Future` class now supports a callback methods, to avoid
  to actively wait for a result.

## iPOPO 0.5.6

:::{admonition} Release Date
:class: info

2014-04-28
:::

### Project

* Added samples to the project repository
* Removed the static website from the repository
* Added the project to [Coveralls](https://coveralls.io/)
* Increased code coverage

### Framework

* Added a `@BundleActivator` decorator, to define the bundle activator
  class. The `activator` module variable should be replaced by this decorator.
* Renamed specifications constants: from `XXX_SPEC` to `SERVICE_XXX`

### iPOPO

* Added a *waiting list* service: instantiates components as soon as
  the iPOPO service and the component factory are registered
* Added `@RequiresMap` handler
* Added an `if_valid` parameter to binding callbacks decorators:
  `@Bind`, `@Update`, `@Unbind`, `@BindField`, `@UpdateField`,
  `@UnbindField`. The decorated method will be called if and only if
  the component valid.
* The `get_factory_context()` from `decorators` becomes public to ease
  the implementation of new decorators

### Remote Services

* Large rewriting of Remote Service core modules
  * Now using OSGi Remote Services properties
  * Added support for the OSGi EDEF file format (XML)
* Added an abstract class to easily write RPC implementations
* Added mDNS service discovery
* Added an MQTT discovery protocol
* Added an MQTT-RPC protocol, based on Node.js
  [MQTT-RPC module](https://github.com/wolfeidau/mqtt-rpc)
* Added a Jabsorb-RPC transport. Pelix can now use Java services and vice-versa, using:
    * [Cohorte Remote Services](https://github.com/cohorte/cohorte-remote-services)
    * [Eclipse ECF](https://wiki.eclipse.org/ECF/) and the
      [Jabsorb-RPC provider](https://github.com/cohorte/cohorte-remote-services/tree/master/deprecated/org.cohorte.ecf.provider.jabsorb)

### Shell

* Enhanced completion with `readline`
* Enhanced commands help generation
* Added arguments to filter the output of `bl`, `sl`, `factories` and `instances`
* Corrected `prompt` when using `readline`
* Corrected `write_lines()` when not giving format arguments
* Added an `echo` command, to test string parsing

### Services

* Added support for *managed service factories* in ConfigurationAdmin
* Added an EventAdmin-MQTT bridge: events from EventAdmin with an
  `event.propagate` property are published over MQTT
* Added an early version of an MQTT Client Factory service

### Miscellaneous

* Added a `misc` package, with utility modules and bundles:
  * `eventadmin_printer`: an EventAdmin handler that prints
    or logs the events it receives
  * `jabsorb`: converts dictionary from and to the Jabsorb-RPC format
  * `mqtt_client`: a wrapper for the [Paho](https://eclipse.dev/paho/)
     MQTT client, used in MQTT discovery and MQTT-RPC.

## iPOPO 0.5.5

:::{admonition} Release Date
:class: info

2013-11-15
:::

### Project

The license of the iPOPO project is now the
[Apache Software License 2.0](https://www.apache.org/licenses/LICENSE-2.0.html).

### Framework

* `get_*_service_reference*()` methods have a default LDAP filter set to `None`.
  Only the service specification is required, event if set to `None`.
* Added a context `use_service(context, svc_ref)`, that allows to
  consume a service in a `with` block.

### iPOPO

* Added the *Handler Factory* pattern: all instance handlers are
  created by their factory, called by iPOPO according to the handler
  IDs found in the factory context. This will simplify the creation of
  new handlers.

### Services

* Added the `ConfigurationAdmin` service
* Added the `FileInstall` service

## iPOPO 0.5.4

:::{admonition} Release Date
:class: info

2013-10-01
:::

### Project

* Global speedup replacing `list.append()` by `bisect.insort()`.
* Optimizations in handling services, components and LDAP filters.
* Some classes of Pelix framework and iPOPO core modules extracted to new modules.
* Fixed support of Python 2.6.
* Replaced Python 3 imports conditions by *try-except* blocks.

### iPOPO

* `@Requires` accepts only one specification
* Added a context `use_ipopo(bundle_context)`, to simplify the usage
  of the iPOPO service, using the keyword `with`.
* `get_factory_details(name)` method now also returns the ID of the
  bundle provided the component factory, and the component instance
  properties.
* Protection of the unregistration of factories, as a component can
  kill another one of the factory during its invalidation.

### Remote Services

* Protection of the unregistration loop during the invalidation of
  JSON-RPC and XML-RPC exporters.
* The *Dispatcher Servlet* now handles the *discovered* part of the
  discovery process. This simplifies the *Multicast Discovery*
  component and suppresses a socket bug/feature on BSD (including Mac OS).

### Shell

* The help command now uses the `inspect` module to list the required
  and optional parameters.
* `IOHandler` now has a `prompt()` method to ask the user to enter a line.
  It replaces the `read()` method, which was to buggy.
* The `make_table()` method now accepts generators as parameters.
* Remote commands handling removed: `get_methods_names()` is not used anymore.

## iPOPO 0.5.3

:::{admonition} Release Date
:class: info

2013-08-01
:::

### iPOPO

* New `get_factory_details(name)` method in the iPOPO service, acting
  like `get_instance_details(name)` but for factories. It returns a
  dictionary describing the given factory.
* New `factory` shell command, which describes a component factory:
  properties, requirements, provided services, ...

### HTTP Service

* Servlet exceptions are now both sent to the client and logged locally

### Remote Services

* Data read from the servlets or sockets are now properly converted
  from bytes to string before being parsed (Python 3 compatibility).

### Shell

* Exceptions are now printed using `str(ex)` instead of `ex.message`
  (Python 3 compatibility).
* The shell output is now flushed, both by the shell I/O handler and
  the text console. The remote console was already flushing its
  output. This allows to run the Pelix shell correctly inside Eclipse.

## iPOPO 0.5.2

:::{admonition} Release Date
:class: info

2013-07-19
:::

### iPOPO

* An error is now logged if a class is manipulated twice. Decorators
  executed after the first manipulation, i.e. upon
  `@ComponentFactory()`, are ignored.
* Better handling of inherited and overridden methods: a decorated
  method can now be overridden in a child class, with the name,
  without warnings.
* Better error logs, with indication of the error source file and line

### HTTP Service

* New servlet binding parameters:
  * `http.name`: Name of HTTP service. The name of component
    instance in the case of the basic implementation.
  * `http.extra`: Extra properties of the HTTP service. In the
    basic implementation, this the content of the `http.extra`
    property of the HTTP server component
* New method `accept_binding(path, params)` in servlets. This allows
  to refuse the binding with a server before to test the availability
  of the registration path, thus to avoid raising a meaningless exception.

### Remote Services

* End points are stored according to their framework
* Added a method `lost_framework(uid)` in the registry of imported
  services, which unregisters all the services provided by the given framework.

### Shell

* Shell *help* command now accepts a command name to print a specific documentation

## iPOPO 0.5.1

:::{admonition} Release Date
:class: info

2013-07-05
:::

### Framework

* `Bundle.update()` now logs the SyntaxError exception that be raised in Python 3.

### HTTP Service

* The HTTP service now supports the update of servlet services
  properties. A servlet service can now update its registration path
  property after having been bound to a HTTP service.
* A *500 server error* page containing an exception trace is now
  generated when a servlet fails.
* The `bound_to()` method of a servlet is called only after the HTTP
  service is ready to accept clients.

### Shell

* The remote shell now provides a service, `pelix.shell.remote`, with
  a `get_access()` method that returns the *(host, port)* tuple where
  the remote shell is waiting for clients.
* Fixed the `threads` command that wasn't working on Python 3.

## iPOPO 0.5

:::{admonition} Release Date
:class: info

2013-05-21
:::

### Framework

* `BundleContext.install_bundle()` now returns the `Bundle` object
  instead of the bundle ID. `BundleContext.get_bundle()` has been
  updated to accept both IDs and `Bundle` objects in order to keep a
  bit of compatibility
* `Framework.get_symbolic_name()` now returns `pelix.framework`
  instead of `org.psem2m.pelix`
* `ServiceEvent.get_type()` is renamed `get_kind()`. The other name is
  still available but is declared deprecated (a warning is logged on
  its first use).
* `BundleContext.install_visiting(path, visitor)`: visits the given
  path and installs the found modules if the visitor accepts them
* `BundleContext.install_package(path)` (*experimental*):
  * Installs all the modules found in the package at the given path
  * Based on `install_visiting()`

### iPOPO

* Components with a `pelix.ipopo.auto_restart` property set to `True` are
  automatically re-instantiated after their bundle has been updated.

### Services

* Remote Services: use services of a distant Pelix instance
  * Multicast discovery
  * XML-RPC transport (not fully usable)
  * JSON-RPC transport (based on a patched version of jsonrpclib)
* EventAdmin: send events (a)synchronously

### Shell

* Shell command methods now take an `IOHandler` object in parameter
  instead of input and output file-like streams. This hides the
  compatibility tricks between Python 2 and 3 and simplifies the
  output formatting.

## iPOPO 0.4

:::{admonition} Release Date
:class: info

2012-11-21
:::

### Framework

* New `create_framework()` utility method
* The framework has been refactored, allowing more efficient services
  and events handling

### iPOPO

 * A component can provide multiple services
 * A service controller can be injected for each provided service, to
   activate or deactivate its registration
 * Dependency injection and service providing mechanisms have been
   refactored, using a basic handler concept.

### Services

* Added a HTTP service component, using the concept of *servlet*
* Added an extensible shell, interactive and remote, simplifying the
  usage of a framework instance

## iPOPO 0.3

:::{admonition} Release Date
:class: info

2012-04-13
:::

Packages have been renamed. As the project goes public, it may not have
relations to isandlaTech projects anymore.

| Previous name            | New name           |
|--------------------------|--------------------|
| `psem2m`                 | `pelix`            |
| `psem2m.service.pelix`   | `pelix.framework`  |
| `psem2m.component`       | `pelix.ipopo`      |
| `psem2m.component.ipopo` | `pelix.ipopo.core` |

## iPOPO 0.2

:::{admonition} Release Date
:class: info

2012-02-07
:::

Version 0.2 is the first public release of the project, under the terms
of the [GPLv3 license](https://www.gnu.org/licenses/gpl-3.0.txt).

## iPOPO 0.1

:::{admonition} Release Date
:class: info

2012-01-20
:::

The first version of the Pelix framework, with packages still named
after the `python.injection` and PSEM2M (now named Cohorte) projects by
isandlaTech (now named Cohorte Technologies).

Back then, Pelix (bundles and services) was the most advanced part of
the project, iPOPO was only an extension of it to handle basic
components.

## python.injections

:::{admonition} Release Date
:class: info

2011-12-20
:::

The proof-of-concept package trying to mimic the iPOJO framework in
Python 2.6. It only supported basic injections described by decorators.
