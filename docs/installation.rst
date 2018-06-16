.. _installation:

Installation
============

iPOPO depends on only one external library,
`jsonrpclib-pelix <https://github.com/tcalmant/jsonrpclib>`_, which
provides some utility methods and is required to enable remote services.

To install iPOPO, you will need Python 2.7, Python 3.4 or newer.
iPOPO is constantly tested, using Tox and Travis-CI, on the following
interpreters:

  * Python 2.7
  * Python 3.4, 3.5 and 3.6

Support for Python 2.6 has been dropped with iPOPO 0.6.
The framework should run on Python 3.2 and 3.3 and also on Pypy, but this is
not guaranteed. Any feedback on those platforms is welcome.

There are many ways to install iPOPO, so let's have a look to some of
them.

System-Wide Installation
------------------------

This is the easiest way to install iPOPO, even though using virtual
environments is recommended to develop your applications.

For a system-wide installation, just run ``pip`` with root privileges::

    $ sudo pip install iPOPO

If you don't have root privileges and you can't or don't want to use
virtual environments, you can install iPOPO for your user only::

    $ pip install --user iPOPO

Virtual Environment
-------------------

Using virtual environments is the recommended way to install libraries
in Python.
It allows to try and develop with specific versions of libraries, to
test some packages, etc. without messing with your Python installation,
nor your main development environment.

It is also useful in production, as virtual environment allows to
isolate libraries, avoiding incompatibilities.

Python 3.3+
'''''''''''

Python 3.3 introduced the ``venv`` module, introducing a standard way
to handle virtual environments.
As this module is included in the Python standard library, you
shouldn't have to install it manually.

Now you can create a new virtual environment, here called *ipopo-venv*::

    $ python3 -m venv ipopo-venv

Continue to :ref:`then` to activate your new environment.

Older Python versions
'''''''''''''''''''''

Before Python 3.3, virtual environments were handled by a third-party
package, ``virtualenv``, which must be installed alongside Python.

If you are on Linux or Mac OS X, the following command should work::

    $ sudo pip install virtualenv

On Linux, virtualenv is probably provided by your distribution.
For example, you can use the following command on Debian or Ubuntu::

    $ sudo apt-get install python-virtualenv

Once virtualenv is installed, you can create you first virtual
environment::

    $ virtualenv ipopo-venv
    New python executable in ipopo-venv/bin/python
    Installing setuptools, pip............done.

.. _then:

Then...
'''''''

Now, whenever you want to work on this project, you will have to
activate the virtual environment::

    $ . ipopo-venv/bin/activate

If you are a Windows user, the following command is for you::

    > ipopo-venv\Scripts\activate

Either way, the ``python`` and ``pip`` commands you type in the shell should
be those of your virtual environment.
The shell prompt indicates the name of the virtual environment currently
in use.

Now you can install iPOPO using ``pip``. As you are in a virtual
environment, you don't need administration rights::

    $ pip install iPOPO

iPOPO is now installed and can be used in this environment. You can
now try it and develop your components.

Once you are done, you can get out of the virtual environment using
the following command (both on Linux and Windows)::

    $ deactivate

Development version
-------------------

If you want to work with the latest version of iPOPO, there are two ways:
you can either let ``pip`` pull in the development version, or you can
tell it to operate on a git checkout.
Either way, a virtual environment is recommended.

Get the git checkout in a new virtual environment and run in development mode::

    $ git clone https://github.com/tcalmant/ipopo.git
    # Cloning into 'ipopo'...
    $ cd ipopo
    $ python3 -m venv ipopo-venv
    New python executable in ipopo-venv/bin/python
    Installing setuptools, pip............done.
    $ . ipopo-venv/bin/activate
    $ python setup.py develop
    # ...
    Finished processing dependencies for iPOPO

This will pull the dependency (*jsonrpclib-pelix*) and activate the
git head as the current version inside the virtual environment.
As the *develop* installation mode uses symbolic links, you simply
have to run ``git pull origin`` to update to the latest version of
iPOPO in your virtual environment.

You can now continue to :ref:`Quick-start`
