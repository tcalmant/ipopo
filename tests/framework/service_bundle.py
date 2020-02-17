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

    def echo(self, value):
        """
        Returns the given value
        """
        return value

    def modify(self, new_props):
        """
        Changes the service properties
        """
        self.registration.set_properties(new_props)


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
        register_service = asyncio.create_task(
            context.register_service(
                IEchoService, self.svc, {"test": True, "answer": 0}
                )
            )
        self.svc.registration = await register_service

        global service
        service = self.svc

    async def stop(self, context):
        """
        Bundle stopped
        """
        assert isinstance(context, BundleContext)

        if unregister:
            # To test auto-unregistration...
            unregister_service = asyncio.create_task(
                self.svc.registration.unregister()
            )
            await unregister_service
