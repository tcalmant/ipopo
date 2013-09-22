#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Constants and exceptions for Pelix.

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.5.4
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
__version_info__ = (0, 5, 4)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

ACTIVATOR = "activator"
"""
Name of the module member that will be used as bundle activator.
It must be an object with the following methods:

* start(BundleContext)
* stop(BundleContext)
"""

OBJECTCLASS = "objectClass"
"""
Property containing the list of specifications (strings) provided by a service
"""

SERVICE_ID = "service.id"
"""
Property containing the ID of a service.
This ID is unique in a framework instance.
"""

SERVICE_RANKING = "service.ranking"
"""
Property that indicates the ranking of a service. It is used to sort the
results of methods like get_service_references()
"""

FRAMEWORK_UID = "framework.uid"
"""
Framework instance "unique" identifier. Used in Remote Services to identify
a framework from another.
It can be generated or be forced using the framework initialization properties.
This property is constant during the life of a framework instance.
"""

# ------------------------------------------------------------------------------

class BundleException(Exception):
    """
    The base of all framework exceptions
    """
    def __init__(self, content):
        """
        Sets up the exception
        """
        if isinstance(content, Exception):
            Exception.__init__(self, str(content))

        else:
            Exception.__init__(self, content)


class FrameworkException(Exception):
    """
    A framework exception is raised when an error can force the framework to
    stop.
    """
    def __init__(self, message, needs_stop=False):
        """
        Sets up the exception

        :param message: A description of the exception
        :param needs_stop: If True, the framework must be stopped
        """
        Exception.__init__(self, message)
        self.needs_stop = needs_stop
