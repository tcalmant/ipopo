#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Greeting service consumer

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

# Standard library
import threading
from typing import Any, List

# Pelix constants
import pelix.constants
from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference

# iPOPO decorators
from pelix.ipopo.decorators import BindField, ComponentFactory, Instantiate, Requires, UnbindField, Validate

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


@ComponentFactory("hello-world-consumer")
@Requires("_services", SERVICE_SPECIFICATION, aggregate=True, optional=True)
@Instantiate("consumer")
class HelloWorldConsumer:
    """
    Simple greeting service consumer
    """

    def __init__(self) -> None:
        """
        Sets up members
        """
        self._services: List[Any] = []
        self._fw_uid = None

    def _use_service(self, service: Any) -> None:
        """
        Calls the given greeting service

        :param service: A greeting service
        """
        service.sayHello(f"from {self._fw_uid} (Pelix framework)")

    @BindField("_services", if_valid=True)
    def bind_greeting(self, field: str, service: Any, reference: ServiceReference[Any]) -> None:
        """
        A greeting service has been bound

        :param field: Name of the injected field
        :param service: The injected service
        :param reference: Reference of the injected service
        """
        # Trace something
        print("A new greeting service has been bound")

        # Use the service. Use a thread to avoid locking iPOPO for too long
        threading.Thread(target=self._use_service, args=[service]).start()

    @UnbindField("_services", if_valid=True)
    def unbind_greeting(self, field: str, service: Any, reference: ServiceReference[Any]) -> None:
        """
        A greeting service has been bound

        :param field: Name of the injected field
        :param service: The injected service
        :param reference: Reference of the injected service
        """
        # Trace something
        print("A greeting service is gone")

        # Avoid to use the service here, as its proxy might have already been
        # disconnected

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        Component validated

        :param context: Bundle context
        """
        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Print it
        print("This framework has UID:", self._fw_uid)

        # Use existing services
        for service in self._services:
            # Use the service. Use a thread to avoid locking iPOPO for too long
            threading.Thread(target=self._use_service, args=[service]).start()
