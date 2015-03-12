iPOPO: A component model for Python
###################################

.. image:: https://pypip.in/version/ipopo/badge.svg?style=flat
    :target: https://pypi.python.org/pypi/ipopo/
    :alt: Latest Version

.. image:: https://pypip.in/license/ipopo/badge.svg?style=flat
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

iPOPO is available on `PyPI <http://pypi.python.org/pypi/iPOPO>`_ and is
released under the terms of the
`Apache License 2.0 <http://www.apache.org/licenses/LICENSE-2.0>`_.


Feedback
########

Feel free to send feedback on your experience of Pelix/iPOPO, via the mailing
lists :

* User list:        http://groups.google.com/group/ipopo-users (don't be shy)
* Development list: http://groups.google.com/group/ipopo-dev

Bugs and features requests can be submitted on GitHub
`tcalmant/ipopo <https://github.com/tcalmant/ipopo/issues>`_.

More information at https://ipopo.coderxpress.net/


Compatibility
#############

Pelix and iPOPO are tested using `Tox <http://testrun.org/tox/latest/>`_ and
`Travis-CI <https://travis-ci.org/tcalmant/ipopo>`_ with Pypy 2.5.0 and
Python 2.7, 3.2, 3.3 and 3.4.

Most of the framework can work with Python 2.6 if the *importlib* package is
installed, but there is no guarantee that the latest features will be
compatible.

Release notes: 0.6.0
####################

See the CHANGELOG.rst file to see what changed in previous releases.

Project
*******

* The support of Python 2.6 has been removed

Utilities
*********

* The XMPP bot class now supports anonymous connections using SSL or StartTLS.
  This is a workaround for
  `issue 351 <https://github.com/fritzy/SleekXMPP/issues/351>`_
  of SleekXMPP.
