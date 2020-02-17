#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Tests the "install packages" handling.

:author: Thomas Calmant, Angelo Cutaia
"""

# Standard library
import os
import pytest

# Pelix
from pelix.framework import FrameworkFactory, Bundle

from tests import log_off, log_on

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

SERVICE_BUNDLE = "tests.framework.service_bundle"
SIMPLE_BUNDLE = "tests.framework.simple_bundle"

# ------------------------------------------------------------------------------


def _list_modules(path, recursive=False):
    """
    Returns the set of path of modules that should have been installed

    :param path: An absolute path to look into
    :param recursive: If True, look into sub-folders
    :return: A set of absolute paths
    """
    results = set()
    for filename in os.listdir(path):
        if '__pycache__' in filename or '__main__' in filename:
            # Ignore cache and executable modules
            continue

        file_path = os.path.join(path, filename)
        if os.path.isdir(file_path) and recursive:
            # Look into sub-folders
            results.update(_list_modules(file_path))
        elif os.path.isfile(file_path):
            # Remove extension to avoid issues with cache files (.pyc)
            results.add(os.path.splitext(file_path)[0])

    return results


class TestPackages:
    """
    Pelix bundle packages installation tests
    """
    @pytest.mark.asyncio
    async def test_invalid_args(self):
        """
        Check error handling when the given path is wrong
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        for path in (None, "", "__nonexistent__", 123):
            with pytest.raises(ValueError):
                await context.install_package(path)

            # Check install visiting with a valid visitor
            with pytest.raises(ValueError):
                await context.install_visiting(path, lambda *x: True)

        # Check with invalid visitor
        with pytest.raises(ValueError):
            await context.install_visiting(os.path.abspath(os.path.dirname(__file__)), None)

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

        # Reset the environment variable
        os.environ['bundle.import.fail'] = "0"

    @pytest.mark.asyncio
    async def test_install_path(self):
        """
        Tries to install the "OK" package
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Get the path to the current test package
        test_root = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "vault")

        # List files in the "ok" package, avoiding cache
        ok_root = os.path.join(test_root, "pkg_ok")
        expected = _list_modules(ok_root, False)

        # Install the package
        bundles, failed = await context.install_package(ok_root)
        if failed:
            pytest.fail("Failed to install some packages: {}".format(failed))

        # Excepted bundles
        for bundle in bundles:
            # Check results
            assert isinstance(bundle, Bundle)
            expected.remove(os.path.splitext(
                os.path.abspath(bundle.get_location()))[0])

        if expected:
            pytest.fail("All bundles should have been installed. "
                      "Remaining: {}".format(expected))

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

        # Reset the environment variable
        os.environ['bundle.import.fail'] = "0"

    @pytest.mark.asyncio
    async def test_install_recursive(self):
        """
        Tries the recursive installation of a path
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Get the path to the current test package
        test_root = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "vault")

        # List files in the package and its children, avoiding cache
        ok_root = os.path.join(test_root, "pkg_ok")
        expected = _list_modules(ok_root, True)

        # Install the package
        bundles, failed = await context.install_package(ok_root, True)
        if failed:
            pytest.fail("Failed to install some packages: {}".format(failed))

        # Excepted bundles
        for bundle in bundles:
            # Check results
            assert isinstance(bundle, Bundle)
            expected.remove(os.path.splitext(
                os.path.abspath(bundle.get_location()))[0])

        if expected:
            pytest.fail("All bundles should have been installed. "
                      "Remaining: {}".format(expected))

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

        # Reset the environment variable
        os.environ['bundle.import.fail'] = "0"

    @pytest.mark.asyncio
    async def test_install_fail(self):
        """
        Tests the installation of a package with failures
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Get the path to the current test package
        test_root = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "vault")

        # List files in the package including failing modules, avoiding cache
        bad_root = os.path.join(test_root, "pkg_fail")
        expected = _list_modules(bad_root, False)

        # Install the package
        log_off()
        bundles, failed = await context.install_package(bad_root)
        log_on()

        if not failed:
            pytest.fail("No failure detection")

        for fail_module_name in failed:
            parts = fail_module_name.split('.')
            assert parts[0] == "pkg_fail", "No prefix set"
            assert parts[-1] == "invalid", "Wrong module failed"

        # Excepted bundles
        to_remove = [name for name in expected if "invalid" in name]
        expected.difference_update(to_remove)
        for bundle in bundles:
            # Check results
            assert isinstance(bundle, Bundle)
            expected.remove(os.path.splitext(
                os.path.abspath(bundle.get_location()))[0])

        if expected:
            pytest.fail("All bundles should have been installed. "
                      "Remaining: {}".format(expected))

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

        # Reset the environment variable
        os.environ['bundle.import.fail'] = "0"

    @pytest.mark.asyncio
    async def test_install_fail_recursive(self):
        """
        Tries the recursive installation of a path
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Get the path to the current test package
        test_root = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "vault")

        # List files in the package which will fail at first sight
        bad_root = os.path.join(test_root, "pkg_fail")
        expected = _list_modules(bad_root, False)

        # Install the package
        log_off()
        bundles, failed = await context.install_package(bad_root)
        log_on()

        if not failed:
            pytest.fail("No failure detection")

        for fail_module_name in failed:
            parts = fail_module_name.split('.')
            assert parts[0] == "pkg_fail", "No prefix set"
            assert parts[-1] == "invalid", "Wrong module failed"

        # Excepted bundles
        to_remove = [name for name in expected if "invalid" in name]
        expected.difference_update(to_remove)
        for bundle in bundles:
            # Check results
            assert isinstance(bundle, Bundle)
            expected.remove(os.path.splitext(
                os.path.abspath(bundle.get_location()))[0])

        if expected:
            pytest.fail("All bundles should have been installed. "
                      "Remaining: {}".format(expected))

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

        # Reset the environment variable
        os.environ['bundle.import.fail'] = "0"

    @pytest.mark.asyncio
    async def test_first_install_fail(self):
        """
        Tests the installation of a package with failures
        """
        #Setup
        framework = FrameworkFactory.get_framework()
        await framework.start()
        context = framework.get_bundle_context()

        # Get the path to the current test package
        test_root = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), "vault")

        # List files in the "ok" package, avoiding cache
        bad_root = os.path.join(test_root, "pkg_invalid")

        # Install the package
        log_off()
        bundles, failed = await context.install_package(bad_root)
        log_on()

        if bundles:
            pytest.fail("Some bundles were installed anyway")

        assert len(failed) == 1
        assert failed.pop() == "pkg_invalid"

        #Teardown
        await framework.stop()
        await FrameworkFactory.delete_framework()

        # Reset the environment variable
        os.environ['bundle.import.fail'] = "0"


if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)
