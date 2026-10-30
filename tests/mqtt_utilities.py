#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Utility methods for MQTT tests

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0

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

import pathlib
import socket
import unittest
from threading import Event

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


MQTT_SERVER = "localhost"
"""
Host of the MQTT broker used by the tests: the one from tests-infra.

Public brokers must not be used as a fallback: tests would publish their content
on the Internet, depend on a third party, and each process looking for a server
on its own could end up on a different broker than its peers.
"""

MQTT_CERTS = pathlib.Path(__file__).parent.parent / "tests-infra" / "mqtt" / "certs"
""" Folder of the test CA and client certificate, trusted by the TLS listeners of the broker """


def _read_broker_secrets() -> dict[str, str]:
    """
    Reads the user name and password made by ``tests-infra/mqtt/prepare.sh``

    :return: The variables of the ``.env`` file, empty if it is missing
    """
    try:
        lines = (MQTT_CERTS.parent / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    return dict(line.split("=", 1) for line in lines if "=" in line)


_SECRETS = _read_broker_secrets()

MQTT_USERNAME = _SECRETS.get("MQTT_TEST_USERNAME", "")
""" User name accepted by the password-protected listeners of the broker """

MQTT_PASSWORD = _SECRETS.get("MQTT_TEST_PASSWORD", "")
""" Password of :data:`MQTT_USERNAME`, generated with the certificates """

MQTT_PORT_PASSWORD = 1884
""" Plain listener, user name and password required """

MQTT_PORT_TLS = 8883
""" TLS listener, anonymous """

MQTT_PORT_MTLS = 8884
""" TLS listener, client certificate, user name and password required """

PUBLICATION_TIMEOUT = 10
"""
Time (in seconds) to wait for the test publication to be acknowledged.
Kept large as a loaded machine can be slow to answer, and considering the broker
as missing would only make tests fail later on, in a way harder to understand.
"""


def find_mqtt_server() -> str | None:
    """
    Checks if the MQTT broker of tests-infra is available

    :return: The host name of the MQTT server, else None
    """
    try:
        from pelix.misc.mqtt_client import MqttClient
    except ImportError:
        raise unittest.SkipTest("MQTT client library is missing")

    evt = Event()
    clt = MqttClient()

    def handle_disconnect(client: MqttClient, result_code: int) -> None:
        evt.set()

    clt.on_disconnect = handle_disconnect

    try:
        # Try to connect
        evt.clear()
        clt.connect(MQTT_SERVER, blocking=True)
    except OSError:
        # Not available
        return None

    try:
        # Try publishing something
        mid = clt.publish("/ipopo/test/bootstrap", "initial.data", wait=True)
        if mid is None:
            # Error while publishing
            return None

        if clt.wait_publication(mid, PUBLICATION_TIMEOUT):
            # Message sent without error and with a correct delay
            return MQTT_SERVER
    finally:
        # Disconnect from the server
        clt.disconnect()

    return None


def has_mqtt_secure_listeners() -> bool:
    """
    Checks if the broker has the TLS and password listeners of tests-infra,
    missing when it was started from an older configuration or without prepare.sh

    :return: True if all the listeners accept connections, and their secrets exist
    """
    if not MQTT_PASSWORD or not (MQTT_CERTS / "ca.crt").exists():
        return False

    for port in (MQTT_PORT_PASSWORD, MQTT_PORT_TLS, MQTT_PORT_MTLS):
        try:
            socket.create_connection((MQTT_SERVER, port), 2).close()
        except OSError:
            return False
    return True
