#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle to check the loading order when instantiating with iPOPO

:author: Thomas Calmant
"""

from pelix.constants import BundleActivator
from pelix.framework import BundleEvent
from pelix.ipopo.constants import IPopoEvent
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Invalidate, Validate

# ------------------------------------------------------------------------------

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

BASIC_INSTANCE = "boot-component"

MAP_SPEC_TEST = "map.spec.test"
FACTORY_MAP = "ipopo.tests.map"

# ------------------------------------------------------------------------------

STATES = []


@ComponentFactory("boot-factory")
@Instantiate(BASIC_INSTANCE)
class BasicComponent(object):
    """
    Dummy instantiated component
    """

    def __init__(self):
        """
        Constructor
        """
        STATES.append(IPopoEvent.INSTANTIATED)

    @Validate
    def validate(self, context):
        """
        Validation
        """
        STATES.append(IPopoEvent.VALIDATED)

    @Invalidate
    def invalidate(self, context):
        """
        Invalidation
        """
        STATES.append(IPopoEvent.INVALIDATED)


@BundleActivator
class ActivatorTest:
    """
    Test activator
    """

    def start(self, context):
        """
        Bundle started
        """
        STATES.append(BundleEvent.STARTED)

    def stop(self, context):
        """
        Bundle stopped
        """
        STATES.append(BundleEvent.STOPPED)
