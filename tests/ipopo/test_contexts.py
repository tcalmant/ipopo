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
import pelix.framework as pelix

# iPOPO
import pelix.ipopo.constants as constants
import pelix.ipopo.contexts as contexts

# Standard library
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

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
            props = {pelix.OBJECTCLASS: "spec", "test": invalid}
            self.assertTrue(without_filter.matches(props),
                            "Should match without filter: {0}".format(props))
            self.assertFalse(with_filter.matches(props),
                             "Shouldn't match with filter: {0}".format(props))

        for valid in ("True", True, [True]):
            props = {pelix.OBJECTCLASS: "spec", "test": valid}
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
                                "Requirement should not be equal to {0}" \
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
        self.assertNotEqual(req_1, req_2,
                        "Requirements are equal with different optional flag")

        req_2.aggregate = not req_1.aggregate
        self.assertNotEqual(req_1, req_2,
                        "Requirements are equal with different flags")

        req_2.optional = req_1.optional
        self.assertNotEqual(req_1, req_2,
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

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Set logging level
    import logging
    logging.basicConfig(level=logging.DEBUG)

    unittest.main()
