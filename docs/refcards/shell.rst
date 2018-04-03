.. _refcard_shell:

.. note:: Work in progress

Pelix Shell
###########

Most of the time, it is necessary to access a Pelix application locally or
remotely in order to monitor it, to update its components or simply to check
its sanity.
The easiest to do those tasks is to use the Pelix Shell: it provides an
extensible set of commands that allows to work on bundles, iPOPO components, ...

The shell is split into two parts:

* the core shell, handling and executing commands
* the UI, which handles input/output operations with the user

Pelix comes with some bundles providing shell commands for various actions,
and a few UI implementations.
Feel free to implement and, maybe, publish new commands UIs according to your
needs.

In order to use the shell, the ``pelix.shell.core`` bundle must be installed
and running.
It doesn't require iPOPO and can therefore be used in minimalist applications.


Provided user interfaces
========================

Pelix includes 3 main user interfaces:

* Text UI: the one to use when running a basic Pelix application
* Remote Shell: useful when managing an application running on a server
* XMPP Shell: useful to access applications behind firewalls

.. note:: Add a note about the common arguments and a link to :ref:`init_config`_

Text UI
-------

The text (or console) UI can be started using the ``python -m pelix.shell``
command.
This command will start a Pelix framework with iPOPO.

If it is available, the Text UI relies on ``readline`` to provide command
and arguments completion.

This UI is provided by the ``pelix.shell.console`` bundle.

Remote Shell
------------

The remote shell UI can be started using the ``python -m pelix.shell.remote``
command.
This command will start a Pelix framework with iPOPO, and will start a Python
console locally.

This UI is provided by the ``pelix.shell.remote`` bundle.

XMPP Shell
----------

The XMPP shell interface allows to communicate with a Pelix framework using an
XMPP client, e.g. `Pidgin <http://pidgin.im/>`_, `Psi <https://psi-im.org/>`_.
The biggest advantages of this interface are the possibility to use TLS to
encrypt conversations and the fact that it is an output-only communication.
This allows to protect Pelix applications behind hardened firewalls, letting
them only to connect the XMPP server.

It requires an XMPP account to connect an XMPP server.
Early tests of this bundle were made against Google Talk (with a GMail account,
not to be confused with Google Hangout) and a private
`OpenFire <http://www.igniterealtime.org/projects/openfire/>`_ server.

The XMPP UI can be started using the ``python -m pelix.shell.xmpp`` command.
This command will start a Pelix framework with iPOPO, and will start a Pelix
console UI locally.

This UI is provided by the ``pelix.shell.xmpp`` bundle.
It depends on the ``sleekxmpp`` package.


Provided command bundles
========================

.. note:: TODO:

    * ``pelix.shell.ipopo``: Commands for iPOPO (factories and instances)
    * ``pelix.shell.configadmin``: Commands for the Configuration Admin service
      (provided by ``pelix.misc.configadmin``)
    * ``pelix.shell.eventadmin``: Commands for the Event Admin service
      (provided by ``pelix.misc.eventadmin``)
    * ``pelix.shell.log``: Commands for the Log Service (``pelix.misc.log``)
    * ``pelix.shell.report``: Provides commands to generate reports about the
      current setup of Pelix and of its host.

How to provide commands
=======================

.. note:: TODO

    * Provide a ``pelix.shell.SERVICE_SHELL_COMMAND`` service

        * ``get_namespace()``
        * ``get_methods()``

    * Use the ``pelix.shell.SERVICE_SHELL_UTILS`` service (tables, ...)
    * Provide completion hints for the Text UI


How to provide a new shell interface
====================================

.. note:: TODO

    * Implement an ``IOHandler``
    * Create a ``ShellSession``
