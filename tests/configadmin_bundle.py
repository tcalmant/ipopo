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

@ComponentFactory()
@Provides(services.SERVICE_CONFIGADMIN_MANAGED)
@Property('_config_pid', constants.SERVICE_PID, 'configadmin-test-pid')
@Instantiate("configadmin-test")
class Configurable(object):
    """
    Configurable component
    """
    def __init__(self):
        """
        """
        self.value = None
        self.deleted = False


    def updated(self, properties):
        """
        """
        if properties is None:
            self.deleted = True
            print('Config deleted')
            return

        self.value = properties.get('config.value', '<not set>')
        print('Config updated:', self.value)
