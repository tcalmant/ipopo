#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Run RSA with etcd-based discovery module

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0
:version: 0.8.1

..

    Copyright 2018 Scott Lewis

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""
# ------------------------------------------------------------------------------
# Standard logging
import logging
_logger = logging.getLogger(__name__)
# ------------------------------------------------------------------------------
# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)
# Documentation strings format
__docformat__ = "restructuredtext en"
# ------------------------------------------------------------------------------
import pelix.framework as pelix
from pelix.ipopo.constants import use_ipopo

# ------- Main constants
# Httpservice config
HTTP_HOSTNAME = '127.0.0.1'
HTTP_PORT = 8181

ETCD_HOSTNAME = 'disco.ecf-project.org'

# ------------------------------------------------------------------------------


def main():
    # Set the initial bundles
    bundles = ['pelix.ipopo.core',
               'pelix.shell.core',
               'pelix.shell.ipopo',
               'pelix.shell.console',
               'pelix.rsa.remoteserviceadmin',  # RSA implementation
               'pelix.http.basic',  # httpservice
               # xmlrpc distribution provider (opt)
               'pelix.rsa.providers.distribution.xmlrpc',
               # etcd discovery provider (opt)
               'pelix.rsa.providers.discovery.discovery_etcd',
               # basic topology manager (opt)
               'pelix.rsa.topologymanagers.basic',
               'pelix.rsa.shell',  # RSA shell commands (opt)
               'samples.rsa.helloconsumer_xmlrpc']  # Example helloconsumer.  Only uses remote proxies

    # Use the utility method to create, run and delete the framework
    framework = pelix.create_framework(
        bundles, {'etcd.hostname': ETCD_HOSTNAME, 'ecf.xmlrpc.server.hostname': HTTP_HOSTNAME})
    framework.start()

    with use_ipopo(framework.get_bundle_context()) as ipopo:
        ipopo.instantiate(
            'pelix.http.service.basic.factory', 'http-server',
            {'pelix.http.address': HTTP_HOSTNAME,
             'pelix.http.port': HTTP_PORT})
    try:
        framework.wait_for_stop()
    except KeyboardInterrupt:
        framework.stop()


if __name__ == '__main__':
    main()
