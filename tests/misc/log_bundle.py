#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Test bundle for the log service

:author: Thomas Calmant
"""

from pelix.ipopo.decorators import ComponentFactory, Requires
from pelix.misc import LOG_SERVICE, LogService

# ------------------------------------------------------------------------------

__version_info__ = (3, 2, 2)
__version__ = ".".join(str(x) for x in __version_info__)

SIMPLE_FACTORY = "log.test.simple"

# ------------------------------------------------------------------------------
# Auto-instantiated component (tests the decorator)


@ComponentFactory(SIMPLE_FACTORY)
@Requires("logger", LOG_SERVICE)
class LoggerComponent:
    """
    Dummy instantiated component
    """

    logger: LogService

    def log(self, level, message):
        """
        Logs something

        :param level: Log level
        :param message: Log message
        """
        self.logger.log(level, message)

    @staticmethod
    def remove_name():
        """
        Removes __name__ from globals
        """
        del globals()["__name__"]
