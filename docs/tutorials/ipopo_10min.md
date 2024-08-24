# iPOPO in 10 minutes

:::{admonition} Authors
Shadi Abras, Thomas Calmant
:::

This tutorial presents how to use the iPOPO framework and its associated
service-oriented component model. The concepts of the service-oriented
component model are introduced, followed by a simple example that
demonstrates the features of iPOPO. This framework uses decorators to
describe components.

:::{note}
This tutorial has been updated to use types instead of named specifications.
:::

## Introduction

iPOPO aims to simplify service-oriented programming on OSGi frameworks
in Python language; the name iPOPO is an abbreviation for *injected POPO*,
where *POPO* would stand for Plain Old Python Object.
The name is in fact a simple modification of the
[Apache iPOJO project](https://web.archive.org/web/20210616112915/http://felix.apache.org/documentation/subprojects/apache-felix-ipojo.html),
which stands for *injected Plain Old Java Object*

iPOPO provides a new way to develop OSGi/iPOJO-like service components
in Python, simplifying service component implementation by transparently
managing the dynamics of the environment as well as other non-functional
requirements. The iPOPO framework allows developers to more clearly
separate functional code (*i.e.* POPOs) from the non-functional code
(*i.e.* dependency management, service provision, configuration, etc.).
At run time, iPOPO combines the functional and non-functional aspects.
To achieve this, iPOPO provides a simple and extensible service
component model based on POPOs.

Since iPOPO v3, we recommend using types as much as possible to avoid issues
when developping large softwares with the framework.

## Basic concepts

iPOPO is separated into two parts:

* Pelix, the underlying bundle and service registry
* iPOPO, the service-oriented component framework

It also defines three major concepts:

* A [bundle](../refcards/bundles.rst) is a single Python module, *i.e.*
  a `.py` file, that is loaded using the Pelix API.
* A [service](../refcards/services.rst) is a Python object that is registered
  to the service registry using the Pelix API, associated to a set of
  specifications and to a dictionary of properties.
* A [component](../refcards/ipopo.rst) is an instance of *component factory*,
  *i.e.* a class manipulated by iPOPO decorators.
  Those decorators injects information into the class that are later used by
  iPOPO to manage the components. Components are defined inside bundles.

## Simple example

In this tutorial we will present how to:

* Publish a service
* Require a service
* Use lifecycle callbacks to activate and deactivate components

### Presentation of the Spell application

To illustrate some of iPOPO features, we will implement a very simple
application. Three bundles compose this application:

* A bundle that defines a component implementing a dictionary service
  (an English and a French dictionaries).
* One with a component requiring the dictionary service and providing
  a spell checker service.
* One that defines a component requiring the spell checker and
  providing a user line interface.

![Service hierarchy](/_static/tutorials/spell_checker/spellchecker_arch.svg){.align-center}

The spell dictionary components provide the `spell_dictionary_service`
specification. The spell checker provides a `spell_checker_service`
specification.

### Preparing the tutorial

The example contains several bundles:

* [`spell_checker_api.py`](../_static/tutorials/spell_checker/spell_checker_api.py)
  defines the Python
  [protocols](https://docs.python.org/3/library/typing.html#annotating-callable-objects)
  that describe the different services in use.
* [`spell_dictionary_EN.py`](../_static/tutorials/spell_checker/spell_dictionary_EN.py)
  defines a component that implements the Dictionary service,
  containing some English words.
* [`spell_dictionary_FR.py`](../_static/tutorials/spell_checker/spell_dictionary_FR.py)
  defines a component that implements the Dictionary service,
  containing some French words.
* [`spell_checker.py`](../_static/tutorials/spell_checker/spell_checker.py)
  contains an implementation of a Spell Checker. The spell checker
  requires a dictionary service and checks if an input passage is
    correct, according to the words contained in the wished dictionary.
* [`spell_client.py`](../_static/tutorials/spell_checker/spell_client.py)
  provides commands for the
  [Pelix shell service](../quickstart.md#play-with-the-shell).
  This component uses a spell checker service. The user can interact
  with the spell checker with this command line interface.

Finally, a
[main_pelix_launcher.py](../_static/tutorials/spell_checker/main_pelix_launcher.py)
script starts the Pelix framework. It is not considered as a bundle as
it is not loaded by the framework, but it can control the latter.

### Definining specifications

:::{note}
This section is new in iPOPO v3
:::

Instead of relying exclusively on specification names to link components
together, it is now recommended to declare protocols or classes and to use
those to declare injected fields.

For example, the `spell_checker_api` bundle contains only the definition of
the specifications we will use in this project.
It is recommended to use a specific file to define specifications and constants
in order to share it between the provider and consumer bundles.

:::{literalinclude} /_static/tutorials/spell_checker/spell_checker_api.py
:language: python
:linenos:
:::

* The `@Specification` decorator will store in the protocol/class the name
  of the specification. This is highly recommended as it will be the name used
  in the Pelix service registry and when communicating with remote framework
  if you want to use remote services.
* We recommend using the Python `Protocol` as parent of each specification class
  as it is meant to declare a type.

Once the specifications are defined, we can continue by implementing them with
different components.

:::{note}
Depending on your own code style, you might to easer provide explicit types
on specification methods methods or let them be inherited from the protocol.

Also note that the specification module must be importable by the bundles,
but doesn't need to be installed as a bundle itself.
:::

### The English dictionary bundle: Providing a service

The `spell_dictionary_EN` bundle is a simple implementation of the
Dictionary service. It contains few English words.

:::{literalinclude} /_static/tutorials/spell_checker/spell_dictionary_EN.py
:language: python
:linenos:
:::

* The `@Component` decorator is used to declare an iPOPO component. It
  must always be on top of other decorators.
* The `@Provides` decorator indicates that the component provides a service.
  We also indicate the type of service we provide, either using the type
  directly (recommended) or its specification name.
* The `@Instantiate` decorator instructs iPOPO to automatically create
  an instance of our component. The relation between components and
  instances is the same than between classes and objects in the
  object-oriented programming.
* The `@Property` decorator indicates the properties associated to
  this component and to its services (*e.g.* French or English language).
* The method decorated with `@Validate` will be called when the
  instance becomes valid.
* The method decorated with `@Invalidate` will be called when the
  instance becomes invalid (*e.g.* when one its dependencies goes
  away) or is stopped.

For more information about decorators, see [](../refcards/ipopo_decorators.rst).

In order for IDEs and type checking tools like MyPy to help you developping
components, you should indicate that the component class inherits from
the specification protocols it provides.

### The French dictionary bundle: Providing a service

The `spell_dictionary_FR` bundle is a similar to the
`spell_dictionary_EN` one. It only differs in the `language` component
property, as it checks some French words declared during component
validation.

:::{literalinclude} /_static/tutorials/spell_checker/spell_dictionary_FR.py
:language: python
:emphasize-lines: 17,21,23,35-43
:linenos:
:::

It is important to note that the iPOPO factory name must be unique in a
framework: only the first one to be registered with a given name will be
taken into account. The name of component instances follows the same
rule.

### The spell checker bundle: Requiring a service

The `spell_checker` bundle aims to provide a spell checker service.
However, to serve this service, this implementation requires a
dictionary service. During this step, we will create an iPOPO component
requiring a Dictionary service and providing the Spell Checker service.

:::{literalinclude} /_static/tutorials/spell_checker/spell_checker.py
:language: python
:linenos:
:::

* The `@Requires` decorator specifies a service dependency. This
  required service is injected in a local variable in this bundle. Its
  `aggregate` attribute tells iPOPO to collect the list of services.
  Again, the specification can be given by type or by name.
  providing the required specification, instead of the first one.
* The `@BindField` decorator indicates that a new required service
  bounded to the platform.
* The `@UnbindField` decorator indicates that one of required service
  has gone away.

As you can see, the injected field is declared twice:

* in the `@Requires` decorator, so that iPOPO knows what fields must be injected and how,
  which is mandatory for iPOPO to work
* at the class level, to give the injected field a type hint

This is due to a limitation of Python that doesn't support annotating class members.
That being said, it is highly recommended to manually declare the field class level at class with its type
in order to benefit fully from type checking tools and code completion in your IDE.

Also note that type hint you indicate must match the parameters you give to `@Requires`:

* If optional is set True, the injected value can be None, else it can only be of the specification type
* If aggregate is set to True, the injected value is a list
* Adapt the type for more complex decorators like `@RequiresMap`, ...

### The spell client bundle

The `spell_client` bundle contains a very simple user interface allowing
a user to interact with a spell checker service.

:::{literalinclude} /_static/tutorials/spell_checker/spell_client.py
:language: python
:linenos:
:::

The component defined here implements and provides a shell command
service, which will be consumed by the Pelix Shell Core Service. It
registers a `spell` shell command.

### Main script: Launching the framework

We have all the bundles required to start playing with the application.
To run the example, we have to start Pelix, then all the required
bundles.

:::{literalinclude} /_static/tutorials/spell_checker/main_pelix_launcher.py
:language: python
:linenos:
:::

### Running the application

Launch the `main_pelix_launcher.py` script. When the framework is
running, type in the console: **spell** to enter your language choice
and then your passage.

Here is a sample run, calling `python main_pelix_launcher.py`:

```
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
```

You can now go back to see other [tutorials](./index.md) or take a look at the
[](../refcards/index.md).
