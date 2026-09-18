#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the iPOPO requirements on several specifications, either all of them
(default) or any of them (``match_any=True``)

:author: Thomas Calmant
"""

import unittest
from collections.abc import Callable
from typing import Any

from pelix.constants import OBJECTCLASS, SERVICE_RANKING
from pelix.framework import BundleContext, Framework, FrameworkFactory
from pelix.internals.registry import ServiceRegistration
from pelix.ipopo.constants import IPopoService
from pelix.ipopo.contexts import Requirement
from pelix.ipopo.decorators import (
    ComponentFactory,
    Property,
    Requires,
    RequiresBest,
    RequiresBroadcast,
    RequiresMap,
    RequiresVarFilter,
    Temporal,
)
from pelix.ipopo.instance import StoredInstance
from tests.ipopo import install_ipopo

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 3)
__version__ = ".".join(str(x) for x in __version_info__)

SPEC_A = "multi.spec.a"
SPEC_B = "multi.spec.b"
SPECS = [SPEC_A, SPEC_B]

# ------------------------------------------------------------------------------


class RequirementMultiSpecTest(unittest.TestCase):
    """
    Tests the Requirement bean with several specifications
    """

    @staticmethod
    def _props(*specs: str, **props: Any) -> dict[str, Any]:
        """
        Prepares service properties
        """
        props[OBJECTCLASS] = list(specs)
        return props

    def test_specifications(self) -> None:
        """
        Tests the normalization of specifications
        """
        req = Requirement("spec")
        self.assertEqual(req.specifications, ["spec"])
        self.assertEqual(req.specification, "spec")
        self.assertFalse(req.match_any)

        # Duplicates are ignored, the first specification is the main one
        req = Requirement(("spec.b", "spec.a", "spec.b"), match_any=True)
        self.assertEqual(req.specifications, ["spec.b", "spec.a"])
        self.assertEqual(req.specification, "spec.b")
        self.assertTrue(req.match_any)

        # "Any" has no meaning with a single specification
        for specs in ("spec", ["spec"], ["spec", "spec"]):
            req = Requirement(specs, match_any=True)
            self.assertFalse(req.match_any)
            self.assertEqual(req, Requirement("spec"))

    def test_equality_copy(self) -> None:
        """
        Tests the equality and the copy of multi-specifications requirements
        """
        req_all = Requirement(SPECS, spec_filter="(test=True)")
        req_any = Requirement(SPECS, spec_filter="(test=True)", match_any=True)

        self.assertNotEqual(req_all, req_any)
        self.assertNotEqual(req_all, Requirement(SPEC_A, spec_filter="(test=True)"))
        self.assertNotEqual(req_all, Requirement([SPEC_A, "other"], spec_filter="(test=True)"))

        for req in (req_all, req_any):
            copy = req.copy()
            self.assertIsNot(copy, req)
            self.assertEqual(copy, req)
            self.assertEqual(copy.specifications, req.specifications)
            self.assertIsNot(copy.specifications, req.specifications)
            self.assertEqual(copy.match_any, req.match_any)
            self.assertEqual(copy.original_filter, req.original_filter)
            self.assertEqual(copy.full_filter, req.full_filter)
            self.assertEqual(copy.lookup_filter, req.lookup_filter)

    def test_single_lookup(self) -> None:
        """
        A single specification requirement must be looked up as before
        """
        req = Requirement(SPEC_A)
        self.assertEqual(req.lookup_specification, SPEC_A)
        self.assertIsNone(req.lookup_filter)

        req.set_filter("(test=True)")
        self.assertEqual(req.lookup_specification, SPEC_A)
        self.assertIs(req.lookup_filter, req.filter)

    def test_all_filters(self) -> None:
        """
        Tests the filters of a requirement on all specifications
        """
        req = Requirement(SPECS, spec_filter="(test=True)")
        self.assertEqual(req.lookup_specification, SPEC_A)
        lookup_filter = req.lookup_filter
        assert lookup_filter is not None

        for props, expected in (
            (self._props(SPEC_A, test=True), False),
            (self._props(SPEC_B, test=True), False),
            (self._props(SPEC_A, SPEC_B, test=True), True),
            (self._props(SPEC_B, "other", SPEC_A, test=True), True),
            (self._props(SPEC_A, SPEC_B, test=False), False),
        ):
            self.assertEqual(req.matches(props), expected, props)
            # The lookup filter is combined with the lookup specification
            if SPEC_A in props[OBJECTCLASS]:
                self.assertEqual(lookup_filter.matches(props), expected, props)

        self.assertFalse(req.matches(None))

    def test_any_filters(self) -> None:
        """
        Tests the filters of a requirement on any specification
        """
        req = Requirement(SPECS, spec_filter="(test=True)", match_any=True)
        self.assertIsNone(req.lookup_specification)
        lookup_filter = req.lookup_filter
        assert lookup_filter is not None

        for props, expected in (
            (self._props(SPEC_A, test=True), True),
            (self._props(SPEC_B, test=True), True),
            (self._props(SPEC_A, SPEC_B, test=True), True),
            (self._props("other", test=True), False),
            (self._props(SPEC_A, test=False), False),
        ):
            self.assertEqual(req.matches(props), expected, props)
            self.assertEqual(lookup_filter.matches(props), expected, props)

        # Without properties filter
        req = Requirement(SPECS, match_any=True)
        lookup_filter = req.lookup_filter
        assert lookup_filter is not None
        self.assertTrue(lookup_filter.matches(self._props(SPEC_B)))
        self.assertFalse(lookup_filter.matches(self._props("other")))

    def test_escaping(self) -> None:
        """
        Specifications are values, not LDAP patterns
        """
        # Those characters would break the filter if they weren't escaped
        for specs in (["spec(a)"], ["spec(a)", "b|c=d"]):
            for match_any in (False, True):
                req = Requirement(specs, match_any=match_any)
                self.assertTrue(req.matches(self._props(*specs)))
                self.assertFalse(req.matches(self._props("spec", "b|c")))

    def test_filter_update(self) -> None:
        """
        The derived filters must follow the properties filter
        """
        for match_any in (False, True):
            req = Requirement(SPECS, match_any=match_any)
            props = self._props(SPEC_A, SPEC_B, test=False)
            self.assertTrue(req.matches(props))

            req.set_filter("(test=True)")
            self.assertFalse(req.matches(props))
            assert req.lookup_filter is not None
            self.assertFalse(req.lookup_filter.matches(props))

            # Direct assignment of the parsed filter
            req.filter = None
            self.assertTrue(req.matches(props))
            self.assertEqual(req.original_filter, "(test=True)")


# ------------------------------------------------------------------------------


class Service:
    """
    A dummy service, recording its calls
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def call(self) -> str:
        self.calls += 1
        return self.name

    def __repr__(self) -> str:
        return f"Service({self.name})"


def make_factory(name: str, *decorators: Callable[[type], type]) -> type:
    """
    Prepares a component factory with the given decorators
    """

    class Consumer:
        _svc: Any = None

    factory: type = Consumer
    for decorator in reversed(decorators):
        factory = decorator(factory)

    return ComponentFactory(name)(factory)


class RequiresMultiSpecTest(unittest.TestCase):
    """
    Tests the requirement handlers with several specifications
    """

    framework: Framework
    context: BundleContext
    ipopo: IPopoService

    def setUp(self) -> None:
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(self.framework.delete, True)
        self.framework.start()
        self.context = self.framework.get_bundle_context()
        self.ipopo = install_ipopo(self.framework)
        self.__counter = 0
        self.__names: dict[int, str] = {}

    def tearDown(self) -> None:
        self.framework.stop()
        FrameworkFactory.delete_framework()

    def instantiate(
        self, *decorators: Callable[[type], type], properties: dict[str, Any] | None = None
    ) -> Any:
        """
        Registers a factory with the given decorators and instantiates it
        """
        self.__counter += 1
        name = f"multi-spec-{self.__counter}"
        self.ipopo.register_factory(self.context, make_factory(f"{name}-factory", *decorators))
        instance = self.ipopo.instantiate(f"{name}-factory", name, properties or {})
        self.__names[id(instance)] = name
        return instance

    def name(self, consumer: Any) -> str:
        """
        Returns the name of the given component instance
        """
        return self.__names[id(consumer)]

    def register(self, name: str, *specs: str, **props: Any) -> tuple[Service, ServiceRegistration[Any]]:
        """
        Registers a service with the given specifications
        """
        svc = Service(name)
        props["name"] = name
        return svc, self.context.register_service(list(specs), svc, props)

    def assertState(self, consumer: Any, valid: bool) -> None:
        """
        Checks the state of the given component
        """
        name = self.name(consumer)
        state = self.ipopo.get_instance_details(name)["state"]
        self.assertEqual(state == StoredInstance.VALID, valid, f"Bad state for {name}: {state}")

    def bindings(self, consumer: Any) -> list[str]:
        """
        Returns the names of the services bound to the given component
        """
        name = self.name(consumer)
        refs = self.ipopo.get_instance_details(name)["dependencies"]["_svc"]["bindings"]
        return sorted(ref.get_property("name") for ref in refs)

    def test_simple(self) -> None:
        """
        Tests @Requires on a single service
        """
        for match_any in (False, True):
            with self.subTest(match_any=match_any):
                consumer = self.instantiate(Requires("_svc", SPECS, match_any=match_any))
                self.assertState(consumer, False)

                svc_a, reg_a = self.register("a", SPEC_A)
                svc_b, reg_b = self.register("b", SPEC_B)
                if match_any:
                    self.assertState(consumer, True)
                    self.assertIs(consumer._svc, svc_a)
                else:
                    self.assertState(consumer, False)
                    self.assertIsNone(consumer._svc)

                svc_ab, reg_ab = self.register("ab", SPEC_A, SPEC_B)
                self.assertState(consumer, True)
                self.assertIs(consumer._svc, svc_a if match_any else svc_ab)

                # The remaining services only provide a single specification
                reg_ab.unregister()
                if match_any:
                    self.assertIs(consumer._svc, svc_a)
                    reg_a.unregister()
                    self.assertState(consumer, True)
                    self.assertIs(consumer._svc, svc_b)
                    reg_b.unregister()
                else:
                    reg_a.unregister()
                    reg_b.unregister()

                self.assertState(consumer, False)
                self.assertIsNone(consumer._svc)

    def test_immediate_rebind(self) -> None:
        """
        Tests the look up of a replacement service
        """
        for match_any in (False, True):
            with self.subTest(match_any=match_any):
                consumer = self.instantiate(
                    Requires("_svc", SPECS, immediate_rebind=True, match_any=match_any)
                )
                svc_ab, reg_ab = self.register("ab", SPEC_A, SPEC_B)
                # Registered after the bound service, but before its
                # replacement: would be chosen if specifications were ignored
                svc_a, reg_a = self.register("a", SPEC_A)
                svc_ab2, reg_ab2 = self.register("ab2", SPEC_B, SPEC_A)
                self.assertIs(consumer._svc, svc_ab)

                reg_ab.unregister()
                self.assertState(consumer, True)
                self.assertIs(consumer._svc, svc_a if match_any else svc_ab2)

                reg_a.unregister()
                reg_ab2.unregister()
                self.assertState(consumer, False)

    def test_optional_aggregate(self) -> None:
        """
        Tests optional and aggregate requirements
        """
        for match_any in (False, True):
            with self.subTest(match_any=match_any):
                optional = self.instantiate(Requires("_svc", SPECS, optional=True, match_any=match_any))
                aggregate = self.instantiate(Requires("_svc", SPECS, aggregate=True, match_any=match_any))
                self.assertState(optional, True)
                self.assertState(aggregate, False)

                svc_a, reg_a = self.register("a", SPEC_A)
                _, reg_b = self.register("b", SPEC_B)
                _, reg_other = self.register("other", "other")
                if match_any:
                    self.assertIs(optional._svc, svc_a)
                    self.assertEqual(self.bindings(aggregate), ["a", "b"])
                else:
                    self.assertIsNone(optional._svc)
                    self.assertState(aggregate, False)

                svc_ab, reg_ab = self.register("ab", SPEC_A, SPEC_B)
                if match_any:
                    self.assertIs(optional._svc, svc_a)
                    self.assertEqual(self.bindings(aggregate), ["a", "ab", "b"])
                else:
                    self.assertIs(optional._svc, svc_ab)
                    self.assertEqual(self.bindings(aggregate), ["ab"])
                    self.assertEqual(aggregate._svc, [svc_ab])

                reg_ab.unregister()
                if match_any:
                    self.assertEqual(self.bindings(aggregate), ["a", "b"])
                else:
                    self.assertIsNone(optional._svc)
                    self.assertState(aggregate, False)

                for reg in (reg_a, reg_b, reg_other):
                    reg.unregister()
                self.assertState(optional, True)
                self.assertIsNone(optional._svc)
                self.assertState(aggregate, False)

    def test_properties_filter(self) -> None:
        """
        Tests the combination of specifications and properties filter
        """
        for match_any in (False, True):
            with self.subTest(match_any=match_any):
                consumer = self.instantiate(
                    Requires("_svc", SPECS, aggregate=True, spec_filter="(ok=True)", match_any=match_any)
                )
                _, reg_a = self.register("a", SPEC_A, ok=False)
                _, reg_ab = self.register("ab", SPEC_A, SPEC_B, ok=False)
                self.assertState(consumer, False)

                # Services modified to match the filter
                reg_a.set_properties({"ok": True})
                self.assertEqual(self.bindings(consumer), ["a"] if match_any else [])
                reg_ab.set_properties({"ok": True})
                self.assertEqual(self.bindings(consumer), ["a", "ab"] if match_any else ["ab"])

                # Services modified to not match anymore
                reg_ab.set_properties({"ok": False})
                self.assertEqual(self.bindings(consumer), ["a"] if match_any else [])

                reg_a.unregister()
                reg_ab.unregister()
                self.assertState(consumer, False)

    def test_requires_best(self) -> None:
        """
        Tests @RequiresBest
        """
        for match_any in (False, True):
            with self.subTest(match_any=match_any):
                consumer = self.instantiate(RequiresBest("_svc", SPECS, match_any=match_any))
                svc_a, reg_a = self.register("a", SPEC_A, **{SERVICE_RANKING: 100})
                self.assertIs(consumer._svc, svc_a if match_any else None)

                svc_ab, reg_ab = self.register("ab", SPEC_A, SPEC_B, **{SERVICE_RANKING: 10})
                svc_ab2, reg_ab2 = self.register("ab2", SPEC_A, SPEC_B, **{SERVICE_RANKING: 20})
                self.assertIs(consumer._svc, svc_a if match_any else svc_ab2)

                reg_ab.set_properties({SERVICE_RANKING: 200})
                self.assertIs(consumer._svc, svc_ab)

                # Replacement must be looked for among matching services
                reg_ab.unregister()
                self.assertIs(consumer._svc, svc_a if match_any else svc_ab2)

                reg_ab2.unregister()
                if match_any:
                    self.assertIs(consumer._svc, svc_a)
                    reg_a.unregister()
                else:
                    reg_a.unregister()
                self.assertState(consumer, False)

    def test_requires_map(self) -> None:
        """
        Tests @RequiresMap
        """
        for match_any in (False, True):
            with self.subTest(match_any=match_any):
                consumer = self.instantiate(
                    RequiresMap("_svc", SPECS, "name", optional=True, match_any=match_any)
                )
                svc_a, reg_a = self.register("a", SPEC_A)
                svc_b, reg_b = self.register("b", SPEC_B)
                svc_ab, reg_ab = self.register("ab", SPEC_A, SPEC_B)
                if match_any:
                    self.assertEqual(consumer._svc, {"a": svc_a, "b": svc_b, "ab": svc_ab})
                else:
                    self.assertEqual(consumer._svc, {"ab": svc_ab})

                reg_ab.unregister()
                self.assertEqual(consumer._svc, {"a": svc_a, "b": svc_b} if match_any else {})

                reg_a.unregister()
                reg_b.unregister()
                self.assertEqual(consumer._svc, {})

                # Already registered services are injected at instantiation
                svc_a, reg_a = self.register("a", SPEC_A)
                svc_ab, reg_ab = self.register("ab", SPEC_A, SPEC_B)
                late = self.instantiate(RequiresMap("_svc", SPECS, "name", match_any=match_any))
                if match_any:
                    self.assertEqual(late._svc, {"a": svc_a, "ab": svc_ab})
                else:
                    self.assertEqual(late._svc, {"ab": svc_ab})
                reg_a.unregister()
                reg_ab.unregister()

    def test_requires_broadcast(self) -> None:
        """
        Tests @RequiresBroadcast
        """
        for match_any in (False, True):
            with self.subTest(match_any=match_any):
                consumer = self.instantiate(RequiresBroadcast("_svc", SPECS, match_any=match_any))
                svc_a, reg_a = self.register("a", SPEC_A)
                svc_ab, reg_ab = self.register("ab", SPEC_A, SPEC_B)

                self.assertTrue(consumer._svc.call())
                self.assertEqual(svc_a.calls, 1 if match_any else 0)
                self.assertEqual(svc_ab.calls, 1)

                reg_ab.unregister()
                self.assertEqual(consumer._svc.call(), match_any)
                self.assertEqual(svc_a.calls, 2 if match_any else 0)

                reg_a.unregister()
                self.assertFalse(consumer._svc.call())

    def test_temporal(self) -> None:
        """
        Tests @Temporal
        """
        for match_any in (False, True):
            with self.subTest(match_any=match_any):
                consumer = self.instantiate(Temporal("_svc", SPECS, timeout=5, match_any=match_any))
                _, reg_a = self.register("a", SPEC_A)
                self.assertState(consumer, match_any)

                _, reg_ab = self.register("ab", SPEC_A, SPEC_B)
                self.assertState(consumer, True)
                self.assertEqual(consumer._svc.call(), "a" if match_any else "ab")

                if not match_any:
                    # The grace period starts: the service with a single
                    # specification must not be used as a replacement
                    reg_ab.unregister()
                    self.assertState(consumer, True)
                    self.assertEqual(self.bindings(consumer), [])

                    _, reg_ab = self.register("ab2", SPEC_B, SPEC_A)
                    self.assertEqual(consumer._svc.call(), "ab2")
                else:
                    # Replaced by the next matching service
                    reg_a.unregister()
                    self.assertEqual(consumer._svc.call(), "ab")
                    _, reg_a = self.register("a", SPEC_A)

                self.ipopo.kill(self.name(consumer))
                reg_a.unregister()
                reg_ab.unregister()

    def test_var_filter(self) -> None:
        """
        Tests @RequiresVarFilter
        """
        for match_any in (False, True):
            with self.subTest(match_any=match_any):
                consumer = self.instantiate(
                    Property("_lang", "lang", "fr"),
                    RequiresVarFilter("_svc", SPECS, spec_filter="(lang={lang})", match_any=match_any),
                )
                svc_a_fr, reg_a_fr = self.register("a_fr", SPEC_A, lang="fr")
                svc_ab_fr, reg_ab_fr = self.register("ab_fr", SPEC_A, SPEC_B, lang="fr")
                svc_b_en, reg_b_en = self.register("b_en", SPEC_B, lang="en")
                self.assertIs(consumer._svc, svc_a_fr if match_any else svc_ab_fr)

                # Change the filter: only a service with a single specification
                consumer._lang = "en"
                if match_any:
                    self.assertIs(consumer._svc, svc_b_en)
                else:
                    self.assertState(consumer, False)
                    self.assertIsNone(consumer._svc)

                svc_ab_en, reg_ab_en = self.register("ab_en", SPEC_B, SPEC_A, lang="en")
                self.assertIs(consumer._svc, svc_b_en if match_any else svc_ab_en)

                # Back to the first filter
                consumer._lang = "fr"
                self.assertIs(consumer._svc, svc_a_fr if match_any else svc_ab_fr)

                for reg in (reg_a_fr, reg_ab_fr, reg_b_en, reg_ab_en):
                    reg.unregister()
                self.assertState(consumer, False)

    def test_details(self) -> None:
        """
        Tests the description of multi-specifications requirements
        """
        for match_any in (False, True):
            with self.subTest(match_any=match_any):
                consumer = self.instantiate(Requires("_svc", SPECS, optional=True, match_any=match_any))
                name = self.name(consumer)
                details = self.ipopo.get_instance_details(name)["dependencies"]["_svc"]
                self.assertEqual(details["specification"], SPEC_A)
                self.assertEqual(details["specifications"], SPECS)
                self.assertEqual(details["match_any"], match_any)

                factory = self.ipopo.get_instance_details(name)["factory"]
                (requirement,) = self.ipopo.get_factory_details(factory)["requirements"]
                self.assertEqual(requirement["specification"], SPEC_A)
                self.assertEqual(requirement["specifications"], SPECS)
                self.assertEqual(requirement["match_any"], match_any)


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging

    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
