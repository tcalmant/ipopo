#!/usr/bin/env python3
"""
Specification of the Hello World service
"""

from typing import Protocol

from pelix.constants import Specification


@Specification("sample.hello")
class HelloWorld(Protocol):
    """
    Hello world specification: definition of the methods a component providing
    that service must implement
    """

    def hello(self, name: str) -> None:
        """
        Prints hello
        """
        ...

    def bye(self, name: str) -> None:
        """
        Prints bye
        """
        ...
