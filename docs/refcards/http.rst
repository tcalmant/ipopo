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

All implementations of the HTTP service must support the following properties:

=============================== ======= ========================================
Property                        Default Description
=============================== ======= ========================================
pelix.http.address              0.0.0.0 The address the HTTP server is bound to
pelix.http.port                 8080    The port the HTTP server is bound to
pelix.http.debug                False   If set, error pages sent to the clients
                                        contain the stack trace of the error,
                                        and the 404 page lists the registered
                                        servlet paths
pelix.http.max_body_size        1048576 Maximum size, in bytes, of the body of a
                                        request. A request with a bigger body is
                                        answered with a 413 error code. A value
                                        lesser than or equal to 0 removes the
                                        limit
pelix.http.socket_timeout       60      Timeout, in seconds, of the sockets
                                        handling the requests. A client which
                                        takes longer to send its request gets a
                                        408 error code. A value lesser than or
                                        equal to 0 removes the timeout
pelix.http.case_sensitive_paths True    If set, servlet paths are matched
                                        case-sensitively, as URI paths are
                                        defined to be. Unset it to restore the
                                        folding of earlier releases
=============================== ======= ========================================

.. versionadded:: 3.2.2
   ``pelix.http.max_body_size`` and ``pelix.http.socket_timeout``.

   Before that release, the body of a request was read without any size limit,
   and a request without a ``Content-Length`` header blocked its handling
   thread until the client closed the connection.

.. versionadded:: 3.3.0
   ``pelix.http.case_sensitive_paths``.

.. note:: ``pelix.http.socket_timeout`` is only applied by the synchronous HTTP
   service.

   The asynchronous service accepts the property, as it is common to all the
   implementations, but leaves the timeouts of the connections to ``aiohttp``.

Request paths
-------------

Before a servlet is looked for, the path of a request is normalized: its query
string is removed, it is percent-decoded, its repeated slashes are collapsed
and its ``.`` and ``..`` segments are resolved.
A request whose path holds a control character, or resolves above the root, is
answered with a 400 error code and never reaches a servlet.

The same normalized path is used to find the servlet and to compute what
:meth:`~pelix.http.AbstractHTTPServletRequest.get_path` and
:meth:`~pelix.http.AbstractHTTPServletRequest.get_sub_path` return, so the
router and the servlet can never disagree about what was requested.

Servlet paths are matched **case-sensitively**: ``/admin`` and ``/Admin`` are
two different resources, as RFC 3986 defines them to be.

.. versionchanged:: 3.3.0
   Paths used to be matched after being lowered, and were neither decoded nor
   resolved. A servlet was given the original path while the server routed on
   the folded one, so a check made on the path a servlet received could be
   evaded by changing its case.

.. warning:: A decoded path segment never holds a separator, but it can hold
   anything else the client encoded.

   A servlet mapping a segment onto a file system, a database key or another
   name space still has to validate it. The server normalizes the structure of
   the path; it cannot know what a segment means to the servlet.

.. warning:: ``pelix.http.debug`` must be kept unset in production.

   A stack trace describes the server: the paths of its files, the packages it
   uses and the data it was handling. By default, the error page only gives an
   error ID, which allows to find the details of the error in the logs of the
   server.

   The same goes for the paths of the registered servlets: by default, the 404
   page doesn't list them, as they would tell any client what the server
   exposes.

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


.. _http_cors:

Cross-Origin Resource Sharing (CORS)
------------------------------------

A browser only lets a script read the response to a request sent to another
origin (scheme, host and port) if the server allows it, with the
``Access-Control-*`` headers defined by the
`CORS protocol <https://fetch.spec.whatwg.org/#http-cors-protocol>`_.

By default, the HTTP services don't send any of those headers: a script loaded
from another origin can't read their responses. Both the basic and the
asynchronous HTTP services apply a CORS policy when one is given, either for
the whole server or per servlet:

* **for the whole server**, with a :class:`CorsHandler` service. The
  ``pelix.http.cors`` bundle provides the ``pelix.http.cors.factory`` component
  factory (:data:`FACTORY_HTTP_CORS`), configured with the properties below.
  The HTTP services bind the best ranked CORS handler service, if any;
* **per servlet**, with the same properties set on the servlet service, or in
  the parameters of :meth:`~HTTPService.register_servlet`. A servlet declares
  its own policy by setting ``pelix.http.cors.origins``: its policy then
  replaces the one of the CORS handler service for the requests it handles.

=============================== ======= ========================================
Property                        Default Description
=============================== ======= ========================================
pelix.http.cors.origins         (none)  Origins allowed to read the responses.
                                        ``*`` allows any origin, an empty list
                                        none
pelix.http.cors.methods         (all)   Methods allowed in cross-origin
                                        requests. If not set, the method
                                        announced by a preflight is allowed
pelix.http.cors.headers         (all)   Request headers allowed in cross-origin
                                        requests. If not set, the headers
                                        announced by a preflight are allowed
pelix.http.cors.expose_headers  (none)  Response headers a script can read, in
                                        addition to the CORS-safelisted ones
pelix.http.cors.credentials     False   If set, requests can carry credentials
                                        (cookies, ``Authorization``, ...)
pelix.http.cors.max_age         (none)  Time, in seconds, a browser can cache
                                        the result of a preflight
=============================== ======= ========================================

List properties accept a list of strings or a comma-separated string.

The HTTP services then behave as follows, for requests carrying an ``Origin``
header on a path covered by a policy:

* a **preflight request** (an ``OPTIONS`` request with an
  ``Access-Control-Request-Method`` header) is answered by the HTTP service
  itself, even if no servlet is registered on its path: ``204`` with the
  ``Access-Control-Allow-*`` headers if the policy accepts it, else ``403``.
  The ``do_OPTIONS`` method of the servlet is not called;
* the response to **any other request** gets the ``Access-Control-Allow-Origin``
  header (and the other ones of the policy) if the policy accepts its origin,
  including the error pages (400, 404, 413, 500, ...) and the WebSocket
  handshakes. A header the servlet set itself is kept as is.

A refused origin doesn't prevent the request from being handled: CORS is
enforced by the browser, which won't let the script read the response. It
doesn't protect the server against a client which ignores it.

When credentials are allowed, the origin of the request is always sent back
instead of ``*``, as browsers refuse credentials with a wildcard. A
``Vary: Origin`` header is then added so that caches don't mix the responses
sent to different origins.

.. warning:: Allowing credentials lets the allowed origins send requests on
   behalf of the users of the server, with their cookies. Only allow the origins
   you trust.

For example, to allow a web application served from another host to call the
servlets of an HTTP service:

.. code-block:: python

    context.install_bundle("pelix.http.cors").start()

    with use_ipopo(context) as ipopo:
        ipopo.instantiate(
            "pelix.http.cors.factory",
            "cors-policy",
            {
                "pelix.http.cors.origins": ["https://app.example.com"],
                "pelix.http.cors.headers": ["Content-Type", "Authorization"],
                "pelix.http.cors.credentials": True,
                "pelix.http.cors.max_age": 600,
            },
        )

A :class:`CorsHandler` service can also be written to give a different policy
to different paths, as each of its methods is given the path of the request:

.. autoclass:: CorsHandler
   :members:

.. versionadded:: 3.2.3

API
---

.. _http_service_api:

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
* ``http.async``: a boolean flag indicating if the servlet is asynchronous
  (True) or synchronous (False). In the case of the basic HTTP service,
  this is always False, as it only supports synchronous servlets.

A servlet can, on the other hand, configure the way the HTTP service handles
the requests it will be given, with the following entries:

* ``pelix.http.max_body_size``: the maximum size, in bytes, of the body of a
  request handled by this servlet. It overrides the property of the same name
  of the HTTP service, in both directions: a servlet can accept bodies bigger
  than the other ones, which is useful to carry RPC payloads, or restrict
  itself to smaller ones. A value lesser than or equal to 0 removes the limit.
* ``pelix.http.cors.origins`` and the other ``pelix.http.cors.*`` entries: the
  CORS policy of the servlet, which replaces the one of the CORS handler
  service (see :ref:`http_cors`).

They can be given either as properties of the servlet service, next to
``pelix.http.path``, or in the ``parameters`` argument of
:meth:`~HTTPService.register_servlet`.

.. versionadded:: 3.2.2
   The ``pelix.http.max_body_size`` entry.

.. versionadded:: 3.2.3
   The ``pelix.http.cors.*`` entries.

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
