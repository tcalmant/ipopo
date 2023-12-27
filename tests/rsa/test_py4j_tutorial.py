#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the RSA Py4J provider, using the tutorial

:author: Thomas Calmant
"""

import io
import os
import subprocess
import tarfile
import tempfile
import time
import unittest
from contextlib import contextmanager
from typing import Generator, Optional
from urllib.request import urlopen

from pelix.framework import create_framework

# ------------------------------------------------------------------------------

KARAF_URL = "http://apache.mediamirrors.org/karaf/4.2.10/apache-karaf-4.2.10.tar.gz"

__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


def install_karaf(folder: Optional[str] = None) -> None:
    """
    Downloads & decompress Karaf tar file

    :param folder: Folder where to decompress the TAR file
    """
    cur_dir = os.getcwd()
    if folder:
        os.makedirs(folder, exist_ok=True)
        os.chdir(folder)
    else:
        folder = cur_dir

    try:
        # Check if Karaf already exists
        find_karaf_root(folder)
    except IOError:
        print("Karaf not found, installing it.")
        with tempfile.TemporaryFile() as fd:
            with urlopen(KARAF_URL) as req:
                fd.write(req.read())

            fd.seek(0)
            with tarfile.open(fileobj=fd, mode="r:gz") as tar:

                def is_within_directory(directory, target):
                    abs_directory = os.path.abspath(directory)
                    abs_target = os.path.abspath(target)

                    prefix = os.path.commonprefix([abs_directory, abs_target])

                    return prefix == abs_directory

                def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
                    for member in tar.getmembers():
                        member_path = os.path.join(path, member.name)
                        if not is_within_directory(path, member_path):
                            raise Exception("Attempted Path Traversal in Tar File")

                    tar.extractall(path, members, numeric_owner=numeric_owner)

                safe_extract(tar)
    else:
        print("Karaf found.")
    finally:
        os.chdir(cur_dir)


def find_karaf_root(folder: Optional[str] = None) -> str:
    """
    Looks for the Karaf root folder in the given directory

    :param folder: Optional known parent folder for the Karaf home
    :return: Path to the Karaf home directory
    :raises IOError: Karaf not found
    """
    karaf_prefix = "apache-karaf-"
    if not folder:
        folder = os.getcwd()

    if os.path.basename(folder).startswith(karaf_prefix):
        return folder

    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if name.startswith(karaf_prefix) and os.path.isdir(path):
            return path

    raise IOError("Karaf folder not found in {}".format(folder))


def start_karaf(karaf_root: str) -> subprocess.Popen:
    """
    Starts Karaf

    :param karaf_root: Root of the Karaf installation (contains bin/)
    :return: A Popen object
    """
    if os.name == "nt":
        script_name = "karaf.bat"
    else:
        script_name = "karaf"

    return subprocess.Popen(
        [os.path.join(karaf_root, "bin", script_name)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def wait_for_prompt(process: subprocess.Popen, prompt: str = "karaf@root()>") -> None:
    """
    Reads the stdout of a process until a prompt is seen

    :param process: A Popen object, with decoded I/O
    :param prompt: The string to look for
    """
    if process.stdout is None:
        raise IOError("Can't read from process")

    output = io.StringIO()
    while True:
        data = process.stdout.read(1)
        if not data:
            # Process ended
            return
        elif data == b"\n":
            # Got a new line, reset the buffer
            output = io.StringIO()
        else:
            output.write(data.decode("UTF-8"))
            if prompt in output.getvalue():
                # Found the prompt
                return


@contextmanager
def use_karaf() -> Generator[subprocess.Popen, None, None]:
    """
    A context that prepares a Karaf installation before giving the hand
    """
    karaf_dir = os.environ.get("KARAF_DIR")

    # Start Karaf
    start = time.time()
    install_karaf(karaf_dir)
    print("Karaf installed in", round(time.time() - start, 3), "s")
    karaf_root = find_karaf_root(karaf_dir)

    start = time.time()
    with start_karaf(karaf_root) as karaf:
        if karaf.stdin is None or karaf.stdout is None:
            raise IOError("Can't access Karaf I/O")

        # Wait for Karaf to start
        wait_for_prompt(karaf)
        print(round(time.time() - start, 3), "- Karaf started")

        # Add the ECF repository
        karaf.stdin.write(b"feature:repo-add ecf\n")
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
            # Exit Karaf
            karaf.stdin.write(b"logout\n")


# ------------------------------------------------------------------------------


class Py4JTutorialTest(unittest.TestCase):
    """
    Tests the Py4J Tutorial
    """

    @classmethod
    def setUpClass(cls):
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

    def test_service_import(self):
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

                for _ in range(10):
                    # Check if we find the Hello world service
                    svc_ref = bc.get_service_reference(
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
