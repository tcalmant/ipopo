#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining multiple classes and component factories for HTTP service tests

:author: Thomas Calmant
"""

from typing import Any, Dict, List, Optional

import pelix.http as http
from pelix.ipopo.decorators import ComponentFactory, Property, Provides

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

SIMPLE_SERVLET_FACTORY = "simple.servlet.factory"
MULTIPLE_SERVLET_FACTORY = "multiple.servlet.factory"

# ------------------------------------------------------------------------------


class SimpleServlet(http.Servlet):
    """
    A simple servlet implementation
    """

    def __init__(self, raiser: bool = False) -> None:
        """
        Sets up the servlet

        :param raiser: If True, the servlet will raise an exception on bound_to
        """
        self.raiser = raiser
        self.accept = True
        self.bound: List[str] = []
        self.unbound: List[str] = []

    def reset(self) -> None:
        """
        Resets the servlet data
        """
        del self.bound[:]
        del self.unbound[:]

    def accept_binding(self, path: str, params: Dict[str, Any]) -> bool:
        """
        Tests if the HTTP server can be accepted
        """
        return self.accept

    def bound_to(self, path: str, params: Dict[str, Any]) -> bool:
        """
        Servlet bound to a path
        """
        self.bound.append(path)

        if self.raiser:
            raise Exception("Some exception")

        return True

    def unbound_from(self, path: str, params: Dict[str, Any]) -> None:
        """
        Servlet unbound from a path
        """
        self.unbound.append(path)

        if self.raiser:
            raise Exception("Some exception")

        return None

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
        self._path: Optional[str] = None
        self._raiser = False

    def change(self, new_path: str) -> None:
        """
        Change the registration path
        """
        self._path = new_path
