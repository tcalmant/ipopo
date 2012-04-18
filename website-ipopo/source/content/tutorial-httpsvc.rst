.. HTTP Service tutorial

HTTP Service tutorial
#####################

.. todo:: Replace code with a simple description and **small** snippets.
   Put the sources in appendices and add a link the source file corresponding to
   each session.


In order to apply the iPOPO mechanisms, this tutorial will describe how to
write and execute an HTTP service based on the whiteboard pattern.

Architecture
************

The HTTP component
******************

In Python, writing a HTTP server is quite simple. The idea is to start a HTTP
server indicating a request handler, which must respond to a client.

The component will start the server with a special request handler, that calls
the best matching servlet component or returns a 404 page.

HTTP Component
==============

.. literalinclude:: /_static/httpsvc/http_svc.py
   :language: python
   :linenos:
   :lines: 197-344


Request Handler
===============

.. literalinclude:: /_static/httpsvc/http_svc.py
   :language: python
   :linenos:
   :lines: 61-194


A simple servlet
****************

The servlet will be a simple *Hello World* writer, with an optional dependency
to write extra information.

Information service
===================

This service is provided by a component that will be manually instantiated.

.. literalinclude:: /_static/httpsvc/extra_info.py
   :language: python
   :linenos:

Hello world servlet
===================

.. literalinclude:: /_static/httpsvc/hello_servlet.py
   :language: python
   :linenos:


Run the server
**************

Now, it's to start the whole project :

.. literalinclude:: /_static/httpsvc/demo.py
   :language: python
   :linenos:
