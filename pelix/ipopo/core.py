#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Core iPOPO implementation

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
import copy
import inspect
import logging
import sys
import threading

# Standard typing module should be optional
try:
    # pylint: disable=W0611
    from typing import Any, Dict, List, Optional, Set, Tuple
    from pelix.framework import BundleContext, ServiceReference
except ImportError:
    pass

# Pelix
from pelix.constants import SERVICE_ID, BundleActivator
from pelix.framework import Bundle, BundleException
from pelix.internals.events import BundleEvent, ServiceEvent
from pelix.utilities import add_listener, remove_listener, is_string

# iPOPO constants
import pelix.ipopo.constants as constants
import pelix.ipopo.handlers.constants as handlers_const

# iPOPO beans
from pelix.ipopo.contexts import FactoryContext, ComponentContext
from pelix.ipopo.instance import StoredInstance

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Prepare the module logger
_logger = logging.getLogger("ipopo.core")

# Built-in handlers, automatically installed
BUILTIN_HANDLERS = (
    "pelix.ipopo.handlers.properties",
    "pelix.ipopo.handlers.provides",
    "pelix.ipopo.handlers.requires",
    "pelix.ipopo.handlers.requiresbest",
    "pelix.ipopo.handlers.requiresmap",
    "pelix.ipopo.handlers.requiresvarfilter",
    "pelix.ipopo.handlers.temporal",
)

# ------------------------------------------------------------------------------


def _set_factory_context(factory_class, bundle_context):
    # type: (type, Optional[BundleContext]) -> Optional[FactoryContext]
    """
    Transforms the context data dictionary into its FactoryContext object form.

    :param factory_class: A manipulated class
    :param bundle_context: The class bundle context
    :return: The factory context, None on error
    """
    try:
        # Try to get the factory context (built using decorators)
        context = getattr(factory_class, constants.IPOPO_FACTORY_CONTEXT)
    except AttributeError:
        # The class has not been manipulated, or too badly
        return None

    if not context.completed:
        # Partial context (class not manipulated)
        return None

    # Associate the factory to the bundle context
    context.set_bundle_context(bundle_context)
    return context


def _load_bundle_factories(bundle):
    # type: (Bundle) -> List[Tuple[FactoryContext, type]]
    """
    Retrieves a list of pairs (FactoryContext, factory class) with all
    readable manipulated classes found in the bundle.

    :param bundle: A Bundle object
    :return: The list of factories loaded from the bundle
    """
    result = []

    # Get the Python module
    module_ = bundle.get_module()

    # Get the bundle context
    bundle_context = bundle.get_bundle_context()

    for name in dir(module_):
        try:
            # Get the module member
            factory_class = getattr(module_, name)
            if not inspect.isclass(factory_class):
                continue

            # Check if it is a class
            if sys.modules[factory_class.__module__] is not module_:
                # Only keep classes from this module
                continue
        except (AttributeError, KeyError):
            # getattr() didn't work or __module__ is not a member of the class,
            # or the module is not known by the interpreter
            continue

        context = _set_factory_context(factory_class, bundle_context)
        if context is None:
            # Error setting up the factory context
            continue

        result.append((context, factory_class))

    return result


# ------------------------------------------------------------------------------


class _IPopoService(object):
    """
    The iPOPO registry and service.

    This service is registered automatically and **must not** be started
    manually.
    """

    def __init__(self, bundle_context):
        # type: (BundleContext) -> None
        """
        :param bundle_context: The iPOPO bundle context
        """
        # Store the bundle context
        self.__context = bundle_context

        # Factories registry : name -> factory class
        self.__factories = {}  # type: Dict[str, type]

        # Instances registry : name -> StoredInstance object
        self.__instances = {}  # type: Dict[str, StoredInstance]

        # Event listeners
        self.__listeners = []  # type: List[Any]

        # Auto-restarted components (Bundle -> [(factory, name, properties)]
        self.__auto_restart = {}  # type: Dict[Bundle, List[Tuple[str, str, Dict]]]

        # Service state
        self.running = False

        # Registries locks
        self.__factories_lock = threading.RLock()
        self.__instances_lock = threading.RLock()
        self.__listeners_lock = threading.RLock()
        self.__handlers_lock = threading.RLock()

        # Handlers factories
        self._handlers_refs = set()  # type: Set[ServiceReference]
        self._handlers = {}  # type: Dict[str, Any]

        # Instances waiting for a handler: Name -> (ComponentContext, instance)
        self.__waiting_handlers = {}  # type: Dict[str, Tuple[ComponentContext, Any]]

        # Register the service listener
        bundle_context.add_service_listener(
            self, None, handlers_const.SERVICE_IPOPO_HANDLER_FACTORY
        )
        self.__find_handler_factories()

    def __find_handler_factories(self):
        """
        Finds all registered handler factories and stores them
        """
        # Get the references
        svc_refs = self.__context.get_all_service_references(
            handlers_const.SERVICE_IPOPO_HANDLER_FACTORY
        )
        if svc_refs:
            for svc_ref in svc_refs:
                # Store each handler factory
                self.__add_handler_factory(svc_ref)

    def __add_handler_factory(self, svc_ref):
        # type: (ServiceReference) -> None
        """
        Stores a new handler factory

        :param svc_ref: ServiceReference of the new handler factory
        """
        with self.__handlers_lock:
            # Get the handler ID
            handler_id = svc_ref.get_property(handlers_const.PROP_HANDLER_ID)
            if handler_id in self._handlers:
                # Duplicated ID
                _logger.warning("Already registered handler ID: %s", handler_id)
            else:
                # Store the service
                self._handlers_refs.add(svc_ref)
                self._handlers[handler_id] = self.__context.get_service(svc_ref)

                # Try to instantiate waiting components
                succeeded = set()
                for (
                    name,
                    (context, instance),
                ) in self.__waiting_handlers.items():
                    if self.__try_instantiate(context, instance):
                        succeeded.add(name)

                # Remove instantiated component from the waiting list
                for name in succeeded:
                    del self.__waiting_handlers[name]

    def __remove_handler_factory(self, svc_ref):
        # type: (ServiceReference) -> None
        """
        Removes an handler factory

        :param svc_ref: ServiceReference of the handler factory to remove
        """
        with self.__handlers_lock:
            # Get the handler ID
            handler_id = svc_ref.get_property(handlers_const.PROP_HANDLER_ID)

            # Check if this is the handler we use
            if svc_ref not in self._handlers_refs:
                return

            # Clean up
            self.__context.unget_service(svc_ref)
            self._handlers_refs.remove(svc_ref)
            del self._handlers[handler_id]

            # List the components using this handler
            to_stop = set()  # type: Set[StoredInstance]
            for factory_name in self.__factories:
                _, factory_context = self.__get_factory_with_context(
                    factory_name
                )
                if handler_id in factory_context.get_handlers_ids():
                    to_stop.update(self.__get_stored_instances(factory_name))

            with self.__instances_lock:
                for stored_instance in to_stop:
                    # Extract information
                    context = stored_instance.context
                    name = context.name
                    instance = stored_instance.instance

                    # Clean up the stored instance (iPOPO side)
                    del self.__instances[name]
                    stored_instance.kill()

                    # Add the component to the waiting queue
                    self.__waiting_handlers[name] = (context, instance)

            # Try to find a new handler factory
            new_ref = self.__context.get_service_reference(
                handlers_const.SERVICE_IPOPO_HANDLER_FACTORY,
                "({0}={1})".format(handlers_const.PROP_HANDLER_ID, handler_id),
            )
            if new_ref is not None:
                self.__add_handler_factory(new_ref)

    def __get_factory_with_context(self, factory_name):
        # type: (str) -> Tuple[type, FactoryContext]
        """
        Retrieves the factory registered with the given and its factory context

        :param factory_name: The name of the factory
        :return: A (factory, context) tuple
        :raise TypeError: Unknown factory, or factory not manipulated
        """
        factory = self.__factories.get(factory_name)
        if factory is None:
            raise TypeError("Unknown factory '{0}'".format(factory_name))

        # Get the factory context
        factory_context = getattr(
            factory, constants.IPOPO_FACTORY_CONTEXT, None
        )
        if factory_context is None:
            raise TypeError(
                "Factory context missing in '{0}'".format(factory_name)
            )

        return factory, factory_context

    def __get_handler_factories(self, handlers_ids):
        # type: (list) -> set
        """
        Returns the list of Handler Factories for the given Handlers IDs.
        Raises a KeyError exception is a handler factory is missing.

        :param handlers_ids: List of handlers IDs
        :raise KeyError: A handler is missing
        """
        # Look for the required handlers
        return {self._handlers[handler_id] for handler_id in handlers_ids}

    def __get_stored_instances(self, factory_name):
        # type: (str) -> List[StoredInstance]
        """
        Retrieves the list of all stored instances objects corresponding to
        the given factory name

        :param factory_name: A factory name
        :return: All components instantiated from the given factory
        """
        with self.__instances_lock:
            return [
                stored_instance
                for stored_instance in self.__instances.values()
                if stored_instance.factory_name == factory_name
            ]

    def __try_instantiate(self, component_context, instance):
        # type: (ComponentContext, object) -> bool
        """
        Instantiates a component, if all of its handlers are there. Returns
        False if a handler is missing.

        :param component_context: A ComponentContext bean
        :param instance: The component instance
        :return: True if the component has started,
                 False if a handler is missing
        """
        with self.__instances_lock:
            # Extract information about the component
            factory_context = component_context.factory_context
            handlers_ids = factory_context.get_handlers_ids()
            name = component_context.name
            factory_name = factory_context.name

            try:
                # Get handlers
                handler_factories = self.__get_handler_factories(handlers_ids)
            except KeyError:
                # A handler is missing, stop here
                return False

            # Instantiate the handlers
            all_handlers = set()  # type: Set[Any]
            for handler_factory in handler_factories:
                handlers = handler_factory.get_handlers(
                    component_context, instance
                )
                if handlers:
                    all_handlers.update(handlers)

            # Prepare the stored instance
            stored_instance = StoredInstance(
                self, component_context, instance, all_handlers
            )

            # Manipulate the properties
            for handler in all_handlers:
                handler.manipulate(stored_instance, instance)

            # Store the instance
            self.__instances[name] = stored_instance

        # Start the manager
        stored_instance.start()

        # Notify listeners now that every thing is ready to run
        self._fire_ipopo_event(
            constants.IPopoEvent.INSTANTIATED, factory_name, name
        )

        # Try to validate it
        stored_instance.update_bindings()
        stored_instance.check_lifecycle()
        return True

    def _autorestart_store_components(self, bundle):
        # type: (Bundle) -> None
        """
        Stores the components of the given bundle with the auto-restart
        property

        :param bundle: A Bundle object
        """
        with self.__instances_lock:
            # Prepare the list of components
            store = self.__auto_restart.setdefault(bundle, [])
            for stored_instance in self.__instances.values():
                # Get the factory name
                factory = stored_instance.factory_name
                if self.get_factory_bundle(factory) is bundle:
                    # Factory from this bundle
                    # Test component properties
                    properties = stored_instance.context.properties
                    if properties.get(constants.IPOPO_AUTO_RESTART):
                        # Auto-restart property found
                        store.append(
                            (factory, stored_instance.name, properties)
                        )

    def _autorestart_components(self, bundle):
        # type: (Bundle) -> None
        """
        Restart the components of the given bundle

        :param bundle: A Bundle object
        """
        with self.__instances_lock:
            instances = self.__auto_restart.get(bundle)
            if not instances:
                # Nothing to do
                return

            for factory, name, properties in instances:
                try:
                    # Instantiate the given component
                    self.instantiate(factory, name, properties)
                except Exception as ex:
                    # Log error, but continue to work
                    _logger.exception(
                        "Error restarting component '%s' ('%s') "
                        "from bundle %s (%d): %s",
                        name,
                        factory,
                        bundle.get_symbolic_name(),
                        bundle.get_bundle_id(),
                        ex,
                    )

    def _autorestart_clear_components(self, bundle):
        # type: (Bundle) -> None
        """
        Clear the list of auto-restart components of the given bundle

        :param bundle: A Bundle object
        """
        with self.__instances_lock:
            # Simply delete the entry, if any
            try:
                del self.__auto_restart[bundle]
            except KeyError:
                pass

    def _fire_ipopo_event(self, kind, factory_name, instance_name=None):
        # type: (int, str, Optional[str]) -> None
        """
        Triggers an iPOPO event

        :param kind: Kind of event
        :param factory_name: Name of the factory associated to the event
        :param instance_name: Name of the component instance associated to the
                              event
        """
        with self.__listeners_lock:
            # Use a copy of the list of listeners
            listeners = self.__listeners[:]

        for listener in listeners:
            try:
                listener.handle_ipopo_event(
                    constants.IPopoEvent(kind, factory_name, instance_name)
                )
            except:
                _logger.exception("Error calling an iPOPO event handler")

    def _prepare_instance_properties(self, properties, factory_properties):
        # type: (dict, dict) -> dict
        """
        Prepares the properties of a component instance, based on its
        configuration, factory and framework properties

        :param properties: Component instance properties
        :param factory_properties: Component factory "default" properties
        :return: The merged properties
        """
        # Normalize given properties
        if properties is None or not isinstance(properties, dict):
            properties = {}

        # Use framework properties to fill missing ones
        framework = self.__context.get_framework()
        for property_name in factory_properties:
            if property_name not in properties:
                # Missing property
                value = framework.get_property(property_name)
                if value is not None:
                    # Set the property value
                    properties[property_name] = value

        return properties

    def _register_bundle_factories(self, bundle):
        # type: (Bundle) -> None
        """
        Registers all factories found in the given bundle

        :param bundle: A bundle
        """
        # Load the bundle factories
        factories = _load_bundle_factories(bundle)

        for context, factory_class in factories:
            try:
                # Register each found factory
                self._register_factory(context.name, factory_class, False)
            except ValueError as ex:
                # Already known factory
                _logger.error(
                    "Cannot register factory '%s' of bundle %d (%s): %s",
                    context.name,
                    bundle.get_bundle_id(),
                    bundle.get_symbolic_name(),
                    ex,
                )
                _logger.error(
                    "class: %s -- module: %s",
                    factory_class,
                    factory_class.__module__,
                )
            else:
                # Instantiate components
                for name, properties in context.get_instances().items():
                    self.instantiate(context.name, name, properties)

    def _register_factory(self, factory_name, factory, override):
        # type: (str, type, bool) -> None
        """
        Registers a component factory

        :param factory_name: The name of the factory
        :param factory: The factory class object
        :param override: If true, previous factory is overridden, else an
                         exception is risen if a previous factory with that
                         name already exists
        :raise ValueError: The factory name already exists or is invalid
        :raise TypeError: Invalid factory type
        """
        if not factory_name or not is_string(factory_name):
            raise ValueError("A factory name must be a non-empty string")

        if not inspect.isclass(factory):
            raise TypeError(
                "Invalid factory class '{0}'".format(type(factory).__name__)
            )

        with self.__factories_lock:
            if factory_name in self.__factories:
                if override:
                    _logger.info("Overriding factory '%s'", factory_name)
                else:
                    raise ValueError(
                        "'{0}' factory already exist".format(factory_name)
                    )

            self.__factories[factory_name] = factory

            # Trigger an event
            self._fire_ipopo_event(
                constants.IPopoEvent.REGISTERED, factory_name
            )

    def _unregister_all_factories(self):
        """
        Unregisters all factories. This method should be called only after the
        iPOPO service has been unregistered (that's why it's not locked)
        """
        factories = list(self.__factories.keys())
        for factory_name in factories:
            self.unregister_factory(factory_name)

    def _unregister_bundle_factories(self, bundle):
        # type: (Bundle) -> None
        """
        Unregisters all factories of the given bundle

        :param bundle: A bundle
        """
        with self.__factories_lock:
            # Find out which factories must be removed
            to_remove = [
                factory_name
                for factory_name in self.__factories
                if self.get_factory_bundle(factory_name) is bundle
            ]

            # Remove all of them
            for factory_name in to_remove:
                try:
                    self.unregister_factory(factory_name)
                except ValueError as ex:
                    _logger.warning(
                        "Error unregistering factory '%s': %s", factory_name, ex
                    )

    def _stop(self):
        """
        iPOPO is stopping: clean everything up
        """
        # Running flag down
        self.running = False

        # Unregister the service listener
        self.__context.remove_service_listener(self)

        # Clean up handler factories usages
        with self.__instances_lock:
            for svc_ref in self._handlers_refs:
                self.__context.unget_service(svc_ref)

            self._handlers.clear()
            self._handlers_refs.clear()

    def framework_stopping(self):
        """
        Called by the framework when it is about to stop
        """
        self._stop()

    def bundle_changed(self, event):
        # type: (BundleEvent) -> None
        """
        A bundle event has been triggered

        :param event: The bundle event
        """
        kind = event.get_kind()
        bundle = event.get_bundle()

        if kind == BundleEvent.STOPPING_PRECLEAN:
            # A bundle is gone, remove its factories after the deactivator has
            # been called. That way, the deactivator can kill manually started
            # components.
            self._unregister_bundle_factories(bundle)

        elif kind == BundleEvent.STARTED:
            # A bundle is staring, register its factories before its activator
            # is called. That way, the activator can use the registered
            # factories.
            self._register_bundle_factories(bundle)

        elif kind == BundleEvent.UPDATE_BEGIN:
            # A bundle will be updated, store its auto-restart component
            self._autorestart_store_components(bundle)

        elif kind == BundleEvent.UPDATED:
            # Update has finished, restart stored components
            self._autorestart_components(bundle)
            self._autorestart_clear_components(bundle)

        elif kind == BundleEvent.UPDATE_FAILED:
            # Update failed, clean the stored components
            self._autorestart_clear_components(bundle)

    def service_changed(self, event):
        # type: (ServiceEvent) -> None
        """
        Called when a handler factory service is un/registered
        """
        # Call sub-methods
        kind = event.get_kind()
        svc_ref = event.get_service_reference()

        if kind == ServiceEvent.REGISTERED:
            # Service coming
            with self.__instances_lock:
                self.__add_handler_factory(svc_ref)

        elif kind == ServiceEvent.UNREGISTERING:
            # Service gone
            with self.__instances_lock:
                self.__remove_handler_factory(svc_ref)

    def instantiate(self, factory_name, name, properties=None):
        # type: (str, str, dict) -> Any
        """
        Instantiates a component from the given factory, with the given name

        :param factory_name: Name of the component factory
        :param name: Name of the instance to be started
        :param properties: Initial properties of the component instance
        :return: The component instance
        :raise TypeError: The given factory is unknown
        :raise ValueError: The given name or factory name is invalid, or an
                           instance with the given name already exists
        :raise Exception: Something wrong occurred in the factory
        """
        # Test parameters
        if not factory_name or not is_string(factory_name):
            raise ValueError("Invalid factory name")

        if not name or not is_string(name):
            raise ValueError("Invalid component name")

        if not self.running:
            # Stop working if the framework is stopping
            raise ValueError("Framework is stopping")

        with self.__instances_lock:
            if name in self.__instances or name in self.__waiting_handlers:
                raise ValueError(
                    "'{0}' is an already running instance name".format(name)
                )

            with self.__factories_lock:
                # Can raise a TypeError exception
                factory, factory_context = self.__get_factory_with_context(
                    factory_name
                )

                # Check if the factory is singleton and if a component is
                # already started
                if (
                    factory_context.is_singleton
                    and factory_context.is_singleton_active
                ):
                    raise ValueError(
                        "{0} is a singleton: {1} can't be "
                        "instantiated.".format(factory_name, name)
                    )

                # Create component instance
                try:
                    instance = factory()
                except Exception:
                    _logger.exception(
                        "Error creating the instance '%s' from factory '%s'",
                        name,
                        factory_name,
                    )
                    raise TypeError(
                        "Factory '{0}' failed to create '{1}'".format(
                            factory_name, name
                        )
                    )

                # Instantiation succeeded: update singleton status
                if factory_context.is_singleton:
                    factory_context.is_singleton_active = True

            # Normalize the given properties
            properties = self._prepare_instance_properties(
                properties, factory_context.properties
            )

            # Set up the component instance context
            component_context = ComponentContext(
                factory_context, name, properties
            )

            # Try to instantiate the component immediately
            if not self.__try_instantiate(component_context, instance):
                # A handler is missing, put the component in the queue
                self.__waiting_handlers[name] = (component_context, instance)

        return instance

    def retry_erroneous(self, name, properties_update=None):
        # type: (str, dict) -> int
        """
        Removes the ERRONEOUS state of the given component, and retries a
        validation

        :param name: Name of the component to retry
        :param properties_update: A dictionary to update the initial properties
                                  of the component
        :return: The new state of the component
        :raise ValueError: Invalid component name
        """
        with self.__instances_lock:
            try:
                stored_instance = self.__instances[name]
            except KeyError:
                raise ValueError(
                    "Unknown component instance '{0}'".format(name)
                )
            else:
                return stored_instance.retry_erroneous(properties_update)

    def invalidate(self, name):
        # type: (str) -> None
        """
        Invalidates the given component

        :param name: Name of the component to invalidate
        :raise ValueError: Invalid component name
        """
        with self.__instances_lock:
            try:
                stored_instance = self.__instances[name]
            except KeyError:
                raise ValueError(
                    "Unknown component instance '{0}'".format(name)
                )
            else:
                # Call back the component during the invalidation
                stored_instance.invalidate(True)

    def is_registered_factory(self, name):
        # type: (str) -> bool
        """
        Tests if the given name is in the factory registry

        :param name: A factory name to be tested
        """
        with self.__factories_lock:
            return name in self.__factories

    def is_registered_instance(self, name):
        # type: (str) -> bool
        """
        Tests if the given name is in the instance registry or in the waiting
        queue

        :param name: A component name to be tested
        """
        with self.__instances_lock:
            return name in self.__instances

    def kill(self, name):
        # type: (str) -> None
        """
        Kills the given component

        :param name: Name of the component to kill
        :raise ValueError: Invalid component name
        """
        if not name:
            raise ValueError("Name can't be None or empty")

        with self.__instances_lock:
            try:
                # Running instance
                stored_instance = self.__instances.pop(name)

                # Store the reference to the factory context
                factory_context = stored_instance.context.factory_context

                # Kill it
                stored_instance.kill()

                # Update the singleton state flag
                factory_context.is_singleton_active = False
            except KeyError:
                # Queued instance
                try:
                    # Extract the component context
                    context, _ = self.__waiting_handlers.pop(name)

                    # Update the singleton state flag
                    context.factory_context.is_singleton_active = False
                except KeyError:
                    raise ValueError(
                        "Unknown component instance '{0}'".format(name)
                    )

    def register_factory(self, bundle_context, factory):
        # type: (BundleContext, type) -> bool
        """
        Registers a manually created factory, using decorators programmatically

        :param bundle_context: The factory bundle context
        :param factory: A manipulated class
        :return: True if the factory has been registered
        :raise ValueError: Invalid parameter, or factory already registered
        :raise TypeError: Invalid factory type (not a manipulated class)
        """
        if factory is None or bundle_context is None:
            # Invalid parameter, to nothing
            raise ValueError("Invalid parameter")

        context = _set_factory_context(factory, bundle_context)
        if not context:
            raise TypeError("Not a manipulated class (no context found)")

        self._register_factory(context.name, factory, False)
        return True

    def unregister_factory(self, factory_name):
        # type: (str) -> bool
        """
        Unregisters the given component factory

        :param factory_name: Name of the factory to unregister
        :return: True the factory has been removed, False if the factory is
                 unknown
        """
        if not factory_name or not is_string(factory_name):
            # Invalid name
            return False

        with self.__factories_lock:
            try:
                # Remove the factory from the registry
                factory_class = self.__factories.pop(factory_name)
            except KeyError:
                # Unknown factory
                return False

            # Trigger an event
            self._fire_ipopo_event(
                constants.IPopoEvent.UNREGISTERED, factory_name
            )

            # Invalidate and delete all components of this factory
            with self.__instances_lock:
                # Compute the list of __instances to remove
                to_remove = self.__get_stored_instances(factory_name)

                # Remove instances from the registry: avoids dependencies \
                # update to link against a component from this factory again.
                for instance in to_remove:
                    try:
                        # Kill the instance
                        self.kill(instance.name)
                    except ValueError:
                        # Unknown instance: already killed by the invalidation
                        # callback of a component killed in this loop
                        # => ignore
                        pass

                # Remove waiting component
                names = [
                    name
                    for name, (context, _) in self.__waiting_handlers.items()
                    if context.factory_context.name == factory_name
                ]
                for name in names:
                    del self.__waiting_handlers[name]

            # Clear the bundle context of the factory
            _set_factory_context(factory_class, None)

        return True

    def add_listener(self, listener):
        """
        Register an iPOPO event listener.

        The event listener must have a method with the following prototype::

           def handle_ipopo_event(self, event):
               '''
               event: A IPopoEvent object
               '''
               # ...

        :param listener: The listener to register
        :return: True if the listener has been added to the registry
        """
        with self.__listeners_lock:
            return add_listener(self.__listeners, listener)

    def remove_listener(self, listener):
        """
        Unregister an iPOPO event listener.

        :param listener: The listener to register
        :return: True if the listener has been removed from the registry
        """
        with self.__listeners_lock:
            return remove_listener(self.__listeners, listener)

    def get_instances(self):
        # type: () -> List[Tuple[str, str, int]]
        """
        Retrieves the list of the currently registered component instances

        :return: A list of (name, factory name, state) tuples.
        """
        with self.__instances_lock:
            return sorted(
                (name, stored_instance.factory_name, stored_instance.state)
                for name, stored_instance in self.__instances.items()
            )

    def get_instance(self, name):
        # type: (str) -> Any
        """
        Returns the instance of the component with the given name

        :param name: A component name
        :return: The component instance
        :raise KeyError: Unknown instance
        """
        return self.__instances[name].instance

    def get_waiting_components(self):
        # type: () -> List[Tuple[str, str, Set[str]]]
        """
        Returns the list of the instances waiting for their handlers

        :return: A list of (name, factory name, missing handlers) tuples
        """
        with self.__instances_lock:
            result = []
            for name, (context, _) in self.__waiting_handlers.items():
                # Compute missing handlers
                missing = set(context.factory_context.get_handlers_ids())
                missing.difference_update(self._handlers.keys())

                result.append((name, context.factory_context.name, missing))

            result.sort()
            return result

    def get_instance_details(self, name):
        # type: (str) -> Dict[str, Any]
        """
        Retrieves a snapshot of the given component instance.
        The result dictionary has the following keys:

        * ``name``: The component name
        * ``factory``: The name of the component factory
        * ``bundle_id``: The ID of the bundle providing the component factory
        * ``state``: The current component state
        * ``services``: A ``{Service ID → Service reference}`` dictionary, with
          all services provided by the component
        * ``dependencies``: A dictionary associating field names with the
          following dictionary:

          * ``handler``: The name of the type of the dependency handler
          * ``filter`` (optional): The requirement LDAP filter
          * ``optional``: A flag indicating whether the requirement is optional
            or not
          * ``aggregate``: A flag indicating whether the requirement is a set
            of services or not
          * ``binding``: A list of the ServiceReference the component is bound
            to

        * ``properties``: A dictionary key → value, with all properties of the
          component. The value is converted to its string representation, to
          avoid unexpected behaviours.

        :param name: The name of a component instance
        :return: A dictionary of details
        :raise ValueError: Invalid component name
        """
        if not is_string(name):
            raise ValueError("Component name must be a string")

        with self.__instances_lock:
            if name not in self.__instances:
                raise ValueError("Unknown component: {0}".format(name))

            stored_instance = self.__instances[name]
            assert isinstance(stored_instance, StoredInstance)
            with stored_instance._lock:
                result = {}  # type: Dict[str, Any]
                result["name"] = stored_instance.name

                # Factory name
                result["factory"] = stored_instance.factory_name

                # Factory bundle
                result[
                    "bundle_id"
                ] = stored_instance.bundle_context.get_bundle().get_bundle_id()

                # Component state
                result["state"] = stored_instance.state

                # Error details
                result["error_trace"] = stored_instance.error_trace

                # Provided service
                result["services"] = {}
                for handler in stored_instance.get_handlers(
                    handlers_const.KIND_SERVICE_PROVIDER
                ):
                    svc_ref = handler.get_service_reference()
                    if svc_ref is not None:
                        svc_id = svc_ref.get_property(SERVICE_ID)
                        result["services"][svc_id] = svc_ref

                # Dependencies
                result["dependencies"] = {}
                for dependency in stored_instance.get_handlers(
                    handlers_const.KIND_DEPENDENCY
                ):
                    # Dependency
                    info = result["dependencies"][dependency.get_field()] = {}
                    info["handler"] = type(dependency).__name__

                    # Requirement
                    req = dependency.requirement
                    info["specification"] = req.specification
                    info["filter"] = str(req.filter) if req.filter else None
                    info["optional"] = req.optional
                    info["aggregate"] = req.aggregate

                    # Bindings
                    info["bindings"] = dependency.get_bindings()

                # Properties
                properties = stored_instance.context.properties.items()
                result["properties"] = {
                    str(key): str(value) for key, value in properties
                }

                # All done
                return result

    def get_factories(self):
        # type: () -> List[str]
        """
        Retrieves the names of the registered factories

        :return: A list of factories. Can be empty.
        """
        with self.__factories_lock:
            return sorted(self.__factories.keys())

    def get_factory_bundle(self, name):
        # type: (str) -> Bundle
        """
        Retrieves the Pelix Bundle object that registered the given factory

        :param name: The name of a factory
        :return: The Bundle that registered the given factory
        :raise ValueError: Invalid factory
        """
        with self.__factories_lock:
            try:
                factory = self.__factories[name]
            except KeyError:
                raise ValueError("Unknown factory '{0}'".format(name))
            else:
                # Bundle Context is stored in the Factory Context
                factory_context = getattr(
                    factory, constants.IPOPO_FACTORY_CONTEXT
                )
                return factory_context.bundle_context.get_bundle()

    def get_factory_details(self, name):
        # type: (str) -> Dict[str, Any]
        """
        Retrieves a dictionary with details about the given factory

        * ``name``: The factory name
        * ``bundle``: The Bundle object of the bundle providing the factory
        * ``properties``: Copy of the components properties defined by the
          factory
        * ``requirements``: List of the requirements defined by the factory

          * ``id``: Requirement ID (field where it is injected)
          * ``specification``: Specification of the required service
          * ``aggregate``: If True, multiple services will be injected
          * ``optional``: If True, the requirement is optional

        * ``services``: List of the specifications of the services provided by
          components of this factory
        * ``handlers``: Dictionary of the non-built-in handlers required by
          this factory.
          The dictionary keys are handler IDs, and it contains a tuple with:

          * A copy of the configuration of the handler (0)
          * A flag indicating if the handler is present or not

        :param name: The name of a factory
        :return: A dictionary describing the factory
        :raise ValueError: Invalid factory
        """
        with self.__factories_lock:
            try:
                factory = self.__factories[name]
            except KeyError:
                raise ValueError("Unknown factory '{0}'".format(name))

            context = getattr(factory, constants.IPOPO_FACTORY_CONTEXT)
            assert isinstance(context, FactoryContext)

            result = {}  # type: Dict[Any, Any]
            # Factory name & bundle
            result["name"] = context.name
            result["bundle"] = context.bundle_context.get_bundle()

            # Configurable properties
            # Name -> Default value
            result["properties"] = {
                prop_name: context.properties.get(prop_name)
                for prop_name in context.properties_fields.values()
            }

            # Requirements (list of dictionaries)
            reqs = result["requirements"] = []
            handler_requires = context.get_handler(constants.HANDLER_REQUIRES)
            if handler_requires is not None:
                for field, requirement in handler_requires.items():
                    reqs.append(
                        {
                            "id": field,
                            "specification": requirement.specification,
                            "aggregate": requirement.aggregate,
                            "optional": requirement.optional,
                            "filter": requirement.original_filter,
                        }
                    )

            # Provided services (list of list of specifications)
            handler_provides = context.get_handler(constants.HANDLER_PROVIDES)
            if handler_provides is not None:
                result["services"] = [
                    specs_controller[0] for specs_controller in handler_provides
                ]
            else:
                result["services"] = []

            # Other handlers
            handlers = set(context.get_handlers_ids())
            handlers.difference_update(
                (
                    constants.HANDLER_PROPERTY,
                    constants.HANDLER_PROVIDES,
                    constants.HANDLER_REQUIRES,
                )
            )
            result["handlers"] = {
                handler: copy.deepcopy(context.get_handler(handler))
                for handler in handlers
            }

            return result


# ------------------------------------------------------------------------------


@BundleActivator
class _IPopoActivator(object):
    """
    The iPOPO bundle activator for Pelix
    """

    def __init__(self):
        """
        Sets up the activator
        """
        self._registration = None
        self._service = None
        self._bundles = []

    def start(self, context):
        # type: (BundleContext) -> None
        # pylint: disable=W0212
        """
        The bundle has started

        :param context: The bundle context
        """
        # Automatically install handlers bundles
        for handler in BUILTIN_HANDLERS:
            try:
                bundle = context.install_bundle(handler)
                bundle.start()
                self._bundles.append(bundle)
            except BundleException as ex:
                _logger.error("Error installing handler %s: %s", handler, ex)

        # Register the iPOPO service
        self._service = _IPopoService(context)
        self._registration = context.register_service(
            constants.SERVICE_IPOPO, self._service, {}
        )

        # Register as a bundle listener
        context.add_bundle_listener(self._service)

        # Register the service as a framework stop listener
        context.add_framework_stop_listener(self._service)

        # Service enters in "run" mode
        self._service.running = True

        # Get all factories
        for bundle in context.get_bundles():
            if bundle.get_state() == Bundle.ACTIVE:
                # Bundle is active, register its factories
                self._service._register_bundle_factories(bundle)

    def stop(self, context):
        # type: (BundleContext) -> None
        # pylint: disable=W0212
        """
        The bundle has stopped

        :param context: The bundle context
        """
        # The service is not in the "run" mode anymore
        self._service._stop()

        # Unregister the listener
        context.remove_bundle_listener(self._service)

        # Unregister the framework stop listener
        context.remove_framework_stop_listener(self._service)

        # Unregister the iPOPO service
        self._registration.unregister()

        # Clean up the service
        self._service._unregister_all_factories()

        # Remove handler bundles
        for bundle in self._bundles:
            bundle.uninstall()
        del self._bundles[:]

        # Clean up references
        self._registration = None
        self._service = None
