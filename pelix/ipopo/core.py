#!/usr/bin/env python
#-- Content-Encoding: UTF-8 --
"""
Core iPOPO implementation

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

# Documentation strings format
__docformat__ = "restructuredtext en"

# Prepare the module logger
_logger = logging.getLogger("ipopo.core")

# ------------------------------------------------------------------------------

class IPopoEvent(object):
    """
    An event object for iPOPO
    """

    REGISTERED = 1
    """ A component factory has been registered """

    INSTANTIATED = 2
    """ A component has been instantiated, but not yet validated """

    VALIDATED = 3
    """ A component has been validated """

    INVALIDATED = 4
    """ A component has been invalidated """

    BOUND = 5
    """ A reference has been injected in the component """

    UNBOUND = 6
    """ A reference has been removed from the component """

    UNREGISTERED = 10
    """ A component factory has been unregistered """


    def __init__(self, kind, factory_name, component_name):
        """
        Sets up the iPOPO event
        
        :param kind: Kind of event
        :param factory_name: Name of the factory associated to the event
        :param component_name: Name of the component instance associated to the
                               event
        """
        self.__kind = kind
        self.__factory_name = factory_name
        self.__component_name = component_name


    def get_component_name(self):
        """
        Retrieves the name of the component associated to the event
        
        :return: the name of the component
        """
        return self.__component_name


    def get_factory_name(self):
        """
        Retrieves the name of the factory associated to the event
        
        :return: the name of the component factory
        """
        return self.__factory_name


    def get_kind(self):
        """
        Retrieves the kind of event
        
        :return: the kind of event
        """
        return self.__kind

# ------------------------------------------------------------------------------

class Requirement(object):
    """
    Represents a component requirement
    """
    # The dictionary form fields
    __stored_fields__ = ('specifications', 'aggregate', 'optional', 'filter')

    def __init__(self, specifications, aggregate=False, optional=False, \
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
        if not specifications:
            raise TypeError("A specification must be given")

        if not isinstance(specifications, list):
            # Convert specification into a list
            specifications = [specifications]

        converted_specs = []
        for spec in specifications:

            if is_string(spec):
                spec_str = spec

            elif inspect.isclass(spec):
                spec_str = spec.__name__

            else:
                raise TypeError("The requirement specification must be a " \
                                "string or a list of string")

            converted_specs.append(spec_str)

        self.aggregate = aggregate
        self.optional = optional
        self.specifications = converted_specs

        # Set up the requirement filter (after setting up self.specification)
        self.filter = None
        self.set_filter(spec_filter)


    def copy(self):
        """
        Returns a copy of this instance
        
        :return: A copy of this instance
        """
        return Requirement(self.specifications, self.aggregate, self.optional, \
                           self.filter)


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
            raise TypeError("Invalid form type '%s'" \
                            % type(dictionary).__name__)

        if not "specifications" in dictionary:
            raise ValueError("Missing specifications in the dictionary form")

        specs = dictionary["specifications"]
        aggregate = dictionary.get("aggregate", False)
        optional = dictionary.get("optional", False)
        spec_filter = ldapfilter.get_ldap_filter(dictionary.get("filter", \
                                                                None))

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

        assert(isinstance(properties, dict))

        # Properties filter test
        return self.filter.matches(properties)


    def set_filter(self, spec_filter):
        """
        Changes the current filter for the given one

        :param spec_filter: The new requirement filter
        :raise TypeError: Unknown filter type
        """
        if spec_filter is not None and not is_string(spec_filter) \
        and not isinstance(spec_filter, ldapfilter.LDAPFilter) \
        and not isinstance(spec_filter, ldapfilter.LDAPCriteria):
            # Unknown type
            raise TypeError("Invalid filter type %s" \
                            % type(spec_filter).__name__)

        ldap_criteria = []
        for spec in self.specifications:
            ldap_criteria.append("(%s=%s)" \
                                 % (pelix.OBJECTCLASS, \
                                    ldapfilter.escape_LDAP(spec)))

        # Make the filter, escaping the specification name
        ldap_filter = "(|%s)" % "".join(ldap_criteria)

        if spec_filter is not None:
            # String given
            ldap_filter = ldapfilter.combine_filters([ldap_filter, spec_filter])

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
        return result

# ------------------------------------------------------------------------------

class FactoryContext(object):
    """
    Represents the data stored in a component factory (class)
    """

    __basic_fields = ('callbacks', 'name', 'properties', 'properties_fields', \
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

        # Provided specifications (array of strings)
        self.provides = []

        # Requirements : Field name -> Requirement object
        self.requirements = {}


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
        # Prepare the instance, initializing it
        instance = cls()

        if not isinstance(dictionary, dict):
            raise TypeError("Invalid form type '%s'" \
                            % type(dictionary).__name__)

        # Basic fields
        for field in cls.__basic_fields:

            if field not in dictionary:
                raise ValueError("Incomplete dictionary form : " \
                                 "missing '%s'" % field)

            setattr(instance, field, dictionary[field])

        # Requirements field
        if 'requirements' not in dictionary:
            raise ValueError("Incomplete dictionary form : " \
                             "missing 'requirements'")

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
        Retrieves the services that this component provides
        
        :return: The services provided by this component
        """
        return self.factory_context.provides



class _StoredInstance(object):
    """
    Represents a component instance
    """

    # Try to reduce memory footprint (stored __instances)
    __slot__ = ('bindings', 'bundle_context', 'context', 'factory_name', \
                'instance', 'name', 'registration', 'state', '_lock')

    INVALID = 0
    """ This component has been invalidated """

    VALID = 1
    """ This component has been validated """

    KILLED = 2
    """ This component has been killed """

    VALIDATING = 3
    """ This component is currently validating """

    VALIDATION_PASSED = 4
    """
    The component validation callback passed, the component validation can end
    """


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

        # Injected service references set
        self._injected_references = set()

        # Component context
        self.context = context

        # The instance name
        self.name = self.context.name

        # Factory name
        self.factory_name = self.context.get_factory_name()

        # Component instance
        self.instance = instance

        # Field -> [Service reference(s)]
        self.bindings = {}

        # The provided service registration
        self.registration = None

        # Set the instance state
        self.state = _StoredInstance.INVALID

        # Register to the events
        self.bundle_context = self.context.get_bundle_context()
        self.bundle_context.add_service_listener(self)


    def __repr__(self):
        """
        String representation
        """
        return self.__str__()


    def __str__(self):
        """
        String representation
        """
        return "StoredInstance(%s, %d)" % (self.name, self.state)


    @SynchronizedClassMethod('_lock')
    def callback(self, event, *args, **kwargs):
        """
        Calls the registered method in the component for the given event

        :param event: An event (IPOPO_CALLBACK_VALIDATE, ...)
        :return: The callback result, or None
        :raise Exception: Something went wrong
        """
        comp_callback = self.context.get_callback(event)
        if not comp_callback:
            # No registered callback
            return None

        # Call it
        return comp_callback(self.instance, *args, **kwargs)


    @SynchronizedClassMethod('_lock')
    def invalidate(self, callback=True):
        """
        Does the post-invalidation job. Unregisters the provided service(s), if
        any

        :param callback: If True, call back the component before the
        invalidation
        """
        if self.state != _StoredInstance.VALID:
            # Instance is not running...
            return

        # Change the state
        self.state = _StoredInstance.INVALID

        if self.registration is not None:
            # Ignore error
            try:
                self.registration.unregister()

            except BundleException:
                # Ignore error at this level
                pass

            self.registration = None

        # Call the component
        if callback:
            self.safe_callback(constants.IPOPO_CALLBACK_INVALIDATE, \
                               self.bundle_context)

            # Trigger an "Invalidated" event
            self._ipopo_service._fire_ipopo_event(IPopoEvent.INVALIDATED,
                                                  self.factory_name, self.name)


    @SynchronizedClassMethod('_lock')
    def kill(self):
        """
        This instance is killed : invalidate it if needed, clean up all members

        When this method is called, this _StoredInstance object must have
        been removed from the registry
        """
        # Already dead...
        if self.state == _StoredInstance.KILLED:
            return

        # Unregister from service events
        self.bundle_context.remove_service_listener(self)

        try:
            self.invalidate(True)

        except:
            _logger.exception("%s: Error invalidating the instance", self.name)

        # Now that we are nearly clean, be sure we were in a good registry state
        assert not self._ipopo_service.is_registered_instance(self.name)

        # Unbind all references
        for field, requirement in self.context.requirements.items():

            field_value = getattr(self.instance, field, None)
            if field_value is None:
                # Ignore unbound fields
                continue

            if not requirement.aggregate:
                # Simple case : only one binding
                self.__unset_binding(field, requirement, field_value)

            else:
                # Multiple bindings
                for service in field_value:
                    self.__unset_binding(field, requirement, service)

        # Change the state
        self.state = _StoredInstance.KILLED

        # Clean up members
        self.bindings.clear()
        self.context = None
        self.instance = None
        self._ipopo_service = None


    @SynchronizedClassMethod('_lock')
    def safe_callback(self, event, *args, **kwargs):
        """
        Calls the registered method in the component for the given event,
        ignoring raised exceptions

        :param event: An event (IPOPO_CALLBACK_VALIDATE, ...)
        :return: The callback result, or None
        """
        if self.state == _StoredInstance.KILLED:
            # Invalid state
            return None

        try:
            return self.callback(event, *args, **kwargs)

        except:
            _logger.exception("Component '%s' : error calling callback " \
                               "method for event %s" % (self.name, event))
            return None


    @SynchronizedClassMethod('_lock')
    def __set_binding(self, field, requirement, reference):
        """
        Injects the given service into the given field

        :param field: The field where the service is injected
        :param requirement: The field requirement description
        :param reference: The injected service reference
        """
        current_value = getattr(self.instance, field, None)

        if requirement.aggregate:
            # Aggregation
            if current_value is not None:
                if not isinstance(current_value, list):
                    # Invalid field content
                    _logger.error("%s : The injected field %s must be a " \
                                  "list, not %s", self.name, field, \
                                  type(current_value).__name__)
                    return

            else:
                # No previous value
                current_value = []

        # Get the service instance
        service = self.bundle_context.get_service(reference)

        if requirement.aggregate:
            # Append the service to the list and inject the whole list
            current_value.append(service)
            setattr(self.instance, field, current_value)

        else:
            # Inject the service directly in the field
            setattr(self.instance, field, service)

        # Keep track of the bound reference
        if field in self.bindings:
            self.bindings[field].append(reference)

        else:
            # Create the list if the needed
            self.bindings[field] = [reference]

        # Keep a track of the injected reference
        self._injected_references.add(reference)

        # Call the component back
        self.safe_callback(constants.IPOPO_CALLBACK_BIND, service, reference)


    @SynchronizedClassMethod('_lock')
    def __set_multiple_binding(self, field, current_value, requirement, \
                               references):
        """
        Injects multiple services in a field in one time. Only works with
        aggregations.

        :param field: The field where to inject the services
        :param current_value: Current field value (should be None or a list)
        :param requirement: Dependency description
        :param references: Injected services references (must be a list)
        """
        if not requirement.aggregate:
            # Not an aggregation...
            _logger.error("%s: field '%s' is not an aggregation", \
                          self.name, field)
            return

        if not isinstance(references, list):
            # Bad references
            _logger.error("%s: Invalid references list type %s", \
                          self.name, type(references).__name__)

        if current_value is not None and not isinstance(current_value, list):
            # Injected field as the right type
            _logger.error("%s: field '%s' must be a list", \
                          self.name, field)

            return

        # Special case for a list : we must ignore already injected
        # references
        if field in self.bindings:
            references = [reference for reference in references \
                          if reference not in self.bindings[field]]

        if not references:
            # Nothing to add, ignore this field
            return

        # Prepare the injected value
        if current_value is not None:
            injected = current_value

        else:
            injected = []

        # Compute the bound services
        bound = []

        for reference in references:
            bound.append(self.bundle_context.get_service(reference))

            # Store the references usage
            self._injected_references.add(reference)

        # Set the field
        setattr(self.instance, field, injected)

        # Add dependency marker
        bindings_value = self.bindings.get(field, None)

        if bindings_value is not None:
            # Extend the existing list
            bindings_value.extend(references)

        else:
            # Add bindings, copying the list
            self.bindings[field] = list(references)

        for service in bound:
            # Inject the service
            injected.append(service)

            # Call Bind
            self.safe_callback(constants.IPOPO_CALLBACK_BIND, service,
                               reference)


    @SynchronizedClassMethod('_lock')
    def __unset_binding(self, field, requirement, service):
        """
        Remove the given service from the given field

        :param field: The field where the service is injected
        :param requirement: The field requirement description
        :param service: The injected service instance
        """
        current_value = getattr(self.instance, field, None)
        if current_value is None:
            # Nothing to do...
            return

        if requirement.aggregate and not isinstance(current_value, list):
            # Aggregation, but invalid field content
            _logger.error("%s : The injected field %s must be a " \
                           "list, not %s", self.name, field, \
                           type(current_value).__name__)
            return

        # Call the component back
        self.safe_callback(constants.IPOPO_CALLBACK_UNBIND, service)

        if requirement.aggregate:
            # Remove the service from the list
            remove_all_occurrences(current_value, service)
            if len(current_value) == 0:
                # Don't keep empty lists
                setattr(self.instance, field, None)

        else:
            # Set single references to None
            setattr(self.instance, field, None)


    @SynchronizedClassMethod('_lock')
    def update_bindings(self):
        """
        Updates the bindings of the given component

        :return: True if the component can be validated
        """
        # Get the requirement, or an empty dictionary
        requirements = self.context.requirements
        if not requirements:
            # No requirements : nothing to do
            return True

        all_bound = True
        component = self.instance

        for field, requires in requirements.items():
            # For each field
            current_value = getattr(component, field, None)
            if not requires.aggregate and current_value is not None:
                # A dependency is already injected
                continue

            # Find possible services (specification test is already in filter
            refs = self.bundle_context.get_all_service_references(None, \
                                                            requires.filter)

            if not refs:
                if not requires.optional:
                    # Required link not found
                    all_bound = False

                continue

            if requires.aggregate:
                # Aggregation
                self.__set_multiple_binding(field, current_value, requires, \
                                            refs)

            else:
                # Normal field, bind the first reference
                self.__set_binding(field, requires, refs[0])

        return all_bound

    @SynchronizedClassMethod('_lock')
    def update_property(self, name, old_value, new_value):
        """
        Handles a property changed event

        :param name: The changed property name
        :param old_value: The previous property value
        :param new_value: The new property value
        """
        if self.registration is not None:
            # use the registration to trigger the service event
            self.registration.set_properties({name: new_value})


    @SynchronizedClassMethod('_lock')
    def validate(self, safe_callback=True):
        """
        Ends the component validation, registering services

        :raise RuntimeError: You try to awake a dead component
        """
        if self.state in (_StoredInstance.VALID, _StoredInstance.VALIDATING):
            # No work to do (yet)
            return

        if self.state == _StoredInstance.KILLED:
            raise RuntimeError("%s: Zombies !" % self.context.name)

        if safe_callback or not self.state == _StoredInstance.VALIDATION_PASSED:
            # Safe call back needed and not yet passed
            self.state = _StoredInstance.VALIDATING
            self.safe_callback(constants.IPOPO_CALLBACK_VALIDATE, \
                               self.bundle_context)

        provides = self.context.get_provides()

        # All good
        self.state = _StoredInstance.VALID

        if not provides:
            # Nothing registered
            self.registration = None

        else:
            self.registration = self.bundle_context.register_service(\
                                            self.context.get_provides(), \
                                            self.instance, \
                                            self.context.properties.copy(), \
                                            True)

        # Trigger the iPOPO event (after the service registration)
        self._ipopo_service._fire_ipopo_event(IPopoEvent.VALIDATED, \
                                              self.factory_name, self.name)



    @SynchronizedClassMethod('_lock')
    def service_changed(self, event):
        """
        Called by Pelix when some service properties changes

        :param event: A ServiceEvent object
        """
        kind = event.get_type()
        reference = event.get_service_reference()

        if self.registration is not None \
        and reference is self.registration.get_reference():
            # The event is about the service provided by this component
            if kind == ServiceEvent.UNREGISTERING \
            and self.state == _StoredInstance.VALID:
                # Our service is being unregistered by someone else,
                # e.g. the framework

                # 1/ The registration is no more valid
                self.registration = None

                # 2/ Invalidate this component (with the call back)
                self.invalidate(True)

            else:
                # Ignore other events
                return

        elif kind == ServiceEvent.REGISTERED:

            # Ignore the event if iPOPO is not running.
            if not self._ipopo_service.running:
                return

            # Maybe a new dependency...
            can_validate = (self.state != _StoredInstance.VALID)

            for field, requires in self.context.requirements.items():

                if reference in self.bindings.get(field, []):
                    # Reference already known, ignore it
                    continue

                field_value = getattr(self.instance, field, None)

                if not requires.aggregate and field_value is not None:
                    # Field already injected
                    continue

                if requires.matches(reference.get_properties()):
                    # Inject the service
                    self.__set_binding(field, requires, reference)

                elif can_validate and not requires.optional \
                and field_value is None:
                    # Missing a required dependency
                    can_validate = False

            if can_validate:
                # ... even a validating dependency
                self.validate(True)

        elif kind == ServiceEvent.UNREGISTERING:
            if reference not in self._injected_references:
                # Unused dependency, ignore it
                return

            # Remove the dependency from the set
            self._injected_references.remove(reference)

            # A dependency may be gone...
            invalidate = False

            for field, binding in self.bindings.items():
                if reference in binding:
                    # We were using this dependency
                    service = self.bundle_context.get_service(reference)
                    field_value = getattr(self.instance, field)
                    requirement = self.context.requirements[field]

                    if not invalidate and not requirement.optional:
                        if not requirement.aggregate or len(field_value) == 1:
                            # Last reference for a required field : invalidate
                            invalidate = True
                            self.safe_callback(\
                                        constants.IPOPO_CALLBACK_INVALIDATE, \
                                        self.bundle_context)

                    # Remove the entry
                    self.__unset_binding(field, requirement, service)

                    # Free the reference to the service
                    self.bundle_context.unget_service(reference)

            # Finish the invalidation
            if invalidate:
                self.invalidate(False)

            # Ask for a new chance, if iPOPO is running... 
            if self._ipopo_service.running and self.update_bindings() \
            and invalidate:
                self.validate(True)

        elif kind == ServiceEvent.MODIFIED:

            # Modified service property
            invalidate = False
            can_validate = (self.state != _StoredInstance.VALID)

            to_remove = []
            for field, binding in self.bindings.items():
                if reference in binding:
                    # We are using this dependency
                    requirement = self.context.requirements[field]

                    if requirement.matches(reference.get_properties()):
                        # The service still corresponds to the field, ignore
                        continue

                    # We lost it... (yeah, same as above, I know)
                    service = self.bundle_context.get_service(reference)
                    field_value = getattr(self.instance, field)

                    if not invalidate and not requirement.optional:
                        if not requirement.aggregate or len(field_value) == 1:
                            # Last reference for a required field : invalidate
                            invalidate = True
                            self.safe_callback(\
                                        constants.IPOPO_CALLBACK_INVALIDATE, \
                                        self.bundle_context)

                    # Remove the entry
                    self.__unset_binding(field, requirement, service)

                    to_remove.append((field, service))

                    # Free the reference to the service
                    self.bundle_context.unget_service(reference)

            # Finish the removal
            for field, service in to_remove:
                remove_all_occurrences(self.bindings[field], service)
                if len(self.bindings[field]) == 0:
                    # Don't keep empty lists
                    del self.bindings[field]

            # Finish the invalidation
            if invalidate:
                # The call back method has already been called
                self.invalidate(False)

            # Ask for a new chance, if iPOPO is running... 
            if self._ipopo_service.running and self.update_bindings() \
            and (invalidate or can_validate):
                self.validate(True)

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
        _logger.exception("Invalid data in manipulated class '%s'", \
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
        if stored_instance.context is None:
            return None

        return stored_instance.context.properties.get(name, None)


    def set_value(self, name, new_value):
        """
        Sets the property value and trigger an update event

        :param name: The property name
        :param new_value: The new property value
        """
        if stored_instance.context is None:
            return None

        # Get the previous value
        old_value = stored_instance.context.properties.get(name, None)

        # Change the property
        stored_instance.context.properties[name] = new_value

        if new_value != old_value:
            # New value is different of the old one, trigger an event
            stored_instance.update_property(name, old_value, new_value)

        return new_value

    return (get_value, set_value)


def _manipulate_component(instance, stored_instance):
    """
    Manipulates the component instance to inject missing elements.

    Injects the properties handling
    """
    assert instance is not None
    assert isinstance(stored_instance, _StoredInstance)

    getter, setter = _field_property_generator(stored_instance)

    # Inject the getter and setter at the instance level
    setattr(instance, constants.IPOPO_PROPERTY_GETTER, getter)
    setattr(instance, constants.IPOPO_PROPERTY_SETTER, setter)

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
                    listener.handle_ipopo_event(IPopoEvent(kind, factory_name,
                                                           component_name))

                except:
                    _logger.exception("Error in an iPOPO event handler")


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
            raise TypeError("Invalid factory class '%s'" \
                            % type(factory).__name__)

        with self.__factories_lock:
            if factory_name in self.__factories:
                if override:
                    _logger.info("Overriding factory '%s'", factory_name)

                else:
                    raise ValueError("'%s' factory already exist" \
                                     % factory_name)

            self.__factories[factory_name] = factory

            # Trigger an event
            self._fire_ipopo_event(IPopoEvent.REGISTERED, factory_name)


    def _unregister_all_factories(self):
        """
        Unregisters all factories. This method should be called only after the
        iPOPO service has been unregistered (that's why it's not locked)
        """
        factories = list(self.__factories.keys())

        for factory_name in factories:
            self._unregister_factory(factory_name)


    def _unregister_bundle_factories(self, bundle):
        """
        Unregisters all factories of the given bundle

        :param bundle: A bundle
        """
        assert isinstance(bundle, Bundle)

        with self.__factories_lock:
            # Find out which factories must be removed
            to_remove = []

            for name, factory in self.__factories.items():
                # Bundle Context is stored in the Factory Context
                factory_context = getattr(factory, \
                                          constants.IPOPO_FACTORY_CONTEXT)

                if factory_context.bundle_context.get_bundle() is bundle:
                    # Found
                    to_remove.append(name)

            # Remove all of them
            for factory in to_remove:
                self._unregister_factory(factory)


    def _unregister_factory(self, factory_name):
        """
        Unregisters the given component factory

        :param factory_name: Name of the factory to unregister
        :return: True the factory has been removed, False if the factory is
                 unknown
        """
        if not factory_name:
            # Empty name
            return False

        with self.__factories_lock:
            if factory_name not in self.__factories:
                # Unknown factory
                return False

            # Trigger an event
            self._fire_ipopo_event(IPopoEvent.UNREGISTERED, factory_name)

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
        if not factory_name:
            raise ValueError("Invalid factory name")

        if not name:
            raise ValueError("Invalid component name")

        with self.__instances_lock:
            if name in self.__instances:
                raise ValueError("'%s' is an already running instance name" \
                                 % name)

            with self.__factories_lock:
                # Can raise a ValueError exception
                factory = self.__factories.get(factory_name, None)
                if factory is None:
                    raise TypeError("Unknown factory '%s'" % factory_name)

                # Get the factory context
                factory_context = getattr(factory, \
                                          constants.IPOPO_FACTORY_CONTEXT, None)
                if factory_context is None:
                    raise TypeError("Factory context missing in '%s'" \
                                    % factory_name)

            # Create component instance
            try:
                instance = factory()

            except:
                _logger.exception("Error creating the instance '%s' " \
                                  "from factory '%s'", name, factory_name)

                raise TypeError("Factory '%s' failed to create '%s'" \
                                % (factory_name, name))

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

        # Try to validate it
        if stored_instance.update_bindings():
            try:
                # Set in validating mode
                stored_instance.state = _StoredInstance.VALIDATING

                stored_instance.callback(constants.IPOPO_CALLBACK_VALIDATE, \
                                         component_context.get_bundle_context())

                # Validation passed
                stored_instance.state = _StoredInstance.VALIDATION_PASSED

                # End the validation on success...
                stored_instance.validate(False)

            except Exception:
                # Log the error
                _logger.exception("Error validating '%s'", name)

                # Kill the component
                self.kill(name)
                return None

        return instance


    def invalidate(self, name):
        """
        Invalidates the given component

        :param name: Name of the component to invalidate
        :raise ValueError: Invalid component name
        """
        with self.__instances_lock:
            if name not in self.__instances:
                raise ValueError("Unknown component instance '%s'" % name)

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
                raise ValueError("Unknown component instance '%s'" % name)

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
        :raise TypeError: Invalid factory type
        """
        if factory is None or bundle_context is None:
            # Invalid parameter, to nothing
            raise ValueError("Invalid parameter")

        context = _set_factory_context(factory, bundle_context)
        if not context:
            return False

        self._register_factory(context.name, factory, False)
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


# ------------------------------------------------------------------------------

class _IPopoActivator(object):
    """
    The iPOPO bundle activator for Pelix
    """

    def __init__(self):
        """
        Sets up the activator
        """
        self.registration = None
        self.service = None


    def start(self, context):
        """
        The bundle has started
        
        :param context: The bundle context
        """
        assert isinstance(context, BundleContext)

        # Register the iPOPO service
        self.service = _IPopoService(context)
        self.registration = context.register_service(\
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
        self.registration.unregister()

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
