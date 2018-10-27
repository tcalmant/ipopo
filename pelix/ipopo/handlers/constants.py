#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO handlers constants and base classes

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

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

SERVICE_IPOPO_HANDLER_FACTORY = "ipopo.handler.factory"
"""
iPOPO handler factory service specification. Those services should implement
the methods of HandlerFactory.
"""

PROP_HANDLER_ID = "ipopo.handler.id"
""" Service property: the ID of the iPOPO handler factory """

# ------------------------------------------------------------------------------

KIND_PROPERTIES = "properties"
"""
Represents the 'properties' kind of handler, which manipulates the component
to notify property changes.
"""

KIND_DEPENDENCY = "dependency"
"""
Represents the 'dependency' kind of handler.
Those handlers must implement the following methods:

* get_bindings(): Retrieves the list of bound service references
* is_valid(): Returns True if the dependency is in a valid state
"""

KIND_SERVICE_PROVIDER = "service_provider"
"""
Represents the 'service_provider' kind of handler.
Those handlers must implement the following method:

* get_service_reference(): Retrieves the reference of the provided service
  (a ServiceReference object).

It should also implement the following ones:

* on_controller_changer(): Called when a component controller has been
  modified. The publication of a service might be stopped if its controller is
  set to False.
* on_property_change(): Called when a component property has been modified.
  The provided service properties should be modified accordingly.
"""

# ------------------------------------------------------------------------------


class HandlerFactory(object):
    # pylint: disable=R0903
    """
    Handler factory abstract class
    """

    def get_handlers(self, component_context, instance):
        """
        Prepares handlers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
        """
        pass


# ------------------------------------------------------------------------------


class Handler(object):
    """
    Basic handler abstract class
    """

    def get_kinds(self):
        # pylint: disable=R0201
        """
        Returns the kinds of this handler

        :return: A tuple of the kinds of this handler, or None
        """
        pass

    def manipulate(self, stored_instance, component_instance):
        """
        Manipulates the associated component instance
        """
        pass

    def check_event(self, event):
        # pylint: disable=R0201, W0613
        """
        Tests if the given service event must be handled or ignored, based
        on the state of the iPOPO service and on the content of the event.

        :param event: A service event
        :return: True if the event can be handled, False if it must be ignored
        """
        return True

    def is_valid(self):
        # pylint: disable=R0201
        """
        Checks this handler is valid. All handlers must be valid for a
        component to be validated

        :return: True if the handler is in a valid state
        """
        return True

    def on_controller_change(self, name, value):
        """
        Notifies the change of state of the controller with the given name

        :param name: The name of the controller
        :param value: The new value of the controller
        """
        pass

    def on_property_change(self, name, old_value, new_value):
        """
        Handles a property changed event

        :param name: The changed property name
        :param old_value: The previous property value
        :param new_value: The new property value
        """
        pass

    def start(self):
        """
        Starts the handler (listeners, ...). Called once, after the component
        has been manipulated by all handlers.
        """
        pass

    def stop(self):
        """
        Stops the handler. Called once, just after the component has been
        killed
        """
        pass

    def clear(self):
        """
        Called just after a component has been killed and all handlers have
        been stopped. The handler should release all its resources here.
        """
        pass

    def pre_validate(self):
        """
        Called just before a component is validated
        """
        pass

    def post_validate(self):
        """
        Called just after a component has been validated
        """
        pass

    def pre_invalidate(self):
        """
        Called just before a component is invalidated
        """
        pass

    def post_invalidate(self):
        """
        Called just after a component has been invalidated
        """
        pass


class HandlerException(Exception):
    """
    Kind of exception used by handlers
    """

    pass


# ------------------------------------------------------------------------------


class ServiceProviderHandler(Handler):
    """
    Service provider handler abstract class
    """

    def get_service_reference(self):
        # pylint: disable=R0201
        """
        Returns the reference to the service provided by this handler
        """
        return None


# ------------------------------------------------------------------------------


class DependencyHandler(Handler):
    """
    Dependency handler abstract class
    """

    def get_field(self):
        # pylint: disable=R0201
        """
        Returns the name of the field where to inject the dependency
        """
        return None

    def try_binding(self):
        # pylint: disable=R0201
        """
        Forces the handler to try to bind to existing services
        """
        pass

    def get_bindings(self):
        # pylint: disable=R0201
        """
        Retrieves the list of the references to the bound services

        :return: A list of ServiceReferences objects
        """
        return None

    def get_value(self):
        # pylint: disable=R0201
        """
        Returns the value to inject
        """
        return None
