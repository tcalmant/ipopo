#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Defines a Qt widget component

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.1
:status: Alpha
"""

# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(map(str, __version_info__))

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# iPOPO
from pelix.ipopo.decorators import ComponentFactory, Provides, Property, \
    Instantiate
import pelix.ipopo.constants as constants

# PyQt4
import PyQt4.QtGui as QtGui

# ------------------------------------------------------------------------------

@ComponentFactory('widget-factory')
@Provides('qt.widget')
@Property('_placement', 'placement', 'main')
@Property('_name', constants.IPOPO_INSTANCE_NAME)
@Instantiate('widget-0')
class DummyWidget(object):
    """
    The widget to add to the main frame
    """
    def __init__(self):
        """
        Sets up the component
        """
        # The placement property
        self._placement = None

        # Instance name
        self._name = None

        # The created widget
        self._widget = None


    def get_name(self):
        """
        Returns the instance name
        """
        return self._name


    def get_widget(self, parent):
        """
        Makes the Qt widget that will show the framework instance information.
        
        This method must/will be be called from the UI thread.
        
        :return: A QWidget object
        """
        if self._widget:
            return self._widget

        # Make a QLabel
        self._widget = QtGui.QLabel("Your are watching label {0}"\
                                    .format(self._name))

        return self._widget


    def clean(self, parent):
        """
        Cleans the UI elements.
        
        This method must/will be be called from the UI thread.
        """
        # Clear references
        self._widget = None
