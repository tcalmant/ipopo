#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Core iPOPO implementation

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

# Pelix
from pelix.internals.events import BundleEvent
from pelix.framework import BundleContext, Bundle
from pelix.utilities import add_listener, remove_listener, is_string
import pelix.framework as pelix

# iPOPO constants
import pelix.ipopo.constants as constants

# iPOPO beans
from pelix.ipopo.contexts import FactoryContext, ComponentContext
from pelix.ipopo.instance import StoredInstance

# Standard library
import inspect
import logging
import threading

# ------------------------------------------------------------------------------

# Prepare the module logger
_logger = logging.getLogger("ipopo.core")

# ------------------------------------------------------------------------------

def _set_factory_context(factory_class, bundle_context):
    """
    Transforms the context data dictionary into its FactoryContext object form.

    :param factory_class: A manipulated class
    :param bundle_context: The class bundle context
    :return: The factory context, None on error
    """
    if not hasattr(factory_class, constants.IPOPO_FACTORY_CONTEXT_DATA):
        # The class has not been manipulated, or too badly
        return None

    # Try to get the context dictionary (built using decorators)
    context_dict = getattr(factory_class, constants.IPOPO_FACTORY_CONTEXT_DATA)

    if not isinstance(context_dict, dict):
        # We got another form of context
        return None

    # Try to load the stored data
    try:
        context = FactoryContext.from_dictionary_form(context_dict)

    except (TypeError, ValueError):
        _logger.exception("Invalid data in manipulated class '%s'",
                          factory_class.__name__)
        # Work on the next class
        return None

    # Setup the context
    context.set_bundle_context(bundle_context)

    # Inject the constructed object
    setattr(factory_class, constants.IPOPO_FACTORY_CONTEXT, context)
    return context


def _load_bundle_factories(bundle):
    """
    Retrieves a list of pairs (FactoryContext, factory class) with all
    readable manipulated classes found in the bundle.

    :param bundle: A Bundle object
    :return: The list of factories loaded from the bundle
    """
    result = []

    # Get the Python module
    module = bundle.get_module()

    # Get the bundle context
    bundle_context = bundle.get_bundle_context()

    # Get all classes defined in the module
    for inspect_member in inspect.getmembers(module, inspect.isclass):

        # Get the class in the result tuple
        factory_class = inspect_member[1]

        context = _set_factory_context(factory_class, bundle_context)

        if context is None:
            # Error setting up the factory context
            continue

        result.append((context, factory_class))

    return result

# ------------------------------------------------------------------------------

def _field_property_generator(stored_instance):
    """
    Generates the methods called by the injected class properties

    :param stored_instance: A stored component instance
    """
    def get_value(self, name):
        """
        Retrieves the property value, from the iPOPO dictionaries

        :param name: The property name
        :return: The property value
        """
        assert stored_instance.context is not None
        return stored_instance.context.properties.get(name, None)


    def set_value(self, name, new_value):
        """
        Sets the property value and trigger an update event

        :param name: The property name
        :param new_value: The new property value
        """
        assert stored_instance.context is not None

        # Get the previous value
        old_value = stored_instance.context.properties.get(name, None)
        if new_value != old_value:
            # Change the property
            stored_instance.context.properties[name] = new_value

            # New value is different of the old one, trigger an event
            stored_instance.update_property(name, old_value, new_value)

        return new_value

    return (get_value, set_value)


def _field_controller_generator(stored_instance):
    """
    Generates the methods called by the injected controller

    :param stored_instance: A stored component instance
    """
    def get_value(self, name):
        """
        Retrieves the controller value, from the iPOPO dictionaries

        :param name: The property name
        :return: The property value
        """
        assert stored_instance.context is not None
        return stored_instance.get_controller_state(name)


    def set_value(self, name, new_value):
        """
        Sets the property value and trigger an update event

        :param name: The property name
        :param new_value: The new property value
        """
        assert stored_instance.context is not None

        # Get the previous value
        old_value = stored_instance.get_controller_state(name)
        if new_value != old_value:
            # Update the controller state
            stored_instance.set_controller_state(name, new_value)

        return new_value

    return (get_value, set_value)


def _manipulate_component(instance, stored_instance):
    """
    Manipulates the component instance to inject missing elements.

    Injects the properties handling
    """
    assert instance is not None
    assert isinstance(stored_instance, StoredInstance)

    # Inject properties
    if stored_instance.context.factory_context.properties_fields:
        # Avoid injection of unused instance fields, avoiding more differences
        # between the class definition and the instance fields
        # -> Removes the overhead if the manipulated class has no __slots__ or
        #    when running in Pypy.
        getter, setter = _field_property_generator(stored_instance)

        # Prepare the methods names
        getter_name = "{0}{1}".format(constants.IPOPO_PROPERTY_PREFIX,
                                      constants.IPOPO_GETTER_SUFFIX)
        setter_name = "{0}{1}".format(constants.IPOPO_PROPERTY_PREFIX,
                                      constants.IPOPO_SETTER_SUFFIX)

        # Inject the getter and setter at the instance level
        setattr(instance, getter_name, getter)
        setattr(instance, setter_name, setter)

    # Inject controllers
    provides_tuples = stored_instance.context.factory_context.provides
    if provides_tuples:
        # Avoid injection of unused instance fields...
        controllers = set([value[1] for value in provides_tuples if value[1]])
        if controllers:
            # Controllers are valid by default
            for name in controllers:
                # Get the current value of the member (True by default)
                controller_value = getattr(instance, name, True)
                # Store the controller value
                stored_instance.set_controller_state(name, controller_value)

            # Prepare the methods names
            getter_name = "{0}{1}".format(constants.IPOPO_CONTROLLER_PREFIX,
                                          constants.IPOPO_GETTER_SUFFIX)
            setter_name = "{0}{1}".format(constants.IPOPO_CONTROLLER_PREFIX,
                                          constants.IPOPO_SETTER_SUFFIX)

            # Inject the getter and setter at the instance level
            getter, setter = _field_controller_generator(stored_instance)
            setattr(instance, getter_name, getter)
            setattr(instance, setter_name, setter)


# ------------------------------------------------------------------------------

class _IPopoService(object):
    """
    The iPOPO registry and service
    """

    def __init__(self, bundle_context):
        """
        Sets up the iPOPO registry

        :param bundle_context: The iPOPO bundle context
        """
        # Store the bundle context
        self.__context = bundle_context

        # Factories registry : name -> factory class
        self.__factories = {}

        # Instances registry : name -> StoredInstance object
        self.__instances = {}

        # Event listeners
        self.__listeners = []

        # Auto-restarted components (Bundle -> [(factory, name, properties)]
        self.__auto_restart = {}

        # Service state
        self.running = False

        # Registries locks
        self.__factories_lock = threading.RLock()
        self.__instances_lock = threading.RLock()
        self.__listeners_lock = threading.RLock()


    def __get_stored_instances_by_factory(self, factory_name):
        """
        Retrieves the list of all stored instances objects corresponding to
        the given factory name

        :param factory_name: A factory name
        :return: All components instantiated from the given factory
        """
        with self.__instances_lock:
            return [stored_instance \
                    for stored_instance in self.__instances.values() \
                    if stored_instance.factory_name == factory_name]


    def _autorestart_store_components(self, bundle):
        """
        Stores the components of the given bundle with the auto-restart property

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
                        store.append((factory, stored_instance.name,
                                      properties))


    def _autorestart_components(self, bundle):
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
                    _logger.exception("Error restarting component '%s' ('%s')"
                                      "from bundle %s (%d): %s", name, factory,
                                      bundle.get_symbolic_name(),
                                      bundle.get_bundle_id(), ex)


    def _autorestart_clear_components(self, bundle):
        """
        Clear the list of auto-restart components of the given bundle

        :param bundle: A Bundle object
        """
        with self.__instances_lock:
            # Simply delete the entry
            if bundle in self.__auto_restart:
                del self.__auto_restart[bundle]


    def _fire_ipopo_event(self, kind, factory_name, component_name=None):
        """
        Triggers an iPOPO event

        :param kind: Kind of event
        :param factory_name: Name of the factory associated to the event
        :param component_name: Name of the component instance associated to the
                               event
        """
        with self.__listeners_lock:
            # Use a copy of the list of listeners
            listeners = self.__listeners[:]

            for listener in listeners:
                try:
                    listener.handle_ipopo_event(constants.IPopoEvent(kind,
                                                             factory_name,
                                                             component_name))

                except:
                    _logger.exception("Error calling an iPOPO event handler")


    def _register_bundle_factories(self, bundle):
        """
        Registers all factories found in the given bundle

        :param bundle: A bundle
        """
        assert isinstance(bundle, Bundle)

        # Load the bundle factories
        factories = _load_bundle_factories(bundle)

        for context, factory_class in factories:
            # Register each found factory
            self._register_factory(context.name, factory_class, True)

            instances = getattr(factory_class, constants.IPOPO_INSTANCES, None)
            if isinstance(instances, dict):
                for name, properties in instances.items():
                    self.instantiate(context.name, name, properties)


    def _register_factory(self, factory_name, factory, override=True):
        """
        Registers a component factory

        :param factory_name: The name of the factory
        :param factory: The factory class object
        :param override: If true, previous factory is overridden, else an
                         exception is risen if a previous factory with that name
                         already exists
        :raise ValueError: The factory name already exists or is invalid
        :raise TypeError: Invalid factory type
        """
        if not factory_name or not is_string(factory_name):
            raise ValueError("A factory name must be a non-empty string")

        if not inspect.isclass(factory):
            raise TypeError("Invalid factory class '{0}'".format(
                                                        type(factory).__name__))

        with self.__factories_lock:
            if factory_name in self.__factories:
                if override:
                    _logger.info("Overriding factory '%s'", factory_name)

                else:
                    raise ValueError("'{0}' factory already exist".format(
                                                                factory_name))

            self.__factories[factory_name] = factory

            # Trigger an event
            self._fire_ipopo_event(constants.IPopoEvent.REGISTERED,
                                   factory_name)


    def _unregister_all_factories(self):
        """
        Unregisters all factories. This method should be called only after the
        iPOPO service has been unregistered (that's why it's not locked)
        """
        factories = list(self.__factories.keys())

        for factory_name in factories:
            self.unregister_factory(factory_name)


    def _unregister_bundle_factories(self, bundle):
        """
        Unregisters all factories of the given bundle

        :param bundle: A bundle
        """
        assert isinstance(bundle, Bundle)

        with self.__factories_lock:
            # Find out which factories must be removed
            to_remove = []

            for factory_name in self.__factories:
                if self.get_factory_bundle(factory_name) is bundle:
                    # Found a factory provided by the given bundle
                    to_remove.append(factory_name)

            # Remove all of them
            for factory_name in to_remove:
                try:
                    self.unregister_factory(factory_name)

                except ValueError as ex:
                    _logger.warning("Error unregistering factory '%s': %s",
                                    factory_name, ex)


    def framework_stopping(self):
        """
        Called by the framework when it is about to stop
        """
        self.running = False


    def bundle_changed(self, event):
        """
        A bundle event has been triggered

        :param event: The bundle event
        """
        assert isinstance(event, BundleEvent)

        kind = event.get_kind()
        bundle = event.get_bundle()

        if kind == BundleEvent.STOPPING_PRECLEAN:
            # A bundle is gone, remove its factories after the deactivator has
            # been called. That way, the deactivator can kill manually started
            # components.
            self._unregister_bundle_factories(bundle)

        elif kind == BundleEvent.STARTING:
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


    def instantiate(self, factory_name, name, properties=None):
        """
        Instantiates a component from the given factory, with the given name

        :param factory_name: Name of the component factory
        :param name: Name of the instance to be started
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
            if name in self.__instances:
                raise ValueError("'{0}' is an already running instance name" \
                                 .format(name))

            with self.__factories_lock:
                # Can raise a ValueError exception
                factory = self.__factories.get(factory_name, None)
                if factory is None:
                    raise TypeError("Unknown factory '{0}'" \
                                    .format(factory_name))

                # Get the factory context
                factory_context = getattr(factory, \
                                          constants.IPOPO_FACTORY_CONTEXT, None)
                if factory_context is None:
                    raise TypeError("Factory context missing in '{0}'" \
                                    .format(factory_name))

            # Create component instance
            try:
                instance = factory()

            except:
                _logger.exception("Error creating the instance '%s' " \
                                  "from factory '%s'", name, factory_name)

                raise TypeError("Factory '{0}' failed to create '{1}'" \
                                .format(factory_name, name))

            # Normalize given properties
            if properties is None or not isinstance(properties, dict):
                properties = {}


            # Use framework properties to fill missing ones
            framework = self.__context.get_bundle(0)
            for property_name in factory_context.properties:
                if property_name not in properties:
                    # Missing property
                    value = framework.get_property(property_name)
                    if value is not None:
                        # Set the property value
                        properties[property_name] = value

            # Set the instance context
            component_context = ComponentContext(factory_context, name, \
                                                 properties)

            # Prepare the stored instance
            stored_instance = StoredInstance(self, component_context, instance)

            # Manipulate the properties
            _manipulate_component(instance, stored_instance)

            # Store the instance
            self.__instances[name] = stored_instance

        # Start the manager
        stored_instance.start()

        # Notify listeners now that every thing is ready to run
        self._fire_ipopo_event(constants.IPopoEvent.INSTANTIATED,
                               factory_name, name)

        # Try to validate it
        stored_instance.update_bindings()
        stored_instance.check_lifecycle()

        return instance


    def invalidate(self, name):
        """
        Invalidates the given component

        :param name: Name of the component to invalidate
        :raise ValueError: Invalid component name
        """
        with self.__instances_lock:
            if name not in self.__instances:
                raise ValueError("Unknown component instance '{0}'"\
                                 .format(name))

            stored_instance = self.__instances[name]

            # Call back the component during the invalidation
            stored_instance.invalidate(True)


    def is_registered_factory(self, name):
        """
        Tests if the given name is in the factory registry

        :param name: A factory name to be tested
        """
        with self.__factories_lock:
            return name in self.__factories


    def is_registered_instance(self, name):
        """
        Tests if the given name is in the instance registry

        :param name: A component name to be tested
        """
        with self.__instances_lock:
            return name in self.__instances


    def kill(self, name):
        """
        Kills the given component

        :param name: Name of the component to kill
        :raise ValueError: Invalid component name
        """
        if not name:
            raise ValueError("Name can't be None or empty")

        with self.__instances_lock:
            if name not in self.__instances:
                raise ValueError("Unknown component instance '{0}'" \
                                 .format(name))

            stored_instance = self.__instances.pop(name)

            # Kill it
            stored_instance.kill()


    def register_factory(self, bundle_context, factory):
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
            if factory_name not in self.__factories:
                # Unknown factory
                return False

            # Trigger an event
            self._fire_ipopo_event(constants.IPopoEvent.UNREGISTERED,
                                   factory_name)

            # Invalidate and delete all components of this factory
            with self.__instances_lock:
                # Compute the list of __instances to remove
                to_remove = self.__get_stored_instances_by_factory(factory_name)

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

            # Remove the factory from the registry
            del self.__factories[factory_name]

        return True


    def add_listener(self, listener):
        """
        Register an iPOPO event listener.

        The event listener must have a method with the following prototype :

        .. python::

           def handle_ipopo_event(self, event):
               '''
               :param event: A IPopoEvent object
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
        """
        Retrieves the list of the currently registered component instances

        :return: A list of (name, factory name, state) tuples.
        """
        with self.__instances_lock:
            result = []
            for name, stored_instance in self.__instances.items():
                result.append((name, stored_instance.factory_name,
                               stored_instance.state))

            result.sort()
            return result


    def get_instance_details(self, name):
        """
        Retrieves a snapshot of the given component instance.
        The result dictionary has the following keys:

        * name: The component name
        * factory: The name of the component factory
        * bundle_id: The ID of the bundle providing the component factory
        * state: The current component state
        * services: A {Service ID -> Service reference} dictionary, with all
          services provided by the component
        * dependencies: A dictionary associating field names with the following
          dictionary:

          * handler: The name of the type of the dependency handler
          * filter (optional): The requirement LDAP filter
          * optional: A flag indicating whether the requirement is optional or
            not
          * aggregate: A flag indicating whether the requirement is a set of
            services or not
          * binding: A list of the ServiceReference the component is bound to

        * properties: A dictionary key -> value, with all properties of the
          component. The value is converted to its string representation, to
          avoid unexcepted behaviors.

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
                result = {}
                result["name"] = stored_instance.name

                # Factory name
                result["factory"] = stored_instance.factory_name

                # Factory bundle
                result["bundle_id"] = stored_instance.bundle_context \
                                                .get_bundle().get_bundle_id()

                # Component state
                result["state"] = stored_instance.state

                # Provided service
                result["services"] = {}
                for handler in stored_instance.get_handlers(
                                            constants.HANDLER_SERVICE_PROVIDER):
                    svc_ref = handler.get_service_reference()
                    if svc_ref is not None:
                        svc_id = svc_ref.get_property(pelix.SERVICE_ID)
                        result["services"][svc_id] = svc_ref

                # Dependencies
                result["dependencies"] = {}
                for dependency in stored_instance.get_handlers(
                                            constants.HANDLER_DEPENDENCY):
                    # Dependency
                    info = result["dependencies"][dependency.field] = {}
                    info["handler"] = type(dependency).__name__

                    # Requirement
                    req = dependency.requirement
                    info["specification"] = req.specification
                    if req.filter:
                        info["filter"] = str(req.filter)

                    info["optional"] = req.optional
                    info["aggregate"] = req.aggregate

                    # Bindings
                    info["bindings"] = dependency.get_bindings()

                # Properties
                properties = stored_instance.context.properties.items()
                result["properties"] = dict((str(key), str(value))
                                            for key, value in properties)

                # All done
                return result


    def get_factories(self):
        """
        Retrieves the names of the registered factories

        :return: A list of factories. Can be empty.
        """
        with self.__factories_lock:
            result = list(self.__factories.keys())
            result.sort()
            return result


    def get_factory_bundle(self, name):
        """
        Retrieves the Pelix Bundle object that registered the given factory

        :param name: The name of a factory
        :return: The Bundle that registered the given factory
        :raise ValueError: Invalid factory
        """
        with self.__factories_lock:
            if name not in self.__factories:
                raise ValueError("Unknown factory '{0}'".format(name))

            factory = self.__factories[name]

            # Bundle Context is stored in the Factory Context
            factory_context = getattr(factory, constants.IPOPO_FACTORY_CONTEXT)
            return factory_context.bundle_context.get_bundle()


    def get_factory_details(self, name):
        """
        Retrieves details about the given factory

        :param name: The name of a factory
        :return: A dictionary describing the factory
        :raise ValueError: Invalid factory
        """
        with self.__factories_lock:
            if name not in self.__factories:
                raise ValueError("Unknown factory '{0}'".format(name))

            factory = self.__factories[name]
            context = getattr(factory, constants.IPOPO_FACTORY_CONTEXT)
            assert isinstance(context, FactoryContext)

            result = {}
            # Factory name & bundle
            result["name"] = context.name
            result["bundle"] = context.bundle_context.get_bundle()

            # Configurable properties
            props = result["properties"] = {}
            for prop_name in context.properties_fields.values():
                # Name -> Default value
                props[prop_name] = context.properties.get(prop_name, None)

            # Requirements (list of dictionaries)
            reqs = result["requirements"] = []
            for field, requirement in context.requirements.items():
                req = {}
                # ID = Field name
                req["id"] = field
                req["aggregate"] = requirement.aggregate
                req["optional"] = requirement.optional

                # Give a copy of the required specifications
                req["specifications"] = requirement.specifications[:]

                # Give the string representation of the original LDAP filter
                req["filter"] = requirement.original_filter

                reqs.append(req)

            # Provided services (list of list of specifications)
            svc = result["services"] = []
            for specs_controller in context.provides:
                svc.append(specs_controller[0])

            return result

# ------------------------------------------------------------------------------

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


    def start(self, context):
        """
        The bundle has started

        :param context: The bundle context
        """
        assert isinstance(context, BundleContext)

        # Register the iPOPO service
        self._service = _IPopoService(context)
        self._registration = context.register_service(\
                                        constants.IPOPO_SERVICE_SPECIFICATION, \
                                        self._service, {})

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
        """
        The bundle has stopped

        :param context: The bundle context
        """
        assert isinstance(context, BundleContext)

        # The service is not in the "run" mode anymore
        self._service.running = False

        # Unregister the listener
        context.remove_bundle_listener(self._service)

        # Unregister the framework stop listener
        context.remove_framework_stop_listener(self._service)

        # Unregister the iPOPO service
        self._registration.unregister()

        # Clean up the service
        self._service._unregister_all_factories()

        # Clean up references
        self._registration = None
        self._service = None

# ------------------------------------------------------------------------------

# The activator instance
activator = _IPopoActivator()
