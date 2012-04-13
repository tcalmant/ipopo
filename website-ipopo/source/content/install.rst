.. Installation

Installation
############

Pre-requisites
**************

The distribution contains iPOPO and Pelix packages, which are fully runnable
with any Python 2.7 to Python 3.2 compatible interpreter.
If the back-port of the `importlib <http://pypi.python.org/pypi/importlib>`_ is
installed, iPOPO can also be run on a Python 2.6 compatible interpreter.

iPOPO has been tested on :

* `CPython <http://python.org/download/>`_ 2.6, 2.7, 3.1 and 3.2
* `Pypy <http://pypy.org/>`_ 1.8

Feel free to report other interpreters which can run iPOPO.

Due to syntax changes, it can't be run on a Python 2.5 interpreter
(e.g. `Jython <http://www.jython.org/>`_).


Set up iPOPO
************

The installation process is based on Python setup tools.

#. Download the latest version of iPOPO
   `here <http://ipopo.coderxpress.net/dl/ipopo-latest.zip>`_
#. Extract the content and go into *ipopo-dist* directory
#. Run the *setup.py* file :

   ``python setup.py install``

#. Test if the installation is correct :

   .. code-block:: python

      $ python
      >>> import pelix
      >>>

#. Start playing with iPOPO with the :ref:`samples`.

.. _unittests:

Unit tests
**********

Unit tests are in a different distribution file :
`unit tests <http://ipopo.coderxpress.net/dl/ipopo-latest-tests.zip>`_.

To apply the tests, just run the following modules :

* tests.utilities_test : Tests the utility module, namely the synchonization
  decorators.
* tests.ldapfilter_test : Tests the LDAP filter module
* tests.pelix_test : Tests the Pelix framework, bundles, services and events
* tests.ipopo_test : Tests the iPOPO component manager and decorators

For example :

.. code-block:: bash
   
   $ export PYTHONPATH=.
   $ python -m tests.ldapfilter_test
   ..............
   ----------------------------------------------------------------------
   Ran 14 tests in 0.002s

   OK

   $ python tests/ipopo_test.py
   ...........
   ----------------------------------------------------------------------
   Ran 11 tests in 0.027s

   OK
