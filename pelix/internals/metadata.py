#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Reader of the bundle metadata, which doesn't import the bundle module.

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

import ast
import inspect
import logging
import os
import re
import tomllib
import types
from collections.abc import Mapping
from importlib.machinery import ModuleSpec
from typing import Any

from pelix.constants import BundleException

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["read_metadata"]

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

BLOCK_MARKER = ".. pelix-bundle"
"""Line starting the metadata block: an RST comment, hidden by Sphinx"""

SIDE_FILE_SUFFIX = ".manifest.toml"
"""Suffix of the side file, named after the last part of the bundle name"""

_BLOCK_START = re.compile(rf"^{re.escape(BLOCK_MARKER)}[ \t]*$", re.MULTILINE)

# Headers which must be strings when given
_STRING_HEADERS = ("symbolic-name", "version", "name", "description", "vendor", "license", "doc-url", "scm")


def _block_text(text: str) -> str | None:
    """
    Extracts the content of the metadata block of a module-level string

    :param text: A module-level string, with its indentation cleaned
    :return: The block content, or None if the string has no block
    """
    match = _BLOCK_START.search(text)
    if match is None:
        return None

    # Like an RST comment: the indented (or blank) lines following the marker
    lines = []
    for line in text[match.end() :].split("\n")[1:]:
        if line.strip() and not line.startswith((" ", "\t")):
            break
        lines.append(line)

    return inspect.cleandoc("\n".join(lines))


def _source_blocks(source: str) -> list[str]:
    """
    Looks for metadata blocks in the module-level strings of a source code

    :param source: The source code of a module
    :return: The content of all the blocks found
    :raise SyntaxError: Invalid source code
    """
    # Avoids parsing most of the modules
    if BLOCK_MARKER not in source:
        return []

    blocks = []
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            block = _block_text(inspect.cleandoc(node.value.value))
            if block is not None:
                blocks.append(block)

    return blocks


def _freeze(value: Any) -> Any:
    """
    Makes a value read from TOML immutable
    """
    if isinstance(value, dict):
        return types.MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def read_metadata(name: str, spec: ModuleSpec | None) -> Mapping[str, Any]:
    """
    Reads the metadata of a bundle, without executing its module.

    The metadata is a TOML block in a module-level string of the module (after
    a ``.. pelix-bundle`` line), or the ``<module>.manifest.toml`` file placed
    next to the module (inside the package, for a package).

    :param name: Name of the bundle module
    :param spec: Import specification of the module
    :return: An immutable mapping, empty if the module declares nothing
    :raise BundleException: Invalid metadata, or declared twice with
                            different contents
    """
    if spec is None or spec.loader is None:
        return types.MappingProxyType({})

    loader: Any = spec.loader
    try:
        # None for a module without source code (.pyc only, extension)
        source = loader.get_source(name) if hasattr(loader, "get_source") else None
    except ImportError:
        source = None

    try:
        blocks = _source_blocks(source) if source else []
    except SyntaxError as ex:
        raise BundleException(f"Can't read the metadata of {name}: {ex}") from ex

    if len(blocks) > 1:
        raise BundleException(f"More than one metadata block in {name}")

    texts = [(f"the module {name}", block) for block in blocks]

    if spec.origin and hasattr(loader, "get_data"):
        side_file = os.path.join(os.path.dirname(spec.origin), name.rpartition(".")[2] + SIDE_FILE_SUFFIX)
        try:
            texts.append((side_file, loader.get_data(side_file).decode("utf-8")))
        except OSError:
            pass

    try:
        parsed = [(origin, tomllib.loads(text)) for origin, text in texts]
    except tomllib.TOMLDecodeError as ex:
        raise BundleException(f"Invalid metadata of {name}: {ex}") from ex

    if len(parsed) > 1:
        origins = ", ".join(origin for origin, _ in parsed)
        if parsed[0][1] != parsed[1][1]:
            raise BundleException(f"Conflicting metadata for {name}: {origins}")

        _logger.warning("Metadata of %s declared twice with the same content: %s", name, origins)

    data = parsed[0][1] if parsed else {}
    for key in _STRING_HEADERS:
        if key in data and not isinstance(data[key], str):
            raise BundleException(f"Invalid metadata of {name}: '{key}' must be a string")

    if data.get("symbolic-name", name) != name:
        raise BundleException(f"Invalid metadata of {name}: symbolic-name is {data['symbolic-name']!r}")

    return _freeze(data)
