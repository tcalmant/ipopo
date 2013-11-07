#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
ConfigurationAdmin implementation

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

TODO:
- listen to services to configure those registered after having updated their
  configuration
- load existing configurations at start up
- look for configuration files updates
- create ConfigurationListeners (shell cache update...)
"""

# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

#-------------------------------------------------------------------------------

# Pelix
from pelix.ipopo.decorators import ComponentFactory, Provides, Property, \
    Validate, Invalidate, Requires, Instantiate, BindField, UnbindField
import pelix.constants
import pelix.ldapfilter as ldapfilter
import pelix.services as services

# Standard library
import json
import logging
import os
import threading
import uuid

#-------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

#-------------------------------------------------------------------------------

class Configuration(object):
    """
    Configuration object
    """
    def __init__(self, pid, properties, config_admin, persistence,
                 factory_pid=None):
        """
        Sets up members

        :param pid: The configuration PID
        """
        # Configuration PID
        self.__pid = pid

        # Factory PID
        self.__factory_pid = factory_pid

        # Properties
        self.__properties = properties

        # Associated services
        self.__config_admin = config_admin
        self.__persistence = persistence

        # Configuration state
        self.__location = None
        self.__updated = False
        self.__deleted = False


    def get_bundle_location(self):
        """
        Get the bundle location.
        Returns the bundle location to which this configuration is bound,
        or None if it is not yet bound to a bundle location.

        :return: The location associated to the configuration
        """
        return self.__location


    def set_bundle_location(self, location):
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
        self.__location = location


    def get_factory_pid(self):
        """
        For a factory configuration returns the PID of the corresponding
        Managed Service Factory, else returns None.

        :return: The factory PID or None
        """
        return self.__factory_pid


    def get_pid(self):
        """
        Returns the PID of this configuration

        :return: The configuration PID
        """
        return self.__pid


    def get_properties(self):
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
        if self.__deleted:
            raise ValueError("{0} has been deleted".format(self.__pid))

        elif not self.__updated:
            # Fresh configuration
            return None

        # Filter a copy of the properties
        props = self.__properties.copy()

        try:
            del props[services.CONFIG_PROP_BUNDLE_LOCATION]
        except KeyError:
            # Ignore
            pass

        return props


    def update(self, properties=None):
        """
        If called without properties, only notifies listeners

        Update the properties of this Configuration object.
        Stores the properties in persistent storage after adding or overwriting
        the following properties:

        * "service.pid" : is set to be the PID of this configuration.
        * "service.factoryPid" : if this is a factory configuration it is set
          to the factory PID else it is not set.

        These system properties are all of type String.

        If the corresponding Managed Service/Managed Service Factory is
        registered, its updated method must be called asynchronously.
        Else, this callback is delayed until aforementioned registration occurs.

        Also initiates an asynchronous call to all ConfigurationListeners with
        a ConfigurationEvent.CM_UPDATED event.

        :param properties: the new set of properties for this configuration
        :raise IOError: Error storing the configuration
        """
        if properties:
            # Make a copy of the properties
            properties = properties.copy()

            # Override properties
            properties[services.CONFIG_PROP_PID] = self.__pid
            properties[services.CONFIG_PROP_BUNDLE_LOCATION] = self.__location
            if self.__factory_pid:
                properties[services.CONFIG_PROP_FACTORY_PID] = self.__factory_pid

            # Try to store the data
            self.__persistence.store(self.__pid, properties)

            # Store the copy
            self.__properties = properties
            self.__updated = True

        # Update configurations
        self.__config_admin._update(self)


    def delete(self):
        """
        Delete this configuration
        """
        # Update status
        self.__deleted = True

        # Notify the configuration admin
        self.__config_admin._delete(self)

        # Remove the file
        self.__persistence.delete(self.__pid)

        # Clean up
        self.__properties.clear()
        self.__persistence = None
        self.__pid = None


    def matches(self, ldap_filter):
        """
        Tests if this configuration matches the given filter.

        :param ldap_filter: A parsed LDAP filter object
        :return: True if the properties of this configuration matches the filter
        """
        return ldap_filter.matches(self.__properties)

#-------------------------------------------------------------------------------

@ComponentFactory()
@Provides(services.SERVICE_CONFIGURATION_ADMIN)
@Requires('_persistences', services.SERVICE_CONFIGADMIN_PERSISTENCE,
          aggregate=True)
@Requires('_managed', services.SERVICE_CONFIGADMIN_MANAGED,
          aggregate=True, optional=True)
@Instantiate('pelix-services-configuration-admin')
class ConfigurationAdmin(object):
    """
    Configuration basic implementation
    """
    def __init__(self):
        """
        Sets up members
        """
        # Persistence services
        self._persistences = []

        # Managed services
        self._managed = []

        # Service reference -> Managed Service
        self._managed_refs = {}
        self.__lock = threading.RLock()

        # Loaded configurations: PID -> Configuration
        self._configs = {}


    @BindField('_managed')
    def _bind_managed(self, _, svc, svc_ref):
        """
        A managed service has been bound
        """
        with self.__lock:
            self._managed_refs[svc_ref] = svc


    @UnbindField('_managed')
    def _unbind_managed(self, _, svc, svc_ref):
        """
        A managed service has gone
        """
        with self.__lock:
            try:
                del self._managed_refs[svc_ref]

            except KeyError:
                pass


    def create_factory_configuration(self, factory_pid):
        """
        Create a new factory Configuration object with a new PID.
        The properties of the new Configuration object are null until the
        first time that its update() method is called.

        :param pid: PID of the factory
        :raise ValueError: Invalid PID
        """
        if not factory_pid:
            raise ValueError("Empty PID")

        # Generate a PID
        pid = "{0}-{1}".format(factory_pid, str(uuid.uuid4()))

        # Create a new factory configuration
        config = self._configs[pid] = Configuration(pid, {}, self,
                                                    self._persistences[0],
                                                    factory_pid)
        return config


    def get_configuration(self, pid):
        """
        Get an existing Configuration object from the persistent store, or
        create a new Configuration object.

        :param pid: PID of the factory
        :raise IOError: File not found/readable
        """
        for persistence in self._persistences[:]:
            if persistence.exists(pid):
                # Load first existing one
                config = persistence.load(pid)
                break

        else:
            # New configuration, with the best ranked persistence
            config = {}
            persistence = self._persistences[0]

        # Return a configuration object, linked to the best persistence
        config = self._configs[pid] = Configuration(pid, config,
                                                    self, persistence)
        return config


    def list_configurations(self, ldap_filter=None):
        """
        List the current Configuration objects which match the filter.

        Only Configuration objects with non-null properties are considered
        current.
        That is, Configuration.get_properties() is guaranteed not to return null
        for each of the returned Configuration objects.

        The syntax of the filter string is as defined in the Filter class.
        The filter can test any configuration properties including the
        following:

        * service.pid (str): the PID under which this is registered
        * service.factoryPid (str): the factory if applicable
        * service.bundleLocation(str): the bundle location

        The filter can also be null, meaning that all Configuration objects
        should be returned.
        """
        if not ldap_filter:
            return list(self._configs.values())

        else:
            # Using an LDAP filter
            ldap_filter = ldapfilter.get_ldap_filter(ldap_filter)
            return [config for config in self._configs.values()
                    if config.matches(ldap_filter)]


    def __get_matching_services(self, pid):
        """
        Returns the list of services that matches the given PID

        :return: The list of services matching the PID
        """
        with self.__lock:
            # Make the list of managed services
            return [svc for svc_ref, svc in self._managed_refs.items()
                    if svc_ref.get_property(pelix.constants.SERVICE_PID) == pid]


    def __notify_services(self, services, properties):
        """
        Calls the updated() method of managed services.
        Logs errors if necessary.

        :param services: Services to be notified
        :param properties: New services properties
        """
        for svc in services:
            try:
                # Only give the properties to the service
                svc.updated(properties)

            except Exception as ex:
                _logger.exception("Error updating service: %s", ex)


    def _update(self, configuration):
        """
        A configuration has been updated
        """
        managed = self.__get_matching_services(configuration.get_pid())
        if managed:
            # Call them in a new thread
            properties = configuration.get_properties()
            thread = threading.Thread(target=self.__notify_services,
                                      args=(managed, properties),
                                      name="ConfigAdmin Update")
            thread.daemon = True
            thread.start()


    def _delete(self, configuration):
        """
        A configuration is about to be deleted
        """
        pid = configuration.get_pid()

        # Clean up before notifying
        del self._configs[pid]

        managed = self.__get_matching_services(pid)
        if managed:
            # Call them in a new thread
            thread = threading.Thread(target=self.__notify_services,
                                      args=(managed, None),
                                      name="ConfigAdmin Delete")
            thread.daemon = True
            thread.start()


#-------------------------------------------------------------------------------

@ComponentFactory(services.FACTORY_CONFIGADMIN_JSON)
@Provides(services.SERVICE_CONFIGADMIN_PERSISTENCE)
@Property('_conf_folder', 'configuration.folder')
@Instantiate('configadmin-json-default',  # Low ranking default storage
             {pelix.constants.SERVICE_RANKING:-1000})
class JsonPersistence(object):
    """
    JSON configuration persistence
    """
    def __init__(self):
        """
        Sets up members
        """
        # Configuration folder
        self._conf_folder = None

        # Loaded configurations: PID -> dictionary
        self._configs = {}


    def _get_file(self, pid):
        """
        Returns the path to the configuration file for the given PID

        :param pid: A configuration PID
        :return: The name of the configuration file
        """
        return os.path.join(self._conf_folder, "{0}.config.js".format(pid))


    def _get_pid(self, filename):
        """
        Extract the PID from the given file name

        :param filename: A file name
        :return: The corresponding PID or None
        """
        # Get the base name
        name = os.path.basename(filename)

        # Remove the extension
        try:
            ext_start = name.index('.config.js')
            return name[:ext_start] or None

        except IndexError:
            return None


    @Validate
    def validate(self, context):
        """
        Component validated
        """
        if not self._conf_folder:
            # ./conf is the default configuration folder
            self._conf_folder = os.path.join(os.getcwd(), "conf")

        # Make the folders if necessary
        if not os.path.exists(self._conf_folder):
            os.makedirs(self._conf_folder)


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        """
        # Clear the cache
        self._configs.clear()
        self._conf_folder = None


    def load(self, pid):
        """
        Loads the configuration file for the given PID

        :param pid: A configuration PID
        :return: The content of the PID
        :raise IOError: File not found/readable
        :raise ValueError: Invalid file content
        """
        try:
            # Read from cache
            return self._configs[pid]

        except KeyError:
            # Need to load the file
            pass

        with open(self._get_file(pid), 'r') as fp:
            data = fp.read()

        # Store the configuration
        content = self._configs[pid] = json.loads(data)
        return content


    def exists(self, pid):
        """
        Returns True if a configuration with the given PID exists

        :param pid: PID of a configuration
        :return: True if a readable configuration exists
        """
        return pid in self._configs or os.path.isfile(self._get_file(pid))


    def store(self, pid, properties):
        """
        Stores the configuration with the given PID. Overwrites existing
        configuration.

        :param pid: A configuration PID
        :param properties: Configuration values
        :raise IOError: File not writable
        """
        # Write to the file
        with open(self._get_file(pid), 'w') as fp:
            fp.write(json.dumps(properties, sort_keys=True,
                                indent=4, separators=(',', ': ')))

        # Update the cache
        self._configs[pid] = properties


    def delete(self, pid):
        """
        Removes the configuration for the given PID. Does nothing if the
        configuration does not exist.

        :param pid: A configuration PID
        :return: True if the file has been successfully removed, else False
        """
        try:
            os.remove(self._get_file(pid))
            return True

        except OSError:
            return False


    def get_pids(self):
        """
        Returns the list of PIDs this storage could read
        """
        return [filename
                for filename in os.listdir(self._conf_folder)
                if os.path.isfile(os.path.join(self._conf_folder, filename))
                and self._get_pid(filename)]

