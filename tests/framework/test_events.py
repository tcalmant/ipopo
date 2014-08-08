#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the framework events.

:author: Thomas Calmant
"""

# Tests
from tests import log_on, log_off
from tests.interfaces import IEchoService

# Pelix
from pelix.framework import FrameworkFactory, Bundle, BundleException, \
    BundleContext, BundleEvent, ServiceEvent

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

SERVICE_BUNDLE = "tests.framework.service_bundle"
SIMPLE_BUNDLE = "tests.framework.simple_bundle"

# ------------------------------------------------------------------------------


class BundleEventTest(unittest.TestCase):
    """
    Pelix bundle event tests
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

        self.test_bundle_name = SIMPLE_BUNDLE

        self.bundle = None
        self.received = []

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)

    def reset_state(self):
        """
        Resets the flags
        """
        del self.received[:]

    def bundle_changed(self, event):
        """
        Called by the framework when a bundle event is triggered

        @param event: The BundleEvent
        """
        assert isinstance(event, BundleEvent)

        bundle = event.get_bundle()
        kind = event.get_kind()
        if self.bundle is not None \
                and kind == BundleEvent.INSTALLED:
            # Bundle is not yet locally known...
            self.assertIs(self.bundle, bundle,
                          "Received an event for an other bundle.")

        self.assertNotIn(kind, self.received, "Event received twice")
        self.received.append(kind)

    def testBundleEvents(self):
        """
        Tests if the signals are correctly received
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        self.assertTrue(context.add_bundle_listener(self),
                        "Can't register the bundle listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        self.assertEqual([BundleEvent.INSTALLED],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([BundleEvent.STARTING, BundleEvent.STARTED],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Stop the bundle
        bundle.stop()
        # Assert the events have been received
        self.assertEqual([BundleEvent.STOPPING, BundleEvent.STOPPING_PRECLEAN,
                          BundleEvent.STOPPED], self.received,
                         "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle
        bundle.uninstall()
        # Assert the events have been received
        self.assertEqual([BundleEvent.UNINSTALLED],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Unregister from events
        context.remove_bundle_listener(self)

# ------------------------------------------------------------------------------


class ServiceEventTest(unittest.TestCase):
    """
    Pelix service event tests
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()

        self.test_bundle_name = SERVICE_BUNDLE

        self.bundle = None
        self.received = []

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework(self.framework)

    def reset_state(self):
        """
        Resets the flags
        """
        del self.received[:]

    def service_changed(self, event):
        """
        Called by the framework when a service event is triggered

        @param event: The ServiceEvent
        """
        assert isinstance(event, ServiceEvent)

        ref = event.get_service_reference()
        self.assertIsNotNone(ref, "Invalid service reference in the event")

        kind = event.get_kind()

        if kind == ServiceEvent.MODIFIED \
                or kind == ServiceEvent.MODIFIED_ENDMATCH:
            # Properties have been modified
            self.assertNotEqual(ref.get_properties(),
                                event.get_previous_properties(),
                                "Modified event for unchanged properties")

        self.assertNotIn(kind, self.received, "Event received twice")
        self.received.append(kind)

    def testDoubleListener(self):
        """
        Tests double registration / unregistration
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Double registration
        self.assertTrue(context.add_service_listener(self),
                        "Can't register the service listener")

        log_off()
        self.assertFalse(context.add_service_listener(self),
                         "Service listener registered twice")
        log_on()

        # Double unregistration
        self.assertTrue(context.remove_service_listener(self),
                        "Can't unregister the service listener")

        log_off()
        self.assertFalse(context.remove_service_listener(self),
                         "Service listener unregistered twice")
        log_on()

    def testInvalidFilterListener(self):
        """
        Tests invalid filter listener registration
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        log_off()
        self.assertRaises(BundleException, context.add_service_listener, self,
                          "Invalid")
        log_on()

        self.assertFalse(context.remove_service_listener(self),
                         "Invalid filter was registered anyway")

    def testServiceEventsNormal(self):
        """
        Tests if the signals are correctly received
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        self.assertTrue(context.add_service_listener(self),
                        "Can't register the service listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        self.assertEqual(
            [], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.REGISTERED],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Stop the bundle
        bundle.stop()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.UNREGISTERING],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle
        bundle.uninstall()
        # Assert the events have been received
        self.assertEqual(
            [], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Unregister from events
        context.remove_service_listener(self)

    def testServiceEventsNoStop(self):
        """
        Tests if the signals are correctly received, even if the service is not
        correctly removed
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        self.assertTrue(context.add_service_listener(self),
                        "Can't register the service listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        self.assertEqual(
            [], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.REGISTERED],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle, without unregistering the service
        module = bundle.get_module()
        module.unregister = False
        bundle.uninstall()

        # Assert the events have been received
        self.assertEqual([ServiceEvent.UNREGISTERING],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Unregister from events
        context.remove_service_listener(self)

    def testServiceModified(self):
        """
        Tests the service modified event
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        self.assertTrue(context.add_service_listener(self, "(test=True)"),
                        "Can't register the service listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.REGISTERED],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Get the service
        ref = context.get_service_reference(IEchoService)
        self.assertIsNotNone(ref, "ServiceReference not found")

        svc = context.get_service(ref)
        self.assertIsNotNone(ref, "Invalid service instance")

        # Modify the service => Simple modification
        svc.modify({"answer": 42})
        self.assertEqual([ServiceEvent.MODIFIED],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Set the same value => No event should be sent
        svc.modify({"answer": 42})
        self.assertEqual([], self.received,
                         "Received {0}".format(self.received))
        self.reset_state()

        # Modify the service => Ends the filter match
        svc.modify({"test": False})
        # Assert the events have been received
        self.assertEqual([ServiceEvent.MODIFIED_ENDMATCH],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Modify the service => the filter matches again
        svc.modify({"test": True})
        # Assert the events have been received
        self.assertEqual([ServiceEvent.MODIFIED],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Stop the bundle
        bundle.stop()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.UNREGISTERING],
                         self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle
        bundle.uninstall()

        # Unregister from events
        context.remove_service_listener(self)

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
