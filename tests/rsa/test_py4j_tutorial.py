#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the RSA Py4J provider, using the tutorial

:author: Thomas Calmant
"""

import io
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from contextlib import contextmanager
from typing import Any, Generator, Iterable, Optional
from urllib.request import urlopen

from pelix.framework import create_framework
from pelix.internals.registry import ServiceReference

try:
    import osgiservicebridge
except ImportError:
    unittest.skip("OSGi Service Bridge not available")

unittest.skip("Skipping Py4J tests due to issues with Karaf not starting correctly")

# ------------------------------------------------------------------------------

KARAF_URL = "https://archive.apache.org/dist/karaf/4.4.6/apache-karaf-4.4.6.tar.gz"

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


def install_karaf(folder_str: Optional[str]=None) -> pathlib.Path:
    """
    Downloads & decompress Karaf tar file

    :param folder: Folder where to decompress the TAR file
    """
    cur_dir = pathlib.Path().absolute()
    if folder_str:
        folder = pathlib.Path(folder_str)
        folder.mkdir(parents=True, exist_ok=True)
    else:
        folder = cur_dir

    try:
        # Check if Karaf already exists
        root = find_karaf_root(folder)
        print("Karaf found.")
        return root
    except IOError:
        print("Karaf not found, installing it.")
        with tempfile.TemporaryFile() as fd:
            with urlopen(KARAF_URL) as req:
                fd.write(req.read())

            fd.seek(0)
            with tarfile.open(fileobj=fd, mode="r:gz") as tar:

                def is_within_directory(directory: str, target: str) -> bool:
                    abs_directory = os.path.abspath(directory)
                    abs_target = os.path.abspath(target)

                    prefix = os.path.commonprefix([abs_directory, abs_target])

                    return prefix == abs_directory

                def safe_extract(
                    tar: tarfile.TarFile,
                    path: str=".",
                    members: Optional[Iterable[tarfile.TarInfo]]=None,
                    *,
                    numeric_owner: bool=False
                ) -> None:
                    for member in tar.getmembers():
                        member_path = os.path.join(path, member.name)
                        if not is_within_directory(path, member_path):
                            raise Exception("Attempted Path Traversal in Tar File")

                    # Filter out examples: paths are too long for Windows
                    filtered_members = (m for m in members or tar.getmembers() if "examples" not in m.path)

                    try:
                        os.chdir(folder)
                        if sys.version_info < (3, 12):
                            tar.extractall(path, filtered_members, numeric_owner=numeric_owner)
                        else:
                            tar.extractall(path, filtered_members, numeric_owner=numeric_owner, filter="data")
                    finally:
                        os.chdir(cur_dir)

                safe_extract(tar)
            return folder


def find_karaf_root(folder: Optional[pathlib.Path]=None) -> pathlib.Path:
    """
    Looks for the Karaf root folder in the given directory

    :param folder: Optional known parent folder for the Karaf home
    :return: Path to the Karaf home directory
    :raises IOError: Karaf not found
    """
    karaf_prefix = "apache-karaf-"
    if not folder:
        folder = pathlib.Path(".").absolute()

    if folder.name.startswith(karaf_prefix):
        return folder

    for path in folder.iterdir():
        if path.name.startswith(karaf_prefix) and path.is_dir():
            return path

    raise IOError("Karaf folder not found in {}".format(folder))


@contextmanager
def start_karaf(karaf_root: pathlib.Path) -> Generator[subprocess.Popen, None, None]:
    """
    Starts Karaf

    :param karaf_root: Root of the Karaf installation (contains bin/)
    :return: A Popen object
    """
    if os.name == "nt":
        script_name = "karaf.bat"
    else:
        script_name = "karaf"

    karaf = None
    try:
        karaf = subprocess.Popen(
            [os.path.join(karaf_root, "bin", script_name)],
            cwd=karaf_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        yield karaf
    finally:
        if karaf is not None:
            karaf.kill()
            karaf.wait(1)
            karaf = None


def wait_for_prompt(process: subprocess.Popen, prompt: str="karaf@root()>") -> None:
    """
    Reads the stdout of a process until a prompt is seen

    :param process: A Popen object, with decoded I/O
    :param prompt: The string to look for
    """
    if process.stdout is None:
        raise IOError("Can't read from process")

    charset = "utf-8" if not os.name == "nt" else "cp850"

    buffer = io.BytesIO()
    while True:
        data = process.stdout.read(1)
        if not data:
            # Process ended
            return
        elif data == b"\n":
            # Got a new line, reset the buffer
            try:
                print("-", buffer.getvalue().decode(charset))
            except UnicodeDecodeError:
                print("Error decoding line", buffer.getvalue())

            buffer = io.BytesIO()
        else:
            buffer.write(data)
            try:
                # Try decoding the whole buffer
                output = buffer.getvalue().decode(charset)
                if prompt in output:
                    # Found the prompt
                    return
            except UnicodeDecodeError:
                # Ignore errors, we might have an incomplete character
                pass


@contextmanager
def use_karaf() -> Generator[subprocess.Popen, None, None]:
    """
    A context that prepares a Karaf installation before giving the hand
    """
    karaf_dir = os.environ.get("KARAF_DIR")

    # Start Karaf
    start = time.time()
    karaf_path = install_karaf(karaf_dir)
    print("Karaf installed in", round(time.time() - start, 3), "s")
    karaf_root = find_karaf_root(karaf_path)

    start = time.time()
    with start_karaf(karaf_root) as karaf:
        if karaf.stdin is None or karaf.stdout is None:
            raise IOError("Can't access Karaf I/O")

        # Wait for Karaf to start
        wait_for_prompt(karaf)
        print(round(time.time() - start, 3), "- Karaf started")

        # Add the ECF repository
        karaf.stdin.write(b"feature:repo-add https://download.eclipse.org/rt/ecf/latest/karaf-features.xml\n")
        karaf.stdin.flush()
        wait_for_prompt(karaf)
        print(round(time.time() - start, 3), "- ECF repository added")

        # Install the tutorial sample
        karaf.stdin.write(b"feature:install -v ecf-rs-examples-python.java-hello\n")
        karaf.stdin.flush()
        wait_for_prompt(karaf)
        print(round(time.time() - start, 3), "- Feature installed")

        # Give hand to the caller
        try:
            yield karaf
        finally:
            try:
                # Exit Karaf
                karaf.stdin.write(b"logout\n")
            except Exception as e:
                print("Error while exiting Karaf:", e)

# ------------------------------------------------------------------------------


class Py4JTutorialTest(unittest.TestCase):
    """
    Tests the Py4J Tutorial
    """

    @classmethod
    def setUpClass(cls) -> None:
        """
        Preliminary checks
        """
        # Check if Java is installed
        try:
            java = subprocess.Popen(
                ["java -version"],
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            java.wait()
        except OSError:
            raise unittest.SkipTest("Java is not installed.")

    def test_service_import(self) -> None:
        """
        Tests the import of a service from Py4J
        """
        bundles = [
            "pelix.ipopo.core",
            "pelix.rsa.remoteserviceadmin",
            "pelix.rsa.topologymanagers.basic",
            "pelix.rsa.providers.distribution.py4j",
            "samples.rsa.helloconsumer",
        ]

        with use_karaf():
            # Start the framework
            fw = create_framework(
                bundles,
                {"ecf.py4j.javaport": 25333, "ecf.py4j.pythonport": 25334},
            )

            try:
                fw.start()
                bc = fw.get_bundle_context()

                from pelix.rsa.topologymanagers.basic import instantiate_basic_topology_manager
                instantiate_basic_topology_manager(bc)

                for _ in range(10):
                    # Check if we find the Hello world service
                    svc_ref: Optional[ServiceReference[Any]] = bc.get_service_reference(
                        "org.eclipse.ecf.examples.hello.IHello",
                        "(service.imported=*)",
                    )
                    if svc_ref is not None:
                        # Found the service reference: service imported
                        break

                    time.sleep(0.5)
                else:
                    # Service not found after 5 seconds
                    self.fail("Py4J service not found")
            finally:
                # Clean up the framework
                fw.delete(True)
