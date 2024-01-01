#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Tests the framework events.

:author: Thomas Calmant
"""

import unittest
from typing import List, Protocol

from pelix.constants import PELIX_SPECIFICATION_FIELD, Specification


class Foobar(Protocol):
    """
    Sample protocol, using class name
    """

    pass


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
    def __get_specification(clazz) -> List[str]:
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


if __name__ == "__main__":
    unittest.main()
