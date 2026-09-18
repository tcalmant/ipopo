#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Definition of Factory and Component context classes

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.2.2

..

    Copyright 2026 Thomas Calmant

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

from collections.abc import Callable, Iterable
from typing import Any, TypeVar, cast

from pelix import ldapfilter
from pelix.constants import OBJECTCLASS
from pelix.framework import BundleContext
from pelix.ipopo import constants
from pelix.utilities import is_string

T = TypeVar("T")

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class Requirement:
    """
    Represents a component requirement

    A requirement can target several specifications: by default, the injected
    service must provide all of them. If ``match_any`` is set, a service
    providing at least one of them is enough.
    """

    # The dictionary form fields (filter is a special case)
    __stored_fields__ = (
        "specifications",
        "aggregate",
        "optional",
        "immediate_rebind",
        "match_any",
    )

    def __init__(
        self,
        specification: str | list[str] | tuple[str, ...],
        aggregate: bool = False,
        optional: bool = False,
        spec_filter: None | str | ldapfilter.LDAPCriteria | ldapfilter.LDAPFilter = None,
        immediate_rebind: bool = False,
        match_any: bool = False,
    ):
        """
        Sets up the requirement

        :param specification: The requirement specification, or a list of specifications. Can't be empty
        :param aggregate: If true, this requirement represents a list
        :param optional: If true, this requirement is optional
        :param spec_filter: A filter to select dependencies
        :param immediate_rebind: If True, the component won't be invalidated
                                 then re-validated if a matching service is
                                 available when the injected dependency is unbound
        :param match_any: If True, a service providing at least one of the
                          specifications matches, else it must provide all of
                          them. Ignored with a single specification
        :raise TypeError: A parameter has an invalid type
        :raise ValueError: An error occurred while parsing the filter, or no specification given
        """
        if isinstance(specification, str):
            raw_specifications: list[str] | tuple[str, ...] = [specification]
        elif isinstance(specification, (list, tuple)):
            raw_specifications = specification
        else:
            raise TypeError("A Requirement specification must be a string or a list of strings")

        specifications: list[str] = []
        for spec in raw_specifications:
            if not is_string(spec):
                raise TypeError("A Requirement specification must be a string")

            if not spec.strip():
                raise ValueError("Empty specification given")

            if spec not in specifications:
                specifications.append(spec)

        if not specifications:
            raise ValueError("No specification given")

        self.specifications = specifications
        # Kept for backward compatibility: the first (main) specification
        self.specification = specifications[0]
        self.aggregate = aggregate
        self.optional = optional
        self.immediate_rebind = immediate_rebind
        # The "any" flag only has a meaning when choosing between specifications
        self.match_any = bool(match_any) and len(specifications) > 1

        # Original filter keeper
        self.__original_filter: str | None = None

        # Full filter (with the specification test)
        self.__full_filter: None | ldapfilter.LDAPCriteria | ldapfilter.LDAPFilter = None

        # Filter to use with the lookup specification (see lookup_filter)
        self.__lookup_filter: None | ldapfilter.LDAPCriteria | ldapfilter.LDAPFilter = None

        # Set up the requirement filter (after setting up self.specifications)
        self.__filter: None | ldapfilter.LDAPCriteria | ldapfilter.LDAPFilter = None
        self.set_filter(spec_filter)

    def __eq__(self, other: object) -> bool:
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

        if self.specifications != other.specifications or self.match_any != other.match_any:
            # Different specifications
            return False

        if self.filter != other.filter:  # noqa: SIM103
            # Different filters (therefore different specifications)
            return False

        return True

    def __ne__(self, other: object) -> bool:
        """
        Inequality test
        """
        return not self.__eq__(other)

    def copy(self) -> "Requirement":
        """
        Returns a copy of this instance

        :return: A copy of this instance
        """
        return Requirement(
            list(self.specifications),
            self.aggregate,
            self.optional,
            self.__original_filter,
            self.immediate_rebind,
            self.match_any,
        )

    def matches(self, properties: dict[str, Any] | None) -> bool:
        """
        Tests if the given _StoredInstance matches this requirement

        :param properties: Service properties
        :return: True if the instance matches this requirement
        """
        if properties is None:
            # No properties : invalid service
            return False

        if self.__full_filter is None:
            # No filter, every matches
            return True

        # Properties filter test
        return self.__full_filter.matches(properties)

    @property
    def filter(self) -> None | ldapfilter.LDAPCriteria | ldapfilter.LDAPFilter:
        """
        The filter on service properties only (without the specification test)
        """
        return self.__filter

    @filter.setter
    def filter(self, props_filter: None | str | ldapfilter.LDAPCriteria | ldapfilter.LDAPFilter) -> None:
        """
        Replaces the parsed properties filter, keeping the original filter
        string, and refreshes the filters derived from it
        """
        self.__filter = ldapfilter.get_ldap_filter(props_filter)
        self.__update_filters()

    @property
    def full_filter(self) -> None | ldapfilter.LDAPFilter | ldapfilter.LDAPCriteria:
        """
        The filter that tests both specification and properties
        """
        return self.__full_filter

    @property
    def lookup_specification(self) -> str | None:
        """
        The specification to give to service lookups and service listeners,
        along with :attr:`lookup_filter`.

        It is None when any of the specifications matches, as the registry
        can't index a service under a set of specifications.
        """
        if self.match_any:
            return None

        return self.specification

    @property
    def lookup_filter(self) -> None | ldapfilter.LDAPFilter | ldapfilter.LDAPCriteria:
        """
        The filter to give to service lookups and service listeners, along
        with :attr:`lookup_specification`: it tests the specifications which
        are not handled by the lookup specification, and the service
        properties.
        """
        return self.__lookup_filter

    @property
    def original_filter(self) -> str:
        """
        The original requirement filter string, not the computed one
        """
        if self.__original_filter is None:
            return ""

        return str(self.__original_filter)

    def set_filter(self, props_filter: None | str | ldapfilter.LDAPCriteria | ldapfilter.LDAPFilter) -> None:
        """
        Changes the current filter for the given one

        :param props_filter: The new requirement filter on service properties
        :raise TypeError: Unknown filter type
        """
        if props_filter is not None and not (
            is_string(props_filter)
            or isinstance(props_filter, (ldapfilter.LDAPFilter, ldapfilter.LDAPCriteria))
        ):
            # Unknown type
            raise TypeError(f"Invalid filter type {type(props_filter).__name__}")

        # Parse the filter first, to keep a consistent state on error
        self.filter = props_filter

        if props_filter is not None:
            # Filter given, keep its string form
            self.__original_filter = str(props_filter)
        else:
            # No filter
            self.__original_filter = None

    def __update_filters(self) -> None:
        """
        Computes the full and lookup filters from the specifications and the
        current properties filter
        """
        spec_clauses = [f"({OBJECTCLASS}={ldapfilter.escape_LDAP(spec)})" for spec in self.specifications]

        if self.match_any:
            any_clause = f"(|{''.join(spec_clauses)})"
            self.__full_filter = ldapfilter.combine_filters((any_clause, self.__filter))
            self.__lookup_filter = self.__full_filter
        else:
            self.__full_filter = ldapfilter.combine_filters((*spec_clauses, self.__filter))
            if len(spec_clauses) == 1:
                # Single specification: the lookup specification is enough
                self.__lookup_filter = self.__filter
            else:
                # The first specification is given as lookup specification
                self.__lookup_filter = ldapfilter.combine_filters((self.__filter, *spec_clauses[1:]))


# ------------------------------------------------------------------------------


class FactoryContext:
    """
    Represents the data stored in a component factory (class)
    """

    __slots__ = (
        "__handlers",
        "__inherited_configuration",
        "__instances",
        "bundle_context",
        "callbacks",
        "completed",
        "field_callbacks",
        "hidden_properties",
        "is_singleton",
        "is_singleton_active",
        "name",
        "properties",
        "properties_fields",
    )

    def __init__(self) -> None:
        """
        Sets up the factory context
        """
        # Factory bundle context
        self.bundle_context: BundleContext | None = None

        # Callbacks : Kind -> callback method
        self.callbacks: dict[str, Callable[..., Any]] = {}

        # Field callbacks: Field -> {Kind -> Callback}
        self.field_callbacks: dict[str, dict[str, tuple[Callable[..., Any], bool]]] = {}

        # The factory name
        self.name: str | None = None

        # Properties : Name -> Value
        self.properties: dict[str, Any] = {}

        # Properties fields : Field name -> Property name
        self.properties_fields: dict[str, str] = {}

        # Hidden Properties: Name -> Value
        self.hidden_properties: dict[str, Any] = {}

        # Singleton factory
        self.is_singleton = False

        # Singleton active
        self.is_singleton_active = False

        # The factory manipulation has been completed
        self.completed = False

        # Handler ID -> configuration
        self.__handlers: dict[str, Any] = {}

        # Inherited configuration
        self.__inherited_configuration: dict[str, Any] = {}

        # Instance name -> Instance properties
        self.__instances: dict[str, dict[str, Any]] = {}

    def __eq__(self, other: object) -> bool:
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

    def __ne__(self, other: object) -> bool:
        """
        Inequality test
        """
        return not self.__eq__(other)

    def _deepcopy(self, data: T) -> T:
        """
        Deep copies the given object

        :param data: Data to copy
        :return: A copy of the data, if supported, else the data itself
        """
        if isinstance(data, dict):
            # Copy dictionary values
            return cast(T, {key: self._deepcopy(value) for key, value in data.items()})
        elif isinstance(data, (list, tuple, set, frozenset)):
            # Copy sequence types values
            return cast(T, type(data)(self._deepcopy(value) for value in data))

        try:
            # Try to use a copy() method, if any
            return data.copy()  # type: ignore
        except AttributeError:
            # Can't copy the data, return it as is
            return data

    def copy(self, inheritance: bool = False) -> "FactoryContext":
        """
        Returns a deep copy of the current FactoryContext instance

        :param inheritance: If True, current handlers configurations are stored
                            as inherited ones
        """
        # Create a new factory context and duplicate its values
        new_context = FactoryContext()
        for field in self.__slots__:
            if not field.startswith("_"):
                setattr(new_context, field, self._deepcopy(getattr(self, field)))

        if inheritance:
            # Store configuration as inherited one
            new_context.__inherited_configuration = self.__handlers.copy()
            new_context.__handlers = {}

        # Remove instances in any case
        new_context.__instances.clear()
        new_context.is_singleton_active = False
        return new_context

    def inherit_handlers(self, excluded_handlers: Iterable[str] | None) -> None:
        """
        Merges the inherited configuration with the current ones

        :param excluded_handlers: Excluded handlers
        """
        if not excluded_handlers:
            excluded_handlers = ()

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

    def add_instance(self, name: str, properties: dict[str, Any]) -> None:
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

    def get_instances(self) -> dict[str, dict[str, Any]]:
        """
        Returns the dictionary of instances to start: name → properties

        :return: A dictionary: instance name → instance properties
        """
        return self._deepcopy(self.__instances)

    def get_handlers_ids(self) -> list[str]:
        """
        Retrieves the IDs of the handlers to instantiate for this component
        """
        return list(self.__handlers.keys())

    def get_handler(self, handler_id: str, default: Any = None) -> Any:
        """
        Retrieves the configuration associated to the given handler

        :param handler_id: The ID of the configured handler
        :param default: The default configuration value
        :return: The existing configuration or the given default
        """
        return self.__handlers.get(handler_id, default)

    def set_handler_default(self, handler_id: str, default: Any = None) -> Any:
        """
        Retrieves the configuration associated to the given handler, creates
        it the entry with the given value if necessary

        :param handler_id: The ID of the configured handler
        :param default: The default configuration value to store if none exists
        :return: The existing configuration or the given default
        """
        return self.__handlers.setdefault(handler_id, default)

    def set_handler(self, handler_id: str, configuration: Any) -> None:
        """
        Stores the configuration of the given handler

        :param handler_id: The ID of the configured handler
        :param configuration: The complete configuration of the handler
        """
        self.__handlers[handler_id] = configuration

    def set_bundle_context(self, bundle_context: BundleContext | None) -> None:
        """
        Sets up the bundle context associated to this factory context

        :param bundle_context: The factory bundle context (or None to clear it)
        """
        self.bundle_context = bundle_context


# ------------------------------------------------------------------------------


class ComponentContext:
    """
    Represents the data stored in a component instance
    """

    # Try to reduce memory footprint (many instances)
    __slots__ = ("__hidden_properties", "factory_context", "name", "properties")

    def __init__(self, factory_context: FactoryContext, name: str, properties: dict[str, Any]) -> None:
        """
        Sets up the context

        :param factory_context: The parent factory context
        :param properties: The component properties
        """
        self.factory_context = factory_context
        self.name = name

        # Force the instance name property
        properties[constants.IPOPO_INSTANCE_NAME] = name

        # Hidden properties
        hidden_props_keys = set(properties).intersection(factory_context.hidden_properties)

        self.__hidden_properties = factory_context.hidden_properties.copy()
        self.__hidden_properties.update(
            {key: value for key, value in properties.items() if key in hidden_props_keys}
        )

        # Public properties
        self.properties = factory_context.properties.copy()
        self.properties.update(
            {key: value for key, value in properties.items() if key not in hidden_props_keys}
        )

    def get_bundle_context(self) -> BundleContext:
        """
        Retrieves the bundle context

        :return: The component bundle context
        """
        if self.factory_context.bundle_context is None:
            raise ValueError(f"Bundle context not set for factory {self.name}")
        return self.factory_context.bundle_context

    def get_callback(self, event: str) -> Callable[..., Any] | None:
        """
        Retrieves the registered method for the given event. Returns None if
        not found

        :param event: A component life cycle event
        :return: The callback associated to the given event
        """
        try:
            return self.factory_context.callbacks.get(event)
        except KeyError:
            return None

    def get_field_callback(self, field: str, event: str) -> tuple[Callable[..., Any], bool] | None:
        """
        Retrieves the registered method for the given event. Returns None if
        not found

        :param field: Name of the dependency field
        :param event: A component life cycle event
        :return: A 2-tuple containing the callback associated to the given
                 event and flag indicating if the callback must be called in
                 valid state only
        """
        try:
            return self.factory_context.field_callbacks[field][event]
        except KeyError:
            return None

    def get_factory_name(self) -> str:
        """
        Retrieves the component factory name

        :return: The component factory name
        """
        if not self.factory_context.name:
            raise ValueError(f"Factory of {self.name} doesn't have a name")

        return self.factory_context.name

    def get_handler(self, handler_id: str) -> Any:
        """
        Retrieves the configuration for the given handler from the factory
        context

        :param handler_id: The ID of the configured handler
        :return: The handler configuration, or None
        """
        return self.factory_context.get_handler(handler_id, None)

    def has_hidden_properties(self) -> bool:
        """
        Returns True if the component must support hidden properties
        """
        return bool(self.__hidden_properties)

    def grab_hidden_properties(self) -> dict[str, Any]:
        """
        A one-shot access to hidden properties (the field is then destroyed)

        :return: A copy of the hidden properties dictionary on the first call
        :raise AttributeError: On any call after the first one
        """
        # Copy properties
        result = self.__hidden_properties.copy()

        # Destroy the field
        self.__hidden_properties.clear()
        del self.__hidden_properties
        return result
