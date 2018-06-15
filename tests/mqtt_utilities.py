#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Utility methods for MQTT tests

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0

..
    Copyright 2018 Thomas Calmant
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
        http://www.apache.org/licenses/LICENSE-2.0
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 0, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def find_mqtt_server():
    """
    Looks for a working server to run the tests

    :return: The host name of a working MQTT server, else None
    """
    try:
        from pelix.misc.mqtt_client import MqttClient
    except ImportError:
        raise unittest.SkipTest("MQTT client library is missing")

    from threading import Event

    evt = Event()
    clt = MqttClient()

    def handle_disconnect(client, rc):
        evt.set()

    clt.on_disconnect = handle_disconnect

    for server in ('localhost', 'test.mosquitto.org', 'iot.eclipse.org',
                   'broker.hivemq.com'):
        try:
            # Try to connect
            evt.clear()
            clt.connect(server)
        except IOError:
            # Not available
            pass
        else:
            try:
                # Try publishing something
                mid = clt.publish(
                    "/ipopo/test/bootstrap", "initial.data", wait=True)

                if not mid:
                    # Error while publishing: next server
                    continue

                if clt.wait_publication(mid, 1):
                    # Message sent without error and with a correct delay
                    return server
                elif evt.is_set():
                    # Got disconnected while waiting
                    continue
            finally:
                # Disconnect from the server
                clt.disconnect()
