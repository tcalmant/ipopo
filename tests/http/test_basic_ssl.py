#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix basic HTTP service test module.

:author: Thomas Calmant
"""

import http.client as httplib
import logging
import shutil
import unittest
from typing import Any, Dict, Optional

import pelix.http as http
from pelix.framework import Framework, FrameworkFactory
from pelix.ipopo.constants import IPopoService
from tests.http.gen_cert import make_certs
from tests.http.utils import get_file, get_tmp_dir, install_bundle, install_ipopo, instantiate_server, kill_server

try:
    from ssl import SSLContext, create_default_context
except ImportError:
    raise unittest.SkipTest("SSLContext not supported")

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8043

PASSWORD = "test_password"

# ------------------------------------------------------------------------------


def get_https_code(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    uri: str = "/",
    method: str = "GET",
    headers: Optional[Dict[str, Any]] = None,
    content: Any = None,
) -> int:
    """
    Retrieves the result of an HTTP request

    :param host: Server host name
    :param port: Server port
    :param uri: Request URI
    :param method: Request HTTP method (GET, POST, ...)
    :param headers: Request headers
    :param content: POST request content
    :param content: POST request content
    :return: A status code
    """
    # Setup the certificate authority
    ctx = create_default_context()
    ctx.load_verify_locations(get_file("ca.crt"), get_file("ca.key"))

    # Don't check the host name, as it depends on the test machine
    ctx.check_hostname = False

    conn = httplib.HTTPSConnection(host, port, context=ctx)
    conn.connect()
    conn.request(method, uri, content, headers or {})
    result = conn.getresponse()
    result.read()
    conn.close()
    return result.status


# ------------------------------------------------------------------------------


class BasicHTTPSTest(unittest.TestCase):
    """
    Tests of the basic HTTPS service
    """

    framework: Framework
    ipopo: IPopoService

    http_bundle = "pelix.http.basic"
    http_factory: str = http.FACTORY_HTTP_BASIC
    instance_name: str = "test-https-service"

    @classmethod
    def setUpClass(cls) -> None:
        """
        Setup the certificates
        """
        make_certs(get_tmp_dir(), PASSWORD)

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Clears the certificates
        """
        shutil.rmtree(get_tmp_dir())
        FrameworkFactory.delete_framework()

    def setUp(self) -> None:
        """
        Sets up the test environment
        """
        # Start a framework
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

        # Install iPOPO
        self.ipopo = install_ipopo(self.framework)

        # Install HTTP service
        install_bundle(self.framework, self.http_bundle)

        # Install test bundle
        self.servlets = install_bundle(self.framework, "tests.http.servlets_bundle")

    def tearDown(self) -> None:
        """
        Cleans up the test environment
        """
        # Stop the framework
        FrameworkFactory.delete_framework()
        self.framework = None  # type: ignore

    def instantiate_server(
        self,
        cert_file: str | None = None,
        key_file: str | None = None,
        password: str | None = None,
        address: str | None = DEFAULT_HOST,
        port: int | None = DEFAULT_PORT,
    ) -> http.HTTPService:
        """
        Instantiates a basic server component
        """
        return instantiate_server(
            self.ipopo, self.http_factory, self.instance_name, address, port, cert_file, key_file, password
        )

    def kill_server(self) -> None:
        """
        Kills the server component
        """
        try:
            kill_server(self.ipopo, self.instance_name)
        except:
            logging.exception("Error while killing the server component")
            raise

    def testSimpleCertificate(self) -> None:
        """
        Tests the use of a certificate without password
        """
        self.instantiate_server(cert_file="server.crt", key_file="server.key")
        self.assertEqual(get_https_code(), 404, "Received something other than a 404")

    def testPasswordCertificate(self) -> None:
        """
        Tests the use of a certificate with a password
        """
        self.instantiate_server(cert_file="server_enc.crt", key_file="server_enc.key", password=PASSWORD)
        self.assertEqual(get_https_code(), 404, "Received something other than a 404")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
