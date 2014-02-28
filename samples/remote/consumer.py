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
__version_info__ = (0, 0, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Instantiate, \
    BindField, UnbindField

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


    @BindField('_services')
    def bind_greeting(self, field, service, reference):
        """
        A greeting service has been bound

        @param field Name of the injected field
        @param service The injected service
        @param reference Reference of the injected service
        """
        # Trace something
        print("A new greeting service has been bound")

        # Use the service
        service.sayHello("from a Python component")


    @UnbindField('_services')
    def unbind_greeting(self, field, service, reference):
        """
        A greeting service has been bound

        @param field Name of the injected field
        @param service The injected service
        @param reference Reference of the injected service
        """
        # Trace something
        print("A greeting service is gone")

        # Avoid to use the service here, as its proxy might have already been
        # disconnected

