#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix OSGi-like services packages

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.1
:status: Beta

..

    Copyright 2013 isandlaTech

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
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

#-------------------------------------------------------------------------------

FACTORY_EVENT_ADMIN = "pelix-services-eventadmin-factory"
""" Name of the EventAdmin component factory """

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

#-------------------------------------------------------------------------------

SERVICE_CONFIGURATION_ADMIN = "pelix.services.configadmin"
""" Specification of the ConfigurationAdmin service """

SERVICE_CONFIGADMIN_MANAGED = "pelix.services.configadmin.managed"
""" Specification of a service managed by ConfigurationAdmin """

SERVICE_CONFIGADMIN_PERSISTENCE = "pelix.services.configadmin.persistence"
""" Specification of a ConfigurationAdmin storage service """

FACTORY_CONFIGADMIN_JSON = "pelix-configadmin-persistence-json-factory"
""" Name of the JSON ConfigurationAdmin storage component factory """

CONFIG_PROP_PID = 'service.pid'
""" Configuration property: the configuration PID """

CONFIG_PROP_FACTORY_PID = 'service.factoryPid'
""" Configuration property: factory PID (not used yet) """

CONFIG_PROP_BUNDLE_LOCATION = 'service.bundleLocation'
""" Configuration property: bound location (not used yet) """

#-------------------------------------------------------------------------------

SERVICE_FILEINSTALL = 'pelix.services.fileinstall'
""" Specification of the File Install service """

SERVICE_FILEINSTALL_LISTENERS = 'pelix.services.fileinstall.listener'
""" Specification of a listener of the File Install service """

PROP_FILEINSTALL_FOLDER = 'fileinstall.folder'
""" Path to the folder to look after, in white board pattern """
