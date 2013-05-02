#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
HTTP Service demo for Pelix / iPOPO : the demo launcher

:author: Thomas Calmant
:license: GPLv3
"""

from pelix.ipopo.constants import IPOPO_SERVICE_SPECIFICATION
import pelix.framework
import sys

import logging
logging.basicConfig(level=logging.DEBUG)

_logger = logging.getLogger("Demo")

def pause():
    """
    Waits for the user to press a key
    """
    _logger.info("Press any key to continue")
    sys.stdin.read(1)


def main(http_port=8080):
    """
    Entry point
    """
    # Prepare framework properties
    fw_props = {"http.port": http_port}

    # Get the framework
    _logger.info("Starting Pelix framework...")
    pause()
    framework = pelix.framework.FrameworkFactory.get_framework(fw_props)
    framework.start()

    # Install iPOPO and demo bundles
    context = framework.get_bundle_context()
    bundles = ('pelix.ipopo.core', 'http_svc', 'hello_servlet', 'extra_info')
    for bundle in bundles:
        _logger.info("Starting bundle %s...", bundle)
        context.install_bundle(bundle).start()

    _logger.info("All bundles successfully started.")

    # Get the iPOPO service
    ipopo_ref = context.get_service_reference(IPOPO_SERVICE_SPECIFICATION)
    ipopo = context.get_service(ipopo_ref)

    # Wait for user to press a key
    _logger.info("Framework is started, the hello world servlet is here : "
          "http://localhost:%d/hello", http_port)

    _logger.info("Next step will be activating the extra information component")
    pause()

    _logger.info("Instantiating extra information...")
    ipopo.instantiate("ExtraInfoFactory", "demo.extra_info_component")
    _logger.info("Look at the servlet page.")
    pause()

    _logger.info("Removing extra information...")
    ipopo.kill("demo.extra_info_component")
    _logger.info("Look at the servlet page.")
    pause()

    _logger.info("Bye !")
    framework.stop()
    pelix.framework.FrameworkFactory.delete_framework(framework)


if __name__ == "__main__":

    # Try to get the HTTP port
    try:
        port = int(sys.argv[1])
    except:
        port = 8080

    main(port)
