#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Pelix/Qt application bootstrap.

Loads Qt in the main thread and starts a Pelix framework in a second one

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

# Import Pelix
import pelix.framework

# Standard library
import logging
import threading

def main():
    """
    Loads Qt and the framework.
    Blocks while Qt or the framework are running.
    """
    # Import the Qt bridge as late as possible, to avoid unwanted module
    # loading
    import qt_bridge

    # Load Qt
    qt_loader = qt_bridge.QtLoader()
    qt_loader.setup()

    # Prepare the framework, with iPOPO and a shell
    framework = pelix.framework.create_framework(['pelix.ipopo.core',
                                                  'pelix.shell.core',
                                                  'pelix.shell.console',
                                                  'pelix.shell.ipopo'])
    context = framework.get_bundle_context()

    # Register the Qt bridge as a service
    context.register_service("qt.ui", qt_loader, {})

    # Run the framework in a new thread
    thread = threading.Thread(target=run_framework, args=(framework,
                                                          qt_loader.stop))
    thread.start()

    # Run the Qt loop (blocking)
    qt_loader.loop()

    # Stop the framework (if still there)
    framework.stop()
    thread.join(1)


def run_framework(framework, on_stop):
    """
    Handles Pelix framework starting and main loop.
    Waits for the framework to stop before stopping Qt and returning.

    This method should be executed in a new thread.

    :param framework: The Pelix framework to run
    :param on_stop: Method to call once the framework has stopped
    """
    try:
        # Start the framework
        context = framework.get_bundle_context()
        framework.start()

        # [...] Install bundles, instantiate components [...]
        context.install_bundle('frame').start()
        context.install_bundle('widget').start()

        # Wait for the framework to stop
        framework.wait_for_stop()

    finally:
        # Stop on errors or if the framework stopped
        if on_stop is not None:
            # Notify the given method
            on_stop()

# Classic...
if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
