#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests an aggregate requirement on a specification that the component provides itself.

:author: Thomas Calmant
"""

import unittest

from pelix.framework import FrameworkFactory
from pelix.ipopo import decorators
from tests.ipopo import install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# ------------------------------------------------------------------------------

SPEC = "test.self_provider.spec"
OTHER = "test.self_provider.other"
ROUNDS = 50


@decorators.ComponentFactory("self-provider-factory")
@decorators.Provides(SPEC)
class Provider:
    pass


@decorators.ComponentFactory("self-provider-other-factory")
@decorators.Provides(OTHER)
class OtherProvider:
    pass


@decorators.ComponentFactory("self-provider-aggregator-factory")
@decorators.Provides(SPEC)
@decorators.Requires("_others", OTHER, aggregate=True, optional=True)
@decorators.Requires("_all", SPEC, aggregate=True, optional=True)
class Aggregator:
    _all: list
    _others: list


class AggregateSelfProviderTest(unittest.TestCase):
    """
    A component providing and aggregating the same specification must still get the earlier providers
    """

    def setUp(self):
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.ipopo = install_ipopo(self.framework)

    def tearDown(self):
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def test_earlier_provider_is_bound(self):
        """
        The first live binding can be the component's own service: the registry scan must still happen.
        The race depends on the service events, hence the number of rounds.
        """
        context = self.framework.get_bundle_context()
        for cls in (Provider, OtherProvider, Aggregator):
            self.ipopo.register_factory(context, cls)

        provider = self.ipopo.instantiate("self-provider-factory", "provider")
        self.ipopo.instantiate("self-provider-other-factory", "other")

        lost = []
        no_self = []
        for i in range(ROUNDS):
            aggregator = self.ipopo.instantiate("self-provider-aggregator-factory", f"aggregator{i}")
            if provider not in aggregator._all:
                lost.append(i)
            if aggregator not in aggregator._all:
                no_self.append(i)

        self.assertEqual([], lost, "aggregators that missed the provider registered before them")
        # A component's own service is not filtered out: it is injected into itself
        self.assertEqual([], no_self, "aggregators missing their own service")

    def test_self_is_bound(self):
        """
        Without any earlier provider, the component's own service is still injected into itself
        """
        context = self.framework.get_bundle_context()
        self.ipopo.register_factory(context, Aggregator)

        aggregator = self.ipopo.instantiate("self-provider-aggregator-factory", "aggregator")
        self.assertEqual([aggregator], aggregator._all)


if __name__ == "__main__":
    unittest.main()
