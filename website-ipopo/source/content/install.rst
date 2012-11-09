.. Installation

.. |SL4A| replace:: SL4A
.. _SL4A: http://code.google.com/p/android-scripting/

Installation
############

Pre-requisites
**************

The distribution contains iPOPO and Pelix packages, which are fully runnable
with any Python 2.7 to Python 3.3 compatible interpreter.
If the back-port of the `importlib <http://pypi.python.org/pypi/importlib>`_ is
installed, iPOPO can also be run on a Python 2.6 compatible interpreter.

iPOPO has been tested on:

* `CPython <http://python.org/download/>`_ 2.6, 2.7, 3.1 and 3.2
* `Pypy <http://pypy.org/>`_ 1.8

Feel free to report other interpreters which can run iPOPO.

Due to syntax changes, iPOPO can't be run on a Python 2.5 interpreter
(e.g. `Jython <http://www.jython.org/>`_).


Set up iPOPO
************

The installation process is based on Python setup tools.

#. Download the latest version of iPOPO
   `here <http://ipopo.coderxpress.net/dl/ipopo-latest.zip>`_
#. Extract the content and go into *ipopo-dist* directory
#. Run the *setup.py* file:

   ``python setup.py install``

#. Test if the installation is correct:

   .. code-block:: python

      $ python
      >>> import pelix
      >>>

#. Start playing with iPOPO with the :ref:`samples`.

.. _unittests:

Unit tests
**********

Unit tests are in a different distribution file:
`unit tests <http://ipopo.coderxpress.net/dl/ipopo-latest-tests.zip>`_.

To apply the tests, just run the following modules:

+---------------------------+--------------------------------------------------+
| Module                    | Description                                      |
+===========================+==================================================+
| ``tests.utilities_test``  | Tests the utility module, namely the             |
|                           | synchronization decorators.                      |
+---------------------------+--------------------------------------------------+
| ``tests.ldapfilter_test`` | Tests the LDAP filter module                     |
+---------------------------+--------------------------------------------------+
| ``tests.pelix_test``      | Tests the Pelix framework, bundles, services and |
|                           | events                                           |
+---------------------------+--------------------------------------------------+
| ``tests.ipopo_test``      | Tests the iPOPO component manager and decorators |
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

   
Installation on Android
***********************

Pelix and iPOPO can also be easily installed on Android, using the |SL4A|_
project.

Install Python on your Android device
=====================================

Pelix has been tested with |SL4A|_ r5 and its default Python 2.6.2 interpreter.

#. Be sure your Android accepts unsigned applications

   * On Android, check the box in *Parameters > Security > Unknown sources*

#. Install the SL4A application, using the barcode on |SL4A|_
#. Install the Python interpreter

   #. Run *SL4A* on your Android
   #. *Menu* > View > Interpreters
   #. *Menu* > Add > Python 2.6.2, it will download Python4Android
   #. Install the downloaded APK, it should be visible in the notifications
   #. Run *Python for Android*
   #. Press Install, it will download the Python interpreter and its library

#. Test the installation

   #. Run *SL4A*
   #. *Menu* > View > Interpreters
   #. Select *Python 2.6.2*: it should start a Python console
   #. Enter ``exit()`` to stop the interpreter
   #. Choose *yes* to close the terminal.


Install ``importlib``
=====================

To work on Python 2.6, Pelix needs the ``importlib`` module.

The easiest way to get it is to download it from Pypi and push it to the SL4A
scripts directory.

#. Download ``importlib`` from Pypi: `<http://pypi.python.org/pypi/importlib>`_
#. Extract the *importlib/__init__.py* file and rename it *importlib.py*
#. Push *importlib.py* to the Android folder */sdcard/sl4a/scripts*

   * You can do it using a removable SD card (and store the file in
     *sl4a/scripts*)

   * Or, if you installed the Android SDK, you can do it with *adb*:

     .. code-block:: bash

        abd push importlib.py /sdcard/sl4a/scripts

.. note::

     You can also put importlib.py in */sdcard/sl4a*, to avoid modifying the
     Python path before start a Pelix framework (see :ref:`test_android`).


Install the Pelix-iPOPO egg file
================================

Currently, the *setup.py* used by Pelix is based on the ``distutils`` package
which can't be used to make. Therefore, you'll have to modify *setup.py*,
replacing the line:

.. code-block:: python

   from distutils.core import setup

by:

.. code-block:: python

   from setuptools import setup

Then you can create the egg file with the following command:

.. code-block:: bash

   python setup.py bdist_egg

The egg file will be created in the *dist* directory, and you need to push it
in the download folder of your Android, namely */sdcard/download* (using *adb*
or copying it on a removable SD card):

.. code-block:: bash

   # Using adb
   adb push dist/iPOPO-0.3-py2.6.egg /sdcard/download


Finally, you'll have to install the egg file with Python4Android:

#. Run *Python for Android*
#. Press *Import Modules*
#. Select *iPOPO-0.3-py2.6.egg*

.. _test_android:

Test the Android installation
=============================

Start a Python interpreter from SL4A and type the following commands:

.. code-block:: python

   # Add the scripts folder in Python path, to access importlib
   import sys
   sys.path.append('./scripts')
   
   # Start a framework
   import pelix.framework
   framework = pelix.framework.FrameworkFactory.get_framework()
   framework.start()
   
   # Install & start iPOPO
   context = framework.get_bundle_context()
   bid = context.install_bundle('pelix.ipopo.core')
   context.get_bundle(bid).start()
   
   # ... iPOPO is ready, see the tutorials to write your components

