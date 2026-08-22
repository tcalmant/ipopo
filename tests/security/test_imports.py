#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pins the import rule of the Pelix security package: it must stay importable with no
framework running, which is what keeps a credential store reusable outside HTTP and
keeps most of the layer unit-testable with a bare import.

:author: Thomas Calmant
"""

import subprocess
import sys
import unittest

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Modules which must not be dragged in by the security package
FORBIDDEN = ("pelix.framework", "pelix.http", "pelix.ipopo")

# ------------------------------------------------------------------------------


def imported_modules(module: str) -> set[str]:
    """
    Imports the given module in a fresh interpreter and returns the Pelix modules it
    loaded.

    :param module: Name of the module to import
    :return: The names of the loaded ``pelix`` modules
    """
    script = f"import {module}, sys; print(' '.join(m for m in sys.modules if m.startswith('pelix')))"
    output = subprocess.run([sys.executable, "-c", script], capture_output=True, check=True, text=True).stdout
    return set(output.split())


class ImportRuleTest(unittest.TestCase):
    """
    Tests what importing the security package pulls in
    """

    def test_the_package_imports_almost_nothing(self) -> None:
        """
        The whole runtime import list is the standard library plus pelix.constants
        """
        self.assertEqual(imported_modules("pelix.security"), {"pelix", "pelix.constants", "pelix.security"})

    def test_the_package_pulls_no_framework(self) -> None:
        """
        Stated separately from the exact set above, because this is the rule and the set
        is only how it is checked today
        """
        loaded = imported_modules("pelix.security")
        for forbidden in FORBIDDEN:
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, loaded)

    def test_the_decorators_pull_no_ipopo(self) -> None:
        """
        They must work on a plain class, with no component model behind it
        """
        self.assertNotIn("pelix.ipopo", imported_modules("pelix.security.decorators"))

    def test_no_module_pulls_pelix_http(self) -> None:
        """
        The direction which is forbidden: pelix.http may depend on pelix.security, so
        that a Protocol signature can name a Subject, but never the other way round. It
        is what keeps a credential store usable by the shell, or by a message broker
        client, rather than only by a servlet
        """
        for module in (
            "pelix.security.decorators",
            "pelix.security._crypt",
            "pelix.security.core",
            "pelix.security.htpasswd",
            "pelix.security.policy",
        ):
            with self.subTest(module=module):
                self.assertNotIn("pelix.http", imported_modules(module))


# ------------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
