#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Core module for Pelix.

Pelix is a Python framework that aims to act as OSGi as much as possible

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

import collections
import importlib
import inspect
import logging
import os
import pathlib
import sys
import threading
import types
import uuid
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Generic,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from pelix.constants import (
    ACTIVATOR,
    ACTIVATOR_LEGACY,
    FRAMEWORK_UID,
    OBJECTCLASS,
    OSGI_FRAMEWORK_UUID,
    PELIX_SPECIFICATION_FIELD,
    BundleException,
    FrameworkException,
)
from pelix.internals.events import BundleEvent, ServiceEvent
from pelix.internals.registry import (
    BundleListener,
    EventDispatcher,
    FrameworkStoppingListener,
    ServiceListener,
    ServiceReference,
    ServiceRegistration,
    ServiceRegistry,
)
from pelix.ldapfilter import LDAPCriteria, LDAPFilter

# Generic type var
T = TypeVar("T")


def reload_module(module_: types.ModuleType) -> types.ModuleType:
    """
    Reloads a module using ``importlib.reload()`` when available

    :param module_: The module to update
    :return: The new version of the module
    :raise ImportError: Error looking for file
    :raise SyntaxError: Syntax error in imported module
    """
    return importlib.reload(module_)


def walk_modules(path: pathlib.Path) -> Generator[Tuple[str, bool], None, None]:
    """
    Code from ``pkgutil.ImpImporter.iter_modules()``: walks through a folder
    and yields all loadable packages and modules.

    :param path: Path where to look for modules
    :return: Generator to walk through found packages and modules
    """
    if path is None or not path.is_dir():
        return

    yielded: Set[str] = set()
    try:
        # Handle packages before same-named modules
        files = sorted(path.iterdir(), key=lambda p: (not p.is_dir, p.name))
    except OSError:
        # Ignore unreadable directories like import does
        return

    for file_path in files:
        mod_name = inspect.getmodulename(file_path.name)
        if mod_name == "__init__" or mod_name in yielded:
            # Ignore package marker and modules named as already-seen packages
            continue

        is_package = False

        if not mod_name and file_path.is_dir() and "." not in file_path.name:
            mod_name = file_path.name
            try:
                dir_contents = sorted(file_path.iterdir(), key=lambda p: (not p.is_dir, p.name))
            except OSError:
                # ignore unreadable directories like import does
                continue

            for sub_filename in dir_contents:
                sub_name = inspect.getmodulename(sub_filename.name)
                if sub_name == "__init__":
                    is_package = True
                    break
            else:
                # not a package
                continue

        if mod_name and "." not in mod_name:
            # Valid package or module name
            yielded.add(mod_name)
            yield mod_name, is_package


# ------------------------------------------------------------------------------


# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# Prepare the module logger
_logger = logging.getLogger("pelix.main")

# ------------------------------------------------------------------------------


def _get_class_spec(clazz: Type[Any]) -> Union[str, List[str]]:
    """
    Extract a specification from the given type
    """
    return getattr(clazz, PELIX_SPECIFICATION_FIELD, clazz.__name__)


class Bundle:
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

    def __init__(
        self,
        framework: "Framework",
        bundle_id: int,
        name: str,
        module_: types.ModuleType,
    ) -> None:
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
        self.__registered_services: Set[ServiceRegistration[Any]] = set()
        self.__registration_lock = threading.Lock()

    def __str__(self) -> str:
        """
        String representation
        """
        return f"Bundle(ID={self.__id}, Name={self.__name})"

    def __get_activator_method(self, method_name: str) -> Optional[Callable[["BundleContext"], None]]:
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

    def _fire_bundle_event(self, kind: int) -> None:
        """
        Fires a bundle event of the given kind

        :param kind: Kind of event
        """
        self.__framework._dispatcher.fire_bundle_event(BundleEvent(kind, self))

    def _registered_service(self, registration: ServiceRegistration[Any]) -> None:
        """
        Bundle is notified by the framework that a service has been registered
        in the name of this bundle.

        :param registration: The service registration object
        """
        with self.__registration_lock:
            self.__registered_services.add(registration)

    def _unregistered_service(self, registration: ServiceRegistration[Any]) -> None:
        """
        Bundle is notified by the framework that a service has been
        unregistered in the name of this bundle.

        :param registration: The service registration object
        """
        with self.__registration_lock:
            self.__registered_services.discard(registration)

    def get_bundle_context(self) -> "BundleContext":
        """
        Retrieves the bundle context

        :return: The bundle context
        """
        return self.__context

    def get_bundle_id(self) -> int:
        """
        Retrieves the bundle ID

        :return: The bundle ID
        """
        return self.__id

    def get_location(self) -> str:
        """
        Retrieves the location of this module

        :return: The location of the Pelix module, or an empty string
        """
        return getattr(self.__module, "__file__", "")

    def get_module(self) -> types.ModuleType:
        """
        Retrieves the Python module corresponding to the bundle

        :return: The Python module
        """
        return self.__module

    def get_registered_services(self) -> List[ServiceReference[Any]]:
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
            raise BundleException("Can't call 'get_registered_services' on an uninstalled bundle")
        return self.__framework._registry.get_bundle_registered_services(self)

    def get_services_in_use(self) -> List[ServiceReference[Any]]:
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
            raise BundleException("Can't call 'get_services_in_use' on an uninstalled bundle")
        return self.__framework._registry.get_bundle_imported_services(self)

    def get_state(self) -> int:
        """
        Retrieves the bundle state

        :return: The bundle state
        """
        return self._state

    def get_symbolic_name(self) -> str:
        """
        Retrieves the bundle symbolic name (its Python module name)

        :return: The bundle symbolic name
        """
        return self.__name

    def get_version(self) -> str:
        """
        Retrieves the bundle version, using the ``__version__`` or
        ``__version_info__`` attributes of its module.

        :return: The bundle version, "0.0.0" by default
        """
        # Get the version value
        version = cast(Optional[str], getattr(self.__module, "__version__", None))
        if version:
            return version

        # Convert the __version_info__ entry
        info = cast(Optional[Tuple[str, ...]], getattr(self.__module, "__version_info__", None))
        if info:
            return ".".join(str(part) for part in __version_info__)

        # No version
        return "0.0.0"

    def start(self) -> bool:
        """
        Starts the bundle. Does nothing if the bundle is already starting or
        active.

        :raise BundleException: The framework is not yet started or the bundle
                                activator failed.
        """
        if self.__framework._state not in (Bundle.STARTING, Bundle.ACTIVE):
            # Framework is not running
            raise BundleException("Framework must be started before its bundles")

        with self._lock:
            if self._state in (Bundle.ACTIVE, Bundle.STARTING):
                # Already started bundle, do nothing
                return False

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
                    _logger.exception("Pelix error raised by %s while starting", self.__name)
                    raise
                except Exception as ex:
                    # Restore previous state
                    self._state = previous_state

                    # Raise the error
                    _logger.exception("Error raised by %s while starting", self.__name)
                    raise BundleException(ex)

            # Bundle is now active
            self._state = Bundle.ACTIVE
            self._fire_bundle_event(BundleEvent.STARTED)
            return True

    def stop(self) -> bool:
        """
        Stops the bundle. Does nothing if the bundle is already stopped.

        :raise BundleException: The bundle activator failed.
        """
        if self._state != Bundle.ACTIVE:
            # Invalid state
            return False

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
                    _logger.exception("Pelix error raised by %s while stopping", self.__name)
                    exception = ex
                except Exception as ex:
                    _logger.exception("Error raised by %s while stopping", self.__name)
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

        return True

    def __unregister_services(self) -> None:
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

    def uninstall(self) -> None:
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

    def update(self) -> None:
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
            module_file = cast(Optional[str], getattr(self.__module, "__file__", None))
            module_path = pathlib.Path(module_file) if module_file else None
            if module_path is not None and module_path.is_file():
                try:
                    module_stat = module_path.stat()

                    # Change modification time to bypass weak time resolution
                    # of the underlying file system
                    os.utime(
                        str(module_path),
                        (module_stat.st_atime, module_stat.st_mtime + 1),
                    )
                except OSError:
                    # Can't touch the file
                    _logger.warning(
                        "Failed to update the modification time of '%s'. "
                        "The bundle update might not reflect the latest "
                        "changes.",
                        module_path,
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
                        str(module_path),
                        (module_stat.st_atime, module_stat.st_mtime),
                    )
                except OSError:
                    # Shouldn't occur, since we succeeded before the update
                    _logger.debug(
                        "Failed to reset the modification time of '%s'",
                        module_path,
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
    """
    The Pelix framework (main) class. It must be instantiated using
    FrameworkFactory
    """

    def __init__(self, properties: Optional[Dict[str, Any]] = None) -> None:
        """
        Sets up the framework.

        :param properties: The framework properties
        """
        # Framework bundle set up
        Bundle.__init__(self, self, 0, self.get_symbolic_name(), sys.modules[__name__])

        # Framework properties
        if not isinstance(properties, dict):
            self.__properties = {}
        else:
            # Use a copy of the properties, to avoid external changes
            self.__properties = properties.copy()

        # Generate and set a framework instance UUID, if needed
        framework_uid: str = str(self.__properties.get(FRAMEWORK_UID) or uuid.uuid4())
        # Normalize the UID: it must be a string
        self.__properties[FRAMEWORK_UID] = framework_uid
        # Also normalize the OSGI_FRAMEWORK_UID: it must be a string
        self.__properties[OSGI_FRAMEWORK_UUID] = framework_uid

        # Properties lock
        self.__properties_lock = threading.Lock()

        # Bundles (start at 1, as 0 is reserved for the framework itself)
        self.__next_bundle_id: int = 1

        # Bundle ID -> Bundle object
        self.__bundles: Dict[int, Bundle] = {}

        # Bundles lock
        self.__bundles_lock = threading.RLock()

        # Service registry
        self._registry = ServiceRegistry(self)
        self.__unregistering_services: Dict[ServiceReference[Any], Any] = {}

        # Event dispatcher
        self._dispatcher = EventDispatcher(self._registry)

        # The wait_for_stop event (initially stopped)
        self._fw_stop_event = threading.Event()
        self._fw_stop_event.set()

    def add_property(self, name: str, value: Any) -> bool:
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
        self,
        clazz: Union[None, str, Type[T]] = None,
        ldap_filter: Union[None, str, LDAPFilter, LDAPCriteria] = None,
        only_one: bool = False,
    ) -> Optional[List[ServiceReference[T]]]:
        """
        Finds all services references matching the given filter.

        :param clazz: Class implemented by the service
        :param ldap_filter: Service filter
        :param only_one: Return the first matching service reference only
        :return: A list of found reference, or None
        :raise BundleException: An error occurred looking for service
                                references
        """
        return self._registry.find_service_references(clazz, ldap_filter, only_one)

    def get_bundle_by_id(self, bundle_id: int) -> Union[Bundle, "Framework"]:
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
                raise BundleException(f"Invalid bundle ID {bundle_id}")

            return self.__bundles[bundle_id]

    def get_bundle_by_name(self, bundle_name: str) -> Optional[Bundle]:
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

    def get_bundles(self) -> List[Bundle]:
        """
        Returns the list of all installed bundles

        :return: the list of all installed bundles
        """
        with self.__bundles_lock:
            return [self.__bundles[bundle_id] for bundle_id in sorted(self.__bundles.keys())]

    def get_properties(self) -> Dict[str, Any]:
        """
        Retrieves a copy of the stored framework properties.
        """
        with self.__properties_lock:
            return self.__properties.copy()

    def get_property(self, name: str) -> Any:
        """
        Retrieves a framework or system property. As framework properties don't
        change while it's running, this method don't need to be protected.

        :param name: The property name
        """
        with self.__properties_lock:
            return self.__properties.get(name, os.getenv(name))

    def get_property_keys(self) -> Tuple[str, ...]:
        """
        Returns an array of the keys in the properties of the service

        :return: An array of property keys.
        """
        with self.__properties_lock:
            return tuple(self.__properties.keys())

    def get_service(self, bundle: Bundle, reference: ServiceReference[T]) -> T:
        """
        Retrieves the service corresponding to the given reference

        :param bundle: The bundle requiring the service
        :param reference: A service reference
        :return: The requested service
        :raise BundleException: The service could not be found
        :raise TypeError: The argument is not a ServiceReference object
        """
        if reference is None:
            raise ValueError("No service reference given")
        if not isinstance(bundle, Bundle):
            raise TypeError("First argument must be a Bundle object")
        if not isinstance(reference, ServiceReference):
            raise TypeError("Second argument must be a ServiceReference object")

        try:
            # Unregistering service, just give it
            return cast(T, self.__unregistering_services[reference])
        except KeyError:
            return self._registry.get_service(bundle, reference)

    def _get_service_objects(self, bundle: Bundle, reference: ServiceReference[T]) -> "ServiceObjects[T]":
        """
        Returns the ServiceObjects object for the service referenced by the
        specified ServiceReference object.

        :param bundle: The bundle requiring the service
        :param reference: Reference to a prototype service factory
        :return: An intermediate object to get more instances of a service
        """
        return ServiceObjects(self._registry, bundle, reference)

    def get_symbolic_name(self) -> str:
        """
        Retrieves the framework symbolic name

        :return: Always "pelix.framework"
        """
        return "pelix.framework"

    def install_bundle(self, name: str, path: Optional[Union[str, pathlib.Path]] = None) -> Bundle:
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
                    sys.path.insert(0, str(path))

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
                raise BundleException(f"Error installing bundle {name}: {ex}")
            finally:
                if path:
                    # Clean up the path. The loaded module(s) might
                    # have changed the path content, so do not use an
                    # index
                    sys.path.remove(str(path))

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

    def install_package(
        self,
        path: Union[str, pathlib.Path],
        recursive: bool = False,
        prefix: Optional[str] = None,
    ) -> Tuple[Set[Bundle], Set[str]]:
        """
        Installs all the modules found in the given package

        :param path: Path of the package (folder)
        :param recursive: If True, install the sub-packages too
        :param prefix: (**internal**) Prefix for all found modules
        :return: A 2-tuple, with the list of installed bundles and the list
                 of failed modules names
        :raise ValueError: Invalid path
        """
        if path and isinstance(path, str):
            path = pathlib.Path(path)

        if not isinstance(path, pathlib.Path):
            raise ValueError(f"Expected path to be string or pathlib.Path, got {type(path).__name__}")

        # Use an absolute path
        path = path.absolute()
        if not path.exists():
            raise ValueError(f"Nonexistent path: {path}")

        # Create a simple visitor
        def visitor(fullname: str, is_package: bool, module_path: str) -> bool:
            # pylint: disable=W0613
            """
            Package visitor: accepts everything in recursive mode,
            else avoids packages
            """
            return recursive or not is_package

        # Set up the prefix if needed
        if prefix is None:
            prefix = path.name

        bundles: Set[Bundle] = set()
        failed: Set[str] = set()

        with self.__bundles_lock:
            try:
                # Install the package first, resolved from the parent directory
                bundles.add(self.install_bundle(prefix, os.path.dirname(path)))

                # Visit the package
                visited, sub_failed = self.install_visiting(path, visitor, prefix)

                # Update the sets
                bundles.update(visited)
                failed.update(sub_failed)
            except BundleException as ex:
                # Error loading the module
                _logger.warning("Error loading package %s: %s", prefix, ex)
                failed.add(prefix)

        return bundles, failed

    def install_visiting(
        self,
        path: Union[str, pathlib.Path],
        visitor: Callable[[str, bool, str], bool],
        prefix: Optional[str] = None,
    ) -> Tuple[Set[Bundle], Set[str]]:
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
        :return: A 2-tuple, with the list of installed bundles and the list of failed modules names
        :raise ValueError: Invalid path or visitor
        """
        # Validate the path
        if path and isinstance(path, str):
            path = pathlib.Path(path)

        if not isinstance(path, pathlib.Path):
            raise ValueError(f"Expected path to be string or pathlib.Path, got {type(path).__name__}")

        # Validate the visitor
        if visitor is None:
            raise ValueError("No visitor method given")

        # Use an absolute path
        path = path.absolute()
        if not path.exists():
            raise ValueError(f"Inexistent path: {path}")

        # Set up the prefix if needed
        if prefix is None:
            prefix = path.name

        bundles: Set[Bundle] = set()
        failed: Set[str] = set()

        with self.__bundles_lock:
            # Walk through the folder to find modules
            for name, is_package in walk_modules(path):
                # Ignore '__main__' modules
                if name == "__main__":
                    continue

                # Compute the full name of the module
                fullname = ".".join((prefix, name)) if prefix else name
                try:
                    if visitor(fullname, is_package, path.name):
                        if is_package:
                            # Install the package
                            bundles.add(self.install_bundle(fullname, path))

                            # Visit the package
                            sub_path = os.path.join(path, name)
                            sub_bundles, sub_failed = self.install_visiting(sub_path, visitor, fullname)
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
        bundle: Bundle,
        clazz: Union[
            str,
            Type[T],
            Iterable[Union[str, Type[Any]]],
        ],
        service: T,
        properties: Optional[Dict[str, Any]],
        send_event: bool,
        factory: bool = False,
        prototype: bool = False,
    ) -> ServiceRegistration[T]:
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
        if not isinstance(clazz, (list, tuple, set)):
            # Make a list from the single class
            clazz = cast(Union[List[str], List[Type[T]]], [clazz])

        # Test the list content
        classes: List[str] = []
        for svc_clazz in clazz:
            if inspect.isclass(svc_clazz):
                # Get the specification field of keep the type name
                svc_clazz = _get_class_spec(svc_clazz)

            if not svc_clazz:
                # Invalid class name
                raise BundleException(f"Invalid class name: {svc_clazz}")

            if isinstance(svc_clazz, str):
                classes.append(svc_clazz)
            elif isinstance(svc_clazz, list):
                classes.extend(svc_clazz)

        # Make the service registration
        registration = self._registry.register(bundle, classes, properties, service, factory, prototype)

        # Update the bundle registration information
        bundle._registered_service(registration)

        if send_event:
            # Call the listeners
            event = ServiceEvent(ServiceEvent.REGISTERED, registration.get_reference())
            self._dispatcher.fire_service_event(event)

        return registration

    def start(self) -> bool:
        """
        Starts the framework

        :return: True if the bundle has been started, False if it was already running
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
            self._dispatcher.fire_bundle_event(BundleEvent(BundleEvent.STARTING, self))

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

    def stop(self) -> bool:
        """
        Stops the framework

        :return: True if the framework stopped, False it wasn't running
        """
        with self._lock:
            if self._state != Bundle.ACTIVE:
                # Invalid state
                return False

            # Hide all services (they will be deleted by bundle.stop())
            for bnd in self.__bundles.values():
                self._registry.hide_bundle_services(bnd)

            # Stopping...
            self._state = Bundle.STOPPING
            self._dispatcher.fire_bundle_event(BundleEvent(BundleEvent.STOPPING, self))

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
            self._dispatcher.fire_bundle_event(BundleEvent(BundleEvent.STOPPED, self))

            # All bundles have been stopped, release "wait_for_stop"
            self._fw_stop_event.set()

            # Force the registry clean up
            self._registry.clear()
            return True

    def delete(self, force: bool = False) -> bool:
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

    def uninstall(self) -> None:
        """
        A framework can't be uninstalled

        :raise BundleException: This method must not be called
        """
        raise BundleException("A framework can't be uninstalled")

    def uninstall_bundle(self, bundle: Bundle) -> None:
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
                raise BundleException(f"Invalid bundle {bundle}")

            # Notify listeners
            self._dispatcher.fire_bundle_event(BundleEvent(BundleEvent.UNINSTALLED, bundle))

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

    def unregister_service(self, registration: ServiceRegistration[Any]) -> bool:
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

    def _hide_bundle_services(self, bundle: Bundle) -> List[ServiceReference[Any]]:
        """
        Hides the services of the given bundle in the service registry

        :param bundle: The bundle providing services
        :return: The references of the hidden services
        """
        return list(self._registry.hide_bundle_services(bundle))

    def _unget_used_services(self, bundle: Bundle) -> None:
        """
        Cleans up all service usages of the given bundle

        :param bundle: Bundle to be cleaned up
        """
        self._registry.unget_used_services(bundle)

    def update(self) -> None:
        """
        Stops and starts the framework, if the framework is active.

        :raise BundleException: Something wrong occurred while stopping or
                                starting the framework.
        """
        with self._lock:
            if self._state == Bundle.ACTIVE:
                self.stop()
                self.start()

    def wait_for_stop(self, timeout: Optional[int] = None) -> bool:
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


class ServiceObjects(Generic[T]):
    """
    Allows multiple service objects for a service to be obtained.
    """

    def __init__(
        self,
        registry: ServiceRegistry,
        bundle: Bundle,
        svc_ref: ServiceReference[T],
    ) -> None:
        """
        :param bundle: Bundle requesting the service
        :param svc_ref: Reference to the requested service
        """
        self.__registry = registry
        self.__bundle = bundle
        self.__reference = svc_ref

    def get_service(self) -> T:
        """
        Returns a service object for the associated service.
        """
        return self.__registry.get_service(self.__bundle, self.__reference)

    def get_service_reference(self) -> ServiceReference[T]:
        """
        Returns the ServiceReference for the service associated with this
        object.

        :return: The ServiceReference to the service associated to this object
        """
        return self.__reference

    def unget_service(self, service: T) -> bool:
        """
        Releases a service object for the associated service.

        :param service: An instance of a service returned by ``get_service()``
        :return: True if the bundle usage has been removed
        """
        return self.__registry.unget_service(self.__bundle, self.__reference, service)


class BundleContext:
    """
    The bundle context is the link between a bundle and the framework.
    It is unique for a bundle and is created by the framework once the bundle
    is installed.
    """

    def __init__(self, framework: Framework, bundle: Bundle) -> None:
        """
        :param framework: Hosting framework
        :param bundle: The associated bundle
        """
        self.__bundle = bundle
        self.__framework = framework

    def __str__(self) -> str:
        """
        String representation
        """
        return f"BundleContext({self.__bundle})"

    def add_bundle_listener(self, listener: BundleListener) -> bool:
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

    def add_framework_stop_listener(self, listener: FrameworkStoppingListener) -> bool:
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
        self,
        listener: ServiceListener,
        ldap_filter: Union[None, LDAPCriteria, LDAPFilter, str] = None,
        specification: Optional[Union[str, Type[Any], Iterable[Union[str, Type[Any]]]]] = None,
    ) -> bool:
        """
        Registers a service listener

        The service listener must have a method with the following prototype::

           def service_changed(self, event):
               '''
               Called by Pelix when some service properties changes

               event: A ServiceEvent object
               '''
               # ...

        :param listener: The listener to register
        :param ldap_filter: Filter that must match the service properties
                            (optional, None to accept all services)
        :param specification: The specification that must provide the service
                              (optional, None to accept all services)
        :return: True if the listener has been successfully registered
        """
        if specification is not None and inspect.isclass(specification):
            specification = _get_class_spec(specification)

        if isinstance(specification, str):
            single_specification_filter = specification
        elif isinstance(specification, list):
            single_specification_filter = None
            spec_filters = [f"({OBJECTCLASS}={spec})" for spec in specification]
            ldap_specification_filter = f"(&{''.join(spec_filters)})"
            if ldap_filter is None:
                ldap_filter = ldap_specification_filter
            else:
                ldap_filter = f"(&{ldap_filter}{ldap_specification_filter})"
        else:
            single_specification_filter = None

        return self.__framework._dispatcher.add_service_listener(
            self, listener, single_specification_filter, ldap_filter
        )

    def get_all_service_references(
        self,
        clazz: Union[None, str, Type[T]] = None,
        ldap_filter: Union[None, str, LDAPFilter, LDAPCriteria] = None,
    ) -> Optional[List[ServiceReference[T]]]:
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

    def get_bundle(self, bundle_id: Union[None, int, Bundle] = None) -> Bundle:
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

        if isinstance(bundle_id, Bundle):
            # Got a bundle (compatibility with older install_bundle())
            bundle_id = bundle_id.get_bundle_id()

        return self.__framework.get_bundle_by_id(bundle_id)

    def get_bundles(self) -> List[Bundle]:
        """
        Returns the list of all installed bundles

        :return: A list of :class:`~pelix.framework.Bundle` objects
        """
        return self.__framework.get_bundles()

    def get_framework(self) -> Framework:
        """
        Returns the :class:`~pelix.FRAMEWORK.Framework` that created this
        bundle context

        :return: The :class:`~pelix.framework.Framework` object
        """
        return self.__framework

    def get_property(self, name: str) -> Any:
        """
        Returns the value of a property of the framework, else returns the OS
        environment value.

        :param name: A property name
        """
        return self.__framework.get_property(name)

    def get_service(self, reference: ServiceReference[T]) -> T:
        """
        Returns the service described with the given reference

        :param reference: A ServiceReference object
        :return: The service object itself
        """
        return self.__framework.get_service(self.__bundle, reference)

    def get_service_objects(self, reference: ServiceReference[T]) -> ServiceObjects[T]:
        """
        Returns the ServiceObjects object for the service referenced by the
        specified ServiceReference object.

        :param reference: Reference to a prototype service factory
        :return: An intermediate object to get more instances of a service
        """
        return self.__framework._get_service_objects(self.__bundle, reference)

    def get_service_reference(
        self,
        clazz: Union[None, str, Type[T]],
        ldap_filter: Union[None, str, LDAPFilter, LDAPCriteria] = None,
    ) -> Optional[ServiceReference[T]]:
        """
        Returns a ServiceReference object for a service that implements and
        was registered under the specified class

        :param clazz: The class name with which the service was registered.
        :param ldap_filter: A filter on service properties
        :return: A service reference, None if not found
        """
        result = self.__framework.find_service_references(clazz, ldap_filter, True)
        return result[0] if result else None

    def get_service_references(
        self,
        clazz: Union[None, str, Type[T]],
        ldap_filter: Union[None, str, LDAPFilter, LDAPCriteria] = None,
    ) -> Optional[List[ServiceReference[T]]]:
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

    def install_bundle(self, name: str, path: Union[None, str, pathlib.Path] = None) -> Bundle:
        """
        Installs the bundle (module) with the given name.

        If a path is given, it is inserted in first place in the Python loading
        path (``sys.path``). All modules loaded alongside this bundle, *i.e.*
        by this bundle or its dependencies, will be looked after in this path
        in priority.

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

    def install_package(
        self, path: Union[str, pathlib.Path], recursive: bool = False
    ) -> Tuple[Set[Bundle], Set[str]]:
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

    def install_visiting(
        self,
        path: Union[str, pathlib.Path],
        visitor: Callable[[str, bool, str], bool],
    ) -> Tuple[Set[Bundle], Set[str]]:
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
        clazz: Union[
            str,
            Type[T],
            Iterable[Union[str, Type[Any]]],
        ],
        service: T,
        properties: Optional[Dict[str, Any]],
        send_event: bool = True,
        factory: bool = False,
        prototype: bool = False,
    ) -> ServiceRegistration[T]:
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

    def remove_bundle_listener(self, listener: BundleListener) -> bool:
        """
        Unregisters the given bundle listener

        :param listener: The bundle listener to remove
        :return: True if the listener has been unregistered, False if it wasn't registered
        """
        return self.__framework._dispatcher.remove_bundle_listener(listener)

    def remove_framework_stop_listener(self, listener: FrameworkStoppingListener) -> bool:
        """
        Unregisters a framework stop listener

        :param listener: The framework stop listener
        :return: True if the listener has been unregistered
        """
        return self.__framework._dispatcher.remove_framework_listener(listener)

    def remove_service_listener(self, listener: ServiceListener) -> bool:
        """
        Unregisters a service listener

        :param listener: The service listener
        :return: True if the listener has been unregistered
        """
        return self.__framework._dispatcher.remove_service_listener(listener)

    def unget_service(self, reference: ServiceReference[Any]) -> bool:
        """
        Disables a reference to the service

        :return: True if the bundle was using this reference, else False
        """
        # Lose the dependency
        return self.__framework._registry.unget_service(self.__bundle, reference)


# ------------------------------------------------------------------------------


class FrameworkFactory:
    """
    A framework factory
    """

    __singleton: Optional[Framework] = None
    """ The framework singleton """

    @classmethod
    def get_framework(cls, properties: Optional[Dict[str, Any]] = None) -> Framework:
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
    def is_framework_running(cls, framework: Optional[Framework] = None) -> bool:
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
    def delete_framework(cls, framework: Optional[Framework] = None) -> bool:
        # pylint: disable=W0212
        """
        Removes the framework singleton

        :return: True on success, else False
        """
        if framework is None:
            framework = cls.__singleton

        if framework is not None and framework is cls.__singleton:
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
    bundles: Iterable[str],
    properties: Optional[Dict[str, Any]] = None,
    auto_start: bool = False,
    wait_for_stop: bool = False,
    auto_delete: bool = False,
) -> Framework:
    """
    Creates a Pelix framework, installs the given bundles and returns its instance reference.

    If *auto_start* is True, the framework will be started once all bundles will have been installed
    If *wait_for_stop* is True, the method will return only when the framework will have stopped.
    This requires *auto_start* to be True.
    If *auto_delete* is True, the framework will be deleted once it has stopped
    and should not be used afterwards
    This requires *wait_for_stop* and *auto_start* to be True.

    :param bundles: Bundles to initially install (shouldn't be empty if *wait_for_stop* is True)
    :param properties: Optional framework properties
    :param auto_start: If True, the framework will be started immediately
    :param wait_for_stop: If True, the method will return only when the framework will have stopped
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

    return framework


def _package_exists(path: str) -> bool:
    """
    Checks if the given Python path matches a valid file or a valid container
    file

    :param path: A Python path
    :return: True if the module or its container exists
    """
    while path:
        if os.path.exists(path):
            return True

        path = os.path.dirname(path)

    return False


def normalize_path() -> None:
    """
    Normalizes sys.path to avoid the use of relative folders
    """
    # Normalize Python paths
    whole_path = [os.path.abspath(path) for path in sys.path if os.path.exists(path)]

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
    for module_ in list(sys.modules.values()):
        try:
            if module_.__path__ is not None:
                # Seems that (some?) DLL-based modules don't have a __path__
                # but their __file__ is already absolute
                module_.__path__ = [
                    os.path.abspath(path) for path in module_.__path__ if _package_exists(path)
                ]
        except AttributeError:
            # builtin modules don't have a __path__
            pass
        except ImportError:
            pass
