.. _configadmin:

Configuration Admin
###################

Concept
=======

The Configuration Admin service allows to easily set, update and delete the
configuration (a dictionary) of managed services.

The Configuration Admin service can be used by any bundle to configure a
service, either by creating, updating or deleting a Configuration object.

The Configuration Admin service handles the persistence of configurations and
distributes them to their target services.

Two kinds of managed services exist:

* Managed Services, which handle the configuration as is
* Managed Service Factories, which can handle multiple configuration of a kind

.. note:: Even if iPOPO doesn't fully respect it, you can find details about
   the Configuration Admin Service Specification in the
   `chapter 104 <https://docs.osgi.org/specification/osgi.cmpn/8.1.0/service.cm.html>`_
   of the OSGi Compendium Services Specification.

.. note:: This page is highly inspired from the
   `Configuration Admin tutorial <https://web.archive.org/web/20200229033154/http://felix.apache.org/documentation/subprojects/apache-felix-config-admin.html>`_
   from the `Apache Felix project <https://felix.apache.org/documentation/index.html>`_.


Basic Usage
===========

Here is a very basic example of a managed service able to handle a single
configuration.
This configuration contains a single entry: the length of a pretty printer.

The managed service must provide the ``pelix.configadmin.managed``
specification, associated to a persistent ID (PID) identifying its
configuration (``service.pid``).

The PID is just a string, which must be globally unique.
Assuming a simple case where your pretty printer configurator receives the
configuration has a unique class name, you may well use that name.

So lets assume, our managed service is called ``PrettyPrinter`` and that name
is also used as the PID.
The class would be:

.. code-block:: python

   class PrettyPrinter:
       def updated(self, props):
           """
           A configuration has been updated
           """
           if props is None:
               # Configuration have been deleted
               pass
           else:
               # Apply configuration from config admin
               pass

Now, in your bundle activator's ``start()`` method you can register
``PrettyPrinter`` as a managed service:

.. code-block:: python

   @BundleActivator
   class Activator:
       def __init__(self):
           self.svc_reg = None

       def start(self, context):
           svc_props = {"service.pid": "pretty.printer"}
           self.svc_reg = context.register_service(
               "pelix.configadmin.managed", PrettyPrinter(), svc_props)

       def stop(self, context):
           if self.svc_reg is not None:
               self.svc_reg.unregister()
               self.svc_reg = None

That's more or less it.
You may now go on to use your favourite tool to create and edit the
configuration for the Pretty Printer, for example something like this:

.. code-block:: python

   # Get the current configuration
   pid = "pretty.printer"
   config = config_admin_svc.get_configuration(pid)
   props = config.get_properties()
   if props is None:
      props = {}

   # Set properties
   props.put("key", "value")

   # Update the configuration
   config.update(props)

After the call to ``update()`` the Configuration Admin service persists the new
configuration data and sends an update to the managed service registered with
the service PID ``pretty.printer``, which happens to be our PrettyPrinter class
as expected.


Managed Service Factory example
===============================

Registering a service as a Managed Service Factory means that it will be able
to receive several different configuration dictionaries.
This can be useful when used by a Service Factory, that is,
a service responsible for creating a distinct instance of a service according
to the bundle consuming it.

A Managed Service Factory needs to provide the
``pelix.configadmin.managed.factory`` specification, as shown below:

.. code-block:: python

   class SmsSenderFactory:
       def __init__(self):
           self.existing = {}

       def updated(pid, props):
           """
           Called when a configuration has been created or updated
           """
           if pid in self.existing:
               # Service already exist
               self.existing[pid].configure(props)
           else:
               # Create the service
               svc = self.create_instance()
               svc.configure(props)
               self.existing[pid] = service

       def deleted(pid):
           """
           Called when a configuration has been deleted
           """
           self.existing[pid].close()
           del self.existing[pid]


The example above shows that, differently from a managed service, the
managed service factory is designed to manage multiple instances of a service.

In fact, the ``updated`` method accept a PID and a dictionary as arguments,
thus allowing to associate a certain configuration dictionary to a particular
service instance (identified by the PID).

Note also that the managed service factory specification requires to implement
(besides the getName method) a ``deleted`` method: this method is invoked when
the Configuration Admin service asks the managed service factory to delete a
specific instance.

The registration of a managed service factory follows the same steps of the
managed service sample:

.. code-block:: python

   @BundleActivator
   class Activator:
       def __init__(self):
           self.svc_reg = None

       def start(self, context):
           svc_props = {"service.pid": "sms.sender"}
           self.svc_reg = context.register_service(
               "pelix.configadmin.managed.factory", SmsSenderFactory(),
               svc_props)

       def stop(self, context):
           if self.svc_reg is not None:
               self.svc_reg.unregister()
               self.svc_reg = None


Finally, using the ConfigurationAdmin interface, it is possible to send new or
updated configuration dictionaries to the newly created managed service
factory:

.. code-block:: python

   @BundleActivator
   class Activator:
       def __init__(self):
           self.configs = {}

       def start(self, context):
           svc_ref = context.get_service_reference("pelix.configadmin")
           if svc_ref is not None:
               # Get the configuration admin service
               config_admin_svc = context.get_service(svc_ref)

               # Create a new configuration for the given factory
               config = config_admin_svc.create_factory_configuration(
                   "sms.sender")

               # Update it
               props = {"key": "value"}
               config.update(props)

               # Store it for future use
               self.configs[config.get_pid()] = config

       def stop(self, context):
           # Clear all configurations (for this example)
           for config in self.configs:
               config.delete()

           self.configs.clear()
