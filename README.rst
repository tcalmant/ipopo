iPOPO : A component model for Python
####################################

.. image:: https://travis-ci.org/tcalmant/ipopo.svg?branch=master
     :target: https://travis-ci.org/tcalmant/ipopo

.. image:: https://coveralls.io/repos/tcalmant/ipopo/badge.png?branch=master
     :target: https://coveralls.io/r/tcalmant/ipopo?branch=master

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

More information at https://ipopo.coderxpress.net/


Compatibility
#############

Pelix and iPOPO are tested using `Tox <http://testrun.org/tox/latest/>`_ and
`Travis-CI <https://travis-ci.org/tcalmant/ipopo>`_ with Python 2.6, 2.7, 3.2
and 3.3.

It is also manually tested with Pypy 1.9 and Python 3.4.

To use iPOPO on Python 2.6, it is necessary to install the *importlib* module
back-port, using ``pip install importlib``.
To execute iPOPO tests on this version, you also need to install the *unittest2*
module.


Release notes
#############

See the CHANGELOG.rst file to see what changed in previous releases.

iPOPO 0.5.7
***********

Project
=======

* Code review to be more PEP-8 compliant
* `jsonrpclib-pelix <https://pypi.python.org/pypi/jsonrpclib-pelix>`_ is now an
  install requirement (instead of an optional one)

Framework
=========

* Forget about previous global members when calling ``Bundle.update()``. This
  ensures to have a fresh dictionary of members after a bundle update
* Removed ``from pelix.constants import *`` in ``pelix.framework``:
  only use ``pelix.constants`` to access constants


Remote Services
===============

* Added support for endpoint name reuse
* Added support for synonyms: specifications that can be used on the remote
  side, or which describe a specification of another language
  (e.g. a Java interface)
* Added support for a *pelix.remote.export.reject* service property: the
  specifications it contains won't be exported, event if indicated in
  *service.exported.interfaces*.
* Jabsorb-RPC:

  * Use the common dispatch() method, like JSON-RPC

* MQTT(-RPC):

  * Explicitly stop the reading loop when the MQTT client is disconnecting
  * Handle unknown correlation ID


Shell
=====

* Added a ``loglevel`` shell command, to update the log level of any logger
* Added a ``--verbose`` argument to the shell console script
* Remote shell module can be ran as a script


HTTP
====

* Remove double-slashes when looking for a servlet


XMPP
====

* Added base classes to write a XMPP client based on
  `SleekXMPP <http://sleekxmpp.com/>`_
* Added a XMPP shell interface, to control Pelix/iPOPO from XMPP


Miscellaneous
=============

* Added an IPv6 utility module, to setup double-stack and to avoids missing
  constants bugs in Windows versions of Python
* Added a ``EventData`` class: it acts like ``Event``, but it allows to store
  a data when setting the event, or to raise an exception in all callers of
  ``wait()``
* Added a ``CountdownEvent`` class, an ``Event`` which is set until a given
   number of calls to ``step()`` is reached
* ``threading.Future`` class now supports a callback methods, to avoid to
  actively wait for a result.
