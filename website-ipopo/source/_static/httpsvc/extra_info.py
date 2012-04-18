#!/usr/bin/python
#-- Content-Encoding: UTF-8 --
"""
HTTP Service demo for Pelix / iPOPO : the extra information service bundle

:author: Thomas Calmant
:license: GPLv3
"""

import os
import platform
import time

# ------------------------------------------------------------------------------

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Provides, Validate, \
    Invalidate, Property, Instantiate, Requires

# ------------------------------------------------------------------------------

# This component will be instantiated manually
@ComponentFactory(name="ExtraInfoFactory")
@Provides(specifications="demo.ExtraInfoService")
class ExtraInfoSvc(object):
    """
    The extra information service
    """

    def get_time(self):
        """
        Retrieves the current date
        """
        return time.time()


    def get_platform(self):
        """
        Retrieves the running platform
        """
        return platform.platform()


    def get_pid(self):
        """
        Retrieves the current PID
        """
        return os.getpid()
