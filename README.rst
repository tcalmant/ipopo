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

iPOPO 0.5.6
***********

Project
=======

* Added samples to the project repository
* Removed the static website from the repository

* Added the project to `Coveralls <https://coveralls.io/>`_
* Increased code coverage


Framework
=========

* Added a ``@BundleActivator`` decorator, to define the bundle activator class.
  The ``activator`` module variable should be replaced by this decorator.
* Renamed specifications constants: from ``XXX_SPEC`` to ``SERVICE_XXX``


iPOPO
=====

* Added a *waiting list* service: instantiates components as soon as the iPOPO
  service and the component factory are registered
* Added ``@RequiresMap`` handler
* Added an ``if_valid`` parameter to binding callbacks decorators: ``@Bind``,
  ``@Update``, ``@Unbind``, ``@BindField``, ``@UpdateField``, ``@UnbindField``.
  The decorated method will be called if and only if the component valid.
* The ``get_factory_context()`` from ``decorators`` becomes public to ease
  the implementation of new decorators


Remote Services
===============

* Large rewriting of Remote Service core modules

  * Now using OSGi Remote Services properties
  * Added support for the OSGi EDEF file format (XML)

* Added an abstract class to easily write RPC implementations
* Added mDNS service discovery
* Added an MQTT discovery protocol
* Added an MQTT-RPC protocol, based on Node.js
  `MQTT-RPC module <https://github.com/wolfeidau/mqtt-rpc>`_
* Added a Jabsorb-RPC transport. Pelix can now use Java services and vice-versa,
  using:

  * `Cohorte Remote Services <https://github.com/isandlaTech/cohorte-remote-services>`_
  * `Eclipse ECF <http://wiki.eclipse.org/ECF>`_ and the
    `Jabsorb-RPC provider <https://github.com/isandlaTech/cohorte-remote-services/tree/master/org.cohorte.ecf.provider.jabsorb>`_


Shell
=====

* Enhanced completion with ``readline``
* Enhanced commands help generation
* Added arguments to filter the output of ``bl``, ``sl``, ``factories``
  and ``instances``
* Corrected ``prompt`` when using ``readline``
* Corrected ``write_lines()`` when not giving format arguments
* Added an ``echo`` command, to test string parsing


Services
========

* Added support for *managed service factories* in ConfigurationAdmin
* Added an EventAdmin-MQTT bridge: events from EventAdmin with an
  *event.propage* property are published over MQTT
* Added an early version of an MQTT Client Factory service


Miscellaneous
=============

* Added a ``misc`` package, with utility modules and bundles:

  * ``eventadmin_printer``: an EventAdmin handler that prints or logs the events
    it receives
  * ``jabsorb``: converts dictionary from and to the Jabsorb-RPC format
  * ``mqtt_client``: a wrapper for the `Paho <http://www.eclipse.org/paho/>`_
    MQTT client, used in MQTT discovery and MQTT-RPC.
