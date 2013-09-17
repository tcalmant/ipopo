iPOPO : A component model for Python
####################################

This is iPOPO, a component model framework for Python based on SOA principles.
It is based on Pelix, an SOA framework.

See http://ipopo.coderxpress.net for documentation and more information.

Feedback
########

Feel free to send feedback on your experience of Pelix/iPOPO, via the mailing
lists :

* User list:        http://groups.google.com/group/ipopo-users
* Development list: http://groups.google.com/group/ipopo-dev

More information at http://ipopo.coderxpress.net/


Compatibility
#############

Pelix and iPOPO are tested using `Tox <http://testrun.org/tox/latest/>`_ and
`Travis-CI <https://travis-ci.org/tcalmant/ipopo>`_ with:

* Python 2.6, 2.7, 3.2 and 3.3

  .. image:: https://travis-ci.org/tcalmant/ipopo.png?branch=dev
     :target: https://travis-ci.org/tcalmant/ipopo

It is also manually tested with:

* Pypy 1.9

To use iPOPO on Python 2.6, it is necessary to install the *importlib* module
back-port, using ``pip install importlib``.
To execute iPOPO tests on this version, you also need to install the *unittest2*
module.

iPOPO is available on `PyPI <http://pypi.python.org/pypi/iPOPO>`_.


Release notes
#############

See the CHANGELOG.rst file to see what changed in previous releases.

iPOPO 0.5.4
***********

Additions
=========

iPOPO
-----

* ``get_factory_details(name)`` method now also returns the ID of the bundle
  provided the component factory, and the component instance properties.

Shell
-----

* The help command now uses the *inspect* module to list the required and
  optional parameters.


Bugs fixed
==========

iPOPO
-----

* Protection of the unregistration of factories, as a component can kill
  another one of the factory during its invalidation.

Remote Services
---------------

* Protection of the unregistration loop during the invalidation of JSON-RPC and
  XML-RPC exporters.
* The *Dispatcher Servlet* now handles the *discovered* part of the discovery
  process. This simplifies the Multicast Discovery component and supresses a
  socket bug/feature on BSD (including Mac OS).

Shell
-----

* The ``make_table()`` method now accepts generators as parameters.
