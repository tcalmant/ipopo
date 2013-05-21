#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Imported end points registry 

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

# ------------------------------------------------------------------------------

# Remote Services constants
import pelix.remote

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Provides, \
    Instantiate

# Standard library
import logging

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

@ComponentFactory('pelix-remote-imports-registry-factory')
@Provides(pelix.remote.SERVICE_REGISTRY)
@Requires('_listeners', pelix.remote.SERVICE_ENDPOINT_LISTENER, True, True,
          "({0}=*)".format(pelix.remote.PROP_LISTEN_IMPORTED))
@Instantiate('pelix-remote-imports-registry')
class ImportsRegistry(object):
    """
    Registry of discovered end points. End points are identified by their UID
    """
    def __init__(self):
        """
        Sets up the component
        """
        # End point URL -> End point
        self._registry = {}

        # Listeners
        self._listeners = []


    def add(self, endpoint):
        """
        Registers an end point and notifies listeners
        
        :param endpoint: An ImportedEndpoint object
        """
        self._registry[endpoint.uid] = endpoint

        # Notify listeners
        if self._listeners:
            for listener in self._listeners[:]:
                try:
                    listener.endpoint_added(endpoint)

                except Exception as ex:
                        _logger.exception("Error calling listener: %s", ex)


    def update(self, uid, new_properties):
        """
        Updates an end point and notifies listeners
        
        :param uid: The UID of the end point
        :param new_properties: The new properties of the end point
        """
        try:
            # Update the stored end point
            stored_endpoint = self._registry[uid]

            # Replace the stored properties
            old_properties = stored_endpoint.properties.copy()
            stored_endpoint.properties = new_properties.copy()

        except KeyError:
            # Unknown end point: ignore it
            return

        else:
            # Notify listeners
            if self._listeners:
                for listener in self._listeners[:]:
                    try:
                        listener.endpoint_updated(stored_endpoint,
                                                  old_properties)

                    except Exception as ex:
                        _logger.exception("Error calling listener: %s", ex)


    def remove(self, uid):
        """
        Unregisters an end point and notifies listeners
        
        :param uid: The UID of the end point to unregister
        """
        try:
            endpoint = self._registry.pop(uid)

        except KeyError:
            # Unknown end point
            return

        else:
            # Notify listeners
            if self._listeners:
                for listener in self._listeners[:]:
                    try:
                        listener.endpoint_removed(endpoint)

                    except Exception as ex:
                        _logger.exception("Error calling listener: %s", ex)
