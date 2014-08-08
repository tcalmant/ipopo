#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Definition of Factory and Component context classes

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 0.5.7
:status: Beta

..

    Copyright 2014 isandlaTech

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
__version_info__ = (0, 5, 7)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix utilities
from pelix.constants import OBJECTCLASS
from pelix.utilities import is_string
import pelix.ldapfilter as ldapfilter

# iPOPO constants
import pelix.ipopo.constants as constants

# Standard library
import copy

# ------------------------------------------------------------------------------


class Requirement(object):
    """
    Represents a component requirement
    """
    # The dictionary form fields (filter is a special case)
    __stored_fields__ = ('specification', 'aggregate', 'optional')

    def __init__(self, specification, aggregate=False, optional=False,
                 spec_filter=None):
        """
        Sets up the requirement

        :param specification: The requirement specification, which must be
                              unique and can't be None
        :param aggregate: If true, this requirement represents a list
        :param optional: If true, this requirement is optional
        :param spec_filter: A filter to select dependencies

        :raise TypeError: A parameter has an invalid type
        :raise ValueError: An error occurred while parsing the filter
        """
        if not is_string(specification):
            raise TypeError("A Requirement specification must be a string")

        if not specification:
            raise ValueError("No specification given")

        self.specification = specification
        self.aggregate = aggregate
        self.optional = optional

        # Original filter keeper
        self.__original_filter = None

        # Full filter (with the specification test)
        self.__full_filter = None

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

        if self.aggregate != other.aggregate \
                or self.optional != other.optional:
            # Different flags
            return False

        if self.specification != other.specification:
            # Different specifications
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

    def __deepcopy__(self, memo):
        """
        Called by copy.deepcopy()
        """
        return self.copy()

    def copy(self):
        """
        Returns a copy of this instance

        :return: A copy of this instance
        """
        return Requirement(self.specification, self.aggregate, self.optional,
                           self.__original_filter)

    def matches(self, properties):
        """
        Tests if the given _StoredInstance matches this requirement

        :param properties: Service properties
        :return: True if the instance matches this requirement
        """
        if properties is None:
            # No properties : invalid service
            return False

        # Properties filter test
        return self.__full_filter.matches(properties)

    @property
    def full_filter(self):
        """
        The filter that tests both specification and properties
        """
        return self.__full_filter

    @property
    def original_filter(self):
        """
        The original requirement filter string, not the computed one
        """
        if self.__original_filter is None:
            return ""

        return str(self.__original_filter)

    def set_filter(self, props_filter):
        """
        Changes the current filter for the given one

        :param props_filter: The new requirement filter on service properties
        :raise TypeError: Unknown filter type
        """
        if props_filter is not None \
                and not (is_string(props_filter)
                         or isinstance(props_filter,
                                       (ldapfilter.LDAPFilter,
                                        ldapfilter.LDAPCriteria))):
            # Unknown type
            raise TypeError("Invalid filter type {0}"
                            .format(type(props_filter).__name__))

        if props_filter is not None:
            # Filter given, keep its string form
            self.__original_filter = str(props_filter)
        else:
            # No filter
            self.__original_filter = None

        # Parse the filter
        self.filter = ldapfilter.get_ldap_filter(props_filter)

        # Prepare the full filter
        spec_filter = "({0}={1})".format(OBJECTCLASS, self.specification)
        self.__full_filter = ldapfilter.combine_filters((spec_filter,
                                                         self.filter))

# ------------------------------------------------------------------------------


class FactoryContext(object):
    """
    Represents the data stored in a component factory (class)
    """
    def __init__(self):
        """
        Sets up the factory context
        """
        # Factory bundle context
        self.bundle_context = None

        # Callbacks : Kind -> callback method
        self.callbacks = {}

        # Field callbacks: Field -> {Kind -> Callback}
        self.field_callbacks = {}

        # The factory name
        self.name = None

        # Properties : Name -> Value
        self.properties = {}

        # Properties fields : Field name -> Property name
        self.properties_fields = {}

        # The factory manipulation has been completed
        self.completed = False

        # Handler ID -> configuration
        self.__handlers = {}

        # Inherited configuration
        self.__inherited_configuration = {}

        # Instance name -> Instance properties
        self.__instances = {}

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

        # Name-based equality
        return self.name == other.name

    def __ne__(self, other):
        """
        Inequality test
        """
        return not self.__eq__(other)

    def copy(self, inheritance=False):
        """
        Returns a deep copy of the current FactoryContext instance

        :param inheritance: If True, current handlers configurations are stored
                            as inherited ones
        """
        # Copy the context
        new_context = copy.deepcopy(self)

        if inheritance:
            # Store configuration as inherited one
            new_context.__inherited_configuration = new_context.__handlers
            new_context.__handlers = {}

        # Remove instances in any case
        new_context.__instances.clear()
        return new_context

    def inherit_handlers(self, excluded_handlers):
        """
        Merges the inherited configuration with the current ones

        :param excluded_handlers: Excluded handlers
        """
        if not excluded_handlers:
            excluded_handlers = tuple()

        for handler, configuration in self.__inherited_configuration.items():
            if handler in excluded_handlers:
                # Excluded handler
                continue

            elif handler not in self.__handlers:
                # Fully inherited configuration
                self.__handlers[handler] = configuration

            # Merge configuration...
            elif isinstance(configuration, dict):
                # Dictionary
                self.__handlers.setdefault(handler, {}).update(configuration)

            elif isinstance(configuration, list):
                # List
                handler_conf = self.__handlers.setdefault(handler, [])
                for item in configuration:
                    if item not in handler_conf:
                        handler_conf.append(item)

        # Clear the inherited configuration dictionary
        self.__inherited_configuration.clear()

    def add_instance(self, name, properties):
        """
        Stores the description of a component instance. The given properties
        are stored as is.

        :param name: Instance name
        :param properties: Instance properties
        :raise NameError: Already known instance name
        """
        if name in self.__instances:
            raise NameError(name)

        # Store properties "as-is"
        self.__instances[name] = properties

    def get_instances(self):
        """
        Returns the dictionary of instances to start: name -> properties

        :return: A dictionary: instance name -> instance properties
        """
        return copy.deepcopy(self.__instances)

    def get_handlers_ids(self):
        """
        Retrieves the IDs of the handlers to instantiate for this component
        """
        return list(self.__handlers.keys())

    def get_handler(self, handler_id, default=None):
        """
        Retrieves the configuration associated to the given handler

        :param handler_id: The ID of the configured handler
        :param default: The default configuration value
        :return: The existing configuration or the given default
        """
        return self.__handlers.get(handler_id, default)

    def set_handler_default(self, handler_id, default=None):
        """
        Retrieves the configuration associated to the given handler, creates
        it the entry with the given value if necessary

        :param handler_id: The ID of the configured handler
        :param default: The default configuration value to store if none exists
        :return: The existing configuration or the given default
        """
        return self.__handlers.setdefault(handler_id, default)

    def set_handler(self, handler_id, configuration):
        """
        Stores the configuration of the given handler

        :param handler_id: The ID of the configured handler
        :param configuration: The complete configuration of the handler
        """
        self.__handlers[handler_id] = configuration

    def set_bundle_context(self, bundle_context):
        """
        Sets up the bundle context associated to this factory context

        :param bundle_context: The factory bundle context (or None to clear it)
        """
        self.bundle_context = bundle_context

# ------------------------------------------------------------------------------


class ComponentContext(object):
    """
    Represents the data stored in a component instance
    """
    # Try to reduce memory footprint (many instances)
    __slots__ = ('factory_context', 'name', 'properties')

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

    def get_bundle_context(self):
        """
        Retrieves the bundle context

        :return: The component bundle context
        """
        return self.factory_context.bundle_context

    def get_callback(self, event):
        """
        Retrieves the registered method for the given event. Returns None if
        not found

        :param event: A component life cycle event
        :return: The callback associated to the given event
        """
        return self.factory_context.callbacks.get(event, None)

    def get_field_callback(self, field, event):
        """
        Retrieves the registered method for the given event. Returns None if
        not found

        :param field: Name of the dependency field
        :param event: A component life cycle event
        :return: A 2-tuple containing the callback associated to the given
                 event and flag indicating if the callback must be called in
                 valid state only
        """
        return self.factory_context.field_callbacks.get(field, {}).get(event)

    def get_factory_name(self):
        """
        Retrieves the component factory name

        :return: The component factory name
        """
        return self.factory_context.name

    def get_handler(self, handler_id):
        """
        Retrieves the configuration for the given handler from the factory
        context

        :param handler_id: The ID of the configured handler
        :return: The handler configuration, or None
        """
        return self.factory_context.get_handler(handler_id, None)
