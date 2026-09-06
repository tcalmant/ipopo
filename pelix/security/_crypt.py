#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Verification of the password hashes an Apache ``.htpasswd`` file can hold.

Pure Python over :mod:`hashlib`, with no external dependency: ``{SHA}``, ``$apr1$``
(Apache MD5) and ``$5$`` / ``$6$`` (SHA-crypt) are implemented here. bcrypt is used
when the optional ``bcrypt`` distribution is installed and refused with a remediation
otherwise, since a pure-Python Blowfish would be both hand-rolled cryptography and
tens of times too slow.

This is the one module of iPOPO where a wrong line silently accepts a wrong password,
so it is written against the published algorithms, tested against published vectors,
and deliberately free of cleverness.

Private module: its contents are an implementation detail of
:mod:`pelix.security.htpasswd`.

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

import base64
import hashlib
import hmac
import re
from enum import Enum

try:
    import bcrypt
except ImportError:
    bcrypt = None  # type: ignore

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class Scheme(Enum):
    """
    Names the format of a stored ``.htpasswd`` hash.
    """

    SHA1 = "sha1"
    """ {SHA}: unsalted and unstretched base64 SHA-1, as htpasswd -s produces """

    APR1 = "apr1"
    """ $apr1$: the Apache MD5 construction, as htpasswd -m produces """

    SHA256 = "sha256crypt"
    """ $5$: SHA-crypt over SHA-256, as htpasswd -2 produces """

    SHA512 = "sha512crypt"
    """ $6$: SHA-crypt over SHA-512, as htpasswd -5 produces """

    BCRYPT = "bcrypt"
    """ $2a$, $2b$, $2y$: bcrypt, which needs the optional bcrypt distribution """

    PLAINTEXT = "plaintext"
    """ Anything unrecognized, which is indistinguishable from a plaintext password """


WEAK_SCHEMES = frozenset({Scheme.SHA1, Scheme.APR1, Scheme.PLAINTEXT})
""" Schemes worth a warning when a file uses them """

MAX_ROUNDS = 100000
"""
Highest accepted SHA-crypt rounds parameter.

The format allows up to 999999999, which a password file can turn into a self-inflicted
denial of service: one login would burn minutes of CPU.
"""

# Alphabet of the crypt base64 variant, in its own order: neither RFC 4648 nor the
# Apache one uses this
_ITOA64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# Matches the classic DES crypt output: 13 characters of the crypt alphabet
_DES_CRYPT = re.compile(rf"^[{re.escape(_ITOA64)}]{{13}}$")

# Matches the optional "rounds=" parameter of a SHA-crypt salt
_ROUNDS = re.compile(r"^rounds=(\d+)$")

# SHA-crypt parameters, per digest
_SHA_CRYPT = {
    Scheme.SHA256: (hashlib.sha256, 32),
    Scheme.SHA512: (hashlib.sha512, 64),
}

# Order in which the digest bytes are read back when encoding a SHA-crypt result. The
# permutation is part of the format and differs between the two digests
_SHA256_ORDER = (
    (0, 10, 20),
    (21, 1, 11),
    (12, 22, 2),
    (3, 13, 23),
    (24, 4, 14),
    (15, 25, 5),
    (6, 16, 26),
    (27, 7, 17),
    (18, 28, 8),
    (9, 19, 29),
    (None, 31, 30),
)

_SHA512_ORDER = (
    (0, 21, 42),
    (22, 43, 1),
    (44, 2, 23),
    (3, 24, 45),
    (25, 46, 4),
    (47, 5, 26),
    (6, 27, 48),
    (28, 49, 7),
    (50, 8, 29),
    (9, 30, 51),
    (31, 52, 10),
    (53, 11, 32),
    (12, 33, 54),
    (34, 55, 13),
    (56, 14, 35),
    (15, 36, 57),
    (37, 58, 16),
    (59, 17, 38),
    (18, 39, 60),
    (40, 61, 19),
    (62, 20, 41),
    (None, None, 63),
)

# ------------------------------------------------------------------------------


class UnsupportedHash(ValueError):
    """
    The stored hash uses a format this build cannot verify.

    The message names the remediation, because that is what the operator needs.
    """


# ------------------------------------------------------------------------------


def classify(stored: str) -> Scheme:
    """
    Names the scheme of a stored hash.

    :param stored: The hash as it appears in the file
    :return: The scheme of the hash, as a :class:`Scheme` member
    :raise UnsupportedHash: The format is recognized and cannot be verified
    """
    if stored.startswith("{SHA}"):
        return Scheme.SHA1

    if stored.startswith("$apr1$"):
        if not _has_md5():
            raise UnsupportedHash(
                "this Python build cannot compute MD5, so $apr1$ hashes cannot be verified. "
                "Re-hash the file with: htpasswd -5"
            )

        return Scheme.APR1

    if stored.startswith("$5$"):
        return Scheme.SHA256

    if stored.startswith("$6$"):
        return Scheme.SHA512

    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        if bcrypt is None:
            raise UnsupportedHash(
                "bcrypt hashes need the optional bcrypt distribution. Install it with: "
                "pip install iPOPO[bcrypt], or re-hash the file with: htpasswd -5"
            )

        return Scheme.BCRYPT

    if _DES_CRYPT.match(stored):
        raise UnsupportedHash(
            "DES crypt truncates the password to 8 characters and cannot be verified on "
            "a modern Python. Re-hash the file with: htpasswd -5"
        )

    # Unknown formats are indistinguishable from plaintext: the caller decides what to do with it
    return Scheme.PLAINTEXT


def verify(password: str, stored: str) -> bool:
    """
    Tells whether the given password produces the given stored hash.

    :param password: The candidate password, untouched: the stored hash was computed
                     over exact bytes
    :param stored: The hash as it appears in the file
    :return: True if the password matches
    :raise UnsupportedHash: The format cannot be verified by this build
    """
    scheme = classify(stored)

    match scheme:
        case Scheme.BCRYPT:
            if bcrypt is None:
                # classify() already refuses this scheme when the module is absent, so this
                # is unreachable through it. It is also what says the attribute below exists
                raise UnsupportedHash("bcrypt is not installed")

            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))

        case Scheme.PLAINTEXT:
            return hmac.compare_digest(password, stored)

        case Scheme.SHA1:
            digest = base64.b64encode(hashlib.sha1(password.encode("utf-8")).digest()).decode("ascii")
            return hmac.compare_digest(f"{{SHA}}{digest}", stored)

        case Scheme.APR1:
            salt = stored[len("$apr1$") :].split("$", 1)[0]
            return hmac.compare_digest(apr1(password, salt), stored)

        case _:  # Scheme.SHA256 or Scheme.SHA512
            return hmac.compare_digest(sha_crypt(password, stored, scheme), stored)


def dummy_hash(scheme: Scheme) -> str:
    """
    Returns a hash of the given scheme, over a password nobody knows.

    It exists so that an unknown user costs the same time as a known one: without it,
    an unknown user returns instantly while a known one burns thousands of rounds, and
    the difference enumerates the file.

    :param scheme: The scheme of the dummy hash to return
    :return: A stored hash of that scheme
    """
    return _DUMMY_HASHES[scheme]


# ------------------------------------------------------------------------------


def _has_md5() -> bool:
    """
    Tells whether this Python build can compute MD5.

    A FIPS-restricted build raises ValueError. Passing ``usedforsecurity=False`` would
    make ``$apr1$`` work, but it would be a lie: it *is* being used for security.

    :return: True if hashlib.md5 is usable
    """
    try:
        hashlib.md5(b"")
    except ValueError:
        return False

    return True


def _to64(value: int, length: int) -> str:
    """
    Encodes an integer in the crypt base64 alphabet, least significant group first.

    :param value: The value to encode
    :param length: Number of characters to emit
    :return: The encoded characters
    """
    out = []
    for _ in range(length):
        out.append(_ITOA64[value & 0x3F])
        value >>= 6

    return "".join(out)


def apr1(password: str, salt: str) -> str:
    """
    Computes the Apache MD5 hash of a password.

    :param password: The candidate password
    :param salt: The salt read from the stored hash, at most 8 characters
    :return: The complete stored form, ``$apr1$salt$hash``
    :raise UnsupportedHash: This Python build cannot compute MD5
    """
    if not _has_md5():
        raise UnsupportedHash("this Python build cannot compute MD5")

    raw_password = password.encode("utf-8")
    raw_salt = salt[:8].encode("utf-8")

    context = hashlib.md5(raw_password + b"$apr1$" + raw_salt)

    # The password is folded in a second time, through a digest of its own
    alternate = hashlib.md5(raw_password + raw_salt + raw_password).digest()
    for offset in range(0, len(raw_password), 16):
        context.update(alternate[: min(len(raw_password) - offset, 16)])

    # Then one byte per bit of the password length, which is what makes an empty
    # password differ from a one-character one
    length = len(raw_password)
    while length:
        context.update(b"\0" if length & 1 else raw_password[:1])
        length >>= 1

    digest = context.digest()

    # 1000 fixed rounds: not a work factor, just what the format says
    for index in range(1000):
        round_context = hashlib.md5()
        round_context.update(raw_password if index & 1 else digest)
        if index % 3:
            round_context.update(raw_salt)

        if index % 7:
            round_context.update(raw_password)

        round_context.update(digest if index & 1 else raw_password)
        digest = round_context.digest()

    encoded = "".join(
        _to64((digest[first] << 16) | (digest[second] << 8) | digest[third], 4)
        for first, second, third in ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5))
    )
    encoded += _to64(digest[11], 2)

    return f"$apr1${salt}${encoded}"


def sha_crypt(password: str, stored: str, scheme: Scheme) -> str:
    """
    Computes the SHA-crypt hash of a password, with the parameters of a stored hash.

    ``$6$`` is not a SHA-512 of the salted password: it is a fixed multi-step digest
    procedure which uses SHA-512 as its primitive, repeated ``rounds`` times.

    :param password: The candidate password
    :param stored: The stored hash, which carries the rounds and the salt
    :param scheme: Scheme.SHA256 or Scheme.SHA512
    :return: The complete stored form
    :raise UnsupportedHash: The rounds parameter is above MAX_ROUNDS
    """
    digest_factory, size = _SHA_CRYPT[scheme]
    prefix = "$5$" if scheme == Scheme.SHA256 else "$6$"

    fields = stored[len(prefix) :].split("$")
    rounds = 5000
    explicit_rounds = False
    match = _ROUNDS.match(fields[0]) if fields else None
    if match is not None:
        rounds = int(match.group(1))
        explicit_rounds = True
        fields = fields[1:]

        if rounds > MAX_ROUNDS:
            raise UnsupportedHash(
                f"rounds={rounds} is above the accepted maximum of {MAX_ROUNDS}: verifying "
                "this hash would take long enough to be a denial of service"
            )

        # The format clamps rather than refuses on the low side
        rounds = max(rounds, 1000)

    salt = fields[0][:16] if fields else ""

    raw_password = password.encode("utf-8")
    raw_salt = salt.encode("utf-8")

    # Digest B, folded back into A a byte at a time below
    alternate = digest_factory(raw_password + raw_salt + raw_password).digest()

    context = digest_factory(raw_password + raw_salt)
    for offset in range(0, len(raw_password), size):
        context.update(alternate[: min(len(raw_password) - offset, size)])

    length = len(raw_password)
    while length:
        context.update(alternate if length & 1 else raw_password)
        length >>= 1

    result = context.digest()

    # Sequences P and S: the password and the salt, stretched to their own lengths
    digest_p = digest_factory(raw_password * len(raw_password)).digest()
    sequence_p = (digest_p * (len(raw_password) // size + 1))[: len(raw_password)]

    digest_s = digest_factory(raw_salt * (16 + result[0])).digest()
    sequence_s = (digest_s * (len(raw_salt) // size + 1))[: len(raw_salt)]

    for index in range(rounds):
        round_context = digest_factory()
        round_context.update(sequence_p if index & 1 else result)
        if index % 3:
            round_context.update(sequence_s)

        if index % 7:
            round_context.update(sequence_p)

        round_context.update(result if index & 1 else sequence_p)
        result = round_context.digest()

    order = _SHA256_ORDER if scheme == Scheme.SHA256 else _SHA512_ORDER
    encoded = ""
    for group in order:
        value = 0
        for index in group:
            value = (value << 8) | (0 if index is None else result[index])

        # The last group of each variant is shorter than the others
        encoded += _to64(value, 4 if group[0] is not None else (3 if group[1] is not None else 2))

    salt_field = f"rounds={rounds}${salt}" if explicit_rounds else salt
    return f"{prefix}{salt_field}${encoded}"


DUMMY_PASSWORD = "there-is-no-such-password"
""" What the dummy hashes below were computed over. The result of verifying against
them is discarded: only the time it takes matters """

# Pinned rather than computed at import time, which would cost the very rounds they
# exist to spend later. The tests check them against the implementation
_DUMMY_HASHES = {
    Scheme.SHA1: "{SHA}cJ3b4B91Y10bXRRAWZLfiUj7tUs=",
    Scheme.APR1: "$apr1$pelix...$EqyZSGnwOp7/mTuHi654S.",
    Scheme.SHA256: "$5$pelix.dummy.slt$ye.Yum4U0t3z5qnz02XrzljePTlTjo9LL2u.WzGU3b0",
    Scheme.SHA512: (
        "$6$pelix.dummy.slt$S9lAfcRXPoHQbLdUgwYNpDArV1FgJod7qEWBxsh."
        "PFOLAerLPbAADn/C2Nz5O9JKPKM3ds5QueJ.a1.mpz1y90"
    ),
    Scheme.PLAINTEXT: DUMMY_PASSWORD,
}
