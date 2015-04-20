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

Release notes: 0.6.1
####################

See the CHANGELOG.rst file to see what changed in previous releases.

iPOPO
*****

* The stack trace of the exception that caused a component to be in the
  ERRONEOUS state is now kept, as a string. It can be seen throught the
  ``instance`` shell command.

Shell
*****

* The command parser has been separated from the shell core service. This
  allows to create custom shells without giving access to Pelix administration
  commands.
* Added ``cd`` and ``pwd`` shell commands, which allow changing the working
  directory of the framework and printing the current one.
* Corrected the encoding of the shell output string, to avoid exceptions when
  printing special characters.

Remote Services
***************

* Corrected a bug where an imported service with the same endpoint name as an
  exported service could be exported after the unregistration of the latter.
