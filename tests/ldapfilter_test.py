#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
LDAP filter parser tests

:author: Thomas Calmant
"""

from pelix.ldapfilter import get_ldap_filter
import pelix.ldapfilter

try:
    import unittest2 as unittest

except ImportError:
    import unittest
    import tests
    tests.inject_unittest_methods()

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

def applyTest(self, filters, key):
    """
    Applies a list of tests according to the given dictionary

    Dictionary format : filter -> ([True, results], [False, results])

    @param filters: A filters test dictionary
    @param key: The key to use in the property dictionary
    """
    props = {}

    for filter_str, tests in filters.items():
        ldap_filter = get_ldap_filter(filter_str)
        self.assertIsNotNone(ldap_filter, "%s is a valid filter" \
                             % filter_str)

        for good in tests[0]:
            props[key] = good
            self.assertTrue(ldap_filter.matches(props), \
                    "Filter '%s' should match %s" % (ldap_filter, props))

        for bad in tests[1]:
            props[key] = bad
            self.assertFalse(ldap_filter.matches(props), \
                    "Filter '%s' should not match %s" \
                    % (ldap_filter, props))

# ------------------------------------------------------------------------------

class LDAPUtilitiesTest(unittest.TestCase):
    """
    Tests for LDAP utility methods
    """

    def testComparator2str(self):
        """
        Tests comparator2str()
        """
        for comparator in ('=', '<', '<=', '>', '>=', '=', '~='):
            # Parse a criteria with that comparator
            ldap_filter = get_ldap_filter("(a%s1)" % comparator)

            # Get the string version of the parsed comparator
            str_comparator = pelix.ldapfilter.comparator2str(\
                                                        ldap_filter.comparator)

            self.assertEquals(str_comparator, comparator,
                              "Bad string for comparator '%s' : '%s'"
                              % (comparator, str_comparator))

        # Invalid comparators
        for comparator in (None, str, str(), int()):
            str_comparator = pelix.ldapfilter.comparator2str(comparator)
            self.assertEquals(str_comparator, "??",
                          "Bad string for comparator '%s' : '%s'"
                          % (comparator, str_comparator))


    def testOperator2str(self):
        """
        Tests operator2str()
        """
        operators = {pelix.ldapfilter.AND: "&",
                     pelix.ldapfilter.OR: "|",
                     pelix.ldapfilter.NOT: "!"}

        for operator, str_operator in operators.items():
            conv_operator = pelix.ldapfilter.operator2str(operator)
            self.assertEquals(str_operator, conv_operator,
                              "Invalid operator conversion '%s' : '%s'"
                              % (str_operator, conv_operator))

        for operator in (None, str, int, str(), "AND", "OR", "NOT", 42):
            conv_operator = pelix.ldapfilter.operator2str(operator)
            self.assertEquals("<unknown>", conv_operator,
                              "Invalid operator conversion '%s' : '%s'"
                              % (str_operator, conv_operator))


    def testEscapeLDAP(self):
        """
        Tests escape_LDAP() and unescape_LDAP()

        Tested values from :
        https://www.owasp.org/index.php/Preventing_LDAP_Injection_in_Java
        """
        # Tested values : normal -> escaped
        tested_values = {
                         # None -> None:
                         None: None,

                         # No escape needed
                         "Helloé": "Helloé",

                         # Sharp escape
                         "# Helloé": "\\# Helloé",

                         # Space escapes
                         " Helloé": "\\ Helloé",
                         "Helloé ": "Helloé\\ ",
                         "Hello é": "Hello é",

                         # Only spaces
                         "   ": "\\  \\ ",

                         # Complex
                         ' Hello\\ + , "World" ; ':
                                    '\\ Hello\\\\ \\+ \\, \\"World\\" \\;\\ ',
                         }

        for normal, escaped in tested_values.items():
            # Escape
            ldap_escape = pelix.ldapfilter.escape_LDAP(normal)
            self.assertEquals(escaped, ldap_escape,
                              "Invalid escape '%s' should be '%s'"
                              % (ldap_escape, escaped))

            # Un-escape
            ldap_unescape = pelix.ldapfilter.unescape_LDAP(ldap_escape)
            self.assertEquals(escaped, ldap_escape,
                              "Invalid un-escape '%s' should be '%s'"
                              % (ldap_unescape, normal))


# ------------------------------------------------------------------------------

class LDAPCriteriaTest(unittest.TestCase):
    """
    Tests for the LDAP criteria behavior
    """

    def testEmptyCriteria(self):
        """
        Empty filter test
        """
        self.assertIsNone(get_ldap_filter(None), "None filter must return None")
        self.assertIsNone(get_ldap_filter(""), "Empty filter must return None")
        self.assertIsNone(get_ldap_filter(" "), \
                          "Trimmed filter must return None")


    def testSimpleCriteria(self):
        """
        Simple boolean filter test
        """
        props = {}

        ldap_filter = get_ldap_filter("(valid=True)")
        self.assertIsNotNone(ldap_filter, "Filter should not be None")

        # Test with a single property
        props["valid"] = True
        self.assertTrue(ldap_filter.matches(props), \
                        "Filter '%s' should match %s" % (ldap_filter, props))

        props["valid"] = False
        self.assertFalse(ldap_filter.matches(props), \
                        "Filter '%s' should not match %s" \
                        % (ldap_filter, props))

        # Test the ignorance of other properties
        props["valid2"] = True
        self.assertFalse(ldap_filter.matches(props), \
                        "Filter '%s' should not match %s" \
                        % (ldap_filter, props))

        props["valid"] = "True"
        self.assertTrue(ldap_filter.matches(props), \
                        "Filter '%s' should match %s" % (ldap_filter, props))


    def testPresenceCriteria(self):
        """
        Test the presence filter
        """
        props = {}

        ldap_filter = get_ldap_filter("(valid=*)")
        self.assertIsNotNone(ldap_filter, "Filter should not be None")

        # Missing value
        self.assertFalse(ldap_filter.matches(props), \
                        "Filter '%s' should not match %s" \
                        % (ldap_filter, props))

        # Still missing
        props["valid2"] = True
        self.assertFalse(ldap_filter.matches(props), \
                        "Filter '%s' should not match %s" \
                        % (ldap_filter, props))

        # Value present
        props["valid"] = True
        self.assertTrue(ldap_filter.matches(props), \
                        "Filter '%s' should match %s" % (ldap_filter, props))

        props["valid"] = False
        self.assertTrue(ldap_filter.matches(props), \
                        "Filter '%s' should match %s" % (ldap_filter, props))

        # Some other type
        props["valid"] = "1234"
        self.assertTrue(ldap_filter.matches(props), \
                        "Filter '%s' should match %s" % (ldap_filter, props))

        # Empty string
        props["valid"] = ""
        self.assertFalse(ldap_filter.matches(props), \
                        "Filter '%s' should not match %s" \
                        % (ldap_filter, props))

        # Empty list
        props["valid"] = []
        self.assertFalse(ldap_filter.matches(props), \
                        "Filter '%s' should not match %s" \
                        % (ldap_filter, props))


    def testStarCriteria(self):
        """
        Tests the start filter on strings
        """
        filters = {}
        # Simple string test
        filters["(string=after*)"] = (("after", "after1234"), \
                                      ("1324after", "before", "After"))

        filters["(string=*before)"] = (("before", "1234before"), \
                                       ("after", "before1234"), "Before")

        filters["(string=*middle*)"] = (("middle", "aaamiddle1234", \
                                         "middle456", "798middle"), \
                                        ("miDDle"))

        filters["(string=*mi*ed*)"] = (("mixed", "mixed1234", "798mixed",
                                        "mi O_O ed"), ("Mixed"))

        # List test
        filters["(string=*li*ed*)"] = ((["listed"], ["toto", "aaaliXed123"]), \
                                      ([], ["LixeD"], ["toto"]))

        applyTest(self, filters, "string")


    def testListCriteria(self):
        """
        Test the presence filter on lists
        """
        filters = {}
        filters["(list=toto)"] = ((["toto"], ["titi", "toto"], \
                                   ["toto", "titi"], \
                                   ["titi", "toto", "tutu"]), \
                                  ([], ["titi"], ["*toto*"]))

        applyTest(self, filters, "list")


    def testInequalityCriteria(self):
        """
        Test the inequality operators
        """
        filters = {}
        filters["(id<10)"] = (("-10", -10, 0, 9), (10, 11, "12"))
        filters["(id<=10)"] = (("-10", -10, 0, 9, 10), (11, "12"))
        filters["(id>=10)"] = ((10, 11, "12"), ("-10", -10, 0, 9))
        filters["(id>10)"] = ((11, "12"), ("-10", -10, 0, 9, 10))

        applyTest(self, filters, "id")


    def testApproximateCriteria(self):
        """
        Tests the approximate criteria
        """
        filters = {}

        # Simple string test
        filters["(string~=aBc)"] = (("abc", "ABC", "aBc", "Abc"),
                                    ("bac", "aDc"))

        # Simple list test
        filters["(string~=dEf)"] = ((["abc", "def"], ["DEF"]),
                                    ([], ["aBc"]))

        # Star test
        filters["(string~=*test*)"] = ((["bigTest", "def"], "test", "TEST42"),
                                    ([], ["aBc"], "T3st"))

        applyTest(self, filters, "string")

# ------------------------------------------------------------------------------

class LDAPFilterTest(unittest.TestCase):
    """
    Tests for the LDAP filter behavior
    """

    def testRepr(self):
        """
        Test repr() -> eval() transformation
        """
        # String filter : no spaces between operators nor operands
        # => allows direct str() results tests
        str_filter = "(&(test=False)(test2=True))"

        # Make the filter
        ldap_filter = get_ldap_filter(str_filter)

        # Assert strings representations are equals
        self.assertEquals(str_filter, str(ldap_filter))

        # Conversion
        repr_filter = repr(ldap_filter)
        self.assertIn(str_filter, repr_filter, \
                      "The representation must contain the filter string")

        # Evaluation
        eval_filter = eval(repr_filter)

        # Equality based on the string form
        self.assertEquals(str_filter, str(eval_filter), "Invalid evaluation")

        # Match test
        for test_value in (True, False):
            for test2_value in (True, False):
                for test3_value in (None, True, False, 42, "string"):
                    properties = {"test": test_value, "test2": test2_value, \
                                  "test3": test3_value}

                    self.assertEquals(ldap_filter.matches(properties), \
                                      eval_filter.matches(properties), \
                                      "Different result found for %s" \
                                      % properties)


    def testNot(self):
        """
        Tests the NOT operator
        """
        filters = {}

        filters["(test=False)"] = ((False, [False], [True, False]),
                                   (True, [True], "1123", 1, 0))

        filters["(!(test=False))"] = ((True, [True], "1123", 1, 0),
                                      (False, [False], [True, False]))

        # Simple cases
        applyTest(self, filters, "test")

        # NOT handles only one operand
        self.assertRaises(ValueError, get_ldap_filter, \
                          "(!(test=True)(test2=False))")


    def testAnd(self):
        """
        Tests the AND operator
        """
        props = {}
        ldap_filter = get_ldap_filter("(&(test=True)(test2=False))")

        # Valid
        props["test"] = True
        props["test2"] = False
        self.assertTrue(ldap_filter.matches(props), \
                    "Filter '%s' should match %s" % (ldap_filter, props))

        # Invalid...
        props["test"] = False
        props["test2"] = False
        self.assertFalse(ldap_filter.matches(props), \
                    "Filter '%s' should not match %s" % (ldap_filter, props))

        props["test"] = False
        props["test2"] = True
        self.assertFalse(ldap_filter.matches(props), \
                    "Filter '%s' should not match %s" % (ldap_filter, props))

        props["test"] = True
        props["test2"] = True
        self.assertFalse(ldap_filter.matches(props), \
                    "Filter '%s' should not match %s" % (ldap_filter, props))

    def testOr(self):
        """
        Tests the OR operator
        """
        props = {}
        ldap_filter = get_ldap_filter("(|(test=True)(test2=False))")

        # Valid ...
        props["test"] = True
        props["test2"] = False
        self.assertTrue(ldap_filter.matches(props), \
                    "Filter '%s' should match %s" % (ldap_filter, props))

        props["test"] = False
        props["test2"] = False
        self.assertTrue(ldap_filter.matches(props), \
                    "Filter '%s' should match %s" % (ldap_filter, props))

        props["test"] = True
        props["test2"] = True
        self.assertTrue(ldap_filter.matches(props), \
                    "Filter '%s' should match %s" % (ldap_filter, props))

        # Invalid...
        props["test"] = False
        props["test2"] = True
        self.assertFalse(ldap_filter.matches(props), \
                    "Filter '%s' should not match %s" % (ldap_filter, props))

# ------------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
