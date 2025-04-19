#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Run RSA with etcd3-based discovery module and xmlrpc distribution module and export
samples.rsa.helloimpl_xmlrpc. NOTE:  For the etcd3 discovery to work, there must
be an etcd3 server/service running on localhost/2379 (default etcd3 port)

:author: Scott Lewis
:copyright: Copyright 2024, Scott Lewis
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2024 Scott Lewis

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

import pelix.framework as pelix
from pelix.ipopo.constants import use_ipopo

# ------------------------------------------------------------------------------
# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------
# etcd3 discovery hostname and port
ETCD_HOSTNAME = "localhost"
ETCD_PORT = 2379

# ------- Main constants for the sample
HTTP_HOSTNAME = "127.0.0.1"
HTTP_PORT = 8181

# ------------------------------------------------------------------------------
def connected_cb():
    print("Etcd3 connected!")
    
def main() -> None:

    import logging
    logging.basicConfig(level=logging.DEBUG)
    # Define the initial bundles
    bundles = (
        "pelix.ipopo.core",
        "pelix.shell.core",
        "pelix.shell.ipopo",
        "pelix.shell.console",
        # RSA implementation
        "pelix.rsa.remoteserviceadmin",
        # topology manager 
        "pelix.rsa.topologymanagers.basic",
        # etcd3 discovery  
        "pelix.rsa.providers.discovery.etcd3.discovery_etcd3",
        # HTTP Service
        "pelix.http.basic",
        # XML-RPC distribution provider (opt)
        "pelix.rsa.providers.distribution.xmlrpc",
        # RSA shell commands (opt)
        "pelix.rsa.shell",
    )

    # Use the utility method to create, run and delete the framework
    framework = pelix.create_framework(
        bundles,
        {
            "ecf.xmlrpc.server.hostname": HTTP_HOSTNAME,
        },
    )
    framework.start()
    # start httpservice, required by the xmlrpc distribution provider
    with use_ipopo(framework.get_bundle_context()) as ipopo:
        ipopo.instantiate(
            "pelix.http.service.basic.factory",
            "http-server",
            {"pelix.http.address": HTTP_HOSTNAME, "pelix.http.port": HTTP_PORT},
        )
    # start etcd3 discovery service client
    with use_ipopo(framework.get_bundle_context()) as ipopo:
        ipopo.instantiate(
            "etcd3-endpoint-discovery-factory",
            "etcd3-endpoint-discovery",
            {"etcd.hostname": ETCD_HOSTNAME, "etcd.port": ETCD_PORT, "etcd.connected_callback": connected_cb},
        )
    # install helloimpl_xmlrpc module, instantiate component and should result
    # in export via xmlrpc distribution provider and advertisement of endpoint
    # description via etcd3
    framework.get_bundle_context().install_bundle("samples.rsa.helloimpl_xmlrpc").start()

    try:
        framework.wait_for_stop()
    except KeyboardInterrupt:
        framework.stop()


if __name__ == "__main__":
    main()
