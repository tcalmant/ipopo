#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Simple bundle registering a service

:author: Thomas Calmant
"""

import os

from pelix.constants import ActivatorProto, BundleActivator

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

SVC = "greetings"
FACTORY = None

SVC_NO_CLEAN = "factory.no.clean"


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
        Provides a new service
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


class RegistrationKeeper:
    """
    Keeps track of factory registration
    """

    def __init__(self, real_reg, given_reg):
        """
        :param real_reg: Registration returned by register_factory
        :param given_reg: Registration given to get_service()
        """
        self.real = real_reg
        self.given = given_reg


class ServiceFactoryCleanupTest:
    """
    Service not to be cleaned up by the
    """

    def __init__(self):
        self.reg = None

    def get_service(self, bundle, registration):
        """
        Provides a new service
        """
        os.environ["factory.get"] = "OK"
        return RegistrationKeeper(self.reg, registration)

    def unget_service(self, bundle, registration):
        os.environ["factory.unget"] = "OK"


@BundleActivator
class ActivatorService(ActivatorProto):
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
        self.reg = context.register_service(SVC, self.factory, {"test": True, "answer": 0}, factory=True)

        global FACTORY
        FACTORY = self.factory

        # Factory without clean up
        svc2 = ServiceFactoryCleanupTest()
        svc2.reg = context.register_service(SVC_NO_CLEAN, svc2, {}, factory=True)

    def stop(self, _):
        """
        Bundle stopped
        """
        self.reg.unregister()
        self.reg = None

        global FACTORY
        FACTORY = None
