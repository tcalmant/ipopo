#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Runs a framework where components are managed by ConfigurationAdmin

Sample usage::

   % python samples/run_configadmin.py
   ** Pelix Shell prompt **
   $ config.create pelix.ipopo.component ipopo.factory.name=sample-greeter-factory \
         instance.name=greeter-fr name=Thomas language=fr
   New configuration: pelix.ipopo.component-...
   INFO:samples.configadmin.greeter:Bonjour, Thomas!
   $ config.delete pelix.ipopo.component-...
   INFO:samples.configadmin.greeter:Goodbye, Thomas!

The "sample-banner" component stays invalid until its configuration exists::

   $ config.update sample.banner text=Hello
   INFO:samples.configadmin.greeter:Banner: Hello

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 1.0.0

..

    Copyright 2026 Thomas Calmant

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

import pelix.framework

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def main() -> None:
    """
    Runs the framework
    """
    fw = pelix.framework.create_framework(
        (
            "pelix.ipopo.core",
            "pelix.ipopo.waiting",
            # ConfigurationAdmin and its bridge to iPOPO
            "pelix.services.configadmin",
            "pelix.ipopo.handlers.configadmin",
            "pelix.ipopo.configadmin",
            # Shell, to play with the configurations
            "pelix.shell.core",
            "pelix.shell.ipopo",
            "pelix.shell.configadmin",
            "pelix.shell.console",
            # Sample bundle
            "samples.configadmin.greeter",
        )
    )

    # Start the framework and wait for it to stop
    fw.start()
    fw.wait_for_stop()


if __name__ == "__main__":
    # Configure the logging package
    import logging

    logging.basicConfig(level=logging.INFO)

    # Run the sample
    main()
