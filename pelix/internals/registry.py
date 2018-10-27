#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Service registry and event dispatcher for Pelix.

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
import bisect
import logging
import threading

# Standard typing module should be optional
try:
    # pylint: disable=W0611
    from typing import Any, Dict, List, Optional, Set, Tuple, Union
except ImportError:
    pass

# Pelix beans
from pelix.constants import (
    OBJECTCLASS,
    SERVICE_ID,
    SERVICE_RANKING,
    SERVICE_BUNDLEID,
    SERVICE_SCOPE,
    SCOPE_SINGLETON,
    SCOPE_BUNDLE,
    SCOPE_PROTOTYPE,
    BundleException,
)
from pelix.services import SERVICE_EVENT_LISTENER_HOOK
from pelix.internals.events import ServiceEvent

# Pelix utility modules
from pelix.utilities import is_string
import pelix.ldapfilter as ldapfilter

# Event hooks
from pelix.internals.hooks import ListenerInfo, ShrinkableList, ShrinkableMap

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class _UsageCounter(object):
    """
    Simple reference usage counter
    """

    __slots__ = ("__count",)

    def __init__(self):
        self.__count = 0

    def inc(self):
        """
        Counter is incremented
        """
        self.__count += 1

    def dec(self):
        """
        Counter is decremented

        :return: True if the counter is still greater than 0
        """
        self.__count -= 1
        return self.__count > 0

    def is_used(self):
        """
        Tests if the reference is still used

        :return: True if the counter is still greater than 0
        """
        return self.__count > 0


# ------------------------------------------------------------------------------


class _FactoryCounter(object):
    """
    A service factory usage counter per bundle and reference
    """

    __slots__ = ("__bundle", "__factored")

    def __init__(self, bundle):
        """
        Sets up members

        :param bundle: The bundle monitored by this counter
        """
        self.__bundle = bundle

        # Service Factory Reference -> (Service instance, Usage counter)
        self.__factored = {}

    def is_used(self):
        # type: () -> bool
        """
        Checks if this counter has at least one value

        :return: True if a service is still referenced by this service
        """
        return bool(self.__factored)

    def _get_from_factory(self, factory, svc_registration):
        # type: (Any, ServiceRegistration) -> Any
        """
        Returns a service instance from a Prototype Service Factory

        :param factory: The prototype service factory
        :param svc_registration: The ServiceRegistration object
        :return: The requested service instance returned by the factory
        """
        svc_ref = svc_registration.get_reference()
        try:
            # Use the existing service
            service, counter = self.__factored[svc_ref]
            counter.inc()
        except KeyError:
            # Create the service
            service = factory.get_service(self.__bundle, svc_registration)
            counter = _UsageCounter()
            counter.inc()

            # Store the counter
            self.__factored[svc_ref] = (service, counter)

        return service

    def _get_from_prototype(self, factory, svc_registration):
        # type: (Any, ServiceRegistration) -> Any
        """
        Returns a service instance from a Prototype Service Factory

        :param factory: The service factory
        :param svc_registration: The ServiceRegistration object
        :return: The requested service instance returned by the factory
        """
        svc_ref = svc_registration.get_reference()
        service = factory.get_service(self.__bundle, svc_registration)

        try:
            # Check if the service already exists
            services, counter = self.__factored[svc_ref]
            services.append(service)
            counter.inc()
        except KeyError:
            counter = _UsageCounter()
            counter.inc()

            # Store the counter
            self.__factored[svc_ref] = ([service], counter)

        return service

    def get_service(self, factory, svc_registration):
        # type: (Any, ServiceRegistration) -> Any
        """
        Returns the service required by the bundle. The Service Factory is
        called only when necessary while the Prototype Service Factory is
        called each time

        :param factory: The service factory
        :param svc_registration: The ServiceRegistration object
        :return: The requested service instance (created if necessary)
        """
        svc_ref = svc_registration.get_reference()
        if svc_ref.is_prototype():
            return self._get_from_prototype(factory, svc_registration)

        return self._get_from_factory(factory, svc_registration)

    def unget_service(self, factory, svc_registration, service=None):
        # type: (Any, ServiceRegistration, Any) -> bool
        """
        Releases references to the given service reference

        :param factory: The service factory
        :param svc_registration: The ServiceRegistration object
        :param service: Service instance (for prototype factories)
        :return: True if all service references to this service factory
                 have been released
        """
        svc_ref = svc_registration.get_reference()
        try:
            _, counter = self.__factored[svc_ref]
        except KeyError:
            logging.warning(
                "Trying to release an unknown service factory: %s", svc_ref
            )
        else:
            if svc_ref.is_prototype():
                # Notify the factory to clean up this instance
                factory.unget_service_instance(
                    self.__bundle, svc_registration, service
                )

            if not counter.dec():
                # All references have been released: clean up
                del self.__factored[svc_ref]

                # Call the factory
                factory.unget_service(self.__bundle, svc_registration)

                # No more reference to this service
                return True

        # Some references are still there
        return False

    def cleanup_service(self, factory, svc_registration):
        # type: (Any, ServiceRegistration) -> bool
        """
        If this bundle used that factory, releases the reference; else does
        nothing

        :param factory: The service factory
        :param svc_registration: The ServiceRegistration object
        :return: True if the bundle was using the factory, else False
        """
        svc_ref = svc_registration.get_reference()
        try:
            # "service" for factories, "services" for prototypes
            services, _ = self.__factored.pop(svc_ref)
        except KeyError:
            return False
        else:
            if svc_ref.is_prototype() and services:
                for service in services:
                    try:
                        factory.unget_service_instance(
                            self.__bundle, svc_registration, service
                        )
                    except Exception:
                        # Ignore instance-level exceptions, potential errors
                        # will reappear in unget_service()
                        pass

            # Call the factory
            factory.unget_service(self.__bundle, svc_registration)

            # No more association
            svc_ref.unused_by(self.__bundle)
            return True


# ------------------------------------------------------------------------------


class ServiceReference(object):
    """
    Represents a reference to a service
    """

    __slots__ = (
        "__bundle",
        "__properties",
        "__service_id",
        "__sort_key",
        "__using_bundles",
        "_props_lock",
        "__usage_lock",
    )

    def __init__(self, bundle, properties):
        """
        :param bundle: The bundle registering the service
        :param properties: The service properties
        :raise BundleException: The properties doesn't contain mandatory
                                entries
        """
        # Check properties
        for mandatory in SERVICE_ID, OBJECTCLASS:
            if mandatory not in properties:
                raise BundleException(
                    "A Service must at least have a '{0}' entry".format(
                        mandatory
                    )
                )

        # Properties lock (used by ServiceRegistration too)
        self._props_lock = threading.RLock()

        # Usage lock
        self.__usage_lock = threading.Lock()

        # Service details
        self.__bundle = bundle
        self.__properties = properties
        self.__service_id = properties[SERVICE_ID]

        # Bundle object -> Usage Counter object
        self.__using_bundles = {}

        # Compute the sort key
        self.__sort_key = None
        self.update_sort_key()

    def __str__(self):
        """
        String representation
        """
        return "ServiceReference(ID={0}, Bundle={1}, Specs={2})".format(
            self.__service_id,
            self.__bundle.get_bundle_id(),
            self.__properties[OBJECTCLASS],
        )

    def __hash__(self):
        """
        Returns the service hash, i.e. its ID, unique in a framework instance.

        :return: The service ID
        """
        return self.__service_id

    def __eq__(self, other):
        """
        Two references are equal if they have the same service ID
        """
        # pylint: disable=W0212
        return self.__service_id == other.__service_id

    def __lt__(self, other):
        """
        Lesser than other
        """
        # pylint: disable=W0212
        return self.__sort_key < other.__sort_key

    def __gt__(self, other):
        """
        Greater than other
        """
        # pylint: disable=W0212
        return self.__sort_key > other.__sort_key

    def __le__(self, other):
        """
        Lesser than or equal to other"
        """
        # pylint: disable=W0212
        return self.__sort_key <= other.__sort_key

    def __ge__(self, other):
        """
        Greater than or equal to other
        """
        # pylint: disable=W0212
        return self.__sort_key >= other.__sort_key

    def __ne__(self, other):
        """
        Two references are different if they have different service IDs
        """
        # pylint: disable=W0212
        return self.__service_id != other.__service_id

    def get_bundle(self):
        """
        Returns the bundle that registered this service

        :return: the bundle that registered this service
        """
        return self.__bundle

    def get_using_bundles(self):
        """
        Returns the list of bundles that use this service

        :return: A list of Bundle objects
        """
        return list(self.__using_bundles.keys())

    def get_properties(self):
        """
        Returns a copy of the service properties

        :return: A copy of the service properties
        """
        with self._props_lock:
            return self.__properties.copy()

    def get_property(self, name):
        """
        Retrieves the property value for the given name

        :return: The property value, None if not found
        """
        with self._props_lock:
            return self.__properties.get(name)

    def get_property_keys(self):
        """
        Returns an array of the keys in the properties of the service

        :return: An array of property keys.
        """
        with self._props_lock:
            return tuple(self.__properties.keys())

    def is_factory(self):
        """
        Returns True if this reference points to a service factory

        :return: True if the service provides from a factory
        """
        return self.__properties[SERVICE_SCOPE] in (
            SCOPE_BUNDLE,
            SCOPE_PROTOTYPE,
        )

    def is_prototype(self):
        """
        Returns True if this reference points to a prototype service factory

        :return: True if the service provides from a prototype factory
        """
        return self.__properties[SERVICE_SCOPE] == SCOPE_PROTOTYPE

    def unused_by(self, bundle):
        """
        Indicates that this reference is not being used anymore by the given
        bundle.
        This method should only be used by the framework.

        :param bundle: A bundle that used this reference
        """
        if bundle is None or bundle is self.__bundle:
            # Ignore
            return

        with self.__usage_lock:
            try:
                if not self.__using_bundles[bundle].dec():
                    # This bundle has cleaner all of its usages of this
                    # reference
                    del self.__using_bundles[bundle]
            except KeyError:
                # Ignore error
                pass

    def used_by(self, bundle):
        """
        Indicates that this reference is being used by the given bundle.
        This method should only be used by the framework.

        :param bundle: A bundle using this reference
        """
        if bundle is None or bundle is self.__bundle:
            # Ignore
            return

        with self.__usage_lock:
            self.__using_bundles.setdefault(bundle, _UsageCounter()).inc()

    def __compute_key(self):
        """
        Computes the sort key according to the service properties

        :return: The sort key to use for this reference
        """
        return (
            -int(self.__properties.get(SERVICE_RANKING, 0)),
            self.__service_id,
        )

    def needs_sort_update(self):
        """
        Checks if the sort key must be updated

        :return: True if the sort key must be updated
        """
        return self.__sort_key != self.__compute_key()

    def update_sort_key(self):
        """
        Recomputes the sort key, based on the service ranking and ID

        See: http://www.osgi.org/javadoc/r4v43/org/osgi/framework/
                          ServiceReference.html#compareTo%28java.lang.Object%29
        """
        self.__sort_key = self.__compute_key()


# ------------------------------------------------------------------------------


class ServiceRegistration(object):
    """
    Represents a service registration object
    """

    __slots__ = (
        "__framework",
        "__reference",
        "__properties",
        "__update_callback",
    )

    def __init__(self, framework, reference, properties, update_callback):
        """
        :param framework: The host framework
        :param reference: A service reference
        :param properties: A reference to the ServiceReference properties
                           dictionary object
        :param update_callback: Method to call when the sort key is modified
        """
        self.__framework = framework
        self.__reference = reference  # type: ServiceReference
        self.__properties = properties
        self.__update_callback = update_callback

    def __str__(self):
        """
        String representation
        """
        return "ServiceRegistration({0})".format(self.__reference)

    def get_reference(self):
        # type: () -> ServiceReference
        """
        Returns the reference associated to this registration

        :return: A ServiceReference object
        """
        return self.__reference

    def set_properties(self, properties):
        """
        Updates the service properties

        :param properties: The new properties
        :raise TypeError: The argument is not a dictionary
        """
        if not isinstance(properties, dict):
            raise TypeError("Waiting for dictionary")

        # Keys that must not be updated
        for forbidden_key in OBJECTCLASS, SERVICE_ID:
            try:
                del properties[forbidden_key]
            except KeyError:
                pass

        to_delete = []
        for key, value in properties.items():
            if self.__properties.get(key) == value:
                # No update
                to_delete.append(key)

        for key in to_delete:
            # Remove unchanged properties
            del properties[key]

        if not properties:
            # Nothing to do
            return

        # Ensure that the service has a valid service ranking
        try:
            properties[SERVICE_RANKING] = int(properties[SERVICE_RANKING])
        except (ValueError, TypeError):
            # Bad value: ignore update
            del properties[SERVICE_RANKING]
        except KeyError:
            # Service ranking not updated: ignore
            pass

        # pylint: disable=W0212
        with self.__reference._props_lock:
            # Update the properties
            previous = self.__properties.copy()
            self.__properties.update(properties)

            if self.__reference.needs_sort_update():
                # The sort key and the registry must be updated
                self.__update_callback(self.__reference)

            # Trigger a new computation in the framework
            event = ServiceEvent(
                ServiceEvent.MODIFIED, self.__reference, previous
            )

            self.__framework._dispatcher.fire_service_event(event)

    def unregister(self):
        """
        Unregisters the service
        """
        self.__framework.unregister_service(self)


# ------------------------------------------------------------------------------


class EventDispatcher(object):
    """
    Simple event dispatcher
    """

    def __init__(self, registry, logger=None):
        """
        Sets up the dispatcher

        :param registry:  The service registry
        :param logger: The logger to be used
        """
        self._registry = registry

        # Logger
        self._logger = logger or logging.getLogger("EventDispatcher")

        # Bundle listeners
        self.__bnd_listeners = []
        self.__bnd_lock = threading.Lock()

        # Service listeners (specification -> listener bean)
        self.__svc_listeners = {}
        # listener instance -> listener bean
        self.__listeners_data = {}
        self.__svc_lock = threading.Lock()

        # Framework stop listeners
        self.__fw_listeners = []
        self.__fw_lock = threading.Lock()

    def clear(self):
        """
        Clears the event dispatcher
        """
        with self.__bnd_lock:
            self.__bnd_listeners = []

        with self.__svc_lock:
            self.__svc_listeners.clear()

        with self.__fw_lock:
            self.__fw_listeners = []

    def add_bundle_listener(self, listener):
        """
        Adds a bundle listener

        :param listener: The bundle listener to register
        :return: True if the listener has been registered, False if it was
                 already known
        :raise BundleException: An invalid listener has been given
        """
        if listener is None or not hasattr(listener, "bundle_changed"):
            raise BundleException("Invalid bundle listener given")

        with self.__bnd_lock:
            if listener in self.__bnd_listeners:
                self._logger.warning(
                    "Already known bundle listener '%s'", listener
                )
                return False

            self.__bnd_listeners.append(listener)
            return True

    def add_framework_listener(self, listener):
        """
        Registers a listener that will be called back right before the
        framework stops.

        :param listener: The framework stop listener
        :return: True if the listener has been registered, False if it was
                 already known
        :raise BundleException: An invalid listener has been given
        """
        if listener is None or not hasattr(listener, "framework_stopping"):
            raise BundleException("Invalid framework listener given")

        with self.__fw_lock:
            if listener in self.__fw_listeners:
                self._logger.warning(
                    "Already known framework listener '%s'", listener
                )
                return False

            self.__fw_listeners.append(listener)
            return True

    def add_service_listener(
        self, bundle_context, listener, specification=None, ldap_filter=None
    ):
        """
        Registers a service listener

        :param bundle_context: The bundle_context of the service listener
        :param listener: The service listener
        :param specification: The specification that must provide the service
                              (optional, None to accept all services)
        :param ldap_filter: Filter that must match the service properties
                            (optional, None to accept all services)
        :return: True if the listener has been registered, False if it was
                 already known
        :raise BundleException: An invalid listener has been given
        """
        if listener is None or not hasattr(listener, "service_changed"):
            raise BundleException("Invalid service listener given")

        with self.__svc_lock:
            if listener in self.__listeners_data:
                self._logger.warning(
                    "Already known service listener '%s'", listener
                )
                return False

            try:
                ldap_filter = ldapfilter.get_ldap_filter(ldap_filter)
            except ValueError as ex:
                raise BundleException("Invalid service filter: {0}".format(ex))

            stored = ListenerInfo(
                bundle_context, listener, specification, ldap_filter
            )
            self.__listeners_data[listener] = stored
            self.__svc_listeners.setdefault(specification, []).append(stored)
            return True

    def remove_bundle_listener(self, listener):
        """
        Unregisters a bundle listener

        :param listener: The bundle listener to unregister
        :return: True if the listener has been unregistered, else False
        """
        with self.__bnd_lock:
            if listener not in self.__bnd_listeners:
                return False

            self.__bnd_listeners.remove(listener)
            return True

    def remove_framework_listener(self, listener):
        """
        Unregisters a framework stop listener

        :param listener: The framework listener to unregister
        :return: True if the listener has been unregistered, else False
        """
        with self.__fw_lock:
            try:
                self.__fw_listeners.remove(listener)
                return True
            except ValueError:
                return False

    def remove_service_listener(self, listener):
        """
        Unregisters a service listener

        :param listener: The service listener
        :return: True if the listener has been unregistered
        """
        with self.__svc_lock:
            try:
                data = self.__listeners_data.pop(listener)
                spec_listeners = self.__svc_listeners[data.specification]
                spec_listeners.remove(data)
                if not spec_listeners:
                    del self.__svc_listeners[data.specification]
                return True
            except KeyError:
                return False

    def fire_bundle_event(self, event):
        """
        Notifies bundle events listeners of a new event in the calling thread.

        :param event: The bundle event
        """
        with self.__bnd_lock:
            # Copy the list of listeners
            listeners = self.__bnd_listeners[:]

        # Call'em all
        for listener in listeners:
            try:
                listener.bundle_changed(event)
            except:
                self._logger.exception("Error calling a bundle listener")

    def fire_framework_stopping(self):
        """
        Calls all framework listeners, telling them that the framework is
        stopping
        """
        with self.__fw_lock:
            # Copy the list of listeners
            listeners = self.__fw_listeners[:]

        for listener in listeners:
            try:
                listener.framework_stopping()
            except:
                self._logger.exception(
                    "An error occurred calling one of the "
                    "framework stop listeners"
                )

    def fire_service_event(self, event):
        """
        Notifies service events listeners of a new event in the calling thread.

        :param event: The service event
        """
        # Get the service properties
        properties = event.get_service_reference().get_properties()
        svc_specs = properties[OBJECTCLASS]
        previous = None
        endmatch_event = None
        svc_modified = event.get_kind() == ServiceEvent.MODIFIED

        if svc_modified:
            # Modified service event : prepare the end match event
            previous = event.get_previous_properties()
            endmatch_event = ServiceEvent(
                ServiceEvent.MODIFIED_ENDMATCH,
                event.get_service_reference(),
                previous,
            )

        with self.__svc_lock:
            # Get the listeners for this specification
            listeners = set()
            for spec in svc_specs:
                try:
                    listeners.update(self.__svc_listeners[spec])
                except KeyError:
                    pass

            # Add those which listen to any specification
            try:
                listeners.update(self.__svc_listeners[None])
            except KeyError:
                pass

        # Filter listeners with EventListenerHooks
        listeners = self._filter_with_hooks(event, listeners)

        # Get the listeners for this specification
        for data in listeners:
            # Default event to send : the one we received
            sent_event = event

            # Test if the service properties matches the filter
            ldap_filter = data.ldap_filter
            if ldap_filter is not None and not ldap_filter.matches(properties):
                # Event doesn't match listener filter...
                if (
                    svc_modified
                    and previous is not None
                    and ldap_filter.matches(previous)
                ):
                    # ... but previous properties did match
                    sent_event = endmatch_event
                else:
                    # Didn't match before either, ignore it
                    continue

            # Call'em
            try:
                data.listener.service_changed(sent_event)
            except:
                self._logger.exception("Error calling a service listener")

    def _filter_with_hooks(self, svc_event, listeners):
        """
        Filters listeners with EventListenerHooks

        :param svc_event: ServiceEvent being triggered
        :param listeners: Listeners to filter
        :return: A list of listeners with hook references
        """
        svc_ref = svc_event.get_service_reference()
        # Get EventListenerHooks service refs from registry
        hook_refs = self._registry.find_service_references(
            SERVICE_EVENT_LISTENER_HOOK
        )
        # only do something if there are some hook_refs
        if hook_refs:
            # Associate bundle context to hooks
            ctx_listeners = {}
            for listener in listeners:
                context = listener.bundle_context
                ctx_listeners.setdefault(context, []).append(listener)

            # Convert the dictionary to a shrinkable one,
            # with shrinkable lists of listeners
            shrinkable_ctx_listeners = ShrinkableMap(
                {
                    context: ShrinkableList(value)
                    for context, value in ctx_listeners.items()
                }
            )

            for hook_ref in hook_refs:
                if not svc_ref == hook_ref:
                    # Get the bundle of the hook service
                    hook_bundle = hook_ref.get_bundle()
                    # lookup service from registry
                    hook_svc = self._registry.get_service(hook_bundle, hook_ref)
                    if hook_svc is not None:
                        # call event method of the hook service,
                        # pass in svc_event and shrinkable_ctx_listeners
                        # (which can be modified by hook)
                        try:
                            hook_svc.event(svc_event, shrinkable_ctx_listeners)
                        except:
                            self._logger.exception(
                                "Error calling EventListenerHook"
                            )
                        finally:
                            # Clean up the service
                            self._registry.unget_service(hook_bundle, hook_ref)

            # Convert the shrinkable_ctx_listeners back to a list of listeners
            # before returning
            ret_listeners = set()
            for bnd_listeners in shrinkable_ctx_listeners.values():
                ret_listeners.update(bnd_listeners)

            return ret_listeners

        # No hook ref
        return listeners


# ------------------------------------------------------------------------------


class ServiceRegistry(object):
    """
    Service registry for Pelix.

    Associates service references to instances and bundles.
    """

    def __init__(self, framework, logger=None):
        """
        Sets up the registry

        :param framework: Associated framework
        :param logger: Logger to use
        """
        # Associated framework
        self.__framework = framework

        # Logger
        self._logger = logger or logging.getLogger("ServiceRegistry")

        # Next service ID
        self.__next_service_id = 1

        # Service reference -> Service instance
        self.__svc_registry = {}  # type: Dict[ServiceReference, Any]

        # Service reference -> (Service factory, Service Registration)
        self.__svc_factories = {}  # type: Dict[Any, Tuple[Any, ServiceRegistration]]

        # Specification -> Service references[] (always sorted)
        self.__svc_specs = {}

        # Services published: Bundle -> set(Service references)
        self.__bundle_svc = {}  # type: Dict[Any, Set[ServiceReference]]

        # Services consumed: Bundle -> {Service reference -> UsageCounter}
        self.__bundle_imports = {}  # type: Dict[Any, Dict[ServiceReference, _UsageCounter]]

        # Service factories consumption: Bundle -> _FactoryCounter
        self.__factory_usage = {}  # type: Dict[Any, _FactoryCounter]

        # Locks
        self.__svc_lock = threading.RLock()

        # Pending unregistration: Service reference -> Service instance
        self.__pending_services = {}  # type: Dict[ServiceReference, Any]

    def clear(self):
        """
        Clears the registry
        """
        with self.__svc_lock:
            self.__svc_registry.clear()
            self.__svc_factories.clear()
            self.__svc_specs.clear()
            self.__bundle_svc.clear()
            self.__bundle_imports.clear()
            self.__factory_usage.clear()
            self.__pending_services.clear()

    def register(
        self, bundle, classes, properties, svc_instance, factory, prototype
    ):
        """
        Registers a service.

        :param bundle: The bundle that registers the service
        :param classes: The classes implemented by the service
        :param properties: The properties associated to the service
        :param svc_instance: The instance of the service
        :param factory: If True, the given service is a service factory
        :param prototype: If True, the given service is a prototype service
                          factory (the factory argument is considered True)
        :return: The ServiceRegistration object
        """
        with self.__svc_lock:
            # Prepare properties
            service_id = self.__next_service_id
            self.__next_service_id += 1
            properties[OBJECTCLASS] = classes
            properties[SERVICE_ID] = service_id
            properties[SERVICE_BUNDLEID] = bundle.get_bundle_id()

            # Compute service scope
            if prototype:
                properties[SERVICE_SCOPE] = SCOPE_PROTOTYPE
            elif factory:
                properties[SERVICE_SCOPE] = SCOPE_BUNDLE
            else:
                properties[SERVICE_SCOPE] = SCOPE_SINGLETON

            # Force to have a valid service ranking
            try:
                properties[SERVICE_RANKING] = int(properties[SERVICE_RANKING])
            except (KeyError, ValueError, TypeError):
                properties[SERVICE_RANKING] = 0

            # Make the service reference
            svc_ref = ServiceReference(bundle, properties)

            # Make the service registration
            svc_registration = ServiceRegistration(
                self.__framework, svc_ref, properties, self.__sort_registry
            )

            # Store service information
            if prototype or factory:
                self.__svc_factories[svc_ref] = (svc_instance, svc_registration)

            # Also store factories, as they must appear like any other service
            self.__svc_registry[svc_ref] = svc_instance

            for spec in classes:
                spec_refs = self.__svc_specs.setdefault(spec, [])
                bisect.insort_left(spec_refs, svc_ref)

            # Reverse map, to ease bundle/service association
            bundle_services = self.__bundle_svc.setdefault(bundle, set())
            bundle_services.add(svc_ref)
            return svc_registration

    def __sort_registry(self, svc_ref):
        # type: (ServiceReference) -> None
        """
        Sorts the registry, after the update of the sort key of given service
        reference

        :param svc_ref: A service reference with a modified sort key
        """
        with self.__svc_lock:
            if svc_ref not in self.__svc_registry:
                raise BundleException("Unknown service: {0}".format(svc_ref))

            # Remove current references
            for spec in svc_ref.get_property(OBJECTCLASS):
                # Use bisect to remove the reference (faster)
                spec_refs = self.__svc_specs[spec]
                idx = bisect.bisect_left(spec_refs, svc_ref)
                del spec_refs[idx]

            # ... use the new sort key
            svc_ref.update_sort_key()

            for spec in svc_ref.get_property(OBJECTCLASS):
                # ... and insert it again
                spec_refs = self.__svc_specs[spec]
                bisect.insort_left(spec_refs, svc_ref)

    def unregister(self, svc_ref):
        # type: (ServiceReference) -> Any
        """
        Unregisters a service

        :param svc_ref: A service reference
        :return: The unregistered service instance
        :raise BundleException: Unknown service reference
        """
        with self.__svc_lock:
            try:
                # Try in pending services
                return self.__pending_services.pop(svc_ref)
            except KeyError:
                # Not pending: continue
                pass

            if svc_ref not in self.__svc_registry:
                raise BundleException("Unknown service: {0}".format(svc_ref))

            # Get the owner
            bundle = svc_ref.get_bundle()

            # Get the service instance
            service = self.__svc_registry.pop(svc_ref)

            for spec in svc_ref.get_property(OBJECTCLASS):
                spec_services = self.__svc_specs[spec]
                # Use bisect to remove the reference (faster)
                idx = bisect.bisect_left(spec_services, svc_ref)
                del spec_services[idx]
                if not spec_services:
                    del self.__svc_specs[spec]

            # Remove the service factory
            if svc_ref.is_factory():
                # Call unget_service for all client bundle
                factory, svc_reg = self.__svc_factories.pop(svc_ref)
                for counter in self.__factory_usage.values():
                    counter.cleanup_service(factory, svc_reg)
            else:
                # Delete bundle association
                bundle_services = self.__bundle_svc[bundle]
                bundle_services.remove(svc_ref)
                if not bundle_services:
                    # Don't keep empty lists
                    del self.__bundle_svc[bundle]

            return service

    def hide_bundle_services(self, bundle):
        """
        Hides the services of the given bundle (removes them from lists, but
        lets them be unregistered)

        :param bundle: The bundle providing services
        :return: The references of the hidden services
        """
        with self.__svc_lock:
            try:
                svc_refs = self.__bundle_svc.pop(bundle)
            except KeyError:
                # Nothing to do
                return set()
            else:
                # Clean the registry
                specs = set()
                for svc_ref in svc_refs:
                    if svc_ref.is_factory():
                        continue

                    # Remove direct references
                    self.__pending_services[svc_ref] = self.__svc_registry.pop(
                        svc_ref
                    )
                    specs.update(svc_ref.get_property(OBJECTCLASS))

                    # Clean the specifications cache
                    for spec in svc_ref.get_property(OBJECTCLASS):
                        spec_services = self.__svc_specs[spec]
                        # Use bisect to remove the reference (faster)
                        idx = bisect.bisect_left(spec_services, svc_ref)
                        del spec_services[idx]
                        if not spec_services:
                            del self.__svc_specs[spec]

            return svc_refs

    def find_service_references(
        self, clazz=None, ldap_filter=None, only_one=False
    ):
        """
        Finds all services references matching the given filter.

        :param clazz: Class implemented by the service
        :param ldap_filter: Service filter
        :param only_one: Return the first matching service reference only
        :return: A list of found references, or None
        :raise BundleException: An error occurred looking for service
                                references
        """
        with self.__svc_lock:
            if clazz is None and ldap_filter is None:
                # Return a sorted copy of the keys list
                # Do not return None, as the whole content was required
                return sorted(self.__svc_registry.keys())

            if hasattr(clazz, "__name__"):
                # Escape the type name
                clazz = ldapfilter.escape_LDAP(clazz.__name__)
            elif is_string(clazz):
                # Escape the class name
                clazz = ldapfilter.escape_LDAP(clazz)

            if clazz is None:
                # Directly use the given filter
                refs_set = sorted(self.__svc_registry.keys())
            else:
                try:
                    # Only for references with the given specification
                    refs_set = iter(self.__svc_specs[clazz])
                except KeyError:
                    # No matching specification
                    return None

            # Parse the filter
            try:
                new_filter = ldapfilter.get_ldap_filter(ldap_filter)
            except ValueError as ex:
                raise BundleException(ex)

            if new_filter is not None:
                # Prepare a generator, as we might not need a complete
                # walk-through
                refs_set = (
                    ref
                    for ref in refs_set
                    if new_filter.matches(ref.get_properties())
                )

            if only_one:
                # Return the first element in the list/generator
                try:
                    return [next(refs_set)]
                except StopIteration:
                    # No match
                    return None

            # Get all the matching references
            return list(refs_set) or None

    def get_bundle_imported_services(self, bundle):
        """
        Returns this bundle's ServiceReference list for all services it is
        using or returns None if this bundle is not using any services.
        A bundle is considered to be using a service if its use count for that
        service is greater than zero.

        The list is valid at the time of the call to this method, however, as
        the Framework is a very dynamic environment, services can be modified
        or unregistered at any time.

        :param bundle: The bundle to look into
        :return: The references of the services used by this bundle
        """
        with self.__svc_lock:
            return sorted(self.__bundle_imports.get(bundle, []))

    def get_bundle_registered_services(self, bundle):
        # type: (Any) -> List[ServiceReference]
        """
        Retrieves the services registered by the given bundle. Returns None
        if the bundle didn't register any service.

        :param bundle: The bundle to look into
        :return: The references to the services registered by the bundle
        """
        with self.__svc_lock:
            return sorted(self.__bundle_svc.get(bundle, []))

    def get_service(self, bundle, reference):
        # type: (Any, ServiceReference) -> Any
        """
        Retrieves the service corresponding to the given reference

        :param bundle: The bundle requiring the service
        :param reference: A service reference
        :return: The requested service
        :raise BundleException: The service could not be found
        """
        with self.__svc_lock:
            if reference.is_factory():
                return self.__get_service_from_factory(bundle, reference)

            # Be sure to have the instance
            try:
                service = self.__svc_registry[reference]

                # Indicate the dependency
                imports = self.__bundle_imports.setdefault(bundle, {})
                imports.setdefault(reference, _UsageCounter()).inc()
                reference.used_by(bundle)
                return service
            except KeyError:
                # Not found
                raise BundleException(
                    "Service not found (reference: {0})".format(reference)
                )

    def __get_service_from_factory(self, bundle, reference):
        # type: (Any, ServiceReference) -> Any
        """
        Returns a service instance from a service factory or a prototype
        service factory

        :param bundle: The bundle requiring the service
        :param reference: A reference pointing to a factory
        :return: The requested service
        :raise BundleException: The service could not be found
        """
        try:
            factory, svc_reg = self.__svc_factories[reference]

            # Indicate the dependency
            imports = self.__bundle_imports.setdefault(bundle, {})
            if reference not in imports:
                # New reference usage: store a single usage
                # The Factory counter will handle the rest
                usage_counter = _UsageCounter()
                usage_counter.inc()
                imports[reference] = usage_counter
                reference.used_by(bundle)

            # Check the per-bundle usage counter
            factory_counter = self.__factory_usage.setdefault(
                bundle, _FactoryCounter(bundle)
            )
            return factory_counter.get_service(factory, svc_reg)
        except KeyError:
            # Not found
            raise BundleException(
                "Service not found (reference: {0})".format(reference)
            )

    def unget_used_services(self, bundle):
        """
        Cleans up all service usages of the given bundle.

        :param bundle: Bundle to be cleaned up
        """
        # Pop used references
        try:
            imported_refs = list(self.__bundle_imports.pop(bundle))
        except KeyError:
            # Nothing to do
            return

        for svc_ref in imported_refs:
            # Remove usage marker
            svc_ref.unused_by(bundle)

            if svc_ref.is_prototype():
                # Get factory information and clean up the service from the
                # factory counter
                factory_counter = self.__factory_usage.pop(bundle)
                factory, svc_reg = self.__svc_factories[svc_ref]
                factory_counter.cleanup_service(factory, svc_reg)
            elif svc_ref.is_factory():
                # Factory service, release it the standard way
                self.__unget_service_from_factory(bundle, svc_ref)

        # Clean up local structures
        try:
            del self.__factory_usage[bundle]
        except KeyError:
            pass

        try:
            self.__bundle_imports.pop(bundle).clear()
        except KeyError:
            pass

    def unget_service(self, bundle, reference, service=None):
        # type: (Any, ServiceReference, Any) -> bool
        """
        Removes the usage of a service by a bundle

        :param bundle: The bundle that used the service
        :param reference: A service reference
        :param service: Service instance (for Prototype Service Factories)
        :return: True if the bundle usage has been removed
        """
        with self.__svc_lock:
            if reference.is_prototype():
                return self.__unget_service_from_factory(
                    bundle, reference, service
                )
            elif reference.is_factory():
                return self.__unget_service_from_factory(bundle, reference)

            try:
                # Remove the service reference from the bundle
                imports = self.__bundle_imports[bundle]
                if not imports[reference].dec():
                    # No more reference to it
                    del imports[reference]
            except KeyError:
                # Unknown reference
                return False
            else:
                # Clean up
                if not imports:
                    del self.__bundle_imports[bundle]

                # Update the service reference
                reference.unused_by(bundle)
                return True

    def __unget_service_from_factory(self, bundle, reference, service=None):
        # type: (Any, ServiceReference, Any) -> bool
        """
        Removes the usage of a a service factory or a prototype
        service factory by a bundle

        :param bundle: The bundle that used the service
        :param reference: A service reference
        :param service: Service instance (for prototype factories)
        :return: True if the bundle usage has been removed
        """
        try:
            factory, svc_reg = self.__svc_factories[reference]
        except KeyError:
            # Unknown service reference
            return False

        # Check the per-bundle usage counter
        try:
            counter = self.__factory_usage[bundle]
        except KeyError:
            # Unknown reference to a factory
            return False
        else:
            if counter.unget_service(factory, svc_reg, service):
                try:
                    # No more dependency
                    reference.unused_by(bundle)

                    # All references have been taken away: clean up
                    if not self.__factory_usage[bundle].is_used():
                        del self.__factory_usage[bundle]

                    # Remove the service reference from the bundle
                    imports = self.__bundle_imports[bundle]
                    del imports[reference]
                except KeyError:
                    # Unknown reference
                    return False
                else:
                    # Clean up
                    if not imports:
                        del self.__bundle_imports[bundle]

        return True
