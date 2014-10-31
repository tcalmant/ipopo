#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Temporal dependency handler

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0
:version: 0.5.9
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
__version_info__ = (0, 5, 9)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix beans
from pelix.constants import BundleActivator
from pelix.utilities import EventData

# iPOPO constants
import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants
import pelix.ipopo.handlers.requires as requires

# Standard library
import threading

# ------------------------------------------------------------------------------


class _HandlerFactory(requires._HandlerFactory):
    """
    Factory service for service registration handlers
    """
    def get_handlers(self, component_context, instance):
        """
        Sets up service providers for the given component

        :param component_context: The ComponentContext bean
        :param instance: The component instance
        :return: The list of handlers associated to the given component
        """
        # Extract information from the context
        requirements = component_context.get_handler(
            ipopo_constants.HANDLER_TEMPORAL)
        requires_filters = component_context.properties.get(
            ipopo_constants.IPOPO_REQUIRES_FILTERS, None)

        # Prepare requirements
        requirements = self._prepare_requirements(
            requirements, requires_filters)

        # Return handlers
        return [TemporalDependency(field, requirement)
                for field, requirement in requirements.items()]


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
        properties = {constants.PROP_HANDLER_ID:
                      ipopo_constants.HANDLER_TEMPORAL}

        # Register the handler factory service
        self._registration = context.register_service(
            constants.SERVICE_IPOPO_HANDLER_FACTORY,
            _HandlerFactory(), properties)

    def stop(self, context):
        """
        Bundle stopped
        """
        # Unregister the service
        self._registration.unregister()
        self._registration = None

# ------------------------------------------------------------------------------


class TemporalException(constants.HandlerException):
    """
    Temporal exception
    """
    pass


class _TemporalProxy(object):
    """
    The injected proxy
    """
    def __init__(self, timeout):
        """
        The temporal proxy
        """
        self.__event = EventData()
        self.__timeout = timeout

    def set_service(self, service):
        """
        Sets the injected service

        :param service: The injected service, or None
        """
        self.__event.set(service)

    def unset_service(self):
        """
        The injected service has gone away
        """
        self.__event.clear()

    def __getattr__(self, item):
        """
        Returns the attribute from the "real" service

        :return: The attribute
        """
        if self.__event.wait(self.__timeout):
            return getattr(self.__event.data, item)
        else:
            raise TemporalException("No service found before timeout")

    def __call__(self, *args, **kwargs):
        """
        Call the underlying object. Lets exception propagate
        """
        if self.__event.wait(self.__timeout):
            # We have a service: call it
            self.__event.data.__call__(*args, **kwargs)
        else:
            raise TemporalException("No service found before timeout")

    def __nonzero__(self):
        """
        Boolean value of the proxy
        """
        return self.__event.is_set() and bool(self.__event.data)


class TemporalDependency(requires.SimpleDependency):
    """
    Manages a temporal dependency field
    """
    def __init__(self, field, requirement):
        """
        Sets up the dependency
        """
        super(TemporalDependency, self).__init__(field, requirement)

        # Internal timeout
        # FIXME: use a customizable timeout
        self.__timeout = 10

        # The delayed unbind timer
        self.__timer = None
        self.__still_valid = False

        # The injected value is the proxy
        self._value = _TemporalProxy(self.__timeout)

    def on_service_arrival(self, svc_ref):
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if self.reference is None:
                # Inject the service
                service = self._context.get_service(svc_ref)
                self.reference = svc_ref
                self._value.set_service(service)
                self.__still_valid = True

                # Cancel timer
                if self.__timer is not None:
                    self.__timer.cancel()
                    self.__unbind_call(*self.__timer.args)
                    self.__timer = None

                # Bind the service
                self._ipopo_instance.bind(self, self._value, self.reference)
                return True

    def on_service_departure(self, svc_ref):
        """
        Called when a service has been unregistered from the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if svc_ref is self.reference:
                # Forget about the service
                self._value.unset_service()

                # Clear the reference
                self.reference = None

                # Look for a replacement
                self._pending_ref = self._context.get_service_reference(
                    self.requirement.specification,
                    self.requirement.filter)

                if self._pending_ref is None:
                    # No replacement found yet, wait a little
                    self.__still_valid = True
                    self.__timer = threading.Timer(
                        self.__timeout,
                        self.__unbind_call, (self._value, svc_ref))
                    self.__timer.start()

                else:
                    # Notify iPOPO immediately
                    self._ipopo_instance.unbind(self, self._value, svc_ref)
                return True

    def __unbind_call(self, service, svc_ref):
        """
        Calls the iPOPO unbind method
        """
        # Timeout expired, we're not valid anymore
        self.__timer = None
        self.__still_valid = False
        self._ipopo_instance.unbind(self, service, svc_ref)

    def is_valid(self):
        """
        Tests if the dependency is in a valid state
        """
        return self.__still_valid \
            and (super(TemporalDependency, self).is_valid()
                 or self._pending_ref is not None)
