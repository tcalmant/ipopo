#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Module defining the types used in the Spell Checker
"""

from typing import Protocol

from pelix.constants import Specification


# Set the name of the specification
@Specification("spell_dictionary_service")
class SpellDictionary(Protocol):
    """
    Definition of the spell dictionary service
    """

    def check_word(self, word: str) -> bool:
        """
        Determines if the given word is contained in the dictionary.

        @param word the word to be checked.
        @return True if the word is in the dictionary, False otherwise.
        """
        ...


@Specification("spell_checker_service")
class SpellChecker(Protocol):
    """
    Definition of the spell checker service
    """

    def check(self, passage: str, language: str = "EN") -> list[str] | None:
        """
        Checks the given passage for misspelled words.

        :param passage: the passage to spell check.
        :param language: language of the spell dictionary to use
        :return: An array of misspelled words or null if no words are misspelled
        :raise KeyError: No dictionary for this language
        """
        ...
