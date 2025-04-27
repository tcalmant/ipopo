#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix basic HTTP service test module.

:author: Thomas Calmant
"""

import http.client as httplib
import logging
import os
import shutil
import tempfile
import unittest
from typing import Any, Dict, Optional, cast

import pelix.http as http
from pelix.framework import Framework, FrameworkFactory
from pelix.ipopo.constants import IPopoService
from tests.http.gen_cert import make_certs
from tests.http.test_basic import install_bundle, install_ipopo

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
TMP_DIR = tempfile.mkdtemp(prefix="ipopo-tests-https")

# ------------------------------------------------------------------------------


def get_file(name: Optional[str]) -> Optional[str]:
    """
    Returns the path to the given certificate file

    :param name: File name
    :return: Full path to the file
    """
    if name and not os.path.exists(name):
        name = os.path.join(TMP_DIR, name)
    return name


def instantiate_server(
    ipopo_svc: IPopoService,
    cert_file: Optional[str],
    key_file: Optional[str],
    password: Optional[str] = None,
    address: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> http.HTTPService:
    """
    Instantiates a basic server component
    """
    cert_file = get_file(cert_file)
    key_file = get_file(key_file)

    return cast(
        http.HTTPService,
        ipopo_svc.instantiate(
            http.FACTORY_HTTP_BASIC,
            "test-https-service",
            {
                http.HTTP_SERVICE_ADDRESS: address,
                http.HTTP_SERVICE_PORT: port,
                http.HTTPS_CERT_FILE: cert_file,
                http.HTTPS_KEY_FILE: key_file,
                http.HTTPS_KEY_PASSWORD: password,
            },
        ),
    )


def kill_server(ipopo_svc: IPopoService) -> None:
    """
    Kills the basic server component
    """
    ipopo_svc.kill("test-https-service")


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

    @classmethod
    def setUpClass(cls) -> None:
        """
        Setup the certificates
        """
        make_certs(TMP_DIR, PASSWORD)

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Clears the certificates
        """
        shutil.rmtree(TMP_DIR)

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
        install_bundle(self.framework, "pelix.http.basic")

        # Install test bundle
        self.servlets = install_bundle(self.framework, "tests.http.servlets_bundle")

    def tearDown(self) -> None:
        """
        Cleans up the test environment
        """
        # Stop the framework
        FrameworkFactory.delete_framework()
        self.framework = None  # type: ignore

    def testSimpleCertificate(self) -> None:
        """
        Tests the use of a certificate without password
        """
        instantiate_server(self.ipopo, cert_file="server.crt", key_file="server.key")

        self.assertEqual(get_https_code(), 404, "Received something other than a 404")

    def testPasswordCertificate(self) -> None:
        """
        Tests the use of a certificate with a password
        """
        instantiate_server(
            self.ipopo, cert_file="server_enc.crt", key_file="server_enc.key", password=PASSWORD
        )

        self.assertEqual(get_https_code(), 404, "Received something other than a 404")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
