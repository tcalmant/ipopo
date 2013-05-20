.. iPOPO on Android

.. |SL4A| replace:: SL4A
.. _SL4A: http://code.google.com/p/android-scripting/

.. |Kivy| replace:: Kivy
.. _Kivy: http://kivy.org/

iPOPO on Android
################

Pelix and iPOPO can be installed on Android too.

Using |SL4A|
************

SL4A allows to run an interactive Python interpreter, or scripts stored on the
SD card.


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

You can create the Python Egg file from the sources, with the following command:

.. code-block:: bash

   python setup.py bdist_egg


.. note:: You will need the setuptools package up to date for this to work:

   .. code-block:: bash
   
      $ easy_install -U setuptools


The egg file will be created in the *dist* directory, and you will need to push
it in the download folder of your Android, namely */sdcard/download*
(using *adb* or copying it on a removable SD card):

.. code-block:: bash

   # Using adb
   adb push dist/iPOPO-0.5-py2.6.egg /sdcard/download


Finally, you'll have to install the egg file with *Python4Android*:

#. Run the *Python for Android* application
#. Press *Import Modules*
#. Select *iPOPO-0.5-py2.6.egg*

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
   context.install_bundle('pelix.ipopo.core').start()
   
   # ... iPOPO is ready, see the tutorials to write your components


Using Kivy
**********

|Kivy|_ is a Python library which allows to write graphical applications that can
be run on multiple devices (Android, iOS, Windows, Linux, ...).

The instructions of Kivy to build an Android application are a good starting
point:

* `Kivy Basics <http://kivy.org/docs/guide/basic.html>`_
* `Create a package for Android <http://kivy.org/docs/guide/packaging-android.html>`_

Install Kivy and Python-for-Android
===================================

.. note:: Python-for-Android is based on a set of Linux scripts. I don't know
   if the Windows/MacOS equivalent exists.
   
   It requires matching Android SDK and NDK. I use SDK API v14 and NDK r8.

#. Install the `Prerequisites <http://python-for-android.readthedocs.org/en/latest/prerequisites/>`_.
#. Download Python-for-Android
#. Compile the tool chain:

   .. code-block:: bash

      # In the Python-for-android folder
      # This might take several minutes
      ./distribute.sh -m "kivy android pyjnius" -d "my-distribution"

   This will build a Python interpreter, the Kivy library (for UI), the
   ``android`` utility module and PyJNIus, which allows to access Java classes
   from Python.


Build an APK
============

#. Write your code in a folder, which we will call **$SRC**. The entry point
   of your application must be in a file called ``main.py``.

#. Build the APK, for example:

   .. code-block:: bash

      # In the Python-for-android folder
      cd dist/my-distribution
      ./build.py --dir "$SRC" \
                 --package "my.application.package.name" \
                 --name "My Application Name" \
                 --version "1.0.0" \
                 --permission INTERNET \
                 --permission CHANGE_WIFI_MULTICAST_STATE \
                 --permission ACCESS_WIFI_STATE \
                 debug

   This will build an APK in the *bin* folder, named
   *MyApplicationName-1.0.0-debug.apk*, that can be installed using ``adb``.

   The given permissions are necessary to use the Pelix Remote Services:

     * INTERNET: gives access to the socket API
     * ACCESS_WIFI_STATE: gives access to the Wifi API
     * CHANGE_WIFI_MULTICAST_STATE: allows to get a Wifi Multicast Lock,
       necessary to listen to multicast packets on the Wifi network.

#. Run the application on the phone.

   .. note:: The first execution takes around 20 seconds to start, as the whole
      Python library is extracted in the application cache.
      The following executions takes around 3 seconds to start.
