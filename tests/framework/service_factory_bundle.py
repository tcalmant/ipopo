#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Simple bundle registering a service

:author: Thomas Calmant
"""

__version__ = (1, 0, 0)

SVC = "greetings"

from pelix.constants import BundleActivator


class Service:
    """
    Service per bundle
    """
    def __init__(self, bundle_id):
        self.__id = bundle_id

    def show(self):
        return self.__id


class ServiceFactoryTest:
    """
    Simple test service
    """
    def get_service(self, bundle, registration):
        """
        Provide a new service
        """
        return Service(bundle.get_bundle_id())


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

    def stop(self, context):
        """
        Bundle stopped
        """
        self.reg.unregister()
        self.reg = None
