#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Simple bundle registering a service

:author: Thomas Calmant, Angelo Cutaia
"""

import os
from pelix.constants import BundleActivator

__version__ = (1, 0, 0)

SVC = "greetings"
FACTORY = None

SVC_NO_CLEAN = "factory.no.clean"


class Service:
    """
    Service per bundle
    """
    def __init__(self, bundle_id):
        self.__id = bundle_id

    async def requester_id(self):
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

    async def get_service(self, bundle, registration):
        """
        Provides a new service
        """
        client_id = bundle.get_bundle_id()
        self.made_for.append(client_id)
        return Service(client_id)

    async def unget_service(self, bundle, registration):
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

    async def get_service(self, bundle, registration):
        """
        Provides a new service
        """
        os.environ['factory.get'] = "OK"
        return RegistrationKeeper(self.reg, registration)

    async def unget_service(self, bundle, registration):
        os.environ['factory.unget'] = "OK"


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

    async def start(self, context):
        """
        Bundle started
        """
        self.context = context

        # Register the service
        self.factory = ServiceFactoryTest()
        self.reg = await context.register_service(
            SVC, self.factory, {"test": True, "answer": 0},
            factory=True)

        global FACTORY
        FACTORY = self.factory

        # Factory without clean up
        svc2 = ServiceFactoryCleanupTest()
        svc2.reg = await context.register_service(
            SVC_NO_CLEAN, svc2, {}, factory=True)

    async def stop(self, _):
        """
        Bundle stopped
        """
        await self.reg.unregister()
        self.reg = None

        global FACTORY
        FACTORY = None
