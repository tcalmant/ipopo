#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
An EventAdmin-like implementation for Pelix: a publish-subscribe service

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.1
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
__version_info__ = (0, 1, 0)
__version__ = ".".join(map(str, __version_info__))

# Documentation strings format
__docformat__ = "restructuredtext en"

#-------------------------------------------------------------------------------

# Pelix
from pelix.ipopo.decorators import ComponentFactory, Provides, Requires, \
    Validate, Invalidate, Bind, Unbind, Property
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
@Requires("_handlers", pelix.services.SERVICE_EVENT_HANDLER, True, True)
@Property("_nb_threads", "pool.threads", 10)
class EventAdmin(object):
    """
    The EventAdmin implementation
    """
    def __init__(self):
        """
        Sets up the members
        """
        # Injected dependencies
        self._handlers = []

        # Number of threads in the pool
        self._nb_threads = 10

        # Service reference -> handler
        self._handlers_refs = {}

        # Thread pool
        self._pool = None


    def _get_handlers(self, topic, properties):
        """
        Retrieves the listeners that requested to handle such an event
        
        :param topic: Topic of the event
        :param properties: Associated properties
        :return: The list of listeners for this event
        """
        handlers = []

        for svc_ref in self._handlers_refs.keys():
            # Check the LDAP filter
            ldap_filter = svc_ref.get_property(pelix.services.PROP_EVENT_FILTER)
            if self.__match_filter(properties, ldap_filter):
                # Filter matches the event, test the topic
                topics = svc_ref.get_property(pelix.services.PROP_EVENT_TOPIC)
                for handled_topic in topics:
                    if fnmatch.fnmatch(topic, handled_topic):
                        # Full match
                        handlers.append(self._handlers_refs[svc_ref])
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


    def __notify_handlers(self, topic, properties, handlers):
        """
        Notifies the handlers of an event
        
        :param topic: Topic of the event
        :param properties: Associated properties
        :param handlers: A list of handlers
        """
        for handler in handlers:
            try:
                # Use a copy of the properties each time
                handler.handle_event(topic, properties.copy())

            except Exception as ex:
                _logger.error("Error notifying an event handler: %s", ex)



    def send(self, topic, properties=None):
        """
        Sends synchronously the given event
        
        :param topic: Topic of event
        :param properties: Associated properties
        """
        # Get the currently available handlers
        handlers = self._get_handlers(topic, properties)

        # Notify them
        self.__notify_handlers(topic, properties, handlers)


    def post(self, topic, properties=None):
        """
        Sends asynchronously the given event
        
        :param topic: Topic of event
        :param properties: Associated properties
        """
        # Get the currently available handlers
        handlers = self._get_handlers(topic, properties)

        # Enqueue the task in the thread pool
        self._pool.enqueue(self.__notify_handlers, topic, properties, handlers)


    @Bind
    def bind(self, service, reference):
        """
        A component dependency has been bound
        
        :param service: The bound service
        :param reference: The service reference
        """
        specifications = reference.get_property(pelix.framework.OBJECTCLASS)
        if pelix.services.SERVICE_EVENT_HANDLER in specifications:
            # An event handler is bound
            self._handlers_refs[reference] = service


    @Unbind
    def unbind(self, service, reference):
        """
        A component dependency has gone
        
        :param service: The unbound service
        :param reference: The service reference
        """
        specifications = reference.get_property(pelix.framework.OBJECTCLASS)
        if pelix.services.SERVICE_EVENT_HANDLER in specifications:
            # An event handler is gone
            del self._handlers_refs[reference]


    @Validate
    def validate(self, context):
        """
        Component validated
        """
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
