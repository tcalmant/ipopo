#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Simple bundle defining a class used as provided service type

:author: Thomas Calmant
"""

__version_info__ = (1, 0, 1)
__version__ = ".".join(str(x) for x in __version_info__)


class IEchoService:
    """
    Interface of an echo service
    """
    def __init__(self):
        """
        Empty constructor
        """
        pass

    def echo(self, value):
        """
        Returns the given value
        """
        pass
