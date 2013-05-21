#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Defines the Qt main frame component

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: GPLv3
:version: 0.1
:status: Alpha
"""

# Module version
__version_widget__ = (0, 1, 0)
__version__ = ".".join(map(str, __version_widget__))

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# PyQt4
import PyQt4.QtGui as QtGui
import PyQt4.uic as uic

# iPOPO
from pelix.ipopo.decorators import ComponentFactory, Requires, Provides, \
    Validate, Invalidate, BindField, UnbindField, Instantiate

# Standard library
import os
import logging

# ------------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

class _QtMainFrame(QtGui.QMainWindow):
    """
    Represents the UI, loaded from a UI file
    """
    def __init__(self, controller, ui_file):
        """
        Sets up the frame
        """
        # Parent constructor
        QtGui.QMainWindow.__init__(self)

        # Store the controller
        self.__controller = controller

        # Load the frame UI
        uic.loadUi(ui_file, self)

        # Connect to signals
        self.action_quit.triggered.connect(controller.quit)
        self.action_about.triggered.connect(self.__about)
        self.action_about_qt.triggered.connect(self.__about_qt)


    def __about(self):
        """
        About signal handler
        """
        QtGui.QMessageBox.about(self, "About...", "Some text here")


    def __about_qt(self):
        """
        About Qt signal handler
        """
        QtGui.QMessageBox.aboutQt(self)

# ------------------------------------------------------------------------------

@ComponentFactory("MainFrameFactory")
@Requires("_qt_loader", 'qt.ui')
@Requires('_widgets_svc', 'qt.widget', aggregate=True, optional=True,
          spec_filter="(placement=main)")
@Provides('qt.frame.main')
@Instantiate("MainFrame")
class MainFrame(object):
    """
    The main frame component
    """
    def __init__(self):
        """
        Sets up the component
        """
        # Bundle context
        self._context = None

        # Valid state flag
        self.__validated = False

        # Main frame
        self._frame = None

        # Qt Loader service
        self._qt_loader = None

        # Frameworks
        self._widgets_svc = None

        # Tabs
        self._widgets_tabs = {}


    def __make_ui(self):
        """
        Sets up the frame. Must be called from the UI thread
        """
        # Load the UI file
        ui_path = os.path.join(os.getcwd(), "main.ui")
        self._frame = _QtMainFrame(self, ui_path)

        # Show the frame
        self._frame.show()


    def __clear_ui(self):
        """
        Clears the UI. Must be called from the UI thread
        """
        # Close the window
        self._frame.hide()
        self._frame = None


    def get_frame(self):
        """
        Retrieves the main frame object
        """
        return self._frame


    def quit(self):
        """
        Stops the framework
        """
        self._context.get_bundle(0).stop()


    def __add_tab(self, widget_qt):
        """
        Adds a tab
        
        To run in the UI thread.
        """
        # Prepare the content
        name = widget_qt.get_name()
        widget = widget_qt.get_widget(self._frame)

        # Add the tab
        tab_bar = self._frame.tab_bar
        tab_bar.addTab(widget, name)

        # Store its widget
        self._widgets_tabs[name] = widget


    def __remove_tab(self, widget_qt):
        """
        Removes a tab
        
        To run in the UI thread.
        """
        # Get component name
        name = widget_qt.get_name()

        # Pop its widget
        widget = self._widgets_tabs.pop(name)

        # Remove the tab
        tab_bar = self._frame.tab_bar
        index = tab_bar.indexOf(widget)
        if index > -1:
            # Found it
            tab_bar.removeTab(index)

        # Clean the component
        widget_qt.clean(self._frame)


    @BindField('_widgets_svc')
    def bind_widget(self, field, service, reference):
        """
        Widget service bound
        """
        if self.__validated:
            self._qt_loader.run_on_ui(self.__add_tab, service)


    @UnbindField('_widgets_svc')
    def unbind_widget(self, field, service, reference):
        """
        Widget service gone
        """
        if self.__validated:
            self._qt_loader.run_on_ui(self.__remove_tab, service)


    @Validate
    def validate(self, context):
        """
        Component validated
        
        :param context: Bundle context
        """
        self._context = context
        self._qt_loader.run_on_ui(self.__make_ui)

        # Make tabs for already known widgets
        if self._widgets_svc:
            for service in self._widgets_svc:
                self._qt_loader.run_on_ui(self.__add_tab, service)

        # Flag to allow un/bind probes to work
        self.__validated = True


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        
        :param context: Bundle context
        """
        # De-activate binding call backs
        self.__validated = False

        # Removes tabs
        if self._widgets_svc:
            for service in self._widgets_svc:
                self._qt_loader.run_on_ui(self.__remove_tab, service)

        # Clear the UI
        self._qt_loader.run_on_ui(self.__clear_ui)

        self._context = None
