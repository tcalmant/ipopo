#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @HiddenProperty decorator.

:author: Thomas Calmant
"""

import random
import unittest

from pelix.framework import FrameworkFactory
from pelix.ipopo.constants import use_ipopo
from tests.ipopo import install_bundle, install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

NAME_A = "componentA"

# ------------------------------------------------------------------------------


class HiddenPropTest(unittest.TestCase):
    """
    Tests the "hidden property" behavior
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)

        # Install the test bundle
        self.module = install_bundle(self.framework)

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def test_hidden_default(self):
        """
        Tests the hidden property
        """
        context = self.framework.get_bundle_context()

        # Instantiate the component
        with use_ipopo(context) as ipopo:
            svc = ipopo.instantiate(self.module.FACTORY_HIDDEN_PROPS, NAME_A)

        # Check default values (and accesses)
        self.assertEqual(svc.hidden, "hidden")
        self.assertEqual(svc.public, "public")

        # Check instance details
        with use_ipopo(context) as ipopo:
            details = ipopo.get_instance_details(NAME_A)

        self.assertNotIn("hidden.prop", details["properties"])

    def test_hidden_instantiate(self):
        """
        Tests the value of hidden properties given as instantiation parameters
        """
        context = self.framework.get_bundle_context()

        # Prepare random values
        hidden_value = random.randint(0, 100)
        public_value = random.randint(0, 100)

        # Instantiate the component
        with use_ipopo(context) as ipopo:
            svc = ipopo.instantiate(
                self.module.FACTORY_HIDDEN_PROPS,
                NAME_A,
                {"hidden.prop": hidden_value, "public.prop": public_value},
            )

        # Check default values (and accesses)
        self.assertEqual(svc.hidden, hidden_value)
        self.assertEqual(svc.public, public_value)

        # Check instance details
        with use_ipopo(context) as ipopo:
            details = ipopo.get_instance_details(NAME_A)

        self.assertNotIn("hidden.prop", details["properties"])

    def test_hidden_reconfigure_dot_override(self):
        """
        Tests that a hidden property can be updated confidentially through
        reconfigure() by prefixing its name with a dot, while its plain name
        is still ignored
        """
        context = self.framework.get_bundle_context()

        with use_ipopo(context) as ipopo:
            svc = ipopo.instantiate(self.module.FACTORY_HIDDEN_PROPS, NAME_A)

        self.assertEqual(svc.hidden, "hidden")

        # A plain name is ignored
        with use_ipopo(context) as ipopo:
            ipopo.reconfigure(NAME_A, {"hidden.prop": "ignored"})

        self.assertEqual(svc.hidden, "hidden")

        # A dot-prefixed name updates the hidden property
        with use_ipopo(context) as ipopo:
            ipopo.reconfigure(NAME_A, {".hidden.prop": "rotated"})

        self.assertEqual(svc.hidden, "rotated")

        # ... and still doesn't become public
        with use_ipopo(context) as ipopo:
            details = ipopo.get_instance_details(NAME_A)

        self.assertNotIn("hidden.prop", details["properties"])


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
