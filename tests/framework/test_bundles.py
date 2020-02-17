#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Tests the bundles handling.

:author: Thomas Calmant, Angelo Cutaia
"""

# Standard library
import os
import pytest


# Tests
from tests import log_on, log_off

# Pelix
from pelix.framework import FrameworkFactory, Bundle, BundleException, \
    BundleContext


# ------------------------------------------------------------------------------

__version__ = "2.0.0"

SERVICE_BUNDLE = "tests.framework.service_bundle"
SIMPLE_BUNDLE = "tests.framework.simple_bundle"

# ------------------------------------------------------------------------------


class TestBundle:
    """
    Pelix bundle registry tests
    """
    @pytest.mark.asyncio
    async def test_import_error(self):
        """
        Tries to install an invalid bundle
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Try to install the bundle
        with pytest.raises(BundleException):
            await context.install_bundle("//Invalid Name\\\\")

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_compatibility(self, test_bundle_id=False):
        """
        Tests a bundle installation + start + stop

        @param test_bundle_id: If True, also tests if the test bundle ID is 1
        """
        #SetUp
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()
        test_bundle_name = SIMPLE_BUNDLE

        # Install the bundle
        bundle_id = await context.install_bundle(test_bundle_name)
        bundle = await context.get_bundle(bundle_id)

        assert isinstance(bundle, Bundle)
        if test_bundle_id:
            assert bundle.get_bundle_id() == 1, "Not the first bundle in framework"

        # Get the internal module
        module_ = bundle.get_module()

        # Assert initial state
        assert module_.started is False, "Bundle should not be started yet"
        assert module_.stopped is False, "Bundle should not be stopped yet"

        # Activator
        await bundle.start()

        assert module_.started is True, "Bundle should be started now"
        assert module_.stopped is False, "Bundle should not be stopped yet"

        # De-activate
        await bundle.stop()

        assert module_.started is True, "Bundle should be changed"
        assert module_.stopped is True, "Bundle should be stopped now"

        # Uninstall (validated in another test)
        await bundle.uninstall()

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_liife_cycle(self, test_bundle_id=False):
        """
        Tests a bundle installation + start + stop

        @param test_bundle_id: If True, also tests if the test bundle ID is 1
        """
        #SetUp
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()
        test_bundle_name = SIMPLE_BUNDLE

        # Install the bundle
        bundle = await context.install_bundle(test_bundle_name)
        assert isinstance(bundle, Bundle)
        if test_bundle_id:
            assert bundle.get_bundle_id() == 1, "Not the first bundle in framework"

        # Get the internal module
        module_ = bundle.get_module()

        # Assert initial state
        assert module_.started is False, "Bundle should not be started yet"
        assert module_.stopped is False, "Bundle should not be stopped yet"

        # Activator
        await bundle.start()
        assert module_.started is True, "Bundle should be started now"
        assert module_.stopped is False, "Bundle should not be stopped yet"

        # De-activate
        await bundle.stop()
        assert module_.started is True, "Bundle should be changed"
        assert module_.stopped is True, "Bundle should be stopped now"

        # Uninstall (validated in another test)
        await bundle.uninstall()

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_life_cycle_recalls(self):
        """
        Tests a bundle installation + start + stop
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()
        test_bundle_name = SIMPLE_BUNDLE

        # Install the bundle
        bundle = await context.install_bundle(test_bundle_name)
        assert isinstance(bundle, Bundle)

        # Get the internal module
        module_ = bundle.get_module()

        # Assert initial state
        assert module_.started is False, "Bundle should not be started yet"
        assert module_.stopped is False, "Bundle should not be stopped yet"

        # Activator
        await bundle.start()
        assert bundle.get_state() == Bundle.ACTIVE, "Bundle should be considered active"
        assert module_.started is True, "Bundle should be started now"
        assert module_.stopped is False, "Bundle should not be stopped yet"

        # Recall activator
        module_.started = False
        await bundle.start()
        assert module_.started is False, "Bundle shouldn't be started twice"

        # Reset to previous state
        module_.started = True

        # De-activate
        await bundle.stop()
        assert bundle.get_state() != Bundle.ACTIVE, "Bundle shouldn't be considered active"
        assert module_.started is True, "Bundle should be changed"
        assert module_.stopped is True, "Bundle should be stopped now"

        # Recall activator
        module_.stopped = False
        await bundle.stop()
        assert module_.stopped is False, "Bundle shouldn't be stopped twice"

        # Uninstall (validated in another test)
        await bundle.uninstall()
        assert bundle.get_state() == Bundle.UNINSTALLED, "Bundle should be considered uninstalled"

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()


    @pytest.mark.asyncio
    async def test_life_cycle_exceptions(self):
        """
        Tests a bundle installation + start + stop
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()
        test_bundle_name = SIMPLE_BUNDLE

        # Install the bundle
        bundle = await context.install_bundle(test_bundle_name)
        assert isinstance(bundle, Bundle)

        # Get the internal module
        module_ = bundle.get_module()

        # Assert initial state
        assert module_.started is False, "Bundle should not be started yet"
        assert module_.stopped is False, "Bundle should not be stopped yet"

        # Activator with exception
        module_.raiser = True
        log_off()
        with pytest.raises(BundleException):
            await bundle.start()
        log_on()

        # Assert post-exception state
        assert bundle.get_state() != Bundle.ACTIVE, "Bundle shouldn't be considered active"
        assert module_.started is False, "Bundle should not be started yet"
        assert module_.stopped is False, "Bundle should not be stopped yet"

        # Activator, without exception
        module_.raiser = False
        await bundle.start()
        assert bundle.get_state() == Bundle.ACTIVE, "Bundle should be considered active"
        assert module_.started is True, "Bundle should be started now"
        assert module_.stopped is False, "Bundle should not be stopped yet"

        # De-activate with exception
        module_.raiser = True
        log_off()
        with pytest.raises(BundleException):
            await bundle.stop()
        log_on()
        assert bundle.get_state() != Bundle.ACTIVE, "Bundle shouldn't be considered active"
        assert module_.started is True, "Bundle should be changed"
        assert module_.stopped is False, "Bundle should be stopped now"

        # Uninstall (validated in another test)
        await bundle.uninstall()

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_uninstall_install(self):
        """
        Runs the life-cycle test twice.

        The bundle is installed then un-installed twice. started and stopped
        values of the bundle should be reset to False.

        Keeping two separate calls instead of using a loop allows to see at
        which pass the test have failed
        """
        # Pass 1: normal test
        await self.test_liife_cycle(True)

        # Pass 2: refresh test
        await self.test_liife_cycle(False)

    @pytest.mark.asyncio
    async def test_uninstall_with_start_stop(self):
        """
        Tests if a bundle is correctly uninstalled and if it is really
        unaccessible after its uninstallation.
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()
        test_bundle_name = SIMPLE_BUNDLE

        # Install the bundle
        bundle = await context.install_bundle(test_bundle_name)
        assert isinstance(bundle, Bundle)
        bid = bundle.get_bundle_id()
        assert bid == 1, "Invalid first bundle ID '{0:d}'".format(bid)

        # Test state
        assert bundle.get_state() == Bundle.RESOLVED, "Invalid fresh install state {0:d}".format(bundle.get_state())

        # Start
        await bundle.start()
        assert bundle.get_state() == Bundle.ACTIVE, "Invalid fresh start state {0:d}".format(bundle.get_state())

        # Stop
        await bundle.stop()
        assert bundle.get_state() == Bundle.RESOLVED, "Invalid fresh stop state {0:d}".format(bundle.get_state())

        # Uninstall
        await bundle.uninstall()
        assert bundle.get_state() == Bundle.UNINSTALLED, "Invalid fresh stop state {0:d}".format(bundle.get_state())

        # The bundle must not be accessible through the framework
        with pytest.raises(BundleException):
            await context.get_bundle(bid)

        with pytest.raises(BundleException):
            await framework.get_bundle_by_id(bid)

        assert await framework.get_bundle_by_name(test_bundle_name) is None, "Bundle is still accessible by name through the framework"

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

    @pytest.mark.asyncio
    async def test_update(self):
        """
        Tests a bundle update
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()
        bundle_content = """#!/usr/bin/python
# -- Content-Encoding: UTF-8 --

# Auto-generated bundle, for Pelix tests
__version__ = "{version}"
test_var = {test}

def test_fct():
    return {test}
"""

        # Compute the bundle full path
        simple_name = "generated_bundle"
        bundle_name = '{0}.{1}'.format(
            __name__.rsplit('.', 1)[0], simple_name)
        bundle_fullname = os.path.join(
            os.path.dirname(__file__), "{0}.py".format(simple_name))

        # 0/ Clean up existing files
        for suffix in ('', 'c', 'o'):
            path = "{0}{1}".format(bundle_fullname, suffix)
            if os.path.exists(path):
                os.remove(path)

        # 1/ Prepare the bundle, test variable is set to False
        with open(bundle_fullname, "w") as file:
            file.write(bundle_content.format(version="1.0.0", test=False))

        # 2/ Install the bundle and get its variable
        bundle = await context.install_bundle(bundle_name)
        module_ = bundle.get_module()

        # Also start the bundle
        await bundle.start()
        assert module_.test_var is False, "Test variable should be False"

        # 3/ Change the bundle file
        with open(bundle_fullname, "w") as file:
            file.write(bundle_content.format(version="1.0.1", test=True))

        # 4/ Update, keeping the module reference
        await bundle.update()
        assert module_ == bundle.get_module(), "Module has changed"
        assert module_.test_var is True, "Test variable should be True"

        # 5/ Change the bundle file, make it erroneous
        with open(bundle_fullname, "w") as file:
            file.write(bundle_content.format(version="1.0.2", test="\n"))

        # No error must be raised...
        log_off()
        await bundle.update()
        log_on()

        # ... but the state of the module shouldn't have changed
        assert module_.test_var is True, "Test variable should still be True"

        # Finally, change the test file to be a valid module
        # -> Used by coverage for its report
        with open(bundle_fullname, "w") as file:
            file.write(bundle_content.format(version="1.0.0", test=False))

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()


    @pytest.mark.asyncio
    async def test_version(self):
        """
        Tests if the version is correctly read from the bundle
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        test_bundle_name = SIMPLE_BUNDLE
        # File path, without extension
        test_bundle_loc = os.path.join(
            os.path.dirname(__file__), test_bundle_name.rsplit('.', 1)[1])

        # Install the bundle
        bundle = await framework.install_bundle(test_bundle_name)
        assert isinstance(bundle, Bundle)

        bid = bundle.get_bundle_id()
        assert bid == 1, "Invalid first bundle ID '{0:d}'".format(bid)

        # Get the internal module
        module_ = bundle.get_module()

        # Validate the bundle name
        assert bundle.get_symbolic_name() == test_bundle_name, "Names are different ({0} / {1})".format(
            bundle.get_symbolic_name(), test_bundle_name
            )

        # Validate get_location()
        bundle_without_ext = os.path.splitext(bundle.get_location())[0]
        full_bundle_path = os.path.abspath(bundle_without_ext)
        assert test_bundle_loc in (bundle_without_ext, full_bundle_path)

        # Validate the version number
        assert bundle.get_version() == module_.__version__, "Different versions found ({0} / {1})".format(
            bundle.get_version(), module_.__version__
            )

        # Remove the bundle
        await bundle.uninstall()

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()


# ------------------------------------------------------------------------------


class TestLocalBundle:
    """
    Tests the installation of the __main__ bundle
    """
    @pytest.mark.asyncio
    async def test_local_bundle(self):
        """
        Tests the correctness of the __main__ bundle objects in the framework
        """
        #SetUp
        framework = FrameworkFactory.get_framework()
        await framework.start()

        fw_context = framework.get_bundle_context()
        assert isinstance(fw_context, BundleContext)

        # Install local bundle in framework (for service installation & co)
        bundle = await fw_context.install_bundle(__name__)

        # Get a reference to the bundle, by name
        bundle_2 = await fw_context.get_framework().get_bundle_by_name(__name__)

        assert bundle is bundle_2, "Different bundle returned by ID and by name"

        # Validate the symbolic name
        assert bundle.get_symbolic_name() == __name__, "Bundle ({0}) and module ({1}) are different".format(
            bundle.get_symbolic_name(), __name__
            )

        # Validate get_bundle() via bundle context
        context_bundle = await bundle.get_bundle_context().get_bundle()
        assert bundle is context_bundle, "Not the same bundle:\n{0:d} / {1}\n{2:d} / {3}".format(
            id(bundle), bundle, id(context_bundle), context_bundle
            )

        # Validate get_version()
        assert bundle.get_version() == __version__, "Not the same version {0} -> {1}".format(
            __version__, bundle.get_version()
            )

        # Validate get_location()
        assert bundle.get_location() == __file__, "Not the same location {0} -> {1}".format(__file__, bundle.get_location())

        #TearDown
        await framework.stop()
        await FrameworkFactory.delete_framework()

# ------------------------------------------------------------------------------


if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)
