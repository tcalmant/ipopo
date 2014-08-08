#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining multiple component factories for iPOPO tests

:author: Thomas Calmant
"""

# iPOPO
from pelix.ipopo.decorators import ComponentFactory, Provides, Validate, \
    Invalidate, Instantiate
from pelix.ipopo.constants import IPopoEvent

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

BASIC_FACTORY = "basic-component-factory"
BASIC_INSTANCE = "basic-component-copy"

# ------------------------------------------------------------------------------
# Auto-instantiated component (tests the decorator)


@ComponentFactory(BASIC_FACTORY)
@Instantiate(BASIC_INSTANCE)
@Provides("basic-component-svc")
class BasicComponent(object):
    """
    Dummy instantiated component
    """
    def __init__(self):
        """
        Constructor
        """
        self.states = []
        self.states.append(IPopoEvent.INSTANTIATED)

    @Validate
    def validate(self, context):
        """
        Validation
        """
        self.states.append(IPopoEvent.VALIDATED)

    @Invalidate
    def invalidate(self, context):
        """
        Invalidation
        """
        self.states.append(IPopoEvent.INVALIDATED)
