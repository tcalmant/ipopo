#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Test bundle for the log service

:author: Thomas Calmant
"""

# iPOPO
from pelix.ipopo.decorators import ComponentFactory, Requires

# Log service
from pelix.misc import LOG_SERVICE

# ------------------------------------------------------------------------------

__version__ = (1, 0, 0)

SIMPLE_FACTORY = "log.test.simple"

# ------------------------------------------------------------------------------
# Auto-instantiated component (tests the decorator)


@ComponentFactory(SIMPLE_FACTORY)
@Requires("logger", LOG_SERVICE)
class LoggerComponent(object):
    """
    Dummy instantiated component
    """
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
        del globals()['__name__']

