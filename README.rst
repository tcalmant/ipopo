iPOPO: A component model for Python
###################################

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


Release notes: 0.5.9
####################

See the CHANGELOG.rst file to see what changed in previous releases.

Project
*******

* iPOPO now works with IronPython (tested inside Unity 3D)

iPOPO
*****

* Components raising an error during validation goes in the ERRONEOUS state,
  instead of going back to INVALID.
  This avoids trying to validate them automatically.
* The ``retry_erroneous()`` method of the iPOPO service and the ``retry`` shell
  command allows to retry the validation of an ERRONEOUS component.
* The ``@SingletonFactory`` decorator can replace the ``@ComponentFactory``
  one.
  It ensures that only one component of this factory can be instantiated at a
  time.
* The ``@Temporal`` requirement decorator allows to require a service and to
  wait a given amount of time for its replacement before invalidating the
  component or while using the requirement.
* ``@RequiresBest`` ensures that it is always the service with the best
  ranking that is injected in the component.
* The ``@PostRegistration`` and ``@PreUnregistration`` callbacks allows the
  component to be notified right after one of its services has been registered
  or will be unregistered.

HTTP
****

* The generated 404 page shows the list of registered servlets paths.
* The 404 and 500 error pages can be customized by a hook service.
* The default binding address is back to "0.0.0.0" instead of "localhost".
  (for those who used the development version)

Utilities
*********

* The ``ThreadPool`` class is now a cached thread pool. It now has a minimum
  and maximum number of threads: only the required threads are alive.
  A thread waits for a task during 60 seconds (by default) before stopping.
