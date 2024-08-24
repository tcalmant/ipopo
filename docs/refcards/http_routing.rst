.. _refcard_http_routing:
.. module:: pelix.http.routing

HTTP Routing utilities
######################

The ``pelix.http.routing`` module provides a utility class and a set of
decorators to ease the development of REST-like servlets.

Decorators
==========

.. important:: A servlet which uses the utility decorators **must** inherit
   from the ``pelix.http.routing.RestDispatcher`` class.

The ``pelix.http.routing.RestDispatcher`` class handles all ``do_*`` methods
and calls the corresponding decorated methods in the child class.

The child class can declare as many methods as necessary, with any name
(public, protected or private) and decorate them with the following decorators.
Note that a method can be decorated multiple times.

.. autoclass:: Http
   :members:

.. autoclass:: HttpGet
   :members:
   :show-inheritance:

.. autoclass:: HttpPost
   :members:
   :show-inheritance:

.. autoclass:: HttpPut
   :members:
   :show-inheritance:

.. autoclass:: HttpHead
   :members:
   :show-inheritance:

.. autoclass:: HttpDelete
   :members:
   :show-inheritance:


The decorated methods muse have the following signature:

.. py:method:: decorated_method(request, response, **kwargs)
   :module:

   Called by the dispatcher to handle a request.

   The keyword arguments must have the same name as the ones given in the URL
   pattern in the decorators.

   :param request: An :class:`~pelix.http.AbstractHTTPServletRequest` object
   :param response: An :class:`~pelix.http.AbstractHTTPServletResponse` object

Supported types
===============

Each argument in the URL can be automatically converted to the requested type.
If the conversion fails, an error 500 is automatically sent back to the client.

====== ========================================================================
Type   Description
====== ========================================================================
string Simple string used as is. The string can't contain a slash (``/``)
int    The argument is converted to an integer. The input must be of base 10. Floats are rejected.
float  The argument is converted to a float. The input must be of base 10.
path   A string representing a path, containing slashes.
uuid   The argument is converted to a ``uuid.UUID`` class.
====== ========================================================================

Multiple arguments can be given at a time, but can only be of one type.

Sample
======

.. code-block:: python

   from pelix.ipopo.decorators import ComponentFactory, Provides, Property, \
      Instantiate
   from pelix.http import HTTP_SERVLET, HTTP_SERVLET_PATH
   from pelix.http.routing import RestDispatcher, HttpGet, HttpPost, HttpPut

   @ComponentFactory()
   @Provides(HTTP_SERVLET)
   @Property('_path', HTTP_SERVLET_PATH, '/api/v0')
   @Instantiate("some-servlet")
   class SomeServlet(RestDispatcher):
      @HttpGet("/list")
      def list_elements(self, request, response):
         response.send_content(200, "<p>The list</p>")

      @HttpPost("/form/<form_id:uuid>")
      def handle_form(self, request, response, form_id):
         response.send_content(200, f"<p>Handled {form_id}</p>")

      @HttpPut("/upload/<some_id:int>/<filename:path>")
      @HttpPut("/upload/<filename:path>")
      def handle_upload(self, request, response, some_id=None, filename=None):
         response.send_content(200, f"<p>Handled {some_id} : {filename}</p>")
