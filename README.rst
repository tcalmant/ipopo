iPOPO: A service-oriented component model for Python
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

.. image:: https://coveralls.io/repos/tcalmant/ipopo/badge.svg?branch=master
     :target: https://coveralls.io/r/tcalmant/ipopo?branch=master
     :alt: Coveralls status

`iPOPO <https://ipopo.coderxpress.net/>`_ is a Python-based Service-Oriented
Component Model (SOCM) based on Pelix, a dynamic service platform.
They are inspired on two popular Java technologies for the development of
long-lived applications: the
`iPOJO <http://felix.apache.org/documentation/subprojects/apache-felix-ipojo.html>`_
component model and the `OSGi <http://osgi.org/>`_ Service Platform.
iPOPO enables to conceive long-running and modular IT services.

See https://ipopo.coderxpress.net for documentation and more information.


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


Concepts
########

**TODO:** Reuse https://ipopo.coderxpress.net/wiki/doku.php?id=ipopo:refcards:concepts

Samples
#######

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

When a required service is unregistered by its provider, the component instances
consuming it are invalidated.
When the method decorated by ``@Invalidate`` is called, the service is still
injected and should be usable (except for special cases, like remote services).

Batteries included
##################

**TODO:** list the services included in Pelix

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

Please note that your contributions will be released under the project's license,
which is the `Apache Software License 2.0 <http://www.apache.org/licenses/LICENSE-2.0>`_.

Compatibility
#############

Pelix and iPOPO are tested using `Tox <http://testrun.org/tox/latest/>`_ and
`Travis-CI <https://travis-ci.org/tcalmant/ipopo>`_ with Pypy 2.5.0 and
Python 2.7, 3.3, 3.4 and 3.5.

iPOPO doesn't support Python 2.6 anymore.

License
#######

iPOPO is released under the `Apache Software License 2.0 <http://www.apache.org/licenses/LICENSE-2.0>`_.


Release notes: 0.6.3
####################

See the CHANGELOG.rst file to see what changed in previous releases.
