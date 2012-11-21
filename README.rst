README
######

This is iPOPO, a component model framework for Python based on SOA principles.
It is based on Pelix, an SOA framework.

See http://ipopo.coderxpress.net for documentation and more information.

Feedback
########

Feel free to send feedback on your experience of Pelix/iPOPO, via the mailing
lists :

* User list :        http://groups.google.com/group/ipopo-users
* Development list : http://groups.google.com/group/ipopo-dev

More information at http://ipopo.coderxpress.net/

Release notes
#############

Version 0.4
***********

Version 0.4 fixes many bugs and provides new features:

* Pelix:

  * ``create_framework()`` utility method
  * The framework has been refactored, allowing more efficient services and
    events handling

* iPOPO:

  * A component can provide multiple services
  * A service controller can be injected for each provided service, to
    activate or deactivate its registration
  * Dependency injection and service providing mechanisms have been refactored,
    using a basic handler concept.

* Included tools:

  * Added a HTTP service component, using the concept of *servlet*
  * Added an extensible shell, interactive and remote, simplifying the usage
    of a framework instance

Version 0.3
***********

Packages have been renamed. As the project goes public, it may not have
relations to isandlaTech projects anymore.

* psem2m                 -> pelix
* psem2m.service.pelix   -> pelix.framework
* psem2m.component       -> pelix.ipopo
* psem2m.component.ipopo -> pelix.ipopo.core

Version 0.2
***********

Version 0.2 is the first public release, under GPLv3 license (see LICENSE).

Compatibility
#############

The package has been tested with:

* Python 2.6, 2.7, 3.1 and 3.2
* Pypy 1.8, 1.9

To work with Python 2.6, the *importlib* module back-port must be installed.
It is available on PyPI.
