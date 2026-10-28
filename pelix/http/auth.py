#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Authentication support for the Pelix HTTP services.

Provides the HTTP Basic authentication scheme and the logic shared by the HTTP
service implementations to authenticate requests with the ``pelix.security``
services.

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

import base64
import binascii
import importlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from pelix import http
from pelix.ipopo.decorators import ComponentFactory, Provides
from pelix.security import (
    ANONYMOUS,
    ATTRIBUTE_SESSION_ID,
    AuthenticationFailed,
    Credentials,
    Subject,
    UsernamePassword,
)

# ------------------------------------------------------------------------------

# Module version
__version_info__ = (3, 3, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

__all__ = [
    "DEFAULT_REALM",
    "SERVLET_AUTH_PARAMETERS",
    "SESSION_METHOD",
    "TRANSPORT",
    "AuthDecision",
    "BasicHttpAuthenticator",
    "BasicHttpAuthenticatorComponent",
    "authenticate_request",
    "login",
    "make_challenges",
    "restore",
]

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

DEFAULT_REALM = "Pelix"
""" Default protection space given in the authentication challenges """

SERVLET_AUTH_PARAMETERS = (http.HTTP_AUTH_REQUIRED, http.HTTP_AUTH_REALM)
""" Servlet service properties overriding the authentication configuration """

# ------------------------------------------------------------------------------


def _quote(value: str) -> str:
    """
    Formats a quoted-string parameter value (RFC 9110, section 5.6.4)

    :param value: The raw value
    :return: The quoted value
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


class BasicHttpAuthenticator(http.HttpAuthenticator):
    """
    HTTP Basic authentication scheme (RFC 7617): a user name and a password,
    sent in clear text in the ``Authorization`` header.

    .. warning:: Only use it over HTTPS: anyone who can read the traffic can
       read the password.
    """

    SCHEME = "Basic"

    def get_scheme(self) -> str:
        return self.SCHEME

    def extract_credentials(self, headers: http.HeadersView) -> Credentials | None:
        authorization = headers.get("Authorization")
        if not authorization:
            return None

        scheme, _, token = str(authorization).strip().partition(" ")
        if scheme.lower() != self.SCHEME.lower():
            # Another scheme: let another authenticator handle it
            return None

        try:
            decoded = base64.b64decode(token.strip(), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as ex:
            raise AuthenticationFailed("Malformed Basic credentials") from ex

        username, separator, password = decoded.partition(":")
        if not separator or not username:
            raise AuthenticationFailed("Malformed Basic credentials")

        return UsernamePassword(username, password)

    def get_challenge(self, realm: str) -> str:
        # The charset parameter tells clients to encode non-ASCII credentials in UTF-8
        return f'{self.SCHEME} realm={_quote(realm)}, charset="UTF-8"'


@ComponentFactory(http.FACTORY_HTTP_AUTH_BASIC)
@Provides(http.HttpAuthenticator)
class BasicHttpAuthenticatorComponent(BasicHttpAuthenticator):
    """
    HTTP Basic authentication service, to instantiate with iPOPO
    """


# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthDecision:
    """
    Result of the authentication of a request
    """

    subject: Subject
    """ The subject the request must be handled as (anonymous if refused) """

    refused: bool = False
    """ If True, the request must be answered with a 401 error """


SESSION_METHOD = "form"
""" Mechanism name of the users who logged in with ``request.login()`` (the Servlet ``FORM``) """

TRANSPORT = "http"
""" Transport name given to the security layer, telling HTTP logins from others in audits """


def _authenticate(credentials: Credentials, source: str | None, method: str) -> Subject:
    """
    Checks credentials with the ``pelix.security`` services

    :param credentials: The credentials extracted from the request
    :param source: The address of the client, for the brute-force throttle
    :param method: The authentication scheme which extracted the credentials
    :return: The authenticated subject
    :raise AuthenticationFailed: Wrong credentials, or locked out
    """
    # Looked up on each call: uninstalling the security bundle drops its module,
    # and a reference kept since the import would see the stopped one forever
    core = importlib.import_module("pelix.security.core")
    return core.authenticate(credentials, source, method=method, transport=TRANSPORT)


def login(username: str, password: str, source: str | None) -> Subject:
    """
    Authenticates a user from a login form, for the HTTP sessions

    :param username: The user name
    :param password: The password
    :param source: The address of the client, for the brute-force throttle
    :return: The authenticated subject
    :raise AuthenticationFailed: Wrong credentials, or locked out
    """
    return _authenticate(UsernamePassword(username, password), source, SESSION_METHOD)


def restore(username: str, session_id: str) -> Subject:
    """
    Rebuilds the subject of a user logged in an HTTP session: its groups and
    roles are those of now, without checking a password again

    :param username: The user name kept in the session
    :param session_id: The identifier of the session
    :return: The authenticated subject
    """
    # Not imported once: as in _authenticate(), the security bundle may have been reloaded
    core = importlib.import_module("pelix.security.core")
    return core.restore_subject(
        username, {ATTRIBUTE_SESSION_ID: session_id}, method=SESSION_METHOD, transport=TRANSPORT
    )


def make_challenges(authenticators: Iterable[http.HttpAuthenticator], realm: str) -> str | None:
    """
    Computes the value of the ``WWW-Authenticate`` header of a 401 response

    :param authenticators: The HTTP authenticator services
    :param realm: The protection space of the requested resource
    :return: The challenges, or None if there is no authenticator
    """
    challenges: list[str] = []
    for authenticator in authenticators:
        try:
            challenges.append(authenticator.get_challenge(realm))
        except Exception:
            _logger.exception("Error getting the challenge of %s", authenticator)

    return ", ".join(challenges) if challenges else None


def authenticate_request(
    authenticators: Iterable[http.HttpAuthenticator],
    headers: http.HeadersView,
    required: bool,
    source: str | None = None,
) -> AuthDecision:
    """
    Authenticates a request.

    Credentials are checked whenever the request carries some, even if the
    resource doesn't require them, so that the servlets can rely on the
    current subject (see :func:`pelix.security.get_current_subject`).
    Wrong credentials are always refused, as a client presenting them expects
    to be authenticated.

    This can take time, as checking a password is costly by design.

    :param authenticators: The HTTP authenticator services
    :param headers: The headers of the request
    :param required: If True, a request without credentials is refused
    :param source: The address of the client, for the brute-force throttle
    :return: The decision
    """
    for authenticator in authenticators:
        try:
            credentials = authenticator.extract_credentials(headers)
        except AuthenticationFailed as ex:
            _logger.info("Refused credentials: %s", ex)
            return AuthDecision(ANONYMOUS, True)
        except Exception:
            # Refuse rather than let a faulty authenticator let the request through
            _logger.exception("Error extracting credentials with %s", authenticator)
            return AuthDecision(ANONYMOUS, True)

        if credentials is None:
            continue

        try:
            subject = _authenticate(credentials, source, authenticator.get_scheme().lower())
        except AuthenticationFailed as ex:
            _logger.info("Authentication failed: %s", ex)
            return AuthDecision(ANONYMOUS, True)
        except Exception:
            _logger.exception("Error authenticating a request")
            return AuthDecision(ANONYMOUS, True)

        return AuthDecision(subject)

    # No credentials
    return AuthDecision(ANONYMOUS, required)
