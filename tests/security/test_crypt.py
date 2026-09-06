#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the verification of the password hashes a .htpasswd file can hold.

The vectors of the SHA-crypt classes are the ones published with the algorithm; the
others were produced by ``openssl passwd`` and cross-checked against the system
``libcrypt``. They are hard-coded rather than generated: a test which computes its own
expectation with the code under test proves nothing here.

:author: Thomas Calmant
"""

import importlib.util
import unittest
from typing import ClassVar

from pelix.security import _crypt

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class ClassifyTest(unittest.TestCase):
    """
    Tests the recognition of the stored formats
    """

    def test_the_supported_schemes(self) -> None:
        cases = {
            "{SHA}qZk+NkcGgWq6PiVxeFDCbJzQ2J0=": _crypt.Scheme.SHA1,
            "$apr1$Salt1234$D8s.gsdmZE5tKuG05Ln6h1": _crypt.Scheme.APR1,
            "$5$Salt1234$fkaLpRxzw5AmCunoMxKXYbdYIEdpMtjffBTHgpMkbJB": _crypt.Scheme.SHA256,
            "$6$Salt1234$6PKOWHd4Jx": _crypt.Scheme.SHA512,
        }
        for stored, scheme in cases.items():
            with self.subTest(scheme=scheme):
                self.assertEqual(_crypt.classify(stored), scheme)

    def test_des_crypt_is_refused(self) -> None:
        """
        Eight-character truncation and a twelve-bit salt, and unimplementable on a
        modern Python anyway
        """
        with self.assertRaises(_crypt.UnsupportedHash) as context:
            _crypt.classify("rEK1ecacw.rKc")

        self.assertIn("htpasswd -5", str(context.exception))

    def test_anything_else_is_plaintext(self) -> None:
        """
        "Support plaintext" and "refuse unknown formats" are the same branch with
        opposite defaults, and the caller owns the default
        """
        for stored in ("hunter2", "", "$9$unknown$scheme", "{MD5}abcd"):
            with self.subTest(stored=stored):
                self.assertEqual(_crypt.classify(stored), _crypt.Scheme.PLAINTEXT)


class Sha1Test(unittest.TestCase):
    """
    Tests {SHA}, the unsalted base64 SHA-1 of htpasswd -s
    """

    # base64(sha1(b"abc")), as htpasswd -s writes it
    VECTOR = "{SHA}qZk+NkcGgWq6PiVxeFDCbJzQ2J0="

    def test_the_vector(self) -> None:
        self.assertTrue(_crypt.verify("abc", self.VECTOR))

    def test_a_wrong_password(self) -> None:
        self.assertFalse(_crypt.verify("abd", self.VECTOR))

    def test_an_empty_password(self) -> None:
        self.assertTrue(_crypt.verify("", "{SHA}2jmj7l5rSw0yVb/vlWAYkK/YBwk="))


class Apr1Test(unittest.TestCase):
    """
    Tests $apr1$, the Apache MD5 construction
    """

    VECTORS: ClassVar[dict[str, str]] = {
        "": "$apr1$Salt1234$RJ65UuCD1ZSOkdcQd0Nq7/",
        "a": "$apr1$Salt1234$oE0AI8r/6R5rEU7EzDQq3.",
        "hunter2": "$apr1$Salt1234$SGnju/duP8ZqWvqbs1MkB1",
        "good": "$apr1$FGkY6bLp$IKkCuz1P..KyQ0FL0L7Ir0",
        # Non-ASCII, to pin that the password is hashed as the bytes it really is
        "pässwörd": "$apr1$Salt1234$W4qW/8xhDkglbB.JlEmC.0",
        # Longer than one MD5 block, which exercises the folding loop
        "0123456789012345678901234567890123456789": "$apr1$Salt1234$CpTUIPIAsdGBCsIjtkeEc1",
    }

    def test_the_vectors(self) -> None:
        for password, stored in self.VECTORS.items():
            with self.subTest(password=password):
                self.assertTrue(_crypt.verify(password, stored))

    def test_a_wrong_password(self) -> None:
        for password, stored in self.VECTORS.items():
            with self.subTest(password=password):
                self.assertFalse(_crypt.verify(f"{password}x", stored))

    def test_the_salt_is_kept(self) -> None:
        self.assertEqual(_crypt.apr1("hunter2", "Salt1234"), self.VECTORS["hunter2"])

    def test_the_salt_is_capped_at_eight_characters(self) -> None:
        """
        The format allows no more, and Apache silently truncates: a longer salt gives
        the very same digest
        """
        self.assertEqual(_crypt.apr1("hunter2", "Salt1234567890")[-22:], self.VECTORS["hunter2"][-22:])


class ShaCryptTest(unittest.TestCase):
    """
    Tests $5$ and $6$, the SHA-crypt construction.

    $6$ is not a SHA-512 of the salted password: it is a fixed multi-step digest
    procedure using SHA-512 as its primitive, repeated 5000 times by default. The
    vectors below come with the algorithm.
    """

    SHA256_VECTORS: ClassVar[dict[tuple[str, str], str]] = {
        ("Hello world!", "$5$saltstring"): "$5$saltstring$5B8vYYiY.CVt1RlTTf8KbXBH3hsxY/GNooZaBBGWEc5",
        ("Hello world!", "$5$rounds=10000$saltstringsaltstring"): (
            "$5$rounds=10000$saltstringsaltst$3xv.VbSHBb41AL9AvLeujZkZRBAwqFMz2.opqey6IcA"
        ),
        ("This is just a test", "$5$rounds=5000$toolongsaltstring"): (
            "$5$rounds=5000$toolongsaltstrin$Un/5jzAHMgOGZ5.mWJpuVolil07guHPvOW8mGRcvxa5"
        ),
        (
            "a very much longer text to encrypt.  This one even stretches over morethan one line.",
            "$5$rounds=1400$anotherlongsaltstring",
        ): ("$5$rounds=1400$anotherlongsalts$Rx.j8H.h8HjEDGomFU8bDkXm3XIUnzyxf12oP84Bnq1"),
        ("we have a short salt string but not a short password", "$5$rounds=77777$short"): (
            "$5$rounds=77777$short$JiO1O3ZpDAxGJeaDIuqCoEFysAe1mZNJRs3pw0KQRd/"
        ),
    }

    SHA512_VECTORS: ClassVar[dict[tuple[str, str], str]] = {
        ("Hello world!", "$6$saltstring"): (
            "$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJu"
            "esI68u4OTLiBFdcbYEdFCoEOfaS35inz1"
        ),
        ("Hello world!", "$6$rounds=10000$saltstringsaltstring"): (
            "$6$rounds=10000$saltstringsaltst$OW1/O6BYHV6BcXZu8QVeXbDWra3Oeqh0sb"
            "HbbMCVNSnCM/UrjmM0Dp8vOuZeHBy/YTBmSK6H9qs/y3RnOaw5v."
        ),
        ("This is just a test", "$6$rounds=5000$toolongsaltstring"): (
            "$6$rounds=5000$toolongsaltstrin$lQ8jolhgVRVhY4b5pZKaysCLi0QBxGoNeKQ"
            "zQ3glMhwllF7oGDZxUhx1yxdYcz/e1JSbq3y6JMxxl8audkUEm0"
        ),
        ("we have a short salt string but not a short password", "$6$rounds=77777$short"): (
            "$6$rounds=77777$short$WuQyW2YR.hBNpjjRhpYD/ifIw05xdfeEyQoMxIXbkvr0g"
            "ge1a1x3yRULJ5CCaUeOxFmtlcGZelFl5CxtgfiAc0"
        ),
    }

    def test_the_sha256_vectors(self) -> None:
        for (password, setting), expected in self.SHA256_VECTORS.items():
            with self.subTest(setting=setting):
                self.assertEqual(_crypt.sha_crypt(password, expected, _crypt.Scheme.SHA256), expected)
                self.assertTrue(_crypt.verify(password, expected))

    def test_the_sha512_vectors(self) -> None:
        for (password, setting), expected in self.SHA512_VECTORS.items():
            with self.subTest(setting=setting):
                self.assertEqual(_crypt.sha_crypt(password, expected, _crypt.Scheme.SHA512), expected)
                self.assertTrue(_crypt.verify(password, expected))

    def test_a_wrong_password(self) -> None:
        for vectors in (self.SHA256_VECTORS, self.SHA512_VECTORS):
            for (password, _), expected in vectors.items():
                with self.subTest(stored=expected[:20]):
                    self.assertFalse(_crypt.verify(f"{password}x", expected))

    def test_it_is_not_a_bare_digest_of_the_salted_password(self) -> None:
        """
        The question comes up every time: a bare sha512 of the same bytes is unrelated
        to what $6$ produces
        """
        import base64
        import hashlib

        stored = "$6$FGkY6bLp$FLRsAi6byimzKD0qdHddj.KT3zGYn0YAQb1fz92.0iRT7oOWSxlrqtRH5PsV2.O54EGWS.YTWcL/GI.oOsXnx."
        naive = base64.b64encode(hashlib.sha512(b"FGkY6bLpgood").digest()).decode("ascii")

        self.assertTrue(_crypt.verify("good", stored))
        self.assertNotIn(naive[:16], stored)

    def test_an_empty_password(self) -> None:
        """
        Accepted by the algorithm, refused by the openssl command line, so it is pinned
        here against what the system libcrypt answers
        """
        stored = "$6$Salt1234$9n2q0b/5q6BDYjbIfWDCa.pc2ztIkmadTm8vExXDkHruVrP.WuCs9mStfH56AOQ5w5ElMFcccmPpMKoRHrgaE."
        self.assertTrue(_crypt.verify("", stored))
        self.assertFalse(_crypt.verify("x", stored))

    def test_the_salt_is_capped_at_sixteen_characters(self) -> None:
        """
        Which is why the vectors above spell the truncated salt in what they expect
        """
        self.assertEqual(
            _crypt.sha_crypt("Hello world!", "$5$rounds=10000$saltstringsaltstring$x", _crypt.Scheme.SHA256),
            "$5$rounds=10000$saltstringsaltst$3xv.VbSHBb41AL9AvLeujZkZRBAwqFMz2.opqey6IcA",
        )

    def test_too_many_rounds_are_refused(self) -> None:
        """
        The format allows up to 999999999, which one login would turn into minutes of
        CPU: a password file must not be able to do that to its own server.

        The two hashes below are published vectors of the algorithm, so this pins the
        cap against something a real tool produces rather than against a fabrication
        """
        published = (
            "$5$rounds=123456$asaltof16chars..$gP3VQ/6X7UUEW3HkBn2w1side3HAKIoTayg/w8DHzX0",
            (
                "$6$rounds=123456$asaltof16chars..$BtCwjqMJGx5hrJhZywWvt0RLE8uZ4oPwc"
                "elCjmw2kSYu.Ec6ycULevoBK25fs2xXgMNrCzIMVcgEJAstJeonj1"
            ),
        )
        for stored in published:
            with self.subTest(stored=stored[:20]), self.assertRaises(_crypt.UnsupportedHash) as context:
                _crypt.verify("a short string", stored)

            self.assertIn(str(_crypt.MAX_ROUNDS), str(context.exception))

    def test_the_accepted_maximum_still_works(self) -> None:
        stored = _crypt.sha_crypt(
            "hunter2", f"$5$rounds={_crypt.MAX_ROUNDS}$Salt1234$x", _crypt.Scheme.SHA256
        )
        self.assertTrue(_crypt.verify("hunter2", stored))


class BcryptTest(unittest.TestCase):
    """
    Tests the optional bcrypt support
    """

    @unittest.skipIf(importlib.util.find_spec("bcrypt") is None, "bcrypt is not installed")
    def test_it_is_verified_when_the_module_is_there(self) -> None:
        """
        The hash is produced by bcrypt itself: what is under test is that the format is
        recognized and handed over, not the bcrypt algorithm
        """
        import bcrypt

        stored = bcrypt.hashpw(b"hunter2", bcrypt.gensalt(4, b"2b")).decode("ascii")

        self.assertEqual(_crypt.classify(stored), _crypt.Scheme.BCRYPT)
        self.assertTrue(_crypt.verify("hunter2", stored))
        self.assertFalse(_crypt.verify("wrong", stored))

    @unittest.skipIf(importlib.util.find_spec("bcrypt") is not None, "bcrypt is installed")
    def test_it_is_refused_with_a_remediation(self) -> None:
        """
        A pure-Python Blowfish would be hand-rolled cryptography and tens of times too
        slow, so the answer is a message naming what to do instead
        """
        for prefix in ("$2a$", "$2b$", "$2y$"):
            with self.subTest(prefix=prefix), self.assertRaises(_crypt.UnsupportedHash) as context:
                _crypt.classify(f"{prefix}04$abcdefghijklmnopqrstuv")

            self.assertIn("bcrypt", str(context.exception))
            self.assertIn("htpasswd -5", str(context.exception))


class DummyHashTest(unittest.TestCase):
    """
    The dummy hashes are what gives an unknown user the cost of a known one
    """

    def test_every_dummy_is_a_hash_of_the_dummy_password(self) -> None:
        """
        Pinned rather than computed at import time, so they are checked here
        """
        for scheme in (
            _crypt.Scheme.SHA1,
            _crypt.Scheme.APR1,
            _crypt.Scheme.SHA256,
            _crypt.Scheme.SHA512,
            _crypt.Scheme.PLAINTEXT,
        ):
            with self.subTest(scheme=scheme):
                stored = _crypt.dummy_hash(scheme)
                self.assertEqual(_crypt.classify(stored), scheme)
                self.assertTrue(_crypt.verify(_crypt.DUMMY_PASSWORD, stored))


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
