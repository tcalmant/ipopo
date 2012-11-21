.. Installation

.. |SL4A| replace:: SL4A
.. _SL4A: http://code.google.com/p/android-scripting/

Installation
############

Pre-requisites
**************

The distribution contains iPOPO and Pelix packages, which are fully runnable
with any Python 2.7 to Python 3.3 compatible interpreter.

iPOPO has been tested on:

* `Python <http://python.org/download/>`_ 2.6, 2.7, 3.1 and 3.2
* `Pypy <http://pypy.org/>`_ 1.9

Feel free to report other interpreters which can run iPOPO.

Due to the use of Python 2.6 syntax, iPOPO can't be run on a Python 2.5
interpreter (e.g. `Jython <http://www.jython.org/>`_) nor on an *incomplete*
Python 2.6 interpreter (e.g.
`Python on a chip <http://code.google.com/p/python-on-a-chip/>`_).

Python 2.6
==========

Pelix needs ``importlib`` to work, which is part of the Python standard library
since version 2.7.
A back port of this module is available on PyPI and can be installed using
the following command:

.. code-block:: bash

   # Install the importlib package
   sudo easy_install -U importlib


Install iPOPO
*************

From the Python Package Index
=============================

Since version 0.4, iPOPO can be installed using ``easy_install`` or ``pip``:

.. code-block:: bash
   :linenos:
   
   # Using easy_install
   sudo easy_install -U iPOPO
   
   # Using pip
   sudo pip install --upgrade iPOPO


From the source files
=====================

The installation process is based on Python setup tools.

#. Download the latest version of iPOPO
   `here <http://ipopo.coderxpress.net/dl/ipopo-latest.zip>`_, or clone the
   git directory from `GitHub <https://github.com/tcalmant/ipopo>`_.
#. Extract the content and go into *ipopo-dist* directory
#. Run the *setup.py* file:

   .. code-block:: bash

      python setup.py install

   .. note:: If you want to modify iPOPO, you can use the following command
      to avoid re-installing iPOPO :

      .. code-block:: bash

         python setup.py develop


#. Test if the installation is correct:

   .. code-block:: python

      $ python
      >>> import pelix
      >>>

#. Start playing with iPOPO with the :ref:`tutorials`.

.. _unittests:

Unit tests
**********

Unit tests are in a different distribution file:
`unit tests <http://ipopo.coderxpress.net/dl/ipopo-latest-tests.zip>`_.

To run the tests, just run the following modules:

+---------------------------+--------------------------------------------------+
| Module                    | Description                                      |
+===========================+==================================================+
| ``tests.ipopo_test``      | Tests the iPOPO component manager and decorators |
+---------------------------+--------------------------------------------------+
| ``tests.ldapfilter_test`` | Tests the LDAP filter module                     |
+---------------------------+--------------------------------------------------+
| ``tests.pelix_test``      | Tests the Pelix framework, bundles, services and |
|                           | events                                           |
+---------------------------+--------------------------------------------------+
| ``tests.utilities_test``  | Tests the utility module, namely the             |
|                           | synchronization decorators                       |
+---------------------------+--------------------------------------------------+
| ``tests.http.basic_test`` | Tests the basic implementation of the HTTP       |
|                           | service                                          |
+---------------------------+--------------------------------------------------+

For example:

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


Coverage scripts
================

To see the coverage of one or all test modules, there are two utility Bash
scripts.
They both use the `coverage <http://nedbatchelder.com/code/coverage/>`_ module
ran in the interpreters defined in the scripts.

.. note:: Coverage must be installed in all interpreters used in the tests,
   by using ``easy_install`` or ``pip``:
   
   .. code-block:: bash
   
      # You might need to update 'distribute' too (with easy_install only)
      $ sudo easy_install -U distribute
   
      $ sudo easy_install -U coverage
      # Or
      $ sudo pip install coverage

* ``cover.sh``: computes the coverage of the given test module. The given
  parameters will automatically be prefixed by *tests/* and suffixed with
  *_test.py*.

  .. code-block:: bash

     $ ./cover.sh ldapfilter
     # ...
     $ ./cover.sh http/basic
     # ...

* ``cover_all.sh``: it runs a list of tests and aggregates their coverage in
  a single report.

  .. code-block:: bash

     $ ./cover_all.sh
     # ...


Customization
=============

Change the interpreters
-----------------------

To change the interpreters that will execute the tests, you have to modify
the **PYTHONS** Bash array


Change the scripts in ``cover_all.sh``
--------------------------------------


Installation on Android
***********************

Pelix and iPOPO can also be installed on Android, using the |SL4A|_ project.

Install Python on your Android device
=====================================

Pelix has been tested with |SL4A|_ r5 and its default Python 2.6.2 interpreter.

#. Your Android must accept unsigned applications

   * On Android, check the box in *Parameters > Security > Unknown sources*

#. Install the SL4A application, using the barcode on the |SL4A|_ project page
#. Install its Python interpreter

   #. Run *SL4A* on your Android
   #. *Menu* > View > Interpreters
   #. *Menu* > Add > Python 2.6.2, it will download *Python4Android*
   #. Install the downloaded APK, it should be visible in the notification bar
      or in the downloads directory
   #. Run the *Python for Android* application
   #. Press *Install*, it will download the Python interpreter and its library

#. Test the installation

   #. Run *SL4A*
   #. *Menu* > View > Interpreters
   #. Select *Python 2.6.2*: it should start a Python console
   #. Enter ``exit()`` to stop the interpreter
   #. Choose *yes* to close the terminal.


Install ``importlib``
=====================

To work on Python 2.6, Pelix needs the ``importlib`` module.

The easiest way to get it is to download it from PyPI and push it to the SL4A
scripts directory.

#. Download ``importlib`` from PyPI: `<http://pypi.python.org/pypi/importlib>`_
#. Extract the *importlib/__init__.py* file and rename it *importlib.py*
#. Push *importlib.py* to the Android folder */sdcard/sl4a*

   * You can do it using a removable SD card and storing the file in
     the *sl4a* folder

   * Or, if you installed the Android SDK, you can do it with *adb*:

     .. code-block:: bash

        abd push importlib.py /sdcard/sl4a


Install the Pelix-iPOPO egg file
================================

You can create the Python Egg file with the following command:

.. code-block:: bash

   python setup.py bdist_egg


.. note:: You will need the setuptools package for this to work:

   .. code-block:: bash
   
      $ easy_install -U setuptools


The egg file will be created in the *dist* directory, and you will need to push
it in the download folder of your Android, namely */sdcard/download*
(using *adb* or copying it on a removable SD card):

.. code-block:: bash

   # Using adb
   adb push dist/iPOPO-0.3-py2.6.egg /sdcard/download


Finally, you'll have to install the egg file with *Python4Android*:

#. Run the *Python for Android* application
#. Press *Import Modules*
#. Select *iPOPO-0.3-py2.6.egg*

.. _test_android:

Test the Android installation
=============================

Start a Python interpreter from SL4A and type the following commands:

.. code-block:: python
   
   # Start a framework
   import pelix.framework
   framework = pelix.framework.FrameworkFactory.get_framework()
   framework.start()
   
   # Install & start iPOPO
   context = framework.get_bundle_context()
   bid = context.install_bundle('pelix.ipopo.core')
   context.get_bundle(bid).start()
   
   # ... iPOPO is ready, see the tutorials to write your components

