#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix miscellaneous modules

:author: Thomas Calmant
:copyright: Copyright 2018, Thomas Calmant
:license: Apache License 2.0
:version: 0.8.1

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

# Module version
__version_info__ = (0, 8, 1)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

FACTORY_EVENT_ADMIN_PRINTER = "pelix-misc-eventadmin-printer-factory"
"""
Name of the EventAdmin printer factory.
"""

# ------------------------------------------------------------------------------

PROPERTY_LOG_LEVEL = "pelix.log.level"
"""
The log level property, which can be an integer or a string from the logging
module (default: logging.INFO)
"""

PROPERTY_LOG_MAX_ENTRIES = "pelix.log.max_entries"
"""
The maximum number of log entries to store in memory (default: 100)
"""

LOG_SERVICE = "pelix.log"
"""
The log service, providing:
- log(level, message, exception=None, reference=None): logs an entry with
  the given log level, human-readable message, exception (if any) and
  associated service reference (if any)
"""

LOG_READER_SERVICE = "pelix.log.reader"
"""
The log reader service, providing:
- add_log_listener(listener): subscribe a listener to log events
- remove_log_listener(listener): unsubscribe a listener from log events
- get_log(): returns the list of stored log entries

Log listeners must provide a ``logged(entry)`` method, accepting a ``LogEntry``
object as parameter.
"""
