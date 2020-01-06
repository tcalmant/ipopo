.. image:: https://ipopo.readthedocs.io/en/latest/_images/logo_texte_200.png
   :alt: iPOPO logo
   :width: 200px
   :align: center
   :target: https://ipopo.readthedocs.io/

iPOPO: A Service-Oriented Component Model for Python
####################################################

.. image:: https://badges.gitter.im/Join%20Chat.svg
   :alt: Join the chat at https://gitter.im/tcalmant/ipopo
   :target: https://gitter.im/tcalmant/ipopo?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge

.. image:: https://img.shields.io/pypi/v/ipopo.svg
   :target: https://pypi.python.org/pypi/ipopo/
   :alt: Latest Version

.. image:: https://img.shields.io/pypi/l/ipopo.svg
   :target: https://pypi.python.org/pypi/ipopo/
   :alt: License

.. image:: https://travis-ci.org/tcalmant/ipopo.svg?branch=master
   :target: https://travis-ci.org/tcalmant/ipopo
   :alt: Travis-CI status

.. image:: https://coveralls.io/repos/github/tcalmant/ipopo/badge.svg?branch=master
   :target: https://coveralls.io/github/tcalmant/ipopo?branch=master
   :alt: Coveralls status

`iPOPO <https://ipopo.readthedocs.io/>`_ is a Python-based Service-Oriented
Component Model (SOCM) based on Pelix, a dynamic service platform.
They are inspired on two popular Java technologies for the development of
long-lived applications: the
`iPOJO <http://felix.apache.org/documentation/subprojects/apache-felix-ipojo.html>`_
component model and the `OSGi <http://osgi.org/>`_ Service Platform.
iPOPO enables to conceive long-running and modular IT services.

See https://ipopo.readthedocs.io/ for documentation and more information.


Note on this version
====================

This is the 1.x branch of iPOPO, which is intended to work with both Python 2.7
and 3.x.

If you are working with Python 3.7+ and ``asyncio``, you should look at the 2.x
branch.

Usage survey
============

In order to gain insight from the iPOPO community, I've put a
`really short survey <https://docs.google.com/forms/d/1zx18_Rg27mjdGrlbtr9fWFmVnZNINo9XCfrYJbr4oJI>`_
on Google Forms (no login required).

Please, feel free to answer it, the more answers, the better.
All feedback is really appreciated.

.. contents::

Install
#######

Option 1: Using pip
===================

iPOPO is available on `PyPI <http://pypi.python.org/pypi/iPOPO>`_ and can be
installed using ``pip``:

.. code-block:: bash

    # Install system-wide
    $ sudo pip install iPOPO

    # ... or user-wide installation
    $ pip install --user iPOPO


Option 2: From source
=====================

.. code-block:: bash

    $ git clone https://github.com/tcalmant/ipopo.git
    $ cd ipopo
    $ python setup.py install


Check install
=============

To check if Pelix is installed correctly, run the following command:

.. code-block:: bash

    $ python -m pelix.shell --version
    Pelix 0.8.0 from /home/tcalmant/git/ipopo/pelix/framework.py

Concepts
########

Pelix brings the concept of *bundle* in Python.
A bundle is a module with a life cycle: it can be installed, started, stopped,
updated and *uninstalled*.

A bundle can declare a class acting as bundle activator, using the
``@BundleActivator`` decorator.
This class will be instantiated by the framework and its ``start()`` and
``stop()`` method will be called to notify the bundle about its activation and
deactivation.

When it is active, a bundle can register services.
A service is an object implementing a specification and associated to a set of
properties.
A component will then be able to select and consume a service according to the
specification(s) it provides and to its properties.

The components are a concept brought by iPOPO.
A component, or component instance, is an object managed by a container.
The container handles the interactions between the component and the Pelix
framework.
That way, the component contains only the code required for its task, not for
its bindings with the framework.
A component is an instance of a component factory, a class `manipulated <https://ipopo.readthedocs.io/en/latest/refcards/ipopo.html>`_
by iPOPO `decorators <https://ipopo.readthedocs.io/en/latest/refcards/ipopo_decorators.html>`_.

For more information, see the `concepts page <https://ipopo.readthedocs.io/en/latest/refcards/index.html>`_
on the wiki.


Sample
######

This sample gives a quick overview of the usage of iPOPO.
For more information, take a look at `iPOPO in 10 minutes <https://ipopo.readthedocs.io/en/latest/quickstart.html>`_.


Service provider
================

The following code defines a component factory (a class) which instances will
provide a ``sample.hello`` service.

.. code-block:: python

    # iPOPO decorators
    from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate

    # Manipulates the class and sets its (unique) factory name
    @ComponentFactory("hello-provider-factory")
    # Indicate that the components will provide a service
    @Provides("sample.hello")
    # Tell iPOPO to instantiate a component instance as soon as the file is loaded
    @Instantiate("hello-provider-auto")
    # A component class must always inherit from object (new-style class)
    class HelloProvider(object):
        """
        A sample service provider
        """
        def hello(self, name="world"):
            """
            Says hello
            """
            print("Hello,", name, "!")

        def bye(self, name="cruel world"):
            """
            Says bye
            """
            print("Bye,", name, "!")

When the bundle providing this component factory will be started, iPOPO will
automatically instantiate a component, due to the ``@Instantiate`` decorator.
It is also possible to instantiate a component using shell commands.

Each component instance will provide a ``sample.hello`` service, which can be
consumed by any bundle or any other component.


Service consumer
================

The following code defines a component factory (a class) which instances will
consume a ``sample.hello`` service. If multiple services are available, iPOPO
will select the one with the highest rank and the lowest service ID
(*i.e.* the oldest service).

.. code-block:: python

    # iPOPO decorators
    from pelix.ipopo.decorators import ComponentFactory, Requires, Instantiate, \
        Validate, Invalidate

    # Manipulates the class and sets its (unique) factory name
    @ComponentFactory("hello-consumer-factory")
    # Indicate that the components require a sample.hello service to work
    # and to inject the found service in the _svc field
    @Requires('_svc', "sample.hello")
    # Tell iPOPO to instantiate a component instance as soon as the file is loaded
    @Instantiate("hello-consumer-auto")
    # A component class must always inherit from object (new-style class)
    class HelloConsumer(object):
        """
        A sample service consumer
        """
        def __init__(self):
            """
            Defines (injected) members
            """
            self._svc = None

        @Validate
        def validate(self, context):
            """
            Component validated: all its requirements have been injected
            """
            self._svc.hello("Consumer")

        @Invalidate
        def invalidate(self, context):
            """
            Component invalidated: one of its requirements is going away
            """
            self._svc.bye("Consumer")

When the bundle providing this component factory will be started, iPOPO will
automatically instantiate a component, due to the ``@Instantiate`` decorator.

Each component instance will require a ``sample.hello`` service. Once iPOPO
has injected all the required services (here, a single ``sample.hello`` service)
in a component instance, this instance will be considered *valid* and iPOPO
will call its method decorated by ``@Validate``.
There, the component can consume its dependencies, start threads, etc..
It is recommended for this method to start threads and to return quickly, as it
blocks iPOPO and the Pelix framework.

When a required service is unregistered by its provider, the component
instances consuming it are invalidated.
When the method decorated by ``@Invalidate`` is called, the service is still
injected and should be usable (except for special cases, like remote services).


Run!
====

To run this sample, you'll need to copy the snippets above in different files:

* copy the *Service provider* snippet in a file called *provider.py*
* copy the *Service consumer* snippet in a file called *consumer.py*

Then, run a Pelix shell in the same folder as those files, and execute the
commands listed in this trace:

.. code-block:: bash

    $ python -m pelix.shell
    ** Pelix Shell prompt **
    $ # Install the bundles
    $ install provider
    Bundle ID: 11
    $ install consumer
    Bundle ID: 12
    $ # Start the bundles (the order isn't important here)
    $ start 11 12
    Starting bundle 11 (provider)...
    Starting bundle 12 (consumer)...
    Hello, Consumer !
    $ # View iPOPO instances
    $ instances
    +----------------------+------------------------------+-------+
    |         Name         |           Factory            | State |
    +======================+==============================+=======+
    | hello-consumer-auto  | hello-consumer-factory       | VALID |
    +----------------------+------------------------------+-------+
    | hello-provider-auto  | hello-provider-factory       | VALID |
    +----------------------+------------------------------+-------+
    | ipopo-shell-commands | ipopo-shell-commands-factory | VALID |
    +----------------------+------------------------------+-------+
    3 components running
    $ # View details about the consumer
    $ instance hello-consumer-auto
    Name.....: hello-consumer-auto
    Factory..: hello-consumer-factory
    Bundle ID: 12
    State....: VALID
    Services.:
    Dependencies:
            Field: _svc
                    Specification: sample.hello
                    Filter......: None
                    Optional.....: False
                    Aggregate....: False
                    Handler......: SimpleDependency
                    Bindings:
                            ServiceReference(ID=11, Bundle=11, Specs=['sample.hello'])
    Properties:
            +---------------+---------------------+
            |      Key      |        Value        |
            +===============+=====================+
            | instance.name | hello-consumer-auto |
            +---------------+---------------------+

    $ # Modify the provider file (e.g. change the 'Hello' string by 'Hi')
    $ # Update the provider bundle (ID: 11)
    $ update 11
    Updating bundle 11 (provider)...
    Bye, Consumer !
    Hi, Consumer !
    $ # Play with other commands (see help)

First, the ``install`` commands are used to install the bundle: they will be
imported but their activator won't be called. If this command fails, the bundle
is not installed and is not referenced by the framework.

If the installation succeeded, the bundle can be started: it's activator is
called (if any). Then, iPOPO detects the component factories provided by the
bundle and instantiates the components declared using the ``@Instantiate``
decorator.

The ``instances`` and ``instance`` commands can be use to print the state and
bindings of the components. Some other commands are very useful, like ``sl``
and ``sd`` to list the registered services and print their details. Use the
``help`` command to see which ones can be used.

The last part of the trace shows what happens when updating a bundle.
First, update the source code of the provider bundle, *e.g.* by changing the
string it prints in the ``hello()`` method.
Then, tell the framework to update the bundle using the ``update`` command.
This command requires a bundle ID, which has been given as a result of the
``install`` command and can be found using ``bl``.

When updating a bundle, the framework stops it and reloads it (using
`imp.reload <https://docs.python.org/3/library/imp.html#imp.reload>`_).
If the update fails, the old version is kept.
If the bundle was active before the update, it is restarted by the framework.

Stopping a bundle causes iPOPO to kill the component instance(s) of the
factories it provided.
Therefore, no one provides the ``sample.hello`` service, which causes the
consumer component to be invalidated.
When the provider bundle is restarted, a new provider component is instantiated
and its service is injected in the consumer, which becomes valid again.


Batteries included
##################

Pelix/iPOPO comes with some useful services:

* Pelix Shell: a simple shell to control the framework (manage bundles,
  show the state of components, ...).
  The shell is split in 5 parts:

  * the parser: a shell interpreter class, which can be reused to create other
    shells (with a basic support of variables);
  * the shell core service: callable from any bundle, it executes the given
    command lines;
  * the UIs: text UI (console) and remote shell (TCP/TLS, XMPP)
  * the commands providers: iPOPO commands, report, EventAdmin, ...
  * the completion providers: Pelix, iPOPO

  See the `shell tutorial <http://ipopo.readthedocs.io/en/latest/quickstart.html#play-with-the-shell>`_
  for more information.

* An HTTP service, based on the HTTP server from the standard library.
  It provides the concept of *servlet*, borrowed from Java.

  See the `HTTP service reference <http://ipopo.readthedocs.io/en/latest/refcards/http.html>`_
  for more information.

  There is also a `routing utility class <http://ipopo.readthedocs.io/en/latest/refcards/http_routing.html>`_,
  based on decorators, which eases the development of REST-like servlets.

* Remote Services: export and import services to/from other Pelix framework or
  event Java OSGi frameworks!

  See the `remote services reference <http://ipopo.readthedocs.io/en/latest/refcards/remote_services.html>`_
  for more information.

Pelix also provides an implementation of the `EventAdmin service <http://ipopo.readthedocs.io/en/latest/refcards/eventadmin.html>`_,
inspired from the `OSGi specification <http://www.osgi.org/Specifications/HomePage>`_.

Feedback
########

Feel free to send feedback on your experience of Pelix/iPOPO, via the mailing
lists:

* User list:        http://groups.google.com/group/ipopo-users
* Development list: http://groups.google.com/group/ipopo-dev

Bugs and features requests can be submitted using the `Issue Tracker <https://github.com/tcalmant/ipopo/issues>`_
on GitHub.


Contributing
############

All contributions are welcome!

#. Create an `issue <https://github.com/tcalmant/ipopo/issues>`_ to discuss
   about your idea or the problem you encounter
#. `Fork <https://github.com/tcalmant/ipopo/fork>`_ the project
#. Develop your changes
#. Check your code with `pylint <https://pypi.python.org/pypi/pylint/>`_
   and `pep8 <https://pypi.python.org/pypi/pep8>`_
#. If necessary, write some unit tests
#. Commit your changes, indicating in each commit a reference to the issue
   you're working on
#. Push the commits on your repository
#. Create a *Pull Request*
#. Enjoy!

Please note that your contributions will be released under the project's
license, which is the `Apache Software License 2.0 <http://www.apache.org/licenses/LICENSE-2.0>`__.


Compatibility
#############

Pelix and iPOPO are tested using
`Travis-CI <https://travis-ci.org/tcalmant/ipopo>`_ with Python 2.7
and 3.4 to 3.6.
Pypy is not tested anymore due to various bugs during tests setup.

iPOPO doesn't support Python 2.6 anymore (since version 0.5.6).


License
#######

iPOPO is released under the `Apache Software License 2.0 <http://www.apache.org/licenses/LICENSE-2.0>`__.
