#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Optional audit sink of the security layer.

Installing this bundle instantiates a component which writes to the
``pelix.security.audit`` logger the security events posted through EventAdmin
(``pelix/security/*``: authentication successes and failures, refused accesses) and
the reveals of :class:`~pelix.security.Secret` values (the
``pelix.security.secret.reveal`` audit event, with the current subject). It never logs
a secret value: the properties holding a :class:`~pelix.security.Secret` or named
after :data:`~pelix.security.DEFAULT_SECRET_KEYS` are left out.

:author: Thomas Calmant
:copyright: Copyright 2026, Thomas Calmant
:license: Apache License 2.0
:version: 3.3.0

..

    Copyright 2026 Thomas Calmant

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

import fnmatch
import logging
import sys
import threading
from typing import TYPE_CHECKING, Any

from pelix import services
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Invalidate, Property, Provides, Validate
from pelix.security import (
    AUDIT_SECRET_REVEAL,
    DEFAULT_SECRET_KEYS,
    TOPIC_ACCESS_DENIED,
    TOPIC_AUTH_FAILURE,
    Secret,
    get_current_subject,
)

if TYPE_CHECKING:
    from pelix.framework import BundleContext

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = ["AUDIT_LOGGER", "FACTORY_AUDIT", "AuditSink"]

# ------------------------------------------------------------------------------

AUDIT_LOGGER = "pelix.security.audit"
""" Name of the logger the audit trail is written to """

FACTORY_AUDIT = "pelix.security.audit.factory"
""" Factory of the audit sink component """

_audit_logger = logging.getLogger(AUDIT_LOGGER)

# Audit hooks can't be removed: a single one is installed for the process, and it
# writes only while an audit sink is valid
_hook_lock = threading.Lock()
_hook_installed = False
_active_sinks = 0

# ------------------------------------------------------------------------------


def _reveal_hook(event: str, args: tuple[Any, ...]) -> None:
    """
    Writes the reveals of secrets while an audit sink is valid
    """
    if event == AUDIT_SECRET_REVEAL and _active_sinks:
        owner, module = args
        _audit_logger.info(
            "secret revealed: owner=%r module=%r subject=%r", owner, module, get_current_subject().name
        )


def _is_secret_key(key: str) -> bool:
    """
    Tells whether a property name looks like the one of a secret
    """
    lower_key = key.lower()
    return any(fnmatch.fnmatchcase(lower_key, pattern) for pattern in DEFAULT_SECRET_KEYS)


@ComponentFactory(FACTORY_AUDIT)
@Provides(services.ServiceEventHandler)
@Property("_event_topics", services.PROP_EVENT_TOPICS, ["pelix/security/*"])
@Instantiate("pelix-security-audit")
class AuditSink(services.ServiceEventHandler):
    """
    Writes the security events and the reveals of secrets to the audit logger
    """

    _event_topics: list[str]

    @Validate
    def _validate(self, _: "BundleContext") -> None:
        global _hook_installed, _active_sinks
        with _hook_lock:
            if not _hook_installed:
                sys.addaudithook(_reveal_hook)
                _hook_installed = True
            _active_sinks += 1

    @Invalidate
    def _invalidate(self, _: "BundleContext") -> None:
        global _active_sinks
        with _hook_lock:
            _active_sinks -= 1

    def handle_event(self, topic: str, properties: dict[str, Any]) -> None:
        """
        Writes an event, without the properties which could hold a secret
        """
        level = logging.WARNING if topic in (TOPIC_AUTH_FAILURE, TOPIC_ACCESS_DENIED) else logging.INFO
        details = " ".join(
            f"{key}={value!r}"
            for key, value in sorted(properties.items())
            if not isinstance(value, Secret) and not _is_secret_key(key)
        )
        _audit_logger.log(level, "%s %s", topic, details)
