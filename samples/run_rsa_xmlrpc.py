#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Run RSA with etcd-based discovery module

:author: Scott Lewis
:copyright: Copyright 2020, Scott Lewis
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2020 Scott Lewis

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
# ------- Main constants for the sample
HTTP_HOSTNAME = "127.0.0.1"
HTTP_PORT = 8181

# ------------------------------------------------------------------------------


def main() -> None:
    # Set the initial bundles
    bundles = (
        "pelix.ipopo.core",
        "pelix.shell.core",
        "pelix.shell.ipopo",
        "pelix.shell.console",
        # RSA implementation
        "pelix.rsa.remoteserviceadmin",
        # HTTP Service
        "pelix.http.basic",
        # XML-RPC distribution provider (opt)
        "pelix.rsa.providers.distribution.xmlrpc",
        # Basic topology manager (opt)
        "pelix.rsa.topologymanagers.basic",
        # RSA shell commands (opt)
        "pelix.rsa.shell",
        # Example helloconsumer.  Only uses remote proxies
        "samples.rsa.helloconsumer_xmlrpc",
    )

    # Use the utility method to create, run and delete the framework
    framework = pelix.create_framework(
        bundles, {"ecf.xmlrpc.server.hostname": HTTP_HOSTNAME}
    )
    framework.start()

    from pelix.rsa.topologymanagers.basic import instantiate_basic_topology_manager
    instantiate_basic_topology_manager(framework.get_bundle_context())
    
    with use_ipopo(framework.get_bundle_context()) as ipopo:
        ipopo.instantiate(
            "pelix.http.service.basic.factory",
            "http-server",
            {"pelix.http.address": HTTP_HOSTNAME, "pelix.http.port": HTTP_PORT},
        )
    try:
        framework.wait_for_stop()
    except KeyboardInterrupt:
        framework.stop()


if __name__ == "__main__":
    main()
