.. _refcard_http_async:

Asynchronous HTTP Service
=========================

The HTTP asynchronous service is an enhanced version of the :ref:`HTTP service <refcard_http>`,
based on `aiohttp <https://docs.aiohttp.org/en/stable/>`_.
It supports both synchronous and asynchronous servlets, keeping compatibility
with the existing HTTP service.

.. important:: The HTTP asynchronous service implementation requires the
   `aiohttp` package to be installed.

   For example, use: ``pip install aiohttp`` to install it.


The asynchronous HTTP service adds support for asynchronous servlets, allowing
the implementation of long-running operations like Server Sent Events and Websockets.


Configuration properties
------------------------

The asynchronous HTTP service supports the same properties as the basic HTTP service:

================== ======= ====================================================
Property           Default Description
================== ======= ====================================================
pelix.http.address 0.0.0.0 The address the HTTP server is bound to
pelix.http.port    8080    The port the HTTP server is bound to
================== ======= ====================================================

Instantiation
-------------

The asynchronous HTTP service factory provided by the ``pelix.http.basic_async``
bundle is named ``pelix.http.service.async.factory``.

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
    context.install_bundle('pelix.http.basic_async').start()

    # Instantiate a HTTP service component
    with use_ipopo(context) as ipopo:
       ipopo.instantiate(
           'pelix.http.service.async.factory', 'http-server',
           {'pelix.http.address': 'localhost',
            'pelix.http.port': 9000})

This code starts an HTTP server which will be listening on port 9000 and the
HTTP service will be ready to handle requests.
As no servlet service has been registered, the server will only return 404
errors.


API
---

Asynchronous HTTP service
^^^^^^^^^^^^^^^^^^^^^^^^^

The asynchronous HTTP service provides the same :ref:`http_service_api`
interface as the synchronous service.

Synchronous Servlet service
^^^^^^^^^^^^^^^^^^^^^^^^^^^

This service is compatible with the synchronous servlets of the HTTP service.
See :ref:`refcard_http` for more information on the synchronous servlets.

Asynchronous Servlet service
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To use the whiteboard pattern, an asynchronous servlet can be registered as a
service providing the ``pelix.http.servlet.async`` specification.
It must also have a valid ``pelix.http.path.async`` property, or it will be ignored.

Like for synchronous servlets, the binding methods described below have a
``parameters`` argument, which represents a set of properties of the server,
given as a dictionary.
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
* ``http.async``: a boolean flag indicating if the servlet is asynchronous
  (True) or synchronous (False). This is set automatically by the HTTP service
  when registering the servlet.

An asynchronous servlet for the Pelix HTTP service has the following methods:

.. py:class:: pelix.http.AsyncServlet
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

   .. py:method:: do_async_XXX(request: ~pelix.http.AbstractAsyncHTTPServletRequest, response: ~pelix.http.AbstractAsyncHTTPServletResponse) -> None

      Each request is handled by the coroutine call ``do_async_XXX`` where ``XXX`` is
      the name of an HTTP method (``do_async_GET``, ``do_async_POST``, ``do_async_PUT``,
      ``do_async_HEAD``, ...).

      If it raises an exception, the server automatically sends an HTTP 500
      error page.
      In nominal behaviour, the method must use the ``response`` argument to
      send a reply to the client.

      :param request: A :class:`~pelix.http.AbstractAsyncHTTPServletRequest`
                        representation of the request
      :param response: The :class:`~pelix.http.AbstractAsyncHTTPServletResponse`
                        object to use to reply to the client

Asynchronous HTTP request
^^^^^^^^^^^^^^^^^^^^^^^^^

Each request method has a request helper argument, which implements the
:class:`~pelix.http.AbstractAsyncHTTPServletRequest` abstract class.

.. autoclass:: pelix.http.AbstractAsyncHTTPServletRequest
   :members: get_command, get_client_address, get_header, get_headers, get_path,
               get_prefix_path, get_sub_path, get_rfile, read_data

Asynchronous HTTP response
^^^^^^^^^^^^^^^^^^^^^^^^^^

Each request method also has a response helper argument, which implements the
:class:`~pelix.http.AbstractAsyncHTTPServletResponse` abstract class.

.. autoclass:: pelix.http.AbstractAsyncHTTPServletResponse
   :members: set_response, set_header, is_header_set, setup_sse, end_headers, get_wfile,
               write, send_sse, send_content

Write a servlet
---------------

This snippet shows how to write a component providing the servlet service:

.. code-block:: python

    from pelix.http import AsyncServlet, HTTP_SERVLET_ASYNC_PATH, \
         AbstractAsyncHTTPServletRequest, AbstractAsyncHTTPServletResponse
    from pelix.ipopo.decorators import ComponentFactory, Property, Provides, \
        Requires, Validate, Invalidate, Unbind, Bind, Instantiate

    @ComponentFactory(name='simple-async-servlet-factory')
    @Instantiate('simple-servlet')
    @Provides(AsyncServlet)
    @Property('_path', HTTP_SERVLET_ASYNC_PATH, "/servlet")
    class SimpleAsyncServletFactory:
      """
      Simple servlet factory
      """
      def __init__(self):
          self._path = None

      def bound_to(self, path, params):
          """
          Servlet bound to a path
          """
          print("Bound to", path)
          return True

      def unbound_from(self, path, params):
          """
          Servlet unbound from a path
          """
          print("Unbound from", path)
          return None

      async def do_async_GET(self,
            request: AbstractAsyncHTTPServletRequest,
            response: AbstractAsyncHTTPServletResponse):
          """
          Handle a GET
          """
          await response.send_content(200, "Hello, Async World!", mime_type="text/plain")


To test this snippet, install and start this bundle and the HTTP service bundle
in a framework, then open a browser to the servlet URL.
If you used the HTTP service instantiation sample, this URL should be
http://localhost:9000/servlet.

Server-Sent Events (SSE) Endpoint
---------------------------------

Server-Sent Events (SSE) allow servers to push updates to clients over HTTP and
are supported by the asynchronous HTTP service.

An SSE endpoint can be implemented by an asynchronous servlet in a
``do_async_XXX`` method (usually, ``do_async_GET``):

1. Call the :py:func:`~pelix.http.AbstractAsyncHTTPServletResponse.setup_sse` method to set up the response for SSE.
   By default, this method will fail if the client doesn't explicitly request SSE by setting the
   ``Accept: text/event-stream`` header.
   You can set the ``strict`` parameter to ``False`` to bypass this check.
2. Call the :py:func:`~pelix.http.AbstractAsyncHTTPServletResponse.end_headers` method to finalize the headers.
3. Use the :py:func:`~pelix.http.AbstractAsyncHTTPServletResponse.send_sse` method to send events to the client.

Here is an example of an SSE endpoint:

.. code-block:: python

    from pelix.http import AsyncServlet, HTTP_SERVLET_ASYNC_PATH, \
         AbstractAsyncHTTPServletRequest, AbstractAsyncHTTPServletResponse
    from pelix.ipopo.decorators import ComponentFactory, Provides, Property

    @ComponentFactory()
    @Provides(AsyncServlet)
    @Property("_path", HTTP_SERVLET_ASYNC_PATH, "/sse")
    class SSEServlet(AsyncServlet):
        async def do_async_GET(self, request: AbstractAsyncHTTPServletRequest, response: AbstractAsyncHTTPServletResponse):
            response.setup_sse()
            await response.end_headers()

            for i in range(5):
                await response.send_sse(f"Message {i}", event="update")
                await asyncio.sleep(1)


WebSocket Server Endpoints
--------------------------

Pelix also supports WebSocket server endpoints through the ``pelix.http.websocket.handler`` specification.
To create a WebSocket handler, inherit from the :py:class:`~pelix.http.AbstractWebSocketHandler` abstract class and implement the required methods.


.. autoclass:: pelix.http.AbstractWebSocketHandler
   :members: ws_accept, ws_open, ws_binary, ws_message, ws_close, ws_error

.. autoclass:: pelix.http.WebSocketSession
   :members: send_text, send_binary, close, get_client_address

Here is an example:

.. code-block:: python

    from pelix.http import AbstractWebSocketHandler, HTTP_WEBSOCKET_PATH, \
         AbstractAsyncHTTPServletRequest, WebSocketSession
    from pelix.ipopo.decorators import ComponentFactory, Provides, Property

    @ComponentFactory()
    @Provides(AbstractWebSocketHandler)
    @Property("_path", HTTP_WEBSOCKET_PATH, "/ws")
    class SampleWebSocketHandler(AbstractWebSocketHandler):
        async def ws_open(self, session: WebSocketSession, request: AbstractAsyncHTTPServletRequest):
            print("WebSocket connection opened")

        async def ws_message(self, session: WebSocketSession, message: str):
            print("Received message:", message)
            await session.send_text(f"Echo: {message}")

        async def ws_close(self, session: WebSocketSession, code: int, reason: str):
            print("WebSocket connection closed")
