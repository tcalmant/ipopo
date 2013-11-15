iPOPO : A component model for Python
####################################

This is iPOPO, a component model framework for Python based on SOA principles.
It is based on Pelix, an SOA framework.

See http://ipopo.coderxpress.net for documentation and more information.

iPOPO is released under the Apache License 2.0.


Feedback
########

Feel free to send feedback on your experience of Pelix/iPOPO, via the mailing
lists :

* User list:        http://groups.google.com/group/ipopo-users (don't be shy)
* Development list: http://groups.google.com/group/ipopo-dev

More information at https://ipopo.coderxpress.net/


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

iPOPO 0.5.5
***********

Project
=======

The license of the iPOPO project is now an Apache License 2.0.


Framework
=========

* ``get_*_service_reference*()`` methods have a default LDAP filter set to
  ``None``. Only the service specification is required, event if set to
  ``None``.

* Added a context ``use_service(context, svc_ref)``, that allows to consume a
  service in a ``with`` block:

  .. code-block:: python

     from pelix.utilities import use_service
     with use_service(bundle_context, svc_ref) as svc:
        svc.foo()

  Service will be released automatically.


iPOPO
=====

* Added the *Handler Factory* pattern : all instance handlers are created by
  their factory, called by iPOPO according to the handler IDs found in the
  factory context.
  This will simplify the creation of new handlers.

* Added a context ``use_ipopo(context)``, that allows to use the iPOPO service
  in a ``with`` block:

  .. code-block:: python

     from pelix.ipopo.constants import use_ipopo
     with use_ipopo(bundle_context) as ipopo:
        ipopo.instantiate('my.factory', 'my.instance', {})

  The iPOPO service will be released automatically.


Services
========

* Added the ConfigurationAdmin service
* Added the FileInstall service
