#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Instance manager class definition

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
import logging
import threading
import traceback

# Standard typing module should be optional
try:
    # pylint: disable=W0611
    from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
    from pelix.framework import ServiceEvent, ServiceReference
    from pelix.ipopo.contexts import ComponentContext
except ImportError:
    pass

# Pelix
from pelix.constants import FrameworkException

# iPOPO constants
import pelix.ipopo.constants as constants
import pelix.ipopo.handlers.constants as handlers_const

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class StoredInstance(object):
    """
    Represents a component instance
    """

    # Try to reduce memory footprint (stored instances)
    __slots__ = (
        "bundle_context",
        "context",
        "factory_name",
        "instance",
        "name",
        "state",
        "_controllers_state",
        "_handlers",
        "_ipopo_service",
        "_lock",
        "_logger",
        "error_trace",
        "__all_handlers",
    )

    INVALID = 0
    """ This component has been invalidated """

    VALID = 1
    """ This component has been validated """

    KILLED = 2
    """ This component has been killed """

    VALIDATING = 3
    """ This component is currently validating """

    ERRONEOUS = 4
    """ This component has failed while validating """

    def __init__(self, ipopo_service, context, instance, handlers):
        # type: (Any, ComponentContext, Any, Iterable[Any]) -> None
        """
        Sets up the instance object

        :param ipopo_service: The iPOPO service that instantiated this
                              component
        :param context: The component context
        :param instance: The component instance
        :param handlers: The list of handlers associated to this component
        """
        # The logger
        self._logger = logging.getLogger(
            "-".join(("InstanceManager", context.name))
        )

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
        self.state = StoredInstance.INVALID

        # Stack track of validation error
        self.error_trace = None  # type: str

        # Store the bundle context
        self.bundle_context = self.context.get_bundle_context()

        # The controllers state dictionary
        self._controllers_state = {}  # type: Dict[str, bool]

        # Handlers: kind -> [handlers]
        self._handlers = {}  # type: Dict[str, Any]
        self.__all_handlers = set(handlers)
        for handler in handlers:
            kinds = handler.get_kinds()
            if kinds:
                for kind in kinds:
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
        return "StoredInstance(Name={0}, State={1})".format(
            self.name, self.state
        )

    def check_event(self, event):
        # type: (ServiceEvent) -> bool
        """
        Tests if the given service event must be handled or ignored, based
        on the state of the iPOPO service and on the content of the event.

        :param event: A service event
        :return: True if the event can be handled, False if it must be ignored
        """
        with self._lock:
            if self.state == StoredInstance.KILLED:
                # This call may have been blocked by the internal state lock,
                # ignore it
                return False

            return self.__safe_handlers_callback("check_event", event)

    def bind(self, dependency, svc, svc_ref):
        # type: (Any, Any, ServiceReference) -> None
        """
        Called by a dependency manager to inject a new service and update the
        component life cycle.
        """
        with self._lock:
            self.__set_binding(dependency, svc, svc_ref)
            self.check_lifecycle()

    def update(self, dependency, svc, svc_ref, old_properties, new_value=False):
        # type: (Any, Any, ServiceReference, dict, bool) -> None
        """
        Called by a dependency manager when the properties of an injected
        dependency have been updated.

        :param dependency: The dependency handler
        :param svc: The injected service
        :param svc_ref: The reference of the injected service
        :param old_properties: Previous properties of the dependency
        :param new_value: If True, inject the new value of the handler
        """
        with self._lock:
            self.__update_binding(
                dependency, svc, svc_ref, old_properties, new_value
            )
            self.check_lifecycle()

    def unbind(self, dependency, svc, svc_ref):
        # type: (Any, Any, ServiceReference) -> None
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
        # type: (str) -> bool
        """
        Retrieves the state of the controller with the given name

        :param name: The name of the controller
        :return: The value of the controller
        :raise KeyError: No value associated to this controller
        """
        return self._controllers_state[name]

    def set_controller_state(self, name, value):
        # type: (str, bool) -> None
        """
        Sets the state of the controller with the given name

        :param name: The name of the controller
        :param value: The new value of the controller
        """
        with self._lock:
            self._controllers_state[name] = value
            self.__safe_handlers_callback("on_controller_change", name, value)

    def update_property(self, name, old_value, new_value):
        # type: (str, Any, Any) -> None
        """
        Handles a property changed event

        :param name: The changed property name
        :param old_value: The previous property value
        :param new_value: The new property value
        """
        with self._lock:
            self.__safe_handlers_callback(
                "on_property_change", name, old_value, new_value
            )

    def update_hidden_property(self, name, old_value, new_value):
        # type: (str, Any, Any) -> None
        """
        Handles an hidden property changed event

        :param name: The changed property name
        :param old_value: The previous property value
        :param new_value: The new property value
        """
        with self._lock:
            self.__safe_handlers_callback(
                "on_hidden_property_change", name, old_value, new_value
            )

    def get_handlers(self, kind=None):
        """
        Retrieves the handlers of the given kind. If kind is None, all handlers
        are returned.

        :param kind: The kind of the handlers to return
        :return: A list of handlers, or an empty list
        """
        with self._lock:
            if kind is not None:
                try:
                    return self._handlers[kind][:]
                except KeyError:
                    return []

            return self.__all_handlers.copy()

    def check_lifecycle(self):
        """
        Tests if the state of the component must be updated, based on its own
        state and on the state of its dependencies
        """
        with self._lock:
            # Validation flags
            was_valid = self.state == StoredInstance.VALID
            can_validate = self.state not in (
                StoredInstance.VALIDATING,
                StoredInstance.VALID,
            )

            # Test the validity of all handlers
            handlers_valid = self.__safe_handlers_callback(
                "is_valid", break_on_false=True
            )

            if was_valid and not handlers_valid:
                # A dependency is missing
                self.invalidate(True)
            elif (
                can_validate and handlers_valid and self._ipopo_service.running
            ):
                # We're all good
                self.validate(True)

    def update_bindings(self):
        # type: () -> bool
        """
        Updates the bindings of the given component

        :return: True if the component can be validated
        """
        with self._lock:
            all_valid = True
            for handler in self.get_handlers(handlers_const.KIND_DEPENDENCY):
                # Try to bind
                self.__safe_handler_callback(handler, "try_binding")

                # Update the validity flag
                all_valid &= self.__safe_handler_callback(
                    handler, "is_valid", only_boolean=True, none_as_true=True
                )
            return all_valid

    def start(self):
        """
        Starts the handlers
        """
        with self._lock:
            self.__safe_handlers_callback("start")

    def retry_erroneous(self, properties_update):
        # type: (dict) -> int
        """
        Removes the ERRONEOUS state from a component and retries a validation

        :param properties_update: A dictionary to update component properties
        :return: The new state of the component
        """
        with self._lock:
            if self.state != StoredInstance.ERRONEOUS:
                # Not in erroneous state: ignore
                return self.state

            # Update properties
            if properties_update:
                self.context.properties.update(properties_update)

            # Reset state
            self.state = StoredInstance.INVALID
            self.error_trace = None

            # Retry
            self.check_lifecycle()

            # Check if the component is still erroneous
            return self.state

    def invalidate(self, callback=True):
        # type: (bool) -> bool
        """
        Applies the component invalidation.

        :param callback: If True, call back the component before the
                         invalidation
        :return: False if the component wasn't valid
        """
        with self._lock:
            if self.state != StoredInstance.VALID:
                # Instance is not running...
                return False

            # Change the state
            self.state = StoredInstance.INVALID

            # Call the handlers
            self.__safe_handlers_callback("pre_invalidate")

            # Call the component
            if callback:
                # pylint: disable=W0212
                self.__safe_validation_callback(
                    constants.IPOPO_CALLBACK_INVALIDATE
                )

                # Trigger an "Invalidated" event
                self._ipopo_service._fire_ipopo_event(
                    constants.IPopoEvent.INVALIDATED,
                    self.factory_name,
                    self.name,
                )

            # Call the handlers
            self.__safe_handlers_callback("post_invalidate")
            return True

    def kill(self):
        # type: () -> bool
        """
        This instance is killed : invalidate it if needed, clean up all members

        When this method is called, this StoredInstance object must have
        been removed from the registry

        :return: True if the component has been killed, False if it already was
        """
        with self._lock:
            # Already dead...
            if self.state == StoredInstance.KILLED:
                return False

            try:
                self.invalidate(True)
            except:
                self._logger.exception(
                    "%s: Error invalidating the instance", self.name
                )

            # Now that we are nearly clean, be sure we were in a good registry
            # state
            assert not self._ipopo_service.is_registered_instance(self.name)

            # Stop all handlers (can tell to unset a binding)
            for handler in self.get_handlers():
                results = self.__safe_handler_callback(handler, "stop")
                if results:
                    try:
                        for binding in results:
                            self.__unset_binding(
                                handler, binding[0], binding[1]
                            )
                    except Exception as ex:
                        self._logger.exception(
                            "Error stopping handler '%s': %s", handler, ex
                        )

            # Call the handlers
            self.__safe_handlers_callback("clear")

            # Change the state
            self.state = StoredInstance.KILLED

            # Trigger the event
            # pylint: disable=W0212
            self._ipopo_service._fire_ipopo_event(
                constants.IPopoEvent.KILLED, self.factory_name, self.name
            )

            # Clean up members
            self._handlers.clear()
            self.__all_handlers.clear()
            self._handlers = None
            self.__all_handlers = None
            self.context = None
            self.instance = None
            self._ipopo_service = None
            return True

    def validate(self, safe_callback=True):
        # type: (bool) -> bool
        """
        Ends the component validation, registering services

        :param safe_callback: If True, calls the component validation callback
        :return: True if the component has been validated, else False
        :raise RuntimeError: You try to awake a dead component
        """
        with self._lock:
            if self.state in (
                StoredInstance.VALID,
                StoredInstance.VALIDATING,
                StoredInstance.ERRONEOUS,
            ):
                # No work to do (yet)
                return False

            if self.state == StoredInstance.KILLED:
                raise RuntimeError("{0}: Zombies !".format(self.name))

            # Clear the error trace
            self.error_trace = None

            # Call the handlers
            self.__safe_handlers_callback("pre_validate")

            if safe_callback:
                # Safe call back needed and not yet passed
                self.state = StoredInstance.VALIDATING

                # Call @ValidateComponent first, then @Validate
                if not self.__safe_validation_callback(
                    constants.IPOPO_CALLBACK_VALIDATE
                ):
                    # Stop there if the callback failed
                    self.state = StoredInstance.VALID
                    self.invalidate(True)

                    # Consider the component has erroneous
                    self.state = StoredInstance.ERRONEOUS
                    return False

            # All good
            self.state = StoredInstance.VALID

            # Call the handlers
            self.__safe_handlers_callback("post_validate")

            # We may have caused a framework error, so check if iPOPO is active
            if self._ipopo_service is not None:
                # pylint: disable=W0212
                # Trigger the iPOPO event (after the service _registration)
                self._ipopo_service._fire_ipopo_event(
                    constants.IPopoEvent.VALIDATED, self.factory_name, self.name
                )
        return True

    def __callback(self, event, *args, **kwargs):
        # type: (str, *Any, **Any) -> Any
        """
        Calls the registered method in the component for the given event

        :param event: An event (IPOPO_CALLBACK_VALIDATE, ...)
        :return: The callback result, or None
        :raise Exception: Something went wrong
        """
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

    def __validation_callback(self, event):
        # type: (str) -> Any
        """
        Specific handling for the ``@ValidateComponent`` and
        ``@InvalidateComponent`` callback, as it requires checking arguments
        count and order

        :param event: The kind of life-cycle callback (in/validation)
        :return: The callback result, or None
        :raise Exception: Something went wrong
        """
        comp_callback = self.context.get_callback(event)
        if not comp_callback:
            # No registered callback
            return True

        # Get the list of arguments
        try:
            args = getattr(comp_callback, constants.IPOPO_VALIDATE_ARGS)
        except AttributeError:
            raise TypeError(
                "@ValidateComponent callback is missing internal description"
            )

        # Associate values to arguments
        mapping = {
            constants.ARG_BUNDLE_CONTEXT: self.bundle_context,
            constants.ARG_COMPONENT_CONTEXT: self.context,
            constants.ARG_PROPERTIES: self.context.properties.copy(),
        }
        mapped_args = [mapping[arg] for arg in args]

        # Call it
        result = comp_callback(self.instance, *mapped_args)
        if result is None:
            # Special case, if the call back returns nothing
            return True

        return result

    def __field_callback(self, field, event, *args, **kwargs):
        # type: (str, str, *Any, **Any) -> Any
        """
        Calls the registered method in the component for the given field event

        :param field: A field name
        :param event: An event (IPOPO_CALLBACK_VALIDATE, ...)
        :return: The callback result, or None
        :raise Exception: Something went wrong
        """
        # Get the field callback info
        cb_info = self.context.get_field_callback(field, event)
        if not cb_info:
            # No registered callback
            return True

        # Extract information
        callback, if_valid = cb_info

        if if_valid and self.state != StoredInstance.VALID:
            # Don't call the method if the component state isn't satisfying
            return True

        # Call it
        result = callback(self.instance, field, *args, **kwargs)
        if result is None:
            # Special case, if the call back returns nothing
            return True

        return result

    def safe_callback(self, event, *args, **kwargs):
        # type: (str, *Any, **Any) -> Any
        """
        Calls the registered method in the component for the given event,
        ignoring raised exceptions

        :param event: An event (IPOPO_CALLBACK_VALIDATE, ...)
        :return: The callback result, or None
        """
        if self.state == StoredInstance.KILLED:
            # Invalid state
            return None

        try:
            return self.__callback(event, *args, **kwargs)
        except FrameworkException as ex:
            # Important error
            self._logger.exception(
                "Critical error calling back %s: %s", self.name, ex
            )

            # Kill the component
            self._ipopo_service.kill(self.name)

            if ex.needs_stop:
                # Framework must be stopped...
                self._logger.error(
                    "%s said that the Framework must be stopped.", self.name
                )
                self.bundle_context.get_framework().stop()
            return False
        except:
            self._logger.exception(
                "Component '%s': error calling callback method for event %s",
                self.name,
                event,
            )
            return False

    def __safe_validation_callback(self, event):
        # type: (str) -> Any
        """
        Calls the ``@ValidateComponent`` or ``@InvalidateComponent`` callback,
        ignoring raised exceptions

        :param event: The kind of life-cycle callback (in/validation)
        :return: The callback result, or None
        """
        if self.state == StoredInstance.KILLED:
            # Invalid state
            return None

        try:
            return self.__validation_callback(event)
        except FrameworkException as ex:
            # Important error
            self._logger.exception(
                "Critical error calling back %s: %s", self.name, ex
            )

            # Kill the component
            self._ipopo_service.kill(self.name)

            # Store the exception as it is a validation error
            self.error_trace = traceback.format_exc()

            if ex.needs_stop:
                # Framework must be stopped...
                self._logger.error(
                    "%s said that the Framework must be stopped.", self.name
                )
                self.bundle_context.get_framework().stop()
            return False
        except:
            self._logger.exception(
                "Component '%s': error calling @ValidateComponent callback",
                self.name,
            )

            # Store the exception as it is a validation error
            self.error_trace = traceback.format_exc()

            return False

    def __safe_field_callback(self, field, event, *args, **kwargs):
        # type: (str, str, *Any, **Any) -> Any
        """
        Calls the registered method in the component for the given event,
        ignoring raised exceptions

        :param field: Name of the modified field
        :param event: A field event (IPOPO_CALLBACK_BIND_FIELD, ...)
        :return: The callback result, or None
        """
        if self.state == StoredInstance.KILLED:
            # Invalid state
            return None

        try:
            return self.__field_callback(field, event, *args, **kwargs)
        except FrameworkException as ex:
            # Important error
            self._logger.exception(
                "Critical error calling back %s: %s", self.name, ex
            )

            # Kill the component
            self._ipopo_service.kill(self.name)

            if ex.needs_stop:
                # Framework must be stopped...
                self._logger.error(
                    "%s said that the Framework must be stopped.", self.name
                )
                self.bundle_context.get_framework().stop()
            return False
        except:
            self._logger.exception(
                "Component '%s' : error calling "
                "callback method for event %s",
                self.name,
                event,
            )
            return False

    def __safe_handler_callback(self, handler, method_name, *args, **kwargs):
        # type: (Any, str, *Any, **Any) -> Any
        """
        Calls the given method with the given arguments in the given handler.
        Logs exceptions, but doesn't propagate them.

        Special arguments can be given in kwargs:

        * 'none_as_true': If set to True and the method returned None or
                          doesn't exist, the result is considered as True.
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
        only_boolean = kwargs.pop("only_boolean", False)
        none_as_true = kwargs.pop("none_as_true", False)

        # Get the method for each handler
        try:
            method = getattr(handler, method_name)
        except AttributeError:
            # Method not found
            result = None
        else:
            try:
                # Call it
                result = method(*args, **kwargs)
            except Exception as ex:
                # No result
                result = None

                # Log error
                self._logger.exception(
                    "Error calling handler '%s': %s", handler, ex
                )

        if result is None and none_as_true:
            # Consider None (nothing returned) as True
            result = True

        if only_boolean:
            # Convert to a boolean result
            return bool(result)

        return result

    def __safe_handlers_callback(self, method_name, *args, **kwargs):
        # type: (str, *Any, **Any) -> bool
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
        if self.state == StoredInstance.KILLED:
            # Nothing to do
            return False

        # Behavior flags
        exception_as_error = kwargs.pop("exception_as_error", False)
        break_on_false = kwargs.pop("break_on_false", False)

        result = True
        for handler in self.get_handlers():
            # Get the method for each handler
            try:
                method = getattr(handler, method_name)
            except AttributeError:
                # Ignore missing methods
                pass
            else:
                try:
                    # Call it
                    res = method(*args, **kwargs)
                    if res is not None and not res:
                        # Ignore 'None' results
                        result = False
                except Exception as ex:
                    # Log errors
                    self._logger.exception(
                        "Error calling handler '%s': %s", handler, ex
                    )

                    # We can consider exceptions as errors or ignore them
                    result = result and not exception_as_error

                if not handler and break_on_false:
                    # The loop can stop here
                    break

        return result

    def __set_binding(self, dependency, service, reference):
        # type: (Any, Any, ServiceReference) -> None
        """
        Injects a service in the component

        :param dependency: The dependency handler
        :param service: The injected service
        :param reference: The reference of the injected service
        """
        # Set the value
        setattr(self.instance, dependency.get_field(), dependency.get_value())

        # Call the component back
        self.safe_callback(constants.IPOPO_CALLBACK_BIND, service, reference)

        self.__safe_field_callback(
            dependency.get_field(),
            constants.IPOPO_CALLBACK_BIND_FIELD,
            service,
            reference,
        )

    def __update_binding(
        self, dependency, service, reference, old_properties, new_value
    ):
        # type: (Any, Any, ServiceReference, dict, bool) -> None
        """
        Calls back component binding and field binding methods when the
        properties of an injected dependency have been updated.

        :param dependency: The dependency handler
        :param service: The injected service
        :param reference: The reference of the injected service
        :param old_properties: Previous properties of the dependency
        :param new_value: If True, inject the new value of the handler
        """
        if new_value:
            # Set the value
            setattr(
                self.instance, dependency.get_field(), dependency.get_value()
            )

        # Call the component back
        self.__safe_field_callback(
            dependency.get_field(),
            constants.IPOPO_CALLBACK_UPDATE_FIELD,
            service,
            reference,
            old_properties,
        )

        self.safe_callback(
            constants.IPOPO_CALLBACK_UPDATE, service, reference, old_properties
        )

    def __unset_binding(self, dependency, service, reference):
        # type: (Any, Any, ServiceReference) -> None
        """
        Removes a service from the component

        :param dependency: The dependency handler
        :param service: The injected service
        :param reference: The reference of the injected service
        """
        # Call the component back
        self.__safe_field_callback(
            dependency.get_field(),
            constants.IPOPO_CALLBACK_UNBIND_FIELD,
            service,
            reference,
        )

        self.safe_callback(constants.IPOPO_CALLBACK_UNBIND, service, reference)

        # Update the injected field
        setattr(self.instance, dependency.get_field(), dependency.get_value())

        # Unget the service
        self.bundle_context.unget_service(reference)
