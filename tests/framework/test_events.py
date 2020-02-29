#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Tests the framework events.

:author: Thomas Calmant, Angelo Cutaia
"""

# Standard library
import asyncio
import pytest

# Tests
from tests import log_on, log_off
from tests.interfaces import IEchoService

# Pelix
from pelix.framework import FrameworkFactory, Bundle, BundleException, \
    BundleContext, BundleEvent, ServiceEvent
from pelix.services import SERVICE_EVENT_LISTENER_HOOK

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

SERVICE_BUNDLE = "tests.framework.service_bundle"
SIMPLE_BUNDLE = "tests.framework.simple_bundle"

# ------------------------------------------------------------------------------


class TestBundleEvent:
    """
    Pelix bundle event tests
    """
    bundle = None
    received = []
    def reset_state(self):
        """
        Resets the flags
        """
        del self.received[:]

    async def bundle_changed(self, event):
        """
        Called by the framework when a bundle event is triggered

        @param event: The BundleEvent
        """
        assert isinstance(event, BundleEvent)

        bundle = event.get_bundle()
        kind = event.get_kind()
        if self.bundle is not None and kind == BundleEvent.INSTALLED:
            # Bundle is not yet locally known...
            assert self.bundle is bundle, "Received an event for an other bundle."

        assert kind not in self.received, "Event received twice"
        self.received.append(kind)

    @pytest.mark.asyncio
    async def test_bundle_events(self):
        """
        Tests if the signals are correctly received
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        test_bundle_name = SIMPLE_BUNDLE

        self.bundle = None
        self.received = []

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        assert await context.add_bundle_listener(self), "Can't register the bundle listener"

        # Install the bundle
        self.bundle = bundle = await context.install_bundle(test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        assert [BundleEvent.INSTALLED] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Start the bundle
        await bundle.start()
        # Assert the events have been received
        assert [BundleEvent.STARTING, BundleEvent.STARTED] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Stop the bundle
        await bundle.stop()
        # Assert the events have been received
        assert [
            BundleEvent.STOPPING,
            BundleEvent.STOPPING_PRECLEAN,
            BundleEvent.STOPPED
            ] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Uninstall the bundle
        await bundle.uninstall()
        # Assert the events have been received
        assert [BundleEvent.UNINSTALLED] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Unregister from events
        await context.remove_bundle_listener(self)

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

# ------------------------------------------------------------------------------


class TestServiceEvent:
    """
    Pelix service event tests
    """
    bundle = None
    received = []
    def reset_state(self):
        """
        Resets the flags
        """
        del self.received[:]

    async def service_changed(self, event):
        """
        Called by the framework when a service event is triggered

        @param event: The ServiceEvent
        """
        assert isinstance(event, ServiceEvent)

        ref = event.get_service_reference()
        assert ref is not None, "Invalid service reference in the event"

        kind = event.get_kind()

        if kind == ServiceEvent.MODIFIED or kind == ServiceEvent.MODIFIED_ENDMATCH:
            # Properties have been modified
            assert await ref.get_properties() != event.get_previous_properties(), "Modified event for unchanged properties"

        assert kind not in self.received, "Event received twice"
        self.received.append(kind)

    @pytest.mark.asyncio
    async def test_double_listener(self):
        """
        Tests double registration / unregistration
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        self.bundle = None
        self.received = []

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Double registration
        assert await context.add_service_listener(self), "Can't register the service listener"

        log_off()
        assert not await context.add_service_listener(self), "Service listener registered twice"
        log_on()

        # Double unregistration
        assert await context.remove_service_listener(self), "Can't unregister the service listener"

        log_off()
        assert not await context.remove_service_listener(self), "Service listener unregistered twice"
        log_on()

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_invalid_filter_listener(self):
        """
        Tests invalid filter listener registration
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        self.bundle = None
        self.received = []

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        log_off()
        with pytest.raises(BundleException):
            await context.add_service_listener(self, "Invalid")
        log_on()

        assert not await context.remove_service_listener(self), "Invalid filter was registered anyway"

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_service_events_normal(self):
        """
        Tests if the signals are correctly received
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        test_bundle_name = SERVICE_BUNDLE

        self.bundle = None
        self.received = []

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        assert await context.add_service_listener(self), "Can't register the service listener"

        # Install the bundle
        self.bundle = bundle = await context.install_bundle(test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        assert [] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Start the bundle
        await bundle.start()
        # Assert the events have been received
        assert [ServiceEvent.REGISTERED] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Stop the bundle
        await bundle.stop()
        # Assert the events have been received
        assert [ServiceEvent.UNREGISTERING] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Uninstall the bundle
        await bundle.uninstall()
        # Assert the events have been received
        assert [] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Unregister from events
        await context.remove_service_listener(self)

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_service_events_nostop(self):
        """
        Tests if the signals are correctly received, even if the service is not
        correctly removed
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        test_bundle_name = SERVICE_BUNDLE

        self.bundle = None
        self.received = []

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        assert await context.add_service_listener(self), "Can't register the service listener"

        # Install the bundle
        self.bundle = bundle = await context.install_bundle(test_bundle_name)
        assert isinstance(bundle, Bundle)
        # Assert the Install events has been received
        assert [] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Start the bundle
        await bundle.start()
        # Assert the events have been received
        assert [ServiceEvent.REGISTERED] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Uninstall the bundle, without unregistering the service
        module_ = bundle.get_module()
        module_.unregister = False
        await bundle.uninstall()

        # Assert the events have been received
        assert [ServiceEvent.UNREGISTERING] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Unregister from events
        await context.remove_service_listener(self)

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_service_modified(self):
        """
        Tests the service modified event
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        test_bundle_name = SERVICE_BUNDLE

        self.bundle = None
        self.received = []

        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Register to events
        assert await context.add_service_listener(self, "(test=True)"), "Can't register the service listener"

        # Install the bundle
        self.bundle = bundle = await context.install_bundle(test_bundle_name)
        assert isinstance(bundle, Bundle)

        # Start the bundle
        await bundle.start()
        # Assert the events have been received
        assert [ServiceEvent.REGISTERED] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Get the service
        ref = await context.get_service_reference(IEchoService)
        assert ref is not None, "ServiceReference not found"

        svc = await context.get_service(ref)
        assert ref is not None, "Invalid service instance"

        # Modify the service => Simple modification
        await svc.modify({"answer": 42})
        assert [ServiceEvent.MODIFIED] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Set the same value => No event should be sent
        await svc.modify({"answer": 42})
        assert [] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Modify the service => Ends the filter match
        await svc.modify({"test": False})
        # Assert the events have been received
        assert [ServiceEvent.MODIFIED_ENDMATCH] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Modify the service => the filter matches again
        await svc.modify({"test": True})
        # Assert the events have been received
        assert [ServiceEvent.MODIFIED] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Stop the bundle
        await bundle.stop()
        # Assert the events have been received
        assert [ServiceEvent.UNREGISTERING] == self.received, "Received {0}".format(self.received)
        self.reset_state()

        # Uninstall the bundle
        await bundle.uninstall()

        # Unregister from events
        await context.remove_service_listener(self)

        # Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

# ------------------------------------------------------------------------------


class TestEventListenerHook:
    """
    Event Listener Hook tests
    """
    bundle = None
    received = []
    @pytest.mark.asyncio
    async def test_normal_behaviour(self):
        """
        Checks if event listener hooks are registered correctly
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        self.bundle = None
        self.received = []

        # Test implementation
        events = []

        class Hook(object):
            @staticmethod
            async def event(svc_event, listeners_dict):
                events.append((svc_event, listeners_dict))

        # Register the hook
        ctx = framework.get_bundle_context()
        reg = await ctx.register_service(SERVICE_EVENT_LISTENER_HOOK, Hook(), {})

        # Hooks shouldn't be aware of themselves
        assert not events

        # Register a dummy service
        dummy_reg = await ctx.register_service("dummy", object(), {})

        # Pop information
        event, listeners = events.pop(0)

        # Check event
        assert isinstance(event, ServiceEvent)
        assert event.get_kind() == ServiceEvent.REGISTERED
        assert event.get_service_reference() is dummy_reg.get_reference()

        # No listeners are registered
        assert not listeners

        # Update the service
        await dummy_reg.set_properties({"hello": "world"})

        # Pop information
        event, listeners = events.pop(0)

        # Check event
        assert isinstance(event, ServiceEvent)
        assert event.get_kind() == ServiceEvent.MODIFIED
        assert event.get_service_reference() is dummy_reg.get_reference()

        # Unregister the service
        await dummy_reg.unregister()

        # Pop information
        event, listeners = events.pop(0)

        # Check event
        assert isinstance(event, ServiceEvent)
        assert event.get_kind() == ServiceEvent.UNREGISTERING
        assert event.get_service_reference() is dummy_reg.get_reference()

        # Unregister the hook
        await reg.unregister()

        # Register a new service
        await ctx.register_service("dummy", object(), {})

        # Hook must not be notified
        assert not events

        # Teardown
        await framework.stop()
        await framework.delete()

    @pytest.mark.asyncio
    async def test_hook(self):
        """
        Tests the hook filtering behaviour
        """
        # Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()

        self.bundle = None
        self.received = []

        # Add a bundle to have two contexts in the test
        fw_ctx = framework.get_bundle_context()
        bnd = await fw_ctx.install_bundle("tests.dummy_1")
        await bnd.start()
        bnd_ctx = bnd.get_bundle_context()

        # Setup a hook
        class Hook(object):
            @staticmethod
            async def event(svc_event, listeners_dict):
                to_remove = await svc_event.get_service_reference().get_property("to.remove")
                info_to_remove = []

                for listener_bc, listeners_info in listeners_dict.items():
                    # Check the dictionary content
                    for listener_info in listeners_info:
                        assert listener_bc is listener_info.bundle_context
                        assert listener_bc is listener_info.listener.context
                        assert listener_bc is listener_info.get_bundle_context()

                        if listener_info.listener in to_remove:
                            info_to_remove.append(listener_info)

                # Remove the requested listeners
                for listener_info in info_to_remove:
                    listeners_dict[listener_info.bundle_context].remove(listener_info)

        await fw_ctx.register_service(SERVICE_EVENT_LISTENER_HOOK, Hook(), {})

        # Register multiple listeners
        class Listener(object):
            def __init__(self, bc):
                self.context = bc
                self.storage = []
                asyncio.create_task(bc.add_service_listener(self))

            async def service_changed(self, event):
                self.storage.append(event)

        listener_referee = Listener(fw_ctx)
        listener_1 = Listener(fw_ctx)
        listener_2 = Listener(bnd_ctx)

        # Register a service that only the referee will get
        reg = await fw_ctx.register_service(
            "dummy", object(), {"to.remove": [listener_1, listener_2]})

        evt = listener_referee.storage.pop(0)
        assert evt.get_service_reference() is reg.get_reference()
        assert evt.get_kind() == ServiceEvent.REGISTERED
        assert not listener_1.storage
        assert not listener_2.storage

        # Modify it so that listener_1 gets it
        await reg.set_properties({"to.remove": [listener_2]})
        assert not listener_2.storage

        evt = listener_referee.storage.pop(0)
        assert evt.get_service_reference() is reg.get_reference()
        assert evt.get_kind() == ServiceEvent.MODIFIED

        evt1 = listener_1.storage.pop(0)
        assert evt1 is evt

        # Modify it so that listener_2, but not listener_1 gets it
        await reg.set_properties({"to.remove": [listener_1]})
        assert not listener_1.storage

        evt = listener_referee.storage.pop(0)
        assert evt.get_service_reference() is reg.get_reference()
        assert evt.get_kind() == ServiceEvent.MODIFIED

        evt2 = listener_2.storage.pop(0)
        assert evt2 is evt

        # Teardown
        await framework.stop()
        await framework.delete()

# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)
