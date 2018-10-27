#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
RequiresBest handler implementation

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

# Pelix beans
from pelix.constants import BundleActivator, SERVICE_RANKING

# iPOPO constants
import pelix.ipopo.constants as ipopo_constants
import pelix.ipopo.handlers.constants as constants
import pelix.ipopo.handlers.requires as requires

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class _HandlerFactory(requires._HandlerFactory):
    # pylint: disable=W0212, R0903
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
            ipopo_constants.HANDLER_REQUIRES_BEST
        )
        requires_filters = component_context.properties.get(
            ipopo_constants.IPOPO_REQUIRES_FILTERS, None
        )

        # Prepare requirements
        requirements = self._prepare_requirements(
            requirements, requires_filters
        )

        # Set up the runtime dependency handlers
        return [
            BestDependency(field, requirement)
            for field, requirement in requirements.items()
        ]


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
            constants.PROP_HANDLER_ID: ipopo_constants.HANDLER_REQUIRES_BEST
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


class BestDependency(requires.SimpleDependency):
    """
    Manages a simple dependency field

    TODO: Allow to use a custom service reference comparator
    """

    def __init__(self, field, requirement):
        """
        Sets up members
        """
        super(BestDependency, self).__init__(field, requirement)

        # Current ranking
        self._current_ranking = None

    def clear(self):
        """
        Cleans up the manager. The manager can't be used after this method has
        been called
        """
        self._current_ranking = None
        super(BestDependency, self).clear()

    def on_service_arrival(self, svc_ref):
        """
        Called when a service has been registered in the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            new_ranking = svc_ref.get_property(SERVICE_RANKING)
            if self._current_ranking is not None:
                if new_ranking > self._current_ranking:
                    # New service with better ranking: use it
                    self._pending_ref = svc_ref
                    old_ref = self.reference
                    old_value = self._value

                    # Clean up like for a departure
                    self._current_ranking = None
                    self._value = None
                    self.reference = None

                    # Unbind (new binding will be done afterwards)
                    self._ipopo_instance.unbind(self, old_value, old_ref)
            else:
                # No ranking yet: inject the service
                self.reference = svc_ref
                self._value = self._context.get_service(svc_ref)
                self._current_ranking = new_ranking
                self._pending_ref = None

                self._ipopo_instance.bind(self, self._value, self.reference)

    def on_service_departure(self, svc_ref):
        """
        Called when a service has been unregistered from the framework

        :param svc_ref: A service reference
        """
        with self._lock:
            if svc_ref is self.reference:
                # Injected service going away...
                service = self._value

                # Clear the instance values
                self._current_ranking = None
                self._value = None
                self.reference = None

                if self.requirement.immediate_rebind:
                    # Look for a replacement
                    self._pending_ref = self._context.get_service_reference(
                        self.requirement.specification, self.requirement.filter
                    )
                else:
                    self._pending_ref = None

                self._ipopo_instance.unbind(self, service, svc_ref)

    def on_service_modify(self, svc_ref, old_properties):
        """
        Called when a service has been modified in the framework

        :param svc_ref: A service reference
        :param old_properties: Previous properties values
        """
        with self._lock:
            if self.reference is None:
                # A previously registered service now matches our filter
                return self.on_service_arrival(svc_ref)
            else:
                # Check if the ranking changed the service to inject
                best_ref = self._context.get_service_reference(
                    self.requirement.specification, self.requirement.filter
                )
                if best_ref is self.reference:
                    # Still the best service: notify the property modification
                    if svc_ref is self.reference:
                        # Call update only if necessary
                        self._ipopo_instance.update(
                            self, self._value, svc_ref, old_properties
                        )
                else:
                    # A new service is now the best: start a departure loop
                    self.on_service_departure(self.reference)

            return None
