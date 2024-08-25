#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Runs the framework corresponding to the event listener hook provider.

Use the ``gen_event`` shell command to generate a new service event.

Use ``gen_filtered_event`` to generate an event that will be handled
differently by the hook: after the 3rd occurrence of this event, the service
listener will be filtered out of the handlers.


:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2023 Thomas Calmant

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
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def main() -> None:
    """
    Runs the framework
    """
    # Create the framework
    fw = pelix.framework.create_framework(
        (
            "pelix.ipopo.core",
            "pelix.shell.core",
            "pelix.shell.ipopo",
            "pelix.shell.console",
            # Event hook
            "samples.hooks.hook_provider",
            # Shell commands for the sample
            "samples.hooks.shell",
        )
    )

    # Start the framework and wait for it to stop
    fw.start()
    fw.wait_for_stop()


if __name__ == "__main__":
    # Run the sample
    main()
