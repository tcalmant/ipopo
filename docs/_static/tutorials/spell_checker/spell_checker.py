#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
The spell_checker component uses the dictionary services to check the spell of
a given text.
"""

import re

from spell_checker_api import SpellChecker, SpellDictionary

from pelix.framework import BundleContext
from pelix.internals.registry import ServiceReference
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Instantiate,
    Invalidate,
    Provides,
    Requires,
    UnbindField,
    Validate,
)


# Name the component factory
@ComponentFactory("spell_checker_factory")
# Provide a Spell Checker service
@Provides(SpellChecker)
# Consume all Spell Dictionary services available (aggregate them)
@Requires("_spell_dictionaries", SpellDictionary, aggregate=True)
# Automatic instantiation
@Instantiate("spell_checker_instance")
class SpellCheckerImpl:
    """
    A component that uses spell dictionary services to check the spelling of
    given texts.
    """

    # We can declare the type of injected fields
    _spell_dictionaries: list[SpellDictionary]

    def __init__(self) -> None:
        """
        Define class members
        """
        # the list of available dictionaries, constructed
        self.languages: dict[str, SpellDictionary] = {}

        # list of some punctuation marks could be found in the given passage,
        # internal
        self.punctuation_marks: set[str] = set()

    @BindField("_spell_dictionaries")
    def bind_dict(
        self, field: str, service: SpellDictionary, svc_ref: ServiceReference[SpellDictionary]
    ) -> None:
        """
        Called by iPOPO when a spell dictionary service is bound to this
        component
        """
        # Extract the dictionary language from its properties
        language = svc_ref.get_property("language")

        # Store the service according to its language
        self.languages[language] = service

    @UnbindField("_spell_dictionaries")
    def unbind_dict(
        self, field: str, service: SpellDictionary, svc_ref: ServiceReference[SpellDictionary]
    ) -> None:
        """
        Called by iPOPO when a dictionary service has gone away
        """
        # Extract the dictionary language from its properties
        language = svc_ref.get_property("language")

        # Remove it from the computed storage
        # The injected list of services is updated by iPOPO
        del self.languages[language]

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        This spell checker has been validated, i.e. at least one dictionary
        service has been bound.
        """
        # Set up internal members
        self.punctuation_marks = {",", ";", ".", "?", "!", ":", " "}
        print("A spell checker has been started")

    @Invalidate
    def invalidate(self, context: BundleContext) -> None:
        """
        The component has been invalidated
        """
        self.punctuation_marks = set()
        print("A spell checker has been stopped")

    def check(self, passage, language="EN"):
        # list of words to be checked in the given passage
        # without the punctuation marks
        checked_list = re.split("([!,?.:; ])", passage)
        try:
            # Get the dictionary corresponding to the requested language
            dictionary = self.languages[language]
        except KeyError:
            # Not found
            raise KeyError(f"Unknown language: {language}")

        # Do the job, calling the found service
        return [
            word
            for word in checked_list
            if word not in self.punctuation_marks and not dictionary.check_word(word)
        ]
