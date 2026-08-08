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

import unittest
from threading import Event

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 2, 2)
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
