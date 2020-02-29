#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Simple bundle registering a service

:author: Thomas Calmant, Angelo Cutaia
"""
import asyncio
from pelix.constants import BundleActivator
from pelix.framework import BundleContext
from tests.interfaces import IEchoService

__version__ = (1, 0, 0)

registered = False
unregistered = False
service = None
unregister = True


class ServiceTest(IEchoService):
    """
    Simple test service
    """
    def __init__(self):
        """
        Constructor
        """
        IEchoService.__init__(self)
        self.toto = 0
        self.registration = None

    async def echo(self, value):
        """
        Returns the given value
        """
        return value

    async def modify(self, new_props):
        """
        Changes the service properties
        """
        await self.registration.set_properties(new_props)


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
        self.svc = None

    async def start(self, context):
        """
        Bundle started
        """
        assert isinstance(context, BundleContext)
        self.context = context

        # Register the service
        self.svc = ServiceTest()
        self.svc.registration = await context.register_service(
            IEchoService, self.svc, {"test": True, "answer": 0}
        )

        global service
        service = self.svc

    async def stop(self, context):
        """
        Bundle stopped
        """
        assert isinstance(context, BundleContext)

        if unregister:
            # To test auto-unregistration...
            await self.svc.registration.unregister()
