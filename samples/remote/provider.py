#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Greeting service provider

:author: Thomas Calmant
:copyright: Copyright 2014, isandlaTech
:license: Apache License 2.0

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
__version_info__ = (0, 5, 7)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix remote services constants
from pelix.constants import BundleActivator
import pelix.remote

# ------------------------------------------------------------------------------

# Service specification
SERVICE_SPECIFICATION = "sample.grettings"

# ------------------------------------------------------------------------------


class HelloWorldImpl(object):
    """
    Implementation of the greeting service
    """
    def sayHello(self, name):
        """
        Prints a greeting message

        @param name Some name
        """
        print("Python>> Hello, {0} !".format(name))

# ------------------------------------------------------------------------------


@BundleActivator
class Activator(object):
    """
    The bundle activator
    """
    def __init__(self):
        """
        Sets up members
        """
        self.__registration = None

    def start(self, context):
        """
        Bundle started

        @param context The bundle context
        """
        # Prepare export properties
        props = {pelix.remote.PROP_EXPORTED_INTERFACES:
                 [SERVICE_SPECIFICATION]}

        # Register the service with the Java specification
        self.__registration = context.register_service(SERVICE_SPECIFICATION,
                                                       HelloWorldImpl(), props)

    def stop(self, context):
        """
        Bundle stopped

        @param context The bundle context
        """
        # Unregister the service
        self.__registration.unregister()
        self.__registration = None
