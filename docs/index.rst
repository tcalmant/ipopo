Welcome to iPOPO
################

.. image:: ./_static/logo_texte_200.png
   :alt: iPOPO logo
   :align: right

iPOPO is a Python-based Service-Oriented Component Model (SOCM) based on Pelix,
a dynamic service platform.
They are inspired by two popular Java technologies for the development of
long-lived applications: the
`iPOJO <http://felix.apache.org/documentation/subprojects/apache-felix-ipojo.html>`_
component model and the `OSGi <http://osgi.org/>`_ Service Platform.
iPOPO enables the conception of long-running and modular IT services.

This documentation is divided into three main parts.
The :ref:`quickstart` will guide you to install iPOPO and write your first
components.
The :ref:`refcards` section details the various concepts of iPOPO.
Finally, the :ref:`tutorials` explain how to use the various built-in
services of iPOPO.
You can also take a look at the slides of the
`iPOPO tutorial <https://github.com/tcalmant/ipopo-tutorials/releases>`_
to have a quick overview of iPOPO.

This documentation is inspired by
the `Flask's one <http://flask.pocoo.org/>`_.

iPOPO depends on a fork of `jsonrpclib`_, called `jsonrpclib-pelix`_.
The documentation of this library is available on
`GitHub <https://github.com/tcalmant/jsonrpclib>`_.

.. _jsonrpclib: https://github.com/joshmarshall/jsonrpclib
.. _jsonrpclib-pelix: https://github.com/tcalmant/jsonrpclib


Usage survey
============

In order to gain insight from the iPOPO community, I've put a
`really short survey <https://docs.google.com/forms/d/1zx18_Rg27mjdGrlbtr9fWFmVnZNINo9XCfrYJbr4oJI>`_
on Google Forms (no login required).

Please, feel free to answer it, the more answers, the better.
All feedback is really appreciated, and I'll write about the aggregated results
on the users' mailing list, once enough answers will have been received.


State of this documentation
===========================

This documentation is a work in progress, starting nearly from scratch.

The previous documentation was provided as a wiki on a dedicated server which I
had to take down due to many reasons (DoS attacks, update issues, ...).
As a result, the documentation is now hosted by
`Read the Docs <https://readthedocs.org/>`_.
The main advantages are that it is now included in the Git repository of the
project, and it can include *docstrings* directly from the source code.

Alas, the wiki content must be completely rewritten in reStructuredText format.
I take this opportunity to update the documentation, but it takes a lot of time,
and I can't work on this project as much as I'd like to.
So, if you have any question which hasn't been answered in the current
documentation, please ask on the
`users' mailing list <https://groups.google.com/forum/#!forum/ipopo-users>`_.

As always, all contributions to the documentation and the code are very
appreciated.

.. include:: contents.rst.inc
