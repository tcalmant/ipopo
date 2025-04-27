#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Simple bundle with an activator (no service registered).

:author: Thomas Calmant
"""

from pelix.constants import ActivatorProto, BundleActivator, FrameworkException
from pelix.framework import BundleContext

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

started = False
stopped = False
raiser = False
fw_raiser = False
fw_raiser_stop = False


@BundleActivator
class ActivatorTest(ActivatorProto):
    """
    Test activator
    """

    def __init__(self):
        """
        Constructor
        """
        self.context = None

    def start(self, context):
        """
        Bundle started
        """
        assert isinstance(context, BundleContext)
        self.context = context

        if fw_raiser:
            raise FrameworkException("Framework Exception", fw_raiser_stop)

        if raiser:
            raise Exception("Some exception")

        global started
        started = True

    def stop(self, context):
        """
        Bundle stopped
        """
        assert isinstance(context, BundleContext)
        assert self.context is context

        if fw_raiser:
            raise FrameworkException("Framework Exception", fw_raiser_stop)

        if raiser:
            raise Exception("Some exception")

        global stopped
        stopped = True
