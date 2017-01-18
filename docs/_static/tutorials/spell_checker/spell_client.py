#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
This bundle defines a component that consumes a spell checker.
It provides a shell command service, registering a "spell" command that can be
used in the shell of Pelix.

It uses a dictionary service to check for the proper spelling of a word by check
for its existence in the dictionary.
"""

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Provides, \
    Validate, Invalidate, Requires, Instantiate

# Specification of a command service for the Pelix shell
from pelix.shell import SHELL_COMMAND_SPEC


# Name the component factory
@ComponentFactory("spell_client_factory")
# Consume a single Spell Checker service
@Requires("_spell_checker", "spell_checker_service")
# Provide a shell command service
@Provides(SHELL_COMMAND_SPEC)
# Automatic instantiation
@Instantiate("spell_client_instance")
class SpellClient(object):
    """
    A component that provides a shell command (spell.spell), using a
    Spell Checker service.
    """

    def __init__(self):
        """
        Defines class members
        """
        # the spell checker service
        self._spell_checker = None

    @Validate
    def validate(self, context):
        """
        Component validated, just print a trace to visualize the event.
        Between this call and the call to invalidate, the _spell_checker member
        will point to a valid spell checker service.
        """
        print('A client for spell checker has been started')

    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated, just print a trace to visualize the event
        """
        print('A spell client has been stopped')

    def get_namespace(self):
        """
        Retrieves the name space of this shell command provider.
        Look at the shell tutorial for more information.
        """
        return "spell"

    def get_methods(self):
        """
        Retrieves the list of (command, method) tuples for all shell commands
        provided by this component.
        Look at the shell tutorial for more information.
        """
        return [("spell", self.spell)]

    def spell(self, io_handler):
        """
        Reads words from the standard input and checks for their existence
        from the selected dictionary.

        :param io_handler: A utility object given by the shell to interact with
                           the user.
        """
        # Request the language of the text to the user
        passage = None
        language = io_handler.prompt("Please enter your language, EN or FR: ")
        language = language.upper()

        while passage != 'quit':
            # Request the text to check
            passage = io_handler.prompt(
                "Please enter your paragraph, or 'quit' to exit:\n")

            if passage and passage != 'quit':
                # A text has been given: call the spell checker, which have been
                # injected by iPOPO.
                misspelled_words = self._spell_checker.check(passage, language)
                if not misspelled_words:
                    io_handler.write_line("All words are well spelled!")
                else:
                    io_handler.write_line(
                        "The misspelled words are: {0}", misspelled_words)
