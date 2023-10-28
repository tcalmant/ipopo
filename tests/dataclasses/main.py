#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Runs a framework and iPOPO to check behaviour with data classes (PEP-557)

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0

..

    Copyright 2020 Thomas Calmant

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

from pelix.framework import create_framework
from pelix.ipopo.constants import use_ipopo

# ------------------------------------------------------------------------------


def main():
    """
    Runs the framework
    """
    # Create the framework
    fw = create_framework(
        ('pelix.ipopo.core', 'pelix.shell.core',
         'pelix.shell.ipopo', 'pelix.shell.console',
         'dataclass_bundle'))

    # Start the framework and wait for it to stop
    fw.start()

    # Register a service
    ctx = fw.get_bundle_context()
    test_svc = object()
    ctx.register_service("dataclass.check", test_svc, {})

    # Start components
    with use_ipopo(ctx) as ipopo:
        before = ipopo.instantiate("dataclass.before", "before", {})
        after = ipopo.instantiate("dataclass.after", "after", {})

    print("CHECK 'before' injection:", before.requirement is test_svc)
    print("CHECK 'after' injection:", after.requirement is test_svc)

    print("before:")
    print(repr(before))

    print()
    print("after:")
    print(repr(after))

    fw.wait_for_stop()


if __name__ == "__main__":
    # Configure the logging package
    import logging
    logging.basicConfig(level=logging.DEBUG)

    # Run the sample
    main()
