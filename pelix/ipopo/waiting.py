#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO instantiation waiting list

Waits for a factory to be registered, or to appear again, to instantiate its
components.

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

# Standard library
import logging
import threading
from typing import Any, Dict, Optional

# Pelix
from pelix.constants import ActivatorProto, BundleActivator, BundleException
from pelix.framework import BundleContext
from pelix.internals.events import ServiceEvent
from pelix.internals.registry import ServiceRegistration
from pelix.ipopo.constants import (
    SERVICE_IPOPO,
    IPopoEvent,
    IPopoService,
    IPopoWaitingList,
    use_ipopo,
)

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class IPopoWaitingListImpl(IPopoWaitingList):
    """
    iPOPO instantiation waiting list
    """

    def __init__(self, bundle_context: BundleContext) -> None:
        """
        Sets up members

        :param bundle_context: The bundle context
        """
        # Bundle context
        self.__context: Optional[BundleContext] = bundle_context

        # The "queue": factory name -> {component name -> properties}
        self.__queue: Dict[str, Dict[str, Dict[str, Any]]] = {}

        # Component Name -> Factory Name
        self.__names: Dict[str, str] = {}

        # Some locking
        self.__lock = threading.RLock()

    def _try_instantiate(self, ipopo: IPopoService, factory: str, component: str) -> None:
        """
        Tries to instantiate a component from the queue. Hides all exceptions.

        :param ipopo: The iPOPO service
        :param factory: Component factory
        :param component: Component name
        """
        try:
            # Get component properties
            with self.__lock:
                properties = self.__queue[factory][component]
        except KeyError:
            # Component not in queue
            return
        else:
            try:
                # Try instantiation
                ipopo.instantiate(factory, component, properties)
            except TypeError:
                # Unknown factory: try later
                pass
            except ValueError as ex:
                # Already known component
                _logger.error("Component already running: %s", ex)
            except Exception as ex:
                # Other error
                _logger.exception("Error instantiating component: %s", ex)

    def _start(self) -> None:
        """
        Starts the instantiation queue (called by its bundle activator)
        """
        if self.__context is None:
            raise ValueError("Missing context for iPOPO waiting list")

        try:
            # Try to register to factory events
            with use_ipopo(self.__context) as ipopo:
                ipopo.add_listener(self)
        except BundleException:
            # Service not yet present
            pass

        # Register the iPOPO service listener
        self.__context.add_service_listener(self, specification=SERVICE_IPOPO)

    def _stop(self) -> None:
        """
        Stops the instantiation queue (called by its bundle activator)
        """
        if self.__context is None:
            raise ValueError("Missing context for iPOPO waiting list")

        # Unregisters the iPOPO service listener
        self.__context.remove_service_listener(self)

        try:
            # Try to register to factory events
            with use_ipopo(self.__context) as ipopo:
                ipopo.remove_listener(self)
        except BundleException:
            # Service not present anymore
            pass

    def _clear(self) -> None:
        """
        Clear all references (called by its bundle activator)
        """
        self.__names.clear()
        self.__queue.clear()
        self.__context = None

    def service_changed(self, event: ServiceEvent[Any]) -> None:
        """
        Handles an event about the iPOPO service
        """
        if self.__context is None:
            raise ValueError("Missing context for iPOPO waiting list")

        kind = event.get_kind()
        if kind == ServiceEvent.REGISTERED:
            # iPOPO service registered: register to factory events
            with use_ipopo(self.__context) as ipopo:
                ipopo.add_listener(self)

    def handle_ipopo_event(self, event: IPopoEvent) -> None:
        """
        Handles an iPOPO event

        :param event: iPOPO event bean
        """
        if self.__context is None:
            raise ValueError("Missing context for iPOPO waiting list")

        kind = event.get_kind()
        if kind == IPopoEvent.REGISTERED:
            # A factory has been registered
            try:
                with use_ipopo(self.__context) as ipopo:
                    factory = event.get_factory_name()

                    with self.__lock:
                        # Copy the list of components names for this factory
                        components = self.__queue[factory].copy()

                    for component in components:
                        self._try_instantiate(ipopo, factory, component)
            except BundleException:
                # iPOPO not yet started
                pass
            except KeyError:
                # No components for this new factory
                pass

    def add(self, factory: str, component: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """
        Enqueues the instantiation of the given component

        :param factory: Factory name
        :param component: Component name
        :param properties: Component properties
        :raise ValueError: Component name already reserved in the queue
        :raise Exception: Error instantiating the component
        """
        if self.__context is None:
            raise ValueError("Missing context for iPOPO waiting list")

        with self.__lock:
            if component in self.__names:
                raise ValueError(f"Component name already queued: {component}")

            # Normalize properties
            if properties is None:
                properties = {}

            # Store component description
            self.__names[component] = factory
            self.__queue.setdefault(factory, {})[component] = properties

            try:
                with use_ipopo(self.__context) as ipopo:
                    # Try to instantiate the component right now
                    self._try_instantiate(ipopo, factory, component)
            except BundleException:
                # iPOPO not yet started
                pass

    def remove(self, component: str) -> None:
        """
        Kills/Removes the component with the given name

        :param component: A component name
        :raise KeyError: Unknown component
        """
        if self.__context is None:
            raise ValueError("Missing context for iPOPO waiting list")

        with self.__lock:
            # Find its factory
            factory = self.__names.pop(component)
            components = self.__queue[factory]

            # Clear the queue
            del components[component]
            if not components:
                # No more component for this factory
                del self.__queue[factory]

            # Kill the component
            try:
                with use_ipopo(self.__context) as ipopo:
                    # Try to instantiate the component right now
                    ipopo.kill(component)
            except (BundleException, ValueError):
                # iPOPO not yet started or component not instantiated
                pass


# ------------------------------------------------------------------------------


@BundleActivator
class Activator(ActivatorProto):
    """
    The bundle activator
    """

    def __init__(self) -> None:
        """
        Constructor
        """
        self.__registration: Optional[ServiceRegistration[IPopoWaitingList]] = None
        self.__service: Optional[IPopoWaitingListImpl] = None

    def start(self, context: BundleContext) -> None:
        """
        Bundle started
        """
        # Start the service
        self.__service = IPopoWaitingListImpl(context)
        self.__service._start()

        # Register it
        self.__registration = context.register_service(IPopoWaitingList, self.__service, {})

    def stop(self, _: BundleContext) -> None:
        """
        Bundle stopped
        """
        if self.__registration is not None:
            # Unregister the service
            self.__registration.unregister()
            self.__registration = None

        if self.__service is not None:
            # Stop the service
            self.__service._stop()

            # Clear it
            self.__service._clear()
            self.__service = None
