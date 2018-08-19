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

iPOPO is released under the terms of the
`Apache Software License 2.0 <https://www.apache.org/licenses/LICENSE-2.0.html>`_.
It depends on a fork of `jsonrpclib`_, called `jsonrpclib-pelix`_.
The documentation of this library is available on
`GitHub <https://github.com/tcalmant/jsonrpclib>`_.

.. _jsonrpclib: https://github.com/joshmarshall/jsonrpclib
.. _jsonrpclib-pelix: https://github.com/tcalmant/jsonrpclib


About this documentation
========================

The previous documentation was provided as a wiki, which has been shut down
for various reasons.
A copy of the previous content is available in the
`convert_doc <https://github.com/tcalmant/ipopo/tree/convert_doc>`_
branch, even though it's starting to age.
The documentation is now hosted on `Read the Docs <https://readthedocs.org/>`_.
The main advantages are that it is now included in the Git repository of the
project, and it can include *docstrings* directly from the source code.

If you have any question which hasn't been answered in the documentation,
please ask on the
`users' mailing list <https://groups.google.com/forum/#!forum/ipopo-users>`_.

As always, all contributions to the documentation and the code are very
appreciated.

.. include:: contents.rst.inc
