#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the initial configuration file handler

:author: Thomas Calmant
"""

import json
import os
import sys
import tempfile
import unittest
from typing import Any, Dict

from pelix.framework import FrameworkFactory
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.decorators import ComponentFactory, Property
from pelix.misc.init_handler import InitFileHandler, _Configuration

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class ConfigurationTest(unittest.TestCase):
    """
    Tests the configuration state bean
    """

    def setUp(self) -> None:
        self.config = _Configuration()

    def test_properties(self) -> None:
        """
        Tests the add/set of framework properties
        """
        # Invalid values are ignored
        self.config.add_properties(None)
        self.config.add_properties(["a", "b"])  # type: ignore
        self.assertDictEqual(self.config.properties, {})

        self.config.add_properties({"a": 1})
        self.config.add_properties({"b": 2})
        self.assertDictEqual(self.config.properties, {"a": 1, "b": 2})

        # Set clears the previous values
        self.config.set_properties({"c": 3})
        self.assertDictEqual(self.config.properties, {"c": 3})

    def test_environment(self) -> None:
        """
        Tests the add/set of environment variables
        """
        self.config.add_environment(None)
        self.config.add_environment({"env_a": "1"})
        self.config.add_environment({"env_b": "2"})

        # Set clears the previous values
        self.config.set_environment({"env_c": "3"})

        # Normalize applies the environment to os.environ
        self.assertNotIn("env_c", os.environ)
        try:
            self.config.normalize()
            self.assertNotIn("env_a", os.environ)
            self.assertNotIn("env_b", os.environ)
            self.assertEqual(os.environ.get("env_c"), "3")
        finally:
            os.environ.pop("env_c", None)

    def test_paths(self) -> None:
        """
        Tests the add/set of Python paths
        """
        self.config.add_paths(None)
        self.assertListEqual(self.config.paths, [])

        self.config.add_paths(["path_1"])
        self.config.add_paths(["path_2"])
        # New paths are prepended
        self.assertListEqual(self.config.paths, ["path_2", "path_1"])

        # Set clears the previous values
        self.config.set_paths(["path_3"])
        self.assertListEqual(self.config.paths, ["path_3"])

    def test_paths_normalization(self) -> None:
        """
        Tests the normalization of paths: only existing ones are kept,
        resolved and deduplicated
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            real_dir = os.path.realpath(tmp_dir)
            self.config.add_paths([tmp_dir, os.path.join(tmp_dir, "missing"), tmp_dir])
            self.config.normalize()
            self.assertListEqual(self.config.paths, [real_dir])

    def test_bundles(self) -> None:
        """
        Tests the add/set of bundle names
        """
        self.config.add_bundles(None)
        self.config.add_bundles(["bundle.a", "bundle.b"])
        self.config.add_bundles(["bundle.c", "bundle.a"])
        # Bundles are kept in addition order
        self.assertListEqual(self.config.bundles, ["bundle.a", "bundle.b", "bundle.c", "bundle.a"])

        # Normalization removes duplicates, keeping the first occurrence
        self.config.normalize()
        self.assertListEqual(self.config.bundles, ["bundle.a", "bundle.b", "bundle.c"])

        # Set clears the previous values
        self.config.set_bundles(["bundle.d"])
        self.assertListEqual(self.config.bundles, ["bundle.d"])

    def test_components(self) -> None:
        """
        Tests the add/set of component descriptions
        """
        self.config.add_components(None)
        self.config.add_components([{"name": "comp-a", "factory": "factory.a"}])
        self.config.add_components(
            [{"name": "comp-b", "factory": "factory.b", "properties": {"answer": 42}}]
        )
        self.assertDictEqual(
            self.config.components,
            {"comp-a": ("factory.a", {}), "comp-b": ("factory.b", {"answer": 42})},
        )

        # Missing mandatory entries
        self.assertRaises(KeyError, self.config.add_components, [{"name": "comp-c"}])
        self.assertRaises(KeyError, self.config.add_components, [{"factory": "factory.c"}])

        # Set clears the previous values
        self.config.set_components([{"name": "comp-d", "factory": "factory.d"}])
        self.assertDictEqual(self.config.components, {"comp-d": ("factory.d", {})})


# ------------------------------------------------------------------------------


TEST_FACTORY = "init.handler.test.factory"


@ComponentFactory(TEST_FACTORY)
@Property("_answer", "config.answer", 0)
class InitHandlerTestComponent:
    """
    Component factory instantiated from a configuration file
    """

    def __init__(self) -> None:
        self._answer = 0


class InitFileHandlerTest(unittest.TestCase):
    """
    Tests the initial configuration file handler
    """

    def setUp(self) -> None:
        self.handler = InitFileHandler()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def _write_conf(self, name: str, configuration: Dict[str, Any]) -> str:
        """
        Writes a configuration file in the temporary directory
        """
        filename = os.path.join(self.tmp_dir.name, name)
        with open(filename, "w") as out_file:
            json.dump(configuration, out_file)
        return filename

    def test_load_file(self) -> None:
        """
        Tests the loading of a single configuration file
        """
        filename = self._write_conf(
            "single.conf",
            {
                "properties": {"some.property": 12},
                "bundles": ["pelix.shell.core"],
                "components": [{"name": "comp", "factory": "factory", "properties": {"a": 1}}],
            },
        )

        self.assertTrue(self.handler.load(filename))
        self.assertDictEqual(self.handler.properties, {"some.property": 12})
        self.assertListEqual(self.handler.bundles, ["pelix.shell.core"])

        # Clear resets the state
        self.handler.clear()
        self.assertDictEqual(self.handler.properties, {})
        self.assertListEqual(self.handler.bundles, [])

    def test_merge_files(self) -> None:
        """
        Tests the merge of two configuration files (system-wide then user)
        """
        first = self._write_conf(
            "first.conf",
            {"properties": {"common": "first", "only.first": 1}, "bundles": ["bundle.a"]},
        )
        second = self._write_conf(
            "second.conf",
            {"properties": {"common": "second"}, "bundles": ["bundle.b"]},
        )

        self.assertTrue(self.handler.load(first))
        self.assertTrue(self.handler.load(second))

        # User-specific values override system-wide ones, bundles are appended
        self.assertDictEqual(self.handler.properties, {"common": "second", "only.first": 1})
        self.assertListEqual(self.handler.bundles, ["bundle.a", "bundle.b"])

    def test_reset_keys(self) -> None:
        """
        Tests the reset_* flags clearing previously loaded values
        """
        first = self._write_conf(
            "first.conf", {"properties": {"only.first": 1}, "bundles": ["bundle.a"]}
        )
        second = self._write_conf(
            "second.conf",
            {"reset_properties": True, "properties": {"fresh": 2}, "reset_bundles": True, "bundles": ["bundle.b"]},
        )

        self.handler.load(first)
        self.handler.load(second)

        self.assertDictEqual(self.handler.properties, {"fresh": 2})
        self.assertListEqual(self.handler.bundles, ["bundle.b"])

    def test_load_defaults(self) -> None:
        """
        Tests the loading of default files found in the default lookup paths
        """
        old_default_path = InitFileHandler.DEFAULT_PATH
        try:
            with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
                # No default file found
                InitFileHandler.DEFAULT_PATH = (first_dir, second_dir)
                self.assertFalse(self.handler.load())

                # Write a default file in each folder: both must be merged
                with open(os.path.join(first_dir, ".pelix.conf"), "w") as out_file:
                    json.dump({"bundles": ["bundle.a"]}, out_file)
                with open(os.path.join(second_dir, ".pelix.conf"), "w") as out_file:
                    json.dump({"bundles": ["bundle.b"]}, out_file)

                self.assertTrue(self.handler.load())
                self.assertListEqual(self.handler.bundles, ["bundle.a", "bundle.b"])
        finally:
            InitFileHandler.DEFAULT_PATH = old_default_path

    def test_load_yaml(self) -> None:
        """
        Tests the loading of a YAML configuration file
        """
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML is missing: can't test YAML configuration")

        filename = os.path.join(self.tmp_dir.name, "config.yaml")
        with open(filename, "w") as out_file:
            out_file.write("bundles:\n  - bundle.a\n  - bundle.b\n")

        self.assertTrue(self.handler.load(filename))
        self.assertListEqual(self.handler.bundles, ["bundle.a", "bundle.b"])

    def test_normalize_sys_path(self) -> None:
        """
        Tests that normalize() puts the working directory first in sys.path
        and adds the configured paths
        """
        old_sys_path = sys.path[:]
        try:
            filename = self._write_conf("paths.conf", {"paths": [self.tmp_dir.name]})
            self.handler.load(filename)
            self.handler.normalize()

            self.assertEqual(sys.path[0], ".")
            self.assertIn(os.path.realpath(self.tmp_dir.name), sys.path)
        finally:
            sys.path = old_sys_path

    def test_instantiate_components(self) -> None:
        """
        Tests the instantiation of the configured components
        """
        filename = self._write_conf(
            "components.conf",
            {
                "components": [
                    {"name": "init-test-component", "factory": TEST_FACTORY, "properties": {"config.answer": 42}}
                ]
            },
        )
        self.handler.load(filename)

        framework = FrameworkFactory.get_framework()
        self.addCleanup(FrameworkFactory.delete_framework)
        framework.start()
        context = framework.get_bundle_context()
        context.install_bundle("pelix.ipopo.core").start()

        with use_ipopo(context) as ipopo:
            ipopo.register_factory(context, InitHandlerTestComponent)

        self.handler.instantiate_components(context)

        with use_ipopo(context) as ipopo:
            details = ipopo.get_instance_details("init-test-component")
            self.assertEqual(details["factory"], TEST_FACTORY)
            # get_instance_details() converts property values to strings
            self.assertEqual(details["properties"]["config.answer"], "42")


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
