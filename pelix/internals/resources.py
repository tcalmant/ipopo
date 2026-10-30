#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Access to the resource files of a bundle.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.3.0

..

    Copyright 2026 Thomas Calmant

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

import fnmatch
import importlib.resources
import pathlib
import zipfile
import zipimport
from importlib.machinery import ModuleSpec
from importlib.resources.abc import Traversable

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["RESOURCES_SUFFIX", "find_entries", "get_entry", "get_root"]

RESOURCES_SUFFIX = ".res"
"""Suffix of the directory holding the resources of a module bundle"""

# ------------------------------------------------------------------------------


def get_root(name: str, spec: ModuleSpec | None) -> Traversable | None:
    """
    Finds the root of the resources of a bundle: the package itself for a
    package, the ``<module>.res`` sibling directory for a module. The dot
    prevents this directory from ever being imported as a package.

    :param name: Name of the bundle module
    :param spec: Import specification of the module
    :return: The root, or None if the bundle has no resource
    """
    if spec is None:
        return None

    if spec.submodule_search_locations is not None:
        return importlib.resources.files(name)

    if not spec.origin:
        return None

    directory = name.rpartition(".")[2] + RESOURCES_SUFFIX
    if isinstance(spec.loader, zipimport.zipimporter):
        root: Traversable = zipfile.Path(spec.loader.archive, f"{spec.loader.prefix}{directory}/")
    else:
        root = pathlib.Path(spec.origin).with_name(directory)

    return root if root.is_dir() else None


def _split(path: str) -> list[str]:
    """
    Splits a relative resource path, refusing the ones leaving the root

    :param path: A "/" separated path
    :return: The names in the path
    :raise ValueError: Absolute path, or path containing ".."
    """
    if path.startswith(("/", "\\")) or ":" in path.split("/")[0]:
        raise ValueError(f"Absolute resource path: {path!r}")

    names = [name for name in path.split("/") if name not in ("", ".")]
    if ".." in names or any("\\" in name for name in names):
        raise ValueError(f"Invalid resource path: {path!r}")

    return names


def get_entry(root: Traversable | None, path: str) -> Traversable | None:
    """
    Looks for a file or a directory in the resources of a bundle

    :param root: Root of the resources
    :param path: Path of the entry, relative to the root
    :return: The entry, or None if it doesn't exist
    :raise ValueError: Absolute path, or path containing ".."
    """
    names = _split(path)
    if root is None:
        return None

    entry = root.joinpath(*names) if names else root
    return entry if entry.is_file() or entry.is_dir() else None


def find_entries(root: Traversable | None, path: str, pattern: str, recurse: bool) -> list[str]:
    """
    Looks for files in the resources of a bundle

    :param root: Root of the resources
    :param path: Directory to look into, relative to the root
    :param pattern: ``fnmatch`` pattern of the file names
    :param recurse: If True, looks into the sub-directories too
    :return: The sorted paths of the files found, relative to the root
    :raise ValueError: Absolute path, or path containing ".."
    """
    names = _split(path)
    directory = get_entry(root, path)
    if directory is None or not directory.is_dir():
        return []

    found: list[str] = []

    def walk(current: Traversable, prefix: list[str]) -> None:
        for child in current.iterdir():
            if child.is_dir():
                if recurse:
                    walk(child, [*prefix, child.name])
            elif fnmatch.fnmatchcase(child.name, pattern):
                found.append("/".join([*prefix, child.name]))

    walk(directory, names)
    return sorted(found)
