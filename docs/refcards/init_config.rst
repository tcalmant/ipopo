.. _refcard_init_config:
.. module:: pelix.misc.init_handler

Initial Configuration File
==========================

The ``pelix.misc.init_handler`` module provides the :class:`~InitFileHandler`
class.
It is able to load the configuration of an iPOPO framework, from one or
multiple files.

This configuration allows to setup environment variables, additional Python
paths, framework properties, a list of bundles to start with the framework
and a list of components to instantiate.


File Format
-----------

Configuration files are in JSON format, with a root object which can contain
the following entries:

* ``properties``: a JSON object defining the initial properties of the
  framework. The object keys must be strings, but can be associated to any
  valid JSON value.
* ``environment``: a JSON object defining new environment variables for the
  process running the framework. Both keys and values must be strings.
* ``paths``: a JSON array containing paths to add to the Python lookup paths.
  The given paths will be prioritized, *i.e.* if a path was already defined in
  ``sys.path``, it will be moved forward.
  The given paths can contains environment variables and the user path marker
  (``~``).

  Note that the current working directory (*cwd*) will always be the first
  element of ``sys.path`` when using an initial configuration handler.
* ``bundles``: a JSON array containing the names of the bundles to install and
  start with the framework.
* ``components``: a JSON array of JSON objects defining the components to
  instantiate. Each component description has the following entries:

  * ``factory``: the name of the component factory
  * ``name``: the name of the instance
  * ``properties`` (optional): a JSON object defining the initial properties of
    the component

Here is a sample initial configuration file:

.. code-block:: javascript

   {
     "properties": {
       "some.value": 42,
       "framework.uuid": "custom-uuid",
       "arrays": ["they", "work", "too", 123],
       "dicts": {"why": "not?"}
     },
     "environment": {
       "new_path": "/opt/foo",
       "LANG": "en_US.UTF-8"
     },
     "paths": [
       "/opt/bar",
       "$new_path/mylib.zip"
     ],
     "bundles": [
       "pelix.misc.log",
       "pelix.shell.log",
       "pelix.http.basic"
     ],
     "components": [
       {
         "factory": "pelix.http.service.basic.factory",
         "name": "httpd",
         "properties": {
            "pelix.http.address": "127.0.0.1"
         }
       }
     ]
   }

Moreover, if the root object contains a ``reset_<name>`` entry, then the
previously loaded configuration for the ``<name>`` entry are forgotten: the
current configuration will replace the old one instead of updating it.

For example:

.. code-block:: javascript

   {
     "bundles": [
        "pelix.http.basic"
     ],
     "reset_bundles": true
   }

When this file will be loaded, the list of bundles declared by previously loaded
configuration files will be cleared and replaced by the one in this file.

.. _init_conf_lookup:

File lookup
-----------

A :class:`~InitFileHandler` object updates its internal state with the content
of the files it parses.
As a result, multiple configuration files can be used to start framework with
a common basic configuration.

When calling :meth:`~InitFileHandler.load` without argument, the handler will
try to load all the files named ``.pelix.conf`` in the following folders and
order:

* ``/etc/default``
* ``/etc``
* ``/usr/local/etc``
* ``~/.local/pelix``
* ``~/.config``
* ``~`` (user directory)
* ``.`` (current working directory)

When giving a file name to :meth:`~InitFileHandler.load`, the handler
will merge the configuration it contains with its current state.

Finally, after having updated a configuration, the :class:`~InitFileHandler`
will remove duplicated in Python path and bundles configurations.


Support in Pelix shell
----------------------

The framework doesn't starts a :class:`~InitFileHandler` on its own: it must be
created and loaded before creating the framework.

Currently, only the Pelix Shell Console supports the initial configuration,
using the following arguments:

* *no argument*: the `.pelix.conf` files are loaded as described in
  :ref:`init_conf_lookup`.
* ``-e``, ``--empty-conf``: no initial configuration file will be loaded
* ``-c <filename>``, ``--conf <filename>``: the default configuration files,
  then given one will be loaded.
* ``-C <filename>``, ``--exclusive-conf <filename>``: only the given
  configuration file will be loaded.

It is planned that the support for initial configuration files will be added
to other shells in future iPOPO versions.


API
---

.. autoclass:: InitFileHandler
   :members: clear, load, normalize, instantiate_components, bundles,
             properties

Sample API Usage
----------------

This sample starts a framework based on the default configuration files, plus
a given one named *some_file.json*.

.. code-block:: python

    import pelix.framework as pelix
    from pelix.misc.init_handler import InitFileHandler

    # Read the initial configuration script
    init = InitFileHandler()

    # Load default configuration
    init.load()

    # Load the given configuration file
    init.load("some_file.json")

    # Normalize configuration (forge sys.path)
    init.normalize()

    # Use the utility method to create, run and delete the framework
    framework = pelix.create_framework(init.bundles, init.properties)
    framework.start()

    # Instantiate configured components
    init.instantiate_components(framework.get_bundle_context())

    # Let the framework live
    try:
        framework.wait_for_stop()
    except KeyboardInterrupt:
        framework.stop()
