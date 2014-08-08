#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the Jabsorb conversion module

:author: Thomas Calmant
"""

# Pelix
import pelix.misc.jabsorb as jabsorb

# Standard library
import uuid
try:
    import unittest2 as unittest
except ImportError:
    import unittest

# ------------------------------------------------------------------------------

__version__ = "1.0.0"

# ------------------------------------------------------------------------------


class JabsorbConverterTest(unittest.TestCase):
    """
    Tests the Jabsorb conversion module
    """
    def testIsBuiltin(self):
        """
        Tests the _is_builtin() method
        """
        for item in (int, 42, str, "toto", bool, True, float, 3.14,
                     dict, {"a": "b"}, set, set([12]), tuple, (1, 2, 3),
                     list, [4, 5, 6]):
            self.assertTrue(jabsorb._is_builtin(item),
                            "Item {0} should be built-in".format(item))

        for item in (unittest.TestCase, jabsorb, jabsorb.to_jabsorb):
            self.assertFalse(jabsorb._is_builtin(item),
                             "Item {0} should not be built-in".format(item))

    def testMirror(self):
        """
        Tests the result of to_jabsorb + from_jabsorb
        """
        value = {"list": [1, 2, 3],
                 "tuple": (1, 2, 3),
                 "set": set((1, 2, 3)),
                 "dict": {"a": "b", "c": "d"},
                 "int": 42,
                 "float": 3.14,
                 None: None,
                 3.10: 51}

        # Convert to Jabsorb
        jabsorb_value = jabsorb.to_jabsorb(value)

        # ... back to "normal" Python
        revert_value = jabsorb.from_jabsorb(jabsorb_value)

        # Check content
        self.assertDictEqual(revert_value, value)

    def testCustomClass(self):
        """
        Tests the conversion of a custom class
        """
        # Basic class
        class Custom(object):
            javaClass = "test.Custom"

            def __init__(self):
                self.value = str(uuid.uuid4())
                self._value = str(uuid.uuid4())
                self.__value = str(uuid.uuid4())

        # Convert it
        value = Custom()
        jabsorb_value = jabsorb.to_jabsorb(value)
        revert = jabsorb.from_jabsorb(jabsorb_value)

        # Check Jabsorb public value
        self.assertEqual(jabsorb_value[jabsorb.JAVA_CLASS], Custom.javaClass)
        self.assertEqual(jabsorb_value['value'], value.value)

        # Check absence of private value
        self.assertNotIn('_value', jabsorb_value)
        self.assertNotIn('__value', jabsorb_value)
        self.assertNotIn('_Custom__value', jabsorb_value)

        # Check revert value
        self.assertEqual(revert[jabsorb.JAVA_CLASS], Custom.javaClass)
        self.assertEqual(revert['value'], value.value)
        self.assertEqual(revert.javaClass, Custom.javaClass)
        self.assertEqual(revert.value, value.value)

    def testBeanInTheMiddle(self):
        """
        Tests the conversion of the content of a bean (half parsed stream)
        """
        class Bean(object):

            def __init__(self):
                self.list = jabsorb.to_jabsorb([1, 2, 3])
                self.tuple = jabsorb.to_jabsorb((1, 2, 3))
                self.set = jabsorb.to_jabsorb(set((1, 2, 3)))

            def __eq__(self, other):
                return self.list == other.list \
                    and self.tuple == other.tuple \
                    and self.set == other.set

        # Prepare the bean
        bean = Bean()

        # Parse its content
        revert = jabsorb.from_jabsorb(bean)
        self.assertIs(revert, bean)
        self.assertEqual(revert.list, [1, 2, 3])
        self.assertEqual(revert.tuple, (1, 2, 3))
        self.assertEqual(revert.set, set((1, 2, 3)))

    def testHashableType(self):
        """
        Tests the behavior of hashable types
        """
        # Prepare items
        hash_dict = jabsorb.HashableDict(((1, 2), (3, 4)))
        hash_attrmap = jabsorb.AttributeMap(hash_dict.items())
        hash_set = jabsorb.HashableSet((1, 2, 3))
        hash_list = jabsorb.HashableList((1, 2, 3))

        # Group'em
        hash_values = [hash_dict, hash_attrmap, hash_set, hash_list]

        # Try to put them in a set
        in_set = set(hash_values)
        self.assertEqual(len(in_set), len(hash_values))

        # Try to put them in a dictionary
        dico = {}
        for value in in_set:
            dico[value] = 42
        self.assertEqual(len(dico), len(hash_values))

    def testDoubleConvert(self):
        """
        Checks the beheavior after a second call to to_jabsorb
        """
        value = {"list": [1, 2, 3],
                 "tuple": (1, 2, 3),
                 "set": set((1, 2, 3)),
                 "dict": {"a": "b", "c": "d"},
                 "int": 42,
                 "float": 3.14,
                 None: None,
                 3.10: 51}

        # Double conversion: no modification on second pass
        first = jabsorb.to_jabsorb(value)
        second = jabsorb.to_jabsorb(first)
        self.assertDictEqual(second, first)

        # Double revert
        revert_second = jabsorb.from_jabsorb(second)
        revert_first = jabsorb.from_jabsorb(revert_second)

        # Check results
        self.assertDictEqual(revert_second, value)
        self.assertDictEqual(revert_first, value)

    def testJsonAndJavaClass(self):
        """
        Tests the conservation of the __jsonclass__ attribute
        """
        for has_json in (True, False):
            for has_java in (True, False):
                if not any((has_json, has_java)):
                    # Out of the scope of this test
                    continue

                # Prepare a fake bean
                value = {"list": [1, 2, 3],
                         "tuple": (1, 2, 3),
                         "set": set((1, 2, 3)),
                         "dict": {"a": "b", "c": "d"},
                         "int": 42,
                         "float": 3.14,
                         None: None,
                         3.10: 51}

                if has_json:
                    value[jabsorb.JSON_CLASS] = [1, 2, 3, [4, 5]]

                if has_java:
                    value[jabsorb.JAVA_CLASS] = 'test.Bean'

                # Convert it
                jabsorb_value = jabsorb.to_jabsorb(value)

                # Check the value of the JSON class
                if has_json:
                    self.assertEqual(jabsorb_value[jabsorb.JSON_CLASS],
                                     value[jabsorb.JSON_CLASS])

                if has_java:
                    self.assertEqual(jabsorb_value[jabsorb.JAVA_CLASS],
                                     value[jabsorb.JAVA_CLASS])

                # Revert
                revert = jabsorb.from_jabsorb(jabsorb_value)
                self.assertDictEqual(revert, value)
