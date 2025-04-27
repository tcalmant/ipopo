#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Tests remote services transports based on HTTPS

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0

..

    Copyright 2025 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import os
import shutil
import ssl
import tempfile
import threading
import unittest
from typing import Any, Iterable, Tuple

import pelix.http
import pelix.remote
from pelix.framework import Framework, create_framework
from pelix.ipopo.constants import use_ipopo
from tests.http.gen_cert import make_certs
from tests.http.test_basic import install_ipopo
from tests.http.test_basic_ssl import instantiate_server
from tests.remote.test_transports_http import SVC_SPEC, HttpTransportsTest, RemoteService

try:
    # Try to import modules
    import multiprocessing
    from multiprocessing import Process, Queue

    # IronPython fails when creating a queue
    Queue()

    # Trick to avoid pytest hanging
    multiprocessing.set_start_method("spawn", force=True)
except ImportError:
    # Some interpreters don't have support for multiprocessing
    raise unittest.SkipTest("Interpreter doesn't support multiprocessing")


# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def load_framework(
    transport: str, components: Iterable[Tuple[str, str]], start_server: bool = True
) -> Framework:
    """
    Starts a Pelix framework in the local process

    :param transport: Name of the transport bundle to install
    :param components: Tuples (factory, name) of instances to start
    """
    all_bundles = [
        "pelix.ipopo.core",
        "pelix.http.basic",
        "pelix.remote.dispatcher",
        "pelix.remote.registry",
        "pelix.remote.discovery.multicast",
        transport,
    ]

    # Start the framework
    framework = create_framework(all_bundles)
    framework.start()

    with use_ipopo(framework.get_bundle_context()) as ipopo:
        if start_server:
            # Start a HTTP service on a random port
            ipopo.instantiate(
                pelix.http.FACTORY_HTTP_BASIC,
                "http-server",
                {pelix.http.HTTP_SERVICE_ADDRESS: "0.0.0.0", pelix.http.HTTP_SERVICE_PORT: 0},
            )

        ipopo.instantiate(pelix.remote.FACTORY_REGISTRY_SERVLET, "dispatcher-servlet")

        # Start the multicast discovery
        ipopo.instantiate(pelix.remote.FACTORY_DISCOVERY_MULTICAST, "multicast-discovery")

        # Start other components
        for factory, name in components:
            ipopo.instantiate(factory, name)

    return framework


def export_framework(state_queue: Queue, transport: str, components: Iterable[Tuple[str, str]]) -> None:
    """
    Starts a Pelix framework, on the export side

    :param state_queue: Queue to store status
    :param transport: Name of the transport bundle to install
    :param components: Tuples (factory, name) of instances to start
    """
    tmp_dir = tempfile.mkdtemp(prefix="ipopo-tests-https")

    try:
        # Load the framework
        framework = load_framework(transport, components, False)
        context = framework.get_bundle_context()
        ipopo = install_ipopo(framework)

        # Prepare certificates
        make_certs(tmp_dir, None)

        # Setup the HTTPS server
        instantiate_server(
            ipopo,
            cert_file=os.path.join(tmp_dir, "server.crt"),
            key_file=os.path.join(tmp_dir, "server.key"),
            address="0.0.0.0",
            port=0,
        )

        # Register the exported service
        event = threading.Event()
        context.register_service(
            SVC_SPEC, RemoteService(state_queue, event), {pelix.remote.PROP_EXPORTED_INTERFACES: "*"}
        )

        # Send the ready state
        state_queue.put("ready")

        # Loop until the end message
        event.wait()

        # Stopping
        state_queue.put("stopping")
        framework.stop()
        framework.delete()
    except Exception as ex:
        state_queue.put("Error: {0}".format(ex))
    finally:
        shutil.rmtree(tmp_dir)


# ------------------------------------------------------------------------------


class HttpsTransportsTest(HttpTransportsTest):
    """
    Tests Pelix built-in Remote Services transports
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(HttpsTransportsTest, self).__init__(*args, **kwargs)
        self._load_framework = load_framework
        self._export_framework = export_framework

    def _run_test(
        self, transport_bundle: str, exporter_factory: str, importer_factory: str, test_kwargs: bool = True
    ) -> None:
        try:
            super(HttpsTransportsTest, self)._run_test(
                transport_bundle, exporter_factory, importer_factory, test_kwargs
            )
        except ssl.SSLError:
            # This should happen as the communication happens on a self-signed
            # certificate
            return


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
