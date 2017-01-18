#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Starts a Pelix framework and installs the Spell Checker bundles
"""

# Pelix framework module and utility methods
import pelix.framework
from pelix.utilities import use_service

# Standard library
import logging


def main():
    """
    Starts a Pelix framework and waits for it to stop
    """
    # Prepare the framework, with iPOPO and the shell console
    # Warning: we only use the first argument of this method, a list of bundles
    framework = pelix.framework.create_framework((
        # iPOPO
        "pelix.ipopo.core",
        # Shell core (engine)
        "pelix.shell.core",
        # Text console
        "pelix.shell.console"))

    # Start the framework, and the pre-installed bundles
    framework.start()

    # Get the bundle context of the framework, i.e. the link between the
    # framework starter and its content.
    context = framework.get_bundle_context()

    # Start the spell dictionary bundles, which provide the dictionary services
    context.install_bundle("spell_dictionary_EN").start()
    context.install_bundle("spell_dictionary_FR").start()

    # Start the spell checker bundle, which provides the spell checker service.
    context.install_bundle("spell_checker").start()

    # Sample usage of the spell checker service
    # 1. get its service reference, that describes the service itself
    ref_config = context.get_service_reference("spell_checker_service")

    # 2. the use_service method allows to grab a service and to use it inside a
    # with block. It automatically releases the service when exiting the block,
    # even if an exception was raised
    with use_service(context, ref_config) as svc_config:
        # Here, svc_config points to the spell checker service
        passage = "Welcome to our framwork iPOPO"
        print("1. Testing Spell Checker:", passage)
        misspelled_words = svc_config.check(passage)
        print(">  Misspelled_words are:", misspelled_words)

    # Start the spell client bundle, which provides a shell command
    context.install_bundle("spell_client").start()

    # Wait for the framework to stop
    framework.wait_for_stop()


# Classic entry point...
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
