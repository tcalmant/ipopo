#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Simple bundle registering a service

:author: Thomas Calmant
"""

from pelix.constants import BundleActivator

__version__ = (1, 0, 0)

SVC = "greetings"
FACTORY = None


class Service:
    """
    Service per bundle
    """
    def __init__(self, bundle_id):
        self.__id = bundle_id

    def requester_id(self):
        return self.__id


class ServiceFactoryTest:
    """
    Simple test service
    """
    def __init__(self):
        """
        Sets up members
        """
        self.made_for = []

    def get_service(self, bundle, registration):
        """
        Provide a new service
        """
        client_id = bundle.get_bundle_id()
        self.made_for.append(client_id)
        return Service(client_id)

    def unget_service(self, bundle, registration):
        """
        Releases a service
        """
        client_id = bundle.get_bundle_id()
        self.made_for.remove(client_id)


@BundleActivator
class ActivatorService:
    """
    Test activator
    """
    def __init__(self):
        """
        Constructor
        """
        self.context = None
        self.factory = None
        self.reg = None

    def start(self, context):
        """
        Bundle started
        """
        self.context = context

        # Register the service
        self.factory = ServiceFactoryTest()
        self.reg = context.register_service(
            SVC, self.factory, {"test": True, "answer": 0},
            factory=True)

        global FACTORY
        FACTORY = self.factory

    def stop(self, _):
        """
        Bundle stopped
        """
        self.reg.unregister()
        self.reg = None

        global FACTORY
        FACTORY = None
