#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Checks that the version of the project is declared consistently everywhere.

iPOPO declares its version in many places: ``pyproject.toml``, and, in every
module, a ``__version_info__`` tuple and a ``:version:`` docstring field. A
release bumps around 200 files by hand, so a single missed file is easy and
this script is the guard against it.

Called without argument, it only checks the consistency of the tree. Called
with a version (the release tag), it also checks that the tree declares that
exact version.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.2.2

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

import argparse
import pathlib
import re
import sys
from collections.abc import Iterator

import tomllib

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

#: Matches ``__version_info__ = (3, 2, 2)``
VERSION_INFO_PATTERN = re.compile(r"^__version_info__\s*=\s*\(([^)]*)\)", re.MULTILINE)

#: Matches the ``:version: 3.2.2`` field of a module docstring
VERSION_FIELD_PATTERN = re.compile(r"^:version:\s*(\S+)\s*$", re.MULTILINE)

#: Root of the repository, i.e. the parent of ``.github``
ROOT = pathlib.Path(__file__).resolve().parents[2]


def get_project_version() -> str:
    """
    Returns the version declared in ``pyproject.toml``
    """
    with open(ROOT / "pyproject.toml", "rb") as fp:
        return str(tomllib.load(fp)["project"]["version"])


def check_module(path: pathlib.Path, expected: str) -> Iterator[str]:
    """
    Checks the version declarations of a single module

    :param path: Path to the module to check
    :param expected: The version every declaration must match
    :return: A generator of error messages, empty if the module is valid
    """
    content = path.read_text(encoding="utf-8")
    relative = path.relative_to(ROOT)

    match = VERSION_INFO_PATTERN.search(content)
    if match is None:
        # Not every file carries a version: only report the ones that do and disagree
        return

    found = ".".join(part.strip() for part in match.group(1).split(","))
    if found != expected:
        yield f"{relative}: __version_info__ declares {found}, expected {expected}"

    field = VERSION_FIELD_PATTERN.search(content)
    if field is None:
        yield f"{relative}: no ':version:' field in the module docstring"
    elif field.group(1) != expected:
        yield f"{relative}: docstring says ':version: {field.group(1)}', expected {expected}"


def main() -> int:
    """
    Script entry point

    :return: The exit code of the script
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "tag",
        nargs="?",
        help="Release tag the declared version must match, e.g. 3.2.2",
    )
    parser.add_argument(
        "--package",
        default="pelix",
        help="Package to walk through (default: pelix)",
    )
    args = parser.parse_args()

    version = get_project_version()
    if args.tag is not None and args.tag != version:
        print(
            f"::error::Tag {args.tag} does not match the version declared in pyproject.toml ({version})",
            file=sys.stderr,
        )
        return 1

    errors = [
        error for path in sorted((ROOT / args.package).rglob("*.py")) for error in check_module(path, version)
    ]
    if errors:
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        print(f"{len(errors)} version inconsistencies found", file=sys.stderr)
        return 1

    print(f"Version {version} is declared consistently in {args.package}/ and pyproject.toml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
