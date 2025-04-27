#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Constants and exceptions for Pelix.

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

import inspect
from typing import TYPE_CHECKING, Any, List, Protocol, Type, TypeVar, Union

if TYPE_CHECKING:
    from pelix.framework import BundleContext

T = TypeVar("T")

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

ACTIVATOR = "__pelix_bundle_activator__"
"""
Name of the module member that will be used as bundle activator.
It must be an object with the following methods:

* start(BundleContext)
* stop(BundleContext)
"""

ACTIVATOR_LEGACY = "activator"
"""
Deprecated: prefer ACTIVATOR

Name of the module member that will be used as bundle activator.
It must be an object with the following methods:

* start(BundleContext)
* stop(BundleContext)
"""

OBJECTCLASS = "objectClass"
"""
Property containing the list of specifications (strings) provided by a service
"""

SERVICE_ID = "service.id"
"""
Property containing the ID of a service.
This ID is unique in a framework instance.
"""

SERVICE_BUNDLEID = "service.bundleid"
"""
Property containing the ID of the bundle providing the service.
"""

SERVICE_PID = "service.pid"
"""
Property containing the Persistent ID of a service, i.e. a string identifier
that will always be the same for a (kind of) service, even after restarting
the framework.
This is used by the Configuration Admin to bind managed services and
configurations.
"""

SERVICE_RANKING = "service.ranking"
"""
Property that indicates the ranking of a service. It is used to sort the
results of methods like get_service_references()
"""

SERVICE_SCOPE = "service.scope"
"""
Property that indicates the service's scope, one of "singleton", "bundle" or
"prototype".
This allows the framework to detect service factories and prototype service
factories.
"""

FRAMEWORK_UID = "framework.uid"
"""
Framework instance "unique" identifier. Used in Remote Services to identify
a framework from another.
It can be generated or be forced using the framework initialization properties.
This property is constant during the life of a framework instance.
"""

OSGI_FRAMEWORK_UUID = "org.osgi.framework.uuid"
"""
OSGi standard framework uuid property name.   Set in framework init to the value
of FRAMEWORK_UID
"""

# ------------------------------------------------------------------------------

SCOPE_SINGLETON = "singleton"
"""
Default service scope: the service is a singleton, which means that the service
object is shared by all bundles
"""

SCOPE_BUNDLE = "bundle"
"""
Service factory scope: the service factory is called each time a new bundle
requires the service.
Each service can have its own version of the service, but will get the same
version if it calls ``get_service()`` multiple times.
"""

SCOPE_PROTOTYPE = "prototype"
"""
Prototype service factory scope: the factory is called each time the caller
gets the service.
This allows all bundles to have multiples objects for the same service.
"""

# ------------------------------------------------------------------------------


class ActivatorProto(Protocol):
    """
    Interface of an activator
    """

    def __init__(self) -> None:
        ...

    def start(self, context: "BundleContext") -> None:
        """
        Bundle activated. This method should return quickly.

        :param context: Fresh bundle context
        """
        ...

    def stop(self, context: "BundleContext") -> None:
        """
        Bundle stopped. Resources should be cleared before this method returns

        :param context: Still valid bundle context
        """
        ...


def BundleActivator(clazz: Type[ActivatorProto]) -> Type[ActivatorProto]:
    # pylint: disable=C0103
    """
    Decorator to declare the bundle activator

    Instantiates the decorated class and stores it as a module member.

    :param clazz: The decorated bundle activator class
    :return: The class itself
    """
    # Add the activator instance to the module
    setattr(inspect.getmodule(clazz), ACTIVATOR, clazz())

    # Return the untouched class
    return clazz


# ------------------------------------------------------------------------------


class BundleException(Exception):
    """
    The base of all framework exceptions
    """

    def __init__(self, content: Any) -> None:
        """
        Sets up the exception
        """
        if isinstance(content, Exception):
            Exception.__init__(self, str(content))
        else:
            Exception.__init__(self, content)


class FrameworkException(Exception):
    """
    A framework exception is raised when an error can force the framework to
    stop.
    """

    def __init__(self, message: str, needs_stop: bool = False) -> None:
        """
        Sets up the exception

        :param message: A description of the exception
        :param needs_stop: If True, the framework must be stopped
        """
        Exception.__init__(self, message)
        self.needs_stop = needs_stop


# ------------------------------------------------------------------------------


def is_from_parent(cls: Type[Any], attribute_name: str, value: Any = None) -> bool:
    """
    Tests if the current attribute value is shared by a parent of the given
    class.

    Returns None if the attribute value is None.

    :param cls: Child class with the requested attribute
    :param attribute_name: Name of the attribute to be tested
    :param value: The exact value in the child class (optional)
    :return: True if the attribute value is shared with a parent class
    """
    if value is None:
        try:
            # Get the current value
            value = getattr(cls, attribute_name)
        except AttributeError:
            # No need to go further: the attribute does not exist
            return False

    for base in cls.__bases__:
        # Look for the value in each parent class
        try:
            return getattr(base, attribute_name) is value
        except AttributeError:
            pass

    # Attribute value not found in parent classes
    return False


# ------------------------------------------------------------------------------

# Specification field
PELIX_SPECIFICATION_FIELD = "__SPECIFICATION__"


class Specification:
    """
    Decorator that injects the Pelix specification information to the decorated class.

    Should be used on protocols and classes that will be registered as service using
    the register_service method.
    """

    def __init__(
        self,
        *specifications: Union[str, Type[Any], List[Union[str, Type[Any]]]],
        ignore_parent: bool = False,
    ) -> None:
        """
        :param specification: Specification of the provided service
        """
        self.__ignore_parent: bool = ignore_parent
        self.__spec: List[str] = []
        for spec in specifications:
            if isinstance(spec, list):
                self.__spec.extend(self._get_name(s) for s in spec)
            else:
                self.__spec.append(self._get_name(spec))

    def __call__(self, cls: Type[T]) -> Type[T]:
        """
        Injects the specification information to the decorated class
        """
        if not self.__spec:
            # No specification: use the class name
            self.__spec = [self._get_name(cls)]

        existing = getattr(cls, PELIX_SPECIFICATION_FIELD, None)
        if not existing:
            prepared = self.__spec
        elif is_from_parent(cls, PELIX_SPECIFICATION_FIELD, existing):
            # Specification already defined in a parent class
            if self.__ignore_parent:
                # Ignore the parent specification
                prepared = self.__spec
            else:
                # Add the specification to the existing one
                prepared = self.__spec + existing
        else:
            if isinstance(existing, list):
                prepared = self.__spec + existing
            else:
                prepared = self.__spec + [existing]

        # Filter to avoid duplicates
        injected: List[str] = []
        for spec in prepared:
            if spec not in injected:
                injected.append(spec)

        setattr(cls, PELIX_SPECIFICATION_FIELD, injected)
        return cls

    def _get_name(self, clazz: Union[str, Type[Any]]) -> str:
        """
        Returns the given string of the name of the class
        """
        if isinstance(clazz, str):
            return clazz

        return clazz.__name__
