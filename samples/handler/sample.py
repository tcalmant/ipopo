#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Sample usage of the Logger handler.

Use the samples/run_handler.py script to run the framework that corresponds to
this sample.

:author: Thomas Calmant
:copyright: Copyright 2023, Thomas Calmant
:license: Apache License 2.0
:version: 1.0.2

..

    Copyright 2023 Thomas Calmant

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        https://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import logging
from pelix.framework import BundleContext
from pelix.ipopo.decorators import (
    ComponentFactory,
    Validate,
    Invalidate,
    Instantiate,
)
from samples.handler.decorator import Logger

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (1, 0, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------


@ComponentFactory()
@Logger("_logger")
@Instantiate("sample-logger-component")
class SampleLoggerComponent:
    """
    Sample component that uses the logger handler
    """

    # Define the injected field
    _logger: logging.Logger

    @Validate
    def validate(self, context: BundleContext) -> None:
        """
        Component validated
        """
        self._logger.debug("Validated ! (Logged from the component)")

    @Invalidate
    def invalidate(self, context: BundleContext) -> None:
        """
        Component invalidated
        """
        self._logger.debug("Invalidated :( (Logged from the component)")
