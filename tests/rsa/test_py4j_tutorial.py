#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the RSA Py4J provider, using the tutorial

:author: Thomas Calmant
"""

import contextlib
import importlib.util
import io
import os
import pathlib
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from typing import Any
from urllib.request import urlopen

from pelix.framework import create_framework
from pelix.internals.registry import ServiceReference

if importlib.util.find_spec("osgiservicebridge") is None:
    raise unittest.SkipTest("OSGi Service Bridge not available")

# ------------------------------------------------------------------------------

# Maven Central rather than archive.apache.org, which is heavily throttled
KARAF_URL = "https://repo1.maven.org/maven2/org/apache/karaf/apache-karaf/4.4.11/apache-karaf-4.4.11.tar.gz"

# Socket timeout (in seconds): a stalled download must not eat the CI job time
DOWNLOAD_TIMEOUT = 30

# Karaf 4.4 can't run on Java 24+, which removed the Security Manager: from there,
# the bundles of the ECF feature run in a bare Felix
FELIX_URL = (
    "https://repo1.maven.org/maven2/org/apache/felix/org.apache.felix.main.distribution/7.0.5/"
    "org.apache.felix.main.distribution-7.0.5.tar.gz"
)
MAVEN = "https://repo1.maven.org/maven2/"
ECF_PY4J = "https://raw.githubusercontent.com/ECF/Py4j-RemoteServicesProvider/master/build/plugins/"
FELIX_BUNDLES = [
    # What Karaf provides
    MAVEN + "org/apache/felix/org.apache.felix.scr/2.2.18/org.apache.felix.scr-2.2.18.jar",
    MAVEN + "org/apache/felix/org.apache.felix.eventadmin/1.6.4/org.apache.felix.eventadmin-1.6.4.jar",
    MAVEN + "org/apache/felix/org.apache.felix.configadmin/1.9.26/org.apache.felix.configadmin-1.9.26.jar",
    MAVEN + "org/apache/felix/org.apache.felix.log/1.3.2/org.apache.felix.log-1.3.2.jar",
    MAVEN + "org/osgi/org.osgi.service.component/1.5.1/org.osgi.service.component-1.5.1.jar",
    MAVEN + "org/osgi/org.osgi.util.function/1.2.0/org.osgi.util.function-1.2.0.jar",
    MAVEN + "org/osgi/org.osgi.util.promise/1.3.0/org.osgi.util.promise-1.3.0.jar",
    MAVEN + "org/slf4j/slf4j-api/1.7.36/slf4j-api-1.7.36.jar",
    MAVEN + "org/slf4j/slf4j-simple/1.7.36/slf4j-simple-1.7.36.jar",
    # The ecf-rs-examples-python.java-hello feature
    MAVEN
    + "org/eclipse/platform/org.eclipse.equinox.supplement/1.7.0/org.eclipse.equinox.supplement-1.7.0.jar",
    MAVEN + "org/eclipse/platform/org.eclipse.equinox.common/3.9.0/org.eclipse.equinox.common-3.9.0.jar",
    MAVEN + "org/eclipse/platform/org.eclipse.core.jobs/3.9.3/org.eclipse.core.jobs-3.9.3.jar",
    MAVEN
    + "org/eclipse/platform/org.eclipse.equinox.concurrent/1.1.0/org.eclipse.equinox.concurrent-1.1.0.jar",
    MAVEN + "org/eclipse/ecf/org.eclipse.ecf.identity/3.10.0/org.eclipse.ecf.identity-3.10.0.jar",
    MAVEN + "org/eclipse/ecf/org.eclipse.ecf/3.13.0/org.eclipse.ecf-3.13.0.jar",
    MAVEN + "org/eclipse/ecf/org.eclipse.ecf.sharedobject/2.7.0/org.eclipse.ecf.sharedobject-2.7.0.jar",
    MAVEN + "org/eclipse/ecf/org.eclipse.ecf.discovery/5.3.0/org.eclipse.ecf.discovery-5.3.0.jar",
    MAVEN
    + "org/eclipse/ecf/org.eclipse.ecf.remoteservice.asyncproxy/2.1.200/"
    + "org.eclipse.ecf.remoteservice.asyncproxy-2.1.200.jar",
    MAVEN + "org/eclipse/ecf/org.eclipse.ecf.remoteservice/8.15.0/org.eclipse.ecf.remoteservice-8.15.0.jar",
    MAVEN
    + "org/eclipse/ecf/org.eclipse.osgi.services.remoteserviceadmin/1.7.0/"
    + "org.eclipse.osgi.services.remoteserviceadmin-1.7.0.jar",
    MAVEN
    + "org/eclipse/ecf/org.eclipse.ecf.osgi.services.remoteserviceadmin.proxy/1.0.102/"
    + "org.eclipse.ecf.osgi.services.remoteserviceadmin.proxy-1.0.102.jar",
    MAVEN
    + "org/eclipse/ecf/org.eclipse.ecf.osgi.services.remoteserviceadmin/4.9.3/"
    + "org.eclipse.ecf.osgi.services.remoteserviceadmin-4.9.3.jar",
    MAVEN
    + "org/eclipse/ecf/org.eclipse.ecf.osgi.services.distribution/2.2.0/"
    + "org.eclipse.ecf.osgi.services.distribution-2.2.0.jar",
    "https://raw.githubusercontent.com/ECF/Py4j-OSGi/master/build/plugins/org.py4j.osgi_1.6.1.202505311223.jar",
    ECF_PY4J + "org.apache.commons.commons-exec_1.5.0.jar",
    ECF_PY4J + "com.google.protobuf_4.31.1.jar",
    ECF_PY4J + "org.eclipse.ecf.provider.direct_2.3.4.202505311223.jar",
    ECF_PY4J + "org.eclipse.ecf.provider.direct.protobuf_2.2.4.202505311223.jar",
    ECF_PY4J + "org.eclipse.ecf.provider.py4j_2.4.2.202505311223.jar",
    ECF_PY4J + "org.eclipse.ecf.provider.py4j.protobuf_1.6.2.202505311223.jar",
    ECF_PY4J + "org.eclipse.ecf.python_1.1.1.202505311223.jar",
    ECF_PY4J + "org.eclipse.ecf.python.protobuf_1.3.0.202505311223.jar",
    ECF_PY4J + "org.eclipse.ecf.examples.hello_1.1.3.202505311223.jar",
    ECF_PY4J + "org.eclipse.ecf.examples.hello.javahost_1.1.5.202505311223.jar",
]

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------


def install_karaf(folder_str: str | None = None) -> pathlib.Path:
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
    except OSError:
        print("Karaf not found, installing it.")
        with tempfile.TemporaryFile() as fd:
            with urlopen(KARAF_URL, timeout=DOWNLOAD_TIMEOUT) as req:
                fd.write(req.read())

            fd.seek(0)
            with tarfile.open(fileobj=fd, mode="r:gz") as tar:

                def is_within_directory(directory: str, target: str) -> bool:
                    abs_directory = os.path.abspath(directory)
                    abs_target = os.path.abspath(target)

                    try:
                        prefix = os.path.commonpath([abs_directory, abs_target])
                    except ValueError:
                        return False

                    return prefix == abs_directory

                def safe_extract(
                    tar: tarfile.TarFile,
                    path: str = ".",
                    members: Iterable[tarfile.TarInfo] | None = None,
                    *,
                    numeric_owner: bool = False,
                ) -> None:
                    for member in tar.getmembers():
                        member_path = os.path.join(path, member.name)
                        if not is_within_directory(path, member_path):
                            raise OSError("Attempted Path Traversal in Tar File")

                    # Filter out examples: paths are too long for Windows
                    filtered_members = (m for m in members or tar.getmembers() if "examples" not in m.path)

                    with contextlib.chdir(folder):
                        if sys.version_info < (3, 12):
                            tar.extractall(path, filtered_members, numeric_owner=numeric_owner)
                        else:
                            tar.extractall(path, filtered_members, numeric_owner=numeric_owner, filter="data")

                safe_extract(tar)
            return folder


def find_karaf_root(folder: pathlib.Path | None = None) -> pathlib.Path:
    """
    Looks for the Karaf root folder in the given directory

    :param folder: Optional known parent folder for the Karaf home
    :return: Path to the Karaf home directory
    :raises OSError: Karaf not found
    """
    karaf_prefix = "apache-karaf-"
    if not folder:
        folder = pathlib.Path(".").absolute()

    if folder.name.startswith(karaf_prefix):
        return folder

    for path in folder.iterdir():
        if path.name.startswith(karaf_prefix) and path.is_dir():
            return path

    raise OSError(f"Karaf folder not found in {folder}")


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


def wait_for_prompt(process: subprocess.Popen, prompt: str = "karaf@root()>") -> str:
    """
    Reads the stdout of a process until a prompt is seen

    :param process: A Popen object, with decoded I/O
    :param prompt: The string to look for
    :return: The lines read before the prompt
    """
    if process.stdout is None:
        raise OSError("Can't read from process")

    charset = "utf-8" if os.name != "nt" else "cp850"

    lines: list[str] = []
    buffer = io.BytesIO()
    while True:
        data = process.stdout.read(1)
        if not data:
            # Process ended
            return "\n".join(lines)
        elif data == b"\n":
            # Got a new line, reset the buffer
            try:
                lines.append(buffer.getvalue().decode(charset))
                print("-", lines[-1])
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
                    return "\n".join(lines)
            except UnicodeDecodeError:
                # Ignore errors, we might have an incomplete character
                pass


@contextmanager
def use_felix(java_bin: str) -> Generator[subprocess.Popen, None, None]:
    """
    Runs the bundles of the ECF tutorial feature in a bare Felix, until the
    Py4J gateway of the Java side listens

    :param java_bin: The Java executable
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        with (
            urlopen(FELIX_URL, timeout=DOWNLOAD_TIMEOUT) as req,
            tarfile.open(fileobj=req, mode="r|gz") as tar,
        ):
            if hasattr(tarfile, "data_filter"):
                tar.extractall(tmp_dir, filter="data")
            else:
                tar.extractall(tmp_dir)

        root = next(pathlib.Path(tmp_dir).iterdir())
        # Only our bundles: the default shell needs a terminal
        bundles = root / "bundle"
        for path in bundles.iterdir():
            path.unlink()
        for url in FELIX_BUNDLES:
            with urlopen(url, timeout=DOWNLOAD_TIMEOUT) as req:
                (bundles / url.rsplit("/", 1)[1]).write_bytes(req.read())

        felix = subprocess.Popen(
            [java_bin, "-jar", "bin/felix.jar"],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.time() + 60
            while time.time() < deadline:
                with socket.socket() as sock:
                    if sock.connect_ex(("127.0.0.1", 25333)) == 0:
                        break
                time.sleep(0.5)
            else:
                raise OSError("The Py4J gateway of Felix didn't start")

            yield felix
        finally:
            felix.kill()
            felix.wait(5)


@contextmanager
def use_karaf() -> Generator[subprocess.Popen, None, None]:
    """
    A context that prepares a Karaf installation before giving the hand
    (a bare Felix from Java 24)
    """
    karaf_dir = os.environ.get("KARAF_DIR")
    java_home = os.environ.get("JAVA_HOME")

    # Check Java version
    if java_home:
        java_bin = os.path.join(java_home, "bin", "java" if os.name != "nt" else "java.exe")
    else:
        java_bin = "java"

    try:
        version_output = subprocess.run(
            [java_bin, "-version"],
            capture_output=True,
            check=False,
        )
        assert version_output.returncode == 0, "Java is not installed or not working"

        match = re.search(r'version "(?P<version>\d+)\.\d+', version_output.stderr.decode("utf-8"))
        if match:
            major_version = int(match.group("version"))
            if major_version < 11:
                raise unittest.SkipTest(f"Java version is too old ({major_version}), need at least Java 11")
        else:
            raise unittest.SkipTest("Can't determine Java version")
    except OSError:
        raise unittest.SkipTest("Java is not installed.")
    except AssertionError as e:
        raise unittest.SkipTest(str(e))

    if major_version >= 24:
        with use_felix(java_bin) as felix:
            yield felix
        return

    # Start Karaf
    start = time.time()
    karaf_path = install_karaf(karaf_dir)
    print("Karaf installed in", round(time.time() - start, 3), "s")
    karaf_root = find_karaf_root(karaf_path)

    start = time.time()
    with start_karaf(karaf_root) as karaf:
        if karaf.stdin is None or karaf.stdout is None:
            raise OSError("Can't access Karaf I/O")

        # Wait for Karaf to start
        wait_for_prompt(karaf)
        print(round(time.time() - start, 3), "- Karaf started")

        # Add the ECF repository
        karaf.stdin.write(b"feature:repo-add https://download.eclipse.org/rt/ecf/latest/karaf-features.xml\n")
        karaf.stdin.flush()
        wait_for_prompt(karaf)
        print(round(time.time() - start, 3), "- ECF repository added")

        # Install the tutorial sample
        for _ in range(3):
            karaf.stdin.write(b"feature:install -v ecf-rs-examples-python.java-hello\n")
            karaf.stdin.flush()
            if "Error executing command" not in wait_for_prompt(karaf):
                break

            # download.eclipse.org sometimes serves an unusable repository: reload it
            time.sleep(5)
            karaf.stdin.write(b"feature:repo-refresh\n")
            karaf.stdin.flush()
            wait_for_prompt(karaf)
        else:
            raise unittest.SkipTest("Can't install the ECF features from download.eclipse.org")
        print(round(time.time() - start, 3), "- Feature installed")

        # Give hand to the caller
        try:
            yield karaf
        finally:
            try:
                # Exit Karaf
                karaf.stdin.write(b"logout\n")
            except Exception as e:  # noqa: BLE001
                print("Error while exiting Karaf:", e)


# ------------------------------------------------------------------------------


class Py4JTutorialTest(unittest.TestCase):
    """
    Tests the Py4J Tutorial
    """

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
            self.addCleanup(fw.delete, True)

            try:
                fw.start()
                bc = fw.get_bundle_context()

                from pelix.rsa.topologymanagers.basic import instantiate_basic_topology_manager

                instantiate_basic_topology_manager(bc)

                for _ in range(10):
                    # Check if we find the Hello world service
                    svc_ref: ServiceReference[Any] | None = bc.get_service_reference(
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
