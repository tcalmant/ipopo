.. _quickstart:

Quickstart
##########

Eager to get started? This page gives a good introduction to iPOPO.
It assumes you already have iPOPO installed. If you do not, head over
to the :ref:`installation` section.

.. _quick_shell:

Play with the shell
===================

The easiest way to see how iPOPO works is by playing with the builtin
shell.

To start the shell locally, you can run the following command::

    bash$ python -m pelix.shell
    ** Pelix Shell prompt **
    $

Survival Kit
------------

As always, the life-saving command is ``help``::

    $ help
    === Name space 'default' ===
    - ? [<command>]
                    Prints the available methods and their documentation,
                    or the documentation of the given command.
    - bd <bundle_id>
                    Prints the details of the bundle with the given ID
                    or name
    - bl [<name>]
                    Lists the bundles in the framework and their state.
                    Possibility to filter on the bundle name.
    ...
    $

The must-be-known shell commands of iPOPO are the following:

======== =======================================================
Command  Description
======== =======================================================
help     Shows the help
loglevel Prints/Changes the log level
exit     Quits the shell (and stops the framework in console UI)
threads  Prints the stack trace of all threads
run      Runs a shell script
======== =======================================================

Bundle commands
---------------

The following commands can be used to handle bundles in the framework:

========= =======================================================
Command   Description
========= =======================================================
install   Installs a module as a bundle
start     Starts the given bundle
update    Updates the given bundle (restarts it if necessary)
uninstall Uninstalls the given bundle (stops it if necessary)
bl        Lists the installed bundles and their state
bd        Prints the details of a bundle
========= =======================================================

In the following example, we install the ``pelix.shell.remote`` bundle,
and play a little with it::

    $ install pelix.shell.remote
    Bundle ID: 12
    $ start 12
    Starting bundle 12 (pelix.shell.remote)...
    $ bl
    +----+----------------------------------------+--------+---------+
    | ID |                  Name                  | State  | Version |
    +====+========================================+========+=========+
    | 0  | pelix.framework                        | ACTIVE | 0.6.4   |
    +----+----------------------------------------+--------+---------+
    ...
    +----+----------------------------------------+--------+---------+
    | 12 | pelix.shell.remote                     | ACTIVE | 0.6.4   |
    +----+----------------------------------------+--------+---------+
    13 bundles installed
    $ update 12
    Updating bundle 12 (pelix.shell.remote)...
    $ stop 12
    Stopping bundle 12 (pelix.shell.remote)...
    $ uninstall 12
    Uninstalling bundle 12 (pelix.shell.remote)...
    $

While the ``install`` command requires the name of a module as argument,
all other commands accepts a bundle ID as argument.

Service Commands
----------------

Services are handles by bundles and can't be modified using the shell.
The following commands can be used to check the state of the service
registry:

======= ================================
Command Description
======= ================================
sl      Lists the registered services
sd      Prints the details of a services
======= ================================

This sample prints the details about the iPOPO core service::

    $ sl
    +----+---------------------------+----------------------------------------------------+---------+
    | ID |      Specifications       |                       Bundle                       | Ranking |
    +====+===========================+====================================================+=========+
    | 1  | ['ipopo.handler.factory'] | Bundle(ID=5, Name=pelix.ipopo.handlers.properties) | 0       |
    +----+---------------------------+----------------------------------------------------+---------+
    ...
    +----+---------------------------+----------------------------------------------------+---------+
    | 8  | ['pelix.ipopo.core']      | Bundle(ID=1, Name=pelix.ipopo.core)                | 0       |
    +----+---------------------------+----------------------------------------------------+---------+
    ...
    11 services registered
    $ sd 8
    ID............: 8
    Rank..........: 0
    Specifications: ['pelix.ipopo.core']
    Bundle........: Bundle(ID=1, Name=pelix.ipopo.core)
    Properties....:
            objectClass = ['pelix.ipopo.core']
            service.id = 8
            service.ranking = 0
    Bundles using this service:
            Bundle(ID=4, Name=pelix.shell.ipopo)
    $

iPOPO Commands
--------------

iPOPO provides a set of commands to handle the components and their
factories:

=========== ============================================
Command     Description
=========== ============================================
factories   Lists registered component factories
factory     Prints the details of a factory
instances   Lists components instances
instance    Prints the details of a component
waiting     Lists the components waiting for an handler
instantiate Starts a new component instance
kill        Kills a component
retry       Retry the validation of a component
=========== ============================================

This snippets installs the ``pelix.shell.remote`` bundle and
instantiate a new remote shell component::

    $ install pelix.shell.remote
    Bundle ID: 12
    $ start 12
    Starting bundle 12 (pelix.shell.remote)...
    $ factories
    +------------------------------+----------------------------------------+
    |           Factory            |                 Bundle                 |
    +==============================+========================================+
    | ipopo-remote-shell-factory   | Bundle(ID=12, Name=pelix.shell.remote) |
    +------------------------------+----------------------------------------+
    | ipopo-shell-commands-factory | Bundle(ID=4, Name=pelix.shell.ipopo)   |
    +------------------------------+----------------------------------------+
    2 factories available
    $ instantiate ipopo-remote-shell-factory rshell pelix.shell.address=0.0.0.0 pelix.shell.port=9000
    Component 'rshell' instantiated.

A remote shell as been started on port 9000 and can be accessed using Netcat::

    bash$ nc localhost 9000
    ------------------------------------------------------------------------
    ** Pelix Shell prompt **

    iPOPO Remote Shell
    ------------------------------------------------------------------------
    $

The remote shell gives access to the same commands as the console UI.
Note that an XMPP version of the shell also exists.

To stop the remote shell, you have to kill the component::

    $ kill rshell
    Component 'rshell' killed.

Finally, to stop the shell, simply run the ``exit`` command or press
``Ctrl+D``.

Hello World!
============

In this section, we will create a service provider and its consumer using iPOPO.
The consumer will use the provider to print a greeting message as soon as it
is bound to it.
To simplify this first sample, the consumer can only be bound to a single
service and its life-cycle is highly tied to the availability of this service.

Here is the code of the provider component, which should be store in the
``provider`` module (``provider.py``).
The component will provide a service with of the ``hello.world`` specification.

.. code-block:: python

   from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate

   # Define the component factory, with a given name
   @ComponentFactory("service-provider-factory")
   # Defines the service to provide when the component is active
   @Provides("hello.world")
   # A component must be instantiated as soon as the bundle is active
   @Instantiate("provider")
   # Don't forget to inherit from object, for Python 2.x compatibility
   class Greetings(object):
         def hello(self, name="World"):
             print("Hello,", name, "!")

Start a Pelix shell like shown in the previous section, then install and start
the provider bundle::

    ** Pelix Shell prompt **
    $ install provider
    Bundle ID: 12
    $ start 12
    Starting bundle 12 (provider)...
    $

The consumer will require the ``hello.world`` service and use it when it is
validated, *i.e.* once this service has been injected.
Here is the code of this component, which should be store in the ``consumer``
module (``consumer.py``).

.. code-block:: python

   from pelix.ipopo.decorators import ComponentFactory, Requires, Instantiate, \
        Validate, Invalidate

   # Define the component factory, with a given name
   @ComponentFactory("service-consumer-factory")
   # Defines the service required by the component to be active
   # The service will be injected in the '_svc' field
   @Requires("_svc", "hello.world")
   # A component must be instantiated as soon as the bundle is active
   @Instantiate("consumer")
   # Don't forget to inherit from object, for Python 2.x compatibility
   class Consumer(object):
         @Validate
         def validate(self, context):
             print("Component validated, calling the service...")
             self._svc.hello("World")
             print("Done.")

         @Invalidate
         def invalidate(self, context):
            print("Component invalidated, the service is gone")

Install and start the ``consumer`` bundle in the active Pelix shell and play
with the various commands described in the :ref:`previous section <quick_shell>`::

    $ install consumer
    Bundle ID: 13
    $ start 13
    Starting bundle 13 (consumer)...
    Component validated, calling the service...
    Hello, World !
    Done.
    $ update 12
    Updating bundle 12 (provider)...
    Component invalidated, the service is gone
    Component validated, calling the service...
    Hello, World !
    Done.
    $ uninstall 12
    Uninstalling bundle 12 (provider)...
    Component invalidated, the service is gone

Hello from somewhere!
=====================

This section reuses the bundles written in the *Hello World* sample, and install
them in two distinct frameworks.
To achieve that, we will use the *Pelix Remote Services*, a set of bundles
intending to share services across multiple Pelix frameworks.
A :ref:`reference card <refcard_remote_services>` provides more information
about this feature.

Core bundles
------------

First, we must install the core bundles of the *remote services* implementation:
the *Imports Registry* (``pelix.remote.registry``) and the
*Exports Dispatcher* (``pelix.remote.dispatcher``).
Both handle the description of the shared services, not their link with the
framework: it will be the job of discovery and transport providers.
The discovery provider we will use requires to access the content of the
*Exports Dispatcher* of the frameworks it finds, through HTTP requests.
A component, the *dispatcher servlet*, must therefore be instantiate to answer
to those requests::

    bash$ python -m pelix.shell
    ** Pelix Shell prompt **
    $ install pelix.remote.registry
    Bundle ID: 11
    $ start 11
    Starting bundle 11 (pelix.remote.registry)...
    $ install pelix.remote.dispatcher
    Bundle ID: 12
    $ start 12
    Starting bundle 12 (pelix.remote.dispatcher)...
    $ instantiate pelix-remote-dispatcher-servlet-factory dispatcher-servlet
    Component 'dispatcher-servlet' instantiated.

The protocols we will use for discovery and transport depends on an HTTP server.
As we are using two framework on the same machine, don't forget to use different
HTTP ports for each framework::

    $ install pelix.http.basic
    Bundle ID: 13
    $ start 13
    Starting bundle 13 (pelix.http.basic)...
    $ instantiate pelix.http.service.basic.factory httpd pelix.http.port=8000
    INFO:httpd:Starting HTTP server: [0.0.0.0]:8000 ...
    INFO:httpd:HTTP server started: [0.0.0.0]:8000
    Component 'httpd' instantiated.

The *dispatcher servlet* will be discovered by the newly started HTTP server
and will be able to answer to clients.

Discovery and Transport
-----------------------

Next, it is necessary to setup the remote service discovery layer. Here, we'll
use a Pelix-specific protocol based on UDP multicast packets.
By default, this protocol uses the UDP port 42000, which must therefore be
accessible on any machine providing or consuming a remote service.

Start two Pelix framework with their shell and, in each one, install the
``pelix.remote.discovery.multicast`` bundle then instantiate the discovery
component::


    $ install pelix.remote.discovery.multicast
    Bundle ID: 14
    $ start 14
    Starting bundle 14 (pelix.remote.discovery.multicast)...
    $ instantiate pelix-remote-discovery-multicast-factory discovery
    Component 'discovery' instantiated.

Finally, you will have to install the transport layer that will be used to send
requests and to wait for their responses.
Here, we'll use the JSON-RPC protocol (``pelix.remote.json_rpc``), which is the
easiest to use (*e.g.* XML-RPC has problems handling dictionaries of complex
types).
Transport providers often require to instantiate two components: one for the
export and one for the import.
This allows to instantiate the export part only, avoiding every single framework
to know about all available services.

    $ install pelix.remote.json_rpc
    Bundle ID: 15
    $ start 15
    Starting bundle 15 (pelix.remote.json_rpc)...
    $ instantiate pelix-jsonrpc-importer-factory importer
    Component 'importer' instantiated.
    $ instantiate pelix-jsonrpc-exporter-factory exporter
    Component 'exporter' instantiated.

Now, the frameworks you ran have all the necessary bundles and services to
detect and use the services of their peers.

Export a service
----------------

Exporting a service is as simple as providing it: just add the
``service.exported.interfaces`` property while registering it and will be
exported automatically.
To avoid typos, this property is defined in the
``pelix.remote.PROP_EXPORTED_INTERFACES`` constant.
This property can contain either a list of names of interfaces/contracts or a
star (``*``) to indicate that all services interfaces are exported.

Here is the new version of the *hello world* provider, with the export property:

.. code-block:: python

   from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate, \
        Property
   from pelix.remote import PROP_EXPORTED_INTERFACES

   @ComponentFactory("service-provider-factory")
   @Provides("hello.world")
   # Here is the new property, to authorize the export
   @Property('_export_itfs', PROP_EXPORTED_INTERFACES, '*')
   @Instantiate("provider")
   class Greetings(object):
         def hello(self, name="World"):
             print("Hello,", name, "!")

That's all!

Now you can install this provider in a framework, using::

    $ install provider
    Bundle ID: 16
    $ start 16
    Starting bundle 16 (provider)...

When installing a consumer in another framework, it will see the provider and
use it::

    $ install consumer
    Bundle ID: 16
    $ start 16
    Component validated, calling the service...
    Done.

You should then see the greeting message (*Hello, World !*) in the shell of the
provider that has been used by the consumer.
