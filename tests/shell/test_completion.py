#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the shell completion handlers

:author: Thomas Calmant
"""

import unittest
from io import StringIO
from typing import Any, List, Optional

import pelix.shell.beans as beans
from pelix.framework import BundleContext, Framework, FrameworkFactory
from pelix.internals.registry import ServiceReference
from pelix.ipopo.constants import use_ipopo
from pelix.ipopo.decorators import ComponentFactory, Property
from pelix.shell.completion import (
    BUNDLE,
    COMPONENT,
    DUMMY,
    FACTORY,
    FACTORY_PROPERTY,
    PROP_COMPLETER_ID,
    SERVICE,
    Completer,
    CompletionInfo,
)
from pelix.shell.completion.core import completion_hints

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

TEST_FACTORY = "completion.test.factory"
TEST_COMPONENT = "completion.test.component"

# ------------------------------------------------------------------------------


@ComponentFactory(TEST_FACTORY)
@Property("_first", "prop.first", 1)
@Property("_second", "prop.second", 2)
class CompletionTestComponent:
    """
    Component factory used to test the iPOPO completers
    """

    def __init__(self) -> None:
        self._first = 1
        self._second = 2


# ------------------------------------------------------------------------------


class CompletionTest(unittest.TestCase):
    """
    Tests the Pelix and iPOPO shell completers
    """

    framework: Framework
    context: BundleContext
    session: beans.ShellSession

    def setUp(self) -> None:
        """
        Starts a framework with the completion bundles
        """
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(FrameworkFactory.delete_framework)
        self.framework.start()
        self.context = self.framework.get_bundle_context()

        for bundle in (
            "pelix.ipopo.core",
            "pelix.shell.core",
            "pelix.shell.completion.pelix",
            "pelix.shell.completion.ipopo",
        ):
            self.context.install_bundle(bundle).start()

        # Register the test factory and start a component
        with use_ipopo(self.context) as ipopo:
            ipopo.register_factory(self.context, CompletionTestComponent)
            ipopo.instantiate(TEST_FACTORY, TEST_COMPONENT, {})

        # Prepare a shell session writing to a string
        self.output = StringIO()
        self.session = beans.ShellSession(beans.IOHandler(StringIO(), self.output))

    def _get_completer(self, completer_id: str) -> Completer:
        """
        Retrieves the completer service with the given ID
        """
        svc_ref: Optional[ServiceReference[Completer]] = self.context.get_service_reference(
            Completer, f"({PROP_COMPLETER_ID}={completer_id})"
        )
        assert svc_ref is not None, f"Completer {completer_id} not found"
        return self.context.get_service(svc_ref)

    def _complete(self, completer_id: str, current: str, arguments: Optional[List[str]] = None) -> List[str]:
        """
        Calls the completer with the given current word
        """
        config = CompletionInfo([completer_id], False)
        completer = self._get_completer(completer_id)
        return completer.complete(config, "$ ", self.session, self.context, arguments or [], current)

    def test_bundle_completer(self) -> None:
        """
        Tests the completion of bundle IDs
        """
        all_ids = {f"{bnd.get_bundle_id()} " for bnd in self.context.get_bundles()}
        matches = self._complete(BUNDLE, "")
        self.assertSetEqual(set(matches), all_ids)

        # Prefix filtering
        matches = self._complete(BUNDLE, "1")
        self.assertTrue(matches)
        for match in matches:
            self.assertTrue(match.startswith("1"))

        # No match
        self.assertListEqual(self._complete(BUNDLE, "9999"), [])

    def test_service_completer(self) -> None:
        """
        Tests the completion of service IDs
        """
        # Register a marker service and find its ID
        svc_reg = self.context.register_service("completion.test.svc", object(), {})
        svc_id = svc_reg.get_reference().get_property("service.id")

        matches = self._complete(SERVICE, "")
        self.assertIn(f"{svc_id} ", matches)

        # Prefix filtering
        matches = self._complete(SERVICE, str(svc_id))
        self.assertIn(f"{svc_id} ", matches)

        # No match
        self.assertListEqual(self._complete(SERVICE, "9999"), [])

    def test_factory_completer(self) -> None:
        """
        Tests the completion of iPOPO factory names
        """
        matches = self._complete(FACTORY, "")
        self.assertIn(f"{TEST_FACTORY} ", matches)

        matches = self._complete(FACTORY, "completion.test.")
        self.assertListEqual(matches, [f"{TEST_FACTORY} "])

        self.assertListEqual(self._complete(FACTORY, "no.such.factory"), [])

    def test_component_completer(self) -> None:
        """
        Tests the completion of iPOPO component instance names
        """
        matches = self._complete(COMPONENT, "")
        self.assertIn(f"{TEST_COMPONENT} ", matches)

        matches = self._complete(COMPONENT, "completion.test.c")
        self.assertListEqual(matches, [f"{TEST_COMPONENT} "])

        self.assertListEqual(self._complete(COMPONENT, "no.such.component"), [])

    def test_factory_property_completer(self) -> None:
        """
        Tests the completion of iPOPO factory property names
        """
        completer = self._get_completer(FACTORY_PROPERTY)

        # Factory name given by a FACTORY completer argument
        config = CompletionInfo([FACTORY, FACTORY_PROPERTY], False)
        matches = completer.complete(config, "$ ", self.session, self.context, [TEST_FACTORY, ""], "")
        self.assertCountEqual(matches, ["prop.first=", "prop.second="])

        # Prefix filtering
        matches = completer.complete(
            config, "$ ", self.session, self.context, [TEST_FACTORY, "prop.f"], "prop.f"
        )
        self.assertListEqual(matches, ["prop.first="])

        # Factory name found through a COMPONENT completer argument
        config = CompletionInfo([COMPONENT, FACTORY_PROPERTY], False)
        matches = completer.complete(config, "$ ", self.session, self.context, [TEST_COMPONENT, ""], "")
        self.assertCountEqual(matches, ["prop.first=", "prop.second="])

        # Unknown factory name
        config = CompletionInfo([FACTORY, FACTORY_PROPERTY], False)
        matches = completer.complete(config, "$ ", self.session, self.context, ["no.such.factory", ""], "")
        self.assertListEqual(matches, [])

        # No factory nor component completer in the signature
        config = CompletionInfo([DUMMY, FACTORY_PROPERTY], False)
        matches = completer.complete(config, "$ ", self.session, self.context, ["arg", ""], "")
        self.assertListEqual(matches, [])

    def test_display_hooks(self) -> None:
        """
        Tests the completion display hooks (matches printing)
        """
        try:
            import readline  # noqa: F401
        except ImportError:
            self.skipTest("readline is missing: can't test display hooks")

        from pelix.shell.completion.ipopo import ComponentFactoryCompleter, ComponentInstanceCompleter
        from pelix.shell.completion.pelix import BundleCompleter, ServiceCompleter

        # Bundle IDs display
        BundleCompleter.display_hook("$ ", self.session, self.context, ["0 ", "1 "], 2)
        output = self.output.getvalue()
        self.assertIn(self.context.get_bundle(1).get_symbolic_name(), output)

        # Service IDs display
        svc_reg = self.context.register_service("completion.test.svc", object(), {})
        svc_id = svc_reg.get_reference().get_property("service.id")
        ServiceCompleter.display_hook("$ ", self.session, self.context, [f"{svc_id} "], 4)
        self.assertIn("completion.test.svc", self.output.getvalue())

        # Factory names display
        ComponentFactoryCompleter.display_hook("$ ", self.session, self.context, [f"{TEST_FACTORY} "], 30)
        self.assertIn(TEST_FACTORY, self.output.getvalue())

        # Component instances display
        ComponentInstanceCompleter.display_hook("$ ", self.session, self.context, [f"{TEST_COMPONENT} "], 30)
        self.assertIn(TEST_COMPONENT, self.output.getvalue())


# ------------------------------------------------------------------------------


class RaisingCompleter:
    """
    A completer that always fails
    """

    def complete(self, *args: Any, **kwargs: Any) -> List[str]:
        raise RuntimeError("Completion failure")


class CompletionHintsTest(unittest.TestCase):
    """
    Tests the completion_hints() dispatching method
    """

    framework: Framework
    context: BundleContext
    session: beans.ShellSession

    def setUp(self) -> None:
        """
        Starts a framework with the Pelix completion bundle
        """
        self.framework = FrameworkFactory.get_framework()
        self.addCleanup(FrameworkFactory.delete_framework)
        self.framework.start()
        self.context = self.framework.get_bundle_context()
        self.context.install_bundle("pelix.shell.completion.pelix").start()

        self.session = beans.ShellSession(beans.IOHandler(StringIO(), StringIO()))

    def _hints(self, config: CompletionInfo, current: str, arguments: List[str]) -> List[str]:
        """
        Calls completion_hints() with common arguments
        """
        return completion_hints(config, "$ ", self.session, self.context, current, arguments)

    def test_dispatch(self) -> None:
        """
        Tests the dispatching to a registered completer
        """
        config = CompletionInfo([BUNDLE], False)

        # Empty current word: position is after existing arguments
        matches = self._hints(config, "", [])
        self.assertIn("1 ", matches)

        # Current word being completed
        matches = self._hints(config, "1", ["1"])
        self.assertListEqual(matches, ["1 "])

        # No match found
        self.assertListEqual(self._hints(config, "9999", ["9999"]), [])

    def test_dummy_completer(self) -> None:
        """
        Tests the dummy completer: no completion at all
        """
        config = CompletionInfo([DUMMY], False)
        self.assertListEqual(self._hints(config, "", []), [])

    def test_unknown_completer(self) -> None:
        """
        Tests with an unknown completer ID: no completion
        """
        config = CompletionInfo(["no.such.completer"], False)
        self.assertListEqual(self._hints(config, "", []), [])

    def test_positional_overflow(self) -> None:
        """
        Tests an argument beyond the declared completers
        """
        # Without the multiple flag: nothing to complete
        config = CompletionInfo([BUNDLE], False)
        self.assertListEqual(self._hints(config, "", ["1"]), [])

        # With the multiple flag: the last completer is reused
        config = CompletionInfo([BUNDLE], True)
        matches = self._hints(config, "", ["1"])
        self.assertIn("1 ", matches)

    def test_raising_completer(self) -> None:
        """
        Tests that a failing completer is ignored
        """
        self.context.register_service(Completer, RaisingCompleter(), {PROP_COMPLETER_ID: "test.raising"})
        config = CompletionInfo(["test.raising"], False)
        self.assertListEqual(self._hints(config, "", []), [])


# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
