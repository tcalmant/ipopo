.. _ipopo_configadmin:

.. module:: pelix.ipopo.configadmin

Components and Configuration Admin
##################################

Concept
=======

The ``pelix.ipopo.configadmin`` bundle bridges :ref:`configadmin` and iPOPO:
it lets an administrator manage a composition at runtime, without writing any
code and without restarting the framework.

It provides three mechanisms:

* a *factory configuration* describes a component instance: creating it
  instantiates the component, updating it reconfigures the component, and
  deleting it kills the component;
* a component which declares a ``service.pid`` property gets the entries of
  the configuration with that PID injected in its properties;
* a component whose factory uses the :class:`~pelix.ipopo.decorators.RequiresConfiguration`
  decorator waits for its configuration before being validated.

This is the counterpart of the ``configuration-policy`` attribute and of the
factory configurations described in the
`chapter 112 <https://docs.osgi.org/specification/osgi.cmpn/8.1.0/service.component.html>`_
of the OSGi Compendium Services Specification, adapted to iPOPO: there is no
callback receiving a configuration dictionary, the entries of a configuration
are simply mapped onto the *properties* of the component.

.. note:: A configuration entry which is only read when the component is
   created, like ``requires.filters`` or ``temporal.timeouts``, keeps its
   initial value when the configuration is updated. Use the ``restart``
   update policy described below to take those into account.

.. note:: A property declared with ``@HiddenProperty`` never becomes public: a
   configuration entry of the same name is ignored. To update it
   confidentially, e.g. to rotate a password, prefix its name with a dot
   (``.password`` updates the ``password`` property).

.. note:: ``service.pid``, ``service.factoryPid`` and ``service.bundleLocation``
   are added by ConfigurationAdmin, not the administrator, and are never
   treated as component properties to remove: a component keeps its PID even
   after its configuration is deleted.


Setting up
==========

The bridge requires the ConfigurationAdmin service and the iPOPO waiting list.
The handler of the ``@RequiresConfiguration`` decorator lives in its own
bundle, which must be installed for the components of a decorated factory to
be instantiated.

.. code-block:: python

   framework = create_framework(
       (
           "pelix.ipopo.core",
           "pelix.ipopo.waiting",
           "pelix.ipopo.handlers.configadmin",
           "pelix.services.configadmin",
           "pelix.ipopo.configadmin",
       )
   )


Creating components from configurations
=======================================

The bridge handles the factory configurations of the
``pelix.ipopo.component`` PID
(:py:const:`pelix.ipopo.constants.IPOPO_CONFIGADMIN_FACTORY_PID`).
Each of those configurations describes one component instance and recognises
the following entries:

+--------------------------+--------------------------------------------------+
| Entry                    | Description                                      |
+==========================+==================================================+
| ``ipopo.factory.name``   | Name of the iPOPO factory to instantiate.        |
|                          | Mandatory: a configuration without it is ignored |
+--------------------------+--------------------------------------------------+
| ``instance.name``        | Name of the component instance. Defaults to the  |
|                          | PID of the configuration                         |
+--------------------------+--------------------------------------------------+
| ``ipopo.update.policy``  | Either ``reconfigure`` (default), to update the  |
|                          | properties of the live component, or ``restart``,|
|                          | to kill it and instantiate it again              |
+--------------------------+--------------------------------------------------+

Only ``ipopo.factory.name`` and ``ipopo.update.policy`` are consumed by the
bridge: every other entry, including ``instance.name`` and the
``service.pid``/``service.factoryPid`` entries added by ConfigurationAdmin,
becomes a property of the component.

Here is a session with the Pelix shell, using the commands of the
``pelix.shell.configadmin`` and ``pelix.shell.ipopo`` bundles:

.. code-block:: text

   $ config.create pelix.ipopo.component ipopo.factory.name=hello-factory \
         instance.name=hello name=world
   New configuration: pelix.ipopo.component-3d5b0f6e-...
   $ instances
   +-------+---------------+-------+
   | Name  | Factory       | State |
   +=======+===============+=======+
   | hello | hello-factory | VALID |
   +-------+---------------+-------+
   $ config.update pelix.ipopo.component-3d5b0f6e-... name=pelix
   $ config.delete pelix.ipopo.component-3d5b0f6e-...

The same can be done programmatically:

.. code-block:: python

   from pelix.ipopo.constants import (
       IPOPO_CONFIG_FACTORY_NAME,
       IPOPO_CONFIGADMIN_FACTORY_PID,
       IPOPO_INSTANCE_NAME,
   )

   config = config_admin.create_factory_configuration(IPOPO_CONFIGADMIN_FACTORY_PID)
   config.update(
       {
           IPOPO_CONFIG_FACTORY_NAME: "hello-factory",
           IPOPO_INSTANCE_NAME: "hello",
           "name": "world",
       }
   )

Components go through the :ref:`iPOPO waiting list <refcard_component>`: a
configuration naming a factory which isn't registered yet is honoured as soon
as it appears, and again if its bundle is stopped then started. With the
default JSON storage, configurations are persistent: the components they
describe come back the next time the framework starts. Stopping the
``pelix.ipopo.configadmin`` bundle kills the components it created.

.. note:: A property removed from a configuration goes back to the value
   declared by the factory with ``@Property``, or to ``None`` if the factory
   doesn't declare it.


Configuring existing components
===============================

A component which declares a ``service.pid`` property, whatever the way it has
been instantiated, follows the configuration with that PID: its entries are
injected in the properties of the component when the configuration is updated,
and the properties go back to their declared value when it is deleted.

.. code-block:: python

   from pelix.constants import SERVICE_PID
   from pelix.ipopo.decorators import ComponentFactory, Instantiate, Property

   @ComponentFactory()
   @Property("_name", "name", "world")
   @Property("_pid", SERVICE_PID, "sample.hello")
   @Instantiate("hello")
   class Hello:
       ...

Components created from a factory configuration, components using the
``@RequiresConfiguration`` decorator and components providing a managed
service are left alone: they already follow their own configuration.

.. note:: Here also, a property removed from the configuration goes back to
   the value declared by the factory with ``@Property``, not to the value it
   was given when the component was instantiated. Use ``@RequiresConfiguration``
   when the component must recover its instantiation values.

.. warning:: Nothing delays the validation of such a component: it is
   validated with the values declared by its factory, then reconfigured once
   the configuration reaches it. Use ``@RequiresConfiguration`` when the
   component must not run without its configuration.


Waiting for a configuration
===========================

The ``@RequiresConfiguration`` decorator binds the components of a factory to
a configuration and, unless the requirement is declared optional, keeps them
invalid as long as no configuration is available.

.. code-block:: python

   from pelix.ipopo.decorators import (
       ComponentFactory, Instantiate, Property, RequiresConfiguration, Validate
   )

   @ComponentFactory()
   @Property("_name", "name", "world")
   @RequiresConfiguration("sample.hello")
   @Instantiate("hello")
   class Hello:
       @Validate
       def validate(self, context):
           # Called only once the "sample.hello" configuration exists:
           # self._name holds the value it gives
           print("Hello,", self._name)

The PID can be omitted, in which case the ``service.pid`` property of the
component is used. This allows several instances of the same factory to follow
different configurations:

.. code-block:: python

   @ComponentFactory("hello-factory")
   @Property("_name", "name", "world")
   @Property("_pid", SERVICE_PID)
   @RequiresConfiguration()
   class Hello:
       ...

   # Then, in a configuration or in an initialization file:
   #   instance.name=hello-fr, service.pid=sample.hello.fr

The ``update_policy`` argument tells what happens when the configuration of a
running component is updated: ``reconfigure`` (default) updates its properties
in place, ``restart`` invalidates the component before applying them, so that
the ``@Validate`` callback is called again.

.. autoclass:: pelix.ipopo.decorators.RequiresConfiguration
   :members:
   :noindex:
