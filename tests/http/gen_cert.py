#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
A utility script to generate test certificates for HTTPS

:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2025 Thomas Calmant

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

import argparse
import os
import subprocess
from typing import Any, List, Optional

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def find_openssl() -> str:
    """
    Looks for the OpenSSL executable

    :return: The absolute path to OpenSSL
    """
    name = "openssl"
    paths = (os.getenv("PATH") or "").split(os.path.pathsep)

    if os.name == "nt":
        # On Windows, look for openssl.exe
        # Also look in the install path for "Git for Windows"
        name += ".exe"
        git_install = os.path.join(os.path.expandvars("%PROGRAMFILES%"), "Git", "usr", "bin")
        paths.append(git_install)

    for path in paths:
        exe = os.path.join(path, name)
        if os.path.exists(exe):
            return exe
    else:
        raise IOError(f"{name} not found in PATH")


def call_openssl(*args: Any) -> None:
    """
    Calls the openssl command

    :param args: OpenSSL arguments
    """
    subprocess.check_output([find_openssl()] + [str(arg) for arg in args], stderr=subprocess.STDOUT)


def write_conf(out_dir: str) -> str:
    """
    Writes the configuration file for OpenSSL

    :param out_dir: Output directory
    :return: The path to the configuration file
    """
    config_file = os.path.join(out_dir, "openssl.cnf")
    with open(config_file, "w+") as fp:
        fp.write(
            """[ req ]
prompt = yes
distinguished_name = req_distinguished_name
x509_extensions = v3_ca

[ req_distinguished_name ]

[ v3_ca ]
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer:always
basicConstraints = critical, CA:true
keyUsage = critical, keyCertSign, cRLSign
"""
        )

    return config_file


def make_subj(common_name: str, encrypted: bool = False) -> str:
    """
    Make a subject string

    :param common_name: Common name used in certificate
    :param encrypted: Add the encrypted flag to the organisation
    :return: A subject string
    """
    return (
        f"/C=FR/ST=Auvergne-Rhone-Alpes/L=Grenoble/O=iPOPO Tests "
        f"({'encrypted' if encrypted else 'plain'})/CN={common_name}"
    )


def make_certs(out_dir: str, key_password: Optional[str]) -> None:
    """
    Generates a certificate chain and two certificates: one with a password and
    one without

    :param out_dir: Output directory
    :param key_password: Password for the protected key
    """
    # Write the configuration file
    config_file = write_conf(out_dir)

    # Make CA key and certificate
    print("--- Preparing CA key and certificate ---")
    call_openssl(
        "req",
        "-new",
        "-x509",
        "-days",
        1,
        "-subj",
        make_subj("iPOPO Test CA"),
        "-keyout",
        os.path.join(out_dir, "ca.key"),
        "-out",
        os.path.join(out_dir, "ca.crt"),
        "-config",
        config_file,
        "-nodes",
    )

    # Make server keys
    print("--- Preparing Server keys ---")
    call_openssl("genrsa", "-out", os.path.join(out_dir, "server.key"), 2048)

    if key_password:
        call_openssl(
            "genrsa",
            "-out",
            os.path.join(out_dir, "server_enc.key"),
            "-des3",
            "-passout",
            "pass:" + key_password,
            2048,
        )

    # Make signing requests
    print("--- Preparing Server certificate requests ---")
    call_openssl(
        "req",
        "-subj",
        make_subj("localhost"),
        "-out",
        os.path.join(out_dir, "server.csr"),
        "-key",
        os.path.join(out_dir, "server.key"),
        "-config",
        config_file,
        "-new",
    )

    if key_password:
        call_openssl(
            "req",
            "-subj",
            make_subj("localhost", True),
            "-out",
            os.path.join(out_dir, "server_enc.csr"),
            "-key",
            os.path.join(out_dir, "server_enc.key"),
            "-passin",
            "pass:" + key_password,
            "-config",
            config_file,
            "-new",
        )

    # Sign server certificates
    print("--- Signing Server keys ---")
    call_openssl(
        "x509",
        "-req",
        "-in",
        os.path.join(out_dir, "server.csr"),
        "-CA",
        os.path.join(out_dir, "ca.crt"),
        "-CAkey",
        os.path.join(out_dir, "ca.key"),
        "-CAcreateserial",
        "-out",
        os.path.join(out_dir, "server.crt"),
        "-days",
        1,
    )

    if key_password:
        call_openssl(
            "x509",
            "-req",
            "-in",
            os.path.join(out_dir, "server_enc.csr"),
            "-CA",
            os.path.join(out_dir, "ca.crt"),
            "-CAkey",
            os.path.join(out_dir, "ca.key"),
            "-CAcreateserial",
            "-out",
            os.path.join(out_dir, "server_enc.crt"),
            "-days",
            1,
        )


def main(args: Optional[List[str]] = None) -> None:
    """
    Entry point
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", help="Output folder", default="tmp")
    parser.add_argument("-p", "--password", help="Server key password", required=True)
    options = parser.parse_args(args)

    if not os.path.exists(options.output):
        os.makedirs(options.output)

    make_certs(options.output, options.password)


if __name__ == "__main__":
    main()
