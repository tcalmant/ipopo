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

