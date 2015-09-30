#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""
:author: Thomas Calmant
:copyright: Copyright 2015, isandlaTech
:license: Apache License 2.0
:version: 0.0.1
:status: Alpha

..

    Copyright 2015 isandlaTech

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

try:
    import unittest2 as unittest
except ImportError:
    import unittest

try:
    # Try to import modules
    from multiprocessing import Process, Queue
    # IronPython fails when creating a queue
    Queue()
except ImportError:
    # Some interpreters don't have support for multiprocessing
    raise unittest.SkipTest("Interpreter doesn't support multiprocessing")

try:
    # Trick to use coverage in sub-processes, from:
    # http://blog.schettino72.net/posts/python-code-coverage-multiprocessing.html
    from coverage.control import coverage

    class WrappedProcess(Process):
        def _bootstrap(self):
            cov = coverage(data_suffix=True)
            cov.start()
            try:
                return Process._bootstrap(self)
            finally:
                cov.stop()
                cov.save()
except ImportError:
    WrappedProcess = Process
