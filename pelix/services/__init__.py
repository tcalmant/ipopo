#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix OSGi-like services packages

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

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

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Service Registry Hooks

SERVICE_EVENT_LISTENER_HOOK = "pelix.internal.hooks.EventListenerHook"
# ------------------------------------------------------------------------------

FACTORY_EVENT_ADMIN = "pelix-services-eventadmin-factory"
""" Name of the EventAdmin component factory """

FACTORY_EVENT_ADMIN_MQTT = "pelix-services-eventadmin-mqtt-factory"
""" Name of the component factory of the MQTT bridge for EventAdmin """

# ------------------------------------------------------------------------------

SERVICE_EVENT_ADMIN = "pelix.services.eventadmin"
""" Specification of the EventAdmin service """

SERVICE_EVENT_HANDLER = "pelix.services.eventadmin.handler"
""" Specification of an EventAdmin event handler """

PROP_EVENT_TOPICS = "event.topics"
""" **List** of the topics handled by an event handler """

PROP_EVENT_FILTER = "event.filter"
""" Filter on events properties for an event handler """

EVENT_PROP_FRAMEWORK_UID = "event.sender.framework.uid"
""" UID of the framework that emitted the event """

EVENT_PROP_TIMESTAMP = "event.timestamp"
""" Time stamp of the event, compute during the call of send() or post() """

EVENT_PROP_PROPAGATE = "event.propagate"
"""
If present in event properties, the event can be propagated through MQTT
"""

# ------------------------------------------------------------------------------

SERVICE_CONFIGURATION_ADMIN = "pelix.configadmin"
""" Specification of the ConfigurationAdmin service """

SERVICE_CONFIGADMIN_MANAGED = "pelix.configadmin.managed"
""" Specification of a service managed by ConfigurationAdmin """

SERVICE_CONFIGADMIN_MANAGED_FACTORY = "pelix.configadmin.managed.factory"
""" Specification of a factory managed by ConfigurationAdmin """

SERVICE_CONFIGADMIN_PERSISTENCE = "pelix.configadmin.persistence"
""" Specification of a ConfigurationAdmin storage service """

FACTORY_CONFIGADMIN_JSON = "pelix-configadmin-persistence-json-factory"
""" Name of the JSON ConfigurationAdmin storage component factory """

CONFIG_PROP_PID = "service.pid"
""" Configuration property: the configuration PID """

CONFIG_PROP_FACTORY_PID = "service.factoryPid"
""" Configuration property: factory PID (not used yet) """

CONFIG_PROP_BUNDLE_LOCATION = "service.bundleLocation"
""" Configuration property: bound location (not used yet) """

# ------------------------------------------------------------------------------

SERVICE_FILEINSTALL = "pelix.services.fileinstall"
""" Specification of the File Install service """

SERVICE_FILEINSTALL_LISTENERS = "pelix.services.fileinstall.listener"
""" Specification of a listener of the File Install service """

PROP_FILEINSTALL_FOLDER = "fileinstall.folder"
""" Path to the folder to look after, in white board pattern """

# ------------------------------------------------------------------------------

SERVICE_MQTT_CONNECTOR_FACTORY = "pelix.mqtt.factory"
""" Specification of an MQTT connection factory """

MQTT_CONNECTOR_FACTORY_PID = "mqtt.connector"
""" PID of the MQTT connection factory """

SERVICE_MQTT_CONNECTION = "pelix.mqtt.connection"
""" Specification of an MQTT connection service """

SERVICE_MQTT_LISTENER = "pelix.mqtt.listener"
""" Specification of an MQTT message listener """

PROP_MQTT_TOPICS = "pelix.mqtt.topics"
""" List of the topics a listener wants to subscribes to """
