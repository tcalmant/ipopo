#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Runs a framework and iPOPO to check behaviour with data classes (PEP-557)

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

import logging
import unittest

from pelix.framework import create_framework
from pelix.ipopo.constants import use_ipopo

# ------------------------------------------------------------------------------


class DataclassTest(unittest.TestCase):
    """
    Tests if dataclasses are handled correctly
    """

    def testDataclasses(self) -> None:
        """
        Tests if dataclasses are handled correctly as services
        """
        # Create the framework
        fw = create_framework(
            (
                "pelix.ipopo.core",
                "pelix.shell.core",
                "pelix.shell.ipopo",
                "tests.dataclasses.dataclass_bundle",
            )
        )

        # Start the framework and wait for it to stop
        fw.start()

        try:
            # Register a service
            ctx = fw.get_bundle_context()
            test_svc = object()
            ctx.register_service("dataclass.check", test_svc, {})

            # Start components
            with use_ipopo(ctx) as ipopo:
                before = ipopo.instantiate("dataclass.before", "before", {})
                after = ipopo.instantiate("dataclass.after", "after", {})

            # Dependency injection
            self.assertIs(before.requirement, test_svc)
            self.assertIs(after.requirement, test_svc)

            # Property injection
            self.assertEqual(before.instance_name, "before")
            self.assertEqual(after.instance_name, "after")

            self.assertEqual(before.property_set, "SAMPLE-before")
            self.assertEqual(after.property_set, "SAMPLE-after")

            # Ensure that the initial value is kept
            self.assertEqual(before.property_default, "Default-before")
            self.assertEqual(after.property_default, "Default-after")
        finally:
            fw.stop()


if __name__ == "__main__":
    # Set logging level
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
