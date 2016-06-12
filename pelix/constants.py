#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Constants and exceptions for Pelix.

:author: Thomas Calmant
:copyright: Copyright 2016, Thomas Calmant
:license: Apache License 2.0
:version: 0.6.4

..

    Copyright 2016 Thomas Calmant

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
import inspect

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 6, 4)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

ACTIVATOR = "__pelix_bundle_activator__"
"""
Name of the module member that will be used as bundle activator.
It must be an object with the following methods:

* start(BundleContext)
* stop(BundleContext)
"""

ACTIVATOR_LEGACY = "activator"
"""
Deprecated: prefer ACTIVATOR

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

SERVICE_PID = 'service.pid'
"""
Property containing the Persistent ID of a service, i.e. a string identifier
that will always be the same for a (kind of) service, even after restarting
the framework.
This is used by the Configuration Admin to bind managed services and
configurations.
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


def BundleActivator(clazz):
    """
    Decorator to declare the bundle activator

    Instantiates the decorated class and stores it as a module member.

    :param clazz: The decorated bundle activator class
    :return: The class itself
    """
    # Add the activator instance to the module
    setattr(inspect.getmodule(clazz), ACTIVATOR, clazz())

    # Return the untouched class
    return clazz

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
