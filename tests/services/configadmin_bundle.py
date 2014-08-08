#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Bundle defining a component to be updated by ConfigAdmin

:author: Thomas Calmant
"""

from pelix.ipopo.decorators import ComponentFactory, Property, Provides, \
    Instantiate

import pelix.constants as constants
import pelix.services as services

# ------------------------------------------------------------------------------

CONFIG_PID = 'test.ca.bundle'

# ------------------------------------------------------------------------------


@ComponentFactory()
@Provides(services.SERVICE_CONFIGADMIN_MANAGED)
@Property('_config_pid', constants.SERVICE_PID, CONFIG_PID)
@Instantiate("configadmin-test")
class Configurable(object):
    """
    Configurable component
    """
    def __init__(self):
        """
        Sets up members
        """
        self.value = None
        self.deleted = False
        self.call_count = 0

    def reset(self):
        """
        Resets the flags
        """
        self.value = None
        self.deleted = False
        self.call_count = 0

    def updated(self, properties):
        """
        Called by the ConfigurationAdmin service
        """
        self.call_count += 1

        if properties is None:
            # Deleted
            self.value = None
            self.deleted = True
            return

        else:
            # Updated
            self.value = properties.get('config.value', '<not set>')
