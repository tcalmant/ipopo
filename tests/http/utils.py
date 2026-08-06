#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Utility methods for Pelix HTTP services tests.

:author: Thomas Calmant
"""

import asyncio
import http.client as httplib
import pathlib
import tempfile
from types import ModuleType
from typing import Any, cast

from pelix import http
from pelix.framework import BundleContext, Framework
from pelix.ipopo.constants import IPopoService

DEFAULT_HOST = "localhost"

SIMPLE_SERVLET_FACTORY = "simple.servlet.factory"
ASYNC_SERVLET_FACTORY = "async.servlet.factory"
MULTIPLE_SERVLET_FACTORY = "multiple.servlet.factory"

TMP_DIR = pathlib.Path(tempfile.mkdtemp(prefix="ipopo-tests-http"))


def get_tmp_dir() -> pathlib.Path:
    """
    Returns the temporary directory used by the tests

    :return: The temporary directory
    """
    if not TMP_DIR.exists():
        TMP_DIR.mkdir(parents=True, exist_ok=True)
    return TMP_DIR


def get_file(name: str | None) -> str | None:
    """
    Returns the path to the given certificate file

    :param name: File name
    :return: Full path to the file
    """
    if not name:
        return None

    if not pathlib.Path(name).exists():
        name = str(get_tmp_dir() / name)
    return name


def install_bundle(framework: Framework, bundle_name: str) -> ModuleType:
    """
    Installs and starts the test bundle and returns its module

    :param framework: A Pelix framework instance
    :param bundle_name: A bundle name
    :return: The installed bundle Python module
    """
    context = framework.get_bundle_context()

    bundle = context.install_bundle(bundle_name)
    bundle.start()

    return bundle.get_module()


def install_ipopo(framework: Framework) -> IPopoService:
    """
    Installs and starts the iPOPO bundle. Returns the iPOPO service

    :param framework: A Pelix framework instance
    :return: The iPOPO service
    :raise Exception: The iPOPO service cannot be found
    """
    context = framework.get_bundle_context()
    assert isinstance(context, BundleContext)

    # Install & start the bundle
    bundle = context.install_bundle("pelix.ipopo.core")
    bundle.start()

    # Get the service
    ref = context.get_service_reference(IPopoService)
    if ref is None:
        raise Exception("iPOPO Service not found")

    return context.get_service(ref)


def instantiate_server(
    ipopo_svc: IPopoService,
    factory: str,
    name: str,
    address: str | None = None,
    port: int | None = None,
    cert_file: str | None = None,
    key_file: str | None = None,
    password: str | None = None,
) -> http.HTTPService:
    """
    Instantiates a basic server component
    """

    cert_file = get_file(cert_file)
    key_file = get_file(key_file)

    return cast(
        http.HTTPService,
        ipopo_svc.instantiate(
            factory,
            name,
            {
                "pelix.http.logger.level": "DEBUG",
                http.HTTP_SERVICE_ADDRESS: address,
                http.HTTP_SERVICE_PORT: port,
                http.HTTPS_CERT_FILE: cert_file,
                http.HTTPS_KEY_FILE: key_file,
                http.HTTPS_KEY_PASSWORD: password,
            },
        ),
    )


def kill_server(ipopo_svc: IPopoService, name: str) -> None:
    """
    Kills the basic server component
    """
    ipopo_svc.kill(name)


def async_test(f):
    """
    Decorator to run a test function in the event loop
    """

    def wrapper(*args, **kwargs):
        return asyncio.get_event_loop().run_until_complete(f(*args, **kwargs))

    return wrapper


def get_http_page(
    port: int,
    host: str = DEFAULT_HOST,
    uri: str = "/",
    method: str = "GET",
    headers: dict[str, Any] | None = None,
    content: Any = None,
) -> tuple[int, bytes]:
    """
    Retrieves the result of an HTTP request

    :param port: Server port
    :param host: Server host name
    :param uri: Request URI
    :param method: Request HTTP method (GET, POST, ...)
    :param headers: Request headers
    :param content: POST request content
    :return: A (code, content) tuple
    """
    conn = httplib.HTTPConnection(host, port)
    conn.connect()
    conn.request(method, uri, content, headers or {})
    result = conn.getresponse()
    data = result.read()
    conn.close()
    return result.status, data


def get_http_code(
    port: int,
    host: str = DEFAULT_HOST,
    uri: str = "/",
    method: str = "GET",
    headers: dict[str, Any] | None = None,
    content: Any = None,
) -> int:
    """
    Retrieves the status code of an HTTP request

    :param port: Server port
    :param host: Server host name
    :param uri: Request URI
    :param method: Request HTTP method (GET, POST, ...)
    :param headers: Request headers
    :param content: POST request content
    :return: A status code
    """
    return get_http_page(port, host, uri, method, headers, content)[0]


def ensure_get_servlet(
    http_svc: http.HTTPService, path: str
) -> tuple[http.Servlet, dict[str, Any], str, http.ServletType]:
    """
    Returns the servlet for the given path, or raises a KeyError if not found
    """
    found = http_svc.get_servlet(path)
    if found is None:
        raise KeyError(f"Servlet not found: {path}")
    return found


class TestServlet:
    """
    Common fields to all test servlets
    """

    # Do not consider this class as a test case
    __test__ = False

    def __init__(self, raiser: bool = False) -> None:
        """
        Sets up the servlet

        :param raiser: If True, the servlet will raise an exception on bound_to
        """
        self.raiser = raiser
        self.accept = True
        self.bound: list[str] = []
        self.unbound: list[str] = []

    def reset(self) -> None:
        """
        Resets the servlet data
        """
        del self.bound[:]
        del self.unbound[:]

    def accept_binding(self, path: str, params: dict[str, Any]) -> bool:
        """
        Tests if the HTTP server can be accepted
        """
        return self.accept

    def bound_to(self, path: str, params: dict[str, Any]) -> bool:
        """
        Servlet bound to a path
        """
        self.bound.append(path)

        if self.raiser:
            raise Exception("Some exception")

        return True

    def unbound_from(self, path: str, params: dict[str, Any]) -> None:
        """
        Servlet unbound from a path
        """
        self.unbound.append(path)

        if self.raiser:
            raise Exception("Some exception")

