#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
The spell_checker component uses the dictionary services to check the spell of
a given text.
"""

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Provides, \
    Validate, Invalidate, Requires, Instantiate, BindField, UnbindField

# Standard library
import re


# Name the component factory
@ComponentFactory("spell_checker_factory")
# Provide a Spell Checker service
@Provides("spell_checker_service")
# Consume all Spell Dictionary services available (aggregate them)
@Requires("_spell_dictionaries", "spell_dictionary_service", aggregate=True)
# Automatic instantiation
@Instantiate("spell_checker_instance")
class SpellChecker(object):
    """
    A component that uses spell dictionary services to check the spelling of
    given texts.
    """

    def __init__(self):
        """
        Define class members
        """
        # the spell dictionary service, injected list
        self._spell_dictionaries = []

        # the list of available dictionaries, constructed
        self.languages = {}

        # list of some punctuation marks could be found in the given passage,
        # internal
        self.punctuation_marks = None

    @BindField('_spell_dictionaries')
    def bind_dict(self, field, service, svc_ref):
        """
        Called by iPOPO when a spell dictionary service is bound to this
        component
        """
        # Extract the dictionary language from its properties
        language = svc_ref.get_property('language')

        # Store the service according to its language
        self.languages[language] = service

    @UnbindField('_spell_dictionaries')
    def unbind_dict(self, field, service, svc_ref):
        """
        Called by iPOPO when a dictionary service has gone away
        """
        # Extract the dictionary language from its properties
        language = svc_ref.get_property('language')

        # Remove it from the computed storage
        # The injected list of services is updated by iPOPO
        del self.languages[language]

    @Validate
    def validate(self, context):
        """
        This spell checker has been validated, i.e. at least one dictionary
        service has been bound.
        """
        # Set up internal members
        self.punctuation_marks = {',', ';', '.', '?', '!', ':', ' '}
        print('A spell checker has been started')

    @Invalidate
    def invalidate(self, context):
        """
        The component has been invalidated
        """
        self.punctuation_marks = None
        print('A spell checker has been stopped')

    def check(self, passage, language="EN"):
        """
        Checks the given passage for misspelled words.

        :param passage: the passage to spell check.
        :param language: language of the spell dictionary to use
        :return: An array of misspelled words or null if no words are misspelled
        :raise KeyError: No dictionary for this language
        """
        # list of words to be checked in the given passage
        # without the punctuation marks
        checked_list = re.split("([!,?.:; ])", passage)
        try:
            # Get the dictionary corresponding to the requested language
            dictionary = self.languages[language]
        except KeyError:
            # Not found
            raise KeyError('Unknown language: {0}'.format(language))

        # Do the job, calling the found service
        return [word for word in checked_list
                if word not in self.punctuation_marks
                and not dictionary.check_word(word)]
