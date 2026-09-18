#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the framework events.

:author: Thomas Calmant
"""

import unittest
from typing import Any, Protocol

from pelix.constants import (
    FORBIDDEN_SPECIFICATION_CHARACTERS,
    PELIX_SPECIFICATION_FIELD,
    Specification,
    check_specification_name,
)
from pelix.ldapfilter import ESCAPE_CHARACTER, ESCAPED_CHARACTERS


class Foobar(Protocol):
    """
    Sample protocol, using class name
    """


@Specification("Hello")
class Foo(Protocol):
    """
    Sample protocol, using specification name
    """


class TestSpecificationDecorator(unittest.TestCase):
    """
    Tests the Specification decorator
    """

    @staticmethod
    def __get_specification(clazz) -> list[str]:
        """
        Returns the specifications of the given class
        """
        return getattr(clazz, PELIX_SPECIFICATION_FIELD)

    def test_single_specification(self) -> None:
        """
        Test the definition of a single specification
        """

        @Specification("TestService")
        class TestService:
            pass

        self.assertListEqual(self.__get_specification(TestService), ["TestService"])

    def test_multiple_specifications(self) -> None:
        """
        Test the definition of multiple specifications
        """

        @Specification("ServiceA", "ServiceB", Foobar, Foo)
        class TestService:
            pass

        self.assertListEqual(self.__get_specification(TestService), ["ServiceA", "ServiceB", "Foobar", "Foo"])

    def test_list_specifications(self) -> None:
        """
        Test the definition of multiple specifications
        """

        @Specification(["ServiceA", Foobar], "ServiceB", Foo)
        class TestService:
            pass

        self.assertListEqual(self.__get_specification(TestService), ["ServiceA", "Foobar", "ServiceB", "Foo"])

    def test_duplicate_specifications(self) -> None:
        """
        Test the definition of multiple specifications with duplicated names
        """

        @Specification("ServiceA", "ServiceB", "ServiceA", Foobar, Foo, "Foobar")
        class TestService:
            pass

        self.assertListEqual(self.__get_specification(TestService), ["ServiceA", "ServiceB", "Foobar", "Foo"])

    def test_inheritance(self) -> None:
        """
        Test the inheritance of specifications
        """

        @Specification("BaseService")
        class BaseService:
            pass

        @Specification("ExtendedService")
        class ExtendedService(BaseService):
            pass

        @Specification("ExtendedService", ignore_parent=True)
        class ExtendedServiceOverride(BaseService):
            pass

        self.assertListEqual(self.__get_specification(BaseService), ["BaseService"])
        self.assertListEqual(self.__get_specification(ExtendedService), ["ExtendedService", "BaseService"])
        self.assertListEqual(self.__get_specification(ExtendedServiceOverride), ["ExtendedService"])

    def test_empty_specifications(self) -> None:
        """
        Empty or blank specification names must be rejected
        """
        invalid_values: tuple[Any, ...] = ("", "   ", [""], ["ServiceA", " "], [])
        for invalid in invalid_values:
            with self.assertRaises(ValueError, msg=f"Accepted {invalid!r}"):
                Specification(invalid)

        with self.assertRaises(ValueError):
            Specification("ServiceA", "")

    def test_forbidden_characters(self) -> None:
        """
        The special characters of LDAP filters must be rejected in specification
        names, as well as leading and trailing spaces
        """
        # Kept in line with what the LDAP filters escape
        self.assertEqual(FORBIDDEN_SPECIFICATION_CHARACTERS, set(ESCAPED_CHARACTERS) | {ESCAPE_CHARACTER})

        invalid_names = [f"spec{char}name" for char in sorted(FORBIDDEN_SPECIFICATION_CHARACTERS)]
        invalid_names += ["*", "a*b(c)", " spec", "spec ", "\tspec", "spec\n"]
        for name in invalid_names:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    check_specification_name(name)
                with self.assertRaises(ValueError):
                    Specification(name)
                with self.assertRaises(ValueError):
                    Specification([name])

        with self.assertRaises(TypeError):
            check_specification_name(123)

        for name in ("pelix.http.servlet", "my-spec", "my_spec", "ns:spec", "a/b", "a b", "Spec2"):
            with self.subTest(name=name):
                self.assertEqual(check_specification_name(name), name)


if __name__ == "__main__":
    unittest.main()
