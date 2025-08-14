#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Utility methods for Pelix HTTP services tests.

:author: Thomas Calmant
"""


import pathlib
import tempfile
from types import ModuleType
from typing import cast

import pelix.http as http
from pelix.framework import BundleContext, Framework
from pelix.ipopo.constants import IPopoService


TMP_DIR = pathlib.Path(tempfile.mkdtemp(prefix="ipopo-tests-http"))


def get_file(name: str | None) -> str | None:
    """
    Returns the path to the given certificate file

    :param name: File name
    :return: Full path to the file
    """
    if not name:
        return None

    if not pathlib.Path(name).exists():
        name = str(TMP_DIR / name)
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
