#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Loads and handles the Pelix initialization file

A configuration file is used to setup a Pelix framework. This module should
be used by shells to load a default configuration.

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2025 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import json
import os
import sys
from typing import Any, Dict, Generator, List, Optional, Tuple

from pelix.framework import BundleContext
from pelix.ipopo.constants import use_ipopo
from pelix.utilities import remove_duplicates

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"


# -----------------------------------------------------------------------------


class _Configuration:
    """
    Represents a configuration loaded from an initialization file
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self._properties: Dict[str, Any] = {}
        self._environment: Dict[str, str] = {}
        self._paths: List[str] = []

        self._bundles: List[str] = []
        self._components: Dict[str, Tuple[str, Dict[str, Any]]] = {}

    @property
    def properties(self) -> Dict[str, Any]:
        """
        Returns the configured framework properties

        :return: A dictionary of framework properties
        """
        return self._properties

    @property
    def paths(self) -> List[str]:
        """
        Returns the paths to add to sys.path

        :return: A list of paths
        """
        return self._paths

    @property
    def bundles(self) -> List[str]:
        """
        Returns the list of bundles to install and start

        :return: A list of names of bundles
        """
        return self._bundles

    @property
    def components(self) -> Dict[str, Tuple[str, Dict[str, Any]]]:
        """
        Returns the definitions of components as a dictionary of tuples.

        Keys are components names, whereas values are (factory, properties)
        tuples

        :return: A name→(factory, properties) dictionary
        """
        return self._components

    def add_properties(self, properties: Optional[Dict[str, Any]]) -> None:
        """
        Updates the framework properties dictionary

        :param properties: New framework properties to add
        """
        if isinstance(properties, dict):
            self._properties.update(properties)

    def set_properties(self, properties: Optional[Dict[str, Any]]) -> None:
        """
        Sets the framework properties dictionary

        :param properties: Framework properties to set
        """
        self._properties = {}
        self.add_properties(properties)

    def add_environment(self, environ: Optional[Dict[str, str]]) -> None:
        """
        Updates the environment dictionary with the given one.

        Existing entries are overridden by the given ones

        :param environ: New environment variables
        """
        if isinstance(environ, dict):
            self._environment.update(environ)

    def set_environment(self, environ: Optional[Dict[str, str]]) -> None:
        """
        Updates the environment dictionary with the given one.
        Cancels the variables previously set.

        :param environ: New environment variables
        """
        self._environment = {}
        self.add_environment(environ)

    def add_paths(self, paths: Optional[List[str]]) -> None:
        """
        Adds entries to the Python path.

        The given paths are normalized before being added to the left of the
        list

        :param paths: New paths to add
        """
        if paths:
            # Use new paths in priority
            self._paths = list(paths) + self._paths

    def set_paths(self, paths: Optional[List[str]]) -> None:
        """
        Adds entries to the Python path.

        The given paths are normalized before being added to the left of the
        Python path.
        Previous paths from configuration files are cleared.

        :param paths: New paths to add
        """
        del self._paths[:]
        self.add_paths(paths)

    def add_bundles(self, bundles: Optional[List[str]]) -> None:
        """
        Adds a list of bundles to install.

        Contrary to paths and environment variables, the bundles are kept in
        the system-wide to user-specific order.

        :param bundles: A list of bundles to install
        """
        if bundles:
            self._bundles.extend(bundles)

    def set_bundles(self, bundles: Optional[List[str]]) -> None:
        """
        Adds a list of bundles to install.
        Previous names from configuration files are cleared.

        Contrary to paths and environment variables, the bundles are kept in
        the system-wide to user-specific order.

        :param bundles: A list of bundles to install
        """
        del self._bundles[:]
        self.add_bundles(bundles)

    def add_components(self, components: Optional[List[Dict[str, Any]]]) -> None:
        """
        Adds a list of components to instantiate

        :param components: The description of components
        :raise KeyError: Missing component configuration
        """
        if components:
            for component in components:
                self._components[component["name"]] = (
                    component["factory"],
                    component.get("properties", {}),
                )

    def set_components(self, components: Optional[List[Dict[str, Any]]]) -> None:
        """
        Adds a list of components to instantiate.
        Removes the previously configured components descriptions.

        :param components: The description of components
        :raise KeyError: Missing component configuration
        """
        self._components.clear()
        self.add_components(components)

    def normalize(self) -> None:
        """
        Normalizes environment variables, paths and filters the lists of
        bundles to install and start.

        After this call, the environment variables of this process will have
        been updated.
        """
        # Add environment variables
        os.environ.update(self._environment)

        # Normalize paths and avoid duplicates
        self._paths = remove_duplicates(
            os.path.realpath(os.path.expanduser(os.path.expandvars(path)))
            for path in self._paths
            if os.path.exists(path)
        )

        # Normalize the lists of bundles
        self._bundles = remove_duplicates(self._bundles)


class InitFileHandler:
    """
    Parses and handles the instructions of initial configuration files
    """

    DEFAULT_PATH: Tuple[str, ...] = (
        "/etc/default",
        "/etc",
        "/usr/local/etc",
        "~/.local/pelix",
        "~/.config",
        "~",
        ".",
    )
    """
    Default path where to find the configuration file.
    Order is from system wide to user specific configuration.
    """

    def __init__(self) -> None:
        # The internal state
        self.__state = _Configuration()

    @property
    def bundles(self) -> List[str]:
        """
        :return: The list of names of bundles to install and start
        """
        return self.__state.bundles

    @property
    def properties(self) -> Dict[str, Any]:
        """
        :return: The initial framework properties
        """
        return self.__state.properties

    def clear(self) -> None:
        """
        Clears the current internal state (cleans up all loaded content)
        """
        # Reset the internal state
        self.__state = _Configuration()

    def find_default(self, filename: str) -> Generator[str, None, None]:
        """
        A generate which looks in common folders for the default configuration
        file. The paths goes from system defaults to user specific files.

        :param filename: The name of the file to find
        :return: The complete path to the found files
        """
        for path in self.DEFAULT_PATH:
            # Normalize path
            path = os.path.expanduser(os.path.expandvars(path))
            fullname = os.path.realpath(os.path.join(path, filename))

            if os.path.exists(fullname) and os.path.isfile(fullname):
                yield fullname

    def load(self, filename: Optional[str] = None) -> bool:
        """
        Loads the given file and adds its content to the current state.
        This method can be called multiple times to merge different files.

        If no filename is given, this method loads all default files found.
        It returns False if no default configuration file has been found

        :param filename: The file to load
        :return: True if the file has been correctly parsed, False if no file
                 was given and no default file exist
        :raise IOError: Error loading file
        """
        if not filename:
            at_least_one = False
            for name in self.find_default(".pelix.conf"):
                at_least_one |= self.load(name)
            return at_least_one
        else:
            _, file_extension = os.path.splitext(filename)
            with open(filename, "r") as filep:
                if file_extension == ".yaml" or file_extension == ".yml":
                    try:
                        import yaml

                        self.__parse(yaml.safe_load(filep))
                    except ImportError:
                        raise IOError("Couldn't parse YAML configuration: YAML parser not available")
                else:
                    self.__parse(json.load(filep))
            return True

    def __parse(self, configuration: Dict[str, Any]) -> None:
        """
        Parses the given configuration dictionary

        :param configuration: A configuration as a dictionary (JSON object)
        """
        for entry in (
            "properties",
            "environment",
            "paths",
            "bundles",
            "components",
        ):
            # Check if current values must be reset
            reset_key = f"reset_{entry}"

            # Compute the name of the method
            call_name = "add" if not configuration.get(reset_key) else "set"
            method = getattr(self.__state, f"{call_name}_{entry}")

            # Update configuration
            method(configuration.get(entry))

    def normalize(self) -> None:
        """
        Normalizes environment variables and the Python path.

        This method first updates the environment variables (``os.environ``).
        Then, it normalizes the Python path (``sys.path``) by resolving all
        references to the user directory and environment variables.
        """
        # Normalize configuration
        self.__state.normalize()

        # Update sys.path, avoiding duplicates
        whole_path = list(self.__state.paths)
        whole_path.extend(sys.path)

        # Ensure the working directory as first search path
        sys.path = ["."]
        for path in whole_path:
            if path not in sys.path:
                sys.path.append(path)

    def instantiate_components(self, context: BundleContext) -> None:
        """
        Instantiate the defined components

        .. note::
           This method requires the iPOPO core service to be registered.
           This means that the ``pelix.ipopo.core`` must have been declared in
           the list of bundles (or installed and started programmatically).

        :param context: A :class:`~pelix.framework.BundleContext` object
        :raise BundleException: Error looking for the iPOPO service or
                                starting a component
        """
        with use_ipopo(context) as ipopo:
            for name, (factory, properties) in self.__state.components.items():
                ipopo.instantiate(factory, name, properties)
