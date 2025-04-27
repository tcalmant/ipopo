#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the framework events.

:author: Thomas Calmant
"""

import unittest

from pelix.framework import (
    Bundle,
    BundleContext,
    BundleEvent,
    BundleException,
    FrameworkFactory,
    ServiceEvent,
)
from pelix.services import SERVICE_EVENT_LISTENER_HOOK
from tests import log_off, log_on
from tests.interfaces import IEchoService

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

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
        FrameworkFactory.delete_framework()

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
        if self.bundle is not None and kind == BundleEvent.INSTALLED:
            # Bundle is not yet locally known...
            self.assertIs(self.bundle, bundle, "Received an event for an other bundle.")

        self.assertNotIn(kind, self.received, "Event received twice")
        self.received.append(kind)

    def testBundleEvents(self):
        """
        Tests if the signals are correctly received
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        self.assertTrue(context.add_bundle_listener(self), "Can't register the bundle listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        self.assertEqual([BundleEvent.INSTALLED], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual(
            [BundleEvent.STARTING, BundleEvent.STARTED], self.received, "Received {0}".format(self.received)
        )
        self.reset_state()

        # Stop the bundle
        bundle.stop()
        # Assert the events have been received
        self.assertEqual(
            [BundleEvent.STOPPING, BundleEvent.STOPPING_PRECLEAN, BundleEvent.STOPPED],
            self.received,
            "Received {0}".format(self.received),
        )
        self.reset_state()

        # Uninstall the bundle
        bundle.uninstall()
        # Assert the events have been received
        self.assertEqual([BundleEvent.UNINSTALLED], self.received, "Received {0}".format(self.received))
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
        FrameworkFactory.delete_framework()

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

        if kind == ServiceEvent.MODIFIED or kind == ServiceEvent.MODIFIED_ENDMATCH:
            # Properties have been modified
            self.assertNotEqual(
                ref.get_properties(),
                event.get_previous_properties(),
                "Modified event for unchanged properties",
            )

        self.assertNotIn(kind, self.received, "Event received twice")
        self.received.append(kind)

    def testDoubleListener(self):
        """
        Tests double registration / unregistration
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Double registration
        self.assertTrue(context.add_service_listener(self), "Can't register the service listener")

        log_off()
        self.assertFalse(context.add_service_listener(self), "Service listener registered twice")
        log_on()

        # Double unregistration
        self.assertTrue(context.remove_service_listener(self), "Can't unregister the service listener")

        log_off()
        self.assertFalse(context.remove_service_listener(self), "Service listener unregistered twice")
        log_on()

    def testInvalidFilterListener(self):
        """
        Tests invalid filter listener registration
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        log_off()
        self.assertRaises(BundleException, context.add_service_listener, self, "Invalid")
        log_on()

        self.assertFalse(context.remove_service_listener(self), "Invalid filter was registered anyway")

    def testServiceEventsNormal(self):
        """
        Tests if the signals are correctly received
        """
        context = self.framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        self.assertTrue(context.add_service_listener(self), "Can't register the service listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        self.assertEqual([], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.REGISTERED], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Stop the bundle
        bundle.stop()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.UNREGISTERING], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle
        bundle.uninstall()
        # Assert the events have been received
        self.assertEqual([], self.received, "Received {0}".format(self.received))
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
        self.assertTrue(context.add_service_listener(self), "Can't register the service listener")

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        self.assertEqual([], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.REGISTERED], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle, without unregistering the service
        module_ = bundle.get_module()
        module_.unregister = False
        bundle.uninstall()

        # Assert the events have been received
        self.assertEqual([ServiceEvent.UNREGISTERING], self.received, "Received {0}".format(self.received))
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
        self.assertTrue(
            context.add_service_listener(self, "(test=True)"), "Can't register the service listener"
        )

        # Install the bundle
        self.bundle = bundle = context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        # Start the bundle
        bundle.start()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.REGISTERED], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Get the service
        ref = context.get_service_reference(IEchoService)
        self.assertIsNotNone(ref, "ServiceReference not found")

        svc = context.get_service(ref)
        self.assertIsNotNone(ref, "Invalid service instance")

        # Modify the service => Simple modification
        svc.modify({"answer": 42})
        self.assertEqual([ServiceEvent.MODIFIED], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Set the same value => No event should be sent
        svc.modify({"answer": 42})
        self.assertEqual([], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Modify the service => Ends the filter match
        svc.modify({"test": False})
        # Assert the events have been received
        self.assertEqual(
            [ServiceEvent.MODIFIED_ENDMATCH], self.received, "Received {0}".format(self.received)
        )
        self.reset_state()

        # Modify the service => the filter matches again
        svc.modify({"test": True})
        # Assert the events have been received
        self.assertEqual([ServiceEvent.MODIFIED], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Stop the bundle
        bundle.stop()
        # Assert the events have been received
        self.assertEqual([ServiceEvent.UNREGISTERING], self.received, "Received {0}".format(self.received))
        self.reset_state()

        # Uninstall the bundle
        bundle.uninstall()

        # Unregister from events
        context.remove_service_listener(self)


# ------------------------------------------------------------------------------


class EventListenerHookTest(unittest.TestCase):
    """
    Event Listener Hook tests
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
        self.framework.delete()

    def test_normal_behaviour(self):
        """
        Checks if event listener hooks are registered correctly
        """
        # Test implementation
        events = []

        class Hook(object):
            @staticmethod
            def event(svc_event, listeners_dict):
                events.append((svc_event, listeners_dict))

        # Register the hook
        ctx = self.framework.get_bundle_context()
        reg = ctx.register_service(SERVICE_EVENT_LISTENER_HOOK, Hook(), {})

        # Hooks shouldn't be aware of themselves
        self.assertFalse(events)

        # Register a dummy service
        dummy_reg = ctx.register_service("dummy", object(), {})

        # Pop information
        event, listeners = events.pop(0)

        # Check event
        assert isinstance(event, ServiceEvent)
        self.assertEqual(event.get_kind(), ServiceEvent.REGISTERED)
        self.assertIs(event.get_service_reference(), dummy_reg.get_reference())

        # No listeners are registered
        self.assertFalse(listeners)

        # Update the service
        dummy_reg.set_properties({"hello": "world"})

        # Pop information
        event, listeners = events.pop(0)

        # Check event
        assert isinstance(event, ServiceEvent)
        self.assertEqual(event.get_kind(), ServiceEvent.MODIFIED)
        self.assertIs(event.get_service_reference(), dummy_reg.get_reference())

        # Unregister the service
        dummy_reg.unregister()

        # Pop information
        event, listeners = events.pop(0)

        # Check event
        assert isinstance(event, ServiceEvent)
        self.assertEqual(event.get_kind(), ServiceEvent.UNREGISTERING)
        self.assertIs(event.get_service_reference(), dummy_reg.get_reference())

        # Unregister the hook
        reg.unregister()

        # Register a new service
        ctx.register_service("dummy", object(), {})

        # Hook must not be notified
        self.assertFalse(events)

    def test_hook(self):
        """
        Tests the hook filtering behaviour
        """
        # Add a bundle to have two contexts in the test
        fw_ctx = self.framework.get_bundle_context()
        bnd = fw_ctx.install_bundle("tests.dummy_1")
        bnd.start()
        bnd_ctx = bnd.get_bundle_context()

        # Setup a hook
        class Hook(object):
            @staticmethod
            def event(svc_event, listeners_dict):
                to_remove = svc_event.get_service_reference().get_property("to.remove")
                info_to_remove = []

                for listener_bc, listeners_info in listeners_dict.items():
                    # Check the dictionary content
                    for listener_info in listeners_info:
                        self.assertIs(listener_bc, listener_info.bundle_context)
                        self.assertIs(listener_bc, listener_info.listener.context)
                        self.assertIs(listener_bc, listener_info.get_bundle_context())

                        if listener_info.listener in to_remove:
                            info_to_remove.append(listener_info)

                # Remove the requested listeners
                for listener_info in info_to_remove:
                    listeners_dict[listener_info.bundle_context].remove(listener_info)

        fw_ctx.register_service(SERVICE_EVENT_LISTENER_HOOK, Hook(), {})

        # Register multiple listeners
        class Listener(object):
            def __init__(self, bc):
                self.context = bc
                self.storage = []
                bc.add_service_listener(self)

            def service_changed(self, event):
                self.storage.append(event)

        listener_referee = Listener(fw_ctx)
        listener_1 = Listener(fw_ctx)
        listener_2 = Listener(bnd_ctx)

        # Register a service that only the referee will get
        reg = fw_ctx.register_service("dummy", object(), {"to.remove": [listener_1, listener_2]})

        evt = listener_referee.storage.pop(0)
        self.assertIs(evt.get_service_reference(), reg.get_reference())
        self.assertEqual(evt.get_kind(), ServiceEvent.REGISTERED)
        self.assertFalse(listener_1.storage)
        self.assertFalse(listener_2.storage)

        # Modify it so that listener_1 gets it
        reg.set_properties({"to.remove": [listener_2]})
        self.assertFalse(listener_2.storage)

        evt = listener_referee.storage.pop(0)
        self.assertIs(evt.get_service_reference(), reg.get_reference())
        self.assertEqual(evt.get_kind(), ServiceEvent.MODIFIED)

        evt1 = listener_1.storage.pop(0)
        self.assertIs(evt1, evt)

        # Modify it so that listener_2, but not listener_1 gets it
        reg.set_properties({"to.remove": [listener_1]})
        self.assertFalse(listener_1.storage)

        evt = listener_referee.storage.pop(0)
        self.assertIs(evt.get_service_reference(), reg.get_reference())
        self.assertEqual(evt.get_kind(), ServiceEvent.MODIFIED)

        evt2 = listener_2.storage.pop(0)
        self.assertIs(evt2, evt)


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
