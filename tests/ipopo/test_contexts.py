#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the behavior of iPOPO contexts classes

:author: Thomas Calmant
"""

# Tests
from tests.ipopo import install_bundle

# Pelix
from pelix.framework import FrameworkFactory
import pelix.constants
import pelix.framework

# iPOPO
import pelix.ipopo.constants as constants
import pelix.ipopo.contexts as contexts
from pelix.ipopo.decorators import ComponentFactory, Provides, Property
from pelix.ipopo.constants import use_ipopo
from pelix.utilities import use_service

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------

FACTORY_PARENT = 'parent'
FACTORY_ALL = "child.all"
FACTORY_NO_PROVIDE = "factory.child.no_provide"
FACTORY_EXTEND_PROVIDE = "child.extend_provide"
FACTORY_REPLACE_PROVIDE = "child.replace_provide"

SPEC_PARENT = 'spec.parent'
SPEC_CHILD = 'spec.child'


@ComponentFactory(FACTORY_PARENT)
@Provides(SPEC_PARENT)
@Property('parent_prop', "prop.parent", "parent.value")
class ParentFactory(object):
    """
    Parent factory, providing a service with a property
    """
    pass


@ComponentFactory(FACTORY_ALL)
class ChildAll(ParentFactory):
    """
    Child factory, inheriting everything from its parent
    """
    pass


@ComponentFactory(FACTORY_NO_PROVIDE, excluded=Provides.HANDLER_ID)
class ChildNoProvides(ParentFactory):
    """
    Child factory, removing the provided service
    """
    pass


@ComponentFactory(FACTORY_EXTEND_PROVIDE)
@Provides(SPEC_CHILD)
class ChildExtendProvides(ParentFactory):
    """
    Child factory, replacing the provided service
    """
    pass


@ComponentFactory(FACTORY_REPLACE_PROVIDE, excluded=Provides.HANDLER_ID)
@Provides(SPEC_CHILD)
class ChildReplaceProvides(ParentFactory):
    """
    Child factory, replacing the provided service
    """
    pass

# ------------------------------------------------------------------------------


class ContextsTests(unittest.TestCase):
    """
    Tests the behavior of iPOPO contexts classes
    """
    def setUp(self):
        """
        Called before each test. Initiates a framework.
        """
        self.framework = FrameworkFactory.get_framework()
        self.framework.start()
        self.ipopo_bundle = install_bundle(self.framework, "pelix.ipopo.core")

    def tearDown(self):
        """
        Called after each test
        """
        FrameworkFactory.delete_framework(self.framework)

    def assertProvides(self, specification, provider):
        """
        Asserts that the given service is provided and is the given object
        """
        context = self.framework.get_bundle_context()
        svc_refs = context.get_all_service_references(specification)
        if not svc_refs:
            self.fail("Service {0} not registered".format(specification))

        for svc_ref in svc_refs:
            with use_service(context, svc_ref) as svc:
                if svc is provider:
                    # Found it
                    break

        else:
            self.fail("Service {0} is not provided by {1}"
                      .format(specification, provider))

    def assertNotProvides(self, specification, provider):
        """
        Asserts that the given service is not provided by the given provider
        """
        context = self.framework.get_bundle_context()
        svc_refs = context.get_all_service_references(specification)
        if svc_refs:
            for svc_ref in svc_refs:
                with use_service(context, svc_ref) as svc:
                    if svc is provider:
                        # Found it
                        self.fail("Service {0} is provided by {1}"
                                  .format(specification, provider))

    def testRequirement(self):
        """
        Tests the Requirement class type checking
        """
        Requirement = contexts.Requirement

        # Invalid specification type
        for invalid in (None, ["specification"], 1234):
            self.assertRaises(TypeError, Requirement, invalid)

        # Empty content
        self.assertRaises(ValueError, Requirement, "")

        # Invalid filter type
        for invalid in (123, ["a", "b"]):
            self.assertRaises(TypeError, Requirement, "spec",
                              spec_filter=invalid)

        # Valid values
        without_filter = Requirement("spec")
        with_filter = Requirement("spec", spec_filter="(test=True)")

        # Match test
        self.assertFalse(without_filter.matches(None),
                         "Should never match with None")
        self.assertFalse(with_filter.matches(None),
                         "Should never match with None")

        for invalid in (None, "False", False, [False]):
            props = {pelix.constants.OBJECTCLASS: "spec", "test": invalid}
            self.assertTrue(without_filter.matches(props),
                            "Should match without filter: {0}".format(props))
            self.assertFalse(with_filter.matches(props),
                             "Shouldn't match with filter: {0}".format(props))

        for valid in ("True", True, [True]):
            props = {pelix.constants.OBJECTCLASS: "spec", "test": valid}
            self.assertTrue(without_filter.matches(props),
                            "Should match without filter: {0}".format(props))
            self.assertTrue(with_filter.matches(props),
                            "Should match with filter: {0}".format(props))

    def testRequirementEquality(self):
        """
        Tests Requirement equality test
        """
        Requirement = contexts.Requirement

        req_1 = Requirement("spec_1", True, True, spec_filter="(test=True)")

        # Identity
        self.assertEqual(req_1, req_1, "Requirement is not equal to itself")

        # Different types
        for req_2 in (None, "spec_1", [], {}):
            self.assertNotEqual(req_1, req_2,
                                "Requirement should not be equal to {0}"
                                .format(req_1))

        # Copy
        req_2 = req_1.copy()
        self.assertEqual(req_1, req_1, "Requirement is not equal to its copy")

        # Different filter
        req_2.set_filter("(test=False)")
        self.assertNotEqual(req_1, req_2,
                            "Requirements are equal with different filter")
        req_2.filter = req_1.filter

        # Different flags
        req_2.optional = not req_1.optional
        self.assertNotEqual(
            req_1, req_2,
            "Requirements are equal with different optional flag")

        req_2.aggregate = not req_1.aggregate
        self.assertNotEqual(req_1, req_2,
                            "Requirements are equal with different flags")

        req_2.optional = req_1.optional
        self.assertNotEqual(
            req_1, req_2,
            "Requirements are equal with different aggregate flags")

    def testCopyFactoryContext(self):
        """
        Tests the copy of a FactoryContext bean
        """
        FactoryContext = contexts.FactoryContext
        Requirement = contexts.Requirement

        # Prepare a requirement
        req_1 = Requirement("spec_1", True, True,
                            spec_filter="(test=True)")

        # Prepare a context (content type is not tested)
        context = FactoryContext()
        context.bundle_context = 0
        context.callbacks['callback'] = 'fct'
        context.name = 'name'
        context.properties['prop'] = 42
        context.properties_fields['field_prop'] = 'prop'

        context.set_handler(constants.HANDLER_PROVIDES, ('provides', None))
        context.set_handler(constants.HANDLER_REQUIRES,
                            {'field_req': req_1})

        # Identity test
        self.assertEqual(context, context, "Identity error")

        # Copy test
        context_2 = context.copy()
        self.assertEqual(context, context_2, "Copy equality error")
        self.assertIsNot(req_1, context_2, "Requirements must be copied")

    def testHandlerInheritance(self):
        """
        Tests the inheritance of handlers
        """
        # Register factories
        context = self.framework.get_bundle_context()
        with use_ipopo(context) as ipopo:
            for factory in (ChildAll, ChildNoProvides, ChildExtendProvides,
                            ChildReplaceProvides):
                ipopo.register_factory(context, factory)

            # Check behavior of "child all"
            component = ipopo.instantiate(FACTORY_ALL, 'all', {})
            self.assertProvides(SPEC_PARENT, component)
            self.assertNotProvides(SPEC_CHILD, component)

            # No service provided
            component = ipopo.instantiate(FACTORY_NO_PROVIDE, 'no_service', {})
            self.assertNotProvides(SPEC_PARENT, component)
            self.assertNotProvides(SPEC_CHILD, component)

            # Service replaced
            component = ipopo.instantiate(FACTORY_REPLACE_PROVIDE,
                                          'replacement', {})
            self.assertNotProvides(SPEC_PARENT, component)
            self.assertProvides(SPEC_CHILD, component)

            # Service added
            component = ipopo.instantiate(FACTORY_EXTEND_PROVIDE,
                                          'addition', {})
            self.assertProvides(SPEC_PARENT, component)
            self.assertProvides(SPEC_CHILD, component)

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
