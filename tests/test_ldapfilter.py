#!/usr/bin/env python3
# -- Content-Encoding: UTF-8 --
"""
LDAP filter parser tests

:author: Thomas Calmant
"""

import inspect
import pytest

from pelix.ldapfilter import get_ldap_filter
import pelix.ldapfilter


# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


def apply_test(self, filters, key):
    """
    Applies a list of tests according to the given dictionary

    Dictionary format: filter -> ([True, results], [False, results])

    @param filters: A filters test dictionary
    @param key: The key to use in the property dictionary
    """
    props = {}

    for filter_str, tests in filters.items():
        ldap_filter = get_ldap_filter(filter_str)
        assert ldap_filter is not None, "{0} is a valid filter" \
                             .format(filter_str)

        for good in tests[0]:
            props[key] = good
            assert ldap_filter.matches(props), \
                            "Filter '{0}' should match {1}" \
                            .format(ldap_filter, props)

        for bad in tests[1]:
            props[key] = bad
            assert not ldap_filter.matches(props), \
                             "Filter '{0}' should not match {1}" \
                             .format(ldap_filter, props)

# ------------------------------------------------------------------------------


class TestLDAPUtilities:
    """
    Tests for LDAP utility methods
    """
    def test_comparator2str(self):
        """
        Tests comparator2str()
        """
        for comparator in ('=', '<', '<=', '>', '>=', '=', '~='):
            # Parse a criteria with that comparator
            ldap_filter = get_ldap_filter("(a{0}1)".format(comparator))

            # Get the string version of the parsed comparator
            str_comparator = pelix.ldapfilter.comparator2str(
                ldap_filter.comparator)

            assert str_comparator == comparator, \
                             "Bad string for comparator '{0}': '{1}'" \
                             .format(comparator, str_comparator)

        # Invalid comparators
        for comparator in (None, str, str(), int()):
            str_comparator = pelix.ldapfilter.comparator2str(comparator)
            assert str_comparator == "??", \
                             "Bad string for comparator '{0}': '{1}'" \
                             .format(comparator, str_comparator)

    def test_operator2str(self):
        """
        Tests operator2str()
        """
        operators = {pelix.ldapfilter.AND: "&",
                     pelix.ldapfilter.OR: "|",
                     pelix.ldapfilter.NOT: "!"}

        for operator, str_operator in operators.items():
            conv_operator = pelix.ldapfilter.operator2str(operator)
            assert str_operator == conv_operator, "Invalid operator conversion '{0}': '{1}'".format(str_operator, conv_operator)

        for operator in (None, str, int, str(), "AND", "OR", "NOT", 42):
            conv_operator = pelix.ldapfilter.operator2str(operator)
            assert conv_operator == "<unknown>", "Invalid operator conversion '{0}': '{1}'".format(operator, conv_operator)

    def test_escape_ldap(self):
        """
        Tests escape_LDAP() and unescape_LDAP()

        Tested values from :
        https://www.owasp.org/index.php/Preventing_LDAP_Injection_in_Java
        """
        # Tested values: normal -> escaped
        tested_values = {None: None,
                         # Empty string -> Empty string
                         "": "",
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
                             '\\ Hello\\\\ \\+ \\, \\"World\\" \\;\\ '}

        for normal, escaped in tested_values.items():
            # Escape
            ldap_escape = pelix.ldapfilter.escape_LDAP(normal)
            assert escaped == ldap_escape, \
                             "Invalid escape '{0}' should be '{1}'" \
                             .format(ldap_escape, escaped)

            # Un-escape
            ldap_unescape = pelix.ldapfilter.unescape_LDAP(ldap_escape)
            assert escaped == ldap_escape, \
                             "Invalid unescape '{0}' should be '{1}'" \
                             .format(ldap_unescape, normal)

    def test_parse_criteria(self):
        """
        Tests the _parse_ldap_criteria() method
        """
        # Invalid criteria / incomplete operators
        for invalid in ("test 12", "=12", "test=", "test~12", "test~"):
            with pytest.raises(ValueError):
                pelix.ldapfilter._parse_ldap_criteria(invalid)

        # Escape test (avoid the first test)
        value = "a=2 tes\\ t\\==1\\ 2\\~"
        criteria = pelix.ldapfilter._parse_ldap_criteria(value, 4, len(value))
        assert criteria.name == "tes t=", \
                         "Escaped name not correctly parsed"
        assert criteria.value == "1 2~", \
                         "Escaped value not correctly parsed"

        # Invalid test range
        test_str = "test=1"
        with pytest.raises(ValueError):
            pelix.ldapfilter._parse_ldap_criteria(test_str, -1, len(test_str))

        with pytest.raises(ValueError):
            pelix.ldapfilter._parse_ldap_criteria(test_str, len(test_str) - 1, len(test_str) - 2)

    def test_parse_ldap(self):
        """
        Tests the _parse_ldap method
        """
        # Empty filters
        for empty in (None, "", "   "):
            assert pelix.ldapfilter._parse_ldap(empty) is None, "Empty filter: must return None"

        # Invalid filters
        for invalid in ("(", "(test", "(|(test=True)(test=False))))", "(test)", "((test=1)(test2=1))"):
            with pytest.raises(ValueError):
                pelix.ldapfilter._parse_ldap(invalid)

        # Criteria parsing
        criteria = pelix.ldapfilter.LDAPCriteria(
            "test", True, pelix.ldapfilter._comparator_eq
            )
        assert pelix.ldapfilter._parse_ldap(str(criteria)) == criteria, "Incorrect result: {0}".format(criteria)

        # Filter parsing
        ldap_filter = pelix.ldapfilter.LDAPFilter(pelix.ldapfilter.AND)
        sub_filter = pelix.ldapfilter.LDAPFilter(pelix.ldapfilter.OR)
        sub_filter_2 = pelix.ldapfilter.LDAPFilter(pelix.ldapfilter.NOT)
        sub_filter_2.subfilters.append(criteria)
        sub_filter.subfilters.append(sub_filter_2)
        sub_filter.subfilters.append(criteria)
        ldap_filter.subfilters.append(sub_filter)
        ldap_filter.subfilters.append(criteria)

        criteria_2 = pelix.ldapfilter.LDAPCriteria(
            "te st=", True, pelix.ldapfilter._comparator_eq)
        ldap_filter.subfilters.append(criteria_2)

        assert pelix.ldapfilter._parse_ldap(str(ldap_filter)) == \
                         ldap_filter.normalize(), \
                         "Incorrect result: {0}".format(ldap_filter)

    def test_combine(self):
        """
        Tests the combine_filters() method
        """
        # Standard case
        criterias = [get_ldap_filter("(test=True)"),
                     get_ldap_filter("(test2=False)")]

        for operator in (pelix.ldapfilter.AND, pelix.ldapfilter.OR):
            ldap_filter = pelix.ldapfilter.combine_filters(criterias, operator)

            assert isinstance(ldap_filter, pelix.ldapfilter.LDAPFilter)
            assert ldap_filter.operator == operator, \
                             "Invalid operator"
            assert len(ldap_filter.subfilters) == 2, \
                             "Invalid count of sub filters"

            for criteria in criterias:
                assert criteria in ldap_filter.subfilters, \
                              "A criteria is missing in the result"

        # No filter given
        for empty in (None, [], tuple(), (None, None, None)):
            assert pelix.ldapfilter.combine_filters(empty) is None, \
                              "Can't combine an empty list of filters"

        # Invalid types
        for invalid in ("Filters", get_ldap_filter("(!(test=True))")):
            with pytest.raises(TypeError):
                pelix.ldapfilter.combine_filters(invalid)

        ldap_filter_1 = get_ldap_filter("(test=True)")
        ldap_filter_2 = pelix.ldapfilter.LDAPFilter(pelix.ldapfilter.AND)

        # Unique filter in result
        assert pelix.ldapfilter.combine_filters((None, ldap_filter_1)) is \
                      ldap_filter_1, "The result of combine must be minimal"

        assert pelix.ldapfilter.combine_filters((ldap_filter_1,
                                                        ldap_filter_2)) is \
                      ldap_filter_1, "The result of combine must be minimal"

    def test_get_ldap_filter(self):
        """
        Tests the get_ldap_filter() method
        """
        # Simple parsing / re-parsing test
        for str_filter, filter_type in \
                (("(|(test=True)(test2=False))", pelix.ldapfilter.LDAPFilter),
                 ("(test=True)", pelix.ldapfilter.LDAPCriteria)):
            ldap_filter = get_ldap_filter(str_filter)
            assert isinstance(ldap_filter, filter_type)

            assert str(ldap_filter) == str_filter, "Invalid parsing"
            assert get_ldap_filter(ldap_filter) is ldap_filter, \
                          "get_ldap_filter should return the given object."

        # Empty filters
        for empty in (None, "", "   "):
            assert get_ldap_filter(empty) is None, \
                              "Empty filter should return None"

        # Invalid types
        for invalid in (1, [], {}):
            with pytest.raises(TypeError):
                get_ldap_filter(invalid)

# ------------------------------------------------------------------------------


class TestLDAPCriteria:
    """
    Tests for the LDAP criteria behavior
    """
    def test_init(self):
        """
        Tests __init__() behavior on invalid values
        """
        for name in (None, "", "name"):
            for value in (None, "", "value"):
                for comparator in (None, True, lambda x: True):
                    if not all((name, value, comparator)) \
                            or (not inspect.isfunction(comparator)
                                and not inspect.ismethod(comparator)):
                        # One value is None
                        with pytest.raises(ValueError):
                            pelix.ldapfilter.LDAPCriteria(name,
                                          value, comparator)

                    else:
                        # All values are OK
                        criteria = pelix.ldapfilter.LDAPCriteria(name, value,
                                                                 comparator)
                        assert name == criteria.name, \
                                         "Name modified"
                        assert value == criteria.value, \
                                         "Value modified"
                        assert inspect.ismethod(criteria.comparator) \
                            or inspect.isfunction(criteria.comparator), \
                            "Invalid comparator accepted"

    def test_repr(self):
        """
        Tests repr() -> eval() transformation
        """
        # String filter: no spaces between operators nor operands
        # => allows direct str() results tests
        str_criteria = "(test=False)"

        # Make the filter
        criteria = get_ldap_filter(str_criteria)
        assert isinstance(criteria, pelix.ldapfilter.LDAPCriteria)

        # Assert strings representations are equals
        assert str_criteria == str(criteria)

        # Conversion
        repr_criteria = repr(criteria)
        assert str_criteria in repr_criteria, \
                      "The representation must contain the criteria string"

        # Evaluation
        eval_filter = eval(repr_criteria)

        # Equality based on the string form
        assert str_criteria == str(eval_filter), "Invalid evaluation"

    def test_eq(self):
        """
        Tests the LDAPFilter objects equality
        """
        # Some filter
        str_filter = "(&(test=False)(test2=True))"
        ldap_filter = get_ldap_filter(str_filter)

        # Test with other values
        assert ldap_filter is not None, "Filter is not equal to None"
        assert ldap_filter == ldap_filter, "Filter is not self-equal"
        assert pelix.ldapfilter.LDAPFilter(pelix.ldapfilter.NOT) != pelix.ldapfilter.LDAPCriteria(
            'test', 123, pelix.ldapfilter._comparator_approximate), "Invalid equality (type)"

        # Tests order must not provide a different filter
        str_filter_2 = "(&(test2 = True)(test = False))"
        ldap_filter_2 = get_ldap_filter(str_filter_2)
        assert ldap_filter == ldap_filter_2, "Filters are not equal"

        # Inequality check
        assert ldap_filter != get_ldap_filter("(test2=true)"), "Invalid equality (type)"
        assert get_ldap_filter("(test2=true)") != ldap_filter, "Invalid equality (type, reverse)"

        assert ldap_filter != \
            get_ldap_filter("(&(test=False)(test2=True)(test3=1))"), "Invalid equality (size)"
        assert get_ldap_filter("(&(test=False)(test2=True)(test3=1))") != ldap_filter, "Invalid equality (size, reverse)"

        assert ldap_filter != get_ldap_filter("(&(test1=False)(test2=True))"), "Invalid equality (sub-filter)"
        assert get_ldap_filter("(&(test1=False)(test2=True))") != ldap_filter, "Invalid equality (sub-filter, reverse)"

        assert ldap_filter != get_ldap_filter("(|(test=False)(test2=True))"), "Invalid equality (operator)"
        assert get_ldap_filter("(|(test=False)(test2=True))") != ldap_filter, "Invalid equality (operator, reverse)"

    def test_normalize(self):
        """
        Tests the normalize() method
        """
        criteria = get_ldap_filter("(test=True)")
        assert criteria is criteria.normalize(), "Criteria.normalize() must return itself"

    def test_empty_criteria(self):
        """
        Empty filter test
        """
        assert get_ldap_filter(None) is None, "None filter must return None"
        assert get_ldap_filter("") is None, "Empty filter must return None"
        assert get_ldap_filter(" ") is None, "Trimmed filter must return None"

    def test_simple_criteria(self):
        """
        Simple boolean filter test
        """
        props = {}

        ldap_filter = get_ldap_filter("(valid=True)")
        assert ldap_filter is not None, "Filter should not be None"

        # Test with a single property
        props["valid"] = True
        assert ldap_filter.matches(props), "Filter '{0}' should match {1}".format(ldap_filter, props)

        props["valid"] = False
        assert not ldap_filter.matches(props), "Filter '{0}' should not match {1}".format(ldap_filter, props)

        # Test the ignorance of other properties
        props["valid2"] = True
        assert not ldap_filter.matches(props), "Filter '{0}' should not match {1}".format(ldap_filter, props)

        props["valid"] = "True"
        assert ldap_filter.matches(props), "Filter '{0}' should match {1}".format(ldap_filter, props)

    def test_presence_criteria(self):
        """
        Test the presence filter
        """
        props = {}

        ldap_filter = get_ldap_filter("(valid=*)")
        assert ldap_filter is not None, "Filter should not be None"

        # Missing value
        assert not ldap_filter.matches(props), "Filter '{0}' should not match {1}".format(ldap_filter, props)

        # Still missing
        props["valid2"] = True
        assert not ldap_filter.matches(props), "Filter '{0}' should not match {1}".format(ldap_filter, props)

        # Value present
        props["valid"] = True
        assert ldap_filter.matches(props), "Filter '{0}' should match {1}".format(ldap_filter, props)

        props["valid"] = False
        assert ldap_filter.matches(props), "Filter '{0}' should match {1}".format(ldap_filter, props)

        # Some other type
        props["valid"] = "1234"
        assert ldap_filter.matches(props), "Filter '{0}' should match {1}".format(ldap_filter, props)

        # Empty values
        for empty in ('', [], tuple()):
            props["valid"] = empty
            assert not ldap_filter.matches(props), "Filter '{0}' should not match {1}".format(ldap_filter, props)

    def test_star_criteria(self):
        """
        Tests the star/joker filter on strings
        """
        filters = {}
        # Simple string test
        filters["(string=after*)"] = (("after", "after1234"),
                                      ("1324after", "before", "After"))

        filters["(string=*before)"] = (("before", "1234before"),
                                       ("after", "before1234"), "Before")

        filters["(string=*middle*)"] = (("middle", "aaamiddle1234",
                                         "middle456", "798middle"),
                                        ("miDDle",))

        filters["(string=*mi*ed*)"] = (("mixed", "mixed1234", "798mixed",
                                        "mi O_O ed"), ("Mixed",))

        # List test
        filters["(string=*li*ed*)"] = ((["listed"], ["toto", "aaaliXed123"]),
                                       ([], ["LixeD"], ["toto"]))

        apply_test(self, filters, "string")

        # Direct call test
        assert not pelix.ldapfilter._comparator_star('T*ue', True), "String star can't be compared to other values"

        assert pelix.ldapfilter._comparator_star('T*ue', 'True'), "String star test failure"

    def test_list_criteria(self):
        """
        Test the presence filter on lists
        """
        filters = {}
        filters["(list=toto)"] = ((["toto"], ["titi", "toto"],
                                   ["toto", "titi"],
                                   ["titi", "toto", "tutu"]),
                                  ([], ["titi"], ["*toto*"]))

        apply_test(self, filters, "list")

    def test_inequality_criteria(self):
        """
        Test the inequality operators
        """
        filters = {}
        filters["(id<10)"] = (("-10", -10, 0, 9), (10, 11, "12"))
        filters["(id<=10)"] = (("-10", -10, 0, 9, 10), (11, "12"))
        filters["(id>=10)"] = ((10, 11, "12"), ("-10", -10, 0, 9))
        filters["(id>10)"] = ((11, "12"), ("-10", -10, 0, 9, 10))

        apply_test(self, filters, "id")

        # Direct call test (for other cases)
        assert pelix.ldapfilter._comparator_gt('13', 14.0), "Integer/Float comparison error"
        assert pelix.ldapfilter._comparator_gt('13.0', 14.0), "Float/Float comparison error"
        assert pelix.ldapfilter._comparator_gt('13.0', 14), "Float/Integer comparison error"

        assert pelix.ldapfilter._comparator_lt('13', 12.0), "Integer/Float comparison error"
        assert pelix.ldapfilter._comparator_lt('13.0', 12.0), "Float/Float comparison error"
        assert pelix.ldapfilter._comparator_lt('13.0', 12), "Float/Integer comparison error"

        assert not pelix.ldapfilter._comparator_gt('13.0', 14 + 1j), "Float/Complex comparison error"
        assert not pelix.ldapfilter._comparator_gt('13', 14 + 1j), "Integer/Complex comparison error"
        assert not pelix.ldapfilter._comparator_gt('13.0 + 1j', 14), "Complex/Integer comparison error"
        assert not pelix.ldapfilter._comparator_gt('13.0 + 1j', 14.0), "Complex/Float comparison error"

        assert not pelix.ldapfilter._comparator_lt('13.0', 12 + 1j), "Float/Complex comparison error"
        assert not pelix.ldapfilter._comparator_lt('13', 12 + 1j), "Integer/Complex comparison error"
        assert not pelix.ldapfilter._comparator_lt('13.0 + 1j', 12), "Complex/Integer comparison error"
        assert not pelix.ldapfilter._comparator_lt('13.0 + 1j', 12.0), "Complex/Float comparison error"

    def test_approximate_criteria(self):
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

        apply_test(self, filters, "string")

        # Direct call test (for other cases)
        assert not pelix.ldapfilter._comparator_approximate('test', None), "Invalid None test result"

        assert pelix.ldapfilter._comparator_approximate('test', ['Test', 12]), "Invalid list test result"

# ------------------------------------------------------------------------------


class TestLDAPfilter:
    """
    Tests for the LDAP filter behavior
    """
    def test_init(self):
        """
        Tests __init__() behavior on invalid values
        """
        # WARNING: don't test True, as True == 1 in Python
        for value in (None, '', -1, {}, lambda x: True):
            with pytest.raises(ValueError):
                pelix.ldapfilter.LDAPFilter(value)

        for operator in (pelix.ldapfilter.AND, pelix.ldapfilter.OR,
                         pelix.ldapfilter.NOT):
            ldap_filter = pelix.ldapfilter.LDAPFilter(operator)
            assert ldap_filter.operator == operator, "Operator modified"
            assert len(ldap_filter.subfilters) == 0, "Filter not empty after init"

    def test_repr(self):
        """
        Test repr() -> eval() transformation
        """
        # String filter: no spaces between operators nor operands
        # => allows direct str() results tests
        str_filter = "(&(test=False)(test2=True))"

        # Make the filter
        ldap_filter = get_ldap_filter(str_filter)

        # Assert strings representations are equals
        assert str_filter == str(ldap_filter)

        # Conversion
        repr_filter = repr(ldap_filter)
        assert str_filter in repr_filter, "The representation must contain the filter string"

        # Evaluation
        eval_filter = eval(repr_filter)

        # Equality based on the string form
        assert str_filter == str(eval_filter), "Invalid evaluation"

        # Match test
        for test_value in (True, False):
            for test2_value in (True, False):
                for test3_value in (None, True, False, 42, "string"):
                    properties = {"test": test_value, "test2": test2_value,
                                  "test3": test3_value}

                    assert ldap_filter.matches(properties) == eval_filter.matches(properties), "Different result found for {0}".format(properties)

    def test_eq(self):
        """
        Tests the LDAPFilter objects equality
        """
        # Some filter
        str_filter = "(&(test=False)(test2=True))"
        ldap_filter = get_ldap_filter(str_filter)

        # Test with other values
        assert ldap_filter is not None, "Filter is not equal to None"
        assert ldap_filter == ldap_filter, "Filter is not self-equal"
        assert pelix.ldapfilter.LDAPFilter(pelix.ldapfilter.NOT) != pelix.ldapfilter.LDAPCriteria(
            'test', 123, pelix.ldapfilter._comparator_approximate), "Invalid equality (type)"

        # Tests order must not provide a different filter
        str_filter_2 = "(&(test2=True)(test=False))"
        ldap_filter_2 = get_ldap_filter(str_filter_2)
        assert ldap_filter == ldap_filter_2, "Filters are not equal"

        # Inequality check
        assert ldap_filter != get_ldap_filter("(test2=true)"), "Invalid equality (type)"

        assert ldap_filter != get_ldap_filter("(&(test=False)(test2=True)(test3=1))"), "Invalid equality (size)"

        assert ldap_filter != get_ldap_filter("(&(test1=False)(test2=True))"), "Invalid equality (sub-filter)"

        assert ldap_filter != get_ldap_filter("(|(test=False)(test2=True))"), "Invalid equality (operator)"

    def test_append(self):
        """
        Tests the filter append() method
        """
        # "And" operator
        ldap_filter = pelix.ldapfilter.LDAPFilter(pelix.ldapfilter.AND)

        # Add a "normal" value
        criteria = get_ldap_filter("(test=True)")
        ldap_filter.append(criteria)
        assert len(ldap_filter.subfilters) == 1, "Criteria not added"

        # Add invalid values
        for invalid_value in (None, "(test=False)", "(|(test=True)(test2=False))"):
            with pytest.raises(TypeError):
                ldap_filter.append(invalid_value)

        # Special case: 'Not' operator
        ldap_filter = pelix.ldapfilter.LDAPFilter(pelix.ldapfilter.NOT)
        ldap_filter.append(criteria)

        # No more value must be accepted
        with pytest.raises(ValueError):
            ldap_filter.append(criteria)

    def test_normalize(self):
        """
        Tests the normalize() method
        """
        # Empty filter
        for operator in (pelix.ldapfilter.AND, pelix.ldapfilter.OR, pelix.ldapfilter.NOT):
            assert pelix.ldapfilter.LDAPFilter(operator).normalize() is None, "Empty filter normalized form must be None"

        # Standard filter
        ldap_filter = get_ldap_filter("(|(test=True)(test2=False))")
        assert ldap_filter.normalize() is ldap_filter, "Normalized filter must return itself"

        criteria = get_ldap_filter("(test=True)")

        # 'Not' Filter with 1 child
        ldap_filter = pelix.ldapfilter.LDAPFilter(pelix.ldapfilter.NOT)
        ldap_filter.append(criteria)
        assert ldap_filter.normalize() is ldap_filter, "'Not' filter with 1 child must return itself"

        # 'And', 'Or' filter
        for operator in (pelix.ldapfilter.AND, pelix.ldapfilter.OR):
            ldap_filter = pelix.ldapfilter.LDAPFilter(operator)
            ldap_filter.append(criteria)
            assert ldap_filter.normalize() == criteria, "'And' or 'Or' with 1 child must return the child"

    def test_not(self):
        """
        Tests the NOT operator
        """
        filters = {}

        filters["(test=False)"] = ((False, [False], [True, False]),
                                   (True, [True], "1123", 1, 0))

        filters["(!(test=False))"] = ((True, [True], "1123", 1, 0),
                                      (False, [False], [True, False]))

        # Simple cases
        apply_test(self, filters, "test")

        # NOT handles only one operand
        with pytest.raises(ValueError):
            get_ldap_filter("(!(test=True)(test2=False))")

    def test_and(self):
        """
        Tests the AND operator
        """
        props = {}
        ldap_filter = get_ldap_filter("(&(test=True)(test2=False))")

        # Valid
        props["test"] = True
        props["test2"] = False
        assert ldap_filter.matches(props), "Filter '{0}' should match {1}".format(ldap_filter, props)

        # Invalid...
        props["test"] = False
        props["test2"] = False
        assert not ldap_filter.matches(props), "Filter '{0}' should not match {1}".format(ldap_filter, props)

        props["test"] = False
        props["test2"] = True
        assert not ldap_filter.matches(props), "Filter '{0}' should not match {1}".format(ldap_filter, props)

        props["test"] = True
        props["test2"] = True
        assert not ldap_filter.matches(props), "Filter '{0}' should not match {1}".format(ldap_filter, props)

    def test_or(self):
        """
        Tests the OR operator
        """
        props = {}
        ldap_filter = get_ldap_filter("(|(test=True)(test2=False))")

        # Valid ...
        props["test"] = True
        props["test2"] = False
        assert ldap_filter.matches(props), "Filter '{0}' should match {1}".format(ldap_filter, props)

        props["test"] = False
        props["test2"] = False
        assert ldap_filter.matches(props), "Filter '{0}' should match {1}".format(ldap_filter, props)

        props["test"] = True
        props["test2"] = True
        assert ldap_filter.matches(props), "Filter '{0}' should match {1}".format(ldap_filter, props)

        # Invalid...
        props["test"] = False
        props["test2"] = True
        assert not ldap_filter.matches(props), "Filter '{0}' should not match {1}".format(ldap_filter, props)
