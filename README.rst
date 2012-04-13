README
======

This is iPOPO, a component model framework for Python based on SOA principles.
It is based on Pelix, an SOA framework.

See http://ipopo.coderxpress.net for documentation and more information.

FEEDBACK
========

Feel free to send feedback on your experience of Pelix/iPOPO, via the mailing
lists :

* User list :        http://groups.google.com/group/ipopo-users
* Development list : http://groups.google.com/group/ipopo-dev

More information at http://ipopo.coderxpress.net/

RELEASE NOTES
=============

Version 0.3
-----------

Packages have been renamed. As the project goes public, it may not have
relations to isandlaTech projets anymore.

* psem2m                 -> pelix
* psem2m.service.pelix   -> pelix.framework
* psem2m.component       -> pelix.ipopo
* psem2m.component.ipopo -> pelix.ipopo.core

Version 0.2
-----------

Version 0.2 is the first public release, under GPLv3 license (see LICENSE).

Compatibility
=============

The package has been tested with:

* CPython 2.6, 2.7, 3.1 and 3.2
* Pypy 1.8

To work with CPython 2.6, the *importlib* module back-port must be installed.
It is available on Pypi. 
