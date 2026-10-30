#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the bundles handling.

:author: Thomas Calmant
"""

import os
import pathlib
import sys
import tempfile
import textwrap
import unittest
import zipfile
from typing import Any, ClassVar

from pelix.framework import Bundle, BundleContext, BundleException, FrameworkFactory
from tests import log_off, log_on

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

SERVICE_BUNDLE = "tests.framework.service_bundle"
SIMPLE_BUNDLE = "tests.framework.simple_bundle"

# ------------------------------------------------------------------------------


class BundlesTest(unittest.TestCase):
    """
    Pelix bundle registry tests
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        self.test_bundle_name = SIMPLE_BUNDLE
        # File path, without extension
        self.test_bundle_loc = os.path.join(
            os.path.dirname(__file__), self.test_bundle_name.rsplit(".", 1)[1]
        )

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def testImportError(self):
        """
        Tries to install an invalid bundle
        """
        # Try to install the bundle
        self.assertRaises(BundleException, self.context.install_bundle, "//Invalid Name\\\\")

    def testCompatibility(self, test_bundle_id=False):
        """
        Tests a bundle installation + start + stop

        @param test_bundle_id: If True, also tests if the test bundle ID is 1
        """
        # Install the bundle
        bundle_id = self.context.install_bundle(self.test_bundle_name)
        bundle = self.context.get_bundle(bundle_id)
        assert isinstance(bundle, Bundle)
        if test_bundle_id:
            self.assertEqual(bundle.get_bundle_id(), 1, "Not the first bundle in framework")

        # Get the internal module
        module_ = bundle.get_module()

        # Assert initial state
        self.assertFalse(module_.started, "Bundle should not be started yet")
        self.assertFalse(module_.stopped, "Bundle should not be stopped yet")

        # Activator
        bundle.start()

        self.assertTrue(module_.started, "Bundle should be started now")
        self.assertFalse(module_.stopped, "Bundle should not be stopped yet")

        # De-activate
        bundle.stop()

        self.assertTrue(module_.started, "Bundle should be changed")
        self.assertTrue(module_.stopped, "Bundle should be stopped now")

        # Uninstall (validated in another test)
        bundle.uninstall()

    def testLifeCycle(self, test_bundle_id=False):
        """
        Tests a bundle installation + start + stop

        @param test_bundle_id: If True, also tests if the test bundle ID is 1
        """
        # Install the bundle
        bundle = self.context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)
        if test_bundle_id:
            self.assertEqual(bundle.get_bundle_id(), 1, "Not the first bundle in framework")

        # Get the internal module
        module_ = bundle.get_module()

        # Assert initial state
        self.assertFalse(module_.started, "Bundle should not be started yet")
        self.assertFalse(module_.stopped, "Bundle should not be stopped yet")

        # Activator
        bundle.start()

        self.assertTrue(module_.started, "Bundle should be started now")
        self.assertFalse(module_.stopped, "Bundle should not be stopped yet")

        # De-activate
        bundle.stop()

        self.assertTrue(module_.started, "Bundle should be changed")
        self.assertTrue(module_.stopped, "Bundle should be stopped now")

        # Uninstall (validated in another test)
        bundle.uninstall()

    def testLifeCycleRecalls(self):
        """
        Tests a bundle installation + start + stop
        """
        # Install the bundle
        bundle = self.context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        # Get the internal module
        module_: Any = bundle.get_module()

        # Assert initial state
        self.assertFalse(module_.started, "Bundle should not be started yet")
        self.assertFalse(module_.stopped, "Bundle should not be stopped yet")

        # Activator
        bundle.start()

        self.assertEqual(bundle.get_state(), Bundle.ACTIVE, "Bundle should be considered active")

        self.assertTrue(module_.started, "Bundle should be started now")
        self.assertFalse(module_.stopped, "Bundle should not be stopped yet")

        # Recall activator
        module_.started = False
        bundle.start()
        self.assertFalse(module_.started, "Bundle shouldn't be started twice")

        # Reset to previous state
        module_.started = True

        # De-activate
        bundle.stop()

        self.assertNotEqual(bundle.get_state(), Bundle.ACTIVE, "Bundle shouldn't be considered active")

        self.assertTrue(module_.started, "Bundle should be changed")
        self.assertTrue(module_.stopped, "Bundle should be stopped now")

        # Recall activator
        module_.stopped = False
        bundle.stop()
        self.assertFalse(module_.stopped, "Bundle shouldn't be stopped twice")

        # Uninstall (validated in another test)
        bundle.uninstall()

        self.assertEqual(bundle.get_state(), Bundle.UNINSTALLED, "Bundle should be considered uninstalled")

    def testLifeCycleExceptions(self):
        """
        Tests a bundle installation + start + stop
        """
        # Install the bundle
        bundle = self.context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        # Get the internal module
        module_: Any = bundle.get_module()

        # Assert initial state
        self.assertFalse(module_.started, "Bundle should not be started yet")
        self.assertFalse(module_.stopped, "Bundle should not be stopped yet")

        # Activator with exception
        module_.raiser = True

        log_off()
        self.assertRaises(BundleException, bundle.start)
        log_on()

        # Assert post-exception state
        self.assertNotEqual(bundle.get_state(), Bundle.ACTIVE, "Bundle shouldn't be considered active")
        self.assertFalse(module_.started, "Bundle should not be started yet")
        self.assertFalse(module_.stopped, "Bundle should not be stopped yet")

        # Activator, without exception
        module_.raiser = False
        bundle.start()

        self.assertEqual(bundle.get_state(), Bundle.ACTIVE, "Bundle should be considered active")

        self.assertTrue(module_.started, "Bundle should be started now")
        self.assertFalse(module_.stopped, "Bundle should not be stopped yet")

        # De-activate with exception
        module_.raiser = True

        log_off()
        self.assertRaises(BundleException, bundle.stop)
        log_on()

        self.assertNotEqual(bundle.get_state(), Bundle.ACTIVE, "Bundle shouldn't be considered active")
        self.assertTrue(module_.started, "Bundle should be changed")
        self.assertFalse(module_.stopped, "Bundle should be stopped now")

        # Uninstall (validated in another test)
        bundle.uninstall()

    def testUninstallInstall(self):
        """
        Runs the life-cycle test twice.

        The bundle is installed then un-installed twice. started and stopped
        values of the bundle should be reset to False.

        Keeping two separate calls instead of using a loop allows to see at
        which pass the test have failed
        """
        # Pass 1: normal test
        self.testLifeCycle(True)

        # Pass 2: refresh test
        self.testLifeCycle(False)

    def testUninstallWithStartStop(self):
        """
        Tests if a bundle is correctly uninstalled and if it is really
        unaccessible after its uninstallation.
        """
        # Install the bundle
        bundle = self.context.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        bid = bundle.get_bundle_id()
        self.assertEqual(bid, 1, f"Invalid first bundle ID '{bid:d}'")

        # Test state
        self.assertEqual(
            bundle.get_state(),
            Bundle.RESOLVED,
            f"Invalid fresh install state {bundle.get_state():d}",
        )

        # Start
        bundle.start()
        self.assertEqual(
            bundle.get_state(), Bundle.ACTIVE, f"Invalid fresh start state {bundle.get_state():d}"
        )

        # Stop
        bundle.stop()
        self.assertEqual(
            bundle.get_state(), Bundle.RESOLVED, f"Invalid fresh stop state {bundle.get_state():d}"
        )

        # Uninstall
        bundle.uninstall()
        self.assertEqual(
            bundle.get_state(),
            Bundle.UNINSTALLED,
            f"Invalid fresh stop state {bundle.get_state():d}",
        )

        # The bundle must not be accessible through the framework
        self.assertRaises(BundleException, self.context.get_bundle, bid)

        self.assertRaises(BundleException, self.framework.get_bundle_by_id, bid)

        found_bundle = self.framework.get_bundle_by_name(self.test_bundle_name)
        self.assertIsNone(found_bundle, "Bundle is still accessible by name through the framework")

    def testUpdate(self):
        """
        Tests a bundle update
        """
        bundle_content = """#!/usr/bin/python
# -- Content-Encoding: UTF-8 --

# Auto-generated bundle, for Pelix tests
__version__ = "{version}"
test_var = {test}

def test_fct():
    return {test}
"""

        # Compute the bundle full path
        simple_name = "generated_bundle"
        bundle_name = f"{__name__.rsplit('.', 1)[0]}.{simple_name}"
        bundle_fullname = os.path.join(os.path.dirname(__file__), f"{simple_name}.py")

        # 0/ Clean up existing files
        for suffix in ("", "c", "o"):
            path = f"{bundle_fullname}{suffix}"
            if os.path.exists(path):
                os.remove(path)

        # 1/ Prepare the bundle, test variable is set to False
        with open(bundle_fullname, "w") as f:
            f.write(bundle_content.format(version="1.0.0", test=False))

        # 2/ Install the bundle and get its variable
        bundle = self.context.install_bundle(bundle_name)
        module_ = bundle.get_module()

        # Also start the bundle
        bundle.start()
        self.assertFalse(module_.test_var, "Test variable should be False")

        # 3/ Change the bundle file
        with open(bundle_fullname, "w") as f:
            f.write(bundle_content.format(version="1.0.1", test=True))

        # 4/ Update, keeping the module reference
        bundle.update()
        self.assertIs(module_, bundle.get_module(), "Module has changed")
        self.assertTrue(module_.test_var, "Test variable should be True")

        # 5/ Change the bundle file, make it erroneous
        with open(bundle_fullname, "w") as f:
            f.write(bundle_content.format(version="1.0.2", test="\n"))

        # No error must be raised...
        log_off()
        bundle.update()
        log_on()

        # ... but the state of the module shouldn't have changed
        self.assertTrue(module_.test_var, "Test variable should still be True")

        # Finally, change the test file to be a valid module
        # -> Used by coverage for its report
        with open(bundle_fullname, "w") as f:
            f.write(bundle_content.format(version="1.0.0", test=False))

    def testVersion(self):
        """
        Tests if the version is correctly read from the bundle
        """
        # Install the bundle
        bundle = self.framework.install_bundle(self.test_bundle_name)
        assert isinstance(bundle, Bundle)

        bid = bundle.get_bundle_id()
        self.assertEqual(bid, 1, f"Invalid first bundle ID '{bid:d}'")

        # Get the internal module
        module_ = bundle.get_module()

        # Validate the bundle name
        self.assertEqual(
            bundle.get_symbolic_name(),
            self.test_bundle_name,
            f"Names are different ({bundle.get_symbolic_name()} / {self.test_bundle_name})",
        )

        # Validate get_location()
        bundle_without_ext = os.path.splitext(bundle.get_location())[0]
        full_bundle_path = os.path.abspath(bundle_without_ext)
        self.assertIn(self.test_bundle_loc, (bundle_without_ext, full_bundle_path))

        # Validate the version number
        self.assertEqual(
            bundle.get_version(),
            module_.__version__,
            f"Different versions found ({bundle.get_version()} / {module_.__version__})",
        )

        # Remove the bundle
        bundle.uninstall()


# ------------------------------------------------------------------------------


class LocalBundleTest(unittest.TestCase):
    """
    Tests the installation of the __main__ bundle
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def testLocalBundle(self):
        """
        Tests the correctness of the __main__ bundle objects in the framework
        """
        fw_context = self.framework.get_bundle_context()
        assert isinstance(fw_context, BundleContext)

        # Install local bundle in framework (for service installation & co)
        bundle = fw_context.install_bundle(__name__)

        # Get a reference to the bundle, by name
        bundle_2 = fw_context.get_framework().get_bundle_by_name(__name__)

        self.assertIs(bundle, bundle_2, "Different bundle returned by ID and by name")

        # Validate the symbolic name
        self.assertEqual(
            bundle.get_symbolic_name(),
            __name__,
            f"Bundle ({bundle.get_symbolic_name()}) and module ({__name__}) are different",
        )

        # Validate get_bundle() via bundle context
        context_bundle = bundle.get_bundle_context().get_bundle()
        self.assertIs(
            bundle,
            context_bundle,
            f"Not the same bundle:\n{id(bundle):d} / {bundle}\n{id(context_bundle):d} / {context_bundle}",
        )

        # Validate get_version()
        self.assertEqual(
            bundle.get_version(),
            __version__,
            f"Not the same version {__version__} -> {bundle.get_version()}",
        )

        # Validate get_location()
        self.assertEqual(
            bundle.get_location(),
            __file__,
            f"Not the same location {__file__} -> {bundle.get_location()}",
        )


# ------------------------------------------------------------------------------


class BundleFilesTestCase(unittest.TestCase):
    """
    Base class of the tests installing bundles written in a temporary directory
    """

    def setUp(self):
        """
        Called before each test. Initiates a framework and a directory.
        """
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = pathlib.Path(tmp.name)
        self.counter = 0

        # Needed by the updates, which reload the modules
        sys.path.insert(0, str(self.directory))
        self.addCleanup(sys.path.remove, str(self.directory))

    def tearDown(self):
        """
        Called after each test
        """
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def write(self, relative: str, content: str) -> pathlib.Path:
        """
        Writes a file in the temporary directory
        """
        path = self.directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")
        return path

    def install(self, source: str, files: dict[str, str] | None = None, *, package: bool = False) -> Bundle:
        """
        Installs a bundle with a new name. The files are relative to the
        module file (inside the package for a package), "{name}" being
        replaced by the last part of the bundle name.
        """
        self.counter += 1
        name = f"tmp_bundle_{id(self)}_{self.counter}"
        self.addCleanup(lambda: [sys.modules.pop(n) for n in list(sys.modules) if n.split(".")[0] == name])
        base = f"{name}/" if package else ""
        self.write(f"{base}__init__.py" if package else f"{name}.py", source)
        for relative, content in (files or {}).items():
            self.write(base + relative.replace("{name}", name), content)
        return self.context.install_bundle(name, self.directory)


class BundleMetadataTest(BundleFilesTestCase):
    """
    Tests the reading of the metadata of the bundles
    """

    BLOCK = """
        \"\"\"
        Documentation.

        .. pelix-bundle
           version = "1.2.3"
           name = "Test"
           [[provide]]
           namespace = "osgi.service"
           objectClass = ["a.B"]

        More documentation.
        \"\"\"
        __version__ = "9.9.9"
        """

    def testBlockPlacements(self):
        """
        Tests the block in the top docstring, in a later string and indented
        """
        later = '"""Doc."""\nimport os\n\n"""\n.. pelix-bundle\n   version = "1.2.3"\n   name = "Test"\n"""\n'
        indented = (
            '"""\n    Doc.\n\n    .. pelix-bundle\n       version = "1.2.3"\n       name = "Test"\n"""\n'
        )
        for label, source in (("top", self.BLOCK), ("later", later), ("indented", indented)):
            with self.subTest(label):
                bundle = self.install(source)
                headers = bundle.get_headers()
                self.assertEqual(headers["version"], "1.2.3")
                self.assertEqual(headers["name"], "Test")
                # The metadata wins over the module attribute
                self.assertEqual(bundle.get_version(), "1.2.3")

    def testHeadersAreImmutable(self):
        """
        Tests that the metadata can't be modified, nested values included
        """
        headers = self.install(self.BLOCK).get_headers()
        self.assertEqual(headers["provide"][0]["objectClass"], ("a.B",))
        with self.assertRaises(TypeError):
            headers["version"] = "2"
        with self.assertRaises(TypeError):
            headers["provide"][0]["objectClass"] = ()

    def testNoMetadata(self):
        """
        Tests the bundles without metadata, with the previous version rules
        """
        for source, version in (
            ("x = 1\n", "0.0.0"),
            ("__version__ = '2.0'\n", "2.0"),
            ("__version_info__ = (3, 1)\n", "3.1"),
        ):
            with self.subTest(source):
                bundle = self.install(source)
                self.assertEqual(dict(bundle.get_headers()), {})
                self.assertEqual(bundle.get_version(), version)

    def testSideFile(self):
        """
        Tests the side file of a module and of a package, and the unused one
        """
        bundle = self.install("x = 1\n", {"{name}.manifest.toml": 'version = "4.5.6"\n'})
        self.assertEqual(bundle.get_version(), "4.5.6")

        bundle = self.install("x = 1\n", {"{name}.manifest.toml": 'version = "7.8.9"\n'}, package=True)
        self.assertEqual(bundle.get_version(), "7.8.9")

        # Not a name of the supported convention
        bundle = self.install("x = 1\n", {"{name}.toml": 'version = "1.0"\n'})
        self.assertEqual(dict(bundle.get_headers()), {})

    def testBlockAndSideFile(self):
        """
        Tests a block and a side file: same content is accepted with a warning
        """
        side = {"{name}.manifest.toml": 'name = "Test"\nversion = "1.2.3"\n'}
        with self.assertLogs("pelix.internals.metadata", "WARNING"):
            bundle = self.install(
                self.BLOCK.replace("[[provide]]", "").replace("namespace", "#").replace("objectClass", "#"),
                side,
            )
        self.assertEqual(bundle.get_headers()["version"], "1.2.3")

        with self.assertRaises(BundleException):
            self.install(self.BLOCK, {"{name}.manifest.toml": 'version = "0.0.1"\n'})

    def testInvalidMetadata(self):
        """
        Tests the metadata which refuse the installation, without importing the module
        """
        block = '"""\n.. pelix-bundle\n   {}\n"""\nraise RuntimeError("imported")\n'
        cases = {
            "two blocks": '"""\n.. pelix-bundle\n   a = 1\n"""\n"""\n.. pelix-bundle\n   a = 1\n"""\nraise RuntimeError\n',
            "bad TOML": block.format("version ="),
            "version not a string": block.format("version = 1"),
            "other symbolic name": block.format('symbolic-name = "other"'),
            "syntax error": '"""\n.. pelix-bundle\n   a = 1\n"""\ndef x(:\n',
        }
        for label, source in cases.items():
            with self.subTest(label):
                before = len(self.framework.get_bundles())
                with self.assertRaises(BundleException):
                    self.install(source)
                self.assertEqual(len(self.framework.get_bundles()), before)

    def testUpdate(self):
        """
        Tests that the metadata follows the updates, and that an invalid one is kept out
        """
        bundle = self.install('"""\n.. pelix-bundle\n   version = "1.0"\n"""\n')
        module_file = pathlib.Path(bundle.get_location())
        module_file.write_text('"""\n.. pelix-bundle\n   version = "2.0"\n"""\n', encoding="utf-8")
        bundle.update()
        self.assertEqual(bundle.get_version(), "2.0")

        module_file.write_text('"""\n.. pelix-bundle\n   version = \n"""\n', encoding="utf-8")
        bundle.update()
        self.assertEqual(bundle.get_version(), "2.0")


class BundleResourcesTest(BundleFilesTestCase):
    """
    Tests the resources of the bundles
    """

    FILES: ClassVar[dict[str, str]] = {
        "{name}.res/a.txt": "A",
        "{name}.res/sub/b.json": "{}",
        "{name}.res/sub/c.txt": "C",
        "{name}.res/sub/deep/d.txt": "D",
    }

    def check(self, bundle: Bundle) -> None:
        """
        Checks the entries of a bundle with the FILES
        """
        entry = bundle.get_entry("sub/c.txt")
        assert entry is not None
        self.assertEqual(entry.read_text(), "C")
        assert bundle.get_entry("sub") is not None
        assert bundle.get_entry("") is not None
        self.assertIsNone(bundle.get_entry("missing.txt"))

        for args, expected in (
            ((), ["a.txt"]),
            (("sub",), ["sub/b.json", "sub/c.txt"]),
            (("", "*.txt", True), ["a.txt", "sub/c.txt", "sub/deep/d.txt"]),
            (("sub", "*", True), ["sub/b.json", "sub/c.txt", "sub/deep/d.txt"]),
            (("missing",), []),
        ):
            with self.subTest(args):
                self.assertEqual(bundle.find_entries(*args), expected)

    def testModule(self):
        """
        Tests the resources of a module bundle, in the <module>.res directory
        """
        bundle = self.install("x = 1\n", self.FILES)
        self.check(bundle)

    def testNoResources(self):
        """
        Tests a module without resources directory, and a module-level directory
        """
        bundle = self.install("x = 1\n")
        self.assertIsNone(bundle.get_entry("a.txt"))
        self.assertEqual(bundle.find_entries("", "*", True), [])

    def testZip(self):
        """
        Tests the resources of a module bundle in a zip archive
        """
        self.counter += 1
        name = f"tmp_bundle_zip_{id(self)}"
        self.addCleanup(lambda: sys.modules.pop(name, None))
        archive = self.directory / "bundle.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr(f"{name}.py", "x = 1\n")
            for relative, content in self.FILES.items():
                zipped.writestr(relative.replace("{name}", name), content)
        self.check(self.context.install_bundle(name, archive))

    def testPackage(self):
        """
        Tests the resources of a package bundle, which are the files of the package
        """
        files = {"a.txt": "A", "sub/b.json": "{}", "sub/c.txt": "C", "sub/deep/d.txt": "D"}
        bundle = self.install("x = 1\n", files, package=True)
        entry = bundle.get_entry("sub/c.txt")
        assert entry is not None
        self.assertEqual(entry.read_text(), "C")
        self.assertEqual(bundle.find_entries("", "*.txt", True), ["a.txt", "sub/c.txt", "sub/deep/d.txt"])

    def testRefusedPaths(self):
        """
        Tests that the paths leaving the resources root are refused
        """
        bundle = self.install("x = 1\n", self.FILES)
        self.write("secret.txt", "S")
        for path in (
            "../secret.txt",
            "sub/../../secret.txt",
            "..",
            str(self.directory / "secret.txt"),
            "/etc/passwd",
            "\\x",
        ):
            with self.subTest(path):
                with self.assertRaises(ValueError):
                    bundle.get_entry(path)
                with self.assertRaises(ValueError):
                    bundle.find_entries(path)


if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
