#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
:author: Thomas Calmant
:copyright: Copyright 2025, Thomas Calmant
:license: Apache License 2.0
:version: 3.1.0

..

    Copyright 2025 Thomas Calmant

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

import unittest
from typing import Any

try:
    # Try to import modules
    import multiprocessing
    from multiprocessing import Process, Queue

    # IronPython fails when creating a queue
    Queue()

    # Trick to avoid pytest hanging
    multiprocessing.set_start_method("spawn", force=True)
except ImportError:
    # Some interpreters don't have support for multiprocessing
    raise unittest.SkipTest("Interpreter doesn't support multiprocessing")

try:
    # Trick to use coverage in sub-processes, from:
    # http://blog.schettino72.net/posts/python-code-coverage-multiprocessing.html
    import coverage

    class WrappedProcess(Process):
        def _bootstrap(self, *args: Any, **kwargs: Any) -> int:
            cov = coverage.Coverage(data_suffix=True)
            cov.start()
            try:
                return Process._bootstrap(self, *args, **kwargs)
            finally:
                cov.stop()
                cov.save()

except ImportError:
    WrappedProcess = Process
