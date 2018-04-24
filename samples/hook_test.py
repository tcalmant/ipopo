#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Hook Test
:author: Scott Lewis
:copyright: Copyright 2017, Scott Lewis
:license: Apache License 2.0
..
    Copyright 2017 Scott Lewis
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

# Pelix remote services constants
from pelix.constants import BundleActivator

from pelix.services import SERVICE_EVENT_LISTENER_HOOK
# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 7, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

class EventListenerHookImpl(object):
    
    def __init__(self,context):
        self._context = context
        self._count = 0
        
    def event(self,service_event,listener_dict):
        print('EventListenerHookSample: service_event='+str(service_event)+",listener_dict="+str(listener_dict))
        # remove it if it's our service context and it's the 3rd time through the hook
        if self._context in listener_dict and self._count > 1:
            print('EventListenerHookSample removing our service listener so it will not be notified')
            listener_dict.pop(self._context)
        else:
            self._count += 1
        

# ------------------------------------------------------------------------------

class ServiceEventListenerImpl(object):
    def service_changed(self,service_event):
        print("MyServiceEventListener event="+str(service_event))
        
@BundleActivator
class Activator(object):
    def __init__(self):
        self.__sel = ServiceEventListenerImpl()
        self.__registration = None

    def start(self, context):
        # Add service listener
        context.add_service_listener(self.__sel)
        # register EventListenerHook as service
        self.__registration = context.register_service(
            SERVICE_EVENT_LISTENER_HOOK, EventListenerHookImpl(context), None)

    def stop(self, context):
        # Unregister the EventListenerHook
        self.__registration.unregister()
        self.__registration = None
        # Remove service listener
        context.remove_service_listener(self.__sel)
        
        