#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix OSGi-like services packages

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

from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Protocol, Union

from pelix.constants import Specification

if TYPE_CHECKING:
    import pelix.ldapfilter as ldapfilter

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"


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


@Specification(SERVICE_EVENT_ADMIN)
class EventAdmin(Protocol):
    """
    Definition of the event admin service
    """

    def send(self, topic: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """
        Sends synchronously the given event

        :param topic: Topic of event
        :param properties: Associated properties
        """
        ...

    def post(self, topic: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """
        Sends asynchronously the given event

        :param topic: Topic of event
        :param properties: Associated properties
        """
        ...


@Specification(SERVICE_EVENT_HANDLER)
class ServiceEventHandler(Protocol):
    """
    Definition of a Service Event handler
    """

    def handle_event(self, topic: str, properties: Dict[str, Any]) -> None:
        """
        An EventAdmin event has been received
        """
        ...


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

FRAMEWORK_PROP_CONFIGADMIN_DISABLE_DEFAULT_PERSISTENCE = "pelix.configadmin.persistence.default.disable"
"""
If this framework property has a value, the default persistence service of
ConfigurationAdmin won't be started
"""

FACTORY_CONFIGADMIN_JSON = "pelix-configadmin-persistence-json-factory"
""" Name of the JSON ConfigurationAdmin storage component factory """

CONFIG_PROP_PID = "service.pid"
""" Configuration property: the configuration PID """

CONFIG_PROP_FACTORY_PID = "service.factoryPid"
""" Configuration property: factory PID (not used yet) """

CONFIG_PROP_BUNDLE_LOCATION = "service.bundleLocation"
""" Configuration property: bound location (not used yet) """


class Configuration(Protocol):
    """
    Representation of a configuration
    """

    def get_bundle_location(self) -> Optional[str]:
        """
        Get the bundle location.
        Returns the bundle location to which this configuration is bound,
        or None if it is not yet bound to a bundle location.

        :return: The location associated to the configuration
        """
        ...

    def set_bundle_location(self, location: Optional[str]) -> None:
        """
        Bind this Configuration object to the specified bundle location.
        If the location parameter is None then the Configuration object
        will not be bound to a location.
        It will be set to the bundle's location before the first time a
        Managed Service/Managed Service Factory receives this Configuration
        object via the updated method and before any plugins are called.
        The bundle location will be set persistently.

        :param location: A bundle location
        """
        ...

    def get_factory_pid(self) -> Optional[str]:
        """
        For a factory configuration returns the PID of the corresponding
        Managed Service Factory, else returns None.

        :return: The factory PID or None
        """
        ...

    def get_pid(self) -> str:
        """
        Returns the PID of this configuration

        :return: The configuration PID
        """
        ...

    def get_properties(self) -> Optional[Dict[str, Any]]:
        """
        Return the properties of this Configuration object.
        The Dictionary object returned is a private copy for the caller and may
        be changed without influencing the stored configuration.

        If called just after the configuration is created and before update has
        been called, this method returns None.

        :return: A private copy of the properties for the caller or null.
        These properties must not contain the "service.bundleLocation"
        property. The value of this property may be obtained from the
        get_bundle_location() method.
        """
        ...

    def is_valid(self) -> bool:
        """
        Checks if this configuration has been updated at least once and has not
        been deleted.

        :return: True if the configuration has properties and has not been deleted
        """
        ...

    def reload(self) -> None:
        """
        Reloads the configuration file using the persistence service

        :raise IOError: File not found/readable
        :raise ValueError: Invalid file content
        """
        ...

    def update(self, properties: Optional[Dict[str, Any]] = None) -> None:
        """
        If called without properties, only notifies listeners

        Update the properties of this Configuration object.
        Stores the properties in persistent storage after adding or overwriting
        the following properties:

        * "service.pid" : is set to be the PID of this configuration.
        * "service.factoryPid" : if this is a factory configuration it is set to
        the factory PID else it is not set.

        These system properties are all of type String.

        If the corresponding Managed Service/Managed Service Factory is
        registered, its updated method must be called asynchronously.
        Else, this callback is delayed until aforementioned registration
        occurs.

        Also initiates an asynchronous call to all ConfigurationListeners with
        a ConfigurationEvent.CM_UPDATED event.

        :param properties: the new set of properties for this configuration
        :raise IOError: Error storing the configuration
        """
        ...

    def delete(self) -> None:
        """
        Delete this configuration
        """
        ...

    def matches(self, ldap_filter: Optional["ldapfilter.LdapFilterOrCriteria"]) -> bool:
        """
        Tests if this configuration matches the given filter.

        :param ldap_filter: A parsed LDAP filter object
        :return: True if the properties of this configuration matches the filter
        """
        ...


@Specification(SERVICE_CONFIGURATION_ADMIN)
class IConfigurationAdmin(Protocol):
    """
    Specification of the configuration admin service
    """

    def create_factory_configuration(self, factory_pid: str) -> Configuration:
        """
        Create a new factory Configuration object with a new PID.
        The properties of the new Configuration object are null until the
        first time that its update() method is called.

        :param factory_pid: PID of the factory
        :raise ValueError: Invalid PID
        """
        ...

    def get_configuration(self, pid: str) -> Configuration:
        """
        Get an existing Configuration object from the persistent store, or
        create a new Configuration object.

        :param pid: PID of the factory
        :raise IOError: File not found/readable
        """
        ...

    def list_configurations(
        self, ldap_filter: Union[None, str, "ldapfilter.LdapFilterOrCriteria"] = None
    ) -> Iterable[Configuration]:
        """
        List the current Configuration objects which match the filter.

        Only Configuration objects with non-null properties are considered
        current.
        That is, Configuration.get_properties() is guaranteed not to return
        null for each of the returned Configuration objects.

        The syntax of the filter string is as defined in the Filter class.
        The filter can test any configuration properties including the
        following:

        * service.pid (str): the PID under which this is registered
        * service.factoryPid (str): the factory if applicable
        * service.bundleLocation(str): the bundle location

        The filter can also be null, meaning that all Configuration objects
        should be returned.
        """
        ...


@Specification(SERVICE_CONFIGADMIN_PERSISTENCE)
class IConfigurationAdminPersistence(Protocol):
    """
    Specification of a configuration admin persistence service
    """

    def get_pids(self) -> Iterable[str]:
        """
        Returns the list of PIDs this storage could read
        """
        ...

    def exists(self, pid: str) -> bool:
        """
        Checks if the given PID exists
        """
        ...

    def load(self, pid: str) -> Dict[str, Any]:
        """
        Loads the configuration with the given PID
        """
        ...

    def store(self, pid: str, properties: Dict[str, Any]) -> None:
        """
        Stores the given configuration
        """
        ...

    def delete(self, pid: str) -> bool:
        """
        Deletes the given configuration
        """
        ...


@Specification(SERVICE_CONFIGADMIN_MANAGED)
class IManagedService(Protocol):
    """
    Specification of a service managed by configuration admin
    """

    def updated(self, properties: Optional[Dict[str, Any]]) -> None:
        """
        Service configuration updated
        """
        ...


@Specification(SERVICE_CONFIGADMIN_MANAGED_FACTORY)
class IManagedServiceFactory(Protocol):
    """
    Specification of a managed service factory
    """

    def get_name(self) -> str:
        """
        Returns the name of the factory
        """
        ...

    def updated(self, pid: str, properties: Optional[Dict[str, Any]]) -> None:
        """
        Service configuration updated
        """
        ...

    def deleted(self, pid: str) -> None:
        """
        Service configuration deleted
        """
        ...


# ------------------------------------------------------------------------------

SERVICE_FILEINSTALL = "pelix.services.fileinstall"
""" Specification of the File Install service """

SERVICE_FILEINSTALL_LISTENERS = "pelix.services.fileinstall.listener"
""" Specification of a listener of the File Install service """

PROP_FILEINSTALL_FOLDER = "fileinstall.folder"
""" Path to the folder to look after, in white board pattern """


@Specification(SERVICE_FILEINSTALL_LISTENERS)
class FileInstallListener(Protocol):
    """
    Specification of the FileInstall listener service
    """

    def folder_change(
        self, folder: str, added: Iterable[str], updated: Iterable[str], deleted: Iterable[str]
    ) -> None:
        """
        Notification of changes in the watched folder

        :param folder: Folder where changes occurred
        :param added: Names of added files
        :param updated: Names of modified files
        :param deleted: Names of removed files
        """
        ...


@Specification(SERVICE_FILEINSTALL)
class FileInstall(Protocol):
    """
    Specification of the FileInstall service
    """

    def add_listener(self, folder: str, listener: FileInstallListener) -> bool:
        """
        Manual registration of a folder listener

        :param folder: Path to the folder to watch
        :param listener: Listener to register
        :return: True if the listener has been registered
        """
        ...

    def remove_listener(self, folder: str, listener: FileInstallListener) -> None:
        """
        Manual unregistration of a folder listener.

        :param folder: Path to the folder the listener watched
        :param listener: Listener to unregister
        :raise ValueError: The listener wasn't watching this folder
        """
        ...


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


@Specification(SERVICE_MQTT_CONNECTOR_FACTORY)
class MqttConnectorFactory(Protocol):
    """
    Specification of an MQTT connector factory
    """

    def publish(
        self, topic: str, payload: bytes, qos: int = 0, retain: bool = False, pid: Optional[str] = None
    ) -> None:
        """
        Publishes an MQTT message

        :param topic: Message topic
        :param payload: RAW message content
        :param qos: MQTT quality of service (0 by default)
        :param retain: Message must be retained
        :param pid: Optional connection PID
        :raise KeyError: Invalid PID
        """
        ...


@Specification(SERVICE_MQTT_LISTENER)
class MqttListener(Protocol):
    """
    Specification of an MQTT listener
    """

    def handle_mqtt_message(self, topic: str, payload: bytes, qos: int) -> None:
        """
        Notification of a new message

        :param topic: Message topic
        :param payload: Raw message payload
        :param qos: Message Quality of Service
        """
        ...
