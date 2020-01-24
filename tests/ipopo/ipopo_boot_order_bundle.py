#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
Bundle to check the loading order when instantiating with iPOPO

:author: Thomas Calmant
"""

# Pelix
from pelix.constants import BundleActivator
from pelix.framework import BundleContext, BundleEvent

# iPOPO
from pelix.ipopo.decorators import ComponentFactory, Validate, Invalidate, \
    Instantiate
from pelix.ipopo.constants import IPopoEvent

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

BASIC_INSTANCE = "boot-component"

MAP_SPEC_TEST = "map.spec.test"
FACTORY_MAP = "ipopo.tests.map"

# ------------------------------------------------------------------------------

STATES = []


@ComponentFactory("boot-factory")
@Instantiate(BASIC_INSTANCE)
class BasicComponent:
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
