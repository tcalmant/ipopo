#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
Defines the decorators associated shell completion handlers to a shell function

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1
:status: Alpha

..

    Copyright 2018 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

# Add some typing
try:
    # pylint: disable=W0611
    from typing import List, Dict
except ImportError:
    pass

try:
    # Everything here relies on readline
    import readline
except ImportError:
    readline = None

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


SVC_COMPLETER = "pelix.shell.completer"
""" Specification of a completer service """

PROP_COMPLETER_ID = "completer.id"
""" Completer service property: ID of the completer """

ATTR_COMPLETERS = "__pelix_shell_completers__"
""" Attribute added to methods to keep the list of completers """

# ------------------------------------------------------------------------------

DUMMY = "dummy"
""" Completer ID: a completer that does nothing """

BUNDLE = "pelix.bundle"
""" Completer ID: Pelix Bundle ID completer """

SERVICE = "pelix.service"
""" Completer ID: Pelix Service ID completer """

FACTORY = "ipopo.factory"
""" Completer ID: iPOPO Factory Name completer """

FACTORY_PROPERTY = "ipopo.factory.property"
""" Completer ID: iPOPO Property Name completer """

COMPONENT = "ipopo.component"
""" Completer ID: iPOPO Component Name completer """

# ------------------------------------------------------------------------------


class CompletionInfo:
    """
    Keep track of the configuration of a completion
    """

    __slots__ = ("__completers", "__multiple")

    def __init__(self, completers, multiple):
        # type: (List[str], bool) -> None
        """
        :param completers: The list of completers IDs
        :param multiple: Flag indicating the repetition of the last completer
        """
        self.__completers = completers or []
        self.__multiple = multiple

    @property
    def completers(self):
        """
        List of IDs of shell completers
        """
        return self.__completers[:]

    @property
    def multiple(self):
        """
        Flag indicating of the last completer can be reused multiple times
        """
        return self.__multiple


class Completion:
    # pylint: disable=R0903
    """
    Decorator that sets up the arguments completion of a shell method
    """

    def __init__(self, *completers, **kwargs):
        # type: (List[str], Dict[str, bool]) -> None
        """
        :param completers: A list of IDs (str) of argument completers
        :param multiple: If True, the last completer is reused multiple times
        """
        self._completers = completers  # type: List[str]
        self._multiple = kwargs.get("multiple", False)

    def __call__(self, method):
        """
        Adds a CoreCompleter with the list of completers as metadata of the
        method.
        Does nothing if the readline library isn't available

        :param method: Decorated method
        :return: The method with a new metadata for the Pelix Shell
        """
        if readline is not None and self._completers:
            # No need to setup completion if readline isn't available
            setattr(
                method,
                ATTR_COMPLETERS,
                CompletionInfo(self._completers, self._multiple),
            )

        return method
