#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Issue 119 (late binding issue on RequiresVarFilter) use case
"""

from pelix.ipopo.decorators import ComponentFactory, Property, Provides, RequiresVarFilter


@ComponentFactory("provider-factory")
@Property("providing", "providing", None)
@Provides("required-service")
class Provider:
    def __init__(self):
        self.providing = None


@ComponentFactory("varservice-factory")
@Property("search", "search")
@RequiresVarFilter("depends", "required-service", spec_filter="(prop={search})")
class VarConsumer:
    def __init__(self):
        self.depends = None
        self.search = None
