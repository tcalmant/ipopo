#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests iPOPO handlers, using the sample logger handler

:author: Thomas Calmant
"""

# Tests
from tests.ipopo import install_bundle, install_ipopo

# Pelix
from pelix.framework import FrameworkFactory
import pelix.ipopo.handlers.constants as constants

# Standard library
import sys
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# Handler bundle name
HANDLER_BUNDLE_NAME = "samples.handler.logger"

# Component bundle name
COMPONENT_BUNDLE_NAME = "samples.handler.sample"

# Handler ID
HANDLER_ID = "sample.handler.logger"

# Name of the component instantiated in samples.handler.sample
COMPONENT_NAME = "sample-logger-component"

# ------------------------------------------------------------------------------


class DummyHandlerFactory(object):
    """
    A dummy handler with a "called" flag
    """
    def __init__(self):
        """
        Sets up members
        """
        self.called = False

    def get_handlers(self, component_context, instance):
        """
        Called by iPOPO to generate handlers
        """
        self.called = True
        return []

# ------------------------------------------------------------------------------


class LifeCycleTest(unittest.TestCase):
    """
    Tests the component life cycle
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

        # Compatibility issue
        if sys.version_info[0] < 3:
            self.assertCountEqual = self.assertItemsEqual

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)
        self.framework = None

    def testHandlerAfterBundle(self):
        """
        Test a single component life cycle
        """
        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # Install the component bundle
        install_bundle(self.framework, COMPONENT_BUNDLE_NAME)

        # The component must be absent
        self.assertFalse(ipopo.is_registered_instance(COMPONENT_NAME),
                         "Instance already there")

        # Install the handler
        install_bundle(self.framework, HANDLER_BUNDLE_NAME)

        # The component must have been validated
        self.assertTrue(ipopo.is_registered_instance(COMPONENT_NAME),
                        "Instance has not been validated")

        # Remove the handler
        self.framework.get_bundle_by_name(HANDLER_BUNDLE_NAME).stop()

        # The component must be absent
        self.assertFalse(ipopo.is_registered_instance(COMPONENT_NAME),
                         "Instance still there")

        # Remove the component
        self.framework.get_bundle_by_name(COMPONENT_BUNDLE_NAME).stop()

    def testHandlerBeforeBundle(self):
        """
        Test a single component life cycle
        """
        # Install the handler
        install_bundle(self.framework, HANDLER_BUNDLE_NAME)

        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # Install the component bundle
        install_bundle(self.framework, COMPONENT_BUNDLE_NAME)

        # The component must have been validated
        self.assertTrue(ipopo.is_registered_instance(COMPONENT_NAME),
                        "Instance has not been validated")

        # Remove the component
        self.framework.get_bundle_by_name(COMPONENT_BUNDLE_NAME).stop()

        # Remove the handler
        self.framework.get_bundle_by_name(HANDLER_BUNDLE_NAME).stop()

    def testWaitingFactoryDetails(self):
        """
        Tests the "handlers" entry of factory details dictionary
        """
        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # Install the component bundle
        install_bundle(self.framework, COMPONENT_BUNDLE_NAME)

        # Find the component in the waiting list
        waiting = ipopo.get_waiting_components()
        for name, factory, missing in waiting:
            if name == COMPONENT_NAME:
                break
        else:
            # Component not found
            self.fail("Component not in the waiting handler list")

        # Check the missing handler
        self.assertCountEqual(missing, [HANDLER_ID])

        # The instance details must fail (instance not ready)
        self.assertRaises(ValueError, ipopo.get_instance_details,
                          COMPONENT_NAME)

        # Get factory details
        factory_details = ipopo.get_factory_details(factory)

        # The handlers details must be present
        self.assertIn(HANDLER_ID, factory_details["handlers"])

        # Install the handler
        install_bundle(self.framework, HANDLER_BUNDLE_NAME)

        # The component is not waiting anymore
        waiting = ipopo.get_waiting_components()
        for name, factory, missing in waiting:
            if name == COMPONENT_NAME:
                self.fail("Component is still waiting for its handler")

        # Get instance details (must not fail)
        ipopo.get_instance_details(COMPONENT_NAME)

        # Remove the handler
        self.framework.get_bundle_by_name(HANDLER_BUNDLE_NAME).stop()

        # The component must be back in the waiting list
        waiting = ipopo.get_waiting_components()
        for name, factory, missing in waiting:
            if name == COMPONENT_NAME:
                break
        else:
            # Component not found
            self.fail("Component not in the waiting handler list")

        # The instance details must fail (instance not ready)
        self.assertRaises(ValueError, ipopo.get_instance_details,
                          COMPONENT_NAME)

    def testDuplicateHandler(self):
        """
        Duplicated handler must be ignored
        """
        # Install iPOPO
        ipopo = install_ipopo(self.framework)

        # Install the original handler
        install_bundle(self.framework, HANDLER_BUNDLE_NAME)

        # Register the duplicated handler
        properties = {constants.PROP_HANDLER_ID: HANDLER_ID}

        # Register the handler factory service
        context = self.framework.get_bundle_context()
        dummy_handler = DummyHandlerFactory()
        svc_reg = context.register_service(
            constants.SERVICE_IPOPO_HANDLER_FACTORY,
            dummy_handler, properties)

        # Install the component bundle
        install_bundle(self.framework, COMPONENT_BUNDLE_NAME)

        # The component is not waiting
        waiting = ipopo.get_waiting_components()
        for info in waiting:
            if info[0] == COMPONENT_NAME:
                self.fail("Component is waiting for its handler")

        # The duplicated handler must not have been called
        self.assertFalse(dummy_handler.called, "Second handler has been used")

        # Remove the original handler
        self.framework.get_bundle_by_name(HANDLER_BUNDLE_NAME).stop()

        # The component is not waiting
        waiting = ipopo.get_waiting_components()
        for info in waiting:
            if info[0] == COMPONENT_NAME:
                self.fail("Component is waiting for its handler")

        # The duplicated handler must have been called
        self.assertTrue(dummy_handler.called,
                        "Second handler has not been used")

        # Unregister the duplicated handler
        svc_reg.unregister()

        # The component must be back in the waiting list
        waiting = ipopo.get_waiting_components()
        for info in waiting:
            if info[0] == COMPONENT_NAME:
                break
        else:
            # Component not found
            self.fail("Component not in the waiting handler list")

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
