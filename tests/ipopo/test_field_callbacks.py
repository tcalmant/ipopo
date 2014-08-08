#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO @Bind/Update/UnbindField decorators.

:author: Thomas Calmant
"""

# Tests
from tests.ipopo import install_bundle, install_ipopo

# Pelix
from pelix.framework import FrameworkFactory

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class FieldCallbackTest(unittest.TestCase):
    """
    Tests the component life cycle
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)
        self.module = install_bundle(self.framework,
                                     "tests.ipopo.ipopo_fields_bundle")

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)

    def testLifeCycleFieldCallback(self):
        """
        Tests the order of field notifications
        """
        # Consumer
        compo = self.ipopo.instantiate(self.module.FACTORY_C, "consumer")
        self.assertEqual(compo.states, [], "States should be empty")

        # Service A
        svc_a = self.ipopo.instantiate(self.module.FACTORY_A, "svcA")
        self.assertEqual(compo.states,
                         [self.module.BIND_A, self.module.BIND_FIELD_A],
                         "Service A bound incorrectly")
        del compo.states[:]

        # Service B
        svc_b = self.ipopo.instantiate(self.module.FACTORY_B, "svcB")
        self.assertEqual(compo.states,
                         [self.module.BIND_B, self.module.BIND_FIELD_B],
                         "Service B bound incorrectly")
        del compo.states[:]

        # Update A
        self.assertNotEqual(svc_a._prop, 42,
                            "Value already at requested value")
        compo.change_a(42)
        self.assertEqual(svc_a._prop, 42, "Value not changed")
        self.assertEqual(compo.states,
                         [self.module.UPDATE_FIELD_A, self.module.UPDATE_A],
                         "Service A updated incorrectly")
        del compo.states[:]

        # Update B
        self.assertNotEqual(svc_b._prop, -123,
                            "Value already at requested value")
        compo.change_b(-123)
        self.assertEqual(svc_b._prop, -123, "Value not changed")
        self.assertEqual(compo.states,
                         [self.module.UPDATE_FIELD_B, self.module.UPDATE_B],
                         "Service B updated incorrectly")
        del compo.states[:]

        # Kill service A
        self.ipopo.kill("svcA")
        self.assertEqual(compo.states,
                         [self.module.UNBIND_FIELD_A, self.module.UNBIND_A],
                         "Service A unbound incorrectly")
        del compo.states[:]

        # Kill service B
        self.ipopo.kill("svcB")
        self.assertEqual(compo.states,
                         [self.module.UNBIND_FIELD_B, self.module.UNBIND_B],
                         "Service B unbound incorrectly")
        del compo.states[:]

        # Kill consumer
        self.ipopo.kill("consumer")

    def testLifeCycleFieldCallbackIfValid(self):
        """
        Tests the order of field notifications with the "if_valid" flag
        """
        # Consumer
        compo = self.ipopo.instantiate(self.module.FACTORY_D, "consumer")
        self.assertEqual(compo.states, [], "States should be empty")

        # -- Component is invalid

        # Start Service B
        svc_b = self.ipopo.instantiate(self.module.FACTORY_B, "svcB")
        self.assertEqual(compo.states, [], "Service B bound: called")
        del compo.states[:]

        # Update B
        self.assertNotEqual(svc_b._prop, -123,
                            "Value already at requested value")
        compo.change_b(-123)
        self.assertEqual(svc_b._prop, -123, "Value not changed")
        self.assertEqual(compo.states, [], "Service B updated: called")
        del compo.states[:]

        # Kill service B
        self.ipopo.kill("svcB")
        self.assertEqual(compo.states, [], "Service B unbound: called")
        del compo.states[:]

        # Start Service A
        self.ipopo.instantiate(self.module.FACTORY_A, "svcA")
        del compo.states[:]

        # -- Component is valid

        # Start Service B
        svc_b = self.ipopo.instantiate(self.module.FACTORY_B, "svcB")
        self.assertEqual(compo.states, [self.module.BIND_FIELD_B],
                         "Service B bound: not called")
        del compo.states[:]

        # Update B
        self.assertNotEqual(svc_b._prop, -123,
                            "Value already at requested value")
        compo.change_b(-123)
        self.assertEqual(svc_b._prop, -123, "Value not changed")
        self.assertEqual(compo.states, [self.module.UPDATE_FIELD_B],
                         "Service B updated: not called")
        del compo.states[:]

        # Kill service B
        self.ipopo.kill("svcB")
        self.assertEqual(compo.states, [self.module.UNBIND_FIELD_B],
                         "Service B unbound: not called")
        del compo.states[:]

        # Restart Service B
        svc_b = self.ipopo.instantiate(self.module.FACTORY_B, "svcB")
        self.assertEqual(compo.states, [self.module.BIND_FIELD_B],
                         "Service B bound: not called")
        del compo.states[:]

        # Kill service A
        self.ipopo.kill("svcA")
        del compo.states[:]

        # -- Component is invalid (again)

        # Update B
        self.assertNotEqual(svc_b._prop, -123,
                            "Value already at requested value")
        compo.change_b(-123)
        self.assertEqual(svc_b._prop, -123, "Value not changed")
        self.assertEqual(compo.states, [], "Service B updated: called")
        del compo.states[:]

        # Kill service B
        self.ipopo.kill("svcB")
        self.assertEqual(compo.states, [], "Service B unbound: called")
        del compo.states[:]

        # Kill consumer
        self.ipopo.kill("consumer")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
