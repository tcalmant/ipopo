.. Shell Service tutorial

Shell Service tutorial
######################

Description
***********

In order to interact with the Pelix framework and its components, the shell
service allows to register a set of commands that will be used by shell
interfaces.

Pelix/iPOPO distribution comes with three bundles:

+--------------------+--------------------------------------------------------+
| Bundle             | Description                                            |
+====================+========================================================+
| pelix.shell.core   | Provides the core shell service, the commands registry |
|                    | and the basic Pelix commands                           |
+--------------------+--------------------------------------------------------+
| pelix.shell.ipopo  | Provides iPOPO shell commands                          |
+--------------------+--------------------------------------------------------+
| pelix.shell.remote | Provides a raw-TCP access to the shell                 |
+--------------------+--------------------------------------------------------+


Usage
*****

Instantiation
=============

The Pelix core shell service and the iPOPO shell commands are available as
soon as their respective bundle is started.

.. code-block:: python
   :linenos:
   
   from pelix.framework import FrameworkFactory
   
   # Start the framework
   framework = FrameworkFactory.get_framework()
   framework.start()
   context = framework.get_bundle_context()
   
   # Install iPOPO
   bid = context.install_bundle('pelix.ipopo.core')
   context.get_bundle(bid).start()
   
   # Install the Pelix core shell
   bid = context.install_bundle('pelix.shell.core')
   context.get_bundle(bid).start()
   
   # Install the iPOPO commands
   bid = context.install_bundle('pelix.shell.ipopo')
   context.get_bundle(bid).start()


The remote shell must be instantiated using iPOPO, using the
``ipopo-remote-shell-factory`` factory:

.. code-block:: python
   :linenos:

   # Get the iPOPO service
   from pelix.ipopo.constants import get_ipopo_svc_ref
   ipopo = get_ipopo_svc_ref(context)[1]
   
   # Install the remote shell bundle
   bid = context.install_bundle('pelix.shell.remote')
   context.get_bundle(bid).start()
   
   # Instantiate a remote shell
   ipopo.instantiate('ipopo-remote-shell-factory', 'ipopo-remote-shell')


By default, the remote shell listens on port 9000, you can access it using
softwares like *telnet* or *netcat*.


Configuration
=============

The core shell service and the iPOPO commands component are not configurable.

The remote shell component can be configured using the following properties:

+---------------+---------------+-----------------------------------------+
| Property      | Default value | Description                             |
+===============+===============+=========================================+
| shell.address | localhost     | Address the server will be bound to     |
+---------------+---------------+-----------------------------------------+
| shell.port    | 9000          | TCP port that the server will listen to |
+---------------+---------------+-----------------------------------------+


Interface
=========

Core shell service
------------------

The core shell service provides the following interface:

+---------------------------------+--------------------------------------------+
| Method                          | Description                                |
+=================================+============================================+
| register_command(namespace,     | Associates the given method to the given   |
| command, method)                | name in the given name space               |
+---------------------------------+--------------------------------------------+
| unregister(namespace, command)  | Unregister the given command from the      |
|                                 | given name space, or the whole name space  |
|                                 | if command is None                         |
+---------------------------------+--------------------------------------------+
| execute(cmdline, stdin, stdout) | Parses and executes the given command line |
|                                 | with given input and output streams        |
+---------------------------------+--------------------------------------------+
| get_banner()                    | Retrieves the welcome banner for the shell |
+---------------------------------+--------------------------------------------+
| get_ps1()                       | Retrieves the prompt string                |
+---------------------------------+--------------------------------------------+


Utility shell service
---------------------

The utility shell service can be used to ease commands implementations.
It provides the following methods:

+----------------------------+----------------------------------------------+
| Method                     | Description                                  |
+============================+==============================================+
| bundlestate_to_str(state)  | Retrieves the string representation of the   |
|                            | state of a bundle                            |
+----------------------------+----------------------------------------------+
| make_table(headers, lines) | Generates an ASCII table using the given     |
|                            | column headers (N-tuple) and the given lines |
|                            | (array of N-tuples)                          |
+----------------------------+----------------------------------------------+


Command method
--------------

A command method must accept *stdin* and *stdout* as its first parameters and
must use them to interact with the client.
The remote shell is based on this behavior, given the client socket as the
input and output of the commands to execute.

Also, a command method should have a documentation, that will be used as its
help message.

Here is the implementation of the *start* method, which starts a bundle with
the given ID:

.. code-block:: python
   :linenos:
   
   def start(self, stdin, stdout, bundle_id):
        """
        start <bundle_id> - Starts the given bundle ID
        """
        bundle_id = int(bundle_id)
        bundle = self._context.get_bundle(bundle_id)
        if bundle is None:
            stdout.write("Unknown bundle: %d\n", bundle_id)

        bundle.start()


Command service
---------------

The core shell service automatically registers all services providing the
``pelix.shell.command`` specification.

Those services must implement the following methods:

+---------------------+-----------------------------------------------------+
| Method              | Description                                         |
+=====================+=====================================================+
| get_namespace()     | Retrieves the name space of the provided commands   |
+---------------------+-----------------------------------------------------+
| get_methods()       | Retrieves the list of (command, method) tuples      |
+---------------------+-----------------------------------------------------+
| get_methods_names() | Retrieves the list of (command, method name) tuples |
+---------------------+-----------------------------------------------------+

The ``get_methods_names()`` method is there to prepare remote services tests,
and will allow to execute commands from a distant framework.


Commands
********

Core
====

These commands are in the name space ``default``, they can be called without
specifying it.

+-------------------+-----------------------------------------+
| Command           | Description                             |
+===================+=========================================+
| help, ?           | Prints the registered shell commands    |
+-------------------+-----------------------------------------+
| quit, exit, close | Exits the shell sessions                |
+-------------------+-----------------------------------------+
| bd <ID>           | Prints the details of the given bundle  |
+-------------------+-----------------------------------------+
| bl                | Prints the list of installed bundles    |
+-------------------+-----------------------------------------+
| sd <ID>           | Prints the details of the given service |
+-------------------+-----------------------------------------+
| sl                | Prints the list of registered services  |
+-------------------+-----------------------------------------+
| start <ID>        | Starts the bundle with the given ID     |
+-------------------+-----------------------------------------+
| stop <ID>         | Stops the bundle with the given ID      |
+-------------------+-----------------------------------------+
| update <ID>       | Updates the bundle with the given ID    |
+-------------------+-----------------------------------------+
| install <name>    | Installs the bundle with the given name |
+-------------------+-----------------------------------------+
| uninstall <ID>    | Uninstalls the bundle with the given ID |
+-------------------+-----------------------------------------+


iPOPO
=====

These commands are in the name space ``ipopo``.

+------------------------------+--------------------------------------------+
| Command                      | Description                                |
+==============================+============================================+
| factories                    | Prints the registered factories            |
+------------------------------+--------------------------------------------+
| instances                    | Prints the instantiated components         |
+------------------------------+--------------------------------------------+
| instance <name>              | Prints the details of the given component  |
|                              | instance                                   |
+------------------------------+--------------------------------------------+
| instantiate <factory> <name> | Instantiate the component of the given     |
| [<property=value> [...]]     | factory with the given name and properties |
+------------------------------+--------------------------------------------+
| kill <name>                  | Kills the component of the given name      |
+------------------------------+--------------------------------------------+


Sample
======

Here is a sample usage of the remote shell, using *netcat* (*nc*) for the
connection and *rlwrap* to allow line modifications:

.. code-block:: none
   :linenos:
   
   
   $ rlwrap nc localhost 9000
   ------------------------------------------------------------------------
   ** Pelix Shell prompt **
   iPOPO Remote Shell
   ------------------------------------------------------------------------
   $ bl
   +----+--------------------+--------+-----------+
   | ID |        Name        | State  |  Version  |
   +====+====================+========+===========+
   | 0  | org.psem2m.pelix   | ACTIVE | (0, 4, 0) |
   +----+--------------------+--------+-----------+
   | 1  | pelix.ipopo.core   | ACTIVE | (0, 4, 0) |
   +----+--------------------+--------+-----------+
   | 2  | pelix.shell.core   | ACTIVE | (0, 1, 0) |
   +----+--------------------+--------+-----------+
   | 3  | pelix.shell.ipopo  | ACTIVE | (0, 1, 0) |
   +----+--------------------+--------+-----------+
   | 4  | pelix.shell.remote | ACTIVE | (0, 1, 0) |
   +----+--------------------+--------+-----------+
   $ sl
   +----+---------------------------+--------------------------------------+---------+
   | ID |      Specifications       |                Bundle                | Ranking |
   +====+===========================+======================================+=========+
   | 1  | ['pelix.ipopo.core']      | Bundle(ID=1, Name=pelix.ipopo.core)  | None    |
   +----+---------------------------+--------------------------------------+---------+
   | 2  | ['pelix.shell']           | Bundle(ID=2, Name=pelix.shell.core)  | None    |
   +----+---------------------------+--------------------------------------+---------+
   | 3  | ['pelix.shell.utilities'] | Bundle(ID=2, Name=pelix.shell.core)  | None    |
   +----+---------------------------+--------------------------------------+---------+
   | 4  | ['ipopo.shell.command']   | Bundle(ID=3, Name=pelix.shell.ipopo) | None    |
   +----+---------------------------+--------------------------------------+---------+
   $ ipopo:instances
   +----------------------+------------------------------+------------+
   |         Name         |           Factory            |   State    |
   +======================+==============================+============+
   | ipopo-remote-shell   | ipopo-remote-shell-factory   | VALIDATING |
   +----------------------+------------------------------+------------+
   | ipopo-shell-commands | ipopo-shell-commands-factory | VALID      |
   +----------------------+------------------------------+------------+
   $ 


How to write a command provider
*******************************

This snippet shows how to write a component providing the command service:

.. code-block:: python
   :linenos:
   
   from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate
   
   @ComponentFactory(name='simple-command-factory')
   @Instantiate('simple-command')
   @Provides(specifications='pelix.shell.command')
   class SimpleServletFactory(object):
       """
       Simple command factory
       """
       def __init__(self):
           """
           Set up the component
           """
           self.counter = 0
       
       def get_namespace(self):
           """
           Retrieves the commands name space
           """
           return "counter"
       
       def get_methods(self):
           """
           Retrieves the commands - methods association
           """
           return [("more", self.increment),
                   ("less", self.decrement),
                   ("print", self.print)]
       
       def get_methods_names(self):
           """
           Retrieves the list of tuples (command, method name) for this command
           handler.
           """
           result = []
           for command, method in self.get_methods():
               result.append((command, method.__name__))

           return result

           
       def increment(self, stdin, stdout, value=1):
           """
           Increments the counter of [value]
           """
           self.counter += value
       
       
       def decrement(self, stdin, stdout, value=2):
           """
           Decrements the counter of [value]
           """
           self.counter -= value
       
       
       def print(self, stdin, stdout):
           """
           Prints the value of the counter
           """
           stdout.write('Counter = {0}'.format(self.counter))


Now you can install this bundle and use the commands *counter:more*,
*counter:less* and *counter:print*.
