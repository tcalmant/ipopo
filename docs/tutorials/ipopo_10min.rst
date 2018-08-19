.. iPOPO in 10 minutes

iPOPO in 10 minutes
###################

:Authors: Shadi Abras, Thomas Calmant

This tutorial presents how to use the iPOPO framework and its associated
service-oriented component model.
The concepts of the service-oriented component model are introduced, followed
by a simple example that demonstrates the features of iPOPO.
This framework uses decorators to describe components.

Introduction
============

iPOPO aims to simplify service-oriented programming on OSGi frameworks in
Python language; the name iPOPO is an abbreviation for *injected POPO*, where
*POPO* would stand for Plain Old Python Object.
The name is in fact a simple modification of the
`Apache iPOJO project <http://felix.apache.org/documentation/subprojects/apache-felix-ipojo.html>`_,
which stands for *injected Plain Old Java Object*

iPOPO provides a new way to develop OSGi/iPOJO-like service components in
Python, simplifying service component implementation by transparently managing
the dynamics of the environment as well as other non-functional requirements.
The iPOPO framework allows developers to more clearly separate functional code
(*i.e.* POPOs) from the non-functional code (*i.e.* dependency management,
service provision, configuration, etc.).
At run time, iPOPO combines the functional and non-functional aspects.
To achieve this, iPOPO provides a simple and extensible service component model
based on POPOs.

Basic concepts
==============

iPOPO is separated into two parts:

* Pelix, the underlying bundle and service registry
* iPOPO, the service-oriented component framework

It also defines three major concepts:

* A :ref:`bundle <refcard_bundles>` is a single Python module, *i.e.* a
  ``.py`` file, that is loaded using the Pelix API.
* A :ref:`service <refcard_services>` is a Python object that is registered to
  service registry using the Pelix API, associated to a set of specifications
  and to a dictionary of properties.
* A :ref:`component <refcard_component>` is an instance of *component factory*,
  *i.e.* a class manipulated by iPOPO decorators.
  Those decorators injects information into the class that are later used by
  iPOPO to manage the components.
  Components are defined inside bundles.


Simple example
==============

In this tutorial we will present how to:

* Publish a service
* Require a service
* Use lifecycle callbacks to activate and deactivate components


Presentation of the Spell application
-------------------------------------

To illustrate some of iPOPO features, we will implement a very simple
application. Three bundles compose this application:

* A bundle that defines a component implementing a dictionary service
  (an English and a French dictionaries).
* One with a component requiring the dictionary service and providing a spell
  checker service.
* One that defines a component requiring the spell checker and providing a user
  line interface.

.. image:: /_static/tutorials/spell_checker/spellchecker_arch.svg
   :align: center
   :alt: Service hierarchy
   :scale: 100%

The spell dictionary components provide the ``spell_dictionary_service``
specification.
The spell checker provides a ``spell_checker_service`` specification.


Preparing the tutorial
----------------------

The example contains several bundles:

* `spell_dictionary_EN.py <../_static/tutorials/spell_checker/spell_dictionary_EN.py>`_
  defines a component that implements the Dictionary service, containing some
  English words.
* `spell_dictionary_FR.py <../_static/tutorials/spell_checker/spell_dictionary_FR.py>`_
  defines a component that implements the Dictionary service, containing some
  French words.
* `spell_checker.py <../_static/tutorials/spell_checker/spell_checker.py>`_
  contains an implementation of a Spell Checker.
  The spell checker requires a dictionary service and checks if an input
  passage is correct, according to the words contained in the wished dictionary.
* `spell_client.py <../_static/tutorials/spell_checker/spell_client.py>`_ provides
  commands for the :ref:`Pelix shell service <quick_shell>`.
  This component uses a spell checker service. The user can interact with the
  spell checker with this command line interface.

Finally, a `main_pelix_launcher.py <../_static/tutorials/spell_checker/main_pelix_launcher.py>`_
script starts the Pelix framework.
It is not considered as a bundle as it is not loaded by the framework, but it
can control the latter.


The English dictionary bundle: Providing a service
--------------------------------------------------

The ``spell_dictionary_EN`` bundle is a simple implementation of the Dictionary
service. It contains few English words.

.. literalinclude:: /_static/tutorials/spell_checker/spell_dictionary_EN.py
   :language: python
   :linenos:

* The ``@Component`` decorator is used to declare an iPOPO component.
  It must always be on top of other decorators.
* The ``@Provides`` decorator indicates that the component provides a service.
* The ``@Instantiate`` decorator instructs iPOPO to automatically create an
  instance of our component. The relation between components and instances is
  the same than between classes and objects in the object-oriented programming.
* The ``@Property`` decorator indicates the properties associated to this
  component and to its services (*e.g.* French or English language).
* The method decorated with ``@Validate`` will be called when the instance
  becomes valid.
* The method decorated with ``@Invalidate`` will be called when the instance
  becomes invalid (*e.g.* when one its dependencies goes away) or is stopped.

For more information about decorators, see :ref:refcard_decorators.


The French dictionary bundle: Providing a service
-------------------------------------------------

The ``spell_dictionary_FR`` bundle is a similar to the ``spell_dictionary_EN``
one. It only differs in the ``language`` component property, as it checks some
French words declared during component validation.

.. literalinclude:: /_static/tutorials/spell_checker/spell_dictionary_FR.py
   :language: python
   :linenos:
   :emphasize-lines: 14,18,20,31-40

It is important to note that the iPOPO factory name must be unique in a
framework: only the first one to be registered with a given name will be taken
into account.
The name of component instances follows the same rule.


The spell checker bundle: Requiring a service
---------------------------------------------

The ``spell_checker`` bundle aims to provide a spell checker service.
However, to serve this service, this implementation requires a dictionary
service.
During this step, we will create an iPOPO component requiring a Dictionary
service and providing the Spell Checker service.

.. literalinclude:: /_static/tutorials/spell_checker/spell_checker.py
   :language: python
   :linenos:

* The ``@Requires`` decorator specifies a service dependency.
  This required service is injected in a local variable in this bundle.
  Its ``aggregate`` attribute tells iPOPO to collect the list of services
  providing the required specification, instead of the first one.
* The ``@BindField`` decorator indicates that a new required service bounded
  to the platform.
* The ``@UnbindField`` decorator indicates that one of required service has
  gone away.


The spell client bundle
-----------------------

The ``spell_client`` bundle contains a very simple user interface allowing a
user to interact with a spell checker service.

.. literalinclude:: /_static/tutorials/spell_checker/spell_client.py
   :language: python
   :linenos:

The component defined here implements and provides a shell command service,
which will be consumed by the Pelix Shell Core Service.
It registers a ``spell`` shell command.


Main script: Launching the framework
------------------------------------

We have all the bundles required to start playing with the application.
To run the example, we have to start Pelix, then all the required bundles.

.. literalinclude:: /_static/tutorials/spell_checker/main_pelix_launcher.py
   :language: python
   :linenos:


Running the application
-----------------------

Launch the ``main_pelix_launcher.py`` script.
When the framework is running, type in the console: **spell** to enter your
language choice and then your passage.

Here is a sample run, calling ``python main_pelix_launcher.py``:

.. code-block:: console

   INFO:pelix.shell.core:Shell services registered
   An English dictionary has been added
   ** Pelix Shell prompt **
   A French dictionary has been added
   A dictionary checker has been started
   1. Testing Spell Checker: Welcome to our framwork iPOPO
   >  Misspelled_words are: ['our', 'framwork']
   A client for spell checker has been started

   $ spell
   Please enter your language, EN or FR: FR
   Please enter your paragraph, or 'quit' to exit:
   Bonjour le monde !
   All words are well spelled !
   Please enter your paragraph, or 'quit' to exit:
   quit
   $ spell
   Please enter your language, EN or FR: EN
   Please enter your paragraph, or 'quit' to exit:
   Hello, world !
   All words are well spelled !
   Please enter your paragraph, or 'quit' to exit:
   Bonjour le monde !
   The misspelled words are: ['Bonjour', 'le', 'monde']
   Please enter your paragraph, or 'quit' to exit:
   quit
   $ quit
   Bye !
   A spell client has been stopped
   INFO:pelix.shell.core:Shell services unregistered

You can now go back to see other :ref:`Tutorials` or take a look at the
:ref:`refcards`.
