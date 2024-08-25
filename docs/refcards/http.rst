.. _refcard_http:
.. module:: pelix.http

HTTP Service
============

The HTTP service is a basic servlet container, dispatching HTTP requests to the
handler registered for the given path.
A servlet can be a simple class or a component, registered programmatically to
the HTTP service, or a service registered in the Pelix framework and
automatically registered by the HTTP service.

.. note:: Even if it borrows the concept of *servlets* from Java, the Pelix
   HTTP service doesn't follow the OSGi specification.
   The latter inherits a lot from the existing Java APIs, while this is an
   uncommon way to work in Python.

The basic implementation of the HTTP service is defined in ``pelix.http.basic``.
It is based on the HTTP server available in the standard Python library
(see `http.server <https://docs.python.org/3/library/http.server.html>`_).
Future implementations might appear in the future Pelix implementations, based
on more robust requests handlers.


Configuration properties
------------------------

All implementations of the HTTP service must support the following property:

================== ======= ====================================================
Property           Default Description
================== ======= ====================================================
pelix.http.address 0.0.0.0 The address the HTTP server is bound to
pelix.http.port    8080    The port the HTTP server is bound to
================== ======= ====================================================

Instantiation
-------------

The HTTP bundle defines a component factory which name is
implementation-dependent.
The HTTP service factory provided by Pelix/iPOPO is
``pelix.http.service.basic.factory``.

Here is a snippet that starts a HTTP server component, named ``http-server``,
which only accepts local clients on port 9000:

.. code-block:: python

    from pelix.framework import FrameworkFactory
    from pelix.ipopo.constants import use_ipopo

    # Start the framework
    framework = FrameworkFactory.get_framework()
    framework.start()
    context = framework.get_bundle_context()

    # Install & start iPOPO
    context.install_bundle('pelix.ipopo.core').start()

    # Install & start the basic HTTP service
    context.install_bundle('pelix.http.basic').start()

    # Instantiate a HTTP service component
    with use_ipopo(context) as ipopo:
       ipopo.instantiate(
           'pelix.http.service.basic.factory', 'http-server',
           {'pelix.http.address': 'localhost',
            'pelix.http.port': 9000})

This code starts an HTTP server which will be listening on port 9000 and the
HTTP service will be ready to handle requests.
As no servlet service has been registered, the server will only return 404
errors.


API
---

HTTP service
^^^^^^^^^^^^

The HTTP service provides the following interface:

.. autoclass:: HTTPService
   :members: get_access, get_hostname, is_https, get_registered_paths,
             get_servlet, register_servlet, unregister

The service also provides two utility methods to ease the display of error
pages:

.. autoclass:: HTTPService
   :noindex:
   :members: make_not_found_page, make_exception_page


Servlet service
^^^^^^^^^^^^^^^

To use the whiteboard pattern, a servlet can be registered as a service
providing the ``pelix.http.servlet`` specification.
It must also have a valid ``pelix.http.path`` property, or it will be ignored.

The binding methods described below have a ``parameters`` argument, which
represents a set of properties of the server, given as a dictionary.
Some parameters can also be given when using the
:meth:`~HTTPService.register_servlet` method, with the ``parameters`` argument.

In any case, the following entries must be set by all implementations of the
HTTP service and can't be overridden when register a servlet.
Note that their content and liability is implementation-dependent:

* ``http.address``: the binding address (*str*) of the HTTP server;
* ``http.port``: the real listening port (*int*) of the HTTP server;
* ``http.https``: a boolean flag indicating if the server is listening
  to HTTP (False) or HTTPS (True) requests;
* ``http.name``: the name (*str*) of the server. If the server is an iPOPO
  component, it should be the instance name;
* ``http.extra``: an implementation dependent set of properties.


A servlet for the Pelix HTTP service has the following methods:

.. py:class:: pelix.http.Servlet
   :module:

   These are the methods that the HTTP service can call in a servlet. Note that
   it is not necessary to implement them all: the service has a default
   behaviour for missing methods.

   .. py:method:: accept_binding(path: str, parameters: Dict[str, Any]) -> bool | None

      This method is called before trying to bind the servlet.
      If it returns False, the servlet won't be bound to the server.
      This allows a servlet service to be bound to a specific server.

      If this method doesn't exist or returns None or anything else but False,
      the calling HTTP service will consider that the servlet accepts to be
      bound to it.

      :param str path: The path of the servlet in the server
      :param dict parameters: The parameters of the server

   .. py:method:: bound_to(path: str, parameters: Dict[str, Any]) -> bool | None

      This method is called when the servlet is bound to a path.
      If it returns False or raises an Exception, the registration is aborted.

      :param str path: The path of the servlet in the server
      :param dict parameters: The parameters of the server

   .. py:method:: unbound_from(path: str, parameters: Dict[str, Any]) -> None

      This method is called when the servlet is bound to a path.
      The parameters are the ones given in :meth:`~HttpServlet.accept_binding`
      and :meth:`~HttpServlet.bound_to`.

      :param str path: The path of the servlet in the server
      :param dict parameters: The parameters of the server

   .. py:method:: do_XXX(request: ~pelix.http.AbstractHTTPServletRequest, response: ~pelix.http.AbstractHTTPServletResponse) -> None

      Each request is handled by the method call ``do_XXX`` where ``XXX`` is
      the name of an HTTP method (``do_GET``, ``do_POST``, ``do_PUT``,
      ``do_HEAD``, ...).

      If it raises an exception, the server automatically sends an HTTP 500
      error page.
      In nominal behaviour, the method must use the ``response`` argument to
      send a reply to the client.

      :param request: A :class:`~pelix.http.AbstractHTTPServletRequest`
                      representation of the request
      :param response: The :class:`~pelix.http.AbstractHTTPServletResponse`
                       object to use to reply to the client

HTTP request
^^^^^^^^^^^^

Each request method has a request helper argument, which implements the
:class:`~pelix.http.AbstractHTTPServletRequest` abstract class.

.. autoclass:: pelix.http.AbstractHTTPServletRequest
   :members: get_command, get_client_address, get_header, get_headers, get_path,
                 get_prefix_path, get_sub_path, get_rfile, read_data

HTTP response
^^^^^^^^^^^^^

Each request method also has a response helper argument, which implements the
:class:`~pelix.http.AbstractHTTPServletResponse` abstract class.

.. autoclass:: pelix.http.AbstractHTTPServletResponse
   :members: set_response, set_header, is_header_set, end_headers, get_wfile,
                 write, send_content

Write a servlet
---------------

This snippet shows how to write a component providing the servlet service:

.. code-block:: python

    from pelix.ipopo.decorators import ComponentFactory, Property, Provides, \
        Requires, Validate, Invalidate, Unbind, Bind, Instantiate

    @ComponentFactory(name='simple-servlet-factory')
    @Instantiate('simple-servlet')
    @Provides(specifications='pelix.http.servlet')
    @Property('_path', 'pelix.http.path', "/servlet")
    class SimpleServletFactory:
      """
      Simple servlet factory
      """
      def __init__(self):
          self._path = None

      def bound_to(self, path, params):
          """
          Servlet bound to a path
          """
          print('Bound to ' + path)
          return True

      def unbound_from(self, path, params):
          """
          Servlet unbound from a path
          """
          print('Unbound from ' + path)
          return None

      def do_GET(self, request, response):
          """
          Handle a GET
          """
          content = """<html>
    <head>
    <title>Test SimpleServlet</title>
    </head>
    <body>
    <ul>
    <li>Client address: {clt_addr[0]}</li>
    <li>Client port: {clt_addr[1]}</li>
    <li>Host: {host}</li>
    <li>Keys: {keys}</li>
    </ul>
    </body>
    </html>""".format(clt_addr=request.get_client_address(),
                    host=request.get_header('host', 0),
                    keys=request.get_headers().keys())

          response.send_content(200, content)

To test this snippet, install and start this bundle and the HTTP service bundle
in a framework, then open a browser to the servlet URL.
If you used the HTTP service instantiation sample, this URL should be
http://localhost:9000/servlet.
