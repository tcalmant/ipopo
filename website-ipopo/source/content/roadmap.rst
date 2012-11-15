.. Project road map

Road map
########

This road map is given as an indication of the future features of iPOPO, but
it might not be fully respected.

Feel free to post feature requests on
`GitHub <https://github.com/tcalmant/ipopo/issues?state=open>`_ or on the
`users mailing list <http://groups.google.com/group/ipopo-users>`_.


Planned for next release
************************

Future work on iPOPO will mainly concern:

#. Improvements on the bundle loading operation:

   * Using the ``__import__`` hook
   * Using a framework instance-local ``sys.modules`` list, to isolate
     the interpreters modules of the framework ones.

#. Ability to load a Python package as bundle or a set of bundles

   * Using the ``__import__`` hook and walking through the package with
     ``importlib``


Ideas for future versions
*************************

* Implement more OSGi-like services:

  * *Service Factories*: special services that returns a service instance
    according to the requesting bundle
  * *LogService*: using the Python logging package to implement the OSGi
    interfaces
  * *ConfigAdmin*: a configuration utility service
  * *EventAdmin*: an inter-service event notifier
  * *Remote Services*: to be able to work with a remote instance of Pelix or
    even with WebServices.
    I am currently looking into `Spyne <http://spyne.io/>`_ to ease the
    implementation.

* Provide a benchmark suite, comparing both start up and execution times
  using Pelix, Pelix/iPOPO or standard Python.

* Add a support of UPnP, in relation with the *Remote Services* implementation

  * A Pelix service might be discovered and used by other devices through UPnP

* Add other interfaces for the Pelix shell:

  * Text interface (standard input)
  * XMPP interface
  * ...

* Add more tutorials to the web site:

  * How to transform a simple module into a Pelix bundle
  * Implementation of a *cron*-like service
  * ...

* Provide a bridge to ease the usage of C libraries as modules or services
* Provide a more interesting specification model, testing if a service
  really implements its claimed specifications.
