#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Greeting service consumer

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

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Instantiate, \
    BindField, UnbindField, Validate

# Pelix constants
import pelix.constants

# Standard library
import threading

# ------------------------------------------------------------------------------

# Service specification
SERVICE_SPECIFICATION = "sample.grettings"

# ------------------------------------------------------------------------------


@ComponentFactory("hello-world-consumer")
@Requires("_services", SERVICE_SPECIFICATION, aggregate=True, optional=True)
@Instantiate("consumer")
class HelloWorldConsumer(object):
    """
    Simple greeting service consumer
    """
    def __init__(self):
        """
        Sets up members
        """
        self._services = []
        self._fw_uid = None

    def _use_service(self, service):
        """
        Calls the given greeting service

        :param service: A greeting service
        """
        service.sayHello("from {0} (Pelix framework)".format(self._fw_uid))

    @BindField('_services', if_valid=True)
    def bind_greeting(self, field, service, reference):
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

    @UnbindField('_services', if_valid=True)
    def unbind_greeting(self, field, service, reference):
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
    def validate(self, context):
        """
        Component validated

        :param context: Bundle context
        """
        # Get the framework UID
        self._fw_uid = context.get_property(pelix.constants.FRAMEWORK_UID)

        # Print it
        print("This framework has UID: {0}".format(self._fw_uid))

        # Use existing services
        for service in self._services:
            # Use the service. Use a thread to avoid locking iPOPO for too long
            threading.Thread(target=self._use_service, args=[service]).start()
