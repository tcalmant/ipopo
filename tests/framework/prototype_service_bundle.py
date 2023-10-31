#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Simple bundle providing a prototype service factory

:author: Thomas Calmant
"""

from pelix.constants import ActivatorProto, BundleActivator


class Instance:
    """
    Instance returned by the service factory
    """

    _id = 1

    def __init__(self, bundle):
        """
        :param bundle: Bundle associated to the service instance
        """
        self.bundle = bundle
        self.released = False
        self.id = Instance._id
        Instance._id += 1

    def __repr__(self):
        return "Instance(id={}, for={}, released={})".format(self.id, self.bundle, self.released)


class PrototypeServiceFactory:
    """
    Implementation of a prototype service factory
    """

    def __init__(self, svc_reg):
        """
        :param svc_reg: Service Registration associated to the factory
        """
        self.svc_reg = svc_reg

        # Bundle -> Service
        self.instances = {}
        self.cleanup = 0

    def get_service(self, bundle, svc_reg):
        """
        Get a new service instance

        :param bundle: Bundle requesting the service
        :param svc_reg: Service registration for this factory
        :return: An instance
        """
        if svc_reg is not self.svc_reg:
            raise ValueError("Bad ServiceRegistration")

        svc = Instance(bundle)
        self.instances.setdefault(bundle, []).append(svc)
        return svc

    def unget_service_instance(self, bundle, svc_reg, svc_instance):
        """
        Release of a single instance

        :param bundle: Bundle releasing the instance
        :param svc_reg: Service registration for this factory
        :param svc_instance: Service instance
        """
        if svc_reg is not self.svc_reg:
            raise ValueError("Bad ServiceRegistration")

        if bundle is not svc_instance.bundle:
            raise ValueError("Wrong bundle for unregistration")

        if svc_instance not in self.instances[bundle]:
            raise ValueError("Unknown instance released")

        svc_instance.released = True
        self.instances[bundle].remove(svc_instance)

    def unget_service(self, bundle, svc_reg):
        """
        Release of a usage by a bundle

        :param bundle: Bundle releasing the service
        :param svc_reg: Service registration for this factory
        """
        if svc_reg is not self.svc_reg:
            raise ValueError("Bad ServiceRegistration")

        bundle_instances = self.instances[bundle]
        if bundle_instances:
            raise ValueError("Some instances are still active: {}".format(bundle_instances))

        del self.instances[bundle]


@BundleActivator
class Activator(ActivatorProto):
    """
    Simple activator
    """

    def __init__(self):
        self._reg = None
        self._reg2 = None
        self._svc = None

    def start(self, context):
        """
        Bundle started

        :param context: Bundle context
        """
        self._svc = PrototypeServiceFactory(None)
        self._reg = context.register_service("test.prototype", self._svc, {}, prototype=True)
        self._svc.svc_reg = self._reg

        # Register the factory as a singleton, to check its variables
        self._reg2 = context.register_service("test.prototype.internal", self._svc, {})

    def stop(self, context):
        """
        Bundle started

        :param context: Bundle context
        """
        self._reg.unregister()
        self._reg2.unregister()
        self._svc = None
