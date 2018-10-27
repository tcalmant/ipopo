#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
RequiresMap handler implementation

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
import logging
import threading

# Pelix beans
from pelix.constants import BundleActivator, BundleException
from pelix.internals.events import ServiceEvent

# iPOPO constants
import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class _HandlerFactory(constants.HandlerFactory):
    # pylint: disable=R0903
    """
    Factory service for service registration handlers
    """

    @staticmethod
    def _prepare_requirements(configs, requires_filters):
        """
        Overrides the filters specified in the decorator with the given ones

        :param configs: Field → (Requirement, key, allow_none) dictionary
        :param requires_filters: Content of the 'requires.filter' component
                                 property (field → string)
        :return: The new configuration dictionary
        """
        if not requires_filters or not isinstance(requires_filters, dict):
            # No explicit filter configured
            return configs

        # We need to change a part of the requirements
        new_requirements = {}
        for field, config in configs.items():
            # Extract values from tuple
            requirement, key, allow_none = config

            try:
                explicit_filter = requires_filters[field]

                # Store an updated copy of the requirement
                requirement_copy = requirement.copy()
                requirement_copy.set_filter(explicit_filter)
                new_requirements[field] = (requirement_copy, key, allow_none)

            except (KeyError, TypeError, ValueError):
                # No information for this one, or invalid filter:
                # keep the factory requirement
                new_requirements[field] = config

        return new_requirements

    def get_handlers(self, component_context, instance):
        """
        Sets up service providers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
        """
        # Extract information from the context
        configs = component_context.get_handler(
            ipopo_constants.HANDLER_REQUIRES_MAP
        )
        requires_filters = component_context.properties.get(
            ipopo_constants.IPOPO_REQUIRES_FILTERS, None
        )

        # Prepare requirements
        configs = self._prepare_requirements(configs, requires_filters)

        # Set up the runtime dependency handlers
        handlers = []
        for field, config in configs.items():
            # Extract values from tuple
            requirement, key, allow_none = config

            # Construct the handler
            if requirement.aggregate:
                handlers.append(
                    AggregateDependency(field, requirement, key, allow_none)
                )
            else:
                handlers.append(
                    SimpleDependency(field, requirement, key, allow_none)
                )

        return handlers


@BundleActivator
class _Activator(object):
    """
    The bundle activator
    """

    def __init__(self):
        """
        Sets up members
        """
        self._registration = None

    def start(self, context):
        """
        Bundle started
        """
        # Set up properties
        properties = {
            constants.PROP_HANDLER_ID: ipopo_constants.HANDLER_REQUIRES_MAP
        }

        # Register the handler factory service
        self._registration = context.register_service(
            constants.SERVICE_IPOPO_HANDLER_FACTORY,
            _HandlerFactory(),
            properties,
        )

    def stop(self, _):
        """
        Bundle stopped
        """
        # Unregister the service
        self._registration.unregister()
        self._registration = None


# ------------------------------------------------------------------------------


class _RuntimeDependency(constants.DependencyHandler):
    """
    Manages a required dependency field when a component is running
    """

    def __init__(self, field, requirement, key, allow_none):
        """
        Sets up the dependency

        :param field: The injected field name
        :param requirement: The Requirement describing this dependency
        :param key: The property used as key in the dictionary
        :param allow_none: Allow None property as key
        """
        # The internal state lock
        self._lock = threading.RLock()

        # The iPOPO StoredInstance object (given during manipulation)
        self._ipopo_instance = None

        # The bundle context
        self._context = None

        # The associated field
        self._field = field

        # The underlying requirement
        self.requirement = requirement

        # The property name
        self._key = key

        # Accept None values
        self._allow_none = allow_none

        # Reference -> Service
        self.services = {}

        # Future injected dictionary
        self._future_value = {}

    def manipulate(self, stored_instance, component_instance):
        """
        Stores the given StoredInstance bean.

        :param stored_instance: The iPOPO component StoredInstance
        :param component_instance: The component instance
        """
        # Store the stored instance...
        self._ipopo_instance = stored_instance

        # ... and the bundle context
        self._context = stored_instance.bundle_context

        # Set the default value for the field: an empty dictionary
        setattr(component_instance, self._field, {})

    def clear(self):
        """
        Cleans up the manager. The manager can't be used after this method has
        been called
        """
        self.services.clear()
        self._future_value.clear()

        self.services = None
        self._lock = None
        self._ipopo_instance = None
        self._context = None
        self.requirement = None
        self._key = None
        self._allow_none = None
        self._future_value = None
        self._field = None

    def get_bindings(self):
        """
        Retrieves the list of the references to the bound services

        :return: A list of ServiceReferences objects
        """
        with self._lock:
            return list(self.services.keys())

    def get_field(self):
        """
        Returns the name of the field handled by this handler
        """
        return self._field

    def get_kinds(self):
        """
        Retrieves the kinds of this handler: 'dependency'

        :return: the kinds of this handler
        """
        return (constants.KIND_DEPENDENCY,)

    def get_value(self):
        """
        Retrieves the value to inject in the component

        :return: The value to inject
        """
        # Return a copy of the future value
        with self._lock:
            # IronPython can't copy dictionary with a None key
            return copy.copy(self._future_value)

    def is_valid(self):
        """
        Tests if the dependency is in a valid state
        """
        return (
            self.requirement is not None and self.requirement.optional
        ) or bool(self._future_value)

    def on_service_arrival(self, svc_ref):
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        """
        raise NotImplementedError

    def on_service_departure(self, svc_ref):
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        """
        raise NotImplementedError

    def on_service_modify(self, svc_ref, old_properties):
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        :param old_properties: Previous properties values
        """
        raise NotImplementedError

    def service_changed(self, event):
        """
        Called by the framework when a service event occurs
        """
        if (
            self._ipopo_instance is None
            or not self._ipopo_instance.check_event(event)
        ):
            # stop() and clean() may have been called after we have been put
            # inside a listener list copy...
            # or we've been told to ignore this event
            return

        # Call sub-methods
        kind = event.get_kind()
        svc_ref = event.get_service_reference()

        if kind == ServiceEvent.REGISTERED:
            # Service coming
            self.on_service_arrival(svc_ref)

        elif kind in (
            ServiceEvent.UNREGISTERING,
            ServiceEvent.MODIFIED_ENDMATCH,
        ):
            # Service gone or not matching anymore
            self.on_service_departure(svc_ref)

        elif kind == ServiceEvent.MODIFIED:
            # Modified properties (can be a new injection)
            self.on_service_modify(svc_ref, event.get_previous_properties())

    def start(self):
        """
        Starts the dependency manager
        """
        self._context.add_service_listener(
            self, self.requirement.filter, self.requirement.specification
        )

    def stop(self):
        """
        Stops the dependency manager (must be called before clear())

        :return: The removed bindings (list) or None
        """
        self._context.remove_service_listener(self)
        if self.services:
            return [
                (service, reference)
                for reference, service in self.services.items()
            ]

        return None

    def try_binding(self):
        """
        Searches for the required service if needed

        :raise BundleException: Invalid ServiceReference found
        """
        with self._lock:
            if self.services:
                # We already are alive (not our first call)
                # => we are updated through service events
                return

            # Get all matching services
            refs = self._context.get_all_service_references(
                self.requirement.specification, self.requirement.filter
            )
            if not refs:
                # No match found
                return

            results = []
            try:
                # Bind all new reference
                for reference in refs:
                    added = self.on_service_arrival(reference)
                    if added:
                        results.append(reference)
            except BundleException as ex:
                # Get the logger for this instance
                logger = logging.getLogger(
                    "-".join((self._ipopo_instance.name, "RequiresMap-Runtime"))
                )
                logger.debug("Error binding multiple references: %s", ex)

                # Undo what has just been done, ignoring errors
                for reference in results:
                    try:
                        self.on_service_departure(reference)

                    except BundleException as ex2:
                        logger.debug("Error cleaning up: %s", ex2)

                del results[:]
                raise


class SimpleDependency(_RuntimeDependency):
    """
    Manages a simple dependency field: one service per dictionary key
    """

    def on_service_arrival(self, svc_ref):
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if svc_ref not in self.services:
                # Get the key property
                prop_value = svc_ref.get_property(self._key)
                if (
                    prop_value not in self._future_value
                    and prop_value is not None
                    or self._allow_none
                ):
                    # Matching new property value
                    service = self._context.get_service(svc_ref)

                    # Store the information
                    self._future_value[prop_value] = service
                    self.services[svc_ref] = service

                    # Call back iPOPO
                    self._ipopo_instance.bind(self, service, svc_ref)
                    return True

            return None

    def on_service_departure(self, svc_ref):
        """
        Called when a service has been unregistered from the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if svc_ref in self.services:
                # Get the service instance
                service = self.services.pop(svc_ref)

                # Get the key property
                prop_value = svc_ref.get_property(self._key)

                # Remove the injected service
                del self._future_value[prop_value]

                self._ipopo_instance.unbind(self, service, svc_ref)
                return True

            return None

    def on_service_modify(self, svc_ref, old_properties):
        """
        Called when a service has been modified in the framework

        :param svc_ref: A service reference
        :param old_properties: Previous properties values
        """
        with self._lock:
            if svc_ref not in self.services:
                # A previously registered service now matches our filter
                return self.on_service_arrival(svc_ref)
            else:
                # Get the property values
                old_value = old_properties.get(self._key)
                prop_value = svc_ref.get_property(self._key)
                service = self.services[svc_ref]

                if old_value != prop_value:
                    if (
                        prop_value is not None
                        or self._allow_none
                        and prop_value not in self._future_value
                    ):
                        # New property accepted and not yet in use
                        del self._future_value[old_value]
                        self._future_value[prop_value] = service

                        # Notify the property modification, with a value change
                        self._ipopo_instance.update(
                            self, service, svc_ref, old_properties, True
                        )
                    else:
                        # Consider the service as gone
                        del self._future_value[old_value]
                        del self.services[svc_ref]
                        self._ipopo_instance.unbind(self, service, svc_ref)
                else:
                    # Notify the property modification
                    self._ipopo_instance.update(
                        self, service, svc_ref, old_properties, False
                    )

            return None


class AggregateDependency(_RuntimeDependency):
    """
    Manages an aggregated dependency field: multiple services per dictionary
    key
    """

    def __store_service(self, key, service):
        """
        Stores the given service in the dictionary

        :param key: Dictionary key
        :param service: Service to add to the dictionary
        """
        self._future_value.setdefault(key, []).append(service)

    def __remove_service(self, key, service):
        """
        Removes the given service from the future dictionary

        :param key: Dictionary key
        :param service: Service to remove from the dictionary
        """
        try:
            # Remove the injected service
            prop_services = self._future_value[key]
            prop_services.remove(service)

            # Clean up
            if not prop_services:
                del self._future_value[key]

        except KeyError:
            # Ignore: can occur when removing a service with a None property,
            # if allow_none is False
            pass

    def get_value(self):
        """
        Retrieves the value to inject in the component

        :return: The value to inject
        """
        with self._lock:
            # The value field must be a deep copy of our dictionary
            if self._future_value is not None:
                return {
                    key: value[:] for key, value in self._future_value.items()
                }

            return None

    def on_service_arrival(self, svc_ref):
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        :return: True if the service is consumed
        """
        with self._lock:
            if svc_ref not in self.services:
                # Get the key property
                prop_value = svc_ref.get_property(self._key)
                if prop_value is not None or self._allow_none:
                    # Get the new service
                    service = self._context.get_service(svc_ref)

                    # Store the information
                    self.__store_service(prop_value, service)
                    self.services[svc_ref] = service

                    self._ipopo_instance.bind(self, service, svc_ref)
                    return True

            return None

    def on_service_departure(self, svc_ref):
        """
        Called when a service has been unregistered from the framework

        :param svc_ref: A service reference
        :return: A tuple (service, reference) if the service has been lost,
                 else None
        """
        with self._lock:
            if svc_ref in self.services:
                # Get the service instance
                service = self.services.pop(svc_ref)

                # Get the key property
                prop_value = svc_ref.get_property(self._key)

                # Remove the injected service
                self.__remove_service(prop_value, service)

                self._ipopo_instance.unbind(self, service, svc_ref)
                return True

            return None

    def on_service_modify(self, svc_ref, old_properties):
        """
        Called when a service has been modified in the framework

        :param svc_ref: A service reference
        :param old_properties: Previous properties values
        :return: A tuple (added, (service, reference)) if the dependency has
                 been changed, else None
        """
        with self._lock:
            if svc_ref not in self.services:
                # A previously registered service now matches our filter
                return self.on_service_arrival(svc_ref)
            else:
                # Get the property values
                service = self.services[svc_ref]
                old_value = old_properties.get(self._key)
                prop_value = svc_ref.get_property(self._key)

                if old_value != prop_value:
                    # Key changed
                    if prop_value is not None or self._allow_none:
                        # New property accepted
                        if old_value is not None or self._allow_none:
                            self.__remove_service(old_value, service)

                        self.__store_service(prop_value, service)

                        # Notify the property modification, with a value change
                        self._ipopo_instance.update(
                            self, service, svc_ref, old_properties, True
                        )
                    else:
                        # Consider the service as gone
                        self.__remove_service(old_value, service)
                        del self.services[svc_ref]
                        self._ipopo_instance.unbind(self, service, svc_ref)
                else:
                    # Simple property update
                    self._ipopo_instance.update(
                        self, service, svc_ref, old_properties, False
                    )

            return None
