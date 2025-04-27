#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Simple bundle defining a class used as provided service type

:author: Thomas Calmant
"""

__version_info__ = (3, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)


from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class IEchoService(Protocol):
    """
    Interface of an echo service
    """

    def echo(self, value: T) -> T:
        """
        Returns the given value
        """
        ...
