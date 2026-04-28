#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining multiple classes and component factories for HTTP service tests

:author: Thomas Calmant
"""

import pelix.http as http
from pelix.ipopo.decorators import ComponentFactory, Property, Provides
from tests.http.utils import ASYNC_SERVLET_FACTORY, SIMPLE_SERVLET_FACTORY, TestServlet

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class SimpleServlet(http.Servlet, TestServlet):
    """
    A simple servlet implementation
    """

    def __init__(self, raiser: bool = False) -> None:
        """
        Sets up the servlet

        :param raiser: If True, the servlet will raise an exception on bound_to
        """
        TestServlet.__init__(self, raiser)

    def do_GET(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
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
</html>""".format(
            clt_addr=request.get_client_address(),
            host=request.get_header("host", 0),
            keys=request.get_headers().keys(),
        )

        response.send_content(200, content)

    def do_POST(
        self, request: http.AbstractHTTPServletRequest, response: http.AbstractHTTPServletResponse
    ) -> None:
        """
        Handle a GET
        """
        response.send_content(201, "Success")


# ------------------------------------------------------------------------------


class AsyncSimpleServlet(http.AsyncServlet, TestServlet):
    """
    A simple asynchronous servlet implementation
    """

    def __init__(self, raiser: bool = False) -> None:
        """
        Sets up the servlet

        :param raiser: If True, the servlet will raise an exception on bound_to
        """
        TestServlet.__init__(self, raiser)

    async def do_async_GET(
        self, request: http.AbstractAsyncHTTPServletRequest, response: http.AbstractAsyncHTTPServletResponse
    ) -> None:
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
</html>""".format(
            clt_addr=request.get_client_address(),
            host=await request.get_header("host", 0),
            keys=(await request.get_headers()).keys(),
        )

        await response.send_content(200, content)

    async def do_async_POST(
        self, request: http.AbstractAsyncHTTPServletRequest, response: http.AbstractAsyncHTTPServletResponse
    ) -> None:
        """
        Handle a GET
        """
        await response.send_content(201, "Success")


# ------------------------------------------------------------------------------


@ComponentFactory(name=SIMPLE_SERVLET_FACTORY)
@Provides(specifications=http.Servlet)
@Property("_path", http.HTTP_SERVLET_PATH, "/simple")
@Property("_raiser", "raiser", False)
class SimpleServletFactory(SimpleServlet):
    """
    Simple servlet factory (same as SimpleServlet)
    """

    def __init__(self) -> None:
        """
        Set up the component
        """
        SimpleServlet.__init__(self, False)
        self._path: str | None = None
        self._raiser = False

    def change(self, new_path: str) -> None:
        """
        Change the registration path
        """
        self._path = new_path


@ComponentFactory(name=ASYNC_SERVLET_FACTORY)
@Provides(specifications=http.AsyncServlet)
@Property("_path", http.HTTP_SERVLET_ASYNC_PATH, "/async")
@Property("_raiser", "raiser", False)
class AsyncServletFactory(AsyncSimpleServlet):
    """
    Simple servlet factory (same as SimpleServlet)
    """

    def __init__(self) -> None:
        """
        Set up the component
        """
        AsyncSimpleServlet.__init__(self, False)
        self._path: str | None = None
        self._raiser = False

    def change(self, new_path: str) -> None:
        """
        Change the registration path
        """
        self._path = new_path
