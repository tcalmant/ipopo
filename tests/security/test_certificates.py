#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the client certificate credentials and their mapping to users in the policy file.

:author: Thomas Calmant
"""

import hashlib
import importlib
import pathlib
import tempfile
import unittest
from typing import Any, cast

import pelix.framework
from pelix.ipopo.constants import use_ipopo
from pelix.security import (
    FACTORY_HTPASSWD,
    FACTORY_POLICY_FILE,
    PROP_HTPASSWD_FILE,
    PROP_HTPASSWD_GROUPS,
    PROP_POLICY_FILE,
    AuthenticationFailed,
    ClientCertificate,
    Subject,
    UsernamePassword,
)
from pelix.security.policy import PolicyError, PolicyFile, PolicyTable, normalize_fingerprint

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

# "good", hashed with SHA-crypt over SHA-512
GOOD_SHA512 = (
    "$6$FGkY6bLp$FLRsAi6byimzKD0qdHddj.KT3zGYn0YAQb1fz92.0iRT7oOWSxlrqtRH5PsV2.O54EGWS.YTWcL/GI.oOsXnx."
)

THOMAS_DER = b"the certificate of thomas"
THOMAS_FINGERPRINT = hashlib.sha256(THOMAS_DER).hexdigest()

# The same value as openssl x509 -fingerprint -sha256 prints it
THOMAS_OPENSSL = ":".join(THOMAS_FINGERPRINT[i : i + 2] for i in range(0, 64, 2)).upper()

# What SSLSocket.getpeercert() returns for a verified certificate
BATCH_DETAILS: dict[str, Any] = {
    "subject": ((("countryName", "FR"),), (("organizationName", "Acme"),), (("commonName", "batch"),)),
    "subjectAltName": (("DNS", "batch.example.com"), ("IP Address", "10.0.0.1")),
}

POLICY = f"""
[roles.admin]
users = ["thomas"]

[roles.operator]
groups = ["ops"]

[permissions]
admin = ["jobs.read"]
operator = ["jobs.submit"]

[certificates.fingerprints]
"{THOMAS_OPENSSL}" = "thomas"

[certificates.subjects]
"CN=batch,O=Acme,C=FR" = "batch"
"""

LOGGER = "pelix.security.policy"

# ------------------------------------------------------------------------------


class FakeSocket:
    """
    Answers getpeercert() like an SSLSocket after its handshake
    """

    def __init__(self, der: bytes | None, details: dict[str, Any] | None) -> None:
        self.der = der
        self.details = details

    def getpeercert(self, binary_form: bool = False) -> Any:
        return self.der if binary_form else self.details


class ClientCertificateTest(unittest.TestCase):
    """
    Tests the credentials bean and how it is built from what the ssl module gives
    """

    def test_the_kind(self) -> None:
        self.assertEqual(ClientCertificate.KIND, "certificate")

    def test_the_fingerprint_is_the_sha256_of_the_der_form(self) -> None:
        certificate = ClientCertificate.from_der(THOMAS_DER)

        self.assertEqual(certificate.fingerprint, THOMAS_FINGERPRINT)
        self.assertEqual(certificate.subject, "")
        self.assertEqual(certificate.alt_names, ())

    def test_the_subject_is_written_the_rfc_4514_way(self) -> None:
        """
        Most specific RDN first, which is the reverse of the certificate order
        """
        certificate = ClientCertificate.from_der(b"batch", BATCH_DETAILS)

        self.assertEqual(certificate.subject, "CN=batch,O=Acme,C=FR")
        self.assertEqual(certificate.alt_names, ("DNS:batch.example.com", "IP Address:10.0.0.1"))

    def test_special_characters_are_escaped(self) -> None:
        """
        Or a common name could forge the look of another organization
        """
        details = {"subject": ((("organizationName", "Acme"),), (("commonName", "evil,O=Acme"),))}
        self.assertEqual(ClientCertificate.from_der(b"x", details).subject, "CN=evil\\,O=Acme,O=Acme")

        details = {"subject": ((("commonName", " #lead"),), (("commonName", "trail "),))}
        self.assertEqual(ClientCertificate.from_der(b"x", details).subject, "CN=trail\\ ,CN=\\ #lead")

    def test_a_multi_valued_rdn(self) -> None:
        details = {"subject": ((("commonName", "a"), ("userId", "b")),)}
        self.assertEqual(ClientCertificate.from_der(b"x", details).subject, "CN=a+UID=b")

    def test_an_attribute_without_a_short_name_keeps_its_ssl_name(self) -> None:
        details = {"subject": ((("emailAddress", "a@example.com"),),)}
        self.assertEqual(ClientCertificate.from_der(b"x", details).subject, "emailAddress=a@example.com")

    def test_from_a_socket(self) -> None:
        certificate = ClientCertificate.from_socket(cast(Any, FakeSocket(b"batch", BATCH_DETAILS)))

        assert certificate is not None
        self.assertEqual(certificate.fingerprint, hashlib.sha256(b"batch").hexdigest())
        self.assertEqual(certificate.subject, "CN=batch,O=Acme,C=FR")

    def test_a_socket_without_a_peer_certificate(self) -> None:
        self.assertIsNone(ClientCertificate.from_socket(cast(Any, FakeSocket(None, None))))


# ------------------------------------------------------------------------------


class FingerprintTest(unittest.TestCase):
    """
    Tests the normalization of the fingerprints written in a policy file
    """

    def test_the_accepted_spellings(self) -> None:
        for spelling in (
            THOMAS_FINGERPRINT,
            THOMAS_FINGERPRINT.upper(),
            THOMAS_OPENSSL,
            THOMAS_OPENSSL.lower(),
        ):
            with self.subTest(spelling=spelling):
                self.assertEqual(normalize_fingerprint(spelling), THOMAS_FINGERPRINT)

    def test_what_is_not_a_sha256_fingerprint(self) -> None:
        for value in ("", "abcd", hashlib.sha1(b"x").hexdigest(), "z" * 64, THOMAS_FINGERPRINT + "00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_fingerprint(value)


class PolicyCertificatesTest(unittest.TestCase):
    """
    Tests the [certificates] tables of the policy file
    """

    def setUp(self) -> None:
        self.table = PolicyTable(POLICY)

    def test_a_certificate_mapped_by_fingerprint(self) -> None:
        self.assertEqual(self.table.get_certificate_user(ClientCertificate(THOMAS_FINGERPRINT)), "thomas")

    def test_a_certificate_mapped_by_subject(self) -> None:
        certificate = ClientCertificate.from_der(b"batch", BATCH_DETAILS)
        self.assertEqual(self.table.get_certificate_user(certificate), "batch")

    def test_the_fingerprint_wins_over_the_subject(self) -> None:
        certificate = ClientCertificate(THOMAS_FINGERPRINT, "CN=batch,O=Acme,C=FR")
        self.assertEqual(self.table.get_certificate_user(certificate), "thomas")

    def test_an_unknown_certificate(self) -> None:
        certificate = ClientCertificate(hashlib.sha256(b"other").hexdigest(), "CN=other")
        self.assertIsNone(self.table.get_certificate_user(certificate))

    def test_subjects_are_compared_exactly(self) -> None:
        for subject in ("cn=batch,o=Acme,c=FR", "CN=batch, O=Acme, C=FR", "CN=batch,O=Acme"):
            with self.subTest(subject=subject):
                certificate = ClientCertificate(hashlib.sha256(b"other").hexdigest(), subject)
                self.assertIsNone(self.table.get_certificate_user(certificate))

    def test_no_section_maps_nothing(self) -> None:
        self.assertIsNone(PolicyTable("").get_certificate_user(ClientCertificate(THOMAS_FINGERPRINT)))

    def test_the_shape_failures(self) -> None:
        cases = {
            "certificates is not a table": "certificates = 12\n",
            "an unknown key": "[certificates.issuers]\n",
            "fingerprints is not a table": "[certificates]\nfingerprints = 12\n",
            "subjects is not a table": '[certificates]\nsubjects = ["CN=a"]\n',
            "a user is not a string": f'[certificates.fingerprints]\n"{THOMAS_FINGERPRINT}" = 12\n',
            "a user is a list": '[certificates.subjects]\n"CN=a" = ["a"]\n',
            "an empty user": '[certificates.subjects]\n"CN=a" = ""\n',
            "not a fingerprint": '[certificates.fingerprints]\n"abcd" = "thomas"\n',
            "a SHA-1 fingerprint": f'[certificates.fingerprints]\n"{hashlib.sha1(b"x").hexdigest()}" = "a"\n',
            "the same fingerprint twice": (
                f'[certificates.fingerprints]\n"{THOMAS_FINGERPRINT}" = "a"\n"{THOMAS_OPENSSL}" = "b"\n'
            ),
        }
        for name, text in cases.items():
            with self.subTest(case=name), self.assertRaises(PolicyError):
                PolicyTable(text)


# ------------------------------------------------------------------------------


class CertificateAuthenticatorTest(unittest.TestCase):
    """
    Tests the policy component as an Authenticator of certificate credentials
    """

    def setUp(self) -> None:
        self.component = PolicyFile()
        self.component._table = PolicyTable(POLICY)

    def test_a_known_certificate_gives_its_user(self) -> None:
        self.assertEqual(
            self.component.authenticate(ClientCertificate(THOMAS_FINGERPRINT)), Subject("thomas")
        )

    def test_an_unknown_certificate_abstains(self) -> None:
        """
        It passed the TLS verification, so it is not "presented and wrong": another
        store may know it
        """
        self.assertIsNone(self.component.authenticate(ClientCertificate(hashlib.sha256(b"x").hexdigest())))

    def test_another_kind_of_credentials_abstains(self) -> None:
        self.assertIsNone(self.component.authenticate(UsernamePassword("thomas", "good")))

    def test_no_table_abstains(self) -> None:
        self.assertIsNone(PolicyFile().authenticate(ClientCertificate(THOMAS_FINGERPRINT)))


class CertificatePipelineTest(unittest.TestCase):
    """
    Tests authenticate() with certificates, through the real bundles: the policy maps the
    certificate, the .htgroup file gives the groups and the policy the roles
    """

    framework: pelix.framework.Framework

    def setUp(self) -> None:
        self.folder = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(self.__remove_folder)

        (self.folder / ".htpasswd").write_text(f"thomas:{GOOD_SHA512}\n")
        (self.folder / ".htpasswd").chmod(0o600)
        (self.folder / ".htgroup").write_text("ops: batch\n")
        self.policy_file = self.folder / "policy.toml"
        self.policy_file.write_text(POLICY)

        self.framework = pelix.framework.create_framework(
            ("pelix.ipopo.core", "pelix.security.core", "pelix.security.htpasswd", "pelix.security.policy")
        )
        self.addCleanup(self.framework.delete, True)
        self.framework.start()

        with use_ipopo(self.framework.get_bundle_context()) as ipopo:
            ipopo.instantiate(
                FACTORY_HTPASSWD,
                "users",
                {
                    PROP_HTPASSWD_FILE: str(self.folder / ".htpasswd"),
                    PROP_HTPASSWD_GROUPS: str(self.folder / ".htgroup"),
                },
            )
            self.policy = ipopo.instantiate(
                FACTORY_POLICY_FILE, "policy", {PROP_POLICY_FILE: str(self.policy_file)}
            )

        # The module the framework loaded: uninstalling a bundle drops its module, so one
        # imported with this test module would be stale after the first framework is deleted
        self.core: Any = importlib.import_module("pelix.security.core")

    def __remove_folder(self) -> None:
        for path in self.folder.iterdir():
            path.unlink()

        self.folder.rmdir()

    def test_a_certificate_gets_the_roles_of_its_user(self) -> None:
        subject = self.core.authenticate(ClientCertificate(THOMAS_FINGERPRINT))

        self.assertEqual(subject.name, "thomas")
        self.assertTrue(subject.authenticated)
        self.assertEqual(subject.roles, frozenset({"admin"}))

    def test_a_certificate_gets_the_groups_of_its_user(self) -> None:
        subject = self.core.authenticate(ClientCertificate.from_der(b"batch", BATCH_DETAILS))

        self.assertEqual(subject.name, "batch")
        self.assertEqual(subject.groups, frozenset({"ops"}))
        self.assertEqual(subject.roles, frozenset({"operator"}))

    def test_an_unknown_certificate_is_refused(self) -> None:
        with self.assertRaises(AuthenticationFailed):
            self.core.authenticate(ClientCertificate(hashlib.sha256(b"x").hexdigest(), "CN=stranger"))

    def test_passwords_still_work(self) -> None:
        """
        The policy registers for certificates only, so it is never asked about a password
        """
        self.assertEqual(
            self.core.authenticate(UsernamePassword("thomas", "good")).roles, frozenset({"admin"})
        )

    def test_a_reload_changes_the_mapping(self) -> None:
        self.policy_file.write_text(POLICY.replace('= "thomas"', '= "batch"'))
        self.policy.reload()

        self.assertEqual(self.core.authenticate(ClientCertificate(THOMAS_FINGERPRINT)).name, "batch")


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
