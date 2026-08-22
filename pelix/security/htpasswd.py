#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Credential store over an Apache ``.htpasswd`` file, with the groups of a matching
``.htgroup``.

One component provides both halves: the password file and the group file are two
properties of the same factory, so the simplest deployment adds one bundle rather than
two.

Both files are parsed as a whole when they are loaded, not entry by entry at login: an
entry this build cannot verify is reported with its file and line number at deploy time
and the user is left **absent**, rather than present and unverifiable. A load-time
failure is found by the operator; a login-time failure is found by a user at three in
the morning.

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

import contextlib
import logging
import os
from collections.abc import Iterable
from typing import TYPE_CHECKING

from pelix import services
from pelix.ipopo.decorators import ComponentFactory, Invalidate, Property, Provides, Validate
from pelix.security import (
    FACTORY_HTPASSWD,
    PROP_CREDENTIAL_KINDS,
    PROP_HTPASSWD_FILE,
    PROP_HTPASSWD_GROUPS,
    PROP_HTPASSWD_PLAINTEXT,
    AuthenticationFailed,
    Authenticator,
    Credentials,
    MembershipProvider,
    Subject,
    UsernamePassword,
    _crypt,
)

if TYPE_CHECKING:
    from pelix.framework import BundleContext

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

# Permission bits which must not be set on a password file: it is readable by somebody
# other than its owner
_SHARED_MODE_BITS = 0o077

# ------------------------------------------------------------------------------


def parse_htpasswd(
    lines: Iterable[str], path: str, allow_plaintext: bool = False
) -> tuple[dict[str, str], int]:
    """
    Parses the content of a ``.htpasswd`` file: ``user:hash`` per line, ``#`` comments.

    A hash this build cannot verify is reported and its user left out, so that nothing
    can be present and unverifiable at the same time.

    :param lines: The lines of the file
    :param path: Path of the file, for the messages
    :param allow_plaintext: Accept an unrecognized hash as a plaintext password
    :return: The users and their stored hash, and the number of skipped entries
    """
    users: dict[str, str] = {}
    skipped = 0

    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        name, separator, stored = line.partition(":")
        if not separator or not name or not stored:
            _logger.warning("%s:%d: ignoring a line which is not 'user:hash'", path, number)
            skipped += 1
            continue

        try:
            scheme = _crypt.classify(stored)
        except _crypt.UnsupportedHash as ex:
            # Never the hash itself, only what it is and where it is
            _logger.warning("%s:%d: ignoring user '%s': %s", path, number, name, ex)
            skipped += 1
            continue

        if scheme == _crypt.Scheme.PLAINTEXT and not allow_plaintext:
            _logger.warning(
                "%s:%d: ignoring user '%s': unrecognized hash format. Set '%s' to true if this "
                "really is a plaintext password",
                path,
                number,
                name,
                PROP_HTPASSWD_PLAINTEXT,
            )
            skipped += 1
            continue

        if scheme in _crypt.WEAK_SCHEMES:
            _logger.warning(
                "%s:%d: user '%s' uses the weak '%s' scheme: an offline copy of this file is "
                "cracked quickly. Re-hash it with: htpasswd -5",
                path,
                number,
                name,
                scheme.value,
            )

        # User names are compared exactly, which is what Apache itself does with these
        # files: nothing is transformed on the way in
        users[name] = stored

    return users, skipped


def parse_htgroup(lines: Iterable[str], path: str) -> dict[str, set[str]]:
    """
    Parses the content of a ``.htgroup`` file: ``groupname: user1 user2`` per line,
    ``#`` comments, and a user may appear in several lines.

    There is no nesting, deliberately: refusing a membership graph is what keeps a
    subject a flat immutable snapshot.

    :param lines: The lines of the file
    :param path: Path of the file, for the messages
    :return: The groups of each user
    """
    groups_of: dict[str, set[str]] = {}

    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        group, separator, members = line.partition(":")
        if not separator or not group:
            _logger.warning("%s:%d: ignoring a line which is not 'group: users'", path, number)
            continue

        for member in members.split():
            groups_of.setdefault(member, set()).add(group)

    return groups_of


def _read_lines(path: str) -> list[str] | None:
    """
    Reads a file, reporting rather than raising.

    :param path: Path of the file
    :return: Its lines, or None if it could not be read or is empty
    """
    try:
        with open(path, encoding="utf-8") as file:
            lines = file.readlines()
    except OSError as ex:
        _logger.error("Error reading %s: %s", path, ex)
        return None

    if not any(line.strip() for line in lines):
        # Far more likely a partial write than an intentional revocation of everyone
        _logger.error("%s is empty: keeping the previous content", path)
        return None

    return lines


def _warn_about_file_mode(path: str) -> None:
    """
    Warns when a password file is readable by somebody other than its owner.

    :param path: Path of the file
    """
    if os.name != "posix":
        return

    try:
        mode = os.stat(path).st_mode
    except OSError:
        return

    if mode & _SHARED_MODE_BITS:
        _logger.warning("%s is readable by other users (mode %o): run chmod 600 on it", path, mode & 0o777)


# ------------------------------------------------------------------------------


@ComponentFactory(FACTORY_HTPASSWD)
@Provides([Authenticator, MembershipProvider, services.FileInstallListener])
@Property("_credential_kinds", PROP_CREDENTIAL_KINDS, ("password",))
@Property("_users_path", PROP_HTPASSWD_FILE)
@Property("_groups_path", PROP_HTPASSWD_GROUPS)
@Property("_allow_plaintext", PROP_HTPASSWD_PLAINTEXT, False)
@Property("_watched_folder", services.PROP_FILEINSTALL_FOLDER)
class HtpasswdStore(Authenticator, MembershipProvider, services.FileInstallListener):
    """
    Authenticates against a ``.htpasswd`` file and reports the groups of a ``.htgroup``.

    Both files are reloaded through the File Install service when it is available. When
    it is not, they are read once at validation: that is graceful degradation, not a
    failure, and it costs no polling thread of our own.
    """

    def __init__(self) -> None:
        self._credential_kinds: tuple[str, ...] = ("password",)
        self._users_path: str = ""
        self._groups_path: str = ""
        self._allow_plaintext: bool = False
        self._watched_folder: str = ""

        # user name -> stored hash
        self._users: dict[str, str] = {}
        # user name -> group names
        self._groups_of: dict[str, set[str]] = {}
        # Scheme of the hash an unknown user is checked against, so that it costs what a
        # known one costs
        self._dummy_scheme: _crypt.Scheme = _crypt.Scheme.SHA512

    @Validate
    def _validate(self, _: "BundleContext") -> None:
        """
        Component validated: read both files once
        """
        if not self._users_path:
            raise ValueError(f"No password file: set the '{PROP_HTPASSWD_FILE}' property")

        self._users_path = os.path.abspath(self._users_path)
        if self._groups_path:
            self._groups_path = os.path.abspath(self._groups_path)

        self.reload()

        # Published last: this is what File Install binds on, and it must not see the
        # component before its content is loaded
        self._watched_folder = os.path.dirname(self._users_path)

    @Invalidate
    def _invalidate(self, _: "BundleContext") -> None:
        """
        Component invalidated
        """
        self._watched_folder = ""
        self._users = {}
        self._groups_of = {}

    def reload(self) -> None:
        """
        Reloads both files.

        On a parse failure, an empty file or an unreadable one, the previous table is
        **kept** and an error is logged. This is the one place where failing closed is
        the wrong instinct: an empty file is far more likely a partial write than an
        intentional revocation of everyone. A successfully parsed file with a user
        removed does revoke that user.
        """
        lines = _read_lines(self._users_path)
        if lines is not None:
            _warn_about_file_mode(self._users_path)
            users, skipped = parse_htpasswd(lines, self._users_path, self._allow_plaintext)
            if users:
                self._users = users
                self._dummy_scheme = self.__pick_dummy_scheme(users)
                _logger.info(
                    "Loaded %d users from %s, skipped %d unsupported entries",
                    len(users),
                    self._users_path,
                    skipped,
                )
            else:
                _logger.error(
                    "No usable entry in %s: keeping the previous %d users", self._users_path, len(self._users)
                )

        if self._groups_path:
            group_lines = _read_lines(self._groups_path)
            if group_lines is not None:
                self._groups_of = parse_htgroup(group_lines, self._groups_path)
                _logger.info("Loaded the groups of %d users from %s", len(self._groups_of), self._groups_path)

    @staticmethod
    def __pick_dummy_scheme(users: dict[str, str]) -> _crypt.Scheme:
        """
        Picks the scheme an unknown user is checked against: the most expensive one the
        file actually uses, so that the fake check is not visibly cheaper than a real
        one.

        :param users: The loaded users
        :return: The scheme, as a :class:`_crypt.Scheme` member
        """
        seen: set[_crypt.Scheme] = set()
        for stored in users.values():
            with contextlib.suppress(_crypt.UnsupportedHash):
                seen.add(_crypt.classify(stored))

        for scheme in (
            _crypt.Scheme.SHA512,
            _crypt.Scheme.SHA256,
            _crypt.Scheme.APR1,
            _crypt.Scheme.SHA1,
        ):
            if scheme in seen:
                return scheme

        return _crypt.Scheme.SHA512

    # ------------------------------------------------------------------------

    def authenticate(self, credentials: Credentials) -> Subject | None:
        """
        Validates a user name and a password against the loaded file
        """
        if not isinstance(credentials, UsernamePassword):
            # Not our kind of credentials: abstain
            return None

        stored = self._users.get(credentials.username)
        if stored is None:
            # An unknown user must not answer instantly while a known one burns
            # thousands of rounds: the difference alone enumerates the file
            with contextlib.suppress(_crypt.UnsupportedHash):
                _crypt.verify(credentials.password, _crypt.dummy_hash(self._dummy_scheme))

            # Abstain rather than fail: this store has never heard of that name, and
            # raising would stop the loop and make every lower-ranked store unreachable
            return None

        try:
            valid = _crypt.verify(credentials.password, stored)
        except _crypt.UnsupportedHash as ex:
            # Unreachable through a loaded file, which refuses such an entry
            _logger.error("Cannot verify the hash of '%s': %s", credentials.username, ex)
            return None

        if not valid:
            # A store which knows the user and rejects the password stops the loop: that
            # is what closes the credential oracle
            raise AuthenticationFailed(f"Wrong password for '{credentials.username}'")

        return Subject(credentials.username)

    def get_groups(self, subject: Subject) -> Iterable[str]:
        """
        Returns the groups the ``.htgroup`` file gives to the subject
        """
        return frozenset(self._groups_of.get(subject.name, ()))

    def get_roles(self, subject: Subject) -> Iterable[str]:
        """
        A password file holds no role: that is the policy's job
        """
        return ()

    # ------------------------------------------------------------------------

    def folder_change(
        self, folder: str, added: Iterable[str], updated: Iterable[str], deleted: Iterable[str]
    ) -> None:
        """
        The File Install service reports a change in the watched folder.

        It delivers base names, and it watches a whole folder, so the two files of
        interest have to be picked out of everything else living next to them.
        """
        watched = {os.path.basename(path) for path in (self._users_path, self._groups_path) if path}
        changed = watched.intersection(set(added) | set(updated) | set(deleted))
        if changed:
            _logger.info("Reloading %s", ", ".join(sorted(changed)))
            self.reload()
