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

iPOPO 0.5.8
***********

Framework
=========

* ``FrameworkFactory.delete_framework()`` can be called with ``None`` or
  without argument. This simplifies the clean up afters tests, etc.
* The list returned by ``Framework.get_bundles()`` is always sorted by
  bundle ID.


iPOPO
=====

* Added the ``immediate_rebind`` option to the ``@Requires`` decorator.
  This indicates iPOPO to not invalidate then revalidate a component if a
  service can replace an unbound required one. This option inly applies to
  non-optional, non-aggregate requirements.


Shell
=====

* The I/O handler is now part of a ShellSession bean. The latter has the same
  API as the I/O handler so there is no need to update existing commands.
  I/O Handler write methods are now synchronized.
* The shell supports variables as arguments, e.g. ``echo $var``.
  See `string.Template <https://docs.python.org/3/library/string.html#template-strings>`_
  for more information. The Template used in Pelix Shell allows ``.`` (dot)
  in names.
* A special variable ``$?`` stores the result of the last command which
  returned a result, i.e. anything but None or False.
* Added *set* and *unset* commands to work with variables
* Added the *run* command to execute a script file.
* Added protection against ``AttributeError`` in *threads* and *thread*
