#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Runs the framework corresponding to the iPOPO Remote Services server.

Usage: run_remote.py [-h] [-s] [-p HTTP_PORT] [-d [DISCOVERY [DISCOVERY ...]]]
                     [-t [TRANSPORT [TRANSPORT ...]]]

* -s: Run in "provider mode", the framework provides a remote service. If not
  given, the framework will consume the remote services it finds

* -p: Force the HTTP server port (default: use a random one)

* -d: Select the discovery protocol(s) to use (default: multicast)
  Available protocols: multicast, mdns

* -t: Select the transport protocol(s) to use (default: jsonrpc)
  Available protocols: jsonrpc, jabsorbrpc

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 0.0.1
:status: Alpha

..

    Copyright 2014 isandlaTech

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
# Module version
__version_info__ = (0, 0, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix
from pelix.ipopo.constants import use_waiting_list
import pelix.framework
import pelix.remote as rs

# Standard library
import argparse
import logging
import sys

# ------------------------------------------------------------------------------

class InstallUtils(object):
    """
    Utility class to install services and instantiate components in a framework
    """
    def __init__(self, context):
        """
        Sets up the utility class
        """
        self.context = context

    def discovery_multicast(self):
        """
        Installs the multicast discovery bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle('pelix.remote.discovery.multicast').start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_DISCOVERY_MULTICAST,
                      "pelix-discovery-multicast")


    def discovery_mdns(self):
        """
        Installs the mDNS discovery bundles and instantiates components
        """
        # Remove Zeroconf debug output
        logging.getLogger("zeroconf").setLevel(logging.WARNING)

        # Install the bundle
        self.context.install_bundle('pelix.remote.discovery.mdns').start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_DISCOVERY_ZEROCONF,
                      "pelix-discovery-zeroconf")


    def discovery_mqtt(self):
        """
        Installs the MQTT discovery bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle('pelix.remote.discovery.mqtt').start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_DISCOVERY_MQTT, "pelix-discovery-mqtt",
                      {"application.id": "sample.rs",
                       "mqtt.host": "127.0.0.1"})


    def transport_jsonrpc(self):
        """
        Installs the JSON-RPC transport bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle('pelix.remote.json_rpc').start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_TRANSPORT_JSONRPC_EXPORTER,
                      "pelix-jsonrpc-exporter")
            ipopo.add(rs.FACTORY_TRANSPORT_JSONRPC_IMPORTER,
                      "pelix-jsonrpc-importer")


    def transport_jabsorbrpc(self):
        """
        Installs the JABSORB-RPC transport bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle('pelix.remote.transport.jabsorb_rpc') \
                                                                        .start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_TRANSPORT_JABSORBRPC_EXPORTER,
                      "pelix-jabsorbrpc-exporter")
            ipopo.add(rs.FACTORY_TRANSPORT_JABSORBRPC_IMPORTER,
                      "pelix-jabsorbrpc-importer")


    def transport_mqttrpc(self):
        """
        Installs the MQTT-RPC transport bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle('pelix.remote.transport.mqtt_rpc').start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_TRANSPORT_MQTTRPC_EXPORTER,
                      "pelix-mqttrpc-exporter",
                      {"mqtt.host": "127.0.0.1"})
            ipopo.add(rs.FACTORY_TRANSPORT_MQTTRPC_IMPORTER,
                      "pelix-mqttrpc-importer",
                      {"mqtt.host": "127.0.0.1"})


    def transport_xmlrpc(self):
        """
        Installs the XML-RPC transport bundles and instantiates components
        """
        # Install the bundle
        self.context.install_bundle('pelix.remote.xml_rpc').start()

        with use_waiting_list(self.context) as ipopo:
            # Instantiate the discovery
            ipopo.add(rs.FACTORY_TRANSPORT_XMLRPC_EXPORTER,
                      "pelix-xmlrpc-exporter")
            ipopo.add(rs.FACTORY_TRANSPORT_XMLRPC_IMPORTER,
                      "pelix-xmlrpc-importer")

# ------------------------------------------------------------------------------

def main(is_server, discoveries, transports, http_port=0):
    """
    Runs the framework

    :param is_server: If True, starts the provider bundle, else the consumer one
    :param discoveries: List of ('multicast' or 'mdns')
    :param transports: List of ('jsonrpc' or 'jabsorbrpc')
    :param http_port: Port the HTTP server must listen to
    """
    # Create the framework
    framework = pelix.framework.create_framework((# iPOPO
                                                  'pelix.ipopo.core',
                                                  'pelix.ipopo.waiting',

                                                  # Shell
                                                  'pelix.shell.core',
                                                  'pelix.shell.ipopo',
                                                  'pelix.shell.console',

                                                  # HTTP Service
                                                  "pelix.http.basic",

                                                  # Remote Services (core)
                                                  'pelix.remote.dispatcher',
                                                  'pelix.remote.registry'))

    # Start everything
    framework.start()
    context = framework.get_bundle_context()

    # Instantiate components
    # Get the iPOPO service
    with use_waiting_list(context) as ipopo:
        # Instantiate remote service components
        # ... HTTP, using a random port
        ipopo.add("pelix.http.service.basic.factory", "http-server",
                  {"pelix.http.port": http_port})

        # ... servlet giving access to the registry
        ipopo.add(rs.FACTORY_REGISTRY_SERVLET,
                  "pelix-remote-dispatcher-servlet")

    # Prepare the utility object
    util = InstallUtils(context)

    # Install the discovery bundles
    for discovery in discoveries:
        getattr(util, "discovery_{0}".format(discovery))()

    # Install the transport bundles
    for transport in transports:
        getattr(util, "transport_{0}".format(transport))()

    # Start the service provider or consumer
    if is_server:
        # ... the provider
        context.install_bundle("remote.provider").start()

    else:
        # ... or the consumer
        context.install_bundle("remote.consumer").start()

    # Start the framework and wait for it to stop
    framework.wait_for_stop()

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description="Pelix Remote Services sample")

    # Provider or consumer
    parser.add_argument("-s", "--server", "--provider", action="store_true",
                        dest="is_server",
                        help="Runs the framework with a service provider")

    # HTTP Port
    parser.add_argument("-p", "--port", action="store", type=int, default=0,
                        dest="http_port",
                        help="Port of the HTTP server (can be 0)")

    # Discovery
    parser.add_argument("-d", "--discovery", nargs="*", default=["multicast"],
                        dest="discoveries", metavar="DISCOVERY",
                        help="Discovery protocols to use (multicast, mdns)")

    # Transport
    parser.add_argument("-t", "--transport", nargs="*", default=["jsonrpc"],
                        dest="transports", metavar="TRANSPORT",
                        help="Transport protocols to use (jsonrpc, jabsorbrpc, "
                             "xmlrpc)")

    # Parse arguments
    args = parser.parse_args(sys.argv[1:])

    # Configure the logging package
    logging.basicConfig(level=logging.DEBUG)

    # Run the sample
    main(args.is_server, args.discoveries, args.transports, args.http_port)
