.. _quickstart:

Quickstart
##########

Eager to get started? This page gives a good introduction to iPOPO.
It assumes you already have iPOPO installed. If you do not, head over
to the :ref:`installation` section.

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

Hello from somewhere!
=====================
