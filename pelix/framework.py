#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Core module for Pelix.

Pelix is a Python framework that aims to act as OSGi as much as possible

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.5.5
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
__version_info__ = (0, 5, 5)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Wild import of constants (to stay compatible with previous version)
from pelix.constants import *

# Pelix beans
from pelix.internals.events import BundleEvent, ServiceEvent
from pelix.internals.registry import EventDispatcher, ServiceRegistry, \
    ServiceReference, ServiceRegistration

# Pelix utility modules
from pelix.utilities import SynchronizedClassMethod, is_string

# Standard library
import imp
import importlib
import inspect
import logging
import os
import pkgutil
import sys
import threading
import uuid

# ------------------------------------------------------------------------------

# Prepare the module logger
_logger = logging.getLogger("pelix.main")

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


    def __init__(self, framework, bundle_id, name, module):
        """
        Sets up the bundle descriptor

        :param framework: The host framework
        :param bundle_id: The ID of the bundle in the host framework
        :param name: The bundle symbolic name
        :param module: The bundle module
        """
        # A reentrant lock for synchronization
        self._lock = threading.RLock()

        # Bundle
        self.__context = BundleContext(framework, self)
        self.__id = bundle_id
        self.__module = module
        self.__name = name

        self.__framework = framework
        self._state = Bundle.RESOLVED

        # Registered services
        self.__registered_services = []
        self.__registration_lock = threading.Lock()


    def __str__(self):
        """
        String representation
        """
        return "Bundle(ID={0}, Name={1})".format(self.__id, self.__name)


    def _fire_bundle_event(self, kind):
        """
        Fires a bundle event of the given kind

        :param kind: Kind of event
        """
        self.__framework._dispatcher.fire_bundle_event(BundleEvent(kind, self))


    def _registered_service(self, registration):
        """
        Bundle is notified by the framework that a service has been registered
        in the name of this bundle.

        :param registration: The service registration object
        """
        with self.__registration_lock:
            self.__registered_services.append(registration)


    def _unregistered_service(self, registration):
        """
        Bundle is notified by the framework that a service has been unregistered
        in the name of this bundle.

        :param registration: The service registration object
        """
        with self.__registration_lock:
            if registration in self.__registered_services:
                self.__registered_services.remove(registration)


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


    def get_registered_services(self):
        """
        Returns this bundle's ServiceReference list for all services it has
        registered or an empty list

        The list is valid at the time of the call to this method, however, as
        the Framework is a very dynamic environment, services can be modified or
        unregistered at any time.

        :return: An array of ServiceReference objects
        :raise BundleException: If the bundle has been uninstalled
        """
        if self._state == Bundle.UNINSTALLED:
            raise BundleException("Can't call 'get_registered_services' on an "
                                  "uninstalled bundle")

        return self.__framework._registry.get_bundle_registered_services(self)


    def get_services_in_use(self):
        """
        Returns this bundle's ServiceReference list for all services it is using
        or an empty list.
        A bundle is considered to be using a service if its use count for that
        service is greater than zero.

        The list is valid at the time of the call to this method, however, as
        the Framework is a very dynamic environment, services can be modified
        or unregistered at any time.

        :return: An array of ServiceReference objects
        :raise BundleException: If the bundle has been uninstalled
        """
        if self._state == Bundle.UNINSTALLED:
            raise BundleException("Can't call 'get_services_in_use' on an "
                                  "uninstalled bundle")

        return self.__framework._registry.get_bundle_imported_services(self)


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
        Retrieves the bundle version, using the ``__version__`` or
        ``__version_info__`` attributes of its module.

        :return: The bundle version, "0.0.0" by default
        """
        # Get the version value
        version = getattr(self.__module, "__version__", None)
        if version:
            return version

        # Convert the __version_info__ entry
        info = getattr(self.__module, "__version_info__", None)
        if info:
            return ".".join(str(part) for part in __version_info__)

        # No version
        return "0.0.0"


    def start(self):
        """
        Starts the bundle. Does nothing if the bundle is already starting or
        active.

        :raise BundleException: The framework is not yet started or the bundle
                                activator failed.
        """
        if self.__framework._state not in (Bundle.STARTING, Bundle.ACTIVE):
            # Framework is not running
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

                except (FrameworkException, BundleException):
                    # Restore previous state
                    self._state = previous_state

                    # Re-raise directly Pelix exceptions
                    _logger.exception("Pelix error raised by %s while starting",
                                      self.__name)
                    raise

                except Exception as ex:
                    # Restore previous state
                    self._state = previous_state

                    # Raise the error
                    _logger.exception("Error raised by %s while starting",
                                      self.__name)
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
            # Store the bundle current state
            previous_state = self._state

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

                except (FrameworkException, BundleException) as ex:
                    # Restore previous state
                    self._state = previous_state

                    # Re-raise directly Pelix exceptions
                    _logger.exception("Pelix error raised by %s while stopping",
                                      self.__name)
                    exception = ex

                except Exception as ex:
                    _logger.exception("Error raised by %s while stopping",
                                      self.__name)
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


    def __unregister_services(self):
        """
        Unregisters all bundle services
        """
        # Copy the services list, as it will be modified during the process
        with self.__registration_lock:
            registered_services = self.__registered_services[:]

        for registration in registered_services:
            try:
                registration.unregister()

            except BundleException:
                # Ignore errors at this level
                pass

        if len(self.__registered_services) != 0:
            _logger.warning("Not all services have been unregistered...")

        with self.__registration_lock:
            # Clear the list, just to be clean
            del self.__registered_services[:]


    def uninstall(self):
        """
        Uninstalls the bundle
        """
        with self._lock:
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

        # Send the update event
        self._fire_bundle_event(BundleEvent.UPDATE_BEGIN)

        try:
            # Stop the bundle
            self.stop()
        except:
            # Something wrong occurred, notify listeners
            self._fire_bundle_event(BundleEvent.UPDATE_FAILED)
            raise

        # Change the source file age
        time_changed = False
        module_file = getattr(self.__module, "__file__", None)
        if module_file is not None and os.path.isfile(module_file):
            try:
                stat = os.stat(module_file)

                # Change modification time to bypass weak time resolution of the
                # underlying file system
                os.utime(module_file, (stat.st_atime, stat.st_mtime + 1))
                time_changed = True

            except OSError:
                # Can't touch the file
                _logger.warning("Failed to update the modification time of "
                                "'%s'. The bundle update might not reflect the "
                                "latest changes.", module_file)

        try:
            # Reload the module
            imp.reload(self.__module)

        except SyntaxError as ex:
            # Exception raised in Python 3
            _logger.exception("Error updating %s: %s", self.__name, ex)

        if time_changed:
            try:
                # Reset times
                os.utime(module_file, (stat.st_atime, stat.st_mtime))

            except OSError:
                # Shouldn't occur, since we succeeded before the update
                _logger.debug("Failed to reset the modification time of '%s'",
                              module_file)

        if restart:
            try:
                # Re-start the bundle
                self.start()
            except:
                # Something wrong occurred, notify listeners
                self._fire_bundle_event(BundleEvent.UPDATE_FAILED)
                raise

        # Bundle update finished
        self._fire_bundle_event(BundleEvent.UPDATED)

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
        # Framework bundle set up
        Bundle.__init__(self, self, 0, self.get_symbolic_name(),
                        sys.modules[__name__])

        # Framework properties
        if not isinstance(properties, dict):
            self.__properties = {}
        else:
            # Use a copy of the properties, to avoid external changes
            self.__properties = properties.copy()

        # Generate a framework instance UUID, if needed
        framework_uid = self.__properties.get(FRAMEWORK_UID)
        if not framework_uid:
            framework_uid = str(uuid.uuid4())

        # Normalize the UID: it must be a string
        self.__properties[FRAMEWORK_UID] = str(framework_uid)

        # Properties lock
        self.__properties_lock = threading.Lock()

        # Bundles (start at 1, as 0 is reserved for the framework itself)
        self.__next_bundle_id = 1

        # Bundle ID -> Bundle object
        self.__bundles = {}

        # Bundles lock
        self.__bundles_lock = threading.RLock()

        # Event dispatcher
        self._dispatcher = EventDispatcher()

        # Service registry
        self._registry = ServiceRegistry(self)
        self.__unregistering_services = {}

        # The wait_for_stop event (initially stopped)
        self._fw_stop_event = threading.Event()
        self._fw_stop_event.set()


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


    def find_service_references(self, clazz=None, ldap_filter=None,
                                only_one=False):
        """
        Finds all services references matching the given filter.

        :param clazz: Class implemented by the service
        :param ldap_filter: Service filter
        :param only_one: Return the first matching service reference only
        :return: A list of found reference, or None
        :raise BundleException: An error occurred looking for service references
        """
        return self._registry.find_service_references(clazz, ldap_filter,
                                                      only_one)


    def get_bundle_by_id(self, bundle_id):
        """
        Retrieves the bundle with the given ID

        :param bundle_id: ID of an installed bundle
        :return: The requested bundle
        :raise BundleException: The ID is invalid
        """
        if bundle_id == 0:
            # "System bundle"
            return self

        with self.__bundles_lock:
            if bundle_id not in self.__bundles:
                raise BundleException("Invalid bundle ID {0}".format(bundle_id))

            return self.__bundles[bundle_id]


    def get_bundle_by_name(self, bundle_name):
        """
        Retrieves the bundle with the given name

        :param bundle_name: Name of the bundle to look for
        :return: The requested bundle, None if not found
        """
        if bundle_name is None:
            # Nothing to do
            return None

        if bundle_name is self.get_symbolic_name():
            # System bundle requested
            return self

        with self.__bundles_lock:
            for bundle in self.__bundles.values():
                if bundle_name == bundle.get_symbolic_name():
                    # Found !
                    return bundle

            # Not found...
            return None


    def get_bundles(self):
        """
        Returns the list of all installed bundles

        :return: the list of all installed bundles
        """
        with self.__bundles_lock:
            return list(self.__bundles.values())


    def get_properties(self):
        """
        Retrieves a copy of the stored framework properties.
        """
        with self.__properties_lock:
            return self.__properties.copy()


    def get_property(self, name):
        """
        Retrieves a framework or system property. As framework properties don't
        change while it's running, this method don't need to be protected.

        :param name: The property name
        """
        with self.__properties_lock:
            return self.__properties.get(name, os.getenv(name))


    def get_property_keys(self):
        """
        Returns an array of the keys in the properties of the service

        :return: An array of property keys.
        """
        with self.__properties_lock:
            return tuple(self.__properties.keys())


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
            raise TypeError("First argument must be a Bundle object")

        if not isinstance(reference, ServiceReference):
            raise TypeError("Second argument must be a ServiceReference object")

        if reference in self.__unregistering_services:
            # Unregistering service, just give it
            return self.__unregistering_services[reference]

        return self._registry.get_service(bundle, reference)


    def get_symbolic_name(self):
        """
        Retrieves the framework symbolic name

        :return: Always "pelix.framework"
        """
        return "pelix.framework"


    def install_bundle(self, name, path=None):
        """
        Installs the bundle with the given name

        *Note:* Before Pelix 0.5.0, this method returned the ID of the installed
        bundle, instead of the Bundle object.

        **WARNING:** The behavior of the loading process is subject to changes,
        as it does not allow to safely run multiple frameworks in the same
        Python interpreter, as they might share global module values.

        :param name: A bundle name
        :param path: Preferred path to load the module
        :return: The installed Bundle object
        :raise BundleException: Something happened
        """
        with self.__bundles_lock:
            # A bundle can't be installed twice
            for bundle in self.__bundles.values():
                if bundle.get_symbolic_name() == name:
                    _logger.warning('Already installed bundle: %s', name)
                    return bundle

            # Load the module
            try:
                if path:
                    # Use the given path in priority
                    sys.path.insert(0, path)

                if name in sys.modules:
                    # The module has already been loaded
                    module = sys.modules[name]

                else:
                    # Load the module
                    #  __import__(name) -> package level
                    # import_module -> module level
                    module = importlib.import_module(name)

            except ImportError as ex:
                # Error importing the module
                raise BundleException("Error installing bundle {0}: {1}" \
                                      .format(name, ex))

            finally:
                if path:
                    # Clean up the path. The loaded module(s) might
                    # have changed the path content, so do not use an
                    # index
                    sys.path.remove(path)

            # Add the module to sys.modules, just to be sure
            sys.modules[name] = module

            # Compute the bundle ID
            bundle_id = self.__next_bundle_id

            # Prepare the bundle object and its context
            bundle = Bundle(self, bundle_id, name, module)

            # Store the bundle
            self.__bundles[bundle_id] = bundle

            # Update the bundle ID counter
            self.__next_bundle_id += 1

        # Fire the bundle installed event
        event = BundleEvent(BundleEvent.INSTALLED, bundle)
        self._dispatcher.fire_bundle_event(event)

        return bundle


    def install_package(self, path, recursive=False, prefix=None):
        """
        Installs all the modules found in the given package

        :param path: Path of the package (folder)
        :param recursive: If True, install the sub-packages too
        :param prefix: (**internal**) Prefix for all found modules
        :return: A 2-tuple, with the list of installed bundles and the list
                 of failed modules names
        :raise ValueError: Invalid path
        """
        if not path:
            raise ValueError("Empty path")

        elif not is_string(path):
            raise ValueError("Path must be a string")

        # Use an absolute path
        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise ValueError("Inexistent path: {0}".format(path))

        # Create a simple visitor
        def visitor(fullname, is_package, module_path):
            # Accept everything in recursive mode, else avoid packages
            return recursive or not is_package

        # Set up the prefix if needed
        if prefix is None:
            prefix = os.path.basename(path)

        bundles = set()
        failed = set()

        with self.__bundles_lock:
            try:
                # Install the package first, resolved from the parent directory
                bundles.add(self.install_bundle(prefix, os.path.dirname(path)))

                # Visit the package
                visited, sub_failed = self.install_visiting(path, visitor,
                                                            prefix)

                # Update the sets
                bundles.update(visited)
                failed.update(sub_failed)

            except BundleException as ex:
                # Error loading the module
                _logger.warning("Error loading package %s: %s", prefix, ex)
                failed.add(prefix)

        return bundles, failed


    def install_visiting(self, path, visitor, prefix=None):
        """
        Installs all the modules found in the given path if they are accepted
        by the visitor.

        The visitor must be a callable accepting 3 parameters:

           * fullname: The full name of the module
           * is_package: If True, the module is a package
           * module_path: The path to the module file

        :param path: Root search path
        :param visitor: The visiting callable
        :param prefix: (**internal**) Prefix for all found modules
        :return: A 2-tuple, with the list of installed bundles and the list
                 of failed modules names
        :raise ValueError: Invalid path or visitor
        """
        # Validate the path
        if not path:
            raise ValueError("Empty path")

        elif not is_string(path):
            raise ValueError("Path must be a string")

        # Validate the visitor
        if visitor is None:
            raise ValueError("No visitor method given")

        # Use an absolute path
        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise ValueError("Inexistent path: {0}".format(path))

        # Set up the prefix if needed
        if prefix is None:
            prefix = os.path.basename(path)

        bundles = set()
        failed = set()

        with self.__bundles_lock:
            # Use an ImpImporter per iteration because, in Python 3,
            # pkgutil.iter_modules() will use a _FileImporter on the second walk
            # in a package which will return nothing
            for name, is_package in pkgutil.ImpImporter(path).iter_modules():
                # Compute the full name of the module
                fullname = '.'.join((prefix, name)) if prefix else name

                try:
                    if visitor(fullname, is_package, path):
                        if is_package:
                            # Install the package
                            bundles.add(self.install_bundle(fullname, path))

                            # Visit the package
                            sub_path = os.path.join(path, name)
                            sub_bundles, sub_failed = self.install_visiting(
                                                                sub_path,
                                                                visitor,
                                                                fullname)
                            bundles.update(sub_bundles)
                            failed.update(sub_failed)

                        else:
                            # Install the bundle
                            bundles.add(self.install_bundle(fullname, path))

                except BundleException as ex:
                    # Error loading the module
                    _logger.warning("Error visiting %s: %s", fullname, ex)

                    # Try the next module
                    failed.add(fullname)
                    continue

        return bundles, failed


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
        classes = []
        for svc_clazz in clazz:

            if inspect.isclass(svc_clazz):
                # Keep the type name
                svc_clazz = svc_clazz.__name__

            if not svc_clazz or not is_string(svc_clazz):
                # Invalid class name
                raise BundleException("Invalid class name: {0}" \
                                      .format(svc_clazz))

            # Class OK
            classes.append(svc_clazz)

        # Make the service registration
        registration = self._registry.register(bundle, classes, properties,
                                               service)

        # Update the bundle registration information
        bundle._registered_service(registration)

        if send_event:
            # Call the listeners
            event = ServiceEvent(ServiceEvent.REGISTERED,
                                 registration.get_reference())
            self._dispatcher.fire_service_event(event)

        return registration


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

        # Reset the stop event
        self._fw_stop_event.clear()

        # Starting...
        self._state = Bundle.STARTING
        self._dispatcher.fire_bundle_event(BundleEvent(BundleEvent.STARTING,
                                                       self))

        # Start all registered bundles (use a copy, just in case...)
        for bundle in self.__bundles.copy().values():
            try:
                bundle.start()

            except FrameworkException as ex:
                # Important error
                _logger.exception("Important error starting bundle: %s", bundle)
                if ex.needs_stop:
                    # Stop the framework (has to be in active state)
                    self._state = Bundle.ACTIVE
                    self.stop()
                    return False

            except BundleException:
                # A bundle failed to start : just log
                _logger.exception("Error starting bundle: %s", bundle)

        # Bundle is now active
        self._state = Bundle.ACTIVE
        return True


    @SynchronizedClassMethod('_lock')
    def stop(self, force=False):
        """
        Stops the framework

        :return: True if the framework stopped, False it wasn't running
        """
        if self._state != Bundle.ACTIVE:
            # Invalid state
            return False

        # Stopping...
        self._state = Bundle.STOPPING
        self._dispatcher.fire_bundle_event(BundleEvent(BundleEvent.STOPPING,
                                                       self))

        # Notify listeners that the bundle is stopping
        self._dispatcher.fire_framework_stopping()

        bid = self.__next_bundle_id - 1
        while bid > 0:
            bundle = self.__bundles.get(bid, None)
            bid -= 1

            if bundle is None or bundle.get_state() != Bundle.ACTIVE:
                # Ignore inactive bundle
                continue

            try:
                bundle.stop()

            except Exception as ex:
                # Just log exceptions
                _logger.exception("Error stopping bundle %s: %s",
                                  bundle.get_symbolic_name(), ex)

        # Framework is now stopped
        self._state = Bundle.RESOLVED
        self._dispatcher.fire_bundle_event(BundleEvent(BundleEvent.STOPPED,
                                                       self))

        # All bundles have been stopped, release "wait_for_stop"
        self._fw_stop_event.set()

        # Force the registry clean up
        self._registry.clear()

        return True


    def uninstall(self):
        """
        A framework can't be uninstalled

        :raise BundleException: This method must not be called
        """
        raise BundleException("A framework can't be uninstalled")


    def uninstall_bundle(self, bundle):
        """
        Ends the uninstallation of the given bundle (must be called by Bundle)

        :param bundle: The bundle to uninstall
        :raise BundleException: Invalid bundle
        """
        if bundle is None:
            # Do nothing
            return

        with self.__bundles_lock:
            # Stop the bundle first
            bundle.stop()

            bundle_id = bundle.get_bundle_id()
            if bundle_id not in self.__bundles:
                raise BundleException("Invalid bundle {0}".format(bundle))

            # Notify listeners
            self._dispatcher.fire_bundle_event(BundleEvent(
                                                       BundleEvent.UNINSTALLED,
                                                       bundle))

            # Remove it from the dictionary
            del self.__bundles[bundle_id]

            # Remove it from the system => avoid unintended behaviors and forces
            # a complete module reload if it is re-installed
            name = bundle.get_symbolic_name()
            if name in sys.modules:
                del sys.modules[name]


    def unregister_service(self, registration):
        """
        Unregisters the given service

        :param registration: A ServiceRegistration to the service to unregister
        :raise BundleException: Invalid reference
        """
        assert isinstance(registration, ServiceRegistration)

        # Get the Service Reference
        reference = registration.get_reference()

        # Remove the service from the registry
        svc_instance = self._registry.unregister(reference)

        # Keep a track of the unregistering reference
        self.__unregistering_services[reference] = svc_instance

        # Call the listeners
        event = ServiceEvent(ServiceEvent.UNREGISTERING, reference)
        self._dispatcher.fire_service_event(event)

        # Update the bundle registration information
        bundle = reference.get_bundle()
        bundle._unregistered_service(registration)

        # Remove the unregistering reference
        del self.__unregistering_services[reference]

        return True


    def update(self):
        """
        Stops and starts the framework, if the framework is active.

        :raise BundleException: Something wrong occurred while stopping or
                                starting the framework.
        """
        with self._lock:
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

        self._fw_stop_event.wait(timeout)

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
        return "BundleContext({0})".format(self.__bundle)


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
        return self.__framework._dispatcher.add_bundle_listener(listener)


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
        return self.__framework._dispatcher.add_framework_listener(listener)


    def add_service_listener(self, listener, ldap_filter=None,
                             specification=None):
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
        :param ldap_filter: Filter that must match the service properties
                            (optional, None to accept all services)
        :param specification: The specification that must provide the service
                              (optional, None to accept all services)
        :return: True if the listener has been successfully registered
        """
        return self.__framework._dispatcher.add_service_listener(listener,
                                                                 specification,
                                                                 ldap_filter)


    def get_all_service_references(self, clazz, ldap_filter=None):
        """
        Returns an array of ServiceReference objects.
        The returned array of ServiceReference objects contains services that
        were registered under the specified class and match the specified filter
        expression.

        :param clazz: Class implemented by the service
        :param ldap_filter: Service filter
        :return: The sorted list of all matching service references, or None
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

        elif type(bundle_id) is Bundle:
            # Got a bundle (compatibility with older install_bundle())
            bundle_id = bundle_id.get_bundle_id()

        return self.__framework.get_bundle_by_id(bundle_id)


    def get_bundles(self):
        """
        Returns the list of all installed bundles

        :return: the list of all installed bundles
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

        :param reference: A ServiceReference object
        :return: The service object itself
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
        return self.__framework.find_service_references(clazz, ldap_filter,
                                                        True)


    def get_service_references(self, clazz, ldap_filter=None):
        """
        Returns the service references for services that were registered under
        the specified class by this bundle and matching the given filter

        :param clazz: The class name with which the service was registered.
        :param ldap_filter: A filter on service properties
        :return: The list of references to the services registered by the
                 calling bundle and matching the filters.
        """
        refs = self.__framework.find_service_references(clazz, ldap_filter)
        for ref in refs:
            if ref.get_bundle() is not self.__bundle:
                refs.remove(ref)

        return refs


    def install_bundle(self, name, path=None):
        """
        Installs the bundle with the given name

        *Note:* Before Pelix 0.5.0, this method returned the ID of the installed
        bundle, instead of the Bundle object.

        **WARNING:** The behavior of the loading process is subject to changes,
        as it does not allow to safely run multiple frameworks in the same
        Python interpreter, as they might share global module values.

        :param name: The name of the bundle to install
        :param path: Preferred path to load the module
        :return: The installed Bundle object
        :raise BundleException: Something happened
        """
        return self.__framework.install_bundle(name, path)


    def install_package(self, path, recursive=False):
        """
        Installs all the modules found in the given package

        :param path: Path of the package (folder)
        :param recursive: If True, install the sub-packages too
        :return: A 2-tuple, with the list of installed bundles and the list
                 of failed modules names
        :raise ValueError: Invalid path
        """
        return self.__framework.install_package(path, recursive)


    def install_visiting(self, path, visitor):
        """
        Installs all the modules found in the given path if they are accepted
        by the visitor.

        The visitor must be a callable accepting 3 parameters:

           * fullname: The full name of the module
           * is_package: If True, the module is a package
           * module_path: The path to the module file

        :param path: Root search path
        :param visitor: The visiting callable
        :return: A 2-tuple, with the list of installed bundles and the list
                 of failed modules names
        :raise ValueError: Invalid path or visitor
        """
        return self.__framework.install_visiting(path, visitor)


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
        return self.__framework.register_service(self.__bundle, clazz,
                                                service, properties, send_event)


    def remove_bundle_listener(self, listener):
        """
        Unregisters a bundle listener

        :param listener: The bundle listener
        :return: True if the listener has been unregistered
        """
        return self.__framework._dispatcher.remove_bundle_listener(listener)


    def remove_framework_stop_listener(self, listener):
        """
        Unregisters a framework stop listener

        :param listener: The framework stop listener
        :return: True if the listener has been unregistered
        """
        return self.__framework._dispatcher.remove_framework_listener(listener)


    def remove_service_listener(self, listener):
        """
        Unregisters a service listener

        :param listener: The service listener
        :return: True if the listener has been unregistered
        """
        return self.__framework._dispatcher.remove_service_listener(listener)


    def unget_service(self, reference):
        """
        Disables a reference to the service

        :return: True if the bundle was using this reference, else False
        """
        # Lose the dependency
        return self.__framework._registry.unget_service(self.__bundle,
                                                        reference)

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
    def is_framework_running(cls, framework=None):
        """
        Tests if the given framework has been constructed and not deleted.
        If *framework* is None, then the methods returns if at least one
        framework is running.

        :param framework: The framework instance to be tested
        :return: True if the framework is running
        """
        if framework is None:
            return cls.__singleton is not None

        else:
            return cls.__singleton == framework


    @classmethod
    def delete_framework(cls, framework):
        """
        Removes the framework singleton

        :return: True on success, else False
        """
        if cls.__singleton is framework:
            # Stop the framework
            try:
                framework.stop()

            except:
                _logger.exception("Error stopping the framework")

            # Uninstall its bundles
            bundles = framework.get_bundles()
            for bundle in bundles:
                try:
                    bundle.uninstall()
                except:
                    _logger.exception("Error uninstalling bundle %s", \
                                      bundle.get_symbolic_name())

            # Clear the event dispatcher
            framework._dispatcher.clear()

            # Clear the singleton
            cls.__singleton = None
            return True

        return False

# ------------------------------------------------------------------------------

def create_framework(bundles, properties=None,
                     auto_start=False, wait_for_stop=False, auto_delete=False):
    """
    Creates a Pelix framework, installs the given bundles and returns its
    instance reference.
    If *auto_start* is True, the framework will be started once all bundles
    will have been installed
    If *wait_for_stop* is True, the method will return only when the framework
    will have stopped. This requires *auto_start* to be True.
    If *auto_delete* is True, the framework will be deleted once it has stopped,
    and the method will return None.
    This requires *wait_for_stop* and *auto_start* to be True.

    :param bundles: Bundles to initially install (shouldn't be empty if
                    *wait_for_stop* is True)
    :param properties: Optional framework properties
    :param auto_start: If True, the framework will be started immediately
    :param wait_for_stop: If True, the method will return only when the
                          framework will have stopped
    :param auto_delete: If True, deletes the framework once it stopped.
    :return: The framework instance
    :raise ValueError: Only one framework can run at a time
    """
    # Test if a framework already exists
    if FrameworkFactory.is_framework_running(None):
        raise ValueError('A framework is already running')

    # Create the framework
    framework = FrameworkFactory.get_framework(properties)

    # Install bundles
    context = framework.get_bundle_context()
    for bundle in bundles:
        context.install_bundle(bundle)

    if auto_start:
        # Automatically start the framework
        framework.start()

        if wait_for_stop:
            # Wait for the framework to stop
            try:
                framework.wait_for_stop(None)

            except KeyboardInterrupt:
                # Stop keyboard interruptions
                if framework.get_state() == Bundle.ACTIVE:
                    framework.stop()

            if auto_delete:
                # Delete the framework
                FrameworkFactory.delete_framework(framework)
                framework = None

    return framework
