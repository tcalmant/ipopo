#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle with a failing @Instantiate constructor, followed by a healthy one
"""

from pelix.ipopo.decorators import ComponentFactory, Instantiate

GOOD_INSTANCE = "good-instance"


# Classes are loaded in alphabetical order: the failing one comes first
@ComponentFactory("a-failing-factory")
@Instantiate("failing-instance")
class AFailing:
    def __init__(self):
        raise ValueError("Failing on purpose")


@ComponentFactory("b-good-factory")
@Instantiate(GOOD_INSTANCE)
class BGood:
    pass
