#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Test package for iPOPO

:author: Thomas Calmant
"""

# iPOPO
from pelix.ipopo.constants import get_ipopo_svc_ref

# ------------------------------------------------------------------------------


def install_bundle(framework, bundle_name="tests.ipopo.ipopo_bundle"):
    """
    Installs and starts the test bundle and returns its module

    @param framework: A Pelix framework instance
    @param bundle_name: A bundle name
    @return: The installed bundle Python module
    """
    context = framework.get_bundle_context()

    bundle = context.install_bundle(bundle_name)
    bundle.start()

    return bundle.get_module()


def install_ipopo(framework):
    """
    Installs and starts the iPOPO bundle. Returns the iPOPO service

    @param framework: A Pelix framework instance
    @return: The iPOPO service
    @raise Exception: The iPOPO service cannot be found
    """
    # Install & start the bundle
    install_bundle(framework, "pelix.ipopo.core")

    # Get the service
    service = get_ipopo_svc_ref(framework.get_bundle_context())
    if service is None:
        raise Exception("iPOPO Service not found")

    return service[1]
