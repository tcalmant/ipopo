#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Greeting service provider

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0

..

    Copyright 2023 Thomas Calmant

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

from typing import Any, Optional
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceRegistration
import pelix.remote
from pelix.constants import ActivatorProto, BundleActivator

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Service specification
SERVICE_SPECIFICATION = "sample.greetings"

# ------------------------------------------------------------------------------


class HelloWorldImpl:
    """
    Implementation of the greeting service
    """

    def sayHello(self, name: str) -> None:
        """
        Prints a greeting message

        @param name Some name
        """
        print("Python>> Hello,", name, "!")


# ------------------------------------------------------------------------------


@BundleActivator
class Activator(ActivatorProto):
    """
    The bundle activator
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self.__registration: Optional[ServiceRegistration[Any]] = None

    def start(self, context: BundleContext) -> None:
        """
        Bundle started

        @param context The bundle context
        """
        # Prepare export properties
        props = {pelix.remote.PROP_EXPORTED_INTERFACES: [SERVICE_SPECIFICATION]}

        # Register the service with the Java specification
        self.__registration = context.register_service(
            SERVICE_SPECIFICATION, HelloWorldImpl(), props
        )

    def stop(self, context: BundleContext) -> None:
        """
        Bundle stopped

        @param context The bundle context
        """
        if self.__registration is not None:
            # Unregister the service
            self.__registration.unregister()
            self.__registration = None
