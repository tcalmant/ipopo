#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Tests that the RSA distribution provider modules can be imported on their own.

These imports used to fail with an ImportError, due to a circular import between
``pelix.rsa.remoteserviceadmin`` and ``pelix.rsa.providers.distribution``. It went
unnoticed because samples and tutorials install ``pelix.rsa.remoteserviceadmin``
first, which primes the module cache.

Each import therefore has to run in a fresh interpreter: an in-process check would
pass spuriously as soon as any earlier test imported ``pelix.rsa``.

:license: Apache License 2.0
"""

import subprocess
import sys
import unittest

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


class FreshImportTest(unittest.TestCase):
    """
    Tests the import of RSA modules in a fresh interpreter
    """

    def assert_imports(self, statement: str) -> None:
        """
        Runs the given statement in a new interpreter and asserts it succeeds

        :param statement: The Python statement to execute
        """
        process = subprocess.run(
            [sys.executable, "-c", statement],
            capture_output=True,
            timeout=60,
            text=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_import_distribution(self) -> None:
        """
        Tests the import of the distribution provider API alone
        """
        self.assert_imports("import pelix.rsa.providers.distribution")

    def test_import_distribution_names(self) -> None:
        """
        Tests the import of names from the distribution provider API alone
        """
        self.assert_imports("from pelix.rsa.providers.distribution import ExportContainer")

    def test_import_xmlrpc(self) -> None:
        """
        Tests the import of the XML-RPC distribution provider alone
        """
        self.assert_imports("import pelix.rsa.providers.distribution.xmlrpc")

    def test_import_reverse_order(self) -> None:
        """
        Tests that the import works whichever side of the cycle comes first
        """
        self.assert_imports("import pelix.rsa.remoteserviceadmin, pelix.rsa.providers.distribution")


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
