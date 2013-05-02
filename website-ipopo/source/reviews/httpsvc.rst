.. HTTP Service tutorial

Basic HTTP Service
##################

Description
***********

The HTTP service is a basic servlet container, dispatching HTTP requests to
the handler registered for the given path.

A servlet can be a simple class or a component, registered programmatically to
the HTTP service, or a service registered in the Pelix framework and
automatically registered by the HTTP service.

Usage
*****

Installation
============

The basic implementation of the HTTP service is defined in ``pelix.http.basic``.
It is based on the HTTP server available in the standard Python library.
Future implementations might appear in the future Pelix implementations, based
on more robust requests handlers, e.g.
`Twisted <http://twistedmatrix.com/trac/>`_.


Configuration
=============

All HTTP services supports the following property:

+--------------------+---------------+-----------------------------------------+
| Property           | Default value | Description                             |
+====================+===============+=========================================+
| pelix.http.address | 0.0.0.0       | The address the HTTP server is bound to |
+--------------------+---------------+-----------------------------------------+
| pelix.http.port    | 8080          | The port the HTTP server is bound to    |
+--------------------+---------------+-----------------------------------------+


Instantiation
=============

The HTTP bundle defines a component factory depending on its implementation.
The basic HTTP service factory is ``pelix.http.service.basic.factory``.


Here is a snippet that starts a HTTP service that accepts local clients only on
port 9000:

.. code-block:: python
   :linenos:
   
   from pelix.framework import FrameworkFactory
   from pelix.ipopo.constants import get_ipopo_svc_ref
   
   # Start the framework
   framework = FrameworkFactory.get_framework()
   framework.start()
   context = framework.get_bundle_context()
   
   # Install & start iPOPO
   context.install_bundle('pelix.ipopo.core').start()
   
   # Install & start the basic HTTP service
   context.install_bundle('pelix.http.basic').start()
   
   # Instantiate a HTTP service component
   ipopo = get_ipopo_svc_ref(context)[1]
   ipopo.instantiate('pelix.http.service.basic.factory',
                     {
                         'pelix.http.address': 'localhost',
                         'pelix.http.port': 9000
                     }


Now, an HTTP server is listening on port 9000 and the HTTP service is ready
to handle requests.


Interface
=========

HTTP service
------------

The HTTP service provides the following interface:

+--------------------------+-------------------------------------------------+
| Method                   | Description                                     |
+==========================+=================================================+
| get_access()             | Retrieves the (host, port) tuple to access the  |
|                          | server                                          |
+--------------------------+-------------------------------------------------+
| get_hostname()           | Retrieves the server host name                  |
+--------------------------+-------------------------------------------------+
| get_servlet(path)        | Retrieves the servlet associated to the given   |
|                          | path                                            |
+--------------------------+-------------------------------------------------+
| register_servlet(path,   | Registers a servlet for the given path.         |
| servlet,parameters=None) | The given parameters will be used when calling  |
|                          | ``bound_to()``                                  |
+--------------------------+-------------------------------------------------+
| unregister(path,         | Unregisters the servlet associated to the given |
| servlet=None)            | path, or the servlet for all its paths.         |
+--------------------------+-------------------------------------------------+

Servlet service
---------------

To use the whiteboard pattern, a servlet can be registered as a service
providing the ``pelix.http.servlet`` specification.

It must also have a valid ``pelix.http.path`` property, or it will be ignored.


Servlet
-------

A servlet for the Pelix HTTP service has the following methods:

+-------------------------+---------------------------------------------+
| Method                  | Description                                 |
+=========================+=============================================+
| bound_to(path,          | Method called when the servlet is bound to  |
| parameters)             | a path. THe parameters are the one used to  |
|                         | call the ``register_servlet()`` method.     |
|                         | If it returns False or raises an Exception, |
|                         | the registration is aborted                 |
+-------------------------+---------------------------------------------+
| unbound_from(path,      | Same as ``bound_to()`` but called when the  |
| parameters)             | servlet is unbound from the path            |
+-------------------------+---------------------------------------------+
| do_*(request, response) | The name of this method depends on the HTTP |
|                         | request to handler, e.g. ``do_POST``,       |
|                         | ``do_GET``, etc. The parameters are HTTP    |
|                         | request and response helpers                |
+-------------------------+---------------------------------------------+


HTTP request
------------

The HTTP request helper wraps the calls to the ``BasicHTTPRequestHandler`` in
the basic implementation, and provides the following methods:

+----------------------+-----------------------------------------------+
| Method               | Description                                   |
+======================+===============================================+
| get_client_address() | Retrieves the address of the client           |
+----------------------+-----------------------------------------------+
| get_header(name,     | Retrieves the value of the given HTTP header  |
| default=None)        |                                               |
+----------------------+-----------------------------------------------+
| get_headers()        | Retrieves all HTTP headers                    |
+----------------------+-----------------------------------------------+
| get_path()           | Retrieves the request path (URI and query)    |
+----------------------+-----------------------------------------------+
| get_rfile()          | Retrieves the underlying input stream as file |
+----------------------+-----------------------------------------------+
| read_data()          | Reads the whole request body (POST, PUT, ...) |
+----------------------+-----------------------------------------------+


HTTP response
-------------

The HTTP response helper wraps the calls to the ``BasicHTTPRequestHandler`` in
the basic implementation, and provides the following methods:

+-----------------------------+------------------------------------------------+
| Method                      | Description                                    |
+=============================+================================================+
| set_response(code, message) | Sets the HTTP response code and message        |
+-----------------------------+------------------------------------------------+
| set_header(name, value)     | Sets the value of the given HTTP header        |
+-----------------------------+------------------------------------------------+
| end_headers()               | Ends the headers parts of the response:        |
|                             | ``set_header()`` can't be called anymore.      |
+-----------------------------+------------------------------------------------+
| get_wfile()                 | Retrieves the underlying output stream as file |
+-----------------------------+------------------------------------------------+
| send_content(http_code,     | Utility method to send a complete response     |
| content, mime_type,         | (code, headers and content)                    |
| http_message,               |                                                |
| content_length)             |                                                |
+-----------------------------+------------------------------------------------+
| write(data)                 | Writes some data on the output stream          |
+-----------------------------+------------------------------------------------+


How to write a servlet
**********************

This snippet shows how to write a component providing the servlet service:

.. code-block:: python
   :linenos:
   
   from pelix.ipopo.decorators import ComponentFactory, Property, Provides, \
     Requires, Validate, Invalidate, Unbind, Bind, Instantiate
   
   @ComponentFactory(name='simple-servlet-factory')
   @Instantiate('simple-servlet')
   @Provides(specifications='pelix.http.servlet')
   @Property('_path', 'pelix.http.path', "/servlet")
   class SimpleServletFactory(object):
       """
       Simple servlet factory
       """
       def __init__(self):
           self._path = None
       
       def bound_to(self, path, params):
           """
           Servlet bound to a path
           """
           self.bound.append(path)
           print('Bound to ' + path)
           return True

       def unbound_from(self, path, params):
           """
           Servlet unbound from a path
           """
           self.unbound.append(path)
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
`<http://localhost:9000/servlet>`_
