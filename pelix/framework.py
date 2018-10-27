#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Core module for Pelix.

Pelix is a Python framework that aims to act as OSGi as much as possible

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

# Standard library
import collections
import importlib
import inspect
import logging
import os
import sys
import threading
import uuid

# Standard typing module should be optional
try:
    # pylint: disable=W0611
    from typing import Any, List, Optional, Set, Union
    import types
except ImportError:
    pass

# Pelix beans and constants
from pelix.constants import (
    ACTIVATOR,
    ACTIVATOR_LEGACY,
    FRAMEWORK_UID,
    OSGI_FRAMEWORK_UUID,
    BundleException,
    FrameworkException,
)
from pelix.internals.events import BundleEvent, ServiceEvent

# pylint: disable=W0611
from pelix.internals.registry import (
    EventDispatcher,
    ServiceRegistry,
    ServiceReference,
    ServiceRegistration,
)

# Pelix utility modules
from pelix.utilities import is_string


if hasattr(importlib, "reload"):
    # This method has been added in Python 3.4 and deprecates imp.reload()
    def reload_module(module_):
        """
        Reloads a module using ``importlib.reload()`` when available

        :param module_: The module to update
        :return: The new version of the module
        :raise ImportError: Error looking for file
        :raise SyntaxError: Syntax error in imported module
        """
        return importlib.reload(module_)


else:
    # Before Python 3.4
    import imp

    def reload_module(module_):
        """
        Reloads a module using ``imp.reload()`` as fallback

        :param module_: The module to update
        :return: The new version of the module
        :raise ImportError: Error looking for file
        :raise SyntaxError: Syntax error in imported module
        """
        return imp.reload(module_)


def walk_modules(path):
    """
    Code from ``pkgutil.ImpImporter.iter_modules()``: walks through a folder
    and yields all loadable packages and modules.

    :param path: Path where to look for modules
    :return: Generator to walk through found packages and modules
    """
    if path is None or not os.path.isdir(path):
        return

    yielded = set()
    try:
        file_names = os.listdir(path)
    except OSError:
        # ignore unreadable directories like import does
        file_names = []

    # handle packages before same-named modules
    file_names.sort()

    for filename in file_names:
        modname = inspect.getmodulename(filename)
        if modname == "__init__" or modname in yielded:
            continue

        file_path = os.path.join(path, filename)
        is_package = False

        if not modname and os.path.isdir(file_path) and "." not in filename:
            modname = filename
            try:
                dir_contents = os.listdir(file_path)
            except OSError:
                # ignore unreadable directories like import does
                dir_contents = []

            for sub_filename in dir_contents:
                sub_name = inspect.getmodulename(sub_filename)
                if sub_name == "__init__":
                    is_package = True
                    break
            else:
                # not a package
                continue

        if modname and "." not in modname:
            yielded.add(modname)
            yield modname, is_package


# ------------------------------------------------------------------------------


# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Prepare the module logger
_logger = logging.getLogger("pelix.main")

# ------------------------------------------------------------------------------


class Bundle(object):
    # pylint: disable=W0212
    """
    Represents a "bundle" in Pelix
    """

    __slots__ = (
        "_lock",
        "__context",
        "__id",
        "__module",
        "__name",
        "__framework",
        "_state",
        "__registered_services",
        "__registration_lock",
    )

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

    def __init__(self, framework, bundle_id, name, module_):
        # type: (Framework, int, str, types.ModuleType) -> None
        """
        Sets up the bundle descriptor

        :param framework: The host framework
        :param bundle_id: The ID of the bundle in the host framework
        :param name: The bundle symbolic name
        :param module_: The bundle module
        """
        # A re-entrant lock for synchronization
        self._lock = threading.RLock()

        # Bundle
        self.__context = BundleContext(framework, self)
        self.__id = bundle_id
        self.__module = module_
        self.__name = name

        self.__framework = framework
        self._state = Bundle.RESOLVED

        # Registered services
        self.__registered_services = set()  # type: Set[ServiceRegistration]
        self.__registration_lock = threading.Lock()

    def __str__(self):
        """
        String representation
        """
        return "Bundle(ID={0}, Name={1})".format(self.__id, self.__name)

    def __get_activator_method(self, method_name):
        """
        Retrieves the requested method of the activator, or returns None

        :param method_name: A method name
        :return: A method, or None
        """
        # Get the activator
        activator = getattr(self.__module, ACTIVATOR, None)
        if activator is None:
            # Get the old activator
            activator = getattr(self.__module, ACTIVATOR_LEGACY, None)
            if activator is not None:
                # Old activator found: print a deprecation warning
                _logger.warning(
                    "Bundle %s uses the deprecated '%s' to declare"
                    " its activator. Use @BundleActivator instead.",
                    self.__name,
                    ACTIVATOR_LEGACY,
                )
        return getattr(activator, method_name, None)

    def _fire_bundle_event(self, kind):
        # type: (int) -> None
        """
        Fires a bundle event of the given kind

        :param kind: Kind of event
        """
        self.__framework._dispatcher.fire_bundle_event(BundleEvent(kind, self))

    def _registered_service(self, registration):
        # type: (ServiceRegistration) -> None
        """
        Bundle is notified by the framework that a service has been registered
        in the name of this bundle.

        :param registration: The service registration object
        """
        with self.__registration_lock:
            self.__registered_services.add(registration)

    def _unregistered_service(self, registration):
        # type: (ServiceRegistration) -> None
        """
        Bundle is notified by the framework that a service has been
        unregistered in the name of this bundle.

        :param registration: The service registration object
        """
        with self.__registration_lock:
            self.__registered_services.discard(registration)

    def get_bundle_context(self):
        # type: () -> BundleContext
        """
        Retrieves the bundle context

        :return: The bundle context
        """
        return self.__context

    def get_bundle_id(self):
        # type: () -> int
        """
        Retrieves the bundle ID

        :return: The bundle ID
        """
        return self.__id

    def get_location(self):
        # type: () -> str
        """
        Retrieves the location of this module

        :return: The location of the Pelix module, or an empty string
        """
        return getattr(self.__module, "__file__", "")

    def get_module(self):

        # type: () -> types.ModuleType
        """
        Retrieves the Python module corresponding to the bundle

        :return: The Python module
        """
        return self.__module

    def get_registered_services(self):
        # type: () -> List[ServiceReference]
        """
        Returns this bundle's ServiceReference list for all services it has
        registered or an empty list

        The list is valid at the time of the call to this method, however, as
        the Framework is a very dynamic environment, services can be modified
        or unregistered at any time.

        :return: An array of ServiceReference objects
        :raise BundleException: If the bundle has been uninstalled
        """
        if self._state == Bundle.UNINSTALLED:
            raise BundleException(
                "Can't call 'get_registered_services' on an "
                "uninstalled bundle"
            )
        return self.__framework._registry.get_bundle_registered_services(self)

    def get_services_in_use(self):
        # type: () -> List[ServiceReference]
        """
        Returns this bundle's ServiceReference list for all services it is
        using or an empty list.
        A bundle is considered to be using a service if its use count for that
        service is greater than zero.

        The list is valid at the time of the call to this method, however, as
        the Framework is a very dynamic environment, services can be modified
        or unregistered at any time.

        :return: An array of ServiceReference objects
        :raise BundleException: If the bundle has been uninstalled
        """
        if self._state == Bundle.UNINSTALLED:
            raise BundleException(
                "Can't call 'get_services_in_use' on an uninstalled bundle"
            )
        return self.__framework._registry.get_bundle_imported_services(self)

    def get_state(self):
        # type: () -> int
        """
        Retrieves the bundle state

        :return: The bundle state
        """
        return self._state

    def get_symbolic_name(self):
        # type: () -> str
        """
        Retrieves the bundle symbolic name (its Python module name)

        :return: The bundle symbolic name
        """
        return self.__name

    def get_version(self):
        # type: () -> str
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
            raise BundleException(
                "Framework must be started before its bundles"
            )

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
            starter = self.__get_activator_method("start")
            if starter is not None:
                try:
                    # Call the start method
                    starter(self.__context)
                except (FrameworkException, BundleException):
                    # Restore previous state
                    self._state = previous_state

                    # Re-raise directly Pelix exceptions
                    _logger.exception(
                        "Pelix error raised by %s while starting", self.__name
                    )
                    raise
                except Exception as ex:
                    # Restore previous state
                    self._state = previous_state

                    # Raise the error
                    _logger.exception(
                        "Error raised by %s while starting", self.__name
                    )
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

        exception = None
        with self._lock:
            # Store the bundle current state
            previous_state = self._state

            # Stopping...
            self._state = Bundle.STOPPING
            self._fire_bundle_event(BundleEvent.STOPPING)

            # Call the activator, if any
            stopper = self.__get_activator_method("stop")
            if stopper is not None:
                try:
                    # Call the start method
                    stopper(self.__context)
                except (FrameworkException, BundleException) as ex:
                    # Restore previous state
                    self._state = previous_state

                    # Re-raise directly Pelix exceptions
                    _logger.exception(
                        "Pelix error raised by %s while stopping", self.__name
                    )
                    exception = ex
                except Exception as ex:
                    _logger.exception(
                        "Error raised by %s while stopping", self.__name
                    )
                    # Store the exception (raised after service clean up)
                    exception = BundleException(ex)

            # Hide remaining services
            self.__framework._hide_bundle_services(self)

            # Intermediate bundle event : activator should have cleaned up
            # everything, but some element could stay (iPOPO components, ...)
            self._fire_bundle_event(BundleEvent.STOPPING_PRECLEAN)

            # Remove remaining services (the hard way)
            self.__unregister_services()

            # Cleanup service usages
            self.__framework._unget_used_services(self)

            # Bundle is now stopped and all its services have been unregistered
            self._state = Bundle.RESOLVED
            self._fire_bundle_event(BundleEvent.STOPPED)

        # Raise the exception, if any
        # pylint: disable=E0702
        # Pylint seems to miss the "is not None" check below
        if exception is not None:
            raise exception

    def __unregister_services(self):
        """
        Unregisters all bundle services
        """
        # Copy the services list, as it will be modified during the process
        with self.__registration_lock:
            registered_services = self.__registered_services.copy()

        for registration in registered_services:
            try:
                registration.unregister()
            except BundleException:
                # Ignore errors at this level
                pass

        if self.__registered_services:
            _logger.warning("Not all services have been unregistered...")

        with self.__registration_lock:
            # Clear the list, just to be clean
            self.__registered_services.clear()

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

    def update(self):
        """
        Updates the bundle
        """
        with self._lock:
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
            module_stat = None
            module_file = getattr(self.__module, "__file__", None)
            if module_file is not None and os.path.isfile(module_file):
                try:
                    module_stat = os.stat(module_file)

                    # Change modification time to bypass weak time resolution
                    # of the underlying file system
                    os.utime(
                        module_file,
                        (module_stat.st_atime, module_stat.st_mtime + 1),
                    )
                except OSError:
                    # Can't touch the file
                    _logger.warning(
                        "Failed to update the modification time of '%s'. "
                        "The bundle update might not reflect the latest "
                        "changes.",
                        module_file,
                    )

            # Clean up the module constants (otherwise kept by reload)
            # Keep special members (__name__, __file__, ...)
            old_content = self.__module.__dict__.copy()
            for name in list(self.__module.__dict__):
                if not (name.startswith("__") and name.endswith("__")):
                    del self.__module.__dict__[name]

            try:
                # Reload the module
                reload_module(self.__module)
            except (ImportError, SyntaxError) as ex:
                # Exception raised if the file is unreadable
                _logger.exception("Error updating %s: %s", self.__name, ex)

                # Reset module content
                self.__module.__dict__.clear()
                self.__module.__dict__.update(old_content)

            if module_stat is not None:
                try:
                    # Reset times
                    os.utime(
                        module_file,
                        (module_stat.st_atime, module_stat.st_mtime),
                    )
                except OSError:
                    # Shouldn't occur, since we succeeded before the update
                    _logger.debug(
                        "Failed to reset the modification time of '%s'",
                        module_file,
                    )

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
    # pylint: disable=W0212
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
        Bundle.__init__(
            self, self, 0, self.get_symbolic_name(), sys.modules[__name__]
        )

        # Framework properties
        if not isinstance(properties, dict):
            self.__properties = {}
        else:
            # Use a copy of the properties, to avoid external changes
            self.__properties = properties.copy()

        # Generate and set a framework instance UUID, if needed
        framework_uid = self.__properties.get(FRAMEWORK_UID)
        if not framework_uid:
            framework_uid = str(uuid.uuid4())
        # Normalize the UID: it must be a string
        self.__properties[FRAMEWORK_UID] = str(framework_uid)
        # Also normalize the OSGI_FRAMEWORK_UID: it must be a string
        self.__properties[OSGI_FRAMEWORK_UUID] = str(framework_uid)

        # Properties lock
        self.__properties_lock = threading.Lock()

        # Bundles (start at 1, as 0 is reserved for the framework itself)
        self.__next_bundle_id = 1

        # Bundle ID -> Bundle object
        self.__bundles = {}

        # Bundles lock
        self.__bundles_lock = threading.RLock()

        # Service registry
        self._registry = ServiceRegistry(self)
        self.__unregistering_services = {}

        # Event dispatcher
        self._dispatcher = EventDispatcher(self._registry)

        # The wait_for_stop event (initially stopped)
        self._fw_stop_event = threading.Event()
        self._fw_stop_event.set()

    def add_property(self, name, value):
        # type: (str, object) -> bool
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

    def find_service_references(
        self, clazz=None, ldap_filter=None, only_one=False
    ):
        # type: (Optional[str], Optional[str], bool) -> Optional[List[ServiceReference]]
        """
        Finds all services references matching the given filter.

        :param clazz: Class implemented by the service
        :param ldap_filter: Service filter
        :param only_one: Return the first matching service reference only
        :return: A list of found reference, or None
        :raise BundleException: An error occurred looking for service
                                references
        """
        return self._registry.find_service_references(
            clazz, ldap_filter, only_one
        )

    def get_bundle_by_id(self, bundle_id):
        # type: (int) -> Union[Bundle, Framework]
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
        # type: (str) -> Optional[Bundle]
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
        # type: () -> List[Bundle]
        """
        Returns the list of all installed bundles

        :return: the list of all installed bundles
        """
        with self.__bundles_lock:
            return [
                self.__bundles[bundle_id]
                for bundle_id in sorted(self.__bundles.keys())
            ]

    def get_properties(self):
        # type: () -> dict
        """
        Retrieves a copy of the stored framework properties.
        """
        with self.__properties_lock:
            return self.__properties.copy()

    def get_property(self, name):
        # type: (str) -> object
        """
        Retrieves a framework or system property. As framework properties don't
        change while it's running, this method don't need to be protected.

        :param name: The property name
        """
        with self.__properties_lock:
            return self.__properties.get(name, os.getenv(name))

    def get_property_keys(self):
        # type: () -> tuple
        """
        Returns an array of the keys in the properties of the service

        :return: An array of property keys.
        """
        with self.__properties_lock:
            return tuple(self.__properties.keys())

    def get_service(self, bundle, reference):
        # type: (Bundle, ServiceReference) -> Any
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
        elif not isinstance(reference, ServiceReference):
            raise TypeError("Second argument must be a ServiceReference object")

        try:
            # Unregistering service, just give it
            return self.__unregistering_services[reference]
        except KeyError:
            return self._registry.get_service(bundle, reference)

    def _get_service_objects(self, bundle, reference):
        # type: (Bundle, ServiceReference) -> ServiceObjects
        """
        Returns the ServiceObjects object for the service referenced by the
        specified ServiceReference object.

        :param bundle: The bundle requiring the service
        :param reference: Reference to a prototype service factory
        :return: An intermediate object to get more instances of a service
        """
        return ServiceObjects(self._registry, bundle, reference)

    def get_symbolic_name(self):
        # type: () -> str
        """
        Retrieves the framework symbolic name

        :return: Always "pelix.framework"
        """
        return "pelix.framework"

    def install_bundle(self, name, path=None):
        # type: (str, str) -> Bundle
        """
        Installs the bundle with the given name

        *Note:* Before Pelix 0.5.0, this method returned the ID of the
        installed bundle, instead of the Bundle object.

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
                    _logger.debug("Already installed bundle: %s", name)
                    return bundle

            # Load the module
            try:
                if path:
                    # Use the given path in priority
                    sys.path.insert(0, path)

                try:
                    # The module has already been loaded
                    module_ = sys.modules[name]
                except KeyError:
                    # Load the module
                    #  __import__(name) -> package level
                    # import_module -> module level
                    module_ = importlib.import_module(name)
            except (ImportError, IOError) as ex:
                # Error importing the module
                raise BundleException(
                    "Error installing bundle {0}: {1}".format(name, ex)
                )
            finally:
                if path:
                    # Clean up the path. The loaded module(s) might
                    # have changed the path content, so do not use an
                    # index
                    sys.path.remove(path)

            # Add the module to sys.modules, just to be sure
            sys.modules[name] = module_

            # Compute the bundle ID
            bundle_id = self.__next_bundle_id

            # Prepare the bundle object and its context
            bundle = Bundle(self, bundle_id, name, module_)

            # Store the bundle
            self.__bundles[bundle_id] = bundle

            # Update the bundle ID counter
            self.__next_bundle_id += 1

        # Fire the bundle installed event
        event = BundleEvent(BundleEvent.INSTALLED, bundle)
        self._dispatcher.fire_bundle_event(event)
        return bundle

    def install_package(self, path, recursive=False, prefix=None):
        # type: (str, bool, str) -> tuple
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
            raise ValueError("Nonexistent path: {0}".format(path))

        # Create a simple visitor
        def visitor(fullname, is_package, module_path):
            # pylint: disable=W0613
            """
            Package visitor: accepts everything in recursive mode,
            else avoids packages
            """
            return recursive or not is_package

        # Set up the prefix if needed
        if prefix is None:
            prefix = os.path.basename(path)

        bundles = set()  # type: Set[Bundle]
        failed = set()  # type: Set[str]

        with self.__bundles_lock:
            try:
                # Install the package first, resolved from the parent directory
                bundles.add(self.install_bundle(prefix, os.path.dirname(path)))

                # Visit the package
                visited, sub_failed = self.install_visiting(
                    path, visitor, prefix
                )

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
            # Walk through the folder to find modules
            for name, is_package in walk_modules(path):
                # Ignore '__main__' modules
                if name == "__main__":
                    continue

                # Compute the full name of the module
                fullname = ".".join((prefix, name)) if prefix else name
                try:
                    if visitor(fullname, is_package, path):
                        if is_package:
                            # Install the package
                            bundles.add(self.install_bundle(fullname, path))

                            # Visit the package
                            sub_path = os.path.join(path, name)
                            sub_bundles, sub_failed = self.install_visiting(
                                sub_path, visitor, fullname
                            )
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

    def register_service(
        self,
        bundle,
        clazz,
        service,
        properties,
        send_event,
        factory=False,
        prototype=False,
    ):
        # type: (Bundle, Union[List[Any], type, str], object, dict, bool, bool, bool) -> ServiceRegistration
        """
        Registers a service and calls the listeners

        :param bundle: The bundle registering the service
        :param clazz: Name(s) of the interface(s) implemented by service
        :param service: The service to register
        :param properties: Service properties
        :param send_event: If not, doesn't trigger a service registered event
        :param factory: If True, the given service is a service factory
        :param prototype: If True, the given service is a prototype service
                          factory (the factory argument is considered True)
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
        if not isinstance(clazz, (list, tuple)):
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
                raise BundleException(
                    "Invalid class name: {0}".format(svc_clazz)
                )

            # Class OK
            classes.append(svc_clazz)

        # Make the service registration
        registration = self._registry.register(
            bundle, classes, properties, service, factory, prototype
        )

        # Update the bundle registration information
        bundle._registered_service(registration)

        if send_event:
            # Call the listeners
            event = ServiceEvent(
                ServiceEvent.REGISTERED, registration.get_reference()
            )
            self._dispatcher.fire_service_event(event)

        return registration

    def start(self):
        # type: () -> bool
        """
        Starts the framework

        :return: True if the bundle has been started, False if it was already
                 running
        :raise BundleException: A bundle failed to start
        """
        with self._lock:
            if self._state in (Bundle.STARTING, Bundle.ACTIVE):
                # Already started framework
                return False

            # Reset the stop event
            self._fw_stop_event.clear()

            # Starting...
            self._state = Bundle.STARTING
            self._dispatcher.fire_bundle_event(
                BundleEvent(BundleEvent.STARTING, self)
            )

            # Start all registered bundles (use a copy, just in case...)
            for bundle in self.__bundles.copy().values():
                try:
                    bundle.start()
                except FrameworkException as ex:
                    # Important error
                    _logger.exception(
                        "Important error starting bundle: %s", bundle
                    )
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

    def stop(self):
        # type: () -> bool
        """
        Stops the framework

        :return: True if the framework stopped, False it wasn't running
        """
        with self._lock:
            if self._state != Bundle.ACTIVE:
                # Invalid state
                return False

            # Hide all services (they will be deleted by bundle.stop())
            for bundle in self.__bundles.values():
                self._registry.hide_bundle_services(bundle)

            # Stopping...
            self._state = Bundle.STOPPING
            self._dispatcher.fire_bundle_event(
                BundleEvent(BundleEvent.STOPPING, self)
            )

            # Notify listeners that the bundle is stopping
            self._dispatcher.fire_framework_stopping()

            bid = self.__next_bundle_id - 1
            while bid > 0:
                bundle = self.__bundles.get(bid)
                bid -= 1

                if bundle is None or bundle.get_state() != Bundle.ACTIVE:
                    # Ignore inactive bundle
                    continue

                try:
                    bundle.stop()
                except Exception as ex:
                    # Just log exceptions
                    _logger.exception(
                        "Error stopping bundle %s: %s",
                        bundle.get_symbolic_name(),
                        ex,
                    )

            # Framework is now stopped
            self._state = Bundle.RESOLVED
            self._dispatcher.fire_bundle_event(
                BundleEvent(BundleEvent.STOPPED, self)
            )

            # All bundles have been stopped, release "wait_for_stop"
            self._fw_stop_event.set()

            # Force the registry clean up
            self._registry.clear()
            return True

    def delete(self, force=False):
        """
        Deletes the current framework

        :param force: If True, stops the framework before deleting it
        :return: True if the framework has been delete, False if is couldn't
        """
        if not force and self._state not in (
            Bundle.INSTALLED,
            Bundle.RESOLVED,
            Bundle.STOPPING,
        ):
            _logger.warning("Trying to delete an active framework")
            return False

        return FrameworkFactory.delete_framework(self)

    def uninstall(self):
        """
        A framework can't be uninstalled

        :raise BundleException: This method must not be called
        """
        raise BundleException("A framework can't be uninstalled")

    def uninstall_bundle(self, bundle):
        # type: (Bundle) -> None
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
            self._dispatcher.fire_bundle_event(
                BundleEvent(BundleEvent.UNINSTALLED, bundle)
            )

            # Remove it from the dictionary
            del self.__bundles[bundle_id]

            # Remove it from the system => avoid unintended behaviors and
            # forces a complete module reload if it is re-installed
            name = bundle.get_symbolic_name()
            try:
                del sys.modules[name]
            except KeyError:
                # Ignore
                pass

            try:
                # Clear reference in parent
                parent, basename = name.rsplit(".", 1)
                if parent:
                    delattr(sys.modules[parent], basename)
            except (KeyError, AttributeError, ValueError):
                # Ignore errors
                pass

    def unregister_service(self, registration):
        # type: (ServiceRegistration) -> bool
        """
        Unregisters the given service

        :param registration: A ServiceRegistration to the service to unregister
        :raise BundleException: Invalid reference
        """
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

    def _hide_bundle_services(self, bundle):
        # type: (Bundle) -> List[ServiceReference]
        """
        Hides the services of the given bundle in the service registry

        :param bundle: The bundle providing services
        :return: The references of the hidden services
        """
        return self._registry.hide_bundle_services(bundle)

    def _unget_used_services(self, bundle):
        # type: (Bundle) -> None
        """
        Cleans up all service usages of the given bundle

        :param bundle: Bundle to be cleaned up
        """
        self._registry.unget_used_services(bundle)

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
        # type: (Optional[int]) -> bool
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


class ServiceObjects(object):
    """
    Allows multiple service objects for a service to be obtained.
    """

    def __init__(self, registry, bundle, svc_ref):
        # type: (ServiceRegistry, Bundle, ServiceReference) -> None
        """
        :param bundle: Bundle requesting the service
        :param svc_ref: Reference to the requested service
        """
        self.__registry = registry
        self.__bundle = bundle
        self.__reference = svc_ref

    def get_service(self):
        # type: () -> Any
        """
        Returns a service object for the associated service.
        """
        return self.__registry.get_service(self.__bundle, self.__reference)

    def get_service_reference(self):
        # type: () -> ServiceReference
        """
        Returns the ServiceReference for the service associated with this
        object.

        :return: The ServiceReference to the service associated to this object
        """
        return self.__reference

    def unget_service(self, service):
        # type: (Any) -> bool
        """
        Releases a service object for the associated service.

        :param service: An instance of a service returned by ``get_service()``
        :return: True if the bundle usage has been removed
        """
        return self.__registry.unget_service(
            self.__bundle, self.__reference, service
        )


class BundleContext(object):
    # pylint: disable=W0212
    """
    The bundle context is the link between a bundle and the framework.
    It is unique for a bundle and is created by the framework once the bundle
    is installed.
    """

    def __init__(self, framework, bundle):
        # type: (Framework, Bundle) -> None
        """
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
        Registers a bundle listener, which will be notified each time a bundle
        is installed, started, stopped or updated.

        The listener must be a callable accepting a single parameter:\

           * **event** -- The description of the event
             (a :class:`~pelix.internals.events.BundleEvent` object).

        :param listener: The bundle listener to register
        :return: True if the listener has been registered, False if it already
                 was
        """
        return self.__framework._dispatcher.add_bundle_listener(listener)

    def add_framework_stop_listener(self, listener):
        """
        Registers a listener that will be called back right before the
        framework stops

        The framework listener must have a method with the following prototype::

           def framework_stopping(self):
               '''
               No parameter given
               '''
               # ...

        :param listener: The framework stop listener
        :return: True if the listener has been registered
        """
        return self.__framework._dispatcher.add_framework_listener(listener)

    def add_service_listener(
        self, listener, ldap_filter=None, specification=None
    ):
        """
        Registers a service listener

        The service listener must have a method with the following prototype::

           def service_changed(self, event):
               '''
               Called by Pelix when some service properties changes

               event: A ServiceEvent object
               '''
               # ...

        :param bundle_context:  This bundle context
        :param listener: The listener to register
        :param ldap_filter: Filter that must match the service properties
                            (optional, None to accept all services)
        :param specification: The specification that must provide the service
                              (optional, None to accept all services)
        :return: True if the listener has been successfully registered
        """
        return self.__framework._dispatcher.add_service_listener(
            self, listener, specification, ldap_filter
        )

    def get_all_service_references(self, clazz, ldap_filter=None):
        """
        Returns an array of ServiceReference objects.
        The returned array of ServiceReference objects contains services that
        were registered under the specified class and match the specified
        filter expression.

        :param clazz: Class implemented by the service
        :param ldap_filter: Service filter
        :return: The sorted list of all matching service references, or None
        """
        return self.__framework.find_service_references(clazz, ldap_filter)

    def get_bundle(self, bundle_id=None):
        # type: (Union[Bundle, int]) -> Bundle
        """
        Retrieves the :class:`~pelix.framework.Bundle` object for the bundle
        matching the given ID (int). If no ID is given (None), the bundle
        associated to this context is returned.

        :param bundle_id: A bundle ID (optional)
        :return: The requested :class:`~pelix.framework.Bundle` object
        :raise BundleException: The given ID doesn't exist or is invalid
        """
        if bundle_id is None:
            # Current bundle
            return self.__bundle
        elif isinstance(bundle_id, Bundle):
            # Got a bundle (compatibility with older install_bundle())
            bundle_id = bundle_id.get_bundle_id()

        return self.__framework.get_bundle_by_id(bundle_id)

    def get_bundles(self):
        # type: () -> List[Bundle]
        """
        Returns the list of all installed bundles

        :return: A list of :class:`~pelix.framework.Bundle` objects
        """
        return self.__framework.get_bundles()

    def get_framework(self):
        # type: () -> Framework
        """
        Returns the :class:`~pelix.FRAMEWORK.Framework` that created this
        bundle context

        :return: The :class:`~pelix.framework.Framework` object
        """
        return self.__framework

    def get_property(self, name):
        # type: (str) -> object
        """
        Returns the value of a property of the framework, else returns the OS
        environment value.

        :param name: A property name
        """
        return self.__framework.get_property(name)

    def get_service(self, reference):
        # type: (ServiceReference) -> Any
        """
        Returns the service described with the given reference

        :param reference: A ServiceReference object
        :return: The service object itself
        """
        return self.__framework.get_service(self.__bundle, reference)

    def get_service_objects(self, reference):
        # type: (ServiceReference) -> ServiceObjects
        """
        Returns the ServiceObjects object for the service referenced by the
        specified ServiceReference object.

        :param reference: Reference to a prototype service factory
        :return: An intermediate object to get more instances of a service
        """
        return self.__framework._get_service_objects(self.__bundle, reference)

    def get_service_reference(self, clazz, ldap_filter=None):
        # type: (Optional[str], Optional[str]) -> Optional[ServiceReference]
        """
        Returns a ServiceReference object for a service that implements and
        was registered under the specified class

        :param clazz: The class name with which the service was registered.
        :param ldap_filter: A filter on service properties
        :return: A service reference, None if not found
        """
        result = self.__framework.find_service_references(
            clazz, ldap_filter, True
        )
        try:
            return result[0]
        except TypeError:
            return None

    def get_service_references(self, clazz, ldap_filter=None):
        # type: (Optional[str], Optional[str]) -> Optional[List[ServiceReference]]
        """
        Returns the service references for services that were registered under
        the specified class by this bundle and matching the given filter

        :param clazz: The class name with which the service was registered.
        :param ldap_filter: A filter on service properties
        :return: The list of references to the services registered by the
                 calling bundle and matching the filters.
        """
        refs = self.__framework.find_service_references(clazz, ldap_filter)
        if refs:
            for ref in refs:
                if ref.get_bundle() is not self.__bundle:
                    refs.remove(ref)

        return refs

    def install_bundle(self, name, path=None):
        # type: (str, str) -> Bundle
        """
        Installs the bundle (module) with the given name.

        If a path is given, it is inserted in first place in the Python loading
        path (``sys.path``). All modules loaded alongside this bundle, *i.e.*
        by this bundle or its dependencies, will be looked after in this path
        in priority.

        .. note::
            Before Pelix 0.5.0, this method returned the ID of the installed
            bundle, instead of the Bundle object.

        .. warning::
            The behavior of the loading process is subject to changes, as it
            does not allow to safely run multiple frameworks in the same Python
            interpreter, as they might share global module values.

        :param name: The name of the bundle to install
        :param path: Preferred path to load the module (optional)
        :return: The :class:`~pelix.framework.Bundle` object of the installed
                 bundle
        :raise BundleException: Error importing the module or one of its
                                dependencies
        """
        return self.__framework.install_bundle(name, path)

    def install_package(self, path, recursive=False):
        # type: (str, bool) -> tuple
        """
        Installs all the modules found in the given package (directory).
        It is a utility method working like
        :meth:`~pelix.framework.BundleContext.install_visiting`, with a visitor
        accepting every module found.

        :param path: Path of the package (folder)
        :param recursive: If True, installs the modules found in sub-directories
        :return: A 2-tuple, with the list of installed bundles
                 (:class:`~pelix.framework.Bundle`) and the list of the names
                 of the modules which import failed.
        :raise ValueError: The given path is invalid
        """
        return self.__framework.install_package(path, recursive)

    def install_visiting(self, path, visitor):
        """
        Looks for modules in the given path and installs those accepted by the
        given visitor.

        The visitor must be a callable accepting 3 parameters:\

           * **fullname** -- The full name of the module
           * **is_package** -- If True, the module is a package
           * **module_path** -- The path to the module file

        :param path: Root search path (folder)
        :param visitor: The visiting callable
        :return: A 2-tuple, with the list of installed bundles
                 (:class:`~pelix.framework.Bundle`) and the list of the names
                 of the modules which import failed.
        :raise ValueError: Invalid path or visitor
        """
        return self.__framework.install_visiting(path, visitor)

    def register_service(
        self,
        clazz,
        service,
        properties,
        send_event=True,
        factory=False,
        prototype=False,
    ):
        # type: (Union[List[Any], type, str], object, dict, bool, bool, bool) -> ServiceRegistration
        """
        Registers a service

        :param clazz: Class or Classes (list) implemented by this service
        :param service: The service instance
        :param properties: The services properties (dictionary)
        :param send_event: If not, doesn't trigger a service registered event
        :param factory: If True, the given service is a service factory
        :param prototype: If True, the given service is a prototype service
                          factory (the factory argument is considered True)
        :return: A ServiceRegistration object
        :raise BundleException: An error occurred while registering the service
        """
        return self.__framework.register_service(
            self.__bundle,
            clazz,
            service,
            properties,
            send_event,
            factory,
            prototype,
        )

    def remove_bundle_listener(self, listener):
        """
        Unregisters the given bundle listener

        :param listener: The bundle listener to remove
        :return: True if the listener has been unregistered,
                 False if it wasn't registered
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
        # type: (ServiceReference) -> bool
        """
        Disables a reference to the service

        :return: True if the bundle was using this reference, else False
        """
        # Lose the dependency
        return self.__framework._registry.unget_service(
            self.__bundle, reference
        )


# ------------------------------------------------------------------------------


class FrameworkFactory(object):
    """
    A framework factory
    """

    __singleton = None  # type: Framework
    """ The framework singleton """

    @classmethod
    def get_framework(cls, properties=None):
        # type: (Optional[dict]) -> Framework
        """
        If it doesn't exist yet, creates a framework with the given properties,
        else returns the current framework instance.

        :return: A Pelix instance
        """
        if cls.__singleton is None:
            # Normalize sys.path
            normalize_path()
            cls.__singleton = Framework(properties)

        return cls.__singleton

    @classmethod
    def is_framework_running(cls, framework=None):
        # type: (Optional[Framework]) -> bool
        """
        Tests if the given framework has been constructed and not deleted.
        If *framework* is None, then the methods returns if at least one
        framework is running.

        :param framework: The framework instance to be tested
        :return: True if the framework is running
        """
        if framework is None:
            return cls.__singleton is not None

        return cls.__singleton == framework

    @classmethod
    def delete_framework(cls, framework=None):
        # type: (Optional[Framework]) -> bool
        # pylint: disable=W0212
        """
        Removes the framework singleton

        :return: True on success, else False
        """
        if framework is None:
            framework = cls.__singleton

        if framework is cls.__singleton:
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
                    _logger.exception(
                        "Error uninstalling bundle %s",
                        bundle.get_symbolic_name(),
                    )

            # Clear the event dispatcher
            framework._dispatcher.clear()

            # Clear the singleton
            cls.__singleton = None
            return True

        return False


# ------------------------------------------------------------------------------


def create_framework(
    bundles,
    properties=None,
    auto_start=False,
    wait_for_stop=False,
    auto_delete=False,
):
    # type: (Union[list, tuple], dict, bool, bool, bool) -> Framework
    """
    Creates a Pelix framework, installs the given bundles and returns its
    instance reference.
    If *auto_start* is True, the framework will be started once all bundles
    will have been installed
    If *wait_for_stop* is True, the method will return only when the framework
    will have stopped. This requires *auto_start* to be True.
    If *auto_delete* is True, the framework will be deleted once it has
    stopped, and the method will return None.
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
        raise ValueError("A framework is already running")

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


def _package_exists(path):
    # type: (str) -> bool
    """
    Checks if the given Python path matches a valid file or a valid container
    file

    :param path: A Python path
    :return: True if the module or its container exists
    """
    while path:
        if os.path.exists(path):
            return True
        else:
            path = os.path.dirname(path)

    return False


def normalize_path():
    """
    Normalizes sys.path to avoid the use of relative folders
    """
    # Normalize Python paths
    whole_path = [
        os.path.abspath(path) for path in sys.path if os.path.exists(path)
    ]

    # Keep the "dynamic" current folder indicator and add the "static"
    # current path
    # Use an OrderedDict to have a faster lookup (path not in whole_set)
    whole_set = collections.OrderedDict((("", 1), (os.getcwd(), 1)))

    # Add original path entries
    for path in whole_path:
        if path not in whole_set:
            whole_set[path] = 1

    # Set the new content of sys.path (still ordered thanks to OrderedDict)
    sys.path = list(whole_set)

    # Normalize paths in loaded modules
    for module_ in sys.modules.values():
        try:
            module_.__path__ = [
                os.path.abspath(path)
                for path in module_.__path__
                if _package_exists(path)
            ]
        except AttributeError:
            # builtin modules don't have a __path__
            pass
        except ImportError:
            pass
