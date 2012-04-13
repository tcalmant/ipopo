#!/usr/bin/env python
#-- Content-Encoding: UTF-8 --
"""
Core module for Pelix.

Pelix is a Python framework that aims to act as OSGi as much as possible

:author: Thomas Calmant
:copyright: Copyright 2012, isandlaTech
:license: GPLv3
:version: 0.3
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

from pelix.utilities import SynchronizedClassMethod, add_listener, \
    remove_listener, is_string

import pelix.ldapfilter as ldapfilter

# ------------------------------------------------------------------------------

import imp
import importlib
import inspect
import logging
import os
import sys
import threading

ACTIVATOR = "activator"

OBJECTCLASS = "objectClass"
SERVICE_ID = "service.id"
SERVICE_RANKING = "service.ranking"

# ------------------------------------------------------------------------------

# Documentation strings format
__docformat__ = "restructuredtext en"

# Module version
__version__ = (1, 0, 0)

# Prepare the module logger
_logger = logging.getLogger("pelix.main")

# ------------------------------------------------------------------------------

class BundleException(Exception):
    """
    The base of all framework exceptions
    """
    def __init__(self, content):
        """
        Sets up the exception
        """
        if isinstance(content, Exception):
            Exception.__init__(self, str(content))

        else:
            Exception.__init__(self, content)


# ------------------------------------------------------------------------------

class Bundle(object):
    """
    Represents a "bundle" in Pelix
    """

    UNINSTALLED = 1
    """ The bundle is uninstalled and may not be used """

    INSTALLED = 2
    """ The bundle is installed but not yet resolved """

    RESOLVED = 4
    """ The bundle is resolved and is able to be started """

    STARTING = 8
    """ The bundle is in the process of starting """

    STOPPING = 16
    """ The bundle is in the process of stopping """

    ACTIVE = 32
    """ The bundle is now running """


    def __init__(self, framework, bundle_id, location):
        """
        Sets up the bundle descriptor

        :param framework: The host framework
        :param bundle_id: The bundle ID in the host framework
        """
        # A reentrant lock for synchronization
        self._lock = threading.RLock()

        # Bundle
        self.__context = None
        self.__framework = framework
        self.__id = bundle_id
        self.__module = None
        self._state = Bundle.RESOLVED
        self.__name = location

        # Services
        self.__registered_services = []
        self.__imported_services = []


    def __str__(self):
        """
        String representation
        """
        return "Bundle(%d, %s)" % (self.__id, self.__name)


    def _fire_bundle_event(self, kind):
        """
        Fires a bundle event of the given kind

        :param kind: Kind of event
        """
        self.__framework.fire_bundle_event(BundleEvent(kind, self))


    def get_bundle_context(self):
        """
        Retrieves the bundle context
        
        :return: The bundle context
        """
        return self.__context


    def get_bundle_id(self):
        """
        Retrieves the bundle ID

        :return: The bundle ID
        """
        return self.__id


    def get_location(self):
        """
        Retrieves the location of this module

        :return: The location of the Pelix module, or an empty string
        """
        return getattr(self.__module, '__file__', "")


    def get_module(self):
        """
        Retrieves the Python module corresponding to the bundle
        
        :return: The Python module
        """
        return self.__module


    def get_state(self):
        """
        Retrieves the bundle state
        
        :return: The bundle state
        """
        return self._state


    def get_symbolic_name(self):
        """
        Retrieves the bundle symbolic name (its Python module name)
        
        :return: The bundle symbolic name
        """
        return self.__name


    def get_version(self):
        """
        Retrieves the bundle version

        :return: The bundle version, (0,0,0) by default
        """
        return getattr(self.__module, "__version__", (0, 0, 0))


    def set_context(self, context):
        """
        Sets the bundle context. Does nothing if a context has already been set.
        This method is first called in the Framework::install_bundle() method
        and then is ignored, so it doesn't need to be synchronized.

        :param context: The bundle context
        """
        if self.__context is None:
            self.__context = context


    def set_module(self, module):
        """
        Sets the bundle module. Does nothing if a module has already been set.

        :param module: A Python module object (the 'bundle')
        """
        if self.__module is None:
            self.__module = module
            self.__name = module.__name__


    def start(self):
        """
        Starts the bundle. Does nothing if the bundle is already starting or
        active.
        
        :raise BundleException: The framework is not yet started or the bundle
                                activator failed.
        """
        if self.__framework._state not in (Bundle.STARTING, Bundle.ACTIVE):
            # Framework is not runnning
            raise BundleException("Framework must be started before its "
                                  "bundles")

        with self._lock:
            if self._state in (Bundle.ACTIVE, Bundle.STARTING):
                # Already started bundle, do nothing
                return

            # Store the bundle current state
            previous_state = self._state

            # Starting...
            self._state = Bundle.STARTING
            self._fire_bundle_event(BundleEvent.STARTING)

            # Call the activator, if any
            activator = getattr(self.__module, ACTIVATOR, None)
            starter = getattr(activator, 'start', None)

            if starter is not None:
                try:
                    # Call the start method
                    starter(self.__context)

                except Exception as ex:
                    # Restore previous state
                    self._state = previous_state

                    # Raise the error
                    _logger.exception("Error calling the activator")
                    raise BundleException(ex)

            # Bundle is now active
            self._state = Bundle.ACTIVE
            self._fire_bundle_event(BundleEvent.STARTED)


    def stop(self):
        """
        Stops the bundle. Does nothing if the bundle is already stopped.
        
        :raise BundleException: The bundle activator failed.
        """
        if self._state != Bundle.ACTIVE:
            # Invalid state
            return

        with self._lock:
            # Stopping...
            self._state = Bundle.STOPPING
            self._fire_bundle_event(BundleEvent.STOPPING)

            # Call the activator, if any
            activator = getattr(self.__module, ACTIVATOR, None)
            stopper = getattr(activator, 'stop', None)

            exception = None
            if stopper is not None:
                try:
                    # Call the start method
                    stopper(self.__context)

                except Exception as ex:
                    _logger.exception("Error calling the activator")
                    # Store the exception (raised after service clean up)
                    exception = BundleException(ex)

            # Intermediate bundle event : activator should have cleaned up
            # everything, but some element could stay (iPOPO components, ...)
            self._fire_bundle_event(BundleEvent.STOPPING_PRECLEAN)

            # Remove remaining services (the hard way)
            self.__unregister_services()

            # Bundle is now stopped and all its services have been unregistered
            self._state = Bundle.RESOLVED
            self._fire_bundle_event(BundleEvent.STOPPED)

        # Raise the exception, if any
        if exception is not None:
            raise exception


    @SynchronizedClassMethod('_lock')
    def store_registration(self, registration):
        """
        Stores a service reference

        :param registration: A service registration
        """
        if isinstance(registration, ServiceRegistration) \
        and registration not in self.__registered_services:
            self.__registered_services.append(registration)


    @SynchronizedClassMethod('_lock')
    def remove_registration(self, registration):
        """
        Removes a service reference from the local store

        :param registration: A service registration
        """
        if registration in self.__registered_services:
            self.__registered_services.remove(registration)


    @SynchronizedClassMethod('_lock')
    def __unregister_services(self):
        """
        Unregisters all bundle services
        """
        # Copy the services list, as it will be modified during the process
        registered_services = self.__registered_services[:]
        for registration in registered_services:
            try:
                registration.unregister()

            except BundleException:
                # Ignore errors at this level
                pass

        if len(self.__registered_services) != 0:
            _logger.warning("Not all services have been unregistered...")

        # Clear the list, just to be clean
        del self.__registered_services[:]


    @SynchronizedClassMethod('_lock')
    def uninstall(self):
        """
        Uninstall the bundle
        """
        if self._state == Bundle.ACTIVE:
            self.stop()

        # Change the bundle state
        self._state = Bundle.UNINSTALLED

        # Call the framework
        self.__framework.uninstall_bundle(self)


    @SynchronizedClassMethod('_lock')
    def update(self):
        """
        Updates the bundle
        """
        # Was it active ?
        restart = self._state == Bundle.ACTIVE

        # Stop the bundle
        self.stop()

        # Change the source file age
        module_file = getattr(self.__module, "__file__", None)
        can_change = module_file is not None and os.path.isfile(module_file)
        if can_change:
            st = os.stat(module_file)

            # Change modification time to bypass weak time resolution of the
            # underlying file system
            os.utime(module_file, (st.st_atime, st.st_mtime + 1))

        # Reload the module
        imp.reload(self.__module)

        if can_change:
            # Reset times
            os.utime(module_file, (st.st_atime, st.st_mtime))

        # Re-start the bundle
        if restart:
            self.start()


    @SynchronizedClassMethod('_lock')
    def unuses_service(self, reference):
        """
        The bundle doesn't use the given service reference anymore

        :param reference: A service reference
        """
        if reference in self.__imported_services:
            self.__imported_services.remove(reference)


    @SynchronizedClassMethod('_lock')
    def uses_service(self, reference):
        """
        The bundle uses the given service reference

        :param reference: A service reference
        """
        if reference not in self.__imported_services:
            self.__imported_services.append(reference)


# ------------------------------------------------------------------------------

class Framework(Bundle):
    """
    The Pelix framework (main) class. It must be instantiated using
    FrameworkFactory
    """
    def __init__(self, properties=None):
        """
        Sets up the framework.

        :param properties: The framework properties
        """
        # Framework
        Bundle.__init__(self, self, 0, sys.modules[__name__])

        # Framework context
        self.set_context(BundleContext(self, self))

        # Framework properties
        if not isinstance(properties, dict):
            self.__properties = {}
        else:
            self.__properties = properties

        # Properties lock
        self.__properties_lock = threading.Lock()

        # Bundles
        self.__next_bundle_id = 1

        # bundle ID -> Bundle object
        self.__bundles = {}

        # Currently registering bundle...
        self.__registering_bundle = None

        # Listeners
        self.__bundle_listeners = []
        self.__service_listeners = []
        self.__framework_listeners = []

        # Listener -> filter (LDAPFilter)
        self.__service_listeners_filters = {}

        # Main service registry
        self.__next_service_id = 1

        # ServiceReference -> service instance
        self.__registry = {}
        self.__unregistering_services = {}

        # The wait_for_stop condition
        self._condition = threading.Condition()


    @SynchronizedClassMethod('_lock')
    def add_bundle_listener(self, listener):
        """
        Registers a bundle listener
        
        The bundle listener must have a method with the following prototype :
        
        .. python::
        
           def bundle_changed(self, bundle_event):
               '''
               :param bundle_event: A BundleEvent object
               '''
               # ... 

        :param listener: The bundle listener
        :return: True if the listener has been registered
        """
        return add_listener(self.__bundle_listeners, listener)


    @SynchronizedClassMethod('_lock')
    def add_framework_stop_listener(self, listener):
        """
        Registers a listener that will be called back right before the framework
        stops
        
        The framework listener must have a method with the following prototype :
        
        .. python::
        
           def framework_stopping(self):
               '''
               No parameter given
               '''
               # ... 

        :param listener: The framework stop listener
        :return: True if the listener has been registered
        """
        return add_listener(self.__framework_listeners, listener)


    @SynchronizedClassMethod('_lock')
    def add_service_listener(self, listener, ldap_filter=None):
        """
        Registers a service listener
        
        The service listener must have a method with the following prototype :
        
        .. python::
        
           def service_changed(self, event):
               '''
               Called by Pelix when some service properties changes
        
               :param event: A ServiceEvent object
               '''
               # ... 

        :param listener: The service listener
        :param ldap_filter: Listener
        """
        if add_listener(self.__service_listeners, listener):
            # Set the associated filter
            try:
                self.__service_listeners_filters[listener] = \
                                    ldapfilter.get_ldap_filter(ldap_filter)

                return True

            except ValueError:
                # Invalid filter
                remove_listener(self.__service_listeners, listener)
                _logger.exception("Invalid service listener filter")
                return False

        return False


    def add_property(self, name, value):
        """
        Adds a property to the framework **if it is not yet set**.
        
        If the property already exists (same name), then nothing is done.
        Properties can't be updated.
        
        :param name: The property name
        :param value: The value to set
        :return: True if the property was stored, else False
        """
        with self.__properties_lock:

            if name in self.__properties:
                # Already stored property
                return False

            self.__properties[name] = value
            return True


    @SynchronizedClassMethod('_lock')
    def find_service_references(self, clazz=None, ldap_filter=None):
        """
        Finds all services references matching the given filter.

        :param clazz: Class implemented by the service
        :param ldap_filter: Service filter
        :return: A list of found reference, or None
        :raise BundleException: An error occurred looking for service references
        """
        if clazz is None and ldap_filter is None:
            # Return a sorted copy of the keys list
            return sorted(self.__registry.keys())

        if inspect.isclass(clazz):
            # Escape the type name
            clazz = ldapfilter.escape_LDAP(clazz.__name__)

        elif is_string(clazz):
            # Escape the class name
            clazz = ldapfilter.escape_LDAP(clazz)

        if clazz is None:
            # Directly use the given filter
            new_filter = ldap_filter

        elif ldap_filter is None:
            # Make a filter for the object class
            new_filter = "(%s=%s)" % (OBJECTCLASS, clazz)

        else:
            # Combine filter with a AND operator
            new_filter = ldapfilter.combine_filters(\
                                    ["(%s=%s)" % (OBJECTCLASS, clazz), \
                                     ldap_filter])

        # Parse the filter
        try:
            new_filter = ldapfilter.get_ldap_filter(new_filter)

        except ValueError as ex:
            raise BundleException(ex)

        if new_filter is None:
            # Normalized filter is None : return everything
            return sorted(self.__registry.keys())

        # Find a reference that matches
        result = [ref
                  for ref in self.__registry.keys()
                  if new_filter.matches(ref.get_properties())]

        if not result:
            # No result found
            return None

        # Sort the results
        result.sort()
        return result


    @SynchronizedClassMethod('_lock')
    def fire_framework_stopping(self):
        """
        Calls all framework listeners, telling them that the framework is
        stopping
        """
        listeners = self.__framework_listeners[:]
        for listener in listeners:
            try:
                listener.framework_stopping()

            except:
                _logger.exception("An error occurred calling one of the " \
                                  "framework stop listeners")


    @SynchronizedClassMethod('_lock')
    def fire_bundle_event(self, event):
        """
        Fires a Bundle event

        :param event: The sent event
        """
        assert isinstance(event, BundleEvent)

        # Use a copy of the list, as a listener could be unregistered during
        # the loop
        listeners = self.__bundle_listeners[:]
        for listener in listeners:
            try:
                listener.bundle_changed(event)

            except:
                _logger.exception("An error occurred calling one of the " \
                                  "bundle listeners")


    @SynchronizedClassMethod('_lock')
    def fire_service_event(self, event):
        """
        Fires a service event

        :param event: The sent event
        """
        assert(isinstance(event, ServiceEvent))

        # Get the service properties
        properties = event.get_service_reference().get_properties()
        previous = None
        endmatch_event = None

        if event.get_type() == ServiceEvent.MODIFIED:
            # Modified service event : prepare the end match event
            previous = event.get_previous_properties()
            endmatch_event = ServiceEvent(ServiceEvent.MODIFIED_ENDMATCH, \
                                          event.get_service_reference(), \
                                          previous)

        # Use a copy of the list, as a listener could be unregistered during
        # the loop
        listeners = self.__service_listeners[:]
        for listener in listeners:

            # Default event to send : the one we received
            sent_event = event

            # Test if the service properties matches the filter
            ldap_filter = self.__service_listeners_filters.get(listener, None)

            if ldap_filter is not None and not ldap_filter.matches(properties):
                # Event doesn't match listener filter...

                if previous is not None and ldap_filter.matches(previous):
                    # ... but previous properties did match
                    sent_event = endmatch_event

                else:
                    # Not an end match, ignore...
                    continue

            try:
                listener.service_changed(sent_event)

            except:
                _logger.exception("An error occurred calling one of the " \
                                  "service listeners")


    @SynchronizedClassMethod('_lock')
    def get_bundle_by_id(self, bundle_id):
        """
        Retrieves the bundle with the given ID

        :param id: ID of an installed bundle
        :return: The requested bundle
        :raise BundleException: The ID is invalid
        """
        if bundle_id == 0:
            # "System bundle"
            return self

        if bundle_id not in self.__bundles:
            raise BundleException("Invalid bundle ID %d" % bundle_id)

        return self.__bundles[bundle_id]


    @SynchronizedClassMethod('_lock')
    def get_bundle_by_name(self, bundle_name):
        """
        Retrieves the bundle with the given name

        :param name: Name of the bundle to look for
        :return: The requested bundle, None if not found
        """
        if bundle_name is None:
            # Nothing to do
            return None

        if bundle_name is self.get_symbolic_name():
            # System bundle requested
            return self

        if self.__registering_bundle is not None \
        and bundle_name == self.__registering_bundle.get_symbolic_name():
            # Request for the installing bundle...
            return self.__registering_bundle

        for bundle in self.__bundles.values():
            if bundle_name == bundle.get_symbolic_name():
                # Found !
                return bundle

        # Not found...
        return None


    @SynchronizedClassMethod('_lock')
    def get_bundles(self):
        """
        Returns a list of all installed bundles
        """
        return list(self.__bundles.values())


    def get_property(self, name):
        """
        Retrieves a framework or system property. As framework properties don't
        change while it's running, this method don't need to be protected.

        :param name: The property name
        """
        with self.__properties_lock:
            if name in self.__properties:
                return self.__properties[name]

        return os.getenv(name)


    @SynchronizedClassMethod('_lock')
    def get_service(self, bundle, reference):
        """
        Retrieves the service corresponding to the given reference

        :param bundle: The bundle requiring the service
        :param reference: A service reference
        :return: The requested service
        :raise BundleException: The service could not be found
        :raise TypeError: The argument is not a ServiceReference object
        """
        if not isinstance(bundle, Bundle):
            raise TypeError("A Bundle object must be given")

        if not isinstance(reference, ServiceReference):
            raise TypeError("A ServiceReference object must be given")

        # Be sure to have the instance
        if reference in self.__registry:
            service = self.__registry[reference]

            # Indicate the dependency
            bundle.uses_service(reference)
            reference.used_by(bundle)

        elif reference in self.__unregistering_services:
            # Unregistering service, just give it
            return self.__unregistering_services[reference]

        else:
            # Not found
            raise BundleException("Service not found (reference: %s)" \
                                  % reference)

        return service


    def get_symbolic_name(self):
        """
        Retrieves the framework symbolic name

        :return: Always "org.psem2m.pelix"
        """
        return "org.psem2m.pelix"


    @SynchronizedClassMethod('_lock')
    def install_bundle(self, location):
        """
        Installs the bundle from the given location

        :param location: A bundle location
        :return: The installed bundle ID
        :raise BundleException: Something happened
        """
        # Compute the bundle ID
        bundle_id = self.__next_bundle_id

        # Prepare the bundle object and its context
        bundle = Bundle(self, bundle_id, location)
        bundle.set_context(BundleContext(self, bundle))

        self.__registering_bundle = bundle

        # Load the module
        try:
            # module = __import__(location) -> package level
            # import_module -> Nested module

            # Special case : __main__ module
            if location == "__main__":
                try:
                    module = sys.modules[location]

                except KeyError:
                    raise BundleException("Error reloading the __main__ module")

            else:
                module = importlib.import_module(location)

        except ImportError as ex:
            # Error importing the module
            self.__registering_bundle = None
            raise BundleException(ex)

        # Set the bundle module
        bundle.set_module(module)

        # The bundle is now registered
        self.__registering_bundle = None

        # Update the bundle ID counter
        self.__next_bundle_id += 1

        # Store the bundle
        self.__bundles[bundle_id] = bundle

        # Fire the bundle installed event
        event = BundleEvent(BundleEvent.INSTALLED, bundle)
        self.fire_bundle_event(event)

        return bundle_id


    @SynchronizedClassMethod('_lock')
    def register_service(self, bundle, clazz, service, properties, send_event):
        """
        Registers a service and calls the listeners

        :param bundle: The bundle registering the service
        :param clazz: Name(s) of the interface(s) implemented by service
        :param properties: Service properties
        :param send_event: If not, doesn't trigger a service registered event
        :return: A ServiceRegistration object
        :raise BundleException: An error occurred while registering the service
        """
        if bundle is None or service is None or not clazz:
            raise BundleException("Invalid registration parameters")

        if not isinstance(properties, dict):
            # Be sure we have a valid dictionary
            properties = {}

        else:
            # Use a copy of the given properties
            properties = properties.copy()

        # Prepare the class specification
        if not isinstance(clazz, list):
            # Make a list from the single class
            clazz = [clazz]

        # Test the list content
        object_class = []
        for svc_clazz in clazz:

            if inspect.isclass(svc_clazz):
                # Keep the type name
                svc_clazz = svc_clazz.__name__

            if not svc_clazz or not is_string(svc_clazz):
                # Invalid class name
                raise BundleException("Invalid class name : %s" % svc_clazz)

            # Class OK
            object_class.append(svc_clazz)


        # Prepare properties
        service_id = self.__next_service_id
        self.__next_service_id += 1

        properties[OBJECTCLASS] = object_class
        properties[SERVICE_ID] = service_id

        # Make the service reference
        ref = ServiceReference(bundle, properties)

        # Store it in global registry
        self.__registry[ref] = service

        # Make the service registration
        registration = ServiceRegistration(self, ref, properties)

        # Store it in the bundle registry
        bundle.store_registration(registration)

        if send_event:
            # Call the listeners
            event = ServiceEvent(ServiceEvent.REGISTERED, ref)
            self.fire_service_event(event)

        return registration


    @SynchronizedClassMethod('_lock')
    def remove_bundle_listener(self, listener):
        """
        Unregisters a bundle listener

        :param listener: The bundle listener
        :return: True if the listener has been unregistered
        """
        return remove_listener(self.__bundle_listeners, listener)


    @SynchronizedClassMethod('_lock')
    def remove_framework_stop_listener(self, listener):
        """
        Unregisters a framework stop listener

        :param listener: The framework stop listener
        :return: True if the listener has been unregistered
        """
        return remove_listener(self.__framework_listeners, listener)


    @SynchronizedClassMethod('_lock')
    def remove_service_listener(self, listener):
        """
        Unregisters a service listener

        :param listener: The service listener
        :return: True if the listener has been unregistered
        """
        # Remove the listener from the list
        result = remove_listener(self.__service_listeners, listener)

        if listener in self.__service_listeners_filters:
            # Also delete the associated filter
            del self.__service_listeners_filters[listener]

        return result


    @SynchronizedClassMethod('_lock')
    def start(self):
        """
        Starts the framework

        :return: True if the bundle has been started, False if it was already
                 running
        :raise BundleException: A bundle failed to start
        """
        if self._state in (Bundle.STARTING, Bundle.ACTIVE):
            # Already started framework
            return

        # Starting...
        self._state = Bundle.STARTING
        self._fire_bundle_event(BundleEvent.STARTING)

        # Start all registered bundles
        try:
            for bundle in self.__bundles.copy().values():
                bundle.start()

        except BundleException:
            # A bundle failed to start : reset the framework state
            self._state = Bundle.RESOLVED

            # Re-raise the error
            raise

        # Bundle is now active
        self._state = Bundle.ACTIVE
        return True


    @SynchronizedClassMethod('_lock')
    def stop(self):
        """
        Stops the framework
        
        :return: True if the framework stopped, False it wasn't running
        """
        if self._state != Bundle.ACTIVE:
            # Invalid state
            return False

        # Stopping...
        self._state = Bundle.STOPPING
        self._fire_bundle_event(BundleEvent.STOPPING)

        # Notify listeners that the bundle is stopping
        self.fire_framework_stopping()

        i = self.__next_bundle_id
        while i > 0:

            bundle = self.__bundles.get(i, None)
            i -= 1

            if bundle is None or bundle.get_state() != Bundle.ACTIVE:
                # Ignore inactive bundle
                continue

            try:
                bundle.stop()

            except:
                # Just log exceptions
                _logger.exception("Error stopping bundle %s" \
                                  % bundle.get_symbolic_name())

        # Framework is now stopped
        self._state = Bundle.RESOLVED
        self._fire_bundle_event(BundleEvent.STOPPED)

        # All bundles have been stopped, release "wait_for_stop"
        with self._condition:
            self._condition.notify_all()

        return True


    def uninstall(self):
        """
        A framework can't be uninstalled

        :raise BundleException: This method must not be called
        """
        raise BundleException("A framework can't be uninstalled")


    @SynchronizedClassMethod('_lock')
    def uninstall_bundle(self, bundle):
        """
        Ends the uninstallation of the given bundle (must be called by Bundle)

        :param bundle: The bundle to uninstall
        :raise BundleException: Invalid bundle
        """
        if bundle is None:
            # Do nothing
            return

        # Stop the bundle first
        bundle.stop()

        bundle_id = bundle.get_bundle_id()
        if bundle_id not in self.__bundles:
            raise BundleException("Invalid bundle %s" % bundle)

        # Notify listeners
        self.fire_bundle_event(BundleEvent(BundleEvent.UNINSTALLED, bundle))

        # Remove it from the dictionary
        del self.__bundles[bundle_id]

        # Remove it from the system => avoid unintended behaviors and forces
        # a complete module reload if it is re-installed
        del sys.modules[bundle.get_symbolic_name()]


    @SynchronizedClassMethod('_lock')
    def unregister_service(self, registration):
        """
        Unregisters the given service

        :param reference: A ServiceRegistration to the service to unregister
        :raise BundleException: Invalid reference
        """
        assert(isinstance(registration, ServiceRegistration))

        reference = registration.get_reference()
        if reference not in self.__registry:
            raise BundleException("Invalid reference %s" % str(reference))

        # Keep a track of the unregistering reference
        self.__unregistering_services[reference] = self.__registry[reference]

        # Remove it from the main registry
        del self.__registry[reference]

        # Call the listeners (blocking call)
        event = ServiceEvent(ServiceEvent.UNREGISTERING, reference)
        self.fire_service_event(event)

        # Remove the registration from the parent bundle
        reference.get_bundle().remove_registration(registration)

        # Remove the unregistering reference
        del self.__unregistering_services[reference]

        return True


    @SynchronizedClassMethod('_lock')
    def update(self):
        """
        Stops and starts the framework
        """
        if self._state == Bundle.ACTIVE:
            self.stop()
            self.start()


    def wait_for_stop(self, timeout=None):
        """
        Waits for the framework to stop. Does nothing if the framework bundle
        is not in ACTIVE state.
        
        Uses a threading.Condition object
        
        :param timeout: The maximum time to wait (in seconds)
        :return: True if the framework has stopped, False if the timeout raised
        """
        if self._state != Bundle.ACTIVE:
            # Inactive framework, ignore the call
            return True

        with self._condition:
            self._condition.wait(timeout)

        with self._lock:
            # If the timeout raised, we should be in another state
            return self._state == Bundle.RESOLVED

# ------------------------------------------------------------------------------

class BundleContext(object):
    """
    Represents a bundle context
    """
    def __init__(self, framework, bundle):
        """
        Sets up the bundle context

        :param framework: Hosting framework
        :param bundle: The associated bundle
        """
        self.__bundle = bundle
        self.__framework = framework


    def __str__(self):
        """
        String representation
        """
        return "BundleContext(%s)" % str(self.__bundle)


    def add_bundle_listener(self, listener):
        """
        Registers a bundle listener

        The bundle listener must have a method with the following prototype :

        .. python::

           def bundle_changed(self, bundle_event):
               '''
               :param bundle_event: A BundleEvent object
               '''
               # ... 

        :param listener: The bundle listener
        :return: True if the listener has been registered
        """
        return self.__framework.add_bundle_listener(listener)


    def add_framework_stop_listener(self, listener):
        """
        Registers a listener that will be called back right before the framework
        stops
        
        The framework listener must have a method with the following prototype :
        
        .. python::
        
           def framework_stopping(self):
               '''
               No parameter given
               '''
               # ... 

        :param listener: The framework stop listener
        :return: True if the listener has been registered
        """
        return self.__framework.add_framework_stop_listener(listener)


    def add_service_listener(self, listener, ldap_filter=None):
        """
        Registers a service listener
        
        The service listener must have a method with the following prototype :
        
        .. python::
        
           def service_changed(self, event):
               '''
               Called by Pelix when some service properties changes
        
               :param event: A ServiceEvent object
               '''
               # ... 

        :param listener: The listener to register
        :param ldap_filter: An LDAP filter on the service properties
        :return: True if the listener has been successfully registered
        """
        return self.__framework.add_service_listener(listener, ldap_filter)


    def get_all_service_references(self, clazz, ldap_filter):
        """
        Returns an array of ServiceReference objects.
        The returned array of ServiceReference objects contains services that
        were registered under the specified class and match the specified filter
        expression.
        """
        return self.__framework.find_service_references(clazz, ldap_filter)


    def get_bundle(self, bundle_id=None):
        """
        Retrieves the bundle with the given ID. If no ID is given (None).

        :param bundle_id: A bundle ID
        :return: The requested bundle
        :raise BundleException: The given ID is invalid
        """
        if bundle_id is None:
            # Current bundle
            return self.__bundle

        return self.__framework.get_bundle_by_id(bundle_id)


    def get_bundles(self):
        """
        Returns a list of all installed bundles
        """
        return self.__framework.get_bundles()


    def get_property(self, name):
        """
        Returns the value of a property of the framework, else returns the OS
        environment value.

        :param name: A property name
        """
        return self.__framework.get_property(name)


    def get_service(self, reference):
        """
        Returns the service described with the given reference
        """
        return self.__framework.get_service(self.__bundle, reference)


    def get_service_reference(self, clazz, ldap_filter=None):
        """
        Returns a ServiceReference object for a service that implements and \
        was registered under the specified class

        :param clazz: The class name with which the service was registered.
        :param ldap_filter: A filter on service properties
        :return: A service reference, None if not found
        """
        refs = self.__framework.find_service_references(clazz, ldap_filter)
        if refs is not None and len(refs) > 0:
            return refs[0]

        return None


    def get_service_references(self, clazz, ldap_filter):
        """
        Returns the service references for services that were registered under
        the specified class by this bundle and matching the given filter

        :param ldap_filter: A filter on service properties
        """
        refs = self.__framework.find_service_references(clazz, ldap_filter)
        for ref in refs:
            if ref.get_bundle() is not self.__bundle:
                refs.remove(ref)

        return refs


    def install_bundle(self, location):
        """
        Installs the bundle at the given location

        :param location: Location of the bundle to install
        :return: The installed bundle ID
        :raise BundleException: An error occurred while installing the bundle
        """
        return self.__framework.install_bundle(location)


    def register_service(self, clazz, service, properties, send_event=True):
        """
        Registers a service

        :param clazz: Class or Classes (list) implemented by this service
        :param service: The service instance
        :param properties: The services properties (dictionary)
        :param send_event: If not, doesn't trigger a service registered event
        :return: A ServiceRegistration object
        :raise BundleException: An error occurred while registering the service
        """
        return self.__framework.register_service(self.__bundle, clazz, \
                                                 service, properties, \
                                                 send_event)


    def remove_bundle_listener(self, listener):
        """
        Unregisters a bundle listener
        
        :param listener: The bundle listener
        :return: True if the listener has been unregistered
        """
        return self.__framework.remove_bundle_listener(listener)


    def remove_framework_stop_listener(self, listener):
        """
        Unregisters a framework stop listener

        :param listener: The framework stop listener
        :return: True if the listener has been unregistered
        """
        return self.__framework.remove_framework_stop_listener(listener)


    def remove_service_listener(self, listener):
        """
        Unregisters a service listener
        
        :param listener: The service listener
        :return: True if the listener has been unregistered
        """
        return self.__framework.remove_service_listener(listener)


    def unget_service(self, reference):
        """
        Disables a reference to the service
        """
        with reference._lock:
            # Lose the dependency
            self.__bundle.unuses_service(reference)
            reference.unused_by(self.__bundle)


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

        for mandatory in (SERVICE_ID, OBJECTCLASS):
            if mandatory not in properties:
                raise BundleException(\
                            "A Service must at least have a '%s' entry" \
                            % mandatory)

        self._lock = threading.RLock()
        self.__bundle = bundle
        self.__properties = properties
        self.__using_bundles = []
        self.__service_id = properties[SERVICE_ID]


    def __str__(self):
        """
        String representation
        """
        return "ServiceReference(%s, %d, %s)" \
                % (self.__service_id, \
                   self.__bundle.get_bundle_id(), \
                   self.__properties[OBJECTCLASS])


    def __hash__(self):
        """
        Returns the service hash
        """
        return self.__service_id


    def __cmp__(self, other):
        """
        ServiceReference comparison

        See : http://www.osgi.org/javadoc/r4v43/org/osgi/framework/ServiceReference.html#compareTo%28java.lang.Object%29
        """
        if self is other:
            return 0

        if not isinstance(other, ServiceReference):
            # Not comparable => lesser
            return -1

        if self.__service_id == other.__service_id:
            # Same ID, same service
            return 0

        service_rank = int(self.__properties.get(SERVICE_RANKING, 65535))
        other_rank = int(other.__properties.get(SERVICE_RANKING, 65535))

        if service_rank == other_rank:
            # Same rank, ID discriminates (greater ID, lesser reference)
            if self.__service_id > other.__service_id:
                return -1
            else:
                return 1

        elif service_rank < other_rank:
            # Lesser rank value, lesser reference
            return -1

        else:
            return 1


    def __eq__(self, other):
        """
        Equal to other
        """
        if self is other:
            # Same object
            return True

        if not isinstance(other, ServiceReference):
            # Not a service reference
            return False

        return self.__service_id == other.__service_id


    def __ge__(self, other):
        """
        Greater or equal
        """
        return self.__cmp__(other) >= 0


    def __gt__(self, other):
        """
        Greater than other
        """
        return self.__cmp__(other) > 0


    def __le__(self, other):
        """
        Lesser or equal
        """
        return self.__cmp__(other) <= 0


    def __lt__(self, other):
        """
        Lesser than other
        """
        return self.__cmp__(other) < 0


    def get_bundle(self):
        """
        Retrieves the bundle that registered this service
        """
        return self.__bundle


    def get_using_bundles(self):
        """
        Retrieves the bundles that use this service
        """
        return self.__using_bundles


    @SynchronizedClassMethod('_lock')
    def get_properties(self):
        """
        Retrieves a copy of the service properties
        """
        return self.__properties.copy()


    @SynchronizedClassMethod('_lock')
    def get_property(self, name):
        """
        Retrieves the property value for the given name

        :return: The property value, None if not found
        """
        return self.__properties.get(name, None)


    @SynchronizedClassMethod('_lock')
    def get_property_keys(self):
        """
        Returns an array of the keys in the properties of the service

        :return: An array of property keys.
        """
        return self.__properties.keys()


    @SynchronizedClassMethod('_lock')
    def unused_by(self, bundle):
        """
        Indicates that this reference is not being used anymore by the given
        bundle

        :param bundle: A bundle that used this reference
        """
        if bundle is None or bundle is self.__bundle:
            # Ignore
            return

        if bundle in self.__using_bundles:
            self.__using_bundles.remove(bundle)


    @SynchronizedClassMethod('_lock')
    def used_by(self, bundle):
        """
        Indicates that this reference is being used by the given bundle

        :param bundle: A bundle using this reference
        """
        if bundle is None or bundle is self.__bundle:
            # Ignore
            return

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
        :param properties: A reference to the service properties dictionary
        """
        self._lock = threading.RLock()
        self.__framework = framework
        self.__reference = reference
        self.__properties = properties


    def __str__(self):
        """
        String representation
        """
        return "ServiceRegistration(%s)" % str(self.__reference)


    def get_reference(self):
        """
        Retrieves the reference associated to this registration
        """
        return self.__reference


    @SynchronizedClassMethod('_lock')
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
            del properties[key]

        if not properties:
            # Nothing to do
            return

        # Update the properties
        previous = self.__properties.copy()
        self.__properties.update(properties)

        # Trigger a new computation in the framework
        self.__framework.fire_service_event(\
                        ServiceEvent(ServiceEvent.MODIFIED, self.__reference, \
                                     previous))


    def unregister(self):
        """
        Unregisters the service
        """
        self.__framework.unregister_service(self)

# ------------------------------------------------------------------------------

class BundleEvent(object):
    """
    Represents a bundle event
    """

    INSTALLED = 1
    """The bundle has been installed."""

    STARTED = 2
    """The bundle has been started."""

    STARTING = 128
    """The bundle is about to be activated."""

    STOPPED = 4
    """
    The bundle has been stopped. All of its services have been unregistered.
    """

    STOPPING = 256
    """The bundle is about to deactivated."""

    STOPPING_PRECLEAN = 512
    """
    The bundle has been deactivated, but some of its services may still remain.
    """

    UNINSTALLED = 16
    """The bundle has been uninstalled."""

    UPDATED = 8
    """The bundle has been updated."""


    def __init__(self, kind, bundle):
        """
        Sets up the event
        """
        self.__kind = kind
        self.__bundle = bundle


    def __str__(self):
        """
        String representation
        """
        return "BundleEvent(%d, %s)" % (self.__kind, str(self.__bundle))


    def get_bundle(self):
        """
        Retrieves the modified bundle
        """
        return self.__bundle


    def get_kind(self):
        """
        Retrieves the kind of event
        """
        return self.__kind

# ------------------------------------------------------------------------------

class ServiceEvent(object):
    """
    Represents a service event
    """

    REGISTERED = 1
    """ This service has been registered """

    MODIFIED = 2
    """ The properties of a registered service have been modified """

    UNREGISTERING = 4
    """ This service is in the process of being unregistered """

    MODIFIED_ENDMATCH = 8
    """
    The properties of a registered service have been modified and the new
    properties no longer match the listener's filter
    """

    def __init__(self, kind, reference, previous_properties=None):
        """
        Sets up the event

        :param kind: Kind of event
        :param reference: Reference to the modified service
        :param previous_properties: Previous service properties (for MODIFIED
                                    and MODIFIED_ENDMATCH events)
        """
        self.__kind = kind
        self.__reference = reference

        if previous_properties is not None \
        and not isinstance(previous_properties, dict):
            # Accept None or dict() only
            previous_properties = {}

        self.__previous_properties = previous_properties


    def __str__(self):
        """
        String representation
        """
        return "ServiceEvent(%s, %s)" % (self.__kind, \
                                         str(self.__reference))


    def get_previous_properties(self):
        """
        Previous service properties, meaningless if the the event is not
        MODIFIED nor MODIFIED_ENDMATCH.
        """
        return self.__previous_properties


    def get_service_reference(self):
        """
        Retrieves the service reference
        """
        return self.__reference


    def get_type(self):
        """
        Retrieves the kind of service event
        """
        return self.__kind

# ------------------------------------------------------------------------------

class FrameworkFactory(object):
    """
    A framework factory
    """

    __singleton = None
    """ The framework singleton """

    @classmethod
    def get_framework(cls, properties=None):
        """
        If it doesn't exist yet, creates a framework with the given properties,
        else returns the current framework instance.

        :return: A Pelix instance
        """
        if cls.__singleton is None:
            cls.__singleton = Framework(properties)

        return cls.__singleton


    @classmethod
    def delete_framework(cls, framework):
        """
        Removes the framework singleton

        :return: True on success, else False
        """
        if cls.__singleton is framework:

            try:
                framework.stop()

            except:
                _logger.exception("Error stopping the framework")


            bundles = framework.get_bundles()
            for bundle in bundles:
                try:
                    bundle.uninstall()
                except:
                    _logger.exception("Error uninstalling bundle %s", \
                                      bundle.get_symbolic_name())

            cls.__singleton = None
            return True

        return False

if __name__ == "__main__":
    FrameworkFactory.get_framework()
