Welcome to iPOPO
################

.. image:: ./_static/logo_texte_500.png
   :alt: iPOPO logo
   :scale: 25%
   :align: right

Welcome to iPOPO's documentation. This documentation is divided in
three main parts.
The :ref:`quickstart` will guide you to install iPOPO and write your
first components.
The :ref:`concepts` section details the various concepts of iPOPO.
Finally, the :ref:`tutorials` explain how to use the various built-in
services of iPOPO.
You can also take a look to the slides of the
`iPOPO tutorial <https://github.com/tcalmant/ipopo-tutorials/releases>`_
to have a quick overview of iPOPO.

This documentation is inspired from
`Flask's one <http://flask.pocoo.org/>`_.

iPOPO depends on a fork of `jsonrpclib`_, called `jsonrpclib-pelix`_.
The documentation of this library is available on
`GitHub <https://github.com/tcalmant/jsonrpclib>`_.

.. _jsonrpclib: https://github.com/joshmarshall/jsonrpclib
.. _jsonrpclib-pelix: https://github.com/tcalmant/jsonrpclib


State of this documentation
===========================

This documentation is a work in progress, going nearly from scratch.

The previous documentation was provided as a wiki on a dedicated server which I
had to take down due to many reasons (DoS attacks, update issues, ...).
As a result, the documentation is now hosted by
`Read the Docs <https://readthedocs.org/>`_.
The main advantages are that it is now included in the Git repository of the
project, and it can include *docstrings* directly from the source code.

Alas, the wiki content must be completely rewritten in reStructuredText format.
I take this opportunity to update the documentation, but it takes a lot of time,
and I can't work on this project as much as I'd like to.
So, if you have any question which can't be answered in the current
documentation, please ask on the
`users mailing list <https://groups.google.com/forum/#!forum/ipopo-users>`_.

As always, all contributions to the documentation and the code are very
appreciated.

.. include:: contents.rst.inc
