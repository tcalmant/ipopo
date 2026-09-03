#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
iPOPO instantiation waiting list

Waits for a factory to be registered, or to appear again, to instantiate its
components.

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

# Standard library
import logging
import threading
from collections.abc import Iterable
from typing import Any

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
__version_info__ = (3, 2, 2)
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
        self.__context: BundleContext | None = bundle_context

        # The "queue": factory name -> {component name -> properties}
        self.__queue: dict[str, dict[str, dict[str, Any]]] = {}

        # Component Name -> Factory Name
        self.__names: dict[str, str] = {}

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
                _logger.error("Component %s already running: %s", component, ex)
            except Exception:
                # Other error
                _logger.exception("Error instantiating component %s from factory %s", component, factory)
            else:
                with self.__lock:
                    removed_concurrently = self.__names.get(component) != factory
                    queued = self.__queue.get(factory, {}).get(component)

                if removed_concurrently:
                    # remove() raced with this instantiation: its kill()
                    # attempt failed because the component didn't exist yet.
                    # Finish the job now that it does
                    try:
                        with use_ipopo(self.__context) as ipopo_svc:
                            ipopo_svc.kill(component)
                    except (BundleException, ValueError):
                        pass
                elif queued is not None and queued is not properties:
                    # update() raced with this instantiation: it stored a new
                    # dictionary and its reconfigure() call was lost, as the
                    # component didn't exist yet. Apply the new properties now
                    try:
                        ipopo.reconfigure(component, queued)
                    except ValueError:
                        # Component killed in the meantime
                        pass

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

    def add(self, factory: str, component: str, properties: dict[str, Any] | None = None) -> None:
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

        # Instantiate outside of the lock: the callbacks of the component can
        # call back into this service from another thread
        try:
            with use_ipopo(self.__context) as ipopo:
                # Try to instantiate the component right now
                self._try_instantiate(ipopo, factory, component)
        except BundleException:
            # iPOPO not yet started
            pass

    def update(
        self, component: str, properties: dict[str, Any], removed: Iterable[str] | None = None
    ) -> None:
        """
        Updates the properties of a queued component. The given properties are
        merged into the current ones: entries that are not given are left
        unchanged. If the component is already instantiated, its properties are
        updated in place.

        The names given in ``removed`` are dropped from the queued properties,
        so that the next instantiation of the component uses the value declared
        by its factory. A value given for them in ``properties`` is still
        applied to the running component, which lets the caller give back their
        declared value right away.

        :param component: A component name
        :param properties: The properties to update
        :param removed: Names of the properties to drop from the queue
        :raise KeyError: Unknown component
        :raise ValueError: The waiting list has no bundle context
        """
        if self.__context is None:
            raise ValueError("Missing context for iPOPO waiting list")

        with self.__lock:
            # Find its factory (raises KeyError if the component is unknown)
            factory = self.__names[component]

            # Keep the merged properties for the next instantiation. Store a
            # new dictionary: the queued one belongs to the caller of add()
            queued = {**self.__queue[factory][component], **properties}
            for key in removed or ():
                queued.pop(key, None)

            self.__queue[factory][component] = queued

        # Reconfigure outside of the lock (see add())
        try:
            with use_ipopo(self.__context) as ipopo:
                # Update the running component, if any
                ipopo.reconfigure(component, properties)
        except BundleException:
            # iPOPO not yet started
            pass
        except ValueError:
            # Component is not instantiated: this is the normal state of a
            # component waiting for its factory, the properties above will be
            # given to it when it is created
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

        # Kill the component outside of the lock (see add())
        try:
            with use_ipopo(self.__context) as ipopo:
                try:
                    ipopo.kill(component)
                except ValueError:
                    # Component not instantiated
                    pass

                with self.__lock:
                    new_factory = self.__names.get(component)

                if new_factory is not None and not ipopo.is_registered_instance(component):
                    # add() raced with this removal: the kill() above destroyed
                    # the component it had just instantiated. Create it again
                    self._try_instantiate(ipopo, new_factory, component)
        except BundleException:
            # iPOPO not yet started
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
        self.__registration: ServiceRegistration[IPopoWaitingList] | None = None
        self.__service: IPopoWaitingListImpl | None = None

    def start(self, context: BundleContext) -> None:
        """
        Bundle started
        """
        # Start the service
        self.__service = IPopoWaitingListImpl(context)
        self.__service._start()

        # Register it
        self.__registration = context.register_service(IPopoWaitingList, self.__service, {})

    def stop(self, context: BundleContext) -> None:
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
