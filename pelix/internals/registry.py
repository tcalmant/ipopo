#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Service registry and event dispatcher for Pelix.

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.5.4
:status: Alpha

..

    This file is part of iPOPO.

    iPOPO is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    iPOPO is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with iPOPO. If not, see <http://www.gnu.org/licenses/>.
"""

# Module version
__version_info__ = (0, 5, 4)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix beans
from pelix.internals.exceptions  import BundleException
from pelix.internals.constants import OBJECTCLASS, SERVICE_ID, SERVICE_RANKING
from pelix.internals.events import ServiceEvent

# Pelix utility modules
from pelix.utilities import is_string
import pelix.ldapfilter as ldapfilter

# Standard library
import logging
import threading

# ------------------------------------------------------------------------------

class ServiceReference(object):
    """
    Represents a reference to a service
    """
    def __init__(self, bundle, properties):
        """
        Sets up the service reference

        :param bundle: The bundle registering the service
        :param properties: The service properties
        :raise BundleException: The properties doesn't contain mandatory entries
        """
        # Check properties
        for mandatory in (SERVICE_ID, OBJECTCLASS):
            if mandatory not in properties:
                raise BundleException(
                            "A Service must at least have a '{0}' entry"\
                            .format(mandatory))

        # Properties lock (used by ServiceRegistration too)
        self._props_lock = threading.RLock()

        # Usage lock
        self.__usage_lock = threading.Lock()

        self.__bundle = bundle
        self.__properties = properties
        self.__using_bundles = []
        self.__service_id = properties[SERVICE_ID]


    def __str__(self):
        """
        String representation
        """
        return "ServiceReference(ID={0}, Bundle={1}, Specs={2})".format(
                                                self.__service_id,
                                                self.__bundle.get_bundle_id(),
                                                self.__properties[OBJECTCLASS])


    def __hash__(self):
        """
        Returns the service hash, i.e. its ID, unique in a framework instance.
        
        :return: The service ID
        """
        return self.__service_id


    def __eq__(self, other):
        """
        Two references are equal if they have the same service ID
        """
        return self.__service_id == other.__service_id


    def __lt__(self, other):
        """
        Lesser than other

        See: http://www.osgi.org/javadoc/r4v43/org/osgi/framework/ServiceReference.html#compareTo%28java.lang.Object%29
        """
        service_rank = int(self.__properties.get(SERVICE_RANKING, 65535))
        other_rank = int(other.__properties.get(SERVICE_RANKING, 65535))

        if service_rank == other_rank:
            # Same rank, ID discriminates (greater ID, lesser reference)
            return self.__service_id > other.__service_id

        else:
            # Rank order
            return service_rank < other_rank


    def __gt__(self, other):
        return not (self == other or self < other)

    def __le__(self, other):
        return self == other or self < other

    def __ge__(self, other):
        return not self < other

    def __ne__(self, other):
        return not self == other


    def get_bundle(self):
        """
        Returns the bundle that registered this service
        
        :return: the bundle that registered this service
        """
        return self.__bundle


    def get_using_bundles(self):
        """
        Returns the list of bundles that use this service
        
        :return: A list of Bundle objects
        """
        return self.__using_bundles


    def get_properties(self):
        """
        Returns a copy of the service properties
        
        :return: A copy of the service properties
        """
        with self._props_lock:
            return self.__properties.copy()


    def get_property(self, name):
        """
        Retrieves the property value for the given name

        :return: The property value, None if not found
        """
        with self._props_lock:
            return self.__properties.get(name, None)


    def get_property_keys(self):
        """
        Returns an array of the keys in the properties of the service

        :return: An array of property keys.
        """
        with self._props_lock:
            return tuple(self.__properties.keys())


    def unused_by(self, bundle):
        """
        Indicates that this reference is not being used anymore by the given
        bundle.
        This method should only be used by the framework.

        :param bundle: A bundle that used this reference
        """
        if bundle is None or bundle is self.__bundle:
            # Ignore
            return

        with self.__usage_lock:
            if bundle in self.__using_bundles:
                self.__using_bundles.remove(bundle)


    def used_by(self, bundle):
        """
        Indicates that this reference is being used by the given bundle.
        This method should only be used by the framework.

        :param bundle: A bundle using this reference
        """
        if bundle is None or bundle is self.__bundle:
            # Ignore
            return

        with self.__usage_lock:
            if bundle not in self.__using_bundles:
                self.__using_bundles.append(bundle)

# ------------------------------------------------------------------------------

class ServiceRegistration(object):
    """
    Represents a service registration object
    """
    def __init__(self, framework, reference, properties):
        """
        Sets up the service registration object

        :param framework: The host framework
        :param reference: A service reference
        :param properties: A reference to the ServiceReference properties
                           dictionary object
        """
        self.__framework = framework
        self.__reference = reference
        self.__properties = properties


    def __str__(self):
        """
        String representation
        """
        return "ServiceRegistration({0})".format(self.__reference)


    def get_reference(self):
        """
        Returns the reference associated to this registration
        
        :return: A ServiceReference object
        """
        return self.__reference


    def set_properties(self, properties):
        """
        Updates the service properties

        :param properties: The new properties
        :raise TypeError: The argument is not a dictionary
        """
        if not isinstance(properties, dict):
            raise TypeError("Waiting for dictionary")

        # Keys that must not be updated
        forbidden_keys = (OBJECTCLASS, SERVICE_ID)

        for forbidden_key in forbidden_keys:
            if forbidden_key in properties:
                del properties[forbidden_key]

        to_delete = []
        for key, value in properties.items():
            if self.__properties.get(key, None) == value:
                # No update
                to_delete.append(key)

        for key in to_delete:
            # Remove unchanged properties
            del properties[key]

        if not properties:
            # Nothing to do
            return

        with self.__reference._props_lock:
            # Update the properties
            previous = self.__properties.copy()
            self.__properties.update(properties)

            # Trigger a new computation in the framework
            event = ServiceEvent(ServiceEvent.MODIFIED, self.__reference,
                                 previous)

            self.__framework._dispatcher.fire_service_event(event)


    def unregister(self):
        """
        Unregisters the service
        """
        self.__framework.unregister_service(self)


# ------------------------------------------------------------------------------

class EventDispatcher(object):
    """
    Simple event dispatcher
    """
    def __init__(self, logger=None):
        """
        Sets up the dispatcher
        
        :param logger: The logger to be used
        """
        # Logger
        self._logger = logger or logging.getLogger("EventDispatcher")

        # Bundle listeners
        self.__bnd_listeners = []
        self.__bnd_lock = threading.Lock()

        # Service listeners (listener -> (spec, filter))
        self.__svc_listeners = {}
        self.__svc_lock = threading.Lock()

        # Framework stop listeners
        self.__fw_listeners = []
        self.__fw_lock = threading.Lock()


    def clear(self):
        """
        Clears the event dispatcher
        """
        with self.__bnd_lock:
            del self.__bnd_listeners[:]

        with self.__svc_lock:
            self.__svc_listeners.clear()

        with self.__fw_lock:
            del self.__fw_listeners[:]


    def add_bundle_listener(self, listener):
        """
        Adds a bundle listener
        
        :param listener: The bundle listener to register
        :return: True if the listener has been registered, False if it was
                 already known
        :raise BundleException: An invalid listener has been given
        """
        if listener is None or not hasattr(listener, 'bundle_changed'):
            raise BundleException("Invalid bundle listener given")

        with self.__bnd_lock:
            if listener in self.__bnd_listeners:
                self._logger.warning("Already known bundle listener '%s'",
                                listener)
                return False

            self.__bnd_listeners.append(listener)
            return True


    def add_framework_listener(self, listener):
        """
        Registers a listener that will be called back right before the framework
        stops.
        
        :param listener: The framework stop listener
        :return: True if the listener has been registered, False if it was
                 already known
        :raise BundleException: An invalid listener has been given
        """
        if listener is None or not hasattr(listener, 'framework_stopping'):
            raise BundleException("Invalid framework listener given")

        with self.__fw_lock:
            if listener in self.__fw_listeners:
                self._logger.warning("Already known framework listener '%s'",
                                listener)
                return False

            self.__fw_listeners.append(listener)
            return True


    def add_service_listener(self, listener, specification=None,
                             ldap_filter=None):
        """
        Registers a service listener
        
        TODO: A listener could be registered multiple times, for different
        specifications and/or filters

        :param listener: The service listener
        :param specification: The specification that must provide the service
                              (optional, None to accept all services)
        :param ldap_filter: Filter that must match the service properties
                            (optional, None to accept all services)
        :return: True if the listener has been registered, False if it was
                 already known
        :raise BundleException: An invalid listener has been given
        """
        if listener is None or not hasattr(listener, 'service_changed'):
            raise BundleException("Invalid service listener given")

        with self.__svc_lock:
            if listener in self.__svc_listeners:
                self._logger.warning("Already known service listener '%s'",
                                listener)
                return False

            try:
                ldap_filter = ldapfilter.get_ldap_filter(ldap_filter)
            except ValueError as ex:
                raise BundleException("Invalid service filter: {0}" \
                                                 .format(ex))

            self.__svc_listeners[listener] = (specification, ldap_filter)
            return True


    def remove_bundle_listener(self, listener):
        """
        Unregisters a bundle listener
        
        :param listener: The bundle listener to unregister
        :return: True if the listener has been unregistered, else False
        """
        with self.__bnd_lock:
            if listener not in self.__bnd_listeners:
                return False

            self.__bnd_listeners.remove(listener)
            return True


    def remove_framework_listener(self, listener):
        """
        Unregisters a framework stop listener
        
        :param listener: The framework listener to unregister
        :return: True if the listener has been unregistered, else False
        """
        with self.__fw_lock:
            if listener not in self.__fw_listeners:
                return False

            self.__fw_listeners.remove(listener)
            return True


    def remove_service_listener(self, listener):
        """
        Unregisters a service listener

        :param listener: The service listener
        :return: True if the listener has been unregistered
        """
        with self.__svc_lock:
            if listener not in self.__svc_listeners:
                return False

            del self.__svc_listeners[listener]
            return True


    def fire_bundle_event(self, event):
        """
        Notifies bundle events listeners of a new event in the calling thread.
        
        :param event: The bundle event
        """
        with self.__bnd_lock:
            # Copy the list of listeners
            listeners = self.__bnd_listeners[:]

        # Call'em all
        for listener in listeners:
            try:
                listener.bundle_changed(event)
            except:
                self._logger.exception("Error calling a bundle listener")


    def fire_framework_stopping(self):
        """
        Calls all framework listeners, telling them that the framework is
        stopping
        """
        with self.__fw_lock:
            # Copy the list of listeners
            listeners = self.__fw_listeners[:]

        for listener in listeners:
            try:
                listener.framework_stopping()

            except:
                self._logger.exception("An error occurred calling one of the " \
                                  "framework stop listeners")


    def fire_service_event(self, event):
        """
        Notifies service events listeners of a new event in the calling thread.
        
        :param event: The service event
        """
        with self.__svc_lock:
            # Copy the list of listeners
            listeners = self.__svc_listeners.copy()

        # Get the service properties
        properties = event.get_service_reference().get_properties()
        svc_specs = properties[OBJECTCLASS]
        previous = None
        endmatch_event = None
        svc_modified = (event.get_kind() == ServiceEvent.MODIFIED)

        if svc_modified:
            # Modified service event : prepare the end match event
            previous = event.get_previous_properties()
            endmatch_event = ServiceEvent(ServiceEvent.MODIFIED_ENDMATCH,
                                          event.get_service_reference(),
                                          previous)

        # Call'em all
        for listener, (specification, ldap_filter) in listeners.items():
            # Test the specification
            if specification is not None and specification not in svc_specs:
                continue

            # Default event to send : the one we received
            sent_event = event

            # Test if the service properties matches the filter
            if ldap_filter is not None \
            and not ldap_filter.matches(properties):
                # Event doesn't match listener filter...
                if svc_modified and previous is not None \
                and ldap_filter.matches(previous):
                    # ... but previous properties did match
                    sent_event = endmatch_event

                else:
                    # Didn't match before either, ignore it
                    continue

            # Call'em
            try:
                listener.service_changed(sent_event)

            except:
                self._logger.exception("Error calling a service listener")

# ------------------------------------------------------------------------------

class ServiceRegistry(object):
    """
    Service registry for Pelix.
    
    Associates service references to instances and bundles.
    """
    def __init__(self, framework, logger=None):
        """
        Sets up the registry
        
        :param framework: Associated framework
        :param logger: Logger to use
        """
        # Associated framework
        self.__framework = framework

        # Logger
        self._logger = logger or logging.getLogger("ServiceRegistry")

        # Next service ID
        self.__next_service_id = 1

        # Service reference -> Service instance
        self.__svc_registry = {}

        # Specification -> Service references[]
        self.__svc_specs = {}

        # Service reference -> Bundle
        self.__svc_bundle = {}

        # Bundle -> Service references[]
        self.__bundle_svc = {}

        # Bundle -> Service references[]
        self.__bundle_imports = {}

        # Locks
        self.__svc_lock = threading.Lock()


    def clear(self):
        """
        Clears the registry
        """
        with self.__svc_lock:
            self.__svc_registry.clear()
            self.__svc_specs.clear()
            self.__svc_bundle.clear()
            self.__bundle_svc.clear()
            self.__bundle_imports.clear()


    def register(self, bundle, classes, properties, svc_instance):
        """
        Registers a service.
        
        :param bundle: The bundle that registers the service
        :param classes: The classes implemented by the service
        :param properties: The properties associated to the service
        :param svc_instance: The instance of the service
        :return: The ServiceRegistration object
        """
        with self.__svc_lock:
            # Prepare properties
            service_id = self.__next_service_id
            self.__next_service_id += 1
            properties[OBJECTCLASS] = classes
            properties[SERVICE_ID] = service_id

            # Make the service reference
            svc_ref = ServiceReference(bundle, properties)

            # Make the service registration
            svc_registration = ServiceRegistration(self.__framework, svc_ref,
                                                   properties)

            # Store service information
            self.__svc_registry[svc_ref] = svc_instance
            self.__svc_bundle[svc_ref] = bundle

            for spec in classes:
                spec_refs = self.__svc_specs.setdefault(spec, [])
                spec_refs.append(svc_ref)
                # Keep the list sorted
                spec_refs.sort()

            # Reverse map, to ease bundle/service association
            self.__bundle_svc.setdefault(bundle, []).append(svc_ref)

            return svc_registration


    def unregister(self, svc_ref):
        """
        Unregisters a service
        
        :param svc_ref: A service reference
        :return: The unregistered service instance
        :raise BundleException: Unknown service reference
        """
        with self.__svc_lock:
            if svc_ref not in self.__svc_registry:
                raise BundleException("Unknown service: {0}" \
                                                 .format(svc_ref))

            # Get the owner
            bundle = self.__svc_bundle.pop(svc_ref)

            # Get the service instance
            service = self.__svc_registry.pop(svc_ref)

            for spec in svc_ref.get_property(OBJECTCLASS):
                spec_services = self.__svc_specs[spec]
                spec_services.remove(svc_ref)
                if len(spec_services) == 0:
                    del self.__svc_specs[spec]

            # Delete bundle association
            bundle_services = self.__bundle_svc[bundle]
            bundle_services.remove(svc_ref)
            if len(bundle_services) == 0:
                # Don't keep empty lists
                del self.__bundle_svc[bundle]

            return service


    def find_service_references(self, clazz=None, ldap_filter=None,
                                only_one=False):
        """
        Finds all services references matching the given filter.

        :param clazz: Class implemented by the service
        :param ldap_filter: Service filter
        :param only_one: Return the first matching service reference only
        :return: A list of found references, or None
        :raise BundleException: An error occurred looking for service references
        """
        with self.__svc_lock:
            if clazz is None and ldap_filter is None:
                # Return a sorted copy of the keys list
                result = list(self.__svc_registry.keys())
                result.sort()
                # Do not return None if the whole content was required
                return result

            if hasattr(clazz, '__name__'):
                # Escape the type name
                clazz = ldapfilter.escape_LDAP(clazz.__name__)

            elif is_string(clazz):
                # Escape the class name
                clazz = ldapfilter.escape_LDAP(clazz)

            if clazz is None:
                # Directly use the given filter
                refs_set = self.__svc_registry.keys()

            else:
                try:
                    # Only for references with the given specification
                    refs_set = iter(self.__svc_specs[clazz])

                except KeyError:
                    # No matching specification
                    return None

            # Parse the filter
            try:
                new_filter = ldapfilter.get_ldap_filter(ldap_filter)

            except ValueError as ex:
                raise BundleException(ex)

            if new_filter is not None:
                # Prepare a generator, as we might not need a complete
                # walk-through
                refs_set = (ref for ref in refs_set
                            if new_filter.matches(ref.get_properties()))

            if only_one:
                # Return the first element in the list/generator
                try:
                    return next(refs_set)

                except StopIteration:
                    # No match
                    return None

            # Get all the matching references
            return list(refs_set) or None


    def get_bundle_imported_services(self, bundle):
        """
        Returns this bundle's ServiceReference list for all services it is using
        or returns None if this bundle is not using any services.
        A bundle is considered to be using a service if its use count for that
        service is greater than zero.
        
        The list is valid at the time of the call to this method, however, as
        the Framework is a very dynamic environment, services can be modified
        or unregistered at any time.
        
        :param bundle: The bundle to look into
        :return: An array of ServiceReference objects or None.
        :raise BundleException: If the bundle has been uninstalled
        """
        with self.__svc_lock:
            return self.__bundle_imports.get(bundle, None)


    def get_bundle_registered_services(self, bundle):
        """
        Retrieves the services registered by the given bundle. Returns None
        if the bundle didn't register any service.
        
        :param bundle: The bundle to look into
        :return: The services registered by the bundle, or None
        """
        with self.__svc_lock:
            return self.__bundle_svc.get(bundle, None)


    def get_service(self, bundle, reference):
        """
        Retrieves the service corresponding to the given reference

        :param bundle: The bundle requiring the service
        :param reference: A service reference
        :return: The requested service
        :raise BundleException: The service could not be found
        """
        with self.__svc_lock:
            # Be sure to have the instance
            try:
                service = self.__svc_registry[reference]

                # Indicate the dependency
                self.__bundle_imports.setdefault(bundle, []).append(reference)
                reference.used_by(bundle)

                return service

            except KeyError:
                # Not found
                raise BundleException("Service not found (reference: {0})" \
                                      .format(reference))


    def unget_service(self, bundle, reference):
        """
        Removes the usage of a service by a bundle

        :param bundle: The bundle that used the service
        :param reference: A service reference
        :return: True if the bundle usage has been removed
        """
        with self.__svc_lock:
            if bundle not in self.__bundle_imports:
                # Unknown bundle
                return False

            imports = self.__bundle_imports[bundle]
            if reference not in imports:
                # Unused reference
                return False

            # Clean up
            imports.remove(reference)
            reference.unused_by(bundle)
            return True
