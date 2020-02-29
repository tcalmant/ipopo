#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Pelix framework test module. Tests the framework, bundles handling, service
handling and events.

:author: Thomas Calmant, Angelo Cutaia
"""

# Standard library
import os
import sys
import asyncio
import time
import pytest

# Tests
from tests import log_on, log_off

# Pelix
from pelix.framework import FrameworkFactory, Bundle, BundleException, \
    BundleContext


# ------------------------------------------------------------------------------

__version__ = "1.0.0"

SIMPLE_BUNDLE = "tests.framework.simple_bundle"

# ------------------------------------------------------------------------------


async def _framework_killer(framework, wait_time):
    """
    Waits *time* seconds before calling framework.stop().

    :param framework: Framework to stop
    :param wait_time: Time to wait (seconds) before stopping the framework
    """
    await asyncio.sleep(wait_time)
    await framework.stop()


class TestFramework:
    """
    Tests the framework factory properties
    """
    stopping = False

    @pytest.mark.asyncio
    async def test_bundle_zero(self):
        """
        Tests if bundle 0 is the framework
        """
        framework = FrameworkFactory.get_framework()

        assert await framework.get_bundle_by_name(None) is None, "None name is not bundle 0"

        assert framework is await framework.get_bundle_by_id(0), "Invalid bundle 0"

        pelix_name = framework.get_symbolic_name()
        assert framework is await framework.get_bundle_by_name(pelix_name), "Invalid system bundle name"

        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_bundle_start(self):
        """
        Tests if a bundle can be started before the framework itself
        """
        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()
        assert isinstance(context, BundleContext)

        # Install a bundle
        bundle = await context.install_bundle(SIMPLE_BUNDLE)

        assert bundle.get_state() == Bundle.RESOLVED, "Bundle should be in RESOLVED state"

        # Starting the bundle now should fail
        with pytest.raises(BundleException):
            await bundle.start()
        assert bundle.get_state() == Bundle.RESOLVED, "Bundle should be in RESOLVED state"

        # Start the framework
        await framework.start()

        # Bundle should have been started now
        assert bundle.get_state() == Bundle.ACTIVE, "Bundle should be in ACTIVE state"

        # Stop the framework
        await framework.stop()

        assert bundle.get_state() == Bundle.RESOLVED, "Bundle should be in RESOLVED state"

        # Try to start the bundle again (must fail)
        with pytest.raises(BundleException):
            await bundle.start()
        assert bundle.get_state() == Bundle.RESOLVED, "Bundle should be in RESOLVED state"

        await FrameworkFactory.delete_framework()

        if SIMPLE_BUNDLE in sys.modules:
            del sys.modules[SIMPLE_BUNDLE]

    @pytest.mark.asyncio
    async def test_framework_doublestart(self):
        """
        Tests double calls to start and stop
        """
        self.stopping = False

        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()

        # Register the stop listener
        await context.add_framework_stop_listener(self)

        assert await framework.start() is True, "Framework couldn't be started"
        assert await framework.start() is False, "Framework started twice"

        # Stop the framework
        assert await framework.stop() is True, "Framework couldn't be stopped"
        assert self.stopping is True, "Stop listener not called"
        self.stopping = False

        assert await framework.stop() is False, "Framework stopped twice"
        assert self.stopping is False, "Stop listener called twice"

        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_framework_restart(self):
        """
        Tests call to Framework.update(), that restarts the framework
        """
        self.stopping = False
        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()

        # Register the stop listener
        await context.add_framework_stop_listener(self)

        # Calling update while the framework is stopped should do nothing
        await framework.update()
        assert self.stopping is False, "Stop listener called"

        # Start and update the framework
        assert await framework.start() is True, "Framework couldn't be started"

        await framework.update()

        # The framework must have been stopped and must be active
        assert self.stopping is True, "Stop listener not called"
        assert framework.get_state() == Bundle.ACTIVE, "Framework hasn't been restarted"

        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_framework_start_raiser(self):
        """
        Tests framework start and stop with a bundle raising exception
        """
        self.stopping = False

        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()

        # Register the stop listener
        await context.add_framework_stop_listener(self)

        # Install the bundle
        bundle = await context.install_bundle(SIMPLE_BUNDLE)
        module_ = bundle.get_module()

        # Set module in raiser mode
        module_.raiser = True

        # Framework can start...
        log_off()
        assert await framework.start() is True, "Framework should be started"
        log_on()

        assert framework.get_state() == Bundle.ACTIVE, "Framework should be in ACTIVE state"

        assert bundle.get_state() == Bundle.RESOLVED, "Bundle should be in RESOLVED state"

        # Stop the framework
        assert await framework.stop() is True, "Framework should be stopped"

        # Remove raiser mode
        module_.raiser = False

        # Framework can start
        assert await framework.start() is True, "Framework couldn't be started"
        assert framework.get_state() == Bundle.ACTIVE, "Framework should be in ACTIVE state"
        assert bundle.get_state() == Bundle.ACTIVE, "Bundle should be in ACTIVE state"

        # Set module in raiser mode
        module_.raiser = True

        # Stop the framework
        log_off()
        assert await framework.stop() is True, "Framework couldn't be stopped"
        log_on()

        assert self.stopping is True, "Stop listener not called"

        await FrameworkFactory.delete_framework()

        if SIMPLE_BUNDLE in sys.modules:
            del sys.modules[SIMPLE_BUNDLE]

    @pytest.mark.asyncio
    async def test_frameworkstop_raiser(self):
        """
        Tests framework start and stop with a bundle raising exception
        """
        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()

        # Register the stop listener
        await context.add_framework_stop_listener(self)

        # Install the bundle
        bundle = await context.install_bundle(SIMPLE_BUNDLE)
        module_ = bundle.get_module()

        # Set module in non-raiser mode
        module_.raiser = False

        # Framework can start...
        log_off()
        assert await framework.start() is True, "Framework should be started"
        assert framework.get_state() == Bundle.ACTIVE, "Framework should be in ACTIVE state"
        assert bundle.get_state() == Bundle.ACTIVE, "Bundle should be in ACTIVE state"
        log_on()

        # Set module in raiser mode
        module_.raiser = True

        # Bundle must raise the exception and stay active
        log_off()
        with pytest.raises(BundleException):
            await bundle.stop()
        assert bundle.get_state() == Bundle.RESOLVED, "Bundle should be in RESOLVED state"
        log_on()

        # Stop framework
        await framework.stop()
        await FrameworkFactory.delete_framework()

        if SIMPLE_BUNDLE in sys.modules:
            del sys.modules[SIMPLE_BUNDLE]

    @pytest.mark.asyncio
    async def test_framework_stopper(self):
        """
        Tests FrameworkException stop flag handling
        """
        framework = FrameworkFactory.get_framework()
        context = framework.get_bundle_context()

        # Install the bundle
        bundle = await context.install_bundle(SIMPLE_BUNDLE)
        module_ = bundle.get_module()

        # Set module in raiser stop mode
        module_.fw_raiser = True
        module_.fw_raiser_stop = True

        log_off()
        assert await framework.start() is False, "Framework should be stopped"
        assert framework.get_state() == Bundle.RESOLVED, "Framework should be stopped"
        assert bundle.get_state() == Bundle.RESOLVED, "Bundle should be stopped"
        log_on()

        # Set module in raiser non-stop mode
        module_.fw_raiser_stop = False

        log_off()
        assert await framework.start() is True, "Framework should be stopped"
        assert framework.get_state() == Bundle.ACTIVE, "Framework should be started"
        assert bundle.get_state() == Bundle.RESOLVED, "Bundle should be stopped"
        log_on()

        # Start the module
        module_.fw_raiser = False
        await bundle.start()
        assert bundle.get_state() == Bundle.ACTIVE, "Bundle should be active"

        # Set module in raiser mode
        module_.fw_raiser = True
        module_.fw_raiser_stop = True

        # Stop the framework
        log_off()
        assert await framework.stop() is True, "Framework couldn't be stopped"
        assert framework.get_state() == Bundle.RESOLVED, "Framework should be stopped"
        assert bundle.get_state() == Bundle.RESOLVED, "Bundle should be stopped"
        log_on()

        await FrameworkFactory.delete_framework()

        if SIMPLE_BUNDLE in sys.modules:
            del sys.modules[SIMPLE_BUNDLE]

    @pytest.mark.asyncio
    async def test_properties_with_preset(self):
        """
        Test framework properties
        """
        pelix_test_name = "PELIX_TEST"
        pelix_test = "42"
        pelix_test_2 = "421"

        # Test with pre-set properties
        props = {pelix_test_name: pelix_test}
        framework = FrameworkFactory.get_framework(props)

        assert await framework.get_property(pelix_test_name) == pelix_test, "Invalid property value (preset value not set)"

        # Pre-set property has priority
        os.environ[pelix_test_name] = pelix_test_2
        assert await framework.get_property(pelix_test_name) == pelix_test, "Invalid property value (preset has priority)"
        del os.environ[pelix_test_name]

        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_properties_without_preset(self):
        """
        Test framework properties
        """
        pelix_test_name = "PELIX_TEST"
        pelix_test = "42"

        # Test without pre-set properties
        framework = FrameworkFactory.get_framework()

        assert await framework.get_property(pelix_test_name) is None, "Magic property value"

        os.environ[pelix_test_name] = pelix_test
        assert await framework.get_property(pelix_test_name) == pelix_test, "Invalid property value"
        del os.environ[pelix_test_name]

        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_added_property(self):
        """
        Tests the add_property method
        """
        pelix_test_name = "PELIX_TEST"
        pelix_test = "42"
        pelix_test_2 = "123"

        # Test without pre-set properties
        framework = FrameworkFactory.get_framework()

        assert await framework.get_property(pelix_test_name) is None, "Magic property value"

        # Add the property
        assert await framework.add_property(pelix_test_name, pelix_test) is True, "add_property shouldn't fail on first call"

        assert await framework.get_property(pelix_test_name) == pelix_test, "Invalid property value"

        # Update the property (must fail)
        assert await framework.add_property(pelix_test_name, pelix_test_2) is False, "add_property must fail on second call"

        assert await framework.get_property(pelix_test_name) == pelix_test, "Invalid property value"

        await FrameworkFactory.delete_framework()

    async def framework_stopping(self):
        """
        Called when framework is stopping
        """
        self.stopping = True

    @pytest.mark.asyncio
    async def test_stop_listener(self):
        """
        Test the framework stop event
        """
        self.stopping = False
        # Set up a framework
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Assert initial state
        assert self.stopping is False, "Invalid initial state"

        # Register the stop listener
        assert await context.add_framework_stop_listener(self) is True, "Can't register the stop listener"

        log_off()
        assert await context.add_framework_stop_listener(self) is False, "Stop listener registered twice"
        log_on()

        # Assert running state
        assert self.stopping is False, "Invalid running state"

        # Stop the framework
        await framework.stop()

        # Assert the listener has been called
        assert self.stopping is True, "Stop listener hasn't been called"

        # Unregister the listener
        assert await context.remove_framework_stop_listener(self) is True, "Can't unregister the stop listener"

        log_off()
        assert await context.remove_framework_stop_listener(self) is False, "Stop listener unregistered twice"
        log_on()

        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_uninstall(self):
        """
        Tests if the framework raises an exception if uninstall() is called
        """
        # Set up a framework
        framework = FrameworkFactory.get_framework()
        with pytest.raises(BundleException):
            await framework.uninstall()

        # Even once started...
        await framework.start()
        with pytest.raises(BundleException):
            await framework.uninstall()
        await framework.stop()

        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_wait_for_stop(self):
        """
        Tests the wait_for_stop() method
        """
        # Set up a framework
        framework = FrameworkFactory.get_framework()

        # No need to wait for the framework...
        assert await framework.wait_for_stop() is True, "wait_for_stop() must return True on stopped framework"

        # Start the framework
        await framework.start()

        # Start the framework killer
        asyncio.create_task(_framework_killer(framework, 0.5))

        # Wait for stop
        start = time.time()
        assert await framework.wait_for_stop() is True, "wait_for_stop(None) should return True"
        end = time.time()
        assert (end - start) < 1, "Wait should be less than 1 sec"

        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_wait_for_stop_timeout(self):
        """
        Tests the wait_for_stop() method
        """
        # Set up a framework
        framework = FrameworkFactory.get_framework()
        await framework.start()

        # Schedule the framework killer
        asyncio.create_task(_framework_killer(framework, 0.5))

        # Wait for stop (timeout not raised)
        start = time.time()
        assert await framework.wait_for_stop(1) is True, "wait_for_stop() should return True"
        end = time.time()
        assert (end - start) < 1, "Wait should be less than 1 sec"

        # Restart framework
        await framework.start()

        # Schedule the framework killer
        asyncio.create_task(_framework_killer(framework, 2))

        # Wait for stop (timeout raised)
        start = time.time()
        assert await framework.wait_for_stop(1) is False, "wait_for_stop() should return False"
        end = time.time()
        assert (end - start) < 1.2, "Wait should be less than 1.2 sec"

        # Wait for framework to really stop
        await framework.wait_for_stop()

        await FrameworkFactory.delete_framework()

# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)
