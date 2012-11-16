#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Core iPOPO implementation

:author: Thomas Calmant
:copyright: Copyright 2012, isandlaTech
:license: GPLv3
:version: 0.4
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

__version__ = (0, 4, 0)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

from pelix.framework import BundleContext, ServiceEvent, BundleEvent, \
    Bundle, BundleException
from pelix.utilities import remove_all_occurrences, SynchronizedClassMethod, \
    add_listener, remove_listener, is_string

import pelix.ipopo.constants as constants
import pelix.framework as pelix
import pelix.ldapfilter as ldapfilter

# ------------------------------------------------------------------------------

import inspect
import logging
import threading

# ------------------------------------------------------------------------------

# Prepare the module logger
_logger = logging.getLogger("ipopo.core")

# ------------------------------------------------------------------------------

class Requirement(object):
    """
    Represents a component requirement
    """
    # The dictionary form fields (filter is a special case)
    __stored_fields__ = ('specifications', 'aggregate', 'optional')

    def __init__(self, specifications, aggregate=False, optional=False,
                 spec_filter=None):
        """
        Sets up the requirement

        :param specifications: The requirement specification (can't be None)
        :param aggregate: If true, this requirement represents a list
        :param optional: If true, this requirement is optional
        :param spec_filter: A filter to select dependencies

        :raise TypeError: A parameter has an invalid type
        :raise ValueError: An error occurred while parsing the filter
        """
        if not isinstance(specifications, (list, tuple)):
            raise TypeError("Specifications must be a list/tuple of strings")

        if not specifications:
            raise ValueError("A specification must be given")

        self.aggregate = aggregate
        self.optional = optional
        self.specifications = specifications

        # Original filter keeper
        self.__original_filter = None

        # Set up the requirement filter (after setting up self.specification)
        self.filter = None
        self.set_filter(spec_filter)


    def __eq__(self, other):
        """
        Equality test
        """
        if other is self:
            # Identity check
            return True

        if not isinstance(other, Requirement):
            # Different types
            return False

        if self.aggregate != other.aggregate or self.optional != other.optional:
            # Different flags
            return False

        if self.filter != other.filter:
            # Different filters (therefore different specifications)
            return False

        return True


    def __ne__(self, other):
        """
        Inequality test
        """
        return not self.__eq__(other)


    def copy(self):
        """
        Returns a copy of this instance

        :return: A copy of this instance
        """
        return Requirement(self.specifications, self.aggregate, self.optional,
                           self.__original_filter)


    @classmethod
    def from_dictionary_form(cls, dictionary):
        """
        Sets up an instance with the given dictionary form

        :param dictionary: The dictionary form
        :return: A configured requirement instance
        :raise ValueError: An attribute is missing in the dictionary form
        :raise TypeError: Invalid form type (only dictionaries are accepted)
        """
        if not isinstance(dictionary, dict):
            raise TypeError("Invalid form type '{0}'".format(
                                                     type(dictionary).__name__))

        if not "specifications" in dictionary:
            raise ValueError("Missing specifications in the dictionary form")

        specs = dictionary["specifications"]
        aggregate = dictionary.get("aggregate", False)
        optional = dictionary.get("optional", False)
        spec_filter = ldapfilter.get_ldap_filter(dictionary.get("filter", None))

        return cls(specs, aggregate, optional, spec_filter)


    def matches(self, properties):
        """
        Tests if the given _StoredInstance matches this requirement

        :param properties: Service properties
        :return: True if the instance matches this requirement
        """
        if properties is None:
            # No properties : invalid service
            return False

        assert isinstance(properties, dict)

        # Properties filter test
        return self.filter.matches(properties)


    def set_filter(self, spec_filter):
        """
        Changes the current filter for the given one

        :param spec_filter: The new requirement filter
        :raise TypeError: Unknown filter type
        """
        if spec_filter is not None and not is_string(spec_filter) \
        and not isinstance(spec_filter,
                           (ldapfilter.LDAPFilter, ldapfilter.LDAPCriteria)):
            # Unknown type
            raise TypeError("Invalid filter type {0}".format(
                                                    type(spec_filter).__name__))

        ldap_criteria = []
        for spec in self.specifications:
            ldap_criteria.append("({0}={1})".format(pelix.OBJECTCLASS,
                                                ldapfilter.escape_LDAP(spec)))

        # Make the filter, escaping the specification name
        ldap_filter = "(|{0})".format("".join(ldap_criteria))

        if spec_filter is not None:
            # Filter given, keep its string form
            self.__original_filter = str(spec_filter)
            ldap_filter = ldapfilter.combine_filters([ldap_filter, spec_filter])

        else:
            # No filter
            self.__original_filter = None

        # Parse the filter
        self.filter = ldapfilter.get_ldap_filter(ldap_filter)


    def to_dictionary_form(self):
        """
        Returns a dictionary form of the current object

        :raise AttributeError: A field to store is missing in the instance
        """
        result = {}
        for field in self.__stored_fields__:
            result[field] = getattr(self, field)

        # Special case: store the original filter
        result['filter'] = self.__original_filter

        return result

# ------------------------------------------------------------------------------

class _RuntimeDependency(object):
    """
    Manages a required dependency field when a component is running
    """
    def __init__(self, stored_instance, field, requirement):
        """
        Sets up the dependency
        
        :param stored_instance: The iPOPO component StoredInstance object
        :param field: The injected field name
        :param requirement: The Requirement describing this dependency
        """
        # The internal state lock
        self._lock = threading.RLock()

        # The iPOPO StoredInstance object
        self._ipopo_instance = stored_instance

        # The bundle context
        self._context = self._ipopo_instance.bundle_context

        # The associated field
        self.field = field

        # The underlying requirement
        self.requirement = requirement

        # Current field value
        self._value = None


    def clear(self):
        """
        Cleans up the manager. The manager can't be used after this method has
        been called
        
        :return: The removed bindings (list) or None
        """
        self._lock = None
        self._ipopo_instance = None
        self._context = None
        self.requirement = None
        self._value = None
        self.field = None


    def get_bindings(self):
        """
        Retrieves the list of the references to the bound services
        
        :return: A list of ServiceReferences objects
        """
        raise NotImplementedError


    def get_kinds(self):
        """
        Retrieves the kinds of this handler: 'dependency'
        
        :return: the kinds of this handler
        """
        return (constants.HANDLER_DEPENDENCY,)


    def get_value(self):
        """
        Retrieves the value to inject in the component (can be different of
        self._value)
        
        :return: The value to inject
        """
        return self._value


    def is_valid(self):
        """
        Tests if the dependency is in a valid state
        """
        return (self.requirement is not None and self.requirement.optional) \
            or self._value is not None


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


    def on_service_modify(self, svc_ref):
        """
        Called when a service has been registered in the framework
        
        :param svc_ref: A service reference
        """
        raise NotImplementedError


    def service_changed(self, event):
        """
        Called by the framework when a service event occurs
        """
        if not self._ipopo_instance.check_event(event):
            # We've been told to ignore this event
            return

        # Call sub-methods
        kind = event.get_type()
        svc_ref = event.get_service_reference()

        if kind == ServiceEvent.REGISTERED:
            # Service coming
            self.on_service_arrival(svc_ref)

        elif kind in (ServiceEvent.UNREGISTERING,
                      ServiceEvent.MODIFIED_ENDMATCH):
            # Service gone or not matching anymore
            self.on_service_departure(svc_ref)

        elif kind == ServiceEvent.MODIFIED:
            # Modified properties (can be a new injection)
            self.on_service_modify(svc_ref)


    def start(self):
        """
        Starts the dependency manager
        """
        self._context.add_service_listener(self, self.requirement.filter)


    def stop(self):
        """
        Stops the dependency manager (must be called before clear())
        """
        self._context.remove_service_listener(self)


class _SimpleDependency(_RuntimeDependency):
    """
    Manages a simple dependency field
    """
    def __init__(self, stored_instance, field, requirement):
        """
        Sets up the dependency
        """
        super(_SimpleDependency, self).__init__(stored_instance, field,
                                                requirement)

        # We have only one reference to keep
        self.reference = None


    def clear(self):
        """
        Cleans up the manager. The manager can't be used after this method has
        been called
        
        :return: The removed bindings (list) or None
        """
        self.reference = None
        super(_SimpleDependency, self).clear()


    def get_bindings(self):
        """
        Retrieves the list of the references to the bound services
        
        :return: A list of ServiceReferences objects
        """
        result = []
        with self._lock:
            if self.reference:
                result.append(self.reference)

        return result


    def on_service_arrival(self, svc_ref):
        """
        Called when a service has been registered in the framework
        
        :param svc_ref: A service reference
        """
        with self._lock:
            if self._value is None:
                # Inject the service
                self.reference = svc_ref
                self._value = self._context.get_service(svc_ref)

                self._ipopo_instance.bind(self, self._value, self.reference)
                return True


    def on_service_departure(self, svc_ref):
        """
        Called when a service has been unregistered from the framework
        
        :param svc_ref: A service reference
        """
        with self._lock:
            if svc_ref is self.reference:
                # Store the current values
                service, reference = self._value, self.reference

                # Clean the instance values
                self._value = None
                self.reference = None

                self._ipopo_instance.unbind(self, service, reference)
                return True


    def on_service_modify(self, svc_ref):
        """
        Called when a service has been modified in the framework
        
        :param svc_ref: A service reference
        """
        with self._lock:
            if self.reference is None:
                # A previously registered service now matches our filter
                return self.on_service_arrival(svc_ref)


    def stop(self):
        """
        Stops the dependency manager (must be called before clear())
        """
        super(_SimpleDependency, self).stop()
        if self.reference is not None:
            # Use a list
            result = [(self._value, self.reference)]
        else:
            result = None

        return result


    def try_binding(self):
        """
        Searches for the required service if needed
        
        :raise BundleException: Invalid ServiceReference found
        """
        with self._lock:
            if self.reference is not None:
                # Already bound
                return

            # Get all matching services
            ref = self._context.get_service_reference(None,
                                                      self.requirement.filter)
            if ref is not None:
                # Found a service
                self.on_service_arrival(ref)


class _AggregateDependency(_RuntimeDependency):
    """
    Manages an aggregated dependency field
    """
    def __init__(self, stored_instance, field, requirement):
        """
        Sets up the dependency
        """
        super(_AggregateDependency, self).__init__(stored_instance, field,
                                                   requirement)
        # Reference -> Service
        self.services = {}

        # Future injected value
        self._future_value = None


    def clear(self):
        """
        Cleans up the manager. The manager can't be used after this method has
        been called
        
        :return: The removed bindings (list) or None
        """
        self.services.clear()
        self.services = None

        if self._future_value is not None:
            del self._future_value[:]
            self._future_value = None

        super(_AggregateDependency, self).clear()


    def get_bindings(self):
        """
        Retrieves the list of the references to the bound services
        
        :return: A list of ServiceReferences objects
        """
        with self._lock:
            return list(self.services.keys())


    def get_value(self):
        """
        Retrieves the value to inject in the component (can be different of
        self._value)
        
        :return: The value to inject
        """
        with self._lock:
            # The value field must be a copy of our list
            if self._future_value is not None:
                self._value = self._future_value[:]
            else:
                self._value = None

            return self._value


    def is_valid(self):
        """
        Tests if the dependency is in a valid state
        """
        return (self.requirement is not None and self.requirement.optional) \
            or self._future_value is not None


    def on_service_arrival(self, svc_ref):
        """
        Called when a service has been registered in the framework
        
        :param svc_ref: A service reference
        """
        with self._lock:
            if svc_ref not in self.services:
                # Get the new service
                service = self._context.get_service(svc_ref)

                if self._future_value is None:
                    # First value
                    self._future_value = []

                # Store the information
                self._future_value.append(service)
                self.services[svc_ref] = service

                self._ipopo_instance.bind(self, service, svc_ref)
                return True


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
                service = self.services[svc_ref]

                # Clean the instance values
                del self.services[svc_ref]
                self._future_value.remove(service)

                # Nullify the value if needed
                if not self._future_value:
                    self._future_value = None

                self._ipopo_instance.unbind(self, service, svc_ref)
                return True


    def on_service_modify(self, svc_ref):
        """
        Called when a service has been modified in the framework
        
        :param svc_ref: A service reference
        :return: A tuple (added, (service, reference)) if the dependency has
                 been changed, else None
        """
        with self._lock:
            if svc_ref not in self.services:
                # A previously registered service now matches our filter
                return self.on_service_arrival(svc_ref)


    def stop(self):
        """
        Stops the dependency manager (must be called before clear())
        """
        super(_AggregateDependency, self).stop()

        if self.services:
            results = [(service, reference)
                       for reference, service in self.services.items()]

        else:
            results = None

        return results


    def try_binding(self):
        """
        Searches for the required service if needed
        
        :raise BundleException: Invalid ServiceReference found
        """
        with self._lock:
            # Get all matching services
            refs = self._context.get_all_service_references(None,
                                                        self.requirement.filter)
            if not refs:
                # No match found
                return

            # Filter found references
            refs = [reference for reference in refs
                    if reference not in self.services]
            if not refs:
                # No new match found
                return

            results = []
            try:
                # Bind all new reference
                for reference in refs:
                    added = self.on_service_arrival(reference)
                    if added:
                        results.append(reference)

            except BundleException as ex:
                _logger.debug("Error binding multiple references: %s", ex)

                # Undo what has just been done, ignoring errors
                for reference in results:
                    try:
                        self.on_service_departure(reference)

                    except BundleException as ex2:
                        _logger.debug("Error cleaning up: %s", ex2)

                del results[:]
                raise

# ------------------------------------------------------------------------------

class _ServiceRegistrationHandler(object):
    """
    Handles the registration of a service provided by a component
    """
    def __init__(self, specifications, controller_name, ipopo_instance):
        """
        Sets up the handler
        
        :param specifications: The service specifications
        :param controller_name: Name of the associated service controller
                                (can be None)
        :param ipopo_instance: The iPOPO component StoredInstance
        """
        self.specifications = specifications
        self._ipopo_instance = ipopo_instance

        self.__controller = controller_name
        # Controller is "on" by default
        self.__controller_on = True
        self.__validated = False

        # The ServiceRegistration and ServiceReference objects
        self._registration = None
        self._svc_reference = None


    def check_event(self, svc_event):
        """
        Tests if the given service event corresponds to the registered service
        
        :param svc_event: A service event
        :return: True if the given event references the provided service 
        """
        return self._svc_reference is not svc_event.get_service_reference()


    def get_kinds(self):
        """
        Retrieves the kinds of this handler: 'service_provider'
        
        :return: the kinds of this handler
        """
        return (constants.HANDLER_SERVICE_PROVIDER,)


    def get_service_reference(self):
        """
        Retrieves the reference of the provided service
        
        :return: A ServiceReference object
        """
        return self._svc_reference


    def on_controller_change(self, name, value):
        """
        Called by the instance manager when a controller value has been modified
        
        :param name: The name of the controller
        :param value: The new value of the controller
        """
        if self.__controller != name:
            # Nothing to do
            return

        # Update the controller value
        self.__controller_on = value
        if value:
            # Controller switched to "ON"
            self._register_service()

        else:
            # Controller switched to "OFF"
            self._unregister_service()


    def on_property_change(self, name, old_value, new_value):
        """
        Called by the instance manager when a component property is modified

        :param name: The changed property name
        :param old_value: The previous property value
        :param new_value: The new property value
        """
        if self._registration is not None:
            # use the registration to trigger the service event
            self._registration.set_properties({name: new_value})


    def post_validate(self):
        """
        Called by the instance manager once the component has been validated
        """
        # Update the validation flag
        self.__validated = True
        self._register_service()


    def pre_invalidate(self):
        """
        Called by the instance manager before the component is invalidated
        """
        # Update the validation flag
        self.__validated = False

        # Force service unregistration
        self._unregister_service()


    def _register_service(self):
        """
        Registers the provided service, if possible
        """
        if self._registration is None and self.specifications \
        and self.__validated and self.__controller_on:
            # Use a copy of component properties
            properties = self._ipopo_instance.context.properties.copy()
            bundle_context = self._ipopo_instance.bundle_context

            # Register the service
            self._registration = bundle_context.register_service(
                                            self.specifications,
                                            self._ipopo_instance.instance,
                                            properties)
            self._svc_reference = self._registration.get_reference()


    def _unregister_service(self):
        """
        Unregisters the provided service, if needed
        """
        if self._registration is not None:
            # Ignore error
            try:
                self._registration.unregister()

            except BundleException as ex:
                # Only log the error at this level
                _logger.error("Error unregistering a component service: %s", ex)

            self._registration = None
            self._svc_reference = None

# ------------------------------------------------------------------------------

class FactoryContext(object):
    """
    Represents the data stored in a component factory (class)
    """

    __basic_fields = ('callbacks', 'name', 'properties', 'properties_fields',
                      'provides')

    def __init__(self):
        """
        Sets up the factory context
        """
        # Factory bundle context
        self.bundle_context = None

        # Callbacks : Kind -> callback method
        self.callbacks = {}

        # The factory name
        self.name = None

        # Properties : Name -> Value
        self.properties = {}

        # Properties fields : Field name -> Property name
        self.properties_fields = {}

        # Provided specifications:
        # Array of tuples (specifications(arrays of strings), controller name)
        self.provides = []

        # Requirements : Field name -> Requirement object
        self.requirements = {}


    def __eq__(self, other):
        """
        Equality test
        """
        if other is self:
            # Identity
            return True

        if not isinstance(other, FactoryContext):
            # Different types
            return False

        # Do not compare the bundle context, as it must not be stored
        for field in ('name', 'callbacks', 'properties', 'properties_fields',
                      'requirements'):
            # Comparable fields
            if getattr(self, field, None) != getattr(other, field, None):
                return False

        # Treat the list differently
        if len(self.provides) != len(other.provides):
            return False

        for provided in self.provides:
            if provided not in other.provides:
                # Missing a provided service
                return False

        return True

    def __ne__(self, other):
        """
        Inequality test
        """
        return not self.__eq__(other)


    def copy(self):
        """
        Returns a copy of the current FactoryContext instance
        """
        context = FactoryContext()

        direct = ("bundle_context", "name")
        copied = ("callbacks", "properties", "properties_fields",
                  "requirements")
        lists = ("provides",)

        # Direct copy of primitive values
        for entry in direct:
            setattr(context, entry, getattr(self, entry))

        # Copy "complex" values
        for entry in copied:
            value = getattr(self, entry)
            if value is not None:
                value = value.copy()

            setattr(context, entry, value)

        # Copy lists
        for entry in lists:
            value = getattr(self, entry)
            if value is not None:
                value = value[:]

            setattr(context, entry, value)

        return context


    @classmethod
    def from_dictionary_form(cls, dictionary):
        """
        Sets up this instance with the given dictionary form

        :param dictionary: The dictionary form
        :raise ValueError: An attribute is missing in the dictionary form
        :raise TypeError: Invalid form type (only dictionaries are accepted)
        """
        if not isinstance(dictionary, dict):
            raise TypeError("Invalid form type '{0}'".format(
                                                    type(dictionary).__name__))

        # Prepare the instance, initializing it
        instance = cls()

        # Basic fields
        for field in cls.__basic_fields:
            if field not in dictionary:
                raise ValueError("Incomplete dictionary form: missing {0}" \
                                 .format(field))

            setattr(instance, field, dictionary[field])

        # Requirements field
        if 'requirements' not in dictionary:
            raise ValueError("Incomplete dictionary form: missing " \
                             "'requirements'")

        requirements = dictionary['requirements']
        if not isinstance(requirements, dict):
            raise TypeError("Only dictionaries are handled for 'requirements'")

        for field, requirement_dict in requirements.items():
            instance.requirements[field] = Requirement.from_dictionary_form(\
                                                            requirement_dict)

        return instance


    def set_bundle_context(self, bundle_context):
        """
        Sets up the bundle context associated to this factory context

        :param bundle_context: The factory bundle context
        """
        if self.bundle_context is None:
            assert isinstance(bundle_context, BundleContext)
            self.bundle_context = bundle_context


    def to_dictionary_form(self):
        """
        Returns a dictionary form of the current object

        :raise AttributeError: A field to store in missing in the instance
        """
        result = {}

        # Fields with standard Python types (no conversion needed)
        for entry in self.__basic_fields:
            result[entry] = getattr(self, entry)

        # Requirements field
        requirements = {}
        for field, requirement in self.requirements.items():
            requirements[field] = requirement.to_dictionary_form()

        result['requirements'] = requirements
        return result


class ComponentContext(object):
    """
    Represents the data stored in a component instance
    """

    # Try to reduce memory footprint (stored __instances)
    __slots__ = ('factory_context', 'name', 'properties', 'requirements')

    def __init__(self, factory_context, name, properties):
        """
        Sets up the context

        :param factory_context: The parent factory context
        :param properties: The component properties
        """
        assert isinstance(factory_context, FactoryContext)
        assert isinstance(properties, dict)

        self.factory_context = factory_context
        self.name = name

        # Force the instance name property
        properties[constants.IPOPO_INSTANCE_NAME] = name

        self.properties = factory_context.properties.copy()
        self.properties.update(properties)

        requires_filters = self.properties.get(\
                                        constants.IPOPO_REQUIRES_FILTERS, None)

        if not requires_filters or not isinstance(requires_filters, dict):
            # No explicit filter configured
            self.requirements = factory_context.requirements

        else:
            # We need to change a part of the requirements
            self.requirements = {}
            for field, requirement in factory_context.requirements.items():

                if field not in requires_filters:
                    # No information for this one, keep the factory requirement
                    self.requirements[field] = requirement

                else:
                    try:
                        # Use a copy of the requirement
                        requirement_copy = requirement.copy()
                        requirement_copy.set_filter(requires_filters[field])

                        self.requirements[field] = requirement_copy

                    except (TypeError, ValueError):
                        # Invalid filter, use the factory requirement
                        self.requirements[field] = requirement


    def get_bundle_context(self):
        """
        Retrieves the bundle context

        :return: The component bundle context
        """
        return self.factory_context.bundle_context


    def get_callback(self, event):
        """
        Retrieves the registered method for the given event. Returns None if not
        found

        :param event: A component life cycle event
        :return: The callback associated to the given event
        """
        return self.factory_context.callbacks.get(event, None)


    def get_factory_name(self):
        """
        Retrieves the component factory name

        :return: The component factory name
        """
        return self.factory_context.name


    def get_provides(self):
        """
        Retrieves the services provided by this component.
        Returns an array containing arrays of specifications.

        :return: An array of tuples (specifications, controller)
        """
        return self.factory_context.provides



class _StoredInstance(object):
    """
    Represents a component instance
    """
    # Try to reduce memory footprint (stored instances)
    __slots__ = ('bundle_context', 'context', 'factory_name', 'instance',
                 'name', 'state', '_controllers_state', '_handlers',
                 '_ipopo_service', '_lock')

    INVALID = 0
    """ This component has been invalidated """

    VALID = 1
    """ This component has been validated """

    KILLED = 2
    """ This component has been killed """

    VALIDATING = 3
    """ This component is currently validating """

    def __init__(self, ipopo_service, context, instance):
        """
        Sets up the instance object

        :param ipopo_service: The iPOPO service that instantiated this component
        :param context: The component context
        :param instance: The component instance
        """
        assert isinstance(context, ComponentContext)

        # The lock
        self._lock = threading.RLock()

        # The iPOPO service
        self._ipopo_service = ipopo_service

        # Component context
        self.context = context

        # The instance name
        self.name = self.context.name

        # Factory name
        self.factory_name = self.context.get_factory_name()

        # Component instance
        self.instance = instance

        # Set the instance state
        self.state = _StoredInstance.INVALID

        # Store the bundle context
        self.bundle_context = self.context.get_bundle_context()

        # The controllers state dictionary
        self._controllers_state = {}

        # Handlers...
        self._handlers = {}

        # The provided services handlers
        for specs, controller in self.context.get_provides():
            handler = _ServiceRegistrationHandler(specs, controller, self)

            for kind in handler.get_kinds():
                self._handlers.setdefault(kind, []).append(handler)

        # The runtime dependency handlers
        for field, requirement in context.requirements.items():
            if requirement.aggregate:
                handler = _AggregateDependency(self, field, requirement)
            else:
                handler = _SimpleDependency(self, field, requirement)

            for kind in handler.get_kinds():
                self._handlers.setdefault(kind, []).append(handler)


    def __repr__(self):
        """
        String representation
        """
        return self.__str__()


    def __str__(self):
        """
        String representation
        """
        return "StoredInstance(Name={0}, State={1})".format(self.name,
                                                            self.state)


    def check_event(self, event):
        """
        Tests if the given service event must be handled or ignored, based
        on the state of the iPOPO service and on the content of the event.
        
        :param event: A service event
        :return: True if the event can be handled, False if it must be ignored
        """
        with self._lock:
            if self.state == _StoredInstance.KILLED:
                # This call may have been blocked by the internal state lock,
                # ignore it
                return False

            return self.__safe_handlers_callback('check_event', event)


    def bind(self, dependency, svc, svc_ref):
        """
        Called by a dependency manager to inject a new service and update the
        component life cycle.
        """
        with self._lock:
            self.__set_binding(dependency, svc, svc_ref)
            self.check_lifecycle()


    def unbind(self, dependency, svc, svc_ref):
        """
        Called by a dependency manager to remove an injected service and to
        update the component life cycle.
        """
        with self._lock:
            # Invalidate first (if needed)
            self.check_lifecycle()

            # Call unbind() and remove the injection
            self.__unset_binding(dependency, svc, svc_ref)

            # Try a new configuration
            if self.update_bindings():
                self.check_lifecycle()


    def get_controller_state(self, name):
        """
        Retrieves the state of the controller with the given name
        
        :param name: The name of the controller
        :return: The value of the controller
        :raise KeyError: No value associated to this controller
        """
        return self._controllers_state[name]


    def set_controller_state(self, name, value):
        """
        Sets the state of the controller with the given name
        
        :param name: The name of the controller
        :param value: The new value of the controller
        """
        with self._lock:
            self._controllers_state[name] = value
            self.__safe_handlers_callback('on_controller_change', name, value)


    def update_property(self, name, old_value, new_value):
        """
        Handles a property changed event

        :param name: The changed property name
        :param old_value: The previous property value
        :param new_value: The new property value
        """
        with self._lock:
            self.__safe_handlers_callback('on_property_change', name, old_value,
                                          new_value)


    def get_handlers(self, kind=None):
        """
        Retrieves the handlers of the given kind. If kind is None, all handlers
        are returned.
        
        :param kind: The kind of the handlers to return
        :return: A list of handlers, or an empty list
        """
        with self._lock:
            if kind is not None:
                return self._handlers.get(kind, [])

            # Prepare the list of handlers to call
            result = []
            for handlers_list in self._handlers.values():
                for handler in handlers_list:
                    if handler not in result:
                        result.append(handler)

            return result


    def check_lifecycle(self):
        """
        Tests if the state of the component must be updated, based on its own
        state and on the state of its dependencies
        """
        with self._lock:
            # Validation flags
            was_valid = (self.state == _StoredInstance.VALID)
            can_validate = self.state not in (_StoredInstance.VALIDATING,
                                              _StoredInstance.VALID)

            # Test the validity of all handlers
            handlers_valid = self.__safe_handlers_callback('is_valid',
                                                           break_on_false=True)

            # A dependency is missing
            if was_valid and not handlers_valid:
                self.invalidate(True)

            # We're all good
            elif can_validate and handlers_valid \
            and self._ipopo_service.running:
                self.validate(True)


    def update_bindings(self):
        """
        Updates the bindings of the given component

        :return: True if the component can be validated
        """
        with self._lock:
            all_valid = True
            for handler in self._handlers.get(constants.HANDLER_DEPENDENCY, []):
                # Try to bind
                self.__safe_handler_callback(handler, 'try_binding')

                # Update the validity flag
                all_valid &= self.__safe_handler_callback(handler, 'is_valid',
                                                          only_boolean=True,
                                                          none_as_true=True)

            return all_valid


    def start(self):
        """
        Starts the handlers
        """
        with self._lock:
            self.__safe_handlers_callback('start')


    def invalidate(self, callback=True):
        """
        Applies the component invalidation.

        :param callback: If True, call back the component before the
                         invalidation
        """
        with self._lock:
            if self.state != _StoredInstance.VALID:
                # Instance is not running...
                return

            # Change the state
            self.state = _StoredInstance.INVALID

            # Call the handlers
            self.__safe_handlers_callback('pre_invalidate')

            # Call the component
            if callback:
                self.__safe_callback(constants.IPOPO_CALLBACK_INVALIDATE,
                                   self.bundle_context)

                # Trigger an "Invalidated" event
                self._ipopo_service._fire_ipopo_event(
                                              constants.IPopoEvent.INVALIDATED,
                                              self.factory_name, self.name)

            # Call the handlers
            self.__safe_handlers_callback('post_invalidate')


    def kill(self):
        """
        This instance is killed : invalidate it if needed, clean up all members

        When this method is called, this _StoredInstance object must have
        been removed from the registry
        """
        with self._lock:
            # Already dead...
            if self.state == _StoredInstance.KILLED:
                return

            # Unregister from service events
            self.bundle_context.remove_service_listener(self)

            try:
                self.invalidate(True)

            except:
                _logger.exception("%s: Error invalidating the instance",
                                  self.name)

            # Now that we are nearly clean, be sure we were in a good registry
            # state
            assert not self._ipopo_service.is_registered_instance(self.name)

            # Stop all handlers (can tell to unset a binding)
            for handler in self.get_handlers():
                results = self.__safe_handler_callback(handler, 'stop')
                if results:
                    try:
                        for binding in results:
                            self.__unset_binding(handler, binding[0],
                                                 binding[1])

                    except Exception as ex:
                        _logger.exception("Error stopping handler '%s': %s",
                                          handler, ex)

            # Call the handlers
            self.__safe_handlers_callback('clear')

            # Change the state
            self.state = _StoredInstance.KILLED

            # Trigger the event
            self._ipopo_service._fire_ipopo_event(constants.IPopoEvent.KILLED,
                                                  self.factory_name, self.name)

            # Clean up members
            self._handlers.clear()
            self._handlers = None
            self.context = None
            self.instance = None
            self._ipopo_service = None


    def validate(self, safe_callback=True):
        """
        Ends the component validation, registering services

        :param safe_callback: If True, calls the component validation callback
        :raise RuntimeError: You try to awake a dead component
        """
        with self._lock:
            if self.state in (_StoredInstance.VALID,
                              _StoredInstance.VALIDATING):
                # No work to do (yet)
                return

            if self.state == _StoredInstance.KILLED:
                raise RuntimeError("{0}: Zombies !".format(self.name))

            # Call the handlers
            self.__safe_handlers_callback('pre_validate')

            if safe_callback:
                # Safe call back needed and not yet passed
                self.state = _StoredInstance.VALIDATING
                if not self.__safe_callback(constants.IPOPO_CALLBACK_VALIDATE,
                                            self.bundle_context):
                    # Stop there if the callback failed
                    self.invalidate(True)
                    return

            # All good
            self.state = _StoredInstance.VALID

            # Call the handlers
            self.__safe_handlers_callback('post_validate')

            # We may have caused a framework error, so check if iPOPO is active
            if self._ipopo_service is not None:
                # Trigger the iPOPO event (after the service _registration)
                self._ipopo_service._fire_ipopo_event(
                                              constants.IPopoEvent.VALIDATED,
                                              self.factory_name, self.name)


    def __callback(self, event, *args, **kwargs):
        """
        Calls the registered method in the component for the given event

        :param event: An event (IPOPO_CALLBACK_VALIDATE, ...)
        :return: The callback result, or None
        :raise Exception: Something went wrong
        """
        with self._lock:
            comp_callback = self.context.get_callback(event)
            if not comp_callback:
                # No registered callback
                return True

            # Call it
            result = comp_callback(self.instance, *args, **kwargs)
            if result is None:
                # Special case, if the call back returns nothing
                return True

            return result


    def __safe_callback(self, event, *args, **kwargs):
        """
        Calls the registered method in the component for the given event,
        ignoring raised exceptions

        :param event: An event (IPOPO_CALLBACK_VALIDATE, ...)
        :return: The callback result, or None
        """
        with self._lock:
            if self.state == _StoredInstance.KILLED:
                # Invalid state
                return None

            try:
                return self.__callback(event, *args, **kwargs)

            except pelix.FrameworkException as ex:
                # Important error
                _logger.exception("Critical error calling back %s: %s",
                                  self.name, ex)

                # Kill the component
                self._ipopo_service.kill(self.name)

                if ex.needs_stop:
                    # Framework must be stopped...
                    _logger.error("%s said that the Framework must be stopped.",
                                  self.name)
                    self.bundle_context.get_bundle(0).stop()
                return False

            except:
                _logger.exception("Component '{0}' : error calling callback " \
                                  "method for event {1}".format(self.name,
                                                                event))
                return False


    def __safe_handler_callback(self, handler, method_name, *args, **kwargs):
        """
        Calls the given method with the given arguments in the given handler.
        Logs exceptions, but doesn't propagate them.
        
        Special arguments can be given in kwargs:
        
        * 'none_as_true': If set to True and the method returned None or doesn't
                          exist, the result is considered as True.
                          If set to False, None result is kept as is.
                          Default is False.
        * 'only_boolean': If True, the result can only be True or False, else
                          the result is the value returned by the method.
                          Default is False.
        
        :param handler: The handler to call
        :param method_name: The name of the method to call
        :param args: List of arguments for the method to call
        :param kwargs: Dictionary of arguments for the method to call and to
                       control the call
        :return: The method result, or None on error
        """
        if handler is None or method_name is None:
            return None

        # Behavior flags
        only_boolean = kwargs.pop('only_boolean', False)
        none_as_true = kwargs.pop('none_as_true', False)

        # Get the method for each handler
        result = None
        method = getattr(handler, method_name, None)
        if method is not None:
            try:
                # Call it
                result = method(*args, **kwargs)

            except Exception as ex:
                # Log errors
                _logger.exception("Error calling handler '%s': %s", handler, ex)

        if result is None and none_as_true:
            # Consider None (nothing returned) as True
            result = True

        if only_boolean:
            # Convert to a boolean result
            result = only_boolean and result

        return result


    def __safe_handlers_callback(self, method_name, *args, **kwargs):
        """
        Calls the given method with the given arguments in all handlers.
        Logs exceptions, but doesn't propagate them.
        Methods called in handlers must return None, True or False.
        
        Special parameters can be given in kwargs:
        
        * 'exception_as_error': if it is set to True and an exception is raised
          by a handler, then this method will return False. By default, this
          flag is set to False and exceptions are ignored.
        * 'break_on_false': if it set to True, the loop calling the handler
          will stop after an handler returned False. By default, this flag
          is set to False, and all handlers are called.
        
        :param method_name: Name of the method to call
        :param args: List of arguments for the method to call
        :param kwargs: Dictionary of arguments for the method to call and the
                       behavior of the call
        :return: True if all handlers returned True (or None), else False
        """
        with self._lock:
            if self.state == _StoredInstance.KILLED:
                # Nothing to do
                return False

            # Behavior flags
            exception_as_error = kwargs.pop('exception_as_error', False)
            break_on_false = kwargs.pop('break_on_false', False)

            result = True
            for handler in self.get_handlers():
                # Get the method for each handler
                method = getattr(handler, method_name, None)
                if method is not None:
                    try:
                        # Call it
                        res = method(*args, **kwargs)
                        if res is not None and not res:
                            # Ignore 'None' results
                            result = False

                    except Exception as ex:
                        # Log errors
                        _logger.exception("Error calling handler '%s': %s",
                                          handler, ex)

                        # We can consider exceptions as errors or ignore them
                        result &= not exception_as_error

                    if not handler and break_on_false:
                        # The loop can stop here
                        break

            return result


    def __set_binding(self, dependency, service, reference):
        """
        Injects a service in the component

        :param dependency: The dependency handler
        :param service: The injected service
        :param reference: The reference of the injected service
        """
        with self._lock:
            # Set the value
            setattr(self.instance, dependency.field, dependency.get_value())

            # Call the component back
            self.__safe_callback(constants.IPOPO_CALLBACK_BIND,
                                 service, reference)


    def __unset_binding(self, dependency, service, reference):
        """
        Removes a service from the component

        :param dependency: The dependency handler
        :param service: The injected service
        :param reference: The reference of the injected service
        """
        with self._lock:
            # Call the component back
            self.__safe_callback(constants.IPOPO_CALLBACK_UNBIND,
                                 service, reference)

            # Update the injected field
            setattr(self.instance, dependency.field, dependency.get_value())

            # Unget the service
            self.bundle_context.unget_service(reference)


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
    assert isinstance(stored_instance, _StoredInstance)

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
            # Prepare the methods names
            getter_name = "{0}{1}".format(constants.IPOPO_CONTROLLER_PREFIX,
                                          constants.IPOPO_GETTER_SUFFIX)
            setter_name = "{0}{1}".format(constants.IPOPO_CONTROLLER_PREFIX,
                                          constants.IPOPO_SETTER_SUFFIX)

            # Inject the getter and setter at the instance level
            getter, setter = _field_controller_generator(stored_instance)
            setattr(instance, getter_name, getter)
            setattr(instance, setter_name, setter)

            # Controllers are valid by default
            for name in controllers:
                stored_instance.set_controller_state(name, True)


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

        # Instances registry : name -> _StoredInstance object
        self.__instances = {}

        # Event listeners
        self.__listeners = []

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

            for name in self.__factories:
                if self.get_factory_bundle(name) is bundle:
                    # Found
                    to_remove.append(name)

            # Remove all of them
            for factory in to_remove:
                self.unregister_factory(factory)


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
            stored_instance = _StoredInstance(self, component_context, instance)

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
                    self.kill(instance.name)

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
        * state: The current component state
        * service (optional): The reference of the service provided by the
          component
        * dependencies: A dictionary associating field names with the following
          dictionary:
        
          * handler: The name of the type of the dependency handler
          * filter (optional): The requirement LDAP filter
          * optional: A flag indicating whether the requirement is optional or
            not
          * aggregate: A flag indicating whether the requirement is a set of
            services or not
          * binding: A list of the ServiceReference the component is bound to
        
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
            assert isinstance(stored_instance, _StoredInstance)
            with stored_instance._lock:
                result = {}
                result["name"] = stored_instance.name

                # Factory name
                result["factory"] = stored_instance.factory_name

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
                    if req.filter:
                        info["filter"] = str(req.filter)

                    info["optional"] = req.optional
                    info["aggregate"] = req.aggregate

                    # Bindings
                    info["bindings"] = dependency.get_bindings()

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
        self.service = None


    def start(self, context):
        """
        The bundle has started

        :param context: The bundle context
        """
        assert isinstance(context, BundleContext)

        # Register the iPOPO service
        self.service = _IPopoService(context)
        self._registration = context.register_service(\
                                        constants.IPOPO_SERVICE_SPECIFICATION, \
                                        self.service, {})

        # Register as a bundle listener
        context.add_bundle_listener(self)

        # Register as a framework stop listener
        context.add_framework_stop_listener(self)

        # Service enters in "run" mode
        self.service.running = True

        # Get all factories
        for bundle in context.get_bundles():
            if bundle.get_state() == Bundle.ACTIVE:
                # Bundle is active, register its factories
                self.service._register_bundle_factories(bundle)


    def stop(self, context):
        """
        The bundle has stopped

        :param context: The bundle context
        """
        assert isinstance(context, BundleContext)

        # The service is not in the "run" mode anymore
        self.service.running = False

        # Unregister the listener
        context.remove_bundle_listener(self)

        # Unregister the framework stop listener
        context.remove_framework_stop_listener(self)

        # Unregister the iPOPO service
        self._registration.unregister()

        # Clean up the service
        self.service._unregister_all_factories()


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
            self.service._unregister_bundle_factories(bundle)

        elif kind == BundleEvent.STARTING:
            # A bundle is staring, register its factories before its activator
            # is called. That way, the activator can use the registered
            # factories.
            self.service._register_bundle_factories(bundle)


    def framework_stopping(self):
        """
        Called when the framework is stopping
        """
        # Avoid new injections, as all bundles will be stopped
        self.service.running = False

# ------------------------------------------------------------------------------

# The activator instance
activator = _IPopoActivator()
