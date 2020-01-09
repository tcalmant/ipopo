#!/usr/bin/python3
# -- Content-Encoding: UTF-8 --
"""
This sample presents the use of an EventListenerHook: a service that will be
notified of each service event before its listeners and which can remove some
listeners from the notification process.

For example, this can be useful to handle an event very early and to hide it
from some listeners to avoid a double-action.

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0

..

    Copyright 2018 Scott Lewis

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
__version_info__ = (0, 8, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


class EventListenerHookImpl(object):
    """
    Implementation of an EventListener hook. It will be notified of any service
    event before standard listeners.
    """

    def __init__(self, context):
        """
        :param context: Context of the parent bundle
        """
        self._context = context
        self._count = 0

    def event(self, service_event, listener_dict):
        """
        A service has been received: this method can alter the list of
        listeners to be notified of this event (remove only).
        It can also be used as a handler for the event that will be called
        before any standard one.

        :param service_event: The ServiceEvent being triggered
        :param listener_dict: A dictionary associating a bundle context to a
                              list of listeners
        """
        print(
            "EventListenerHookImpl: service_event=",
            service_event,
            ", listener_dict=",
            listener_dict,
            sep="",
        )

        # Remove it if it's our service context, has the "to_filter" property
        # and it's the 3rd time through the hook
        svc_ref = service_event.get_service_reference()
        to_filter = svc_ref.get_property("to_filter")
        if self._context in listener_dict and to_filter:
            if self._count >= 3:
                print(
                    "EventListenerHookSample removing our service listener "
                    "so it will not be notified"
                )
                listener_dict.pop(self._context)
            else:
                self._count += 1


# ------------------------------------------------------------------------------


class ServiceEventListenerImpl(object):
    """
    A standard service event
    """

    def service_changed(self, service_event):
        """
        Notification of a service event, always executed after the hook.

        :param service_event: The service event to handle
        """
        print("ServiceEventListenerImpl event=", service_event)


@BundleActivator
class Activator(object):
    """
    Bundle activator
    """

    def __init__(self):
        self.__sel = ServiceEventListenerImpl()
        self.__registration = None

    def start(self, context):
        """
        Bundle is starting

        :param context: The context of the bundle
        """
        # Add a "standard" service listener
        context.add_service_listener(self.__sel)

        # Register a EventListenerHook as a service
        self.__registration = context.register_service(
            SERVICE_EVENT_LISTENER_HOOK,
            EventListenerHookImpl(context),
            {"sample": True},
        )

    def stop(self, context):
        """
        Bundle is stopping

        :param context: The context of the bundle
        """
        # Unregister the EventListenerHook service
        self.__registration.unregister()
        self.__registration = None

        # Remove the standard service listener
        context.remove_service_listener(self.__sel)
