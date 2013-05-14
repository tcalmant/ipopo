#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
An EventAdmin-like implementation for Pelix: a publish-subscribe service

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.2
:status: Alpha

..

    This file is part of iPOPO.

    iPOPO is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    
    iPOPO is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with iPOPO. If not, see <http://www.gnu.org/licenses/>.
"""

# Module version
__version_info__ = (0, 2, 0)
__version__ = ".".join(map(str, __version_info__))

# Documentation strings format
__docformat__ = "restructuredtext en"

#-------------------------------------------------------------------------------

# Pelix
from pelix.ipopo.decorators import ComponentFactory, Provides, Property, \
    Validate, Invalidate
import pelix.framework
import pelix.ldapfilter
import pelix.services
import pelix.threadpool

# Standard library
import fnmatch
import logging

#-------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

#-------------------------------------------------------------------------------

@ComponentFactory("pelix-services-eventadmin-factory")
@Provides(pelix.services.SERVICE_EVENT_ADMIN)
@Property("_nb_threads", "pool.threads", 10)
class EventAdmin(object):
    """
    The EventAdmin implementation
    """
    def __init__(self):
        """
        Sets up the members
        """
        # The bundle context
        self._context = None

        # The framework instance UID
        self._fw_uid = None

        # Number of threads in the pool
        self._nb_threads = 10

        # Thread pool
        self._pool = None


    def _get_handlers_ids(self, topic, properties):
        """
        Retrieves the IDs of the listeners that requested to handle this event
        
        :param topic: Topic of the event
        :param properties: Associated properties
        :return: The IDs of the services to call back for this event
        """
        handlers = []

        # Get the handler service references
        handlers_refs = self._context.get_all_service_references(\
                                          pelix.services.SERVICE_EVENT_HANDLER,
                                          None)

        if handlers_refs is None:
            # No service found
            return

        # Normalize properties
        if not isinstance(properties, dict):
            properties = {}

        else:
            properties = properties.copy()

        # Add EventAdmin properties
        properties[pelix.services.EVENT_PROP_FRAMEWORK_UID] = self._fw_uid

        for svc_ref in handlers_refs:
            # Check the LDAP filter
            ldap_filter = svc_ref.get_property(pelix.services.PROP_EVENT_FILTER)
            if self.__match_filter(properties, ldap_filter):
                # Filter matches the event, test the topic
                topics = svc_ref.get_property(pelix.services.PROP_EVENT_TOPIC)
                for handled_topic in topics:
                    if fnmatch.fnmatch(topic, handled_topic):
                        # Full match, keep the service ID
                        handlers.append(svc_ref.get_property(\
                                                 pelix.framework.SERVICE_ID))
                        break

        return handlers


    def __match_filter(self, properties, ldap_filter):
        """
        Tests if the given properties match the given filter
        
        :param properties: A set of properties
        :param ldap_filter: An LDAP filter string, object or None
        :return: True if the properties match the filter
        """
        if not ldap_filter:
            # No filter
            return True

        # Normalize the filter
        ldap_filter = pelix.ldapfilter.get_ldap_filter(ldap_filter)
        return ldap_filter.matches(properties)


    def __get_service(self, service_id):
        """
        Retrieves the reference and the service associated to the given ID,
        or a (None, None) tuple if no service was found.
        
        The service must be freed with BundleContext.unget_service() after usage
        
        :param service_id: A service ID
        :return: A (reference, service) tuple or (None, None)
        """
        try:
            # Prepare the filter
            ldap_filter = "({0}={1})".format(pelix.framework.SERVICE_ID,
                                             service_id)

            # Get the reference
            ref = self._context.get_service_reference(None, ldap_filter)
            if ref is None:
                # Unknown service
                return None, None

            # Get the service
            return ref, self._context.get_service(ref)

        except pelix.framework.BundleException:
            # Service disappeared
            return None


    def __notify_handlers(self, topic, properties, handlers_ids):
        """
        Notifies the handlers of an event
        
        :param topic: Topic of the event
        :param properties: Associated properties
        :param handlers_ids: IDs of the services to notify
        """
        if self._context is None:
            # No more context
            return

        for handler_id in handlers_ids:
            # Define the "ref" variable name (and reset it on each loop)
            ref = None
            try:
                # Get the service
                ref, handler = self.__get_service(handler_id)
                if handler is not None:
                    # Use a copy of the properties each time
                    handler.handle_event(topic, properties.copy())

            except Exception as ex:
                _logger.exception("Error notifying event handler %d: %s (%s)",
                                  handler_id, ex, type(ex).__name__)

            finally:
                if ref is not None:
                    self._context.unget_service(ref)



    def send(self, topic, properties=None):
        """
        Sends synchronously the given event
        
        :param topic: Topic of event
        :param properties: Associated properties
        """
        # Get the currently available handlers
        handlers_ids = self._get_handlers_ids(topic, properties)
        if handlers_ids:
            # Notify them
            self.__notify_handlers(topic, properties, handlers_ids)


    def post(self, topic, properties=None):
        """
        Sends asynchronously the given event
        
        :param topic: Topic of event
        :param properties: Associated properties
        """
        # Get the currently available handlers
        handlers_ids = self._get_handlers_ids(topic, properties)
        if handlers_ids:
            # Enqueue the task in the thread pool
            self._pool.enqueue(self.__notify_handlers, topic, properties,
                               handlers_ids)


    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Store the bundle context
        self._context = context

        # Get the framework instance UID
        self._fw_uid = context.get_property(pelix.framework.FRAMEWORK_UID)

        # Normalize properties
        try:
            self._nb_threads = int(self._nb_threads)
            if self._nb_threads < 2:
                # Minimal value
                self._nb_threads = 2

        except ValueError:
            # Default value
            self._nb_threads = 10

        # Create the thread pool
        self._pool = pelix.threadpool.ThreadPool(self._nb_threads,
                                                 logname="eventadmin-pool")
        self._pool.start()


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        """
        # Stop the thread pool (empties its queue)
        self._pool.stop()
        self._pool = None

        # Forget the bundle context
        self._context = None
        self._fw_uid = None
