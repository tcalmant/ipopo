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

Common script arguments
-----------------------

Before looking at the available user interfaces, note that all of them support
arguments to handle the Initial Configuration files
(see :ref:`refcard_init_config`).

In addition to their specific arguments, the scripts starting the user
interfaces also accept the following ones:

====================================== =========================================
Argument                               Description
====================================== =========================================
``-h``, ``--help``                     Prints the script usage
``--version``                          Prints the script version
``-D KEY=VALUE``                       Sets up a framework property
``-v``, ``--verbose``                  Sets the logger to DEBUG mode
``--init FILE``                        Start by running a Pelix shell script
``--run FILE``                         Run a Pelix shell script then exit
``-c FILE``, ``--conf FILE``           Use a configuration file, above the system configuration
``-C FILE``, ``--exclusive-conf FILE`` Use a configuration file, ignore the system configuration
``-e``, ``--empty-conf``               Don't use any initial configuration
====================================== =========================================

Text UI
-------

The Text UI is the easiest way to manage or test your programs with Pelix/iPOPO.
It provides the most basic yet complete interaction with the Pelix Shell core
service.

If it is available, the Text UI relies on ``readline`` to provide command
and arguments completion.

Script startup
^^^^^^^^^^^^^^

The text (or console) UI can be started using the ``python -m pelix.shell``
command.
This command will start a Pelix framework, with iPOPO and the most commonly
used shell command providers.

This script only accepts the common shell parameters.

Programmatic startup
^^^^^^^^^^^^^^^^^^^^

This UI is provided by the ``pelix.shell.console`` bundle.
It is a raw bundle, which does not provide a component factory: the UI is
available while the bundle is active.
There is no configuration available when starting the Text UI programmatically.

Remote Shell
------------

Pelix frameworks are often started on remote locations, but still need to be
managed with the Pelix shell.
Instead of using an SSH connection to work on a foreground server, you can use
the Pelix Remote Shell.

The Pelix Remote Shell is a simple interface to the Pelix Shell core service
of its framework instance, based on a TCP server.
Unlike the console UI, multiple users can connect the framework at the same
time, each with his own shell session (variables, ...).

By default, the remote shell starts a TCP server listening the local interface
(*localhost*) on port 9000.
It is possible to enforce the server by setting up OpenSSL certificates.
The server will have its own certificate, which should be checked by the
clients, and each client will have to connect with its own certificate, signed
by an authority recognized by the server.
See :ref:`certificates_setup` for more information on how to setup this kind
of certificates.

.. note::
    TLS features and arguments are available only if the Python interpreters
    fully provides the ``ssl`` module, *i.e.* if it has been built with OpenSSL.

Script startup
^^^^^^^^^^^^^^

The remote shell UI can be started using the ``python -m pelix.shell.remote``
command.
This command will start a Pelix framework with iPOPO, and will start a Python
console locally.

In addition to the common parameters, the script accepts the following ones:

=============================== ========= ======================================
Argument                        Default   Description
=============================== ========= ======================================
``--no-input``                  *not set* If set, don't start the Python console (useful for server/daemon mode)
``-a ADDR``, ``--address ADDR`` localhost Server binding address
``-p PORT``, ``--port PORT``    9000      Server binding port
``--ca-chain FILE``             ``None``  Path to the certificate authority chain file (to authenticate clients)
``--cert FILE``                 ``None``  Path to the server certificate file
``--key FILE``                  ``None``  Path to the server private key file
``--key-password PASSWORD``     ``None``  Password of the server private key
=============================== ========= ======================================

Programmatic startup
^^^^^^^^^^^^^^^^^^^^

The remote shell is provided as the ``ipopo-remote-shell-factory`` component
factory defined in the ``pelix.shell.remote`` bundle.
You should use the constant ``pelix.shell.FACTORY_REMOTE_SHELL`` instead of the
factory name when instantiating the component.

This factory accepts the following properties:

================================ ========= =====================================
Name                             Default   Description
================================ ========= =====================================
``pelix.shell.address``          localhost Server binding address
``pelix.shell.port``             9000      Server binding port
``pelix.shell.ssl.ca``           ``None``  Path to the clients certificate authority chain file
``pelix.shell.ssl.cert``         ``None``  Path to the server's SSL certificate file
``pelix.shell.ssl.key``          ``None``  Path to the server's private key
``pelix.shell.ssl.key_password`` ``None``  Password of the server's private key
================================ ========= =====================================


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

Script startup
^^^^^^^^^^^^^^

The XMPP UI can be started using the ``python -m pelix.shell.xmpp`` command.
This command will start a Pelix framework with iPOPO, and will start a Pelix
console UI locally.

In addition to the common parameters, the script accepts the following ones:

============================== ========= =======================================
Argument                       Default   Description
============================== ========= =======================================
``-j JID``, ``--jid JID``      ``None``  Jabber ID (user account)
``--password PASSWORD``        ``None``  Account password
``-s ADDR``, ``--server ADDR`` ``None``  Address of the XMPP server (found in the Jabber ID by default)
``-p PORT``, ``--port PORT``   5222      Port of the XMPP server
``--tls``                      *not set* If set, use a STARTTLS connection
``--ssl``                      *not set* If set, use an SSL connection
============================== ========= =======================================

Programmatic startup
^^^^^^^^^^^^^^^^^^^^

This UI depends on the ``sleekxmpp`` third-party package, which can be installed
using the following command::

    pip install sleekxmpp

The XMPP shell is provided as the ``ipopo-xmpp-shell-factory`` component
factory defined in the ``pelix.shell.xmpp`` bundle.
You should use the constant ``pelix.shell.FACTORY_XMPP_SHELL`` instead of the
factory name when instantiating the component.

This factory accepts the following properties:

======================== ========= =========================
Name                     Default   Description
======================== ========= =========================
``shell.xmpp.server``    localhost XMPP server hostname
``shell.xmpp.port``      5222      XMPP server port
``shell.xmpp.jid``       ``None``  JID (XMPP account) to use
``shell.xmpp.password``  ``None``  User password
``shell.xmpp.tls``       1         Use a STARTTLS connection
``shell.xmpp.ssl``       0         Use an SSL connection
======================== ========= =========================


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

.. _certificates_setup:

How to prepare certificates for the Remote Shell
================================================

In order to use certificate-based client authentication with the Remote Shell
in TLS mode, you will have to prepare a certificate authority, which will be
used to sign server and clients certificates.

The following commands are a summary of
`OpenSSL Certificate Authority <https://jamielinux.com/docs/openssl-certificate-authority/index.html>`_
page by `Jamie Nguyen <https://jamielinux.com/>`_.

Prepare the root certificate
----------------------------

* Prepare the environment of the root certificate:

  .. code-block:: bash

    mkdir ca
    cd ca/
    mkdir certs crl newcerts private
    chmod 700 private/
    touch index.txt
    echo 1000 > serial

* Download the sample `openssl.cnf <https://jamielinux.com/docs/openssl-certificate-authority/appendix/root-configuration-file.html>`_
  file to the ``ca/`` directory and edit it to fit your needs.

* Create the root certificate. The following snippet creates a 4096 bits
  private key and creates a certificate valid for 7300 days (20 years).
  The ``v3_ca`` extension allows to use the certificate as an authority.

  .. code-block:: bash

    openssl genrsa -aes256 -out private/ca.key.pem 4096
    chmod 400 private/ca.key.pem

    openssl req -config openssl.cnf -key private/ca.key.pem \
        -new -x509 -days 7300 -sha256 -extensions v3_ca \
        -out certs/ca.cert.pem
    chmod 444 certs/ca.cert.pem

    openssl x509 -noout -text -in certs/ca.cert.pem

Prepare an intermediate certificate
-----------------------------------

Using intermediate certificates allows to hide the root certificate private
key from the network: once the intermediate certificate has signed, the root
certificate private key should be hidden in a server somewhere not accessible
from the outside.
If your intermediate certificate is compromised, you can use the root
certificate to revoke it.

* Prepare the environment of the intermediate certificate:

  .. code-block:: bash

    mkdir intermediate
    cd intermediate/
    mkdir certs crl csr newcerts private
    chmod 700 private/
    touch index.txt
    echo 1000 > serial
    echo 1000 > crlnumber

* Download the sample `intermediate/openssl.cnf <https://jamielinux.com/docs/openssl-certificate-authority/appendix/intermediate-configuration-file.html>`_
  file to the ``ca/intermediate`` folder and edit it to your needs.

* Generate the intermediate certificate and sign it with the root certificate.
  The ``v3_intermediate_ca`` extension allows to use the certificate as an
  intermediate authority.
  Intermediate certificates are valid less time than the root certificate.
  Here we consider a validity of 10 years.

  .. code-block:: bash

    openssl genrsa -aes256 -out intermediate/private/intermediate.key.pem 4096
    chmod 400 intermediate/private/intermediate.key.pem

    openssl req -config intermediate/openssl.cnf \
        -new -sha256 -key intermediate/private/intermediate.key.pem \
        -out intermediate/csr/intermediate.csr.pem

    openssl ca -config openssl.cnf -extensions v3_intermediate_ca \
        -days 3650 -notext -md sha256 \
        -in intermediate/csr/intermediate.csr.pem \
        -out intermediate/certs/intermediate.cert.pem
    chmod 444 intermediate/certs/intermediate.cert.pem

    openssl x509 -noout -text -in intermediate/certs/intermediate.cert.pem

    openssl verify -CAfile certs/ca.cert.pem \
        intermediate/certs/intermediate.cert.pem

* Generate the Certificate Authority chain file. This is simply the bottom
  list of certificates of your authority:

  .. code-block:: bash

    cat intermediate/certs/intermediate.cert.pem certs/ca.cert.pem \
        > intermediate/certs/ca-chain.cert.pem

    chmod 444 intermediate/certs/ca-chain.cert.pem

Prepare the server certificate
------------------------------

The steps to generate the certificate is simple. For simplicity, we consider
we are in the same folder hierarchy as before.

This certificate must has a validity period shorter than the intermediate
certificate.

#. Generate a server private key. This can be done on any machine:

   .. code-block:: bash

      openssl genrsa -aes256 -out intermediate/private/server.key.pem 2048
      openssl genrsa -out intermediate/private/server.key.pem 2048
      chmod 400 intermediate/private/server.key.pem

#. Prepare a certificate signing request

   .. code-block:: bash

      openssl req -config intermediate/openssl.cnf \
          -key intermediate/private/server.key.pem -new -sha256 \
          -out intermediate/csr/server.csr.pem

#. Sign the certificate with the intermediate certificate. The ``server_cert``
   extension indicates a server certificate which can't sign other ones.

   .. code-block:: bash

      openssl ca -config intermediate/openssl.cnf -extensions server_cert \
          -days 375 -notext -md sha256 \
          -in intermediate/csr/server.csr.pem \
          -out intermediate/certs/server.cert.pem
      chmod 444 intermediate/certs/server.cert.pem

      openssl x509 -noout -text -in intermediate/certs/server.cert.pem

      openssl verify -CAfile intermediate/certs/ca-chain.cert.pem \
          intermediate/certs/server.cert.pem

Prepare a client certificate
----------------------------

The steps to generate the client certificates are the same as for the server.

#. Generate a client private key. This can be done on any machine:

   .. code-block:: bash

      openssl genrsa -out intermediate/private/client1.key.pem 2048
      chmod 400 intermediate/private/client1.key.pem

#. Prepare a certificate signing request

   .. code-block:: bash

      openssl req -config intermediate/openssl.cnf \
          -key intermediate/private/client1.key.pem -new -sha256 \
          -out intermediate/csr/client1.csr.pem

#. Sign the certificate with the intermediate certificate. The ``usr_cert``
   extension indicates this is a client certificate, which cannot be used to
   sign other certificates.

   .. code-block:: bash

      openssl ca -config intermediate/openssl.cnf -extensions usr_cert \
          -days 375 -notext -md sha256 \
          -in intermediate/csr/client1.csr.pem \
          -out intermediate/certs/client1.cert.pem
      chmod 444 intermediate/certs/client1.cert.pem

      openssl x509 -noout -text -in intermediate/certs/client1.cert.pem

      openssl verify -CAfile intermediate/certs/ca-chain.cert.pem \
          intermediate/certs/client1.cert.pem


Connect a TLS Remote Shell
==========================

To connect a basic remote shell, you can use ``netcat``, which is available
for nearly all operating systems and all architectures.

To connect a TLS remote shell, you should use the OpenSSL client: ``s_client``.
It is necessary to indicate the client certificate in order to be accepted by
the server.
It is also recommended to indicate the authority chain to ensure that the
server is not a rogue one.

Here is a sample command line to connect a TLS remote shell on the local host,
listening on port 9001.

.. code-block:: bash

    openssl s_client -connect localhost:9001 \
        -cert client1.cert.pem -key client1.key.pem \
        -CAfile ca-chain.cert.pem
