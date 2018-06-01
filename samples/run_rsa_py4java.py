#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

Run RSA with py4java distribution and discovery module

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0
:version: 0.1.0

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
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)
# Documentation strings format
__docformat__ = "restructuredtext en"
# ------------------------------------------------------------------------------
import pelix.framework as pelix
# ------- Main constants
# Httpservice config
HTTP_HOSTNAME = 'localhost'
HTTP_PORT = 8181
# ------------------------------------------------------------------------------
def main():
    # Set the initial bundles
    bundles = ['pelix.ipopo.core', 
               'pelix.shell.core', 
               'pelix.shell.ipopo',
               'pelix.shell.console', 
               'pelix.rsa.remoteserviceadmin', # RSA implementation
               'pelix.rsa.topologymanagers.basic',  # basic topology manager (opt)
               'pelix.rsa.shell', # RSA shell commands (opt)
               'pelix.rsa.providers.distribution.py4j',
               'samples.rsa.helloimpl',
               'samples.rsa.helloconsumer' ]  # Example helloconsumer.  Only uses remote proxies

    # Use the utility method to create, run and delete the framework
    framework = pelix.create_framework(
        bundles, { 'ecf.py4j.javaport': 25333, 'ecf.py4j.pythonport':25334 })
    framework.start()

    try:
        framework.wait_for_stop()
    except KeyboardInterrupt:
        framework.stop()

    
if __name__ == '__main__':
    main()